import type { ModelCheckResult, ModelProfilePayload } from "../components/ai/aiConfig";
import type {
  AdminDocumentAction,
  AdminDocumentDetail,
  AdminDocumentList,
  AdminDocumentPatch,
  AdminUserItem,
  AnswerDocument,
  AuditEventsResponse,
  AuthorizedCategory,
  EmbeddingJob,
  EmbeddingOverview,
  EmbeddingPreflight,
  LoginResponse,
  ModelRegistryState,
  PdfDraftListItem,
  QueryResponse,
  SearchMode,
  SearchResponse,
  EffectivityView,
  Excerpt,
  TextSpan,
  StagePolicy,
  UserInfo,
} from "../types";

function resolveApiBase(): string {
  const configured = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(
    /\/$/,
    "",
  );
  if (configured) return configured;
  if (
    typeof window !== "undefined" &&
    (window.location.hostname === "tauri.localhost" ||
      window.location.protocol === "tauri:" ||
      Boolean((window as unknown as { __TAURI__?: unknown }).__TAURI__))
  ) {
    return "http://127.0.0.1:8000";
  }
  return "";
}

const API_BASE = resolveApiBase();
let queryTimeoutMs = 50000;
let pdfWorkTimeoutMs = 130000;

export class ApiRequestError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly traceId?: string,
    readonly details?: Record<string, unknown>,
  ) {
    super(message);
  }
}

function bearerHeader(accessToken?: string): Record<string, string> {
  return accessToken ? { Authorization: "Bearer " + accessToken } : {};
}

function createTimeoutController(
  externalSignal?: AbortSignal | null,
  timeoutMs = 20000,
): { signal: AbortSignal; cleanup: () => void } {
  const controller = new AbortController();
  const onExternalAbort = () => controller.abort();
  if (externalSignal) {
    if (externalSignal.aborted) {
      controller.abort();
    } else {
      externalSignal.addEventListener("abort", onExternalAbort, { once: true });
    }
  }
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  return {
    signal: controller.signal,
    cleanup: () => {
      clearTimeout(timer);
      if (externalSignal) {
        externalSignal.removeEventListener("abort", onExternalAbort);
      }
    },
  };
}

async function request<T>(path: string, init: RequestInit): Promise<T> {
  const isForm = typeof FormData !== "undefined" && init.body instanceof FormData;
  const timeoutMs = path.startsWith("/api/v1/query/") || path.endsWith("/retry") ? queryTimeoutMs
    : ((path === "/api/v1/admin/documents/drafts" || path.endsWith("/reextract") ||
        path.endsWith("/reprocess")) && init.method === "POST") ||
        (path.startsWith("/api/v1/admin/documents/") && init.method === "PATCH") ? pdfWorkTimeoutMs
      : path.endsWith("/probe") ? 35000
        // A model check lists models and sends one request; a cold local model may load first.
        : path.endsWith("/model-registry/test") || /\/model-registry\/[^/]+\/test$/.test(path) ? 100000
        // Synthesis waits for a (possibly CPU-only) model; comprehensive search may embed.
        : path === "/api/v1/synthesis" ? 150000
        : path === "/api/v1/search/comprehensive" ? 60000
        // Embedding preflight probes the service and asks for a test vector (server cap 90 s).
        : path === "/api/v1/admin/embeddings/preflight" ||
            (path === "/api/v1/admin/embeddings/jobs" && init.method === "POST") ? 95000
          : 20000;
  const { signal, cleanup } = createTimeoutController(init.signal, timeoutMs);
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal,
      headers: {
        ...(isForm ? {} : { "Content-Type": "application/json" }),
        ...init.headers,
      },
    });
    if (!response.ok) {
      const body = (await response.json().catch(() => ({}))) as {
        message?: string;
        detail?: string;
        code?: string;
        trace_id?: string;
        details?: Record<string, unknown>;
      };
      throw new ApiRequestError(
        typeof body.message === "string"
          ? body.message
          : typeof body.detail === "string"
            ? body.detail
            : "Không thể hoàn tất yêu cầu.",
        response.status,
        body.code ?? "REQUEST_FAILED",
        body.trace_id,
        body.details,
      );
    }
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  } catch (caught) {
    // A client-side timeout aborts the internal signal only; surface it as a
    // readable error instead of the browser's raw "signal is aborted" message.
    if (signal.aborted && !init.signal?.aborted) {
      throw new ApiRequestError(
        "Máy chủ phản hồi quá lâu. Hãy thử lại sau.",
        408,
        "CLIENT_TIMEOUT",
      );
    }
    throw caught;
  } finally {
    cleanup();
  }
}

export function queryEvidence(
  payload: {
    question: string;
    scope: {
      scope_mode: "SELECTED" | "ALL_AUTHORIZED";
      category_ids: string[];
      document_types: string[];
      as_of_date: string;
    };
    facts: Array<{
      key: string;
      value: string;
      status: "user_confirmed" | "extracted_unconfirmed" | "inferred_uncertain";
      source?: string;
    }>;
    /** API mode only: try the external escalation model first ("Phân tích sâu"). */
    deep_analysis?: boolean;
  },
  options: { accessToken?: string; signal?: AbortSignal } = {},
): Promise<QueryResponse> {
  return request<QueryResponse>("/api/v1/query/evidence", {
    method: "POST",
    headers: bearerHeader(options.accessToken),
    signal: options.signal,
    body: JSON.stringify(payload),
  });
}

export async function getSystemMode(): Promise<{ effective_mode: string }> {
  const response = await request<{
    effective_mode: string; query_timeout_seconds?: number; pdf_timeout_seconds?: number;
  }>("/api/v1/system/mode", { method: "GET" });
  if (Number.isFinite(response.query_timeout_seconds) && Number(response.query_timeout_seconds) > 0) {
    queryTimeoutMs = Math.min(305000, Number(response.query_timeout_seconds) * 1000 + 5000);
  }
  if (Number.isFinite(response.pdf_timeout_seconds) && Number(response.pdf_timeout_seconds) > 0) {
    pdfWorkTimeoutMs = Math.min(610000, Number(response.pdf_timeout_seconds) * 1000 + 10000);
  }
  return response;
}

export interface AgentSession {
  session_id: string;
  expires_at: string;
  facts_revision: string;
  memory_revision: string;
}

export interface MemoryItem {
  id: string;
  kind: "message" | "preferences" | string;
  content: string;
  created_at: string;
  expires_at?: string | null;
}

export interface MemoryPreferences {
  enabled: boolean;
  default_category_ids: string[];
  default_as_of_date: string | null;
}

export type TurnPayload = Parameters<typeof queryEvidence>[0];

export function createAgentSession(
  accessToken: string,
  options: { signal?: AbortSignal } = {},
): Promise<AgentSession> {
  return request<AgentSession>("/api/v1/agent/sessions", {
    method: "POST",
    headers: bearerHeader(accessToken),
    signal: options.signal,
    body: JSON.stringify({ incognito: true }),
  });
}

export function deleteAgentSession(accessToken: string, sessionId: string): Promise<void> {
  return request<void>("/api/v1/agent/sessions/" + encodeURIComponent(sessionId), {
    method: "DELETE",
    headers: bearerHeader(accessToken),
  });
}

export function deleteSessionFact(accessToken: string, sessionId: string, key: string): Promise<void> {
  return request<void>(
    "/api/v1/agent/sessions/" + encodeURIComponent(sessionId) + "/facts?key=" + encodeURIComponent(key),
    { method: "DELETE", headers: bearerHeader(accessToken) },
  );
}

export async function listMemory(accessToken: string, sessionId: string): Promise<MemoryItem[]> {
  const response = await request<{ items: MemoryItem[] }>(
    "/api/v1/memory?session_id=" + encodeURIComponent(sessionId),
    { method: "GET", headers: bearerHeader(accessToken) },
  );
  return response.items;
}

export function deleteMemoryItem(
  accessToken: string,
  sessionId: string,
  itemId: string,
): Promise<void> {
  return request<void>(
    "/api/v1/memory/" + encodeURIComponent(itemId) + "?session_id=" + encodeURIComponent(sessionId),
    { method: "DELETE", headers: bearerHeader(accessToken) },
  );
}

export function clearMemory(accessToken: string, sessionId: string): Promise<void> {
  return request<void>("/api/v1/memory?session_id=" + encodeURIComponent(sessionId), {
    method: "DELETE",
    headers: bearerHeader(accessToken),
  });
}

export function getMemoryPreferences(
  accessToken: string,
  sessionId: string,
): Promise<MemoryPreferences> {
  return request<MemoryPreferences>(
    "/api/v1/memory/preferences?session_id=" + encodeURIComponent(sessionId),
    { method: "GET", headers: bearerHeader(accessToken) },
  );
}

export function setMemoryPreferences(
  accessToken: string,
  sessionId: string,
  preferences: MemoryPreferences,
): Promise<{ status: string }> {
  return request<{ status: string }>(
    "/api/v1/memory/preferences?session_id=" + encodeURIComponent(sessionId),
    { method: "PUT", headers: bearerHeader(accessToken), body: JSON.stringify(preferences) },
  );
}

export function cancelAgentTurn(
  accessToken: string,
  sessionId: string,
  turnId: string,
): Promise<{ status: string }> {
  return request<{ status: string }>(
    "/api/v1/agent/sessions/" + encodeURIComponent(sessionId) +
      "/turns/" + encodeURIComponent(turnId) + "/cancel",
    { method: "POST", headers: bearerHeader(accessToken) },
  );
}

const TURN_ERROR_MESSAGES: Record<string, string> = {
  SESSION_EXPIRED: "Phiên bộ nhớ đã hết hạn.",
  QUERY_TIMEOUT: "Tra cứu mất quá nhiều thời gian. Hãy thử lại.",
  QUERY_FAILED: "Không thể hoàn tất lượt tra cứu.",
  MEMORY_CAPACITY_EXCEEDED: "Bộ nhớ phiên đã đầy. Hãy xóa dữ liệu tạm rồi thử lại.",
  TURN_CANCELLED: "Đã dừng lượt tra cứu hiện tại.",
  REQUEST_CANCELLED: "Đã dừng lượt tra cứu hiện tại.",
  CITATION_INVALID: "Căn cứ không còn khớp với nguồn đã duyệt.",
};

type TurnEventData = Record<string, unknown> & { code?: string };

function parseSseBlock(block: string): { event: string; data: TurnEventData } | undefined {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  if (dataLines.length === 0) return undefined;
  try {
    const data: unknown = JSON.parse(dataLines.join("\n"));
    if (!data || typeof data !== "object" || Array.isArray(data)) throw new Error();
    return { event, data: data as TurnEventData };
  } catch {
    throw new ApiRequestError("Luồng kết quả không hợp lệ. Hãy thử lại.", 502, "STREAM_INVALID");
  }
}

async function readTurnStream(response: Response): Promise<QueryResponse> {
  const reader = response.body?.getReader();
  if (!reader) {
    throw new ApiRequestError("Luồng kết quả không khả dụng.", 502, "STREAM_UNAVAILABLE");
  }
  const decoder = new TextDecoder();
  let buffer = "";
  let evidence: QueryResponse["evidence"] = [];
  let analysis: Partial<QueryResponse> = {};
  let base: TurnEventData = {};
  let complete = false;
  let evidenceReceived = false;
  let analysisReceived = false;
  let queryId: string | undefined;
  let runId: string | undefined;
  let lastSequence = 0;

  const invalid = (): never => {
    throw new ApiRequestError("Luồng kết quả không hợp lệ. Hãy thử lại.", 502, "STREAM_INVALID");
  };

  const handle = (block: string) => {
    const parsed = parseSseBlock(block);
    if (!parsed) return;
    const { event, data } = parsed;
    if (event === "turn_error" || event === "turn_cancelled") {
      const code = typeof data.code === "string" ? data.code : "QUERY_FAILED";
      throw new ApiRequestError(
        TURN_ERROR_MESSAGES[code] ?? TURN_ERROR_MESSAGES.QUERY_FAILED,
        code === "SESSION_EXPIRED" ? 410 : 409,
        code,
      );
    }
    if (!["retrieval_started", "evidence_verified", "evidence_complete", "analysis_ready",
      "explanation_unavailable", "answer_complete"].includes(event)) return;
    if (typeof data.query_id !== "string" || typeof data.run_id !== "string" ||
        typeof data.event_sequence !== "number" || !Number.isInteger(data.event_sequence) ||
        data.event_sequence <= lastSequence) invalid();
    if (queryId !== undefined && (queryId !== data.query_id || runId !== data.run_id)) invalid();
    queryId = data.query_id as string;
    runId = data.run_id as string;
    lastSequence = data.event_sequence as number;
    base = { ...base, query_id: data.query_id, run_id: data.run_id,
      facts_revision: data.facts_revision, snapshot_revision: data.snapshot_revision };
    if (event === "evidence_verified") {
      if (!Array.isArray(data.evidence) || !data.evidence.every((item: unknown) =>
        item !== null && typeof item === "object" &&
        typeof (item as { evidence_id?: unknown }).evidence_id === "string")) invalid();
      evidence = data.evidence as QueryResponse["evidence"];
      evidenceReceived = true;
    } else if (event === "analysis_ready") {
      if (!["evidence_found", "conditional", "insufficient", "conflicting"].includes(String(data.status)) ||
          !Array.isArray(data.claims) || !Array.isArray(data.suggestions)) invalid();
      const { query_id, run_id, facts_revision, snapshot_revision, event_sequence, ...rest } = data;
      void query_id; void run_id; void facts_revision; void snapshot_revision; void event_sequence;
      analysis = rest as Partial<QueryResponse>;
      analysisReceived = true;
    } else if (event === "answer_complete") {
      complete = true;
    }
  };

  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer = (buffer + decoder.decode(value, { stream: true })).replace(/\r\n/g, "\n");
      if (buffer.length > 2 * 1024 * 1024) invalid();
      let index = buffer.indexOf("\n\n");
      while (index >= 0) {
        handle(buffer.slice(0, index));
        buffer = buffer.slice(index + 2);
        if (complete) break;
        index = buffer.indexOf("\n\n");
      }
      // answer_complete is the protocol's terminal event. A proxy may keep
      // the HTTP connection open; the UI must not wait for EOF after a result.
      if (complete) {
        void reader.cancel().catch(() => undefined);
        buffer = "";
        break;
      }
    }
    buffer += decoder.decode();
    if (buffer.trim()) handle(buffer);
  } catch (caught) {
    void reader.cancel().catch(() => undefined);
    throw caught;
  } finally {
    reader.releaseLock();
  }
  if (!complete || !evidenceReceived || !analysisReceived) {
    throw new ApiRequestError(
      "Luồng kết quả bị ngắt trước khi hoàn tất. Hãy thử lại.", 502, "STREAM_INCOMPLETE",
    );
  }
  return {
    claims: [], evidence_groups: [], missing_information: [], suggestions: [],
    coverage_checks: {}, answer_generated: false, explanation_unavailable: false,
    ...analysis, ...base, evidence,
  } as unknown as QueryResponse;
}

async function streamingRequest(
  path: string,
  init: RequestInit,
  onTurnId?: (turnId: string) => void,
): Promise<QueryResponse> {
  const { signal, cleanup } = createTimeoutController(init.signal, queryTimeoutMs);
  try {
    const response = await fetch(API_BASE + path, {
      ...init,
      signal,
      headers: { "Content-Type": "application/json", ...init.headers },
    });
    if (!response.ok) {
      const body = (await response.json().catch(() => ({}))) as {
        message?: string; code?: string; trace_id?: string;
      };
      throw new ApiRequestError(
        typeof body.message === "string" ? body.message : "Không thể hoàn tất yêu cầu.",
        response.status, body.code ?? "REQUEST_FAILED", body.trace_id,
      );
    }
    const turnId = response.headers.get("X-Turn-Id");
    if (turnId) onTurnId?.(turnId);
    return await readTurnStream(response);
  } catch (caught) {
    if (signal.aborted && !init.signal?.aborted) {
      throw new ApiRequestError("Máy chủ phản hồi quá lâu. Hãy thử lại sau.", 408, "CLIENT_TIMEOUT");
    }
    throw caught;
  } finally {
    cleanup();
  }
}

/** Run one memory-backed turn and resolve with the assembled query result. */
export function runAgentTurn(
  accessToken: string,
  sessionId: string,
  payload: TurnPayload,
  options: { signal?: AbortSignal; idempotencyKey: string; onTurnId?: (turnId: string) => void },
): Promise<QueryResponse> {
  return streamingRequest(
    "/api/v1/agent/sessions/" + encodeURIComponent(sessionId) + "/turns",
    {
      method: "POST",
      headers: { ...bearerHeader(accessToken), "Idempotency-Key": options.idempotencyKey },
      signal: options.signal,
      body: JSON.stringify(payload),
    },
    options.onTurnId,
  );
}

/** Re-run a finished or failed turn, then replay its stored events. */
export async function retryAgentTurn(
  accessToken: string,
  sessionId: string,
  turnId: string,
  options: { signal?: AbortSignal; idempotencyKey: string; onTurnId?: (turnId: string) => void },
): Promise<QueryResponse> {
  const retried = await request<{ turn_id: string; run_id: string }>(
    "/api/v1/agent/sessions/" + encodeURIComponent(sessionId) +
      "/turns/" + encodeURIComponent(turnId) + "/retry",
    {
      method: "POST",
      headers: { ...bearerHeader(accessToken), "Idempotency-Key": options.idempotencyKey },
      signal: options.signal,
    },
  );
  options.onTurnId?.(retried.turn_id);
  return streamingRequest(
    "/api/v1/agent/sessions/" + encodeURIComponent(sessionId) +
      "/turns/" + encodeURIComponent(retried.turn_id) + "/events?run_id=" +
      encodeURIComponent(retried.run_id),
    { method: "GET", headers: bearerHeader(accessToken), signal: options.signal },
  );
}

export function loginWithPassword(
  username: string,
  password: string,
  client: "web" | "desktop" = "web",
): Promise<LoginResponse> {
  return request<LoginResponse>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password, client }),
  });
}

export function getCurrentUser(accessToken: string): Promise<UserInfo> {
  return request<UserInfo>("/api/v1/auth/me", {
    method: "GET",
    headers: bearerHeader(accessToken),
  });
}

export function logoutSession(accessToken: string): Promise<void> {
  return request<void>("/api/v1/auth/logout", {
    method: "POST",
    headers: bearerHeader(accessToken),
  });
}

export function changePassword(
  accessToken: string,
  currentPassword: string,
  newPassword: string,
): Promise<void> {
  return request<void>("/api/v1/auth/password", {
    method: "POST",
    headers: bearerHeader(accessToken),
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
}

export function listAuthorizedCategories(
  accessToken?: string,
  options: { signal?: AbortSignal } = {},
): Promise<AuthorizedCategory[]> {
  return request<AuthorizedCategory[]>("/api/v1/categories", {
    method: "GET",
    headers: bearerHeader(accessToken),
    signal: options.signal,
  });
}

const CITATION_VIEWER_PATH =
  /^\/api\/v1\/citations\/ev_[0-9a-fA-F-]+\/pdf(\?as_of_date=\d{4}-\d{2}-\d{2})?$/;

/**
 * Fetches the hash-checked source PDF behind a citation. Only the backend's own
 * citation route is accepted so a malformed `viewer_url` can never redirect the
 * authenticated request to another host.
 */
export function fetchCitationPdf(
  viewerUrl: string,
  options: { accessToken?: string; signal?: AbortSignal } = {},
): Promise<Blob> {
  if (!CITATION_VIEWER_PATH.test(viewerUrl)) {
    return Promise.reject(new ApiRequestError("Đường dẫn xem nguồn không hợp lệ.", 400, "VIEWER_URL_INVALID"));
  }
  return fetchSourcePdf(viewerUrl, options);
}

async function fetchSourcePdf(
  viewerUrl: string, options: { accessToken?: string; signal?: AbortSignal },
): Promise<Blob> {
  const { signal, cleanup } = createTimeoutController(options.signal);
  try {
    const response = await fetch(`${API_BASE}${viewerUrl}`, {
      method: "GET",
      headers: bearerHeader(options.accessToken),
      signal,
      redirect: "error",
      cache: "no-store",
    });
    if (!response.ok) {
      const body = (await response.json().catch(() => ({}))) as {
        message?: string;
        code?: string;
        trace_id?: string;
      };
      throw new ApiRequestError(
        typeof body.message === "string" ? body.message : "Không thể mở PDF gốc.",
        response.status,
        body.code ?? "REQUEST_FAILED",
        body.trace_id,
      );
    }
    if (!(response.headers.get("Content-Type") ?? "").startsWith("application/pdf")) {
      throw new ApiRequestError("Máy chủ không trả về PDF.", 502, "VIEWER_CONTENT_INVALID");
    }
    return await response.blob();
  } finally {
    cleanup();
  }
}

const ORIGINAL_SOURCE_PATH =
  /^\/api\/v1\/citations\/ev_[0-9a-fA-F-]+\/original(\?as_of_date=\d{4}-\d{2}-\d{2})?$/;

export interface OriginalFile {
  blob: Blob;
  /** pdf | docx | doc | txt, from the server's X-Source-Format header. */
  format: string;
  filename: string;
}

function filenameFromDisposition(header: string | null): string | undefined {
  if (!header) return undefined;
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (encoded) {
    try {
      return decodeURIComponent(encoded[1].trim());
    } catch {
      // fall back to the ASCII name below
    }
  }
  const plain = /filename="([^"]+)"/i.exec(header);
  return plain?.[1];
}

/**
 * The file exactly as it was imported (ACL, version and SHA-256 re-checked by the
 * server): the PDF itself (scans included) or the original Word/TXT file.
 */
export async function fetchOriginalFile(
  originalUrl: string,
  options: { accessToken?: string; signal?: AbortSignal } = {},
): Promise<OriginalFile> {
  if (!ORIGINAL_SOURCE_PATH.test(originalUrl)) {
    throw new ApiRequestError("Đường dẫn tệp gốc không hợp lệ.", 400, "SOURCE_URL_INVALID");
  }
  return fetchSourceFile(originalUrl, options);
}

async function fetchSourceFile(
  path: string, options: { accessToken?: string; signal?: AbortSignal },
): Promise<OriginalFile> {
  const { signal, cleanup } = createTimeoutController(options.signal, 60000);
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      method: "GET",
      headers: bearerHeader(options.accessToken),
      signal,
      redirect: "error",
      cache: "no-store",
    });
    if (!response.ok) {
      const body = (await response.json().catch(() => ({}))) as {
        message?: string; code?: string; trace_id?: string;
      };
      throw new ApiRequestError(
        typeof body.message === "string" ? body.message : "Không thể mở tệp gốc.",
        response.status, body.code ?? "REQUEST_FAILED", body.trace_id,
      );
    }
    const format = (response.headers.get("X-Source-Format") ?? "").toLowerCase() ||
      ((response.headers.get("Content-Type") ?? "").startsWith("application/pdf") ? "pdf" : "");
    const filename =
      filenameFromDisposition(response.headers.get("Content-Disposition")) ??
      `van-ban.${format || "bin"}`;
    return { blob: await response.blob(), format, filename };
  } finally {
    cleanup();
  }
}

export function fetchAdminDraftPdf(
  accessToken: string, versionId: string, signal?: AbortSignal,
): Promise<Blob> {
  return fetchSourcePdf(`/api/v1/admin/documents/drafts/${encodeURIComponent(versionId)}/pdf`, {
    accessToken, signal,
  });
}

/** Diagnostics of one OCR page (documents/ocr.py); for the reviewer, never evidence. */
export interface OcrDiagnostics {
  words?: number;
  mean_confidence?: number;
  low_confidence_share?: number;
  low_confidence_words?: string[];
  suspect_tokens?: string[];
  suspect_markers?: string[];
  ink_share?: number | null;
  rotation?: number;
  flags?: string[];
}

export interface ReviewTaskPage {
  page_number: number;
  extraction_method: string;
  text_quality: string;
  extraction_error?: string | null;
  ocr_diagnostics?: OcrDiagnostics | null;
  text: string;
  text_truncated: boolean;
  reviewed_at?: string | null;
}

export interface ReviewTask {
  id: string; reason: string; risk: string; status: string;
  /** Set for page-text tasks (OCR or unreadable text layer). */
  page?: ReviewTaskPage | null;
}

export function listAdminReviewTasks(accessToken: string, versionId: string, signal?: AbortSignal): Promise<ReviewTask[]> {
  return request(`/api/v1/admin/documents/review-tasks?version_id=${encodeURIComponent(versionId)}&status=open`, {
    method: "GET", headers: bearerHeader(accessToken), signal,
  });
}

export interface PotentialDuplicate {
  document_version_id: string;
  title: string;
  document_number: string | null;
  status: string;
}

export function listAdminContentDuplicates(
  accessToken: string, versionId: string, signal?: AbortSignal,
): Promise<{ content_check_available: boolean; potential_duplicates: PotentialDuplicate[] }> {
  return request(`/api/v1/admin/documents/drafts/${encodeURIComponent(versionId)}/duplicates`, {
    method: "GET", headers: bearerHeader(accessToken), signal,
  });
}

export function resolveAdminReviewTask(accessToken: string, taskId: string, note: string): Promise<unknown> {
  return request(`/api/v1/admin/documents/review-tasks/${encodeURIComponent(taskId)}/resolve`, {
    method: "POST", headers: bearerHeader(accessToken), body: JSON.stringify({ resolution_note: note }),
  });
}

export function listAdminDrafts(accessToken: string): Promise<PdfDraftListItem[]> {
  return request<PdfDraftListItem[]>("/api/v1/admin/documents/drafts", {
    method: "GET",
    headers: bearerHeader(accessToken),
  });
}

export function uploadAdminDraft(
  accessToken: string,
  formData: FormData,
  options: { signal?: AbortSignal } = {},
): Promise<{
  document_id: string;
  document_version_id: string;
  sha256: string;
  page_count: number;
  node_count: number;
  review_required_pages: number;
  content_check_available?: boolean;
  potential_duplicates?: PotentialDuplicate[];
}> {
  return request("/api/v1/admin/documents/drafts", {
    method: "POST",
    headers: bearerHeader(accessToken),
    body: formData,
    signal: options.signal,
  });
}

export function submitAdminDraft(
  accessToken: string,
  versionId: string,
): Promise<{ document_version_id: string; status: string }> {
  return request(`/api/v1/admin/documents/drafts/${versionId}/submit`, {
    method: "POST",
    headers: bearerHeader(accessToken),
  });
}

export function reextractAdminDraft(accessToken: string, versionId: string): Promise<{
  status: string;
  pages_restored: number;
  nodes_anchored: number;
  nodes_unresolved: number;
  possible_duplicates: number;
}> {
  return request(`/api/v1/admin/documents/drafts/${encodeURIComponent(versionId)}/reextract`, {
    method: "POST",
    headers: bearerHeader(accessToken),
  });
}

export function approveAdminDraft(
  accessToken: string,
  versionId: string,
  payload: { category_ids: string[]; review_note: string; resolve_all_tasks: boolean; revision?: number },
): Promise<{ document_id: string; document_version_id: string; status: string; approved_nodes: number }> {
  return request(`/api/v1/admin/documents/drafts/${versionId}/approve`, {
    method: "POST",
    headers: bearerHeader(accessToken),
    body: JSON.stringify(payload),
  });
}

export function rejectAdminDraft(
  accessToken: string,
  versionId: string,
  reviewNote: string,
  revision?: number,
): Promise<{ document_version_id: string; status: string }> {
  return request(`/api/v1/admin/documents/drafts/${versionId}/reject`, {
    method: "POST",
    headers: bearerHeader(accessToken),
    body: JSON.stringify({ review_note: reviewNote, revision }),
  });
}

const ADMIN_DOCUMENTS_PATH = "/api/v1/admin/documents";

function adminVersionPath(id: string, versionId: string): string {
  return `${ADMIN_DOCUMENTS_PATH}/${encodeURIComponent(id)}/versions/${encodeURIComponent(versionId)}`;
}

export function listAdminDocuments(
  accessToken: string, filters: Record<string, string>, page: number, signal?: AbortSignal,
): Promise<AdminDocumentList> {
  const params = new URLSearchParams({ page: String(page), page_size: "20" });
  for (const [key, value] of Object.entries(filters)) {
    if (value.trim()) params.set(key, value.trim());
  }
  return request(`${ADMIN_DOCUMENTS_PATH}?${params}`, {
    headers: bearerHeader(accessToken), signal, cache: "no-store",
  });
}

export function getAdminDocument(
  accessToken: string, id: string, versionId: string, pageNumber: number, nodePage: number,
  signal?: AbortSignal,
): Promise<AdminDocumentDetail> {
  const params = new URLSearchParams({
    page_number: String(pageNumber), node_page: String(nodePage),
  });
  if (versionId) params.set("version_id", versionId);
  return request(`${ADMIN_DOCUMENTS_PATH}/${encodeURIComponent(id)}?${params}`, {
    headers: bearerHeader(accessToken), signal, cache: "no-store",
  });
}

export function fetchAdminDocumentOriginal(
  accessToken: string, id: string, versionId: string, signal?: AbortSignal,
): Promise<OriginalFile> {
  return fetchSourceFile(`${adminVersionPath(id, versionId)}/original`, { accessToken, signal });
}

export function fetchAdminDocumentPdf(
  accessToken: string, id: string, versionId: string, signal?: AbortSignal,
): Promise<Blob> {
  return fetchSourcePdf(`${adminVersionPath(id, versionId)}/original?pdf=true`, { accessToken, signal });
}

interface AdminDocumentMutation {
  version_id: string;
  revision: number;
  status: string;
}

export function patchAdminDocument(
  accessToken: string, id: string, versionId: string, patch: AdminDocumentPatch,
): Promise<AdminDocumentMutation> {
  return request(adminVersionPath(id, versionId), {
    method: "PATCH", headers: bearerHeader(accessToken), body: JSON.stringify(patch),
  });
}

export function reprocessAdminDocument(
  accessToken: string, id: string, versionId: string, revision: number,
): Promise<AdminDocumentMutation> {
  return request(`${adminVersionPath(id, versionId)}/reprocess`, {
    method: "POST", headers: bearerHeader(accessToken), body: JSON.stringify({ revision }),
  });
}

export function changeAdminDocumentAvailability(
  accessToken: string, documentIds: string[], action: AdminDocumentAction, reason: string,
): Promise<{ updated: number }> {
  return request(`${ADMIN_DOCUMENTS_PATH}/actions`, {
    method: "POST", headers: bearerHeader(accessToken),
    body: JSON.stringify({ document_ids: documentIds, action, reason, confirmed: true }),
  });
}

export function listAdminCategories(accessToken: string): Promise<AuthorizedCategory[]> {
  return request<AuthorizedCategory[]>("/api/v1/admin/categories", {
    method: "GET",
    headers: bearerHeader(accessToken),
  });
}

export function createAdminCategory(
  accessToken: string,
  payload: { code: string; name: string; remote_processing_allowed: boolean },
): Promise<AuthorizedCategory> {
  return request<AuthorizedCategory>("/api/v1/admin/categories", {
    method: "POST",
    headers: bearerHeader(accessToken),
    body: JSON.stringify(payload),
  });
}

export function deleteAdminCategory(
  accessToken: string,
  categoryId: string,
): Promise<{ id: string; code: string; status: string }> {
  return request(`/api/v1/admin/categories/${encodeURIComponent(categoryId)}`, {
    method: "DELETE",
    headers: bearerHeader(accessToken),
  });
}

export function updateAdminCategory(
  accessToken: string, categoryId: string,
  payload: { code: string; name: string; remote_processing_allowed: boolean },
): Promise<AuthorizedCategory> {
  return request(`/api/v1/admin/categories/${encodeURIComponent(categoryId)}`, {
    method: "PATCH", headers: bearerHeader(accessToken), body: JSON.stringify(payload),
  });
}

export function listAdminUsers(accessToken: string): Promise<AdminUserItem[]> {
  return request<AdminUserItem[]>("/api/v1/admin/users", {
    method: "GET",
    headers: bearerHeader(accessToken),
  });
}

export function upsertAdminUser(
  accessToken: string,
  payload: {
    username: string;
    display_name: string;
    password?: string;
    roles: string[];
    category_ids: string[];
    review_category_ids?: string[];
    must_change_password: boolean;
    disabled: boolean;
    remote_ai_allowed?: boolean;
  },
): Promise<AdminUserItem> {
  return request<AdminUserItem>("/api/v1/admin/users", {
    method: "POST",
    headers: bearerHeader(accessToken),
    body: JSON.stringify(payload),
  });
}

export function deleteAdminUser(
  accessToken: string,
  userId: string,
): Promise<{ id: string; username: string; status: string }> {
  return request(`/api/v1/admin/users/${encodeURIComponent(userId)}`, {
    method: "DELETE",
    headers: bearerHeader(accessToken),
  });
}

export interface EffectivityProposal {
  id: string;
  action: string;
  scope: "document" | "node";
  valid_from?: string | null;
  review_status: string;
  proposed_by: "rule" | "ai" | "person";
  confidence?: number | null;
  condition_text?: string | null;
  source_quote?: string | null;
  source_page?: number | null;
  source_label?: string | null;
  target_number?: string | null;
  target_path?: string | null;
  resolution_state: "resolved" | "unresolved" | "ambiguous";
  target_document_id?: string | null;
  target_document_number?: string | null;
  target_title?: string | null;
  target_label?: string | null;
}

export interface EffectivityProposalGroup {
  source_document_id: string;
  source_number?: string | null;
  source_title: string;
  proposals: EffectivityProposal[];
}

/** G1: proposals grouped by the document that states them (REVIEWER, can_review). */
export function listEffectivityProposals(
  accessToken: string, status: "draft" | "approved" | "rejected" = "draft",
): Promise<{ groups: EffectivityProposalGroup[]; count: number }> {
  return request(`/api/v1/admin/effectivity/proposals?status=${status}&limit=500`, {
    method: "GET", headers: bearerHeader(accessToken),
  });
}

export function reviewEffectivityProposals(
  accessToken: string,
  payload: {
    note: string;
    decisions: { relation_id: string; decision: "approve" | "reject"; valid_from?: string }[];
  },
): Promise<{ batch_id: string; results: { relation_id: string; decision: string }[] }> {
  return request("/api/v1/admin/effectivity/proposals/review", {
    method: "POST", headers: bearerHeader(accessToken), body: JSON.stringify(payload),
  });
}

export function createEffectivityAttestation(
  accessToken: string,
  payload: {
    document_id: string; result: string; valid_for_from: string; valid_for_to: string;
    source_note: string;
  },
): Promise<{ id: string; status: string }> {
  return request("/api/v1/admin/effectivity/attestations", {
    method: "POST", headers: bearerHeader(accessToken), body: JSON.stringify(payload),
  });
}

export interface ComprehensiveItem {
  rank: number;
  node_id: string;
  document_id: string;
  document_version_id?: string;
  document_number?: string | null;
  title: string;
  display_title?: string;
  kind_label?: string | null;
  doc_type?: string;
  issuing_body?: string | null;
  publication_date?: string | null;
  source_format?: string;
  original_filename?: string | null;
  /** "local_ocr" when the clause comes from a reviewed OCR page of a scan. */
  extraction_method?: string | null;
  label: string;
  heading?: string | null;
  node_type?: string;
  path?: string;
  page?: number | null;
  page_end?: number | null;
  quote_exact: string;
  snippet: string;
  excerpt?: Excerpt & { highlights: TextSpan[] };
  viewer_url: string;
  original_url?: string;
  effectivity?: EffectivityView | null;
  channels: string[];
  rerank_score?: number | null;
  section: string;
  /** direct | related | weak | unscored — relevance to the words of the query. */
  tier?: string;
  /** phrase | terms | number | semantic | concept | relation | partial | none */
  match?: string;
  matched_terms?: string[];
  listing?: boolean;
  groups: { root_document_id?: string | null; root_number?: string | null; role: string;
            note?: string }[];
}

export interface ComprehensiveDocument {
  rank: number;
  document_id: string;
  document_version_id: string;
  document_number?: string | null;
  title: string;
  display_title?: string;
  kind_label?: string | null;
  doc_type: string;
  issuing_body?: string | null;
  publication_date?: string | null;
  source_format?: string;
  original_filename?: string | null;
  original_url?: string;
  effectivity?: EffectivityView | null;
  best_tier: string;
  tier_counts: Record<string, number>;
  listing: boolean;
  matched_clause_count: number;
  has_more_clauses: boolean;
  clauses: ComprehensiveItem[];
  groups: ComprehensiveItem["groups"];
}

export interface ComprehensiveResult {
  result_set_id: string;
  query: string;
  as_of_date: string;
  page: number;
  page_size: number;
  view?: "clauses" | "documents";
  total_items: number;
  total_documents?: number;
  has_more: boolean;
  items: ComprehensiveItem[];
  documents?: ComprehensiveDocument[];
  hidden_items: number;
  understood?: { phrases: string[]; mode: string };
  tiers?: Record<string, number>;
  scope: { documents_in_scope: number; categories: string[]; data_date?: string | null;
           as_of_date: string; statement: string };
  channels: Record<string, { count: number; enabled: boolean; available?: boolean;
                             cap?: number; relative_threshold?: number; note?: string | null;
                             nodes_without_vector?: number; capped?: boolean }>;
  totals: { clauses: number; documents: number; only_semantic: number; only_relation: number;
            only_concept: number };
  ranking: { reranked: boolean; reranked_count: number; total: number; note?: string };
  concepts: { term: string; expansion: string; source: string; selected: boolean }[];
  sections: { key: string; label: string; count: number; collapsed: boolean }[];
  display: string;
  empty_message?: string | null;
  clause_level_warning?: string | null;
}

/** G2: run all channels once; the fixed result set is then paged by id. */
export function runComprehensiveSearch(
  accessToken: string,
  payload: {
    q: string; as_of_date?: string; display: "default" | "all" | "history";
    channels?: string[]; excluded_concepts?: string[]; category_ids?: string[];
    doc_types?: string[]; page_size?: number; mode?: "auto" | "phrase" | "keywords";
    view?: "clauses" | "documents"; clauses_per_document?: number; tier?: string[];
  },
): Promise<ComprehensiveResult> {
  return request("/api/v1/search/comprehensive", {
    method: "POST", headers: bearerHeader(accessToken), body: JSON.stringify(payload),
  });
}

export function getComprehensivePage(
  accessToken: string, resultSetId: string, page: number,
  filters: {
    status?: string; verification?: string; tier?: string[];
    view?: "clauses" | "documents"; pageSize?: number; clausesPerDocument?: number;
  } = {},
): Promise<ComprehensiveResult> {
  const params = new URLSearchParams({
    page: String(page), page_size: String(filters.pageSize ?? 20),
  });
  if (filters.status) params.append("status", filters.status);
  if (filters.verification) params.append("verification", filters.verification);
  for (const tier of filters.tier ?? []) params.append("tier", tier);
  if (filters.view) params.append("view", filters.view);
  if (filters.clausesPerDocument) {
    params.append("clauses_per_document", String(filters.clausesPerDocument));
  }
  return request(
    `/api/v1/search/comprehensive/${encodeURIComponent(resultSetId)}?${params.toString()}`,
    { method: "GET", headers: bearerHeader(accessToken) },
  );
}

/** Every matching clause of one document in a fixed result set. */
export function getComprehensiveDocumentClauses(
  accessToken: string, resultSetId: string, documentId: string,
  filters: { status?: string; verification?: string; tier?: string[] } = {},
): Promise<{ result_set_id: string; document_id: string; clauses: ComprehensiveItem[] }> {
  const params = new URLSearchParams();
  if (filters.status) params.append("status", filters.status);
  if (filters.verification) params.append("verification", filters.verification);
  for (const tier of filters.tier ?? []) params.append("tier", tier);
  const query = params.toString();
  return request(
    `/api/v1/search/comprehensive/${encodeURIComponent(resultSetId)}/documents/` +
      `${encodeURIComponent(documentId)}${query ? `?${query}` : ""}`,
    { method: "GET", headers: bearerHeader(accessToken) },
  );
}

export interface SynthesisEvidence {
  evidence_id: string;
  document_number?: string | null;
  title: string;
  label: string;
  page?: number | null;
  quote_exact: string;
  viewer_url: string;
  effectivity?: EffectivityView | null;
  labels: { code: string; name: string; status: string }[];
}

export interface SynthesisPoint {
  group: string;
  text: string;
  evidence_ids: string[];
  status: "verified" | "unverified";
  check_notes: string[];
}

/** One AI statement after every check layer (synthesis/checks.py verify_claim). */
export interface FocusedClaim {
  text: string;
  evidence_ids: string[];
  /** "verified" = matched against the cited clauses; never "legally correct". */
  status?: "verified" | "needs_review";
  notes: string[];
  source?: "ai" | "system";
  batch?: number;
}

/** "Diễn giải AI" of one question (only_relevant): answer first, then its evidence. */
export interface FocusedAnswer {
  status: "answered" | "partial" | "not_found" | "no_evidence" | "model_unavailable"
    | "no_valid_claims";
  question: string;
  focus: { aspects: string[]; subject: string[]; strict: boolean };
  lead: FocusedClaim;
  points: FocusedClaim[];
  gaps: string[];
  notes: string[];
  documents: AnswerDocument[];
  reviewed_documents: AnswerDocument[];
  evidence: { evidence_id: string; quote_exact: string; label: string;
              document_number?: string | null }[];
  other_documents: AnswerDocument[];
  excluded: { other_aspect: number; off_topic: number; mentioned: number };
  rejected: { text: string; reasons: string[] }[];
}

export interface SynthesisResult {
  result_set_id: string;
  mode?: "focused";
  answer?: FocusedAnswer;
  layers: {
    verbatim: { group: string; evidence: SynthesisEvidence[] }[];
    interpretation: SynthesisPoint[];
    suggestions: SynthesisPoint[];
  };
  coverage: { used: number; total: number; groups_remaining: number; partial: boolean;
              message: string };
  can_continue: boolean;
  model_calls: number;
  external_ai_used: boolean;
  ai_limited: boolean;
  disclaimer: string;
}

/** G4: checked synthesis by group and batch over a fixed result set. */
export function runSynthesis(
  accessToken: string,
  payload: { result_set_id: string; restart?: boolean; deep_analysis?: boolean;
             expand?: boolean; only_relevant?: boolean },
): Promise<SynthesisResult> {
  return request("/api/v1/synthesis", {
    method: "POST", headers: bearerHeader(accessToken), body: JSON.stringify(payload),
  });
}

export interface LabelProposal {
  node_id: string;
  code: string;
  name: string;
  label?: string | null;
  text: string;
  document_number?: string | null;
}

export function listLabelProposals(accessToken: string): Promise<LabelProposal[]> {
  return request("/api/v1/admin/labels/proposals", {
    method: "GET", headers: bearerHeader(accessToken),
  });
}

export function reviewLabels(
  accessToken: string,
  payload: { decision: "approve" | "reject";
             items: { node_id: string; taxonomy_code: string }[] },
): Promise<{ updated: number; batch_id: string }> {
  return request("/api/v1/admin/labels/review", {
    method: "POST", headers: bearerHeader(accessToken), body: JSON.stringify(payload),
  });
}

export async function getAdminModelRegistry(accessToken: string): Promise<ModelRegistryState> {
  const raw = await request<ModelRegistryState | unknown[]>("/api/v1/admin/model-registry", {
    method: "GET",
    headers: bearerHeader(accessToken),
  });
  if (Array.isArray(raw)) {
    return { profiles: [], routes: [] };
  }
  return raw;
}

export function upsertAdminModelProfile(
  accessToken: string,
  payload: ModelProfilePayload,
): Promise<{ profile_id: string; status: string }> {
  return request("/api/v1/admin/model-registry", {
    method: "POST",
    headers: bearerHeader(accessToken),
    body: JSON.stringify(payload),
  });
}

/** Check a profile that is not saved yet: configuration, key, connection, model, one request. */
export function testAdminModelDraft(
  accessToken: string, payload: ModelProfilePayload,
): Promise<ModelCheckResult> {
  return request("/api/v1/admin/model-registry/test", {
    method: "POST", headers: bearerHeader(accessToken), body: JSON.stringify(payload),
  });
}

/** Check a saved profile and record its health (ready only after a complete pass). */
export function testAdminModelProfile(
  accessToken: string, profileId: string,
): Promise<ModelCheckResult> {
  return request(`/api/v1/admin/model-registry/${encodeURIComponent(profileId)}/test`, {
    method: "POST", headers: bearerHeader(accessToken),
  });
}

export function upsertAdminStageRoute(
  accessToken: string,
  payload: {
    mode: string; stage: string; profile_id: string; fallback: string[];
    escalation_profile_id?: string | null;
  },
): Promise<{ mode: string; stage: string; profile_id: string }> {
  return request("/api/v1/admin/model-registry/routes", {
    method: "POST",
    headers: bearerHeader(accessToken),
    body: JSON.stringify(payload),
  });
}

export function upsertAdminStagePolicy(
  accessToken: string,
  payload: StagePolicy,
): Promise<StagePolicy> {
  return request("/api/v1/admin/model-registry/policies", {
    method: "POST",
    headers: bearerHeader(accessToken),
    body: JSON.stringify(payload),
  });
}

export function probeAdminModelProfile(
  accessToken: string, profileId: string,
): Promise<{ health: string; status?: string }> {
  return request(`/api/v1/admin/model-registry/${encodeURIComponent(profileId)}/probe`, {
    method: "POST", headers: bearerHeader(accessToken),
  });
}

export function getAdminEmbeddings(accessToken: string): Promise<EmbeddingOverview> {
  return request("/api/v1/admin/embeddings", {
    method: "GET", headers: bearerHeader(accessToken),
  });
}

export function preflightAdminEmbedding(
  accessToken: string,
  payload: { profile_id: string; rebuild: boolean; batch_size: number },
): Promise<EmbeddingPreflight> {
  return request("/api/v1/admin/embeddings/preflight", {
    method: "POST", headers: bearerHeader(accessToken), body: JSON.stringify(payload),
  });
}

export function createAdminEmbeddingJob(
  accessToken: string,
  payload: { profile_id: string; rebuild: boolean; batch_size: number; confirmed: true },
): Promise<EmbeddingJob> {
  return request("/api/v1/admin/embeddings/jobs", {
    method: "POST", headers: bearerHeader(accessToken), body: JSON.stringify(payload),
  });
}

export function controlAdminEmbeddingJob(
  accessToken: string, jobId: string, action: "pause" | "resume" | "retry" | "cancel",
): Promise<EmbeddingJob> {
  return request(
    `/api/v1/admin/embeddings/jobs/${encodeURIComponent(jobId)}/${action}`,
    { method: "POST", headers: bearerHeader(accessToken) },
  );
}

export function listAdminAuditEvents(accessToken: string): Promise<AuditEventsResponse> {
  return request<AuditEventsResponse>("/api/v1/admin/audit-events", {
    method: "GET",
    headers: bearerHeader(accessToken),
  });
}

/** Search v1 query parameters; every optional filter is omitted when unset. */
export interface SearchParams {
  q: string;
  mode?: SearchMode;
  categoryIds?: string[];
  docType?: string;
  issuingBody?: string;
  asOfDate?: string;
  onlyActive?: boolean;
  page?: number;
  pageSize?: number;
  clausePage?: number;
  clausePageSize?: number;
}

export function buildSearchQueryString(params: SearchParams): string {
  const search = new URLSearchParams();
  const query = params.q.trim();
  if (query) search.set("q", query);
  if (params.mode) search.set("mode", params.mode);
  for (const categoryId of params.categoryIds ?? []) {
    if (categoryId) search.append("category_id", categoryId);
  }
  const docType = params.docType?.trim();
  if (docType) search.set("doc_type", docType);
  const issuingBody = params.issuingBody?.trim();
  if (issuingBody) search.set("issuing_body", issuingBody);
  if (params.asOfDate) search.set("as_of_date", params.asOfDate);
  if (params.onlyActive) search.set("only_active", "true");
  if (params.page && params.page > 1) search.set("page", String(params.page));
  if (params.pageSize) search.set("page_size", String(params.pageSize));
  // Per-document clause window; page 1 is the backend default and stays implicit.
  if (params.clausePage && params.clausePage > 1) {
    search.set("clause_page", String(params.clausePage));
  }
  if (params.clausePageSize) {
    search.set("clause_page_size", String(params.clausePageSize));
  }
  return search.toString();
}

/** Grouped document search used by the Search page (not the 12-clause chat limit). */
export function searchDocuments(
  params: SearchParams,
  options: { accessToken?: string; signal?: AbortSignal } = {},
): Promise<SearchResponse> {
  return request<SearchResponse>(`/api/v1/search?${buildSearchQueryString(params)}`, {
    method: "GET",
    headers: bearerHeader(options.accessToken),
    signal: options.signal,
  });
}

/** Partial ("any term") matches loaded only when the user expands that section. */
export function searchApproximate(
  params: SearchParams,
  options: { accessToken?: string; signal?: AbortSignal } = {},
): Promise<SearchResponse> {
  return request<SearchResponse>(
    `/api/v1/search/approximate?${buildSearchQueryString(params)}`,
    {
      method: "GET",
      headers: bearerHeader(options.accessToken),
      signal: options.signal,
    },
  );
}
