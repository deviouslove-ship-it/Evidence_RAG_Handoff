import { useCallback, useEffect, useRef, useState } from "react";

import {
  ApiRequestError,
  getComprehensiveDocumentClauses,
  getComprehensivePage,
  listAuthorizedCategories,
  runComprehensiveSearch,
  type ComprehensiveResult,
} from "../api/client";
import { DocumentCard } from "../components/DocumentCard";
import {
  DOC_TYPE_LABELS,
  formatVnDate,
  fromSearchDocument,
  fromSearchItem,
  type DocView,
} from "../components/documentDisplay";
import { STATUS_LABELS, VERIFICATION_LABELS } from "../components/effectivityLabels";
import { SynthesisPanel } from "../components/SynthesisPanel";
import type { AuthorizedCategory } from "../types";

/**
 * "Tìm kiếm văn bản": one page on top of the G2 comprehensive search (exact, semantic,
 * concept and relation channels fused by RRF into a fixed result set).  Results are one
 * card per document; clauses whose words only partly match, or that were found by
 * meaning without the query's phrases, are kept in a separate, collapsed list.
 */

export type SearchKind = "semantic" | "keywords" | "phrase";

const KIND_OPTIONS: Array<{ value: SearchKind; label: string; hint: string }> = [
  {
    value: "semantic", label: "Tìm theo nghĩa (toàn diện)",
    hint: "Từ khóa, cụm từ, cách diễn đạt tương đương, khái niệm mở rộng và văn bản có quan hệ.",
  },
  {
    value: "keywords", label: "Tìm đủ các từ",
    hint: "Điều khoản chứa đủ mọi từ đã nhập, không cần liền nhau.",
  },
  {
    value: "phrase", label: "Tìm chính xác cụm từ",
    hint: "Điều khoản chứa nguyên vẹn cụm từ đã nhập (có hoặc không dấu).",
  },
];
const DOC_TYPE_OPTIONS = ["law", "decree", "circular", "joint_circular", "directive", "decision",
  "other"];
const RELEVANT_TIERS = ["direct", "related", "unscored"];
const PAGE_SIZE = 10;
const QUERY_MAX_CHARS = 500;

const ERROR_MESSAGES: Record<string, string> = {
  SEARCH_BUSY: "Máy chủ đang xử lý nhiều lượt tìm kiếm. Hãy thử lại sau vài giây.",
  QUERY_TOO_LONG: `Câu tìm kiếm quá dài. Rút gọn dưới ${QUERY_MAX_CHARS} ký tự.`,
  TOO_MANY_TERMS: "Câu tìm kiếm có quá nhiều từ. Giữ tối đa 20 từ.",
  RATE_LIMITED: "Bạn tìm kiếm quá nhanh. Thử lại sau vài giây.",
  SEARCH_TIMEOUT: "Tìm kiếm mất quá nhiều thời gian. Thu hẹp bộ lọc rồi thử lại.",
  CLIENT_TIMEOUT: "Tìm kiếm mất quá nhiều thời gian. Thu hẹp bộ lọc rồi thử lại.",
  RESULT_SET_EXPIRED: "Kết quả đã hết hạn lưu tạm. Hãy tìm lại.",
  QUERY_EMPTY: "Hãy nhập nội dung cần tìm.",
};

interface SearchForm {
  q: string;
  kind: SearchKind;
  categoryIds: string[];
  docType: string;
  asOfDate: string;
  display: "default" | "all" | "history";
}

const EMPTY_FORM: SearchForm = {
  q: "", kind: "semantic", categoryIds: [], docType: "", asOfDate: "", display: "default",
};

/** Links of the former search page (?q=…&mode=phrase&category_id=…) keep working. */
function readForm(initialQuery?: string): SearchForm {
  const form = { ...EMPTY_FORM };
  if (typeof window !== "undefined") {
    try {
      const params = new URLSearchParams(window.location.search);
      form.q = params.get("q") ?? "";
      const mode = params.get("mode");
      form.kind = mode === "phrase" ? "phrase" : mode === "keywords" ? "keywords" : "semantic";
      form.categoryIds = params.getAll("category_id").filter(Boolean);
      form.docType = params.get("doc_type") ?? "";
      form.asOfDate = params.get("as_of_date") ?? "";
    } catch {
      // desktop shells without a usable location keep the defaults
    }
  }
  const trimmed = initialQuery?.trim();
  if (trimmed) form.q = trimmed;
  return form;
}

function writeLocation(form: SearchForm) {
  if (typeof window === "undefined") return;
  try {
    const params = new URLSearchParams();
    if (form.q.trim()) params.set("q", form.q.trim());
    if (form.kind !== "semantic") params.set("mode", form.kind);
    for (const id of form.categoryIds) params.append("category_id", id);
    if (form.docType) params.set("doc_type", form.docType);
    if (form.asOfDate) params.set("as_of_date", form.asOfDate);
    const query = params.toString();
    window.history.replaceState(window.history.state, "",
      `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`);
  } catch {
    // ignore: the URL is only a convenience
  }
}

function errorMessage(caught: unknown): string {
  if (caught instanceof ApiRequestError) return ERROR_MESSAGES[caught.code] ?? caught.message;
  return "Mất kết nối tới máy chủ. Nội dung bạn nhập vẫn được giữ.";
}

interface SearchPageProps {
  accessToken?: string;
  initialQuery?: string;
}

export function SearchPage({ accessToken, initialQuery }: SearchPageProps) {
  const [form, setForm] = useState<SearchForm>(() => readForm(initialQuery));
  const [categories, setCategories] = useState<AuthorizedCategory[]>([]);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [statusFilter, setStatusFilter] = useState("");
  const [verificationFilter, setVerificationFilter] = useState("");
  const [excluded, setExcluded] = useState<string[]>([]);
  const [result, setResult] = useState<ComprehensiveResult>();
  const [documents, setDocuments] = useState<DocView[]>([]);
  const [weak, setWeak] = useState<ComprehensiveResult>();
  const [weakOpen, setWeakOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loadingDocument, setLoadingDocument] = useState<string>();
  const [error, setError] = useState<string>();
  const autoRun = useRef(false);

  useEffect(() => {
    if (!accessToken) {
      setCategories([]);
      return undefined;
    }
    const controller = new AbortController();
    listAuthorizedCategories(accessToken, { signal: controller.signal })
      .then((items) => setCategories(items))
      .catch(() => setCategories([]));
    return () => controller.abort();
  }, [accessToken]);

  const update = (patch: Partial<SearchForm>) => setForm((current) => ({ ...current, ...patch }));

  const pageFilters = useCallback((tiers: string[], status = statusFilter,
                                   verification = verificationFilter) => ({
    tier: tiers, status: status || undefined, verification: verification || undefined,
    view: "documents" as const, pageSize: PAGE_SIZE, clausesPerDocument: 3,
  }), [statusFilter, verificationFilter]);

  const search = useCallback(async (next: SearchForm = form, nextExcluded = excluded) => {
    const q = next.q.trim();
    if (!accessToken || !q) return;
    setBusy(true);
    setError(undefined);
    setWeak(undefined);
    setWeakOpen(false);
    writeLocation(next);
    try {
      const response = await runComprehensiveSearch(accessToken, {
        q,
        display: next.display,
        mode: next.kind === "semantic" ? "auto" : next.kind,
        channels: next.kind === "semantic" ? undefined : ["exact"],
        excluded_concepts: nextExcluded,
        category_ids: next.categoryIds.length ? next.categoryIds : undefined,
        doc_types: next.docType ? [next.docType] : undefined,
        ...(next.asOfDate ? { as_of_date: next.asOfDate } : {}),
        view: "documents", page_size: PAGE_SIZE, clauses_per_document: 3,
        tier: RELEVANT_TIERS,
      });
      setStatusFilter("");
      setVerificationFilter("");
      setResult(response);
      setDocuments((response.documents ?? []).map(fromSearchDocument));
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }, [accessToken, excluded, form]);

  const initialForm = useRef(form);
  useEffect(() => {
    // Opened from Hỏi đáp ("Xem tất cả kết quả") or from an old link: run that query once.
    if (autoRun.current || !accessToken || !initialForm.current.q.trim()) return;
    autoRun.current = true;
    void search(initialForm.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken]);

  const lastInitial = useRef(initialQuery?.trim());
  useEffect(() => {
    const trimmed = initialQuery?.trim();
    if (!trimmed || trimmed === lastInitial.current) return;
    lastInitial.current = trimmed;
    const next = { ...form, q: trimmed };
    setForm(next);
    autoRun.current = true;
    void search(next);
    // Only a new question from Hỏi đáp re-runs the search.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialQuery]);

  async function goTo(page: number, status = statusFilter, verification = verificationFilter) {
    if (!accessToken || !result) return;
    setBusy(true);
    setError(undefined);
    try {
      const response = await getComprehensivePage(accessToken, result.result_set_id, page,
                                                   pageFilters(RELEVANT_TIERS, status, verification));
      setResult(response);
      setDocuments((response.documents ?? []).map(fromSearchDocument));
      if (weakOpen) await loadWeak(1, status, verification);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function loadWeak(page = 1, status = statusFilter, verification = verificationFilter) {
    if (!accessToken || !result) return;
    try {
      setWeak(await getComprehensivePage(accessToken, result.result_set_id, page,
                                         pageFilters(["weak"], status, verification)));
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  async function loadMore(documentId: string, weakList = false) {
    if (!accessToken || !result) return;
    setLoadingDocument(documentId);
    try {
      const response = await getComprehensiveDocumentClauses(
        accessToken, result.result_set_id, documentId, {
          tier: weakList ? ["weak"] : RELEVANT_TIERS,
          status: statusFilter || undefined, verification: verificationFilter || undefined,
        });
      const replace = (items: DocView[]) => items.map((document) => document.key === documentId
        ? { ...document, clauses: response.clauses.map(fromSearchItem), moreClauses: 0 }
        : document);
      if (weakList) {
        setWeak((current) => current && {
          ...current,
          documents: current.documents?.map((document) => document.document_id === documentId
            ? { ...document, clauses: response.clauses, matched_clause_count: response.clauses.length }
            : document),
        });
      } else {
        setDocuments((current) => replace(current));
      }
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setLoadingDocument(undefined);
    }
  }

  const toggleConcept = (expansion: string) => {
    const next = excluded.includes(expansion)
      ? excluded.filter((item) => item !== expansion)
      : [...excluded, expansion];
    setExcluded(next);
    void search(form, next);
  };

  const tiers = result?.tiers ?? {};
  const weakCount = tiers.weak ?? 0;
  const relevantCount = (tiers.direct ?? 0) + (tiers.related ?? 0) + (tiers.unscored ?? 0);
  const totalPages = result?.total_documents
    ? Math.max(1, Math.ceil(result.total_documents / PAGE_SIZE)) : 1;
  const kindHint = KIND_OPTIONS.find((option) => option.value === form.kind)?.hint;
  const terminated = result?.sections.find((section) => section.key === "terminated");

  return (
    <div className="search-page">
      <header className="search-header">
        <h1>Tìm kiếm văn bản</h1>
        <p>
          Tìm trong kho văn bản đã duyệt theo từ khóa, cụm từ, số hiệu hoặc cách diễn đạt tương
          đương. Mỗi văn bản là một mục riêng, kèm điều khoản khớp và nút mở tệp gốc.
        </p>
      </header>

      <form
        className="search-form"
        onSubmit={(event) => {
          event.preventDefault();
          void search();
        }}
        role="search"
      >
        <div className="search-query-row">
          <label className="field-label search-query-field">
            Nội dung cần tìm
            <input
              autoComplete="off"
              className="search-input"
              maxLength={QUERY_MAX_CHARS}
              onChange={(event) => update({ q: event.target.value })}
              placeholder="Ví dụ: bổ nhiệm, miễn nhiệm; báo cáo định kỳ; 55/2021/TT-BCA"
              type="search"
              value={form.q}
            />
          </label>
          <button className="primary-button" disabled={busy || !accessToken || !form.q.trim()}
                  type="submit">
            {busy ? "Đang tìm…" : "Tìm kiếm"}
          </button>
        </div>
        <fieldset className="search-kind">
          <legend>Cách tìm</legend>
          {KIND_OPTIONS.map((option) => (
            <label className="search-kind-option" key={option.value}>
              <input
                checked={form.kind === option.value}
                name="search-kind"
                onChange={() => update({ kind: option.value })}
                type="radio"
              />
              <span>{option.label}</span>
            </label>
          ))}
          {kindHint && <small className="evidence-meta">{kindHint}</small>}
        </fieldset>
        <button
          aria-controls="search-filters"
          aria-expanded={filtersOpen}
          className="secondary-button search-filter-toggle"
          onClick={() => setFiltersOpen((value) => !value)}
          type="button"
        >
          {filtersOpen ? "Ẩn bộ lọc" : "Bộ lọc"}
        </button>
        {filtersOpen && (
          <div aria-label="Bộ lọc tìm kiếm" className="search-filters" id="search-filters"
               role="group">
            {categories.length > 0 && (
              <fieldset className="search-filter-field search-filter-categories">
                <legend>Danh mục</legend>
                <div className="category-pills">
                  {categories.map((category) => (
                    <label className="fact-chip" key={category.id}>
                      <input
                        checked={form.categoryIds.includes(category.id)}
                        onChange={() => update({
                          categoryIds: form.categoryIds.includes(category.id)
                            ? form.categoryIds.filter((id) => id !== category.id)
                            : [...form.categoryIds, category.id],
                        })}
                        type="checkbox"
                      />
                      <span>{category.name}</span>
                    </label>
                  ))}
                </div>
              </fieldset>
            )}
            <label className="field-label">
              Loại văn bản
              <select onChange={(event) => update({ docType: event.target.value })}
                      value={form.docType}>
                <option value="">Tất cả loại văn bản</option>
                {DOC_TYPE_OPTIONS.map((value) => (
                  <option key={value} value={value}>{DOC_TYPE_LABELS[value]}</option>
                ))}
              </select>
            </label>
            <label className="field-label">
              Hiệu lực tại ngày
              <input onChange={(event) => update({ asOfDate: event.target.value })} type="date"
                     value={form.asOfDate} />
            </label>
            <label className="field-label">
              Phạm vi thời gian
              <select
                onChange={(event) => update({ display: event.target.value as SearchForm["display"] })}
                value={form.display}
              >
                <option value="default">Ưu tiên văn bản còn hiệu lực, chưa xác minh</option>
                <option value="all">Tất cả văn bản, kể cả hết hiệu lực</option>
                <option value="history">Đối chiếu lịch sử</option>
              </select>
            </label>
            {result && (
              <>
                <label className="field-label">
                  Trạng thái hiệu lực
                  <select onChange={(event) => {
                    setStatusFilter(event.target.value);
                    void goTo(1, event.target.value, verificationFilter);
                  }} value={statusFilter}>
                    <option value="">Tất cả</option>
                    {Object.entries(STATUS_LABELS).map(([key, label]) => (
                      <option key={key} value={key}>{label}</option>
                    ))}
                  </select>
                </label>
                <label className="field-label">
                  Trạng thái xác minh
                  <select onChange={(event) => {
                    setVerificationFilter(event.target.value);
                    void goTo(1, statusFilter, event.target.value);
                  }} value={verificationFilter}>
                    <option value="">Tất cả</option>
                    {Object.entries(VERIFICATION_LABELS).map(([key, label]) => (
                      <option key={key} value={key}>{label}</option>
                    ))}
                  </select>
                </label>
              </>
            )}
          </div>
        )}
      </form>

      {!accessToken && (
        <p className="status-pill status-warning" role="status">
          Đăng nhập để tìm kiếm trong văn bản đã duyệt.
        </p>
      )}
      {error && <p className="status-pill status-danger" role="alert">{error}</p>}
      {busy && !result && <p className="chat-progress" role="status">Đang tìm…</p>}

      {result && (
        <section aria-label="Kết quả tìm kiếm" className="search-result-area" aria-live="polite">
          <div className="search-summary-box">
            <p className="search-summary">
              {result.total_documents ?? 0} văn bản có điều khoản liên quan
              {" "}({tiers.direct ?? 0} điều khoản khớp trực tiếp, {tiers.related ?? 0} có liên
              quan{tiers.unscored ? `, ${tiers.unscored} chưa phân loại` : ""})
              {weakCount > 0 ? `; ${weakCount} điều khoản chỉ khớp một phần` : ""}.
            </p>
            <p className="evidence-meta">
              Đã tìm trong {result.scope.documents_in_scope} văn bản được phép
              {result.scope.categories.length > 0 ? ` (${result.scope.categories.join(", ")})` : ""}
              ; hiệu lực tính tại ngày {formatVnDate(result.scope.as_of_date)}
              {result.scope.data_date ? `; kho dữ liệu đến ngày ${formatVnDate(result.scope.data_date)}` : ""}.
            </p>
            {result.understood && result.understood.phrases.length > 0 && (
              <p className="evidence-meta">
                Cụm từ dùng để đánh giá mức liên quan:{" "}
                {result.understood.phrases.map((phrase) => `«${phrase}»`).join(" · ")}
              </p>
            )}
            {terminated && terminated.count > 0 && (
              <p className="evidence-meta">
                {terminated.count} điều khoản thuộc văn bản hết hiệu lực, bị thay thế hoặc tạm
                ngưng được xếp sau cùng.
              </p>
            )}
            {result.clause_level_warning && (
              <p className="evidence-meta search-clause-warning">{result.clause_level_warning}</p>
            )}
          </div>

          {result.concepts.length > 0 && (
            <details className="concept-chips">
              <summary>Khái niệm mở rộng đã dùng ({result.concepts.length})</summary>
              <p className="evidence-meta">
                Bỏ chọn để loại khái niệm khỏi lượt tìm. Kết quả chỉ khớp khái niệm do AI gợi ý,
                chưa được duyệt, không được tính là liên quan trực tiếp.
              </p>
              {result.concepts.map((concept) => (
                <label className="fact-chip" key={concept.expansion}>
                  <input
                    checked={!excluded.includes(concept.expansion)}
                    onChange={() => toggleConcept(concept.expansion)}
                    type="checkbox"
                  />
                  <span>
                    {concept.expansion}
                    {concept.source === "ai" ? " (AI gợi ý, chưa duyệt)" : ""}
                  </span>
                </label>
              ))}
            </details>
          )}

          {documents.length === 0 && relevantCount === 0 && (
            <p className="search-empty">
              {result.empty_message ??
                "Chưa thấy điều khoản khớp với nội dung đã nhập. Thử bớt từ, đổi cách tìm hoặc mở kết quả khớp một phần bên dưới."}
            </p>
          )}
          <div className="doc-list">
            {documents.map((document, index) => (
              <DocumentCard
                accessToken={accessToken}
                document={document}
                index={(result.page - 1) * PAGE_SIZE + index + 1}
                key={document.key}
                loadingMore={loadingDocument === document.key}
                onLoadMore={() => void loadMore(document.key)}
              />
            ))}
          </div>
          {(result.total_documents ?? 0) > PAGE_SIZE && (
            <nav aria-label="Phân trang kết quả" className="search-pagination">
              <button className="secondary-button" disabled={busy || result.page <= 1}
                      onClick={() => void goTo(result.page - 1)} type="button">
                ‹ Trang trước
              </button>
              <span className="search-page-indicator">Trang {result.page} / {totalPages}</span>
              <button className="secondary-button" disabled={busy || !result.has_more}
                      onClick={() => void goTo(result.page + 1)} type="button">
                Trang sau ›
              </button>
            </nav>
          )}

          {weakCount > 0 && (
            <section aria-label="Kết quả khớp một phần" className="search-weak">
              <button
                aria-expanded={weakOpen}
                className="secondary-button"
                onClick={() => {
                  const next = !weakOpen;
                  setWeakOpen(next);
                  if (next && !weak) void loadWeak(1);
                }}
                type="button"
              >
                {weakOpen ? "Thu gọn" : "Xem"} {weakCount} điều khoản chỉ khớp một phần hoặc chỉ theo
                nghĩa
              </button>
              {weakOpen && (
                <>
                  <p className="evidence-meta">
                    Các điều khoản này chỉ có một vài từ trùng (thường là từ chung) hoặc được tìm theo
                    nghĩa mà không chứa cụm từ của câu tìm kiếm; chỉ dùng để rà soát thêm.
                  </p>
                  <div className="doc-list">
                    {(weak?.documents ?? []).map((document) => {
                      const view = fromSearchDocument(document);
                      return (
                        <DocumentCard
                          accessToken={accessToken}
                          document={{ ...view, role: "weak" }}
                          key={view.key}
                          loadingMore={loadingDocument === view.key}
                          onLoadMore={() => void loadMore(view.key, true)}
                        />
                      );
                    })}
                  </div>
                  {weak && (weak.total_documents ?? 0) > PAGE_SIZE && (
                    <nav aria-label="Phân trang kết quả khớp một phần"
                         className="search-pagination">
                      <button className="secondary-button" disabled={weak.page <= 1}
                              onClick={() => void loadWeak(weak.page - 1)} type="button">
                        ‹ Trang trước
                      </button>
                      <span className="search-page-indicator">Trang {weak.page}</span>
                      <button className="secondary-button" disabled={!weak.has_more}
                              onClick={() => void loadWeak(weak.page + 1)} type="button">
                        Trang sau ›
                      </button>
                    </nav>
                  )}
                </>
              )}
            </section>
          )}

          <details className="search-technical">
            <summary>Thông tin kỹ thuật của lượt tìm</summary>
            <ul className="chat-technical-list">
              {Object.entries(result.channels).map(([key, info]) => (
                <li key={key}>
                  {CHANNEL_LABELS[key] ?? key}: {info.enabled ? `${info.count} kết quả` : "tắt"}
                  {key === "semantic" && info.enabled && info.cap
                    ? ` (tối đa ${info.cap}, giữ từ ${Math.round((info.relative_threshold ?? 0) * 100)}% độ tương đồng của kết quả gần nhất)`
                    : ""}
                  {info.note ? ` — ${info.note}` : ""}
                </li>
              ))}
              <li>
                Xếp hạng: hợp kênh RRF{result.ranking.reranked
                  ? `, xếp lại ${result.ranking.reranked_count}/${result.ranking.total} kết quả đầu`
                  : ", không xếp lại bằng model"}; trong mỗi nhóm hiệu lực, điều khoản khớp trực
                tiếp đứng trước.
              </li>
              <li>{result.scope.statement}</li>
            </ul>
          </details>

          {accessToken && (
            <SynthesisPanel accessToken={accessToken} onlyRelevant
                            resultSetId={result.result_set_id} />
          )}
        </section>
      )}
    </div>
  );
}

const CHANNEL_LABELS: Record<string, string> = {
  exact: "Kênh chính xác (từ khóa, cụm từ, số hiệu)",
  semantic: "Kênh theo nghĩa",
  concept: "Kênh khái niệm mở rộng",
  relation: "Kênh quan hệ văn bản",
};
