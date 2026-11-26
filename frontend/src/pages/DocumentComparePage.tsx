import { useCallback, useEffect, useRef, useState } from "react";

import {
  ApiRequestError,
  compareDocuments,
  getDocumentVersions,
  runComprehensiveSearch,
  summarizeComparison,
  type ComprehensiveDocument,
} from "../api/client";
import { CompareDiffView } from "../components/CompareDiffView";
import { DOC_TYPE_LABELS, formatVnDate } from "../components/documentDisplay";
import { EffectivityBadges } from "../components/EffectivityBadges";
import type {
  ChangeSignalsView,
  CompareMode,
  ComparePreset,
  CompareRequest,
  CompareResponse,
  ComparisonItem,
  DocumentMeta,
  DocumentSide,
  DocumentVersionsResponse,
  RelatedAmendmentDocument,
  SideView,
  SummarizeFallbackReason,
  SummarizeResponse,
} from "../types";
import {
  COMPARE_AMENDMENT_ACTION_LABELS,
  COMPARE_KIND_LABELS,
  COMPARE_MODE_LABELS,
} from "../types";

/**
 * "So sánh văn bản": three selection modes on top of the ACL-safe C2 comparison API.
 * Everything shown is read-only evidence — the deterministic engine produces the diff,
 * the optional AI summary is explicitly requested and always labeled, and every result
 * carries the reference disclaimer. No legal data is ever modified from this page.
 */

export interface DocumentComparePageProps {
  accessToken?: string;
  /** Quick access from SearchPage/DocumentCard: one document preselected as side A. */
  preset?: ComparePreset;
}

/** Document metadata carried from the picker (source_format drives OpenOriginalButton). */
interface PickedDocument {
  id: string;
  title: string;
  document_number: string | null;
  doc_type: string;
  issuing_body: string | null;
  source_format: string;
}

const MODE_ORDER: CompareMode[] = ["versions", "amendment_pair", "cross_document"];

const FALLBACK_REASON_LABELS: Record<SummarizeFallbackReason, string> = {
  no_changes: "Không có thay đổi nội dung để tóm tắt.",
  ai_not_configured: "Máy chủ chưa cấu hình model AI cho tác vụ tóm tắt.",
  remote_blocked_by_document_policy:
    "Văn bản thuộc danh mục hạn chế xử lý từ xa; chỉ dùng kết quả xác định.",
  ai_timeout: "Model AI phản hồi quá lâu; đã dùng kết quả xác định.",
  ai_unavailable: "Không gọi được model AI; đã dùng kết quả xác định.",
  ai_error: "Model AI trả lỗi; đã dùng kết quả xác định.",
  ai_output_rejected: "Kết quả AI không đạt kiểm tra căn cứ; đã dùng kết quả xác định.",
};

const IMPACT_FILTER_LABELS = {
  all: "Tất cả",
  high: "Thay đổi cốt lõi (số liệu, thời hạn, nghĩa vụ)",
};

function metaToPick(meta: DocumentMeta): PickedDocument {
  // The versions/preset payloads carry no source_format; "pdf" is the repo default and
  // a wrong guess degrades gracefully inside OpenOriginalButton (tab → download).
  return {
    id: meta.id,
    title: meta.title,
    document_number: meta.document_number,
    doc_type: meta.doc_type,
    issuing_body: meta.issuing_body,
    source_format: "pdf",
  };
}

function pickFromSearch(document: ComprehensiveDocument): PickedDocument {
  return {
    id: document.document_id,
    title: document.display_title ?? document.title,
    document_number: document.document_number ?? null,
    doc_type: document.doc_type,
    issuing_body: document.issuing_body ?? null,
    source_format: document.source_format ?? "pdf",
  };
}

function errorMessage(caught: unknown): string {
  return caught instanceof Error ? caught.message : "Mất kết nối tới máy chủ. Hãy thử lại.";
}

/** Search box over the ALLOWED store (exact channel, documents view) for one side. */
function DocumentPicker({ accessToken, label, docType, onDocTypeChange, onPick, selectedId }: {
  accessToken?: string;
  label: string;
  docType: string;
  onDocTypeChange: (value: string) => void;
  onPick: (document: PickedDocument) => void;
  selectedId?: string;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ComprehensiveDocument[]>();
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string>();

  async function run() {
    const trimmed = query.trim();
    if (!accessToken || !trimmed) return;
    setSearching(true);
    setError(undefined);
    try {
      const response = await runComprehensiveSearch(accessToken, {
        q: trimmed,
        mode: "keywords",
        channels: ["exact"],
        display: "all",
        view: "documents",
        page_size: 8,
        clauses_per_document: 1,
        ...(docType ? { doc_types: [docType] } : {}),
      });
      setResults(response.documents ?? []);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setSearching(false);
    }
  }

  return (
    <div className="compare-picker">
      <form
        className="compare-picker-form"
        onSubmit={(event) => {
          event.preventDefault();
          void run();
        }}
        role="search"
      >
        <label className="field-label">
          {label}
          <input
            autoComplete="off"
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Số hiệu hoặc từ khóa, ví dụ: 55/2021/TT-BCA"
            type="search"
            value={query}
          />
        </label>
        <label className="field-label">
          Loại văn bản
          <select onChange={(event) => onDocTypeChange(event.target.value)} value={docType}>
            <option value="">Tất cả loại văn bản</option>
            {Object.entries(DOC_TYPE_LABELS).map(([value, text]) => (
              <option key={value} value={value}>{text}</option>
            ))}
          </select>
        </label>
        <button
          className="secondary-button"
          disabled={searching || !accessToken || !query.trim()}
          type="submit"
        >
          {searching ? "Đang tìm…" : "Tìm văn bản"}
        </button>
      </form>
      {error && <p className="status-pill status-danger" role="alert">{error}</p>}
      {results && results.length === 0 && (
        <p className="evidence-meta">Không tìm thấy văn bản phù hợp trong phạm vi được phép.</p>
      )}
      {results && results.length > 0 && (
        <ul className="compare-picker-results">
          {results.map((document) => (
            <li key={document.document_id}>
              <button
                className="compare-pick-option"
                data-selected={document.document_id === selectedId ? "true" : undefined}
                onClick={() => onPick(pickFromSearch(document))}
                type="button"
              >
                <strong>{document.document_number ?? document.title}</strong>
                <span>{document.display_title ?? document.title}</span>
                <small>
                  {DOC_TYPE_LABELS[document.doc_type] ?? document.doc_type}
                  {document.issuing_body ? ` · ${document.issuing_body}` : ""}
                </small>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function sideCitation(doc: DocumentSide, side: SideView | null): string {
  if (!side) return "không có nội dung tương ứng";
  const label = side.citation_label || side.structural_key || "Đoạn văn";
  const pages = side.page_start == null
    ? ""
    : side.page_end != null && side.page_end > side.page_start
      ? `, trang ${side.page_start}–${side.page_end}`
      : `, trang ${side.page_start}`;
  return `${doc.document_number ?? doc.title} — ${label}${pages} (phiên bản ${doc.version_number})`;
}

function signalReportText(signals: ChangeSignalsView): string {
  const parts: string[] = [];
  if (signals.deadlines_changed.length > 0) {
    parts.push(`thời hạn: ${signals.deadlines_changed.map((span) => span.raw_text).join(", ")}`);
  }
  if (signals.amounts_changed.length > 0) {
    parts.push(`mức tiền/số lượng: ${signals.amounts_changed.map((span) => span.raw_text).join(", ")}`);
  }
  if (signals.dates_changed.length > 0) {
    parts.push(`ngày: ${signals.dates_changed
      .map(([day, month, year]) =>
        `${String(day).padStart(2, "0")}/${String(month).padStart(2, "0")}/${year}`)
      .join(", ")}`);
  }
  if (signals.modality_shifted) parts.push("thay đổi mức độ bắt buộc/cho phép/cấm");
  if (signals.exception_changed) parts.push("thay đổi ngoại lệ");
  return parts.join("; ");
}

function quoteBlock(text: string | null): string {
  if (!text) return "> (không có nội dung)";
  return text.split("\n").map((line) => `> ${line}`).join("\n");
}

/** Plain-text Markdown report: document numbers, Điều/Khoản labels and pages of both sides. */
function buildMarkdownReport(
  result: CompareResponse,
  items: ComparisonItem[],
  ai: SummarizeResponse | undefined,
  filters: { onlyChanges: boolean; impactFilter: "all" | "high" },
): string {
  const summary = result.summary;
  const lines: string[] = [
    "# Báo cáo đối chiếu văn bản",
    "",
    `- Chế độ: ${COMPARE_MODE_LABELS[result.mode]}`,
    `- Ngày đối chiếu: ${formatVnDate(result.as_of_date) ?? result.as_of_date}`,
    `- Vế A: ${result.left_doc.document_number ?? result.left_doc.title} — ${result.left_doc.title} (phiên bản ${result.left_doc.version_number})`,
    `- Vế B: ${result.right_doc.document_number ?? result.right_doc.title} — ${result.right_doc.title} (phiên bản ${result.right_doc.version_number})`,
    `- Bộ lọc khi sao chép: ${filters.onlyChanges ? "chỉ điểm thay đổi" : "tất cả các mục"}${filters.impactFilter === "high" ? ", chỉ tác động cốt lõi" : ""}`,
    `- Tổng số mục: ${summary.total_items} — Thêm mới: ${summary.added}; Bị bãi bỏ/Xóa: ${summary.removed}; Sửa đổi: ${summary.modified}; Đổi vị trí/số Điều: ${summary.moved_or_renumbered}; Không đổi: ${summary.unchanged}`,
    `- Thay đổi tác động cốt lõi (thời hạn/con số/nghĩa vụ – cấm đoán): ${summary.high_impact_changes}`,
  ];
  if (summary.explicit_amendment_links > 0) {
    lines.push(`- Căn chỉnh theo liên kết sửa đổi đã duyệt: ${summary.explicit_amendment_links}`);
  }
  lines.push("", `## Các mục đối chiếu (${items.length})`, "");
  items.forEach((item, index) => {
    const label = item.left?.citation_label || item.right?.citation_label
      || item.left?.structural_key || item.right?.structural_key || "Đoạn văn";
    lines.push(`### ${index + 1}. [${COMPARE_KIND_LABELS[item.change_kind]}] ${label}`);
    if (item.alignment_method) {
      const alignment = item.alignment_method === "semantic_lexical"
        && item.change_kind === "moved_or_renumbered"
        ? "Khớp nội dung — đổi số hiệu"
        : item.alignment_method === "explicit_amendment"
          ? "Liên kết sửa đổi đã duyệt"
          : item.alignment_method === "structural_key"
            ? "Khớp số Điều"
            : "Khớp nội dung";
      lines.push(`- Phương pháp căn chỉnh: ${alignment}`);
    }
    if (item.change_kind === "moved_or_renumbered" && item.content_also_modified) {
      lines.push("- Ghi chú: đổi vị trí/số Điều kèm sửa nội dung");
    }
    lines.push(`- Vế A: ${sideCitation(result.left_doc, item.left)}`);
    lines.push(`- Vế B: ${sideCitation(result.right_doc, item.right)}`);
    const signals = signalReportText(item.signals);
    if (signals) lines.push(`- Tín hiệu thay đổi: ${signals}`);
    if (item.amendment_link) {
      const action = item.amendment_link.action
        ? COMPARE_AMENDMENT_ACTION_LABELS[item.amendment_link.action] ?? item.amendment_link.action
        : "sửa đổi";
      const from = item.amendment_link.valid_from
        ? ` — hiệu lực từ ${formatVnDate(item.amendment_link.valid_from) ?? item.amendment_link.valid_from}`
        : "";
      lines.push(`- Liên kết sửa đổi đã duyệt: ${action}${from}`);
      if (item.amendment_link.source_quote) {
        lines.push(`  > «${item.amendment_link.source_quote}»`);
      }
    }
    lines.push("- Nguyên văn vế A:", quoteBlock(item.left?.text_original ?? null));
    lines.push("- Nguyên văn vế B:", quoteBlock(item.right?.text_original ?? null));
    lines.push("");
  });
  if (ai) {
    lines.push("## Tóm tắt thay đổi cốt lõi", "");
    lines.push(ai.mode_used === "ai"
      ? "Tóm tắt tham khảo từ AI — đã đối chiếu số liệu với căn cứ"
      : `Tóm tắt xác định (không dùng AI)${ai.reason ? ` — ${FALLBACK_REASON_LABELS[ai.reason] ?? ai.reason}` : ""}`);
    if (ai.executive_summary) lines.push("", ai.executive_summary);
    for (const change of ai.key_changes) {
      const status = change.status === "verified" ? "đã đối chiếu căn cứ" : "CẦN THẨM ĐỊNH";
      lines.push(`- ${change.point} [${status}]`);
      if (change.check_notes.length > 0) {
        lines.push(`  - Ghi chú kiểm tra: ${change.check_notes.join("; ")}`);
      }
    }
    lines.push("");
  }
  if (summary.deterministic_highlights.length > 0) {
    lines.push("## Điểm nhấn xác định", "");
    for (const highlight of summary.deterministic_highlights) lines.push(`- ${highlight}`);
    lines.push("");
  }
  lines.push(result.disclaimer);
  return lines.join("\n");
}

export function DocumentComparePage({ accessToken, preset }: DocumentComparePageProps) {
  const [mode, setMode] = useState<CompareMode>(preset?.mode ?? "versions");
  const [leftPick, setLeftPick] = useState<PickedDocument>();
  const [rightPick, setRightPick] = useState<PickedDocument>();
  const [leftDocType, setLeftDocType] = useState("");
  const [rightDocType, setRightDocType] = useState("");
  const [versions, setVersions] = useState<DocumentVersionsResponse>();
  const [versionsError, setVersionsError] = useState<string>();
  const [leftVersionId, setLeftVersionId] = useState("");
  const [rightVersionId, setRightVersionId] = useState("");
  const [asOfDate, setAsOfDate] = useState("");
  const [onlyChanges, setOnlyChanges] = useState(true);
  const [impactFilter, setImpactFilter] = useState<"all" | "high">("all");
  const [displayMode, setDisplayMode] = useState<"side_by_side" | "inline">("side_by_side");
  const [result, setResult] = useState<CompareResponse>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [errorHint, setErrorHint] = useState<string>();
  // The summary is tied to the comparison_id of the result that was on screen when the
  // user asked for it (NOT aiResult.response.comparison_id — the server recomputes and
  // issues a fresh UUID per request). It renders only while that tie still matches.
  const [aiResult, setAiResult] =
    useState<{ comparisonId: string; response: SummarizeResponse }>();
  const [aiBusy, setAiBusy] = useState(false);
  const [aiError, setAiError] = useState<string>();
  const [copied, setCopied] = useState(false);
  const [copyMessage, setCopyMessage] = useState<string>();

  // Stale-response guards (review fix round 1): every selection change bumps the
  // sequence and aborts in-flight requests; a response may populate state only if its
  // captured sequence is still current and its own controller was not aborted.
  const requestSeq = useRef(0);
  const compareController = useRef<AbortController | null>(null);
  const aiController = useRef<AbortController | null>(null);

  const resetOutputs = useCallback(() => {
    requestSeq.current += 1;
    compareController.current?.abort();
    compareController.current = null;
    aiController.current?.abort();
    aiController.current = null;
    setResult(undefined);
    setAiResult(undefined);
    setError(undefined);
    setErrorHint(undefined);
    setAiError(undefined);
    setBusy(false);
    setAiBusy(false);
    setCopied(false);
    setCopyMessage(undefined);
  }, []);

  // Unmount: abort everything and invalidate any pending response so no state update
  // can leak after the page is gone (logout/tab switch unmounts it).
  useEffect(() => () => {
    requestSeq.current += 1;
    compareController.current?.abort();
    aiController.current?.abort();
  }, []);

  // Quick-access preset: resolve the preselected document id(s) to metadata.
  useEffect(() => {
    if (!preset || !accessToken) return undefined;
    setMode(preset.mode);
    resetOutputs();
    let active = true;
    void (async () => {
      if (preset.leftDocumentId) {
        try {
          const response = await getDocumentVersions(accessToken, preset.leftDocumentId);
          if (!active) return;
          setLeftPick(metaToPick(response.document));
          if (preset.mode !== "cross_document") {
            setVersions(response);
            setRightVersionId(response.versions[0]?.id ?? "");
            setLeftVersionId(response.versions[1]?.id ?? response.versions[0]?.id ?? "");
          }
        } catch (caught) {
          if (active) setError(errorMessage(caught));
        }
      }
      if (preset.rightDocumentId && preset.mode !== "versions") {
        try {
          const response = await getDocumentVersions(accessToken, preset.rightDocumentId);
          if (active) setRightPick(metaToPick(response.document));
        } catch {
          // The right side can always be picked manually.
        }
      }
    })();
    return () => {
      active = false;
    };
  }, [preset, accessToken, resetOutputs]);

  // Versions of the left document (versions + amendment_pair modes).
  useEffect(() => {
    if (!accessToken || !leftPick || mode === "cross_document") return undefined;
    if (versions?.document.id === leftPick.id) return undefined;
    let active = true;
    setVersionsError(undefined);
    getDocumentVersions(accessToken, leftPick.id)
      .then((response) => {
        if (!active) return;
        setVersions(response);
        // Default: newest (current) version on side B, the previous one on side A.
        setRightVersionId(response.versions[0]?.id ?? "");
        setLeftVersionId(response.versions[1]?.id ?? response.versions[0]?.id ?? "");
      })
      .catch((caught) => {
        if (active) setVersionsError(errorMessage(caught));
      });
    return () => {
      active = false;
    };
  }, [accessToken, leftPick, mode, versions]);

  const versionList = versions && leftPick && versions.document.id === leftPick.id
    ? versions.versions
    : [];
  const related: RelatedAmendmentDocument[] =
    mode === "amendment_pair" && versions && leftPick && versions.document.id === leftPick.id
      ? versions.related_amendment_documents
      : [];

  function changeMode(next: CompareMode) {
    setMode(next);
    resetOutputs();
    if (next === "versions") setRightPick(undefined);
  }

  function pickLeft(document: PickedDocument) {
    setLeftPick(document);
    setVersions(undefined);
    setLeftVersionId("");
    setRightVersionId("");
    if (mode !== "cross_document") setRightPick(undefined);
    resetOutputs();
  }

  function pickRight(document: PickedDocument) {
    setRightPick(document);
    resetOutputs();
  }

  /** One-click suggestion: place the original on side A, the amending document on B. */
  function pickRelated(entry: RelatedAmendmentDocument) {
    const picked = metaToPick(entry);
    if (entry.directions.includes("amends_this_document")) {
      setRightPick(picked);
    } else if (leftPick) {
      // The picked document amends this one: swap so the original stays on side A.
      setRightPick(leftPick);
      setLeftPick(picked);
      setVersions(undefined);
      setLeftVersionId("");
      setRightVersionId("");
    }
    resetOutputs();
  }

  const buildPayload = useCallback((): CompareRequest | undefined => {
    if (!leftPick) return undefined;
    const rightId = mode === "versions" ? leftPick.id : rightPick?.id;
    if (!rightId) return undefined;
    return {
      mode,
      left_document_id: leftPick.id,
      right_document_id: rightId,
      left_version_id: mode === "versions" ? leftVersionId || null : null,
      right_version_id: mode === "versions" ? rightVersionId || null : null,
      as_of_date: asOfDate || null,
      // The full pair list is fetched once; the toolbar filters client-side so toggling
      // is instant and the reading order (and summary counts) stay stable.
      only_changes: false,
      include_embeddings: true,
    };
  }, [mode, leftPick, rightPick, leftVersionId, rightVersionId, asOfDate]);

  const canCompare = Boolean(
    accessToken && leftPick && !busy && (
      mode === "versions"
        ? versionList.length >= 2 && leftVersionId && rightVersionId
          && leftVersionId !== rightVersionId
        : rightPick && rightPick.id !== leftPick.id
    ),
  );

  async function runCompare() {
    const payload = buildPayload();
    if (!accessToken || !payload) return;
    resetOutputs();
    const seq = requestSeq.current;
    const controller = new AbortController();
    compareController.current = controller;
    setBusy(true);
    try {
      const response = await compareDocuments(accessToken, payload, { signal: controller.signal });
      // A selection change (or unmount) bumped the sequence: this response belongs to
      // an old selection and must never populate state.
      if (seq !== requestSeq.current || controller.signal.aborted) return;
      setResult(response);
    } catch (caught) {
      // Aborted requests (selection change/unmount) are silent, never an error banner.
      if (seq !== requestSeq.current || controller.signal.aborted) return;
      if (caught instanceof ApiRequestError) {
        setError(caught.message);
        const hint = caught.details?.hint;
        if (typeof hint === "string") setErrorHint(hint);
      } else {
        setError(errorMessage(caught));
      }
    } finally {
      if (seq === requestSeq.current && compareController.current === controller) {
        setBusy(false);
        compareController.current = null;
      }
    }
  }

  async function runSummarize() {
    const payload = buildPayload();
    if (!accessToken || !payload || !result) return;
    // Identity tie: remember which on-screen comparison this summary was requested for.
    const comparisonId = result.comparison_id;
    const seq = requestSeq.current;
    aiController.current?.abort();
    const controller = new AbortController();
    aiController.current = controller;
    setAiBusy(true);
    setAiError(undefined);
    setAiResult(undefined);
    try {
      const response = await summarizeComparison(accessToken, payload, { signal: controller.signal });
      if (seq !== requestSeq.current || controller.signal.aborted) return;
      setAiResult({ comparisonId, response });
    } catch (caught) {
      if (seq !== requestSeq.current || controller.signal.aborted) return;
      if (caught instanceof ApiRequestError) {
        const hint = caught.details?.hint;
        setAiError(typeof hint === "string" ? `${caught.message} ${hint}` : caught.message);
      } else {
        setAiError(errorMessage(caught));
      }
    } finally {
      if (seq === requestSeq.current && aiController.current === controller) {
        setAiBusy(false);
        aiController.current = null;
      }
    }
  }

  // The AI block (and the report's AI section) only renders when the stored tie still
  // matches the current result — a summary for comparison A can never appear under B.
  const aiForCurrentResult = aiResult && result && aiResult.comparisonId === result.comparison_id
    ? aiResult.response
    : undefined;

  const visibleItems = (result?.items ?? []).filter((item) =>
    (!onlyChanges || item.change_kind !== "unchanged")
    && (impactFilter === "all" || item.impact_level === "high"));

  function copyReport() {
    if (!result) return;
    const text = buildMarkdownReport(result, visibleItems, aiForCurrentResult, { onlyChanges, impactFilter });
    const report = (ok: boolean) => {
      setCopied(ok);
      setCopyMessage(ok
        ? "Đã sao chép báo cáo Markdown"
        : "Không thể sao chép tự động. Hãy thử lại hoặc sao chép thủ công.");
    };
    const fallback = () => {
      const focused = document.activeElement;
      const field = document.createElement("textarea");
      field.value = text;
      field.readOnly = true;
      field.style.cssText = "position:fixed;inset-block-start:0;opacity:0";
      document.body.append(field);
      field.select();
      try {
        report(typeof document.execCommand === "function" && document.execCommand("copy"));
      } catch {
        report(false);
      } finally {
        field.remove();
        if (focused instanceof HTMLElement) focused.focus({ preventScroll: true });
      }
    };
    if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
      void navigator.clipboard.writeText(text).then(() => report(true)).catch(fallback);
    } else {
      fallback();
    }
  }

  const leftSourceFormat = leftPick?.source_format ?? "pdf";
  // In versions mode both sides are the same picked document, so they share its format.
  const rightSourceFormat = mode === "versions"
    ? leftSourceFormat
    : rightPick?.source_format ?? "pdf";

  return (
    <div className="compare-page">
      <header className="compare-header">
        <h1>So sánh văn bản</h1>
        <p>
          Đối chiếu hai phiên bản của một văn bản hoặc hai văn bản trong kho được phép: điểm
          thay đổi, tín hiệu thời hạn/con số/nghĩa vụ và căn cứ hiệu lực. Kết quả chỉ mang tính
          tham khảo, không thay thế thẩm định của chuyên viên.
        </p>
      </header>

      {!accessToken && (
        <p className="status-pill status-warning" role="status">
          Đăng nhập để so sánh văn bản trong phạm vi được phép.
        </p>
      )}

      <fieldset className="compare-modes">
        <legend>Chế độ so sánh</legend>
        {MODE_ORDER.map((value) => (
          <label className="compare-mode-option" key={value}>
            <input
              checked={mode === value}
              name="compare-mode"
              onChange={() => changeMode(value)}
              type="radio"
            />
            <span>{COMPARE_MODE_LABELS[value]}</span>
          </label>
        ))}
      </fieldset>

      <section aria-label="Chọn văn bản so sánh" className="compare-selection admin-card">
        {mode === "versions" && (
          <>
            <DocumentPicker
              accessToken={accessToken}
              docType={leftDocType}
              label="Văn bản cần so sánh phiên bản"
              onDocTypeChange={setLeftDocType}
              onPick={pickLeft}
              selectedId={leftPick?.id}
            />
            {leftPick && versionList.length === 0 && !versionsError && (
              <p className="evidence-meta" role="status">Đang tải danh sách phiên bản…</p>
            )}
            {versionsError && (
              <p className="status-pill status-danger" role="alert">{versionsError}</p>
            )}
            {leftPick && versionList.length === 1 && (
              <p className="evidence-meta">
                Văn bản này chỉ có một phiên bản đã duyệt và kiểm chứng nguồn trong kho;
                không thể so sánh phiên bản.
              </p>
            )}
            {versionList.length >= 2 && (
              <div className="compare-version-row">
                <label className="field-label">
                  Phiên bản cũ (vế A)
                  <select
                    onChange={(event) => {
                      setLeftVersionId(event.target.value);
                      resetOutputs();
                    }}
                    value={leftVersionId}
                  >
                    {versionList.map((version) => (
                      <option key={version.id} value={version.id}>
                        Phiên bản {version.version_number} ({version.is_current ? "hiện hành" : "đã thay thế"})
                        {version.publication_date
                          ? ` — ban hành ${formatVnDate(version.publication_date)}`
                          : ""}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field-label">
                  Phiên bản mới (vế B)
                  <select
                    onChange={(event) => {
                      setRightVersionId(event.target.value);
                      resetOutputs();
                    }}
                    value={rightVersionId}
                  >
                    {versionList.map((version) => (
                      <option key={version.id} value={version.id}>
                        Phiên bản {version.version_number} ({version.is_current ? "hiện hành" : "đã thay thế"})
                        {version.publication_date
                          ? ` — ban hành ${formatVnDate(version.publication_date)}`
                          : ""}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            )}
            {leftVersionId && leftVersionId === rightVersionId && versionList.length >= 2 && (
              <p className="evidence-meta">Hai vế đang chọn cùng một phiên bản; hãy chọn hai phiên bản khác nhau.</p>
            )}
          </>
        )}

        {mode === "amendment_pair" && (
          <>
            <DocumentPicker
              accessToken={accessToken}
              docType={leftDocType}
              label="Văn bản gốc (vế A)"
              onDocTypeChange={setLeftDocType}
              onPick={pickLeft}
              selectedId={leftPick?.id}
            />
            {related.length > 0 && (
              <div aria-label="Văn bản sửa đổi/bổ sung liên kết" className="compare-related" role="group">
                <p className="evidence-meta">
                  Văn bản sửa đổi/bổ sung/thay thế đã duyệt, liên kết với văn bản gốc:
                </p>
                <ul>
                  {related.map((entry) => (
                    <li key={entry.id}>
                      <button
                        className="secondary-button"
                        data-selected={rightPick?.id === entry.id ? "true" : undefined}
                        onClick={() => pickRelated(entry)}
                        type="button"
                      >
                        {entry.document_number ?? entry.title}
                        {" — "}
                        {entry.actions.map((action) =>
                          COMPARE_AMENDMENT_ACTION_LABELS[action] ?? action).join(", ")}
                      </button>
                      <small>
                        {entry.title}
                        {entry.directions.includes("amended_by_this_document")
                          && !entry.directions.includes("amends_this_document")
                          ? " (văn bản gốc đã chọn sửa đổi văn bản này — hai vế sẽ đổi chỗ)"
                          : ""}
                      </small>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <DocumentPicker
              accessToken={accessToken}
              docType={rightDocType}
              label="Văn bản sửa đổi/bổ sung (vế B) — chọn thủ công"
              onDocTypeChange={setRightDocType}
              onPick={pickRight}
              selectedId={rightPick?.id}
            />
          </>
        )}

        {mode === "cross_document" && (
          <div className="compare-cross-pickers">
            <DocumentPicker
              accessToken={accessToken}
              docType={leftDocType}
              label="Văn bản vế A"
              onDocTypeChange={setLeftDocType}
              onPick={pickLeft}
              selectedId={leftPick?.id}
            />
            <DocumentPicker
              accessToken={accessToken}
              docType={rightDocType}
              label="Văn bản vế B"
              onDocTypeChange={setRightDocType}
              onPick={pickRight}
              selectedId={rightPick?.id}
            />
          </div>
        )}

        {leftPick && (
          <p className="compare-picked" data-side="left">
            Vế A: <strong>{leftPick.document_number ?? leftPick.title}</strong> — {leftPick.title}
          </p>
        )}
        {mode !== "versions" && rightPick && (
          <p className="compare-picked" data-side="right">
            Vế B: <strong>{rightPick.document_number ?? rightPick.title}</strong> — {rightPick.title}
          </p>
        )}
        {mode !== "versions" && leftPick && rightPick && leftPick.id === rightPick.id && (
          <p className="evidence-meta">Hai vế đang chọn cùng một văn bản; hãy chọn hai văn bản khác nhau.</p>
        )}

        <div className="compare-run-row">
          <label className="field-label">
            Hiệu lực tại ngày
            <input
              onChange={(event) => {
                setAsOfDate(event.target.value);
                resetOutputs();
              }}
              type="date"
              value={asOfDate}
            />
          </label>
          <button
            className="primary-button"
            disabled={!canCompare}
            onClick={() => void runCompare()}
            type="button"
          >
            {busy ? "Đang so sánh…" : "So sánh"}
          </button>
        </div>
      </section>

      {error && (
        <p className="status-pill status-danger" role="alert">
          {error}
          {errorHint ? ` ${errorHint}` : ""}
        </p>
      )}
      {busy && <p className="chat-progress" role="status">Đang so sánh…</p>}

      {result && (
        <section aria-label="Kết quả so sánh" aria-live="polite" className="compare-result">
          <div className="compare-result-head">
            <div className="compare-result-doc" data-side="left">
              <strong>{result.left_doc.document_number ?? result.left_doc.title}</strong>
              <span>{result.left_doc.title}</span>
              <small>Phiên bản {result.left_doc.version_number}</small>
              <EffectivityBadges view={result.left_doc.effectivity} />
            </div>
            <span className="compare-vs">so với</span>
            <div className="compare-result-doc" data-side="right">
              <strong>{result.right_doc.document_number ?? result.right_doc.title}</strong>
              <span>{result.right_doc.title}</span>
              <small>Phiên bản {result.right_doc.version_number}</small>
              <EffectivityBadges view={result.right_doc.effectivity} />
            </div>
          </div>

          <div aria-label="Tổng hợp kết quả so sánh" className="compare-summary-cards" role="group">
            <div className="compare-count-card" data-kind="added">
              <strong>{result.summary.added}</strong>
              <span>Thêm mới</span>
            </div>
            <div className="compare-count-card" data-kind="removed">
              <strong>{result.summary.removed}</strong>
              <span>Bị bãi bỏ/Xóa</span>
            </div>
            <div className="compare-count-card" data-kind="modified">
              <strong>{result.summary.modified}</strong>
              <span>Sửa đổi</span>
            </div>
            <div className="compare-count-card" data-kind="moved_or_renumbered">
              <strong>{result.summary.moved_or_renumbered}</strong>
              <span>Đổi vị trí/số Điều</span>
            </div>
            <div className="compare-count-card" data-kind="unchanged">
              <strong>{result.summary.unchanged}</strong>
              <span>Không đổi</span>
            </div>
          </div>

          {result.summary.high_impact_changes > 0 && (
            <p className="status-pill status-warning" role="status">
              {result.summary.high_impact_changes} điểm thay đổi về thời hạn / con số /
              nghĩa vụ – cấm đoán. Cần đối chiếu kỹ trước khi áp dụng.
            </p>
          )}
          <p className="evidence-meta">
            Tổng số mục đối chiếu: {result.summary.total_items}
            {result.summary.explicit_amendment_links > 0
              ? `; ${result.summary.explicit_amendment_links} cặp căn chỉnh theo liên kết sửa đổi đã duyệt`
              : ""}
            ; hiệu lực tính tại ngày {formatVnDate(result.as_of_date) ?? result.as_of_date}.
          </p>
          {result.summary.deterministic_highlights.length > 0 && (
            <details className="compare-highlights-block" open>
              <summary>
                Điểm nhấn xác định ({result.summary.deterministic_highlights.length})
              </summary>
              <ul className="compare-highlights">
                {result.summary.deterministic_highlights.map((highlight, index) => (
                  <li key={index}>{highlight}</li>
                ))}
              </ul>
            </details>
          )}

          <div aria-label="Bộ lọc kết quả so sánh" className="compare-toolbar" role="group">
            <label className="fact-chip compare-only-changes">
              <input
                checked={onlyChanges}
                onChange={(event) => setOnlyChanges(event.target.checked)}
                type="checkbox"
              />
              <span>Chỉ xem điểm thay đổi</span>
            </label>
            <label className="field-label">
              Mức tác động
              <select
                onChange={(event) => setImpactFilter(event.target.value as "all" | "high")}
                value={impactFilter}
              >
                <option value="all">{IMPACT_FILTER_LABELS.all}</option>
                <option value="high">{IMPACT_FILTER_LABELS.high}</option>
              </select>
            </label>
            <div aria-label="Chế độ hiển thị" className="compare-display-switch" role="group">
              <button
                aria-pressed={displayMode === "side_by_side"}
                className={displayMode === "side_by_side"
                  ? "secondary-button active" : "secondary-button"}
                onClick={() => setDisplayMode("side_by_side")}
                type="button"
              >
                Song song (2 cột)
              </button>
              <button
                aria-pressed={displayMode === "inline"}
                className={displayMode === "inline"
                  ? "secondary-button active" : "secondary-button"}
                onClick={() => setDisplayMode("inline")}
                type="button"
              >
                Gộp dòng (Inline)
              </button>
            </div>
            <button
              className="secondary-button"
              onClick={copyReport}
              type="button"
            >
              {copied ? "Đã sao chép" : "Sao chép báo cáo đối chiếu (Markdown)"}
            </button>
            <span role="status">{copyMessage}</span>
          </div>

          {visibleItems.length === 0 ? (
            <p className="compare-empty">
              {result.items.length === 0
                ? "Không có nội dung đã duyệt để so sánh giữa hai bên."
                : "Không có mục nào khớp bộ lọc hiện tại."}
            </p>
          ) : (
            <CompareDiffView
              accessToken={accessToken}
              displayMode={displayMode}
              items={visibleItems}
              leftDoc={result.left_doc}
              leftSourceFormat={leftSourceFormat}
              rightDoc={result.right_doc}
              rightSourceFormat={rightSourceFormat}
            />
          )}
          <p className="admin-hint">{result.disclaimer}</p>
        </section>
      )}

      {result && (
        <section aria-label="Tóm tắt thay đổi cốt lõi bằng AI" className="compare-ai admin-card">
          <h2>Tóm tắt thay đổi cốt lõi bằng AI</h2>
          <p className="evidence-meta">
            Chỉ chạy khi bạn bấm nút. Số liệu trong tóm tắt AI được đối chiếu với căn cứ;
            điểm chưa đạt kiểm tra luôn được gắn nhãn cần thẩm định.
          </p>
          <button
            className="primary-button"
            disabled={aiBusy || !accessToken}
            onClick={() => void runSummarize()}
            type="button"
          >
            {aiBusy ? "Đang tóm tắt…" : "Tóm tắt bằng AI"}
          </button>
          {aiBusy && (
            <p className="chat-progress" role="status">
              Đang tóm tắt… có thể mất tới một phút.
            </p>
          )}
          {aiError && <p className="status-pill status-danger" role="alert">{aiError}</p>}
          {aiForCurrentResult && (
            <div className="compare-ai-result">
              {aiForCurrentResult.mode_used === "ai" ? (
                <p className="compare-ai-label" data-mode="ai">
                  Tóm tắt tham khảo từ AI — đã đối chiếu số liệu với căn cứ
                </p>
              ) : (
                <p className="compare-ai-label" data-mode="fallback">
                  Tóm tắt xác định (không dùng AI)
                  {aiForCurrentResult.reason
                    ? ` — ${FALLBACK_REASON_LABELS[aiForCurrentResult.reason] ?? aiForCurrentResult.reason}`
                    : ""}
                </p>
              )}
              {aiForCurrentResult.summary_status === "needs_review" && (
                <span className="tag compare-review-tag" data-status="needs_review">
                  Cần thẩm định
                </span>
              )}
              {aiForCurrentResult.executive_summary && (
                <p className="compare-ai-summary">{aiForCurrentResult.executive_summary}</p>
              )}
              {aiForCurrentResult.key_changes.length > 0 && (
                <ul className="compare-ai-points">
                  {aiForCurrentResult.key_changes.map((change, index) => (
                    <li key={index}>
                      <span>{change.point}</span>{" "}
                      <span className="tag compare-review-tag" data-status={change.status}>
                        {change.status === "verified" ? "Đã đối chiếu căn cứ" : "Cần thẩm định"}
                      </span>
                      {change.check_notes.length > 0 && (
                        <small className="compare-ai-notes">
                          {" "}({change.check_notes.join("; ")})
                        </small>
                      )}
                      {change.item_keys.length > 0 && (
                        <small className="compare-ai-items">
                          {change.item_keys.map((key, keyIndex) => (
                            <a href={`#compare-item-${key}`} key={key}>
                              {keyIndex > 0 ? ", " : " "}[{key}]
                            </a>
                          ))}
                        </small>
                      )}
                    </li>
                  ))}
                </ul>
              )}
              {aiForCurrentResult.mode_used === "deterministic_fallback"
                && aiForCurrentResult.deterministic_highlights.length > 0 && (
                <ul className="compare-highlights">
                  {aiForCurrentResult.deterministic_highlights.map((highlight, index) => (
                    <li key={index}>{highlight}</li>
                  ))}
                </ul>
              )}
              {aiForCurrentResult.external_api_used && (
                <p role="note">Đã dùng API ngoài cho lượt này.</p>
              )}
              {aiForCurrentResult.ai_limited && (
                <p role="note">Đã chạm trần chi phí; phần tóm tắt AI bị giới hạn.</p>
              )}
              <p className="admin-hint">{aiForCurrentResult.disclaimer}</p>
            </div>
          )}
        </section>
      )}
    </div>
  );
}