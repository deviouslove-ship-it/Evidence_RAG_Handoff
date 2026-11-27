import { useCallback, useEffect, useRef, useState } from "react";

import {
  cancelConflictScan,
  createConflictScan,
  getConflictScan,
  listAuthorizedCategories,
  listConflictScans,
  runComprehensiveSearch,
  type ComprehensiveDocument,
} from "../api/client";
import { ConflictFindingCard } from "../components/ConflictFindingCard";
import { DOC_TYPE_LABELS, formatVnDate } from "../components/documentDisplay";
import type {
  AuthorizedCategory,
  ConflictFindingType,
  ConflictScanDetailResponse,
  ConflictScanRunView,
  CreateConflictScanRequest,
} from "../types";
import {
  CONFLICT_FINDING_TYPE_LABELS,
  CONFLICT_RUN_STATUS_LABELS,
  CONTENT_TAXONOMY_LABELS,
} from "../types";

export interface ConflictReviewPageProps {
  accessToken?: string;
  onOpenCompare?: (leftDocumentId: string, rightDocumentId: string) => void;
}

interface PickedScopeDocument {
  id: string;
  title: string;
  document_number: string | null;
  doc_type: string;
}

type ScopeMode = "documents" | "category";
type FindingTypeFilter = "all" | ConflictFindingType;

const MAX_PICKED_DOCUMENTS = 20;
const MIN_PICKED_DOCUMENTS = 2;
const POLL_INTERVAL_MS = 2000;

const FINDING_FILTER_OPTIONS: Array<{ value: FindingTypeFilter; label: string }> = [
  { value: "all", label: "Tất cả" },
  { value: "contradiction", label: CONFLICT_FINDING_TYPE_LABELS.contradiction },
  { value: "overlap", label: CONFLICT_FINDING_TYPE_LABELS.overlap },
  { value: "exception_refinement", label: CONFLICT_FINDING_TYPE_LABELS.exception_refinement },
  { value: "superseded_already", label: CONFLICT_FINDING_TYPE_LABELS.superseded_already },
];

function generateRequestId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  const suffix = Math.random().toString(16).slice(2, 10);
  return `scan-${Date.now()}-${suffix}`;
}

function errorMessage(caught: unknown, fallback: string): string {
  return caught instanceof Error ? caught.message : fallback;
}

function isAbortError(caught: unknown): boolean {
  return caught instanceof DOMException
    ? caught.name === "AbortError"
    : caught instanceof Error && caught.name === "AbortError";
}

function isActiveScanStatus(status: ConflictScanRunView["status"]): boolean {
  return status === "queued" || status === "running";
}

export function ConflictReviewPage({
  accessToken,
  onOpenCompare,
}: ConflictReviewPageProps) {
  const [scopeMode, setScopeMode] = useState<ScopeMode>("documents");
  const [categories, setCategories] = useState<AuthorizedCategory[]>([]);
  const [selectedCategoryId, setSelectedCategoryId] = useState("");
  const [pickedDocs, setPickedDocs] = useState<PickedScopeDocument[]>([]);

  const [searchQuery, setSearchQuery] = useState("");
  const [searchDocType, setSearchDocType] = useState("");
  const [searchResults, setSearchResults] = useState<ComprehensiveDocument[]>();
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string>();

  const [docTypes, setDocTypes] = useState<string[]>([]);
  const [taxonomyCodes, setTaxonomyCodes] = useState<string[]>([]);
  const [asOfDate, setAsOfDate] = useState("");
  const [includeExpired, setIncludeExpired] = useState(false);
  const [useAi, setUseAi] = useState(false);

  const [recentScans, setRecentScans] = useState<ConflictScanRunView[]>([]);
  const [activeScan, setActiveScan] = useState<ConflictScanDetailResponse>();
  const [findingFilter, setFindingFilter] = useState<FindingTypeFilter>("all");
  const [pollTick, setPollTick] = useState(0);

  const [submitting, setSubmitting] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState<string>();

  const actionControllerRef = useRef<AbortController | null>(null);
  const pollControllerRef = useRef<AbortController | null>(null);
  const recentControllerRef = useRef<AbortController | null>(null);
  const pollTimerRef = useRef<number | null>(null);
  const lifecycleEpochRef = useRef(0);
  const mountedRef = useRef(true);

  const abortAllInFlight = useCallback(() => {
    lifecycleEpochRef.current += 1;
    if (pollTimerRef.current !== null) {
      window.clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    actionControllerRef.current?.abort();
    actionControllerRef.current = null;
    pollControllerRef.current?.abort();
    pollControllerRef.current = null;
    recentControllerRef.current?.abort();
    recentControllerRef.current = null;
    if (mountedRef.current) {
      setSubmitting(false);
      setCancelling(false);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      abortAllInFlight();
    };
  }, [abortAllInFlight]);

  const loadInitialData = useCallback(
    async (token: string, signal: AbortSignal) => {
      try {
        const [cats, scans] = await Promise.all([
          listAuthorizedCategories(token, { signal }),
          listConflictScans(token, { limit: 15, offset: 0, signal }),
        ]);
        if (signal.aborted) return;
        setCategories(cats);
        setSelectedCategoryId((prev) => prev || cats[0]?.id || "");
        setRecentScans(scans.items);
      } catch (caught) {
        if (signal.aborted || isAbortError(caught)) return;
        setError(errorMessage(caught, "Không thể tải danh mục và lịch sử rà soát."));
      }
    },
    [],
  );

  useEffect(() => {
    if (!accessToken) {
      abortAllInFlight();
      setCategories([]);
      setSelectedCategoryId("");
      setRecentScans([]);
      setActiveScan(undefined);
      setError(undefined);
      return;
    }
    const controller = new AbortController();
    void loadInitialData(accessToken, controller.signal);
    return () => {
      controller.abort();
    };
  }, [accessToken, abortAllInFlight, loadInitialData]);

  const refreshRecentScans = useCallback(async (token: string) => {
    recentControllerRef.current?.abort();
    const controller = new AbortController();
    recentControllerRef.current = controller;
    const epoch = lifecycleEpochRef.current;
    try {
      const list = await listConflictScans(token, {
        limit: 15,
        offset: 0,
        signal: controller.signal,
      });
      if (controller.signal.aborted || lifecycleEpochRef.current !== epoch) return;
      setRecentScans(list.items);
    } catch {
      // Keep current list on transient refresh failures or aborts.
    } finally {
      if (recentControllerRef.current === controller) {
        recentControllerRef.current = null;
      }
    }
  }, []);

  useEffect(() => {
    if (!accessToken || !activeScan || !isActiveScanStatus(activeScan.status)) {
      return undefined;
    }
    const runId = activeScan.run_id;
    const epoch = lifecycleEpochRef.current;
    const timer = window.setTimeout(() => {
      if (lifecycleEpochRef.current !== epoch) return;
      pollControllerRef.current?.abort();
      const controller = new AbortController();
      pollControllerRef.current = controller;
      void getConflictScan(accessToken, runId, { signal: controller.signal })
        .then((detail) => {
          if (controller.signal.aborted || lifecycleEpochRef.current !== epoch) return;
          setActiveScan(detail);
          if (isActiveScanStatus(detail.status)) {
            setPollTick((prev) => prev + 1);
          } else {
            void refreshRecentScans(accessToken);
          }
        })
        .catch((caught) => {
          if (controller.signal.aborted || isAbortError(caught) || lifecycleEpochRef.current !== epoch) {
            return;
          }
          setError(errorMessage(caught, "Không thể cập nhật tiến độ lượt quét."));
        });
    }, POLL_INTERVAL_MS);
    pollTimerRef.current = timer;

    return () => {
      window.clearTimeout(timer);
      if (pollTimerRef.current === timer) {
        pollTimerRef.current = null;
      }
      pollControllerRef.current?.abort();
      pollControllerRef.current = null;
    };
  }, [accessToken, activeScan, pollTick, refreshRecentScans]);

  if (!accessToken) {
    return (
      <section className="conflict-page" aria-label="Rà soát mâu thuẫn">
        <header className="conflict-header">
          <h1>Rà soát mâu thuẫn văn bản</h1>
          <p>Phát hiện quy định trái ngược, chồng chéo hoặc ngoại lệ giữa các văn bản được phép truy cập.</p>
        </header>
        <p className="status-pill status-warning" role="status">
          Đăng nhập để rà soát mâu thuẫn văn bản trong phạm vi được phép.
        </p>
      </section>
    );
  }

  async function handleSearchDocuments(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = searchQuery.trim();
    if (!accessToken || !trimmed) return;
    setSearching(true);
    setSearchError(undefined);
    try {
      const response = await runComprehensiveSearch(accessToken, {
        q: trimmed,
        mode: "keywords",
        channels: ["exact"],
        display: "all",
        view: "documents",
        page_size: 8,
        clauses_per_document: 1,
        ...(searchDocType ? { doc_types: [searchDocType] } : {}),
      });
      setSearchResults(response.documents ?? []);
    } catch (caught) {
      setSearchError(errorMessage(caught, "Không tìm kiếm được văn bản."));
    } finally {
      setSearching(false);
    }
  }

  function addPickedDocument(doc: ComprehensiveDocument) {
    setError(undefined);
    setPickedDocs((prev) => {
      if (prev.some((item) => item.id === doc.document_id)) return prev;
      if (prev.length >= MAX_PICKED_DOCUMENTS) return prev;
      return [
        ...prev,
        {
          id: doc.document_id,
          title: doc.display_title ?? doc.title,
          document_number: doc.document_number ?? null,
          doc_type: doc.doc_type,
        },
      ];
    });
  }

  function removePickedDocument(documentId: string) {
    setPickedDocs((prev) => prev.filter((item) => item.id !== documentId));
  }

  function toggleStringItem(list: string[], value: string): string[] {
    return list.includes(value) ? list.filter((item) => item !== value) : [...list, value];
  }

  const canStartScan =
    !submitting &&
    (scopeMode === "documents"
      ? pickedDocs.length >= MIN_PICKED_DOCUMENTS && pickedDocs.length <= MAX_PICKED_DOCUMENTS
      : Boolean(selectedCategoryId));

  async function handleStartScan(event: React.FormEvent) {
    event.preventDefault();
    if (!accessToken || !canStartScan) return;
    abortAllInFlight();
    const epoch = lifecycleEpochRef.current;
    const controller = new AbortController();
    actionControllerRef.current = controller;
    setSubmitting(true);
    setError(undefined);

    const payload: CreateConflictScanRequest = {
      request_id: generateRequestId(),
      ...(scopeMode === "documents"
        ? { document_ids: pickedDocs.map((item) => item.id) }
        : { category_id: selectedCategoryId }),
      ...(docTypes.length > 0 ? { doc_types: docTypes } : {}),
      ...(taxonomyCodes.length > 0 ? { taxonomy_codes: taxonomyCodes } : {}),
      ...(asOfDate ? { as_of_date: asOfDate } : {}),
      include_expired: includeExpired,
      use_ai: useAi,
    };

    try {
      const created = await createConflictScan(accessToken, payload, {
        signal: controller.signal,
      });
      if (controller.signal.aborted || lifecycleEpochRef.current !== epoch) return;
      const detail = await getConflictScan(accessToken, created.run_id, {
        signal: controller.signal,
      });
      if (controller.signal.aborted || lifecycleEpochRef.current !== epoch) return;
      setActiveScan(detail);
      setFindingFilter("all");
      if (isActiveScanStatus(detail.status)) {
        setPollTick((prev) => prev + 1);
      }
      void refreshRecentScans(accessToken);
    } catch (caught) {
      if (controller.signal.aborted || isAbortError(caught) || lifecycleEpochRef.current !== epoch) {
        return;
      }
      setError(errorMessage(caught, "Không thể khởi tạo lượt quét mâu thuẫn."));
    } finally {
      if (actionControllerRef.current === controller) {
        actionControllerRef.current = null;
      }
      if (lifecycleEpochRef.current === epoch) {
        setSubmitting(false);
      }
    }
  }

  async function handleSelectScan(runId: string) {
    if (!accessToken) return;
    abortAllInFlight();
    const epoch = lifecycleEpochRef.current;
    const controller = new AbortController();
    actionControllerRef.current = controller;
    setError(undefined);
    try {
      const detail = await getConflictScan(accessToken, runId, { signal: controller.signal });
      if (controller.signal.aborted || lifecycleEpochRef.current !== epoch) return;
      setActiveScan(detail);
      setFindingFilter("all");
      if (isActiveScanStatus(detail.status)) {
        setPollTick((prev) => prev + 1);
      }
    } catch (caught) {
      if (controller.signal.aborted || isAbortError(caught) || lifecycleEpochRef.current !== epoch) {
        return;
      }
      setError(errorMessage(caught, "Không thể tải chi tiết lượt quét."));
    } finally {
      if (actionControllerRef.current === controller) {
        actionControllerRef.current = null;
      }
    }
  }

  async function handleCancelScan() {
    if (!accessToken || !activeScan || cancelling) return;
    const runId = activeScan.run_id;
    abortAllInFlight();
    const epoch = lifecycleEpochRef.current;
    const controller = new AbortController();
    actionControllerRef.current = controller;
    setCancelling(true);
    setError(undefined);
    try {
      const updatedRun = await cancelConflictScan(accessToken, runId, {
        signal: controller.signal,
      });
      if (controller.signal.aborted || lifecycleEpochRef.current !== epoch) return;
      setActiveScan((prev) =>
        prev && prev.run_id === updatedRun.run_id
          ? { ...prev, ...updatedRun }
          : {
              ...updatedRun,
              findings: [],
              total_findings: 0,
              hidden_due_to_acl: 0,
              disclaimer: "Gợi ý tự động — cần chuyên viên thẩm định trước khi áp dụng.",
            },
      );
      void refreshRecentScans(accessToken);
    } catch (caught) {
      if (controller.signal.aborted || isAbortError(caught) || lifecycleEpochRef.current !== epoch) {
        return;
      }
      setError(errorMessage(caught, "Không thể hủy lượt quét."));
    } finally {
      if (actionControllerRef.current === controller) {
        actionControllerRef.current = null;
      }
      if (lifecycleEpochRef.current === epoch) {
        setCancelling(false);
      }
    }
  }

  const visibleFindings = activeScan
    ? activeScan.findings.filter(
        (item) => findingFilter === "all" || item.finding_type === findingFilter,
      )
    : [];

  return (
    <div className="conflict-page">
      <header className="conflict-header">
        <h1>Rà soát mâu thuẫn văn bản</h1>
        <p>
          Phát hiện quy định trái ngược, chồng chéo hoặc ngoại lệ giữa các văn bản trong phạm vi được phép.
          Kết quả chỉ mang tính tham khảo tự động và cần chuyên viên thẩm định.
        </p>
      </header>

      <section className="admin-card conflict-form-card" aria-label="Khởi tạo lượt quét mâu thuẫn">
        <h2>Thiết lập phạm vi rà soát</h2>

        <fieldset className="conflict-scope-switch">
          <legend>Chế độ phạm vi</legend>
          <label className="compare-mode-option">
            <input
              checked={scopeMode === "documents"}
              name="conflict-scope-mode"
              onChange={() => setScopeMode("documents")}
              type="radio"
            />
            <span>Chọn trực tiếp 2–20 văn bản</span>
          </label>
          <label className="compare-mode-option">
            <input
              checked={scopeMode === "category"}
              name="conflict-scope-mode"
              onChange={() => setScopeMode("category")}
              type="radio"
            />
            <span>Quét theo 1 danh mục</span>
          </label>
        </fieldset>

        {scopeMode === "documents" ? (
          <div className="conflict-doc-picker">
            <form className="compare-picker-form" onSubmit={handleSearchDocuments} role="search">
              <label className="field-label">
                Tìm văn bản để thêm vào phạm vi
                <input
                  autoComplete="off"
                  onChange={(event) => setSearchQuery(event.target.value)}
                  placeholder="Số hiệu hoặc từ khóa, ví dụ: 10/2024/NĐ-CP"
                  type="search"
                  value={searchQuery}
                />
              </label>
              <label className="field-label">
                Loại văn bản tìm kiếm
                <select
                  onChange={(event) => setSearchDocType(event.target.value)}
                  value={searchDocType}
                >
                  <option value="">Tất cả loại văn bản</option>
                  {Object.entries(DOC_TYPE_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <button
                className="secondary-button"
                disabled={searching || !searchQuery.trim()}
                type="submit"
              >
                {searching ? "Đang tìm…" : "Tìm văn bản"}
              </button>
            </form>

            {searchError && (
              <p className="status-pill status-danger" role="alert">
                {searchError}
              </p>
            )}
            {searchResults && searchResults.length === 0 && (
              <p className="evidence-meta">Không tìm thấy văn bản phù hợp trong phạm vi được phép.</p>
            )}
            {searchResults && searchResults.length > 0 && (
              <ul className="compare-picker-results">
                {searchResults.map((doc) => {
                  const alreadyAdded = pickedDocs.some((item) => item.id === doc.document_id);
                  const limitReached = pickedDocs.length >= MAX_PICKED_DOCUMENTS;
                  return (
                    <li key={doc.document_id}>
                      <button
                        className="compare-pick-option"
                        data-selected={alreadyAdded ? "true" : undefined}
                        disabled={alreadyAdded || limitReached}
                        onClick={() => addPickedDocument(doc)}
                        type="button"
                      >
                        <strong>
                          {doc.document_number ?? doc.title}
                          {alreadyAdded ? " (Đã chọn)" : ""}
                        </strong>
                        <span>{doc.display_title ?? doc.title}</span>
                        <small>{DOC_TYPE_LABELS[doc.doc_type] ?? doc.doc_type}</small>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}

            <div className="conflict-picked-list" aria-label="Văn bản đã chọn">
              <p className="evidence-meta">
                Đã chọn {pickedDocs.length}/{MAX_PICKED_DOCUMENTS} văn bản (cần tối thiểu {MIN_PICKED_DOCUMENTS}).
              </p>
              {pickedDocs.length > 0 && (
                <div className="conflict-chip-group">
                  {pickedDocs.map((doc) => (
                    <span className="conflict-chip" key={doc.id}>
                      <span>{doc.document_number ?? doc.title}</span>
                      <button
                        aria-label={`Bỏ ${doc.document_number ?? doc.title}`}
                        className="conflict-chip-remove"
                        onClick={() => removePickedDocument(doc.id)}
                        type="button"
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="conflict-category-picker">
            <label className="field-label">
              Danh mục rà soát
              <select
                onChange={(event) => setSelectedCategoryId(event.target.value)}
                value={selectedCategoryId}
              >
                {categories.length === 0 && <option value="">Chưa có danh mục được cấp quyền</option>}
                {categories.map((cat) => (
                  <option key={cat.id} value={cat.id}>
                    {cat.name} ({cat.code})
                  </option>
                ))}
              </select>
            </label>
          </div>
        )}

        <form className="form-stack" onSubmit={handleStartScan}>
          <div className="conflict-filter-grid">
            <label className="field-label">
              Hiệu lực tại ngày
              <input
                onChange={(event) => setAsOfDate(event.target.value)}
                type="date"
                value={asOfDate}
              />
            </label>
            <label className="checkbox-row">
              <input
                checked={includeExpired}
                onChange={(event) => setIncludeExpired(event.target.checked)}
                type="checkbox"
              />
              <span>Bao gồm văn bản đã hết hiệu lực / bị thay thế</span>
            </label>
          </div>

          <fieldset className="field-set">
            <legend>Lọc loại văn bản (tùy chọn)</legend>
            <div className="category-pills">
              {Object.entries(DOC_TYPE_LABELS).map(([value, label]) => (
                <label className="fact-chip" key={value}>
                  <input
                    checked={docTypes.includes(value)}
                    onChange={() => setDocTypes((prev) => toggleStringItem(prev, value))}
                    type="checkbox"
                  />
                  <span>{label}</span>
                </label>
              ))}
            </div>
          </fieldset>

          <fieldset className="field-set">
            <legend>Lọc nhóm nội dung (tùy chọn)</legend>
            <div className="category-pills">
              {Object.entries(CONTENT_TAXONOMY_LABELS).map(([code, label]) => (
                <label className="fact-chip" key={code}>
                  <input
                    checked={taxonomyCodes.includes(code)}
                    onChange={() => setTaxonomyCodes((prev) => toggleStringItem(prev, code))}
                    type="checkbox"
                  />
                  <span>{label}</span>
                </label>
              ))}
            </div>
          </fieldset>

          <div className="conflict-ai-option">
            <label className="checkbox-row">
              <input
                checked={useAi}
                onChange={(event) => setUseAi(event.target.checked)}
                type="checkbox"
              />
              <span>Bổ sung phân tích AI</span>
            </label>
            <p className="admin-hint">
              Mặc định tắt để trả kết quả xác định tức thời; khi bật, lượt quét chạy nền theo hàng đợi và
              chỉ gửi cặp văn bản ra mô hình ngoài khi toàn bộ danh mục nguồn cho phép xử lý từ xa.
            </p>
          </div>

          <div className="form-actions">
            <button className="primary-button" disabled={!canStartScan} type="submit">
              {submitting ? "Đang khởi tạo lượt quét…" : "Bắt đầu rà soát mâu thuẫn"}
            </button>
          </div>
        </form>
      </section>

      {error && (
        <p className="status-pill status-danger" role="alert">
          {error}
        </p>
      )}

      {recentScans.length > 0 && (
        <section className="admin-card" aria-label="Lượt quét gần đây">
          <h2>Lượt quét gần đây ({recentScans.length})</h2>
          <div className="conflict-recent-list">
            {recentScans.map((scan) => (
              <div className="conflict-recent-item" key={scan.run_id}>
                <div>
                  <strong>
                    {CONFLICT_RUN_STATUS_LABELS[scan.status] ?? scan.status}
                  </strong>
                  <span className="evidence-meta">
                    {" · "}
                    {scan.scope_document_count} văn bản · Ngày đối chiếu{" "}
                    {formatVnDate(scan.as_of_date) ?? scan.as_of_date}
                    {scan.progress_total > 0
                      ? ` · ${scan.progress_done}/${scan.progress_total} cặp`
                      : ""}
                  </span>
                </div>
                <button
                  className="secondary-button"
                  onClick={() => void handleSelectScan(scan.run_id)}
                  type="button"
                >
                  Xem kết quả
                </button>
              </div>
            ))}
          </div>
        </section>
      )}

      {activeScan && (
        <section
          aria-label="Kết quả rà soát mâu thuẫn"
          aria-live="polite"
          className="admin-card conflict-results-section"
        >
          <div className="conflict-status-bar">
            <div>
              <h2>Chi tiết lượt quét</h2>
              <p className="conflict-status-text" role="status">
                Trạng thái:{" "}
                <strong>
                  {CONFLICT_RUN_STATUS_LABELS[activeScan.status] ?? activeScan.status}
                </strong>
                {activeScan.status === "running" || activeScan.progress_total > 0
                  ? ` (${activeScan.progress_done}/${activeScan.progress_total} cặp)`
                  : ""}
                {" · "}
                {activeScan.scope_document_count} văn bản · Tại ngày{" "}
                {formatVnDate(activeScan.as_of_date) ?? activeScan.as_of_date}
              </p>
            </div>
            {isActiveScanStatus(activeScan.status) && (
              <button
                className="secondary-button"
                disabled={cancelling}
                onClick={() => void handleCancelScan()}
                type="button"
              >
                {cancelling ? "Đang hủy…" : "Hủy lượt quét"}
              </button>
            )}
          </div>

          <p className="conflict-disclaimer status-pill status-warning" role="note">
            {activeScan.disclaimer || activeScan.reference_notice}
          </p>

          {activeScan.error_message && (
            <p className="status-pill status-danger" role="alert">
              {activeScan.error_message}
            </p>
          )}

          {activeScan.hidden_due_to_acl > 0 && (
            <p className="status-pill status-warning" role="status">
              Có {activeScan.hidden_due_to_acl} phát hiện đã bị ẩn do quyền truy cập danh mục hoặc
              kiểm chứng nguồn thay đổi.
            </p>
          )}

          {activeScan.summary_json && (
            <div className="conflict-summary-grid" role="group" aria-label="Tổng hợp lượt quét">
              <div className="conflict-summary-card">
                <strong>{activeScan.summary_json.total_documents}</strong>
                <span>Văn bản đã quét</span>
              </div>
              <div className="conflict-summary-card">
                <strong>{activeScan.summary_json.candidate_pairs_evaluated}</strong>
                <span>Cặp điều khoản đối chiếu</span>
              </div>
              <div className="conflict-summary-card">
                <strong>{activeScan.summary_json.total_findings}</strong>
                <span>Phát hiện gợi ý</span>
              </div>
              <div className="conflict-summary-card">
                <strong>{activeScan.summary_json.ai_used ? "Có" : "Không"}</strong>
                <span>Phân tích AI</span>
              </div>
            </div>
          )}

          <div
            aria-label="Lọc theo loại phát hiện"
            className="conflict-filter-tabs"
            role="group"
          >
            {FINDING_FILTER_OPTIONS.map((option) => (
              <button
                aria-pressed={findingFilter === option.value}
                className={
                  findingFilter === option.value
                    ? "secondary-button active"
                    : "secondary-button"
                }
                key={option.value}
                onClick={() => setFindingFilter(option.value)}
                type="button"
              >
                {option.label}
              </button>
            ))}
          </div>

          {isActiveScanStatus(activeScan.status) ? (
            <p className="chat-progress" role="status">
              Đang xử lý lượt quét (tự động cập nhật mỗi 2 giây)…
            </p>
          ) : visibleFindings.length === 0 ? (
            <p className="evidence-meta">
              {activeScan.findings.length === 0
                ? "Chưa ghi nhận phát hiện mâu thuẫn hoặc chồng chéo nào trong phạm vi này."
                : "Không có phát hiện nào khớp bộ lọc loại hiện tại."}
            </p>
          ) : (
            <div className="conflict-findings-list">
              {visibleFindings.map((finding) => (
                <ConflictFindingCard
                  accessToken={accessToken}
                  finding={finding}
                  key={finding.id}
                  onCompareDocuments={onOpenCompare}
                />
              ))}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
