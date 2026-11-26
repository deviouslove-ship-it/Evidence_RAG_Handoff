import { useEffect, useRef, useState } from "react";
import { ApiRequestError, fetchDocumentVersionPdf } from "../api/client";
import type { PageTextCandidateDoc, PageTextEntryState } from "./pageTextIntent";

interface PageTextPanelProps {
  accessToken?: string;
  state: PageTextEntryState;
  onSelectCandidate: (candidate: PageTextCandidateDoc, pdfPageNumber: number) => void;
  onConfirmPdfPage: (candidate: PageTextCandidateDoc, pdfPageNumber: number) => void;
  onCancelTask: (taskId: string) => void;
  onRequestAiRetry: (candidate: PageTextCandidateDoc, pageNumber: number) => void;
}

export function PageTextPanel({
  accessToken,
  state,
  onSelectCandidate,
  onConfirmPdfPage,
  onCancelTask,
  onRequestAiRetry,
}: PageTextPanelProps) {
  const [pdfPageInput, setPdfPageInput] = useState(
    state.kind === "confirm_pdf_page" ? String(state.pageNumber) : "1",
  );
  const [copied, setCopied] = useState(false);
  const [copyMessage, setCopyMessage] = useState("");
  const [pdfUrl, setPdfUrl] = useState<string>();
  const [pdfBusy, setPdfBusy] = useState(false);
  const [pdfError, setPdfError] = useState<string>();
  const pdfRequest = useRef<AbortController | null>(null);
  const documentKey = "candidate" in state && state.candidate
    ? `${state.candidate.document_id}/${state.candidate.document_version_id}/${
      state.kind === "ready" ? state.response.page_number : state.pageNumber}`
    : state.kind;

  useEffect(() => {
    if (state.kind === "confirm_pdf_page") {
      setPdfPageInput(String(state.pageNumber));
    }
    setCopied(false);
    setCopyMessage("");
  }, [state]);

  useEffect(() => {
    return () => {
      if (pdfUrl) URL.revokeObjectURL(pdfUrl);
    };
  }, [pdfUrl]);

  useEffect(() => {
    pdfRequest.current?.abort();
    pdfRequest.current = null;
    setPdfUrl(undefined);
    setPdfBusy(false);
    setPdfError(undefined);
    return () => {
      pdfRequest.current?.abort();
      pdfRequest.current = null;
    };
  }, [accessToken, documentKey]);

  async function openOriginalPdf(candidate: PageTextCandidateDoc) {
    if (!accessToken || pdfBusy) return;
    const controller = new AbortController();
    pdfRequest.current = controller;
    setPdfBusy(true);
    setPdfError(undefined);
    try {
      const blob = await fetchDocumentVersionPdf(
        accessToken,
        candidate.document_id,
        candidate.document_version_id,
        controller.signal,
      );
      if (controller.signal.aborted || pdfRequest.current !== controller) return;
      const nextUrl = URL.createObjectURL(blob);
      setPdfUrl(nextUrl);
    } catch (caught) {
      if (controller.signal.aborted || pdfRequest.current !== controller) return;
      setPdfError(
        caught instanceof ApiRequestError
          ? caught.message
          : "Không thể tải bản PDF gốc lúc này.",
      );
    } finally {
      if (pdfRequest.current === controller) {
        pdfRequest.current = null;
        setPdfBusy(false);
      }
    }
  }

  if (state.kind === "missing_doc") {
    return (
      <section className="page-text-panel" aria-label="Chọn văn bản đọc trang">
        <p className="status-pill status-warning">Chưa rõ văn bản cần đọc trang {state.pageNumber}</p>
        <p className="evidence-meta">
          Hãy nêu tên hoặc số hiệu văn bản trong câu hỏi (ví dụ: &ldquo;Đọc nội dung trang{" "}
          {state.pageNumber} Nghị định ...&rdquo;), hoặc tra cứu văn bản trước rồi hỏi tiếp.
        </p>
      </section>
    );
  }

  if (state.kind === "not_found") {
    return (
      <section className="page-text-panel" aria-label="Không tìm thấy văn bản">
        <p className="status-pill status-warning">Không tìm thấy văn bản &ldquo;{state.query}&rdquo;</p>
        <p className="evidence-meta">
          Không có văn bản đã duyệt nào khớp trong phạm vi quyền đọc hiện tại.
        </p>
      </section>
    );
  }

  if (state.kind === "choose_doc") {
    return (
      <section className="page-text-panel" aria-label="Chọn văn bản cần đọc trang">
        <h2>Chọn văn bản cần đọc trang {state.pageNumber}</h2>
        <p className="evidence-meta">
          Có nhiều văn bản khớp yêu cầu. Chọn đúng văn bản để đọc theo số thứ tự trang PDF:
        </p>
        <ul className="page-text-candidate-list">
          {state.candidates.map((item) => (
            <li key={item.document_version_id}>
              <button
                className="secondary-button"
                onClick={() => onSelectCandidate(item, state.pageNumber)}
                type="button"
              >
                {item.document_number ? `${item.document_number} — ` : ""}
                {item.title}
              </button>
            </li>
          ))}
        </ul>
      </section>
    );
  }

  if (state.kind === "confirm_pdf_page") {
    const parsed = Number(pdfPageInput);
    const valid = Number.isSafeInteger(parsed) && parsed >= 1;
    return (
      <section className="page-text-panel" aria-label="Xác nhận số trang PDF">
        <h2>Xác nhận số trang PDF</h2>
        <p>
          Bạn nhắc tới <strong>trang in {state.pageNumber}</strong> của{" "}
          <strong>
            {state.candidate.document_number ? `${state.candidate.document_number} — ` : ""}
            {state.candidate.title}
          </strong>
          . Số trang in trên giấy có thể khác số thứ tự trang trong tệp PDF (bìa, mục lục).
        </p>
        <div className="action-group">
          <label className="field-label" style={{ maxWidth: "10rem" }}>
            Trang PDF
            <input
              min={1}
              onChange={(event) => setPdfPageInput(event.target.value)}
              type="number"
              value={pdfPageInput}
            />
          </label>
          <button
            className="primary-button"
            disabled={!valid}
            onClick={() => onConfirmPdfPage(state.candidate, parsed)}
            type="button"
          >
            Đọc Trang PDF {valid ? parsed : state.pageNumber}
          </button>
        </div>
      </section>
    );
  }

  if (state.kind === "loading") {
    const taskId = state.response?.task_id;
    return (
      <section className="page-text-panel" aria-label="Đang đọc trang PDF">
        <h2>
          Trang PDF {state.pageNumber} — {state.candidate.title}
        </h2>
        <p className="status-pill status-warning" role="status">
          Đang đọc ảnh trang PDF bằng OCR AI cục bộ…
        </p>
        {taskId && (
          <button
            className="secondary-button"
            onClick={() => onCancelTask(taskId)}
            type="button"
          >
            Hủy đọc trang
          </button>
        )}
      </section>
    );
  }

  if (state.kind === "error") {
    return (
      <section className="page-text-panel" aria-label="Lỗi đọc trang PDF">
        <p className="status-pill status-danger" role="alert">
          {state.message}
        </p>
      </section>
    );
  }

  const { response, candidate } = state;
  const pageText = response.page_text ?? "";

  return (
    <section className="page-text-panel" aria-label={`Nội dung Trang PDF ${response.page_number}/${response.total_pages}`}>
      <header className="results-header">
        <div>
          <h2>
            Trang PDF {response.page_number}/{response.total_pages}
          </h2>
          <p className="evidence-meta">
            {response.document_number ? `${response.document_number} — ` : ""}
            {response.document_title}
          </p>
        </div>
        <span className={response.verified ? "status-pill status-success" : "status-pill status-warning"}>
          {response.verified
            ? "Chữ đã trích xuất của trang"
            : (response.warning ?? `AI đọc từ ảnh trang ${response.page_number} — chưa đối chiếu thủ công`)}
        </span>
      </header>

      <pre className="page-text-content">{pageText || "(Trang không có chữ)"}</pre>

      {Boolean(response.warnings?.length || response.unreadable?.length) && (
        <div className="status-pill status-warning">
          <strong>Phần cần đối chiếu với trang gốc</strong>
          <ul>{[...(response.warnings ?? []), ...(response.unreadable ?? [])].map((note, index) => (
            <li key={index}>{note}</li>
          ))}</ul>
        </div>
      )}

      <div className="action-group">
        <button
          className="secondary-button"
          onClick={() => {
            const report = (ok: boolean) => {
              setCopied(ok);
              setCopyMessage(ok ? "Đã sao chép" : "Không thể sao chép tự động. Hãy chọn và sao chép phần chữ bên trên.");
            };
            const fallback = () => {
              const focused = document.activeElement;
              const field = document.createElement("textarea");
              field.value = pageText;
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
              void navigator.clipboard.writeText(pageText).then(() => report(true)).catch(fallback);
            } else fallback();
          }}
          type="button"
        >
          {copied ? "Đã sao chép" : "Sao chép nội dung trang"}
        </button>
        <span role="status">{copyMessage}</span>
        <button
          className="secondary-button"
          disabled={pdfBusy}
          onClick={() => void openOriginalPdf(candidate)}
          type="button"
        >
          {pdfBusy ? "Đang mở trang gốc…" : "Mở trang gốc"}
        </button>
        {response.verified && (
          <button
            className="secondary-button"
            onClick={() => onRequestAiRetry(candidate, response.page_number)}
            type="button"
          >
            Đọc lại bằng OCR AI
          </button>
        )}
      </div>

      {pdfError && <p className="status-pill status-danger" role="alert">{pdfError}</p>}
      {pdfUrl && (
        <div className="page-text-pdf-wrap">
          <div className="action-group">
            <button
              className="secondary-button"
              onClick={() => {
                URL.revokeObjectURL(pdfUrl);
                setPdfUrl(undefined);
              }}
              type="button"
            >
              Đóng PDF gốc
            </button>
          </div>
          <iframe
            className="pdf-frame document-source-preview"
            src={`${pdfUrl}#page=${response.page_number}`}
            title={`Trang gốc ${response.page_number}`}
          />
        </div>
      )}
    </section>
  );
}
