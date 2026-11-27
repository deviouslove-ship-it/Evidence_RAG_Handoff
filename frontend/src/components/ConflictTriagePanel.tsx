import { useCallback, useEffect, useRef, useState } from "react";

import { listAdminConflictFindings, reviewConflictFinding } from "../api/client";
import type {
  ConflictAmendmentAction,
  ConflictFindingView,
  ConflictReviewStatus,
} from "../types";
import {
  CONFLICT_AMENDMENT_ACTION_LABELS,
  CONFLICT_FINDING_TYPE_LABELS,
  CONFLICT_PRECEDENCE_LABELS,
  CONFLICT_REVIEW_STATUS_LABELS,
  CONFLICT_SEVERITY_LABELS,
} from "../types";

export interface ConflictTriagePanelProps {
  accessToken: string;
}

const AMENDMENT_ACTIONS: ConflictAmendmentAction[] = [
  "modify",
  "replace",
  "add",
  "repeal",
  "repeal_partial",
  "suspend",
];

function isAbortError(caught: unknown): boolean {
  return caught instanceof DOMException
    ? caught.name === "AbortError"
    : caught instanceof Error && caught.name === "AbortError";
}

function FindingTriageItem({
  accessToken,
  finding,
  onReviewed,
}: {
  accessToken: string;
  finding: ConflictFindingView;
  onReviewed: (message: string) => Promise<void>;
}) {
  const [reviewNote, setReviewNote] = useState(finding.review_note ?? "");
  const [createDraft, setCreateDraft] = useState(false);
  const [amendmentAction, setAmendmentAction] = useState<ConflictAmendmentAction>("modify");
  const [sourceSide, setSourceSide] = useState<"a" | "b">("a");
  const [validFrom, setValidFrom] = useState("");
  const [busy, setBusy] = useState(false);
  const [itemError, setItemError] = useState<string>();

  async function submitDecision(decision: "confirm" | "dismiss") {
    if (busy) return;
    setBusy(true);
    setItemError(undefined);
    try {
      const shouldCreateDraft = decision === "confirm" && createDraft;
      const result = await reviewConflictFinding(accessToken, finding.id, {
        decision,
        review_note: reviewNote.trim() || null,
        create_amendment_draft: shouldCreateDraft,
        ...(shouldCreateDraft
          ? {
              amendment_action: amendmentAction,
              source_side: sourceSide,
              ...(validFrom ? { valid_from: validFrom } : {}),
            }
          : {}),
      });
      const baseMsg =
        decision === "confirm"
          ? "Đã xác nhận phát hiện mâu thuẫn."
          : "Đã bỏ qua phát hiện mâu thuẫn.";
      const draftSuffix = result.linked_amendment_id
        ? ` Đã tạo đề xuất sửa đổi ở trạng thái bản nháp (${result.amendment_review_status ?? "draft"}) để duyệt tại tab Hiệu lực.`
        : "";
      await onReviewed(baseMsg + draftSuffix);
    } catch (caught) {
      setItemError(caught instanceof Error ? caught.message : "Không thể lưu kết quả thẩm định.");
    } finally {
      setBusy(false);
    }
  }

  const sideATitle =
    [finding.document_a_number, finding.document_a_title].filter(Boolean).join(" · ") ||
    finding.document_a_id;
  const sideBTitle =
    [finding.document_b_number, finding.document_b_title].filter(Boolean).join(" · ") ||
    finding.document_b_id;

  return (
    <article className="conflict-finding-card" data-status={finding.review_status}>
      <div className="conflict-finding-tags">
        <span className="tag conflict-type-tag" data-type={finding.finding_type}>
          {CONFLICT_FINDING_TYPE_LABELS[finding.finding_type] ?? finding.finding_type}
        </span>
        <span className="tag conflict-severity-tag" data-severity={finding.severity}>
          {CONFLICT_SEVERITY_LABELS[finding.severity] ?? finding.severity}
        </span>
        <span className="tag conflict-review-tag" data-status={finding.review_status}>
          {CONFLICT_REVIEW_STATUS_LABELS[finding.review_status] ?? finding.review_status}
        </span>
        <span className="tag">
          {CONFLICT_PRECEDENCE_LABELS[finding.precedence_result] ?? finding.precedence_result}
        </span>
      </div>

      <p className="conflict-explanation">{finding.explanation}</p>

      <div className="conflict-sides">
        <section className="conflict-side" data-side="a" aria-label="Trích dẫn vế A">
          <div className="conflict-side-head">
            <strong className="conflict-doc-title">{sideATitle}</strong>
            <span className="tag">
              {finding.node_a_label || finding.node_a_path || "Đoạn văn"}
            </span>
          </div>
          <p className="conflict-node-text">
            {finding.node_a_text ?? "(Không có nội dung trích dẫn)"}
          </p>
        </section>
        <section className="conflict-side" data-side="b" aria-label="Trích dẫn vế B">
          <div className="conflict-side-head">
            <strong className="conflict-doc-title">{sideBTitle}</strong>
            <span className="tag">
              {finding.node_b_label || finding.node_b_path || "Đoạn văn"}
            </span>
          </div>
          <p className="conflict-node-text">
            {finding.node_b_text ?? "(Không có nội dung trích dẫn)"}
          </p>
        </section>
      </div>

      {finding.linked_amendment_id && (
        <p className="evidence-meta">
          Đã liên kết đề xuất sửa đổi mã <code>{finding.linked_amendment_id}</code> (trạng thái{" "}
          <strong>draft</strong> — xử lý tiếp tại tab Hiệu lực).
        </p>
      )}

      {itemError && (
        <p className="status-pill status-danger" role="alert">
          {itemError}
        </p>
      )}

      <div className="conflict-triage-controls form-stack">
        <label className="field-label">
          Ghi chú thẩm định
          <input
            disabled={busy}
            onChange={(event) => setReviewNote(event.target.value)}
            placeholder="Nhập căn cứ xác nhận hoặc lý do bỏ qua..."
            type="text"
            value={reviewNote}
          />
        </label>

        {!finding.linked_amendment_id && (
          <>
            <label className="checkbox-row">
              <input
                checked={createDraft}
                disabled={busy}
                onChange={(event) => setCreateDraft(event.target.checked)}
                type="checkbox"
              />
              <span>Tạo đề xuất sửa đổi (bản nháp)</span>
            </label>

            {createDraft && (
              <div className="conflict-draft-fields">
                <div className="compact-form-grid">
                  <label className="field-label">
                    Loại tác động sửa đổi
                    <select
                      disabled={busy}
                      onChange={(event) =>
                        setAmendmentAction(event.target.value as ConflictAmendmentAction)
                      }
                      value={amendmentAction}
                    >
                      {AMENDMENT_ACTIONS.map((action) => (
                        <option key={action} value={action}>
                          {CONFLICT_AMENDMENT_ACTION_LABELS[action]}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="field-label">
                    Văn bản nguồn tác động
                    <select
                      disabled={busy}
                      onChange={(event) => setSourceSide(event.target.value as "a" | "b")}
                      value={sourceSide}
                    >
                      <option value="a">Vế A tác động lên Vế B</option>
                      <option value="b">Vế B tác động lên Vế A</option>
                    </select>
                  </label>
                  <label className="field-label">
                    Ngày có hiệu lực sửa đổi (tùy chọn)
                    <input
                      disabled={busy}
                      onChange={(event) => setValidFrom(event.target.value)}
                      type="date"
                      value={validFrom}
                    />
                  </label>
                </div>
                <p className="admin-hint">
                  Bản ghi sửa đổi luôn được lưu ở trạng thái bản nháp (draft) và phải qua quy trình
                  duyệt tại tab Hiệu lực trước khi làm thay đổi trạng thái văn bản.
                </p>
              </div>
            )}
          </>
        )}

        <div className="form-actions">
          <button
            className="primary-button"
            disabled={busy}
            onClick={() => void submitDecision("confirm")}
            type="button"
          >
            Xác nhận
          </button>
          <button
            className="secondary-button"
            disabled={busy}
            onClick={() => void submitDecision("dismiss")}
            type="button"
          >
            Bỏ qua
          </button>
        </div>
      </div>
    </article>
  );
}

export function ConflictTriagePanel({ accessToken }: ConflictTriagePanelProps) {
  const [statusFilter, setStatusFilter] = useState<"" | ConflictReviewStatus>("pending");
  const [items, setItems] = useState<ConflictFindingView[]>([]);
  const [total, setTotal] = useState(0);
  const [disclaimer, setDisclaimer] = useState(
    "Gợi ý tự động — cần chuyên viên thẩm định trước khi áp dụng.",
  );
  const [loading, setLoading] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string>();
  const [errorMsg, setErrorMsg] = useState<string>();
  const controllerRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setLoading(true);
    setErrorMsg(undefined);
    try {
      const response = await listAdminConflictFindings(accessToken, {
        ...(statusFilter ? { review_status: statusFilter } : {}),
        limit: 100,
        offset: 0,
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      setItems(response.items);
      setTotal(response.total);
      if (response.disclaimer) setDisclaimer(response.disclaimer);
    } catch (caught) {
      if (controller.signal.aborted || isAbortError(caught)) return;
      setErrorMsg(
        caught instanceof Error ? caught.message : "Không tải được hàng đợi rà soát mâu thuẫn.",
      );
    } finally {
      if (controllerRef.current === controller) {
        controllerRef.current = null;
      }
      if (!controller.signal.aborted) {
        setLoading(false);
      }
    }
  }, [accessToken, statusFilter]);

  useEffect(() => {
    void load();
    return () => {
      controllerRef.current?.abort();
      controllerRef.current = null;
    };
  }, [load]);

  return (
    <section className="admin-panel conflict-triage-panel" aria-label="Rà soát mâu thuẫn">
      <div className="compact-card-header">
        <div>
          <h2>Hàng đợi thẩm định phát hiện mâu thuẫn ({total})</h2>
          <p className="admin-hint">{disclaimer}</p>
        </div>
        <label className="field-label">
          Trạng thái rà soát
          <select
            onChange={(event) =>
              setStatusFilter(event.target.value as "" | ConflictReviewStatus)
            }
            value={statusFilter}
          >
            <option value="">Tất cả trạng thái</option>
            <option value="pending">{CONFLICT_REVIEW_STATUS_LABELS.pending}</option>
            <option value="confirmed">{CONFLICT_REVIEW_STATUS_LABELS.confirmed}</option>
            <option value="dismissed">{CONFLICT_REVIEW_STATUS_LABELS.dismissed}</option>
            <option value="linked_amendment">
              {CONFLICT_REVIEW_STATUS_LABELS.linked_amendment}
            </option>
          </select>
        </label>
      </div>

      {statusMsg && (
        <p className="status-pill status-success" role="status">
          {statusMsg}
        </p>
      )}
      {errorMsg && (
        <p className="status-pill status-danger" role="alert">
          {errorMsg}
        </p>
      )}
      {loading && <p className="evidence-meta">Đang tải danh sách phát hiện…</p>}

      {!loading && items.length === 0 ? (
        <p className="evidence-meta">Không có phát hiện mâu thuẫn nào trong bộ lọc hiện tại.</p>
      ) : (
        <div className="conflict-findings-list">
          {items.map((finding) => (
            <FindingTriageItem
              accessToken={accessToken}
              finding={finding}
              key={finding.id}
              onReviewed={async (message) => {
                setStatusMsg(message);
                await load();
              }}
            />
          ))}
        </div>
      )}
    </section>
  );
}
