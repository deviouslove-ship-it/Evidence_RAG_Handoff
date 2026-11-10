import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import {
  ApiRequestError,
  cancelAgentTurn,
  clearMemory,
  createAgentSession,
  deleteAgentSession,
  deleteMemoryItem,
  deleteSessionFact,
  getMemoryPreferences,
  listAuthorizedCategories,
  listMemory,
  retryAgentTurn,
  runAgentTurn,
  setMemoryPreferences,
  type MemoryItem,
  type TurnPayload,
} from "../api/client";
import { AiInterpretation } from "../components/AiInterpretation";
import { DocumentCard } from "../components/DocumentCard";
import { fromAnswerDocument, fromEvidence, type DocView } from "../components/documentDisplay";
import { FactChips } from "../components/FactChips";
import { localDateISO } from "../localDate";
import { SAMPLE_PROMPTS } from "../samplePrompts";
import type { AuthorizedCategory, EvidenceRef, QueryResponse } from "../types";

interface Fact {
  key: string;
  value: string;
  status: "user_confirmed" | "extracted_unconfirmed" | "inferred_uncertain";
  dirty?: boolean;
}

export interface ExternalWorkspaceSync {
  response: QueryResponse;
  selected?: EvidenceRef;
  question?: string;
  accessToken?: string;
  seq: number;
}

interface EvidenceChatProps {
  accessToken?: string;
  externalSync?: ExternalWorkspaceSync;
  /** Optional: opens the document search page with the submitted question. */
  onViewAllResults?: (question: string) => void;
  /** Server operating mode; "Phân tích sâu" is offered only in API (Hybrid Auto). */
  operatingMode?: string;
}

// Backend enum values shown to users in Vietnamese; unknown values fall back to the raw code.
const RESULT_STATUS_LABELS: Record<string, string> = {
  evidence_found: "đã tìm thấy căn cứ",
  conditional: "có căn cứ, cần đối chiếu điều kiện áp dụng",
  insufficient: "chưa đủ căn cứ",
  conflicting: "các căn cứ có điểm mâu thuẫn",
};
const CLAIM_STATUS_LABELS: Record<string, string> = {
  supported: "được nguồn hỗ trợ",
  conditional: "có điều kiện",
  needs_review: "cần rà soát",
  blocked: "không dùng được",
};
const COVERAGE_LABELS: Record<string, string> = {
  source_verified: "Nguồn",
  effective_checked: "Hiệu lực",
  applicability_checked: "Phạm vi áp dụng",
  claim_supported: "Căn cứ",
  transition_checked: "Chuyển tiếp",
  required_facts_complete: "Dữ kiện",
  scope_expansion: "Phạm vi tra cứu",
};
const COVERAGE_STATE_LABELS: Record<string, string> = {
  passed: "đạt",
  failed: "không đạt",
  unknown: "chưa xác định",
};

// General questions that do not depend on a particular document being loaded.
const STARTER_SUGGESTIONS = SAMPLE_PROMPTS;

function newIdempotencyKey(): string {
  const cryptoApi = globalThis.crypto as Crypto | undefined;
  if (cryptoApi?.randomUUID) return cryptoApi.randomUUID();
  return `turn-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

/**
 * Facts come only from what the user typed (a document number, an Điều).  Nothing is
 * taken from the evidence: a number the user did not write must never become a search
 * condition, and a fact of an earlier question is not carried into a new one.
 */
function extractFactsFromQuestion(questionText: string, kept: Fact[]): Fact[] {
  const next: Fact[] = kept
    .filter((fact) => fact.status === "user_confirmed" && fact.value.trim())
    .map((fact) => ({ ...fact, dirty: false }));
  const docNum = questionText.match(/\b\d{1,4}\/\d{4}\/[A-ZĐa-zđ0-9-]+\b/)?.[0];
  if (docNum && !next.some((f) => f.key === "Số hiệu văn bản")) {
    next.push({ key: "Số hiệu văn bản", value: docNum, status: "extracted_unconfirmed" });
  }
  const articleMatch = questionText.match(/\bĐiều\s+\d+[a-zđ]?\b/i)?.[0];
  if (articleMatch && !next.some((f) => f.key === "Điều khoản")) {
    next.push({ key: "Điều khoản", value: articleMatch, status: "extracted_unconfirmed" });
  }
  return next;
}

function shortClauseLabel(label: string, number?: string | null): string {
  return number ? `${label}, ${number}` : label;
}

/** One question of the session with its own result; kept in RAM until logout. */
interface ChatEntry {
  id: string;
  question: string;
  status: "loading" | "done" | "error";
  result?: QueryResponse;
  error?: string;
}

const SPLIT_WIDTH_KEY = "evidence-rag.chat.left-width";
const SPLIT_DEFAULT = 42;
const SPLIT_MIN = 28;
const SPLIT_MAX = 72;
const STOPPED_MESSAGE = "Đã dừng lượt tra cứu hiện tại.";
const EXPIRED_MESSAGE = "Căn cứ đã hết hạn hoặc kho văn bản đã thay đổi. Hãy tra cứu lại.";

function clampSplit(value: number): number {
  return Math.min(SPLIT_MAX, Math.max(SPLIT_MIN, value));
}

function readStoredSplit(): number {
  try {
    const raw = window.localStorage.getItem(SPLIT_WIDTH_KEY);
    const value = raw === null ? Number.NaN : Number(raw);
    return Number.isFinite(value) ? clampSplit(value) : SPLIT_DEFAULT;
  } catch {
    return SPLIT_DEFAULT;
  }
}

/** Below this width the two panes become two tabs. */
function useNarrow(query = "(max-width: 900px)"): boolean {
  const read = () =>
    typeof window !== "undefined" && typeof window.matchMedia === "function"
      ? window.matchMedia(query).matches
      : false;
  const [narrow, setNarrow] = useState(read);
  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const media = window.matchMedia(query);
    const onChange = () => setNarrow(media.matches);
    onChange();
    media.addEventListener?.("change", onChange);
    return () => media.removeEventListener?.("change", onChange);
  }, [query]);
  return narrow;
}

function buildViews(result?: QueryResponse) {
  const evidence = result?.evidence ?? [];
  const labels = new Map<string, string>();
  for (const document of result?.documents ?? []) {
    for (const clause of document.clauses) {
      labels.set(clause.evidence_id, shortClauseLabel(clause.label, document.document_number));
    }
  }
  for (const item of evidence) {
    if (!labels.has(item.evidence_id)) {
      labels.set(item.evidence_id, shortClauseLabel(item.label, item.document_number));
    }
  }
  let documentViews: DocView[] = [];
  if (result) {
    if (result.documents && result.documents.length > 0) {
      const quotes = new Map(evidence.map((item) => [item.evidence_id, item.quote_exact]));
      documentViews = result.documents.map((document) =>
        fromAnswerDocument(document, quotes, labels));
    } else {
      documentViews = fromEvidence(evidence);
    }
  }
  const mainDocuments = documentViews.filter((document) => document.role !== "reference");
  const referenceDocuments = documentViews.filter((document) => document.role === "reference");
  return { evidence, clauseLabels: labels, documentViews, mainDocuments, referenceDocuments };
}

/** Card numbers [n] a sentence of the answer refers to (by document number). */
function citedNumbers(text: string, documents: DocView[]): number[] {
  const hits: number[] = [];
  documents.forEach((document, index) => {
    if (document.number && text.includes(document.number)) hits.push(index + 1);
  });
  return hits;
}

function CiteLinks({ numbers, onCite }: { numbers: number[]; onCite: (n: number) => void }) {
  if (numbers.length === 0) return null;
  return (
    <span className="ai-cites">
      {numbers.map((n) => (
        <button
          aria-label={`Căn cứ ${n}`}
          className="ai-cite chat-cite"
          key={n}
          onClick={() => onCite(n)}
          type="button"
        >
          [{n}]
        </button>
      ))}
    </span>
  );
}

interface ChatTurnProps {
  entry: ChatEntry;
  selected: boolean;
  onSelect: () => void;
  onCite: (n: number) => void;
}

/** A question with its short answer; selecting it shows its evidence on the right. */
function ChatTurn({ entry, selected, onSelect, onCite }: ChatTurnProps) {
  const views = useMemo(() => buildViews(entry.result), [entry.result]);
  const { evidence, mainDocuments } = views;
  const result = entry.result;
  const answer = result?.answer ?? undefined;
  const notFound = Boolean(result) && (answer?.outcome === "not_found" ||
    (!answer && evidence.length === 0));
  return (
    <article className="chat-turn" data-selected={selected} data-status={entry.status}>
      <button
        aria-pressed={selected}
        className="chat-turn-question message-user"
        onClick={onSelect}
        type="button"
      >
        {entry.question}
      </button>
      {entry.status === "loading" && (
        <p className="chat-progress" role="status">
          Đang tìm văn bản và điều khoản liên quan…
        </p>
      )}
      {entry.status === "error" && (
        <p className="chat-turn-error">Chưa có kết quả cho câu hỏi này. Xem chi tiết ở khung bên phải.</p>
      )}
      {entry.status === "done" && result && (
        <section
          aria-label={selected ? "Câu trả lời" : undefined}
          className="answer-panel chat-answer"
          data-outcome={answer?.outcome}
        >
          <p className="answer-summary">
            {answer?.summary ?? (evidence.length > 0
              ? `Tìm thấy ${views.documentViews.length} văn bản có nội dung liên quan; đọc trích dẫn nguyên văn ở khung kết quả.`
              : "Chưa tìm thấy căn cứ phù hợp trong phạm vi đã chọn.")}
          </p>
          {answer && answer.points.length > 0 && (
            <ul className="answer-points">
              {answer.points.map((point) => (
                <li key={point}>
                  {point}{" "}
                  <CiteLinks numbers={citedNumbers(point, mainDocuments)} onCite={onCite} />
                </li>
              ))}
            </ul>
          )}
          {mainDocuments.length > 0 && (
            <p className="chat-cites">
              <span className="evidence-meta">Căn cứ:</span>{" "}
              <CiteLinks
                numbers={mainDocuments.map((_, index) => index + 1)}
                onCite={onCite}
              />
            </p>
          )}
          {result.external_ai_used && (
            <p className="status-pill status-warning">Đã dùng API ngoài cho lượt này.</p>
          )}
          {notFound && !answer && null}
        </section>
      )}
    </article>
  );
}

export function EvidenceChat({
  accessToken, externalSync, onViewAllResults, operatingMode,
}: EvidenceChatProps) {
  const [question, setQuestion] = useState("");
  const [deepAnalysis, setDeepAnalysis] = useState(false);
  const [submittedQuestion, setSubmittedQuestion] = useState<string>();
  const [facts, setFacts] = useState<Fact[]>([]);
  const [categories, setCategories] = useState<AuthorizedCategory[]>([]);
  const [categoriesLoading, setCategoriesLoading] = useState(false);
  const [categoriesError, setCategoriesError] = useState<string>();
  const [scopeMode, setScopeMode] = useState<"ALL_AUTHORIZED" | "SELECTED">("ALL_AUTHORIZED");
  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
  const [asOfDate, setAsOfDate] = useState(localDateISO);
  const [history, setHistory] = useState<ChatEntry[]>([]);
  const [selectedId, setSelectedId] = useState<string>();
  const [tab, setTab] = useState<"chat" | "results">("chat");
  const [leftPct, setLeftPct] = useState(readStoredSplit);
  const [cited, setCited] = useState<{ entryId: string; n: number; tick: number }>();
  const narrow = useNarrow();
  const splitRef = useRef<HTMLDivElement | null>(null);
  const messagesRef = useRef<HTMLDivElement | null>(null);
  const draggingRef = useRef(false);
  const entrySeq = useRef(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const abortRef = useRef<AbortController | null>(null);
  const sessionRef = useRef<{ id: string; token: string } | null>(null);
  const sessionEpoch = useRef(0);
  const memoryBusyRef = useRef(false);
  const dateManuallySet = useRef(false);
  const lastTurnRef = useRef<{ sessionId: string; turnId: string; payloadKey: string } | null>(null);
  const [memoryItems, setMemoryItems] = useState<MemoryItem[]>([]);
  const [prefsEnabled, setPrefsEnabled] = useState(false);
  const [defaultCategoryIds, setDefaultCategoryIds] = useState<string[]>([]);
  const [memoryBusy, setMemoryBusy] = useState(false);

  const effectiveToken = accessToken ?? externalSync?.accessToken;

  useEffect(() => {
    const refreshDefaultDate = () => {
      if (!dateManuallySet.current) setAsOfDate(localDateISO());
    };
    window.addEventListener("focus", refreshDefaultDate);
    const timer = window.setInterval(refreshDefaultDate, 60_000);
    return () => {
      window.removeEventListener("focus", refreshDefaultDate);
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    // End the RAM session of the previous login (or on unmount) so no memory outlives it.
    return () => {
      sessionEpoch.current += 1;
      const owned = sessionRef.current;
      sessionRef.current = null;
      lastTurnRef.current = null;
      if (owned) void deleteAgentSession(owned.token, owned.id).catch(() => undefined);
    };
  }, [accessToken]);

  useEffect(() => {
    abortRef.current?.abort();
    setMemoryItems([]);
    setPrefsEnabled(false);
    setDefaultCategoryIds([]);
    setScopeMode("ALL_AUTHORIZED");
    setSelectedCategories([]);
    dateManuallySet.current = false;
    setAsOfDate(localDateISO());
    memoryBusyRef.current = false;
    setMemoryBusy(false);
    setQuestion("");
    setSubmittedQuestion(undefined);
    setFacts([]);
    setHistory([]);
    setSelectedId(undefined);
    setCited(undefined);
    setTab("chat");
    setError(undefined);
    setBusy(false);
  }, [accessToken]);

  useEffect(() => {
    if (!externalSync) return;
    const id = `ext-${externalSync.seq}`;
    setHistory((prev) => prev.some((entry) => entry.id === id) ? prev : [...prev, {
      id, question: externalSync.question ?? "Câu hỏi từ khung chat nổi", status: "done",
      result: externalSync.response,
    }]);
    setSelectedId(id);
    if (externalSync.question) {
      setSubmittedQuestion(externalSync.question);
    }
    setError(undefined);
  }, [externalSync]);

  useEffect(() => {
    try {
      window.localStorage.setItem(SPLIT_WIDTH_KEY, String(Math.round(leftPct * 10) / 10));
    } catch {
      /* layout preference only */
    }
  }, [leftPct]);

  useEffect(() => {
    const box = messagesRef.current;
    if (box) box.scrollTop = box.scrollHeight;
  }, [history]);

  useEffect(() => {
    if (!cited) return;
    const target = document.getElementById(`chat-doc-${cited.entryId}-${cited.n}`);
    target?.scrollIntoView?.({ behavior: "smooth", block: "start" });
    target?.focus?.({ preventScroll: true });
    const timer = window.setTimeout(
      () => setCited((current) => (current?.tick === cited.tick ? undefined : current)), 2600);
    return () => window.clearTimeout(timer);
  }, [cited]);

  useEffect(() => {
    if (!accessToken) {
      setCategories([]);
      setCategoriesLoading(false);
      setCategoriesError(undefined);
      return;
    }
    let active = true;
    const controller = new AbortController();
    setCategoriesLoading(true);
    setCategoriesError(undefined);
    listAuthorizedCategories(accessToken, { signal: controller.signal })
      .then((items) => {
        if (active && !controller.signal.aborted) {
          setCategories(items);
          setCategoriesLoading(false);
        }
      })
      .catch((caught) => {
        if (active && !controller.signal.aborted) {
          setCategories([]);
          setCategoriesLoading(false);
          setCategoriesError(
            caught instanceof Error
              ? caught.message
              : "Không thể tải phạm vi danh mục được phép.",
          );
        }
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [accessToken]);

  const selectedEntry = history.find((entry) => entry.id === selectedId) ?? history[history.length - 1];
  const result = selectedEntry?.status === "done" ? selectedEntry.result : undefined;
  const views = useMemo(() => buildViews(result), [result]);
  const { evidence, clauseLabels, mainDocuments, referenceDocuments } = views;
  const latestEntry = history[history.length - 1];
  const factsDirty = useMemo(() => facts.some((fact) => fact.dirty), [facts]);
  const answer = result?.answer ?? undefined;
  const canSubmit =
    Boolean(effectiveToken) &&
    !busy &&
    !memoryBusy &&
    !categoriesLoading &&
    !categoriesError &&
    Boolean(question.trim()) &&
    (scopeMode !== "SELECTED" || selectedCategories.length > 0);

  async function ensureSession(token: string, signal: AbortSignal): Promise<string> {
    if (signal.aborted) throw new DOMException("Đã dừng", "AbortError");
    const owned = sessionRef.current;
    if (owned && owned.token === token) return owned.id;
    const epoch = sessionEpoch.current;
    // Once the server creates a session, retain the response long enough to
    // delete it if the user stopped or changed accounts in the meantime.
    const created = await createAgentSession(token);
    if (signal.aborted || epoch !== sessionEpoch.current) {
      void deleteAgentSession(token, created.session_id).catch(() => undefined);
      throw new DOMException("Đã dừng", "AbortError");
    }
    const existing = sessionRef.current;
    if (existing && existing.token === token) {
      void deleteAgentSession(token, created.session_id).catch(() => undefined);
      return existing.id;
    }
    sessionRef.current = { id: created.session_id, token };
    return created.session_id;
  }

  async function refreshMemory() {
    const owned = sessionRef.current;
    if (!owned) {
      setMemoryItems([]);
      setPrefsEnabled(false);
      setDefaultCategoryIds([]);
      return;
    }
    try {
      const [items, prefs] = await Promise.all([
        listMemory(owned.token, owned.id),
        getMemoryPreferences(owned.token, owned.id),
      ]);
      if (sessionRef.current?.id !== owned.id) return;
      setMemoryItems(items);
      setPrefsEnabled(prefs.enabled);
      setDefaultCategoryIds(prefs.default_category_ids);
    } catch (caught) {
      if (sessionRef.current?.id === owned.id && caught instanceof ApiRequestError && caught.status === 410) {
        sessionEpoch.current += 1;
        sessionRef.current = null;
        lastTurnRef.current = null;
        setMemoryItems([]);
        setPrefsEnabled(false);
        setDefaultCategoryIds([]);
        setFacts([]);
        memoryBusyRef.current = false;
        setMemoryBusy(false);
        setError("Phiên bộ nhớ đã hết hạn và dữ kiện tạm đã được xóa. Hãy kiểm tra rồi thử lại.");
      }
    }
  }

  async function executeTurn(
    token: string,
    payload: TurnPayload,
    controller: AbortController,
    retry: boolean,
  ): Promise<QueryResponse> {
    const payloadKey = JSON.stringify(payload);
    let attemptedSessionId: string | undefined;
    const attempt = async (): Promise<QueryResponse> => {
      const sessionId = await ensureSession(token, controller.signal);
      attemptedSessionId = sessionId;
      const previous = lastTurnRef.current;
      const onTurnId = (turnId: string) => {
        if (!controller.signal.aborted && abortRef.current === controller &&
            sessionRef.current?.id === sessionId) {
          lastTurnRef.current = { sessionId, turnId, payloadKey };
        }
      };
      if (retry && previous && previous.sessionId === sessionId && previous.payloadKey === payloadKey) {
        lastTurnRef.current = null;
        try {
          return await retryAgentTurn(token, sessionId, previous.turnId, {
            signal: controller.signal, idempotencyKey: newIdempotencyKey(), onTurnId,
          });
        } catch (caught) {
          // The failed turn was invalidated (e.g. memory item deleted): ask again.
          if (!(caught instanceof ApiRequestError && caught.code === "TURN_NOT_FOUND")) throw caught;
        }
      }
      lastTurnRef.current = null;
      return runAgentTurn(token, sessionId, payload, {
        signal: controller.signal, idempotencyKey: newIdempotencyKey(), onTurnId,
      });
    };
    try {
      return await attempt();
    } catch (caught) {
      if (caught instanceof ApiRequestError && caught.status === 410 &&
          caught.code !== "RESULT_SET_EXPIRED" &&
          !controller.signal.aborted && abortRef.current === controller &&
          sessionRef.current?.id === attemptedSessionId) {
        sessionEpoch.current += 1;
        sessionRef.current = null;
        lastTurnRef.current = null;
        setMemoryItems([]);
        setPrefsEnabled(false);
        setDefaultCategoryIds([]);
        setFacts([]);
        throw new ApiRequestError(
          "Phiên bộ nhớ đã hết hạn và dữ kiện tạm đã được xóa. Hãy kiểm tra rồi thử lại.",
          410, "SESSION_EXPIRED",
        );
      }
      throw caught;
    }
  }

  function patchEntry(id: string, patch: Partial<ChatEntry>) {
    setHistory((prev) => prev.map((entry) => entry.id === id ? { ...entry, ...patch } : entry));
  }

  function resetHistory() {
    setHistory([]);
    setSelectedId(undefined);
    setCited(undefined);
    setSubmittedQuestion(undefined);
  }

  const citeEntry = useCallback((entryId: string, n: number) => {
    setSelectedId(entryId);
    setTab("results");
    setCited({ entryId, n, tick: Date.now() });
  }, []);

  async function runQuery(
    textToRun: string, options: { retry?: boolean; entryId?: string } = {},
  ) {
    const clean = textToRun.trim();
    if (!clean) return;
    if (memoryBusyRef.current) return;
    if (!effectiveToken) {
      setError("Hãy đăng nhập tài khoản trước khi tra cứu.");
      return;
    }
    if (categoriesLoading || categoriesError) {
      setError("Chưa tải được phạm vi danh mục. Hãy thử lại sau.");
      return;
    }
    if (scopeMode === "SELECTED" && selectedCategories.length === 0) {
      setError("Hãy chọn ít nhất một danh mục trước khi tra cứu.");
      return;
    }
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    // Facts belong to the question they were read from: re-running that question keeps
    // them (after the user edits or confirms one); a new question starts without any.
    const sameQuestion = clean === submittedQuestion;
    const sentFacts = sameQuestion ? facts : [];
    if (!sameQuestion) setFacts([]);
    setSubmittedQuestion(clean);
    entrySeq.current += 1;
    const entryId = options.entryId ?? `entry-${entrySeq.current}`;
    const replaced = options.entryId !== undefined;
    setHistory((prev) => {
      const settled = prev.map((entry) => entry.status === "loading"
        ? { ...entry, status: "error" as const, error: STOPPED_MESSAGE } : entry);
      return replaced && settled.some((entry) => entry.id === entryId)
        ? settled.map((entry) => entry.id === entryId
          ? { ...entry, status: "loading" as const, error: undefined, result: undefined } : entry)
        : [...settled, { id: entryId, question: clean, status: "loading" as const }];
    });
    setSelectedId(entryId);
    setCited(undefined);
    setBusy(true);
    setError(undefined);
    try {
      const queryDate = dateManuallySet.current ? asOfDate : localDateISO();
      setAsOfDate(queryDate);
      const payload = {
        question: clean,
        facts: sentFacts
          .filter((fact) => fact.value.trim())
          .map(({ key, value, status }) => ({ key, value, status })),
        scope: {
          scope_mode: scopeMode,
          category_ids: scopeMode === "SELECTED" ? selectedCategories : [],
          document_types: [],
          as_of_date: queryDate,
        },
        ...(operatingMode === "API" && deepAnalysis ? { deep_analysis: true } : {}),
      };
      const response = await executeTurn(
        effectiveToken, payload, controller, options.retry === true,
      );
      if (abortRef.current !== controller) return;
      patchEntry(entryId, { status: "done", result: response, error: undefined });
      setTab("results");
      setFacts(extractFactsFromQuestion(clean, sentFacts));
      void refreshMemory();
    } catch (caught) {
      if (abortRef.current !== controller) return;
      let message: string;
      if (controller.signal.aborted) {
        message = STOPPED_MESSAGE;
      } else if (caught instanceof ApiRequestError && caught.status === 401) {
        message = "Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại.";
      } else if (caught instanceof ApiRequestError && caught.code === "RESULT_SET_EXPIRED") {
        message = EXPIRED_MESSAGE;
      } else {
        message = caught instanceof Error ? caught.message : "Không thể tra cứu lúc này.";
      }
      patchEntry(entryId, { status: "error", error: message, result: undefined });
    } finally {
      if (abortRef.current === controller) {
        setBusy(false);
      }
    }
  }

  function submit() {
    void runQuery(question);
  }

  function stopCurrentQuery() {
    abortRef.current?.abort();
    setBusy(false);
    setHistory((prev) => prev.map((entry) => entry.status === "loading"
      ? { ...entry, status: "error" as const, error: STOPPED_MESSAGE } : entry));
    // Aborting the HTTP stream does not stop server work; cancel the turn explicitly.
    const turn = lastTurnRef.current;
    const owned = sessionRef.current;
    if (turn && owned && owned.id === turn.sessionId) {
      void cancelAgentTurn(owned.token, turn.sessionId, turn.turnId).catch(() => undefined);
    }
  }

  async function clearSessionMemory() {
    if (memoryBusyRef.current) return;
    memoryBusyRef.current = true;
    setMemoryBusy(true);
    sessionEpoch.current += 1;
    const epoch = sessionEpoch.current;
    abortRef.current?.abort();
    abortRef.current = null;
    const owned = sessionRef.current;
    setBusy(false);
    try {
      if (owned) {
        try { await clearMemory(owned.token, owned.id); }
        catch (caught) {
          if (!(caught instanceof ApiRequestError && caught.status === 410)) throw caught;
        }
      }
      if (sessionEpoch.current !== epoch) return;
      sessionRef.current = null;
      lastTurnRef.current = null;
      setFacts([]);
      setMemoryItems([]);
      setPrefsEnabled(false);
      setDefaultCategoryIds([]);
      resetHistory();
      setQuestion("");
      setError(undefined);
    } catch {
      if (sessionEpoch.current === epoch) {
        setError("Không thể xác nhận việc xóa bộ nhớ trên máy chủ. Hãy thử lại.");
      }
    } finally {
      if (sessionEpoch.current === epoch) {
        memoryBusyRef.current = false;
        setMemoryBusy(false);
      }
    }
  }

  async function removeMemoryItem(itemId: string) {
    const owned = sessionRef.current;
    if (!owned || memoryBusyRef.current) return;
    memoryBusyRef.current = true;
    setMemoryBusy(true);
    const epoch = sessionEpoch.current;
    try {
      await deleteMemoryItem(owned.token, owned.id, itemId);
      if (sessionEpoch.current !== epoch || sessionRef.current?.id !== owned.id) return;
      lastTurnRef.current = null;
      setFacts([]);
      resetHistory();
      await refreshMemory();
    } catch (caught) {
      if (sessionEpoch.current === epoch) {
        setError(caught instanceof Error ? caught.message : "Không thể xóa mục bộ nhớ.");
      }
    } finally {
      if (sessionEpoch.current === epoch) {
        memoryBusyRef.current = false;
        setMemoryBusy(false);
      }
    }
  }

  async function updateFacts(next: Fact[]) {
    const removed = facts.find((fact) => !next.some((item) => item.key === fact.key));
    const owned = sessionRef.current;
    if (!removed || !owned) {
      setFacts(next);
      return;
    }
    if (memoryBusyRef.current) return;
    memoryBusyRef.current = true;
    setMemoryBusy(true);
    const epoch = sessionEpoch.current;
    try {
      await deleteSessionFact(owned.token, owned.id, removed.key);
      if (sessionEpoch.current !== epoch || sessionRef.current?.id !== owned.id) return;
      setFacts(next);
      // The result of the latest question was built with the removed fact.
      setHistory((prev) => prev.slice(0, -1));
      setSelectedId(undefined);
      lastTurnRef.current = null;
      await refreshMemory();
    } catch (caught) {
      if (sessionEpoch.current === epoch) {
        setError(caught instanceof Error ? caught.message : "Không thể xóa dữ kiện trong phiên.");
      }
    } finally {
      if (sessionEpoch.current === epoch) {
        memoryBusyRef.current = false;
        setMemoryBusy(false);
      }
    }
  }

  async function togglePreferences(enabled: boolean) {
    if (!effectiveToken || memoryBusyRef.current ||
        (enabled && (scopeMode !== "SELECTED" || selectedCategories.length === 0))) return;
    memoryBusyRef.current = true;
    setMemoryBusy(true);
    const epoch = sessionEpoch.current;
    const controller = new AbortController();
    try {
      const sessionId = await ensureSession(effectiveToken, controller.signal);
      const preferences = {
        enabled,
        default_category_ids: enabled ? selectedCategories : [],
        default_as_of_date: null,
      };
      await setMemoryPreferences(effectiveToken, sessionId, preferences);
      if (sessionEpoch.current !== epoch) return;
      lastTurnRef.current = null;
      setPrefsEnabled(enabled);
      setDefaultCategoryIds(preferences.default_category_ids);
      await refreshMemory();
    } catch (caught) {
      if (sessionEpoch.current === epoch) {
        setError(caught instanceof Error ? caught.message : "Không thể lưu sở thích tra cứu.");
      }
    } finally {
      if (sessionEpoch.current === epoch) {
        memoryBusyRef.current = false;
        setMemoryBusy(false);
      }
    }
  }

  function toggleCategory(id: string) {
    setSelectedCategories((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id],
    );
  }

  const scopeLabel =
    scopeMode === "ALL_AUTHORIZED"
      ? prefsEnabled && defaultCategoryIds.length > 0
        ? `Danh mục mặc định đã lưu (${defaultCategoryIds.length})`
        : "Tất cả danh mục được phép"
      : `Đã chọn ${selectedCategories.length} danh mục`;
  const coverageEntries = Object.entries(result?.coverage_checks ?? {});
  const selectedIsLatest = Boolean(selectedEntry) && selectedEntry?.id === latestEntry?.id;

  function startDrag(event: PointerEvent<HTMLDivElement>) {
    draggingRef.current = true;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    event.preventDefault();
  }

  function moveDrag(event: PointerEvent<HTMLDivElement>) {
    if (!draggingRef.current) return;
    const box = splitRef.current?.getBoundingClientRect();
    if (!box || box.width <= 0) return;
    setLeftPct(clampSplit(((event.clientX - box.left) / box.width) * 100));
  }

  function endDrag(event: PointerEvent<HTMLDivElement>) {
    draggingRef.current = false;
    event.currentTarget.releasePointerCapture?.(event.pointerId);
  }

  function keyResize(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "ArrowLeft") setLeftPct((value) => clampSplit(value - 2));
    else if (event.key === "ArrowRight") setLeftPct((value) => clampSplit(value + 2));
    else if (event.key === "Home") setLeftPct(SPLIT_MIN);
    else if (event.key === "End") setLeftPct(SPLIT_MAX);
    else return;
    event.preventDefault();
  }

  const showChatPane = !narrow || tab === "chat";
  const showResultsPane = !narrow || tab === "results";

  return (
    <div className="chat-page chat-split-page">
      <header className="chat-header chat-header-compact">
        <h1>Hỏi đáp có căn cứ</h1>
        <p>
          Trả lời từ văn bản đã duyệt trong kho. Mỗi văn bản kèm điều, khoản liên quan,
          trích dẫn nguyên văn và nút mở đúng tệp gốc.
        </p>
      </header>
      {narrow && (
        <div aria-label="Chọn khung hiển thị" className="chat-tabs" role="tablist">
          <button
            aria-selected={tab === "chat"}
            className="chat-tab"
            onClick={() => setTab("chat")}
            role="tab"
            type="button"
          >
            Hỏi đáp
          </button>
          <button
            aria-selected={tab === "results"}
            className="chat-tab"
            onClick={() => setTab("results")}
            role="tab"
            type="button"
          >
            Kết quả
          </button>
        </div>
      )}
      <div
        className="chat-split"
        data-narrow={narrow}
        ref={splitRef}
        style={narrow ? undefined : { gridTemplateColumns: `${leftPct}% 10px minmax(0, 1fr)` }}
      >
        <section aria-label="Hỏi đáp" className="chat-pane chat-pane-left" hidden={!showChatPane}>
          <div className="chat-messages" ref={messagesRef}>
            {history.length === 0 && (
              <div className="sample-prompts" aria-label="Gợi ý câu hỏi mẫu">
                <span className="sample-prompts-title">Câu hỏi mẫu:</span>
                {STARTER_SUGGESTIONS.map((item) => (
                  <button
                    className="ai-prompt-chip"
                    disabled={busy || memoryBusy || !effectiveToken}
                    key={item}
                    onClick={() => {
                      setQuestion(item);
                      void runQuery(item);
                    }}
                    type="button"
                  >
                    {item}
                  </button>
                ))}
              </div>
            )}
            {history.map((entry) => (
              <ChatTurn
                entry={entry}
                key={entry.id}
                onCite={(n) => citeEntry(entry.id, n)}
                onSelect={() => {
                  setSelectedId(entry.id);
                  setCited(undefined);
                  if (narrow) setTab("results");
                }}
                selected={entry.id === selectedEntry?.id}
              />
            ))}
          </div>

          <div className="composer chat-composer">
            <textarea
              aria-label="Câu hỏi tra cứu"
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && (event.ctrlKey || event.metaKey) && canSubmit) {
                  event.preventDefault();
                  submit();
                }
              }}
              placeholder="Nhập câu hỏi, ví dụ: Thủ tục bổ nhiệm, miễn nhiệm trong Công an nhân dân"
              rows={2}
              value={question}
            />
            {categoriesError && (
              <p className="status-pill status-danger" role="alert">
                {categoriesError}
              </p>
            )}
            {categoriesLoading && (
              <p className="status-pill status-warning" role="status">
                Đang tải phạm vi danh mục được phép…
              </p>
            )}
            <div className="composer-options">
              {categories.length > 0 && (
                <div className="scope-selector" aria-label="Chọn phạm vi danh mục">
                  <label>
                    <input
                      checked={scopeMode === "ALL_AUTHORIZED"}
                      name="scope_mode"
                      onChange={() => setScopeMode("ALL_AUTHORIZED")}
                      type="radio"
                    />{" "}
                    {prefsEnabled && defaultCategoryIds.length > 0
                      ? `Danh mục mặc định đã lưu (${defaultCategoryIds.length})`
                      : `Tất cả danh mục (${categories.length})`}
                  </label>
                  <label>
                    <input
                      checked={scopeMode === "SELECTED"}
                      name="scope_mode"
                      onChange={() => setScopeMode("SELECTED")}
                      type="radio"
                    />{" "}
                    Chọn danh mục
                  </label>
                  {scopeMode === "SELECTED" && (
                    <div className="category-pills">
                      {categories.map((cat) => (
                        <label className="fact-chip" key={cat.id}>
                          <input
                            checked={selectedCategories.includes(cat.id)}
                            onChange={() => toggleCategory(cat.id)}
                            type="checkbox"
                          />
                          <span>{cat.name}</span>
                        </label>
                      ))}
                    </div>
                  )}
                </div>
              )}
              <label className="date-inline">
                Hiệu lực tại ngày{" "}
                <input
                  aria-label="Ngày hiệu lực"
                  onChange={(event) => {
                    dateManuallySet.current = Boolean(event.target.value);
                    setAsOfDate(event.target.value || localDateISO());
                  }}
                  type="date"
                  value={asOfDate}
                />
              </label>
              {operatingMode === "API" && (
                <label
                  className="date-inline"
                  title="Dùng model API ngoài nếu bạn và danh mục được phép; chỉ chạy khi đã tìm thấy căn cứ"
                >
                  <input
                    checked={deepAnalysis}
                    onChange={(event) => setDeepAnalysis(event.target.checked)}
                    type="checkbox"
                  />{" "}
                  Phân tích sâu
                </label>
              )}
            </div>
            <div className="composer-actions">
              <span className="scope-line">
                Phạm vi: {scopeLabel} · {asOfDate}
              </span>
              <div className="action-group">
                {busy && (
                  <button className="secondary-button" onClick={stopCurrentQuery} type="button">
                    Dừng
                  </button>
                )}
                <button
                  className="primary-button"
                  disabled={!canSubmit}
                  onClick={submit}
                  type="button"
                >
                  {busy ? "Đang tra cứu…" : "Tra cứu"}
                </button>
              </div>
            </div>
            {error && (
              <p className="status-pill status-danger" role="alert">
                {error}
              </p>
            )}
            {!effectiveToken && (
              <p className="status-pill status-warning" role="status">
                Đăng nhập để tra cứu và mở văn bản gốc.
              </p>
            )}
          </div>
        </section>

        {!narrow && (
          <div
            aria-label="Kéo để chỉnh độ rộng hai khung"
            aria-orientation="vertical"
            aria-valuemax={SPLIT_MAX}
            aria-valuemin={SPLIT_MIN}
            aria-valuenow={Math.round(leftPct)}
            className="chat-resizer"
            onKeyDown={keyResize}
            onPointerCancel={endDrag}
            onPointerDown={startDrag}
            onPointerMove={moveDrag}
            onPointerUp={endDrag}
            role="separator"
            tabIndex={0}
          />
        )}

        <section
          aria-label="Kết quả và căn cứ"
          className="chat-pane chat-pane-right"
          hidden={!showResultsPane}
        >
          {!selectedEntry && (
            <p className="chat-pane-empty">Kết quả và căn cứ sẽ hiển thị ở đây</p>
          )}
          {selectedEntry?.status === "loading" && (
            <p className="chat-pane-empty" role="status">Đang tìm căn cứ…</p>
          )}
          {selectedEntry?.status === "error" && (
            <div className="chat-pane-error">
              <p className="status-pill status-danger" role="alert">
                {selectedEntry.error ?? "Không thể tra cứu lúc này."}
              </p>
              <button
                className="secondary-button"
                disabled={busy || memoryBusy}
                onClick={() => void runQuery(selectedEntry.question, {
                  retry: true, entryId: selectedEntry.id,
                })}
                type="button"
              >
                Thử lại
              </button>
            </div>
          )}

          {result && selectedEntry && (
            <>
              <header className="results-header">
                <h2>Kết quả và căn cứ</h2>
                <span
                  className={evidence.length === 0
                    ? "status-pill status-warning" : "status-pill status-success"}
                >
                  {evidence.length} căn cứ
                </span>
              </header>
              {answer && answer.topics.length > 0 && (
                <div className="answer-topics">
                  <h3>Theo nhóm nội dung</h3>
                  <ul>
                    {answer.topics.map((topic) => (
                      <li key={topic.name}>
                        <strong>{topic.name}:</strong> {topic.references.join("; ")}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {answer && answer.notes.length > 0 && (
                <ul className="answer-notes" aria-label="Lưu ý">
                  {answer.notes.map((note) => (
                    <li key={note}>{note}</li>
                  ))}
                </ul>
              )}
              {mainDocuments.length > 0 && (
                <AiInterpretation
                  accessToken={effectiveToken}
                  deepAnalysis={operatingMode === "API" && deepAnalysis}
                  key={answer?.result_set_id}
                  onExpired={() => {
                    lastTurnRef.current = null;
                    patchEntry(selectedEntry.id, {
                      status: "error", error: EXPIRED_MESSAGE, result: undefined,
                    });
                    setQuestion(selectedEntry.question);
                  }}
                  resultSetId={answer?.result_set_id}
                />
              )}
              {result.disclaimer && <p className="answer-disclaimer">{result.disclaimer}</p>}
              {mainDocuments.length === 0 && (
                <p className="evidence-meta">Không có văn bản liên quan để hiển thị.</p>
              )}
              {mainDocuments.length > 0 && (
                <section aria-label="Văn bản liên quan" className="doc-list-section">
                  <h2>Văn bản liên quan ({mainDocuments.length})</h2>
                  <div className="doc-list">
                    {mainDocuments.map((document, index) => (
                      <div
                        className={cited?.entryId === selectedEntry.id && cited.n === index + 1
                          ? "doc-card-slot is-cited" : "doc-card-slot"}
                        id={`chat-doc-${selectedEntry.id}-${index + 1}`}
                        key={document.key}
                        tabIndex={-1}
                      >
                        <DocumentCard
                          accessToken={effectiveToken}
                          document={document}
                          index={index + 1}
                        />
                      </div>
                    ))}
                  </div>
                </section>
              )}
              {referenceDocuments.length > 0 && (
                <details className="doc-reference">
                  <summary>
                    Văn bản chỉ nhắc đến nội dung này trong danh mục, liệt kê ({referenceDocuments.length})
                  </summary>
                  <p className="evidence-meta">
                    Các đoạn dưới đây liệt kê tên văn bản khác có cụm từ của câu hỏi; không dùng làm căn
                    cứ trực tiếp.
                  </p>
                  <div className="doc-list">
                    {referenceDocuments.map((document) => (
                      <DocumentCard
                        accessToken={effectiveToken}
                        document={document}
                        key={document.key}
                      />
                    ))}
                  </div>
                </details>
              )}
              {onViewAllResults && (
                <div className="chat-search-link">
                  <button
                    className="secondary-button"
                    onClick={() => onViewAllResults(selectedEntry.question)}
                    type="button"
                  >
                    Xem tất cả kết quả tìm kiếm
                  </button>
                  <span className="evidence-meta">
                    Mở trang Tìm kiếm văn bản với câu hỏi này để xem toàn bộ kết quả và bộ lọc.
                  </span>
                </div>
              )}
            </>
          )}

          <details className="chat-technical">
            <summary>Thông tin kỹ thuật và phiên làm việc</summary>
            <div className="chat-technical-body">
              {answer && answer.understood_phrases.length > 0 && (
                <p className="evidence-meta">
                  Cụm từ dùng để tìm: {answer.understood_phrases.map((phrase) => `«${phrase}»`).join(" · ")}
                </p>
              )}
              <div className="chat-facts">
                <span className="evidence-meta">Dữ kiện đọc từ câu hỏi:</span>
                {facts.length === 0 && <span className="evidence-meta"> chưa có.</span>}
                {facts.length > 0 && !selectedIsLatest && (
                  <span className="evidence-meta"> (của câu hỏi mới nhất)</span>
                )}
                <FactChips
                  facts={facts}
                  onChange={busy || memoryBusy ? undefined : (next) => void updateFacts(next)}
                />
                {factsDirty && result && selectedIsLatest && (
                  <div className="status-pill status-warning" role="status">
                    Đã chỉnh sửa dữ kiện — kết quả bên trên dựa trên dữ kiện trước đó.
                    <button
                      className="inline-action-button"
                      disabled={busy || memoryBusy}
                      onClick={() => {
                        if (submittedQuestion && latestEntry) {
                          void runQuery(submittedQuestion, { entryId: latestEntry.id });
                        }
                      }}
                      type="button"
                    >
                      Cập nhật dữ kiện &amp; tra cứu lại
                    </button>
                  </div>
                )}
              </div>
              {result && (
                <ul className="chat-technical-list">
                  {result.status && (
                    <li>Trạng thái kết quả: {RESULT_STATUS_LABELS[result.status] ?? result.status}.</li>
                  )}
                  {coverageEntries.length > 0 && (
                    <li>
                      Kiểm tra: {coverageEntries
                        .map(([key, value]) =>
                          `${COVERAGE_LABELS[key] ?? key}: ${COVERAGE_STATE_LABELS[value] ?? value}`)
                        .join(" · ")}
                    </li>
                  )}
                  {result.ai_selection_applied && (
                    <li>Model đã hỗ trợ chọn căn cứ; nội dung hiển thị lấy nguyên văn từ nguồn.</li>
                  )}
                  {result.ai_limited && (
                    <li>Đã chạm trần chi phí model; kết quả hiển thị không dùng model đó.</li>
                  )}
                  {result.claims.map((claim) => (
                    <li key={`${claim.evidence_ids.join(",")}-${claim.text.slice(0, 24)}`}>
                      Trích dẫn {clauseLabels.get(claim.evidence_ids[0]) ?? "căn cứ"}: mức hỗ trợ{" "}
                      {CLAIM_STATUS_LABELS[claim.status] ?? claim.status}.
                    </li>
                  ))}
                  {(result.missing_information ?? []).map((info) => (
                    <li key={info}>{info}</li>
                  ))}
                </ul>
              )}
              {effectiveToken && (
                <details className="memory-panel">
                  <summary>Bộ nhớ phiên ({memoryItems.length})</summary>
                  <label className="checkbox-row">
                    <input
                      checked={prefsEnabled}
                      disabled={busy || memoryBusy || (!prefsEnabled &&
                        (scopeMode !== "SELECTED" || selectedCategories.length === 0))}
                      onChange={(event) => void togglePreferences(event.target.checked)}
                      type="checkbox"
                    />
                    <span>
                      Dùng phạm vi danh mục hiện tại làm mặc định cho các lượt sau (khi chọn "Tất cả
                      danh mục")
                    </span>
                  </label>
                  {memoryItems.length === 0 ? (
                    <p className="evidence-meta">Chưa có mục nào được ghi nhớ trong phiên này.</p>
                  ) : (
                    <ul className="memory-list">
                      {memoryItems.map((item) => (
                        <li key={item.id}>
                          <span title={item.content}>
                            {item.kind === "preferences" ? "Sở thích: " : "Câu hỏi: "}
                            {item.content.length > 80 ? `${item.content.slice(0, 78)}…` : item.content}
                          </span>
                          <button
                            className="inline-action-button"
                            disabled={busy || memoryBusy}
                            onClick={() => void removeMemoryItem(item.id)}
                            type="button"
                          >
                            Xóa
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                  <p className="evidence-meta">
                    Dữ liệu phiên chỉ nằm trong RAM, tự xóa khi hết hạn hoặc đăng xuất. Xóa một mục sẽ
                    làm mới ngữ cảnh nối tiếp của phiên.
                  </p>
                </details>
              )}
              {(facts.length > 0 || history.length > 0 || memoryItems.length > 0) && (
                <button
                  className="secondary-button"
                  disabled={memoryBusy}
                  onClick={() => void clearSessionMemory()}
                  title="Xóa dữ kiện và lịch sử tạm thời trong RAM của phiên này"
                  type="button"
                >
                  Xóa dữ liệu tạm ({facts.length + history.length + memoryItems.length})
                </button>
              )}
            </div>
          </details>
        </section>
      </div>
    </div>
  );
}
