import { useEffect, useRef, useState } from "react";
import {
  applyAdminOcrAiProposal,
  cancelAdminOcrAiProposal,
  createAdminOcrAiProposal,
  getAdminOcrAiProposal,
  rejectAdminOcrAiProposal,
} from "../api/client";
import type { AdminOcrAiApplyResponse, AdminOcrAiProposal } from "../types";
import { makeClientRequestId } from "../requestId";

interface OcrAiPanelProps {
  accessToken: string;
  documentId: string;
  versionId: string;
  pageNumber: number;
  revision: number;
  currentText: string;
  disabled?: boolean;
  onApplied: (result: AdminOcrAiApplyResponse) => Promise<void> | void;
}

export function OcrAiPanel({
  accessToken,
  documentId,
  versionId,
  pageNumber,
  revision,
  currentText,
  disabled,
  onApplied,
}: OcrAiPanelProps) {
  const [proposal, setProposal] = useState<AdminOcrAiProposal>();
  const [draftText, setDraftText] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const abortRef = useRef<AbortController | null>(null);
  const timerRef = useRef<number | null>(null);
  const mountedRef = useRef(true);
  const contextKey = [accessToken, documentId, versionId, pageNumber, revision].join("\0");
  const contextRef = useRef(contextKey);
  contextRef.current = contextKey;

  function isCurrentContext() {
    return mountedRef.current && contextRef.current === contextKey;
  }

  function stopPolling() {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    abortRef.current?.abort();
    abortRef.current = null;
  }

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      stopPolling();
    };
  }, []);

  useEffect(() => {
    stopPolling();
    setProposal(undefined);
    setDraftText("");
    setNote("");
    setError(undefined);
    setBusy(false);
  }, [accessToken, documentId, versionId, pageNumber, revision]);

  const pollingStatus = proposal?.status;
  const pollingProposalId = proposal?.proposal_id;

  useEffect(() => {
    if (
      !accessToken
      || !pollingProposalId
      || (pollingStatus !== "queued" && pollingStatus !== "running")
    ) {
      return;
    }
    const controller = new AbortController();
    abortRef.current = controller;

    const schedulePoll = () => {
      timerRef.current = window.setTimeout(async () => {
        if (!mountedRef.current || controller.signal.aborted) return;
        try {
          const next = await getAdminOcrAiProposal(accessToken, pollingProposalId, controller.signal);
          if (!mountedRef.current || controller.signal.aborted) return;
          setProposal(next);
          if (next.status === "ready") {
            setDraftText(next.candidate_text ?? "");
          } else if (next.status === "queued" || next.status === "running") {
            schedulePoll();
          }
        } catch (caught) {
          if (!controller.signal.aborted && mountedRef.current) {
            setError(caught instanceof Error ? caught.message : "Không thể kiểm tra tác vụ OCR AI.");
          }
        }
      }, 1000);
    };

    schedulePoll();
    return () => {
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      controller.abort();
      if (abortRef.current === controller) abortRef.current = null;
    };
  }, [accessToken, pollingProposalId, pollingStatus]);

  async function requestAiRead() {
    if (!accessToken || busy || disabled) return;
    stopPolling();
    const controller = new AbortController();
    abortRef.current = controller;
    setBusy(true);
    setError(undefined);
    try {
      const created = await createAdminOcrAiProposal(
        accessToken,
        documentId,
        versionId,
        { page_number: pageNumber, expected_revision: revision, request_id: makeClientRequestId() },
        controller.signal,
      );
      if (!mountedRef.current || controller.signal.aborted) return;
      setProposal(created);
      if (created.status === "ready") {
        setDraftText(created.candidate_text ?? "");
      }
    } catch (caught) {
      if (!controller.signal.aborted && mountedRef.current) {
        setError(caught instanceof Error ? caught.message : "Không thể gửi yêu cầu OCR AI.");
      }
    } finally {
      if (isCurrentContext() && !controller.signal.aborted) setBusy(false);
    }
  }

  async function cancelActive() {
    if (!proposal || !accessToken || busy) return;
    stopPolling();
    setBusy(true);
    setError(undefined);
    try {
      const updated = await cancelAdminOcrAiProposal(accessToken, proposal.proposal_id);
      if (isCurrentContext()) setProposal(updated);
    } catch (caught) {
      if (isCurrentContext()) {
        setError(caught instanceof Error ? caught.message : "Không thể hủy tác vụ OCR AI.");
      }
    } finally {
      if (isCurrentContext()) setBusy(false);
    }
  }

  async function rejectReady() {
    if (!proposal || !accessToken || busy) return;
    setBusy(true);
    setError(undefined);
    try {
      const updated = await rejectAdminOcrAiProposal(accessToken, proposal.proposal_id, note);
      if (isCurrentContext()) {
        setProposal(updated);
        setDraftText("");
        setNote("");
      }
    } catch (caught) {
      if (isCurrentContext()) {
        setError(caught instanceof Error ? caught.message : "Không thể bỏ qua đề xuất OCR AI.");
      }
    } finally {
      if (isCurrentContext()) setBusy(false);
    }
  }

  async function applyReady() {
    if (!proposal || !accessToken || busy) return;
    setBusy(true);
    setError(undefined);
    try {
      const res = await applyAdminOcrAiProposal(accessToken, proposal.proposal_id, {
        expected_revision: revision,
        corrected_text: draftText,
        note: note || undefined,
      });
      if (isCurrentContext()) {
        setProposal(res.proposal);
        await onApplied(res);
      }
    } catch (caught) {
      if (isCurrentContext()) {
        setError(caught instanceof Error ? caught.message : "Không thể áp dụng đề xuất OCR AI.");
      }
    } finally {
      if (isCurrentContext()) setBusy(false);
    }
  }

  const isRunning = proposal?.status === "queued" || proposal?.status === "running";
  const isReady = proposal?.status === "ready" && !proposal.stale;
  const isStale = proposal?.stale || proposal?.status === "stale";
  const warnings = proposal?.candidate?.warnings ?? [];
  const unreadable = proposal?.candidate?.unreadable ?? [];

  return (
    <section className="ocr-ai-panel" aria-label="Hỗ trợ OCR AI trang hiện tại">
      <div className="action-group">
        <button
          className="secondary-button"
          disabled={Boolean(disabled) || busy || isRunning}
          onClick={() => void requestAiRead()}
          type="button"
        >
          Đọc lại trang này bằng OCR AI
        </button>
        {isRunning && (
          <button
            className="secondary-button"
            disabled={busy}
            onClick={() => void cancelActive()}
            type="button"
          >
            Hủy tác vụ OCR AI
          </button>
        )}
      </div>

      {error && (
        <p className="status-pill status-danger" role="alert">
          {error}
        </p>
      )}

      {isRunning && (
        <p className="status-pill status-warning" role="status">
          Đang đọc ảnh trang {pageNumber} bằng OCR AI cục bộ…
        </p>
      )}

      {isStale && (
        <p className="status-pill status-warning" role="status">
          Phiên bản hoặc nội dung trang đã thay đổi. Hãy tạo lại yêu cầu OCR AI.
        </p>
      )}

      {proposal?.status === "failed" && (
        <p className="status-pill status-danger" role="alert">
          Tác vụ OCR AI thất bại ({proposal.error_code ?? "OCR_AI_FAILED"}).
        </p>
      )}

      {proposal?.status === "cancelled" && (
        <p className="evidence-meta">Đã hủy đề xuất OCR AI cho trang {pageNumber}.</p>
      )}

      {proposal?.status === "rejected" && (
        <p className="evidence-meta">Đã bỏ qua đề xuất OCR AI (bản gốc vẫn giữ nguyên).</p>
      )}

      {isReady && proposal && (
        <div className="document-confirmation">
          <p className="status-pill status-warning">
            Đề xuất OCR AI — phải đối chiếu với ảnh PDF trước khi áp dụng
          </p>

          {(warnings.length > 0 || unreadable.length > 0) && (
            <div className="ocr-ai-warnings">
              {warnings.length > 0 && (
                <div>
                  <strong>Cảnh báo OCR AI:</strong>
                  <ul>
                    {warnings.map((w, idx) => (
                      <li key={`w-${idx}`}>{w}</li>
                    ))}
                  </ul>
                </div>
              )}
              {unreadable.length > 0 && (
                <div>
                  <strong>Phần không đọc rõ:</strong>
                  <ul>
                    {unreadable.map((u, idx) => (
                      <li key={`u-${idx}`}>{u}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          <div className="ocr-ai-compare">
            <div>
              <strong>Chữ hiện tại (trang {pageNumber})</strong>
              <pre className="ocr-page-text">{proposal.current_page_text ?? currentText ?? ""}</pre>
            </div>
            <div>
              <strong>So sánh thay đổi</strong>
              <pre className="ocr-page-text ocr-ai-diff">
                {(proposal.diff ?? []).map((entry, idx) => (
                  <div
                    className={`ocr-diff-line ocr-diff-${entry.op}`}
                    key={`d-${idx}`}
                  >
                    {entry.op === "delete" ? `- ${entry.text}` : entry.op === "insert" ? `+ ${entry.text}` : `  ${entry.text}`}
                  </div>
                ))}
              </pre>
            </div>
          </div>

          <label className="field-label">
            Chữ OCR AI để áp dụng
            <textarea
              aria-label="Chữ OCR AI để áp dụng"
              disabled={busy}
              maxLength={50000}
              onChange={(event) => setDraftText(event.target.value)}
              rows={8}
              value={draftText}
            />
          </label>
          <label className="field-label">
            Ghi chú áp dụng (tùy chọn)
            <input
              aria-label="Ghi chú áp dụng OCR AI"
              disabled={busy}
              maxLength={500}
              onChange={(event) => setNote(event.target.value)}
              type="text"
              value={note}
            />
          </label>

          <div className="action-group">
            <button
              className="primary-button"
              disabled={busy || !draftText.trim()}
              onClick={() => void applyReady()}
              type="button"
            >
              Áp dụng đề xuất vào bản nháp
            </button>
            <button
              className="secondary-button"
              disabled={busy}
              onClick={() => void rejectReady()}
              type="button"
            >
              Bỏ qua đề xuất
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
