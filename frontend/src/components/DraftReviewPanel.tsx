import { useEffect, useRef, useState } from "react";
import { fetchAdminDraftPdf, listAdminContentDuplicates, listAdminReviewTasks, reextractAdminDraft, resolveAdminReviewTask, type PotentialDuplicate, type ReviewTask } from "../api/client";
import type { PdfDraftListItem } from "../types";

const REVIEW_REASON_LABELS: Record<string, string> = {
  possible_duplicate_content: "Có thể trùng nội dung với tài liệu đã có; đối chiếu nguồn và phiên bản",
  unanchored_source_spans: "Có đoạn chưa gắn chính xác với trang PDF; cần xử lý trước khi phê duyệt",
  source_revalidation_required: "Cần đối chiếu lại dữ liệu trích xuất với PDF gốc",
  source_reextraction_review: "Cần rà soát lại kết quả trích xuất từ PDF gốc",
  metadata_and_source_verification: "Cần xác minh thông tin và nguồn công bố",
  metadata_changed: "Cần kiểm tra lại thông tin văn bản đã chỉnh sửa",
  document_reprocessed: "Cần rà soát lại kết quả xử lý từ tệp gốc",
  document_number_not_in_ocr_text: "Không thấy số hiệu đã khai báo trong chữ OCR hai trang đầu; đối chiếu số hiệu trên bản scan",
};

const OCR_FLAG_LABELS: Record<string, string> = {
  NO_TEXT: "OCR không đọc được chữ",
  LOW_CONFIDENCE: "độ tin cậy nhận dạng thấp",
  LITTLE_TEXT_FOR_INK: "trang có nhiều nội dung nhưng đọc được ít chữ (có thể sót bảng, dấu, chữ mờ)",
  SUSPECT_CHARACTERS: "có ký tự/từ không phải tiếng Việt",
  SUSPECT_POINT_MARKERS: "ký hiệu điểm có thể bị đọc nhầm (ví dụ “l)” thành “1)”)",
  DOCUMENT_NUMBER_NOT_FOUND: "không thấy số hiệu văn bản đã khai báo trong chữ OCR",
  ROTATED: "trang bị xoay, đã đọc lại sau khi xoay",
};

function pageTaskLabel(task: ReviewTask): string | undefined {
  const page = task.page;
  if (!page) return undefined;
  if (page.extraction_method === "local_ocr") {
    return `Trang ${page.page_number}: chữ do OCR đọc từ bản scan; đối chiếu với trang scan rồi xác nhận`;
  }
  if (!page.text) {
    return `Trang ${page.page_number}: chưa có chữ (không có lớp chữ, OCR chưa chạy hoặc không đọc được)`;
  }
  return `Trang ${page.page_number}: lớp chữ có ký tự lỗi; đối chiếu với bản gốc`;
}

function OcrPageCheck({ task, onShowPage }: { task: ReviewTask; onShowPage: (page: number) => void }) {
  const page = task.page;
  if (!page) return null;
  const diagnostics = page.ocr_diagnostics ?? {};
  const flags = (diagnostics.flags ?? []).map((flag) => OCR_FLAG_LABELS[flag] ?? flag);
  return <div className="ocr-page-check">
    {page.extraction_method === "local_ocr" && <p className="evidence-meta">
      {diagnostics.words ?? 0} từ · độ tin cậy trung bình {diagnostics.mean_confidence ?? "?"}%
      {typeof diagnostics.low_confidence_share === "number"
        && ` · ${Math.round(diagnostics.low_confidence_share * 100)}% từ dưới 60%`}
      {diagnostics.rotation ? ` · đã xoay ${diagnostics.rotation}°` : ""}
    </p>}
    {flags.length > 0 && <p className="status-pill status-warning">Cần chú ý: {flags.join("; ")}.</p>}
    {(diagnostics.suspect_tokens?.length ?? 0) > 0 && <p className="evidence-meta">
      Từ nghi đọc sai: {diagnostics.suspect_tokens?.join(", ")}
    </p>}
    {(diagnostics.suspect_markers?.length ?? 0) > 0 && <p className="evidence-meta">
      Dòng có ký hiệu điểm nghi đọc nhầm: {diagnostics.suspect_markers?.join(" | ")}
    </p>}
    {(diagnostics.low_confidence_words?.length ?? 0) > 0 && <p className="evidence-meta">
      Từ độ tin cậy thấp: {diagnostics.low_confidence_words?.join(", ")}
    </p>}
    <button className="link-button" type="button" onClick={() => onShowPage(page.page_number)}>
      Xem trang {page.page_number} của bản scan
    </button>
    <details>
      <summary>Chữ đã trích xuất của trang {page.page_number} (dữ liệu xử lý, không phải bản gốc)</summary>
      <pre className="ocr-page-text">{page.text || "(trống)"}{page.text_truncated ? "\n…" : ""}</pre>
    </details>
    {!page.text && <p className="evidence-meta">
      Chỉ xác nhận khi trang này không có nội dung văn bản (trang ký, đóng dấu); nếu có chữ,
      hãy cấu hình OCR và trích xuất lại hoặc từ chối bản nháp.
    </p>}
  </div>;
}

export function DraftReviewPanel({ draft, accessToken, canResolve, canReextract, onUpdated }: {
  draft: PdfDraftListItem; accessToken: string; canResolve: boolean; canReextract: boolean;
  onUpdated: () => Promise<void>;
}) {
  const [pdfUrl, setPdfUrl] = useState<string>();
  const [pdfPage, setPdfPage] = useState<number>();
  const [tasks, setTasks] = useState<ReviewTask[]>([]);
  const [duplicates, setDuplicates] = useState<PotentialDuplicate[]>([]);
  const [contentCheckAvailable, setContentCheckAvailable] = useState<boolean>();
  const [note, setNote] = useState("");
  const [error, setError] = useState<string>();
  const [status, setStatus] = useState<string>();
  const [busy, setBusy] = useState(false);
  const resolving = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    let objectUrl: string | undefined;
    setPdfUrl(undefined);
    setTasks([]);
    setDuplicates([]);
    setContentCheckAvailable(undefined);
    setError(undefined);
    setStatus(undefined);
    setNote("");
    fetchAdminDraftPdf(accessToken, draft.document_version_id, controller.signal).then((blob) => {
      const next = URL.createObjectURL(blob);
      if (controller.signal.aborted) { URL.revokeObjectURL(next); return; }
      objectUrl = next;
      setPdfUrl(next);
    }).catch((caught: unknown) => {
      if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : "Không thể mở PDF.");
    });
    listAdminReviewTasks(accessToken, draft.document_version_id, controller.signal).then((items) => {
      if (!controller.signal.aborted) setTasks(items);
    }).catch((caught: unknown) => {
      if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : "Không thể tải tác vụ.");
    });
    listAdminContentDuplicates(accessToken, draft.document_version_id, controller.signal).then((result) => {
      if (!controller.signal.aborted) {
        setDuplicates(result.potential_duplicates ?? []);
        setContentCheckAvailable(result.content_check_available === true);
      }
    }).catch((caught: unknown) => {
      if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : "Không thể kiểm tra trùng nội dung.");
    });
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [accessToken, draft.document_version_id]);

  async function resolve(task: ReviewTask) {
    if (resolving.current || !note.trim() || !pdfUrl || !canResolve) return;
    resolving.current = true;
    setBusy(true);
    setError(undefined);
    try {
      await resolveAdminReviewTask(accessToken, task.id, note.trim());
      setTasks(await listAdminReviewTasks(accessToken, draft.document_version_id));
      await onUpdated();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Không thể xử lý tác vụ.");
    } finally { resolving.current = false; setBusy(false); }
  }

  async function reextract() {
    if (resolving.current || !pdfUrl || !canReextract) return;
    resolving.current = true;
    setBusy(true);
    setError(undefined);
    setStatus(undefined);
    try {
      const result = await reextractAdminDraft(accessToken, draft.document_version_id);
      setStatus(`Đã khôi phục ${result.pages_restored} trang, gắn ${result.nodes_anchored} đoạn; còn ${result.nodes_unresolved} đoạn chưa gắn trang. Cần thẩm định trước khi phê duyệt.`);
      try {
        const [items, matches] = await Promise.all([
          listAdminReviewTasks(accessToken, draft.document_version_id),
          listAdminContentDuplicates(accessToken, draft.document_version_id),
          onUpdated(),
        ]);
        setTasks(items);
        setDuplicates(matches.potential_duplicates ?? []);
        setContentCheckAvailable(matches.content_check_available === true);
      } catch {
        setError("Đã trích xuất lại nhưng chưa thể tải lại danh sách rà soát; hãy mở lại bản nháp.");
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Không thể trích xuất lại PDF.");
    } finally { resolving.current = false; setBusy(false); }
  }

  return <section className="admin-card" aria-label="Rà soát PDF nguồn">
    <h3>{draft.title}</h3>
    {error && <p role="alert">{error}</p>}
    {status && <p role="status">{status}</p>}
    {pdfUrl ? <iframe className="pdf-frame" key={pdfPage ?? 0} style={{ height: "55vh" }}
      src={pdfPage ? `${pdfUrl}#page=${pdfPage}` : pdfUrl} title={`PDF chờ duyệt: ${draft.title}`} />
      : <p>Đang mở PDF nguồn đã kiểm tra mã băm…</p>}
    <p>Đối chiếu bản gốc và nội dung tác vụ trước khi ghi nhận xử lý. Đóng tác vụ chưa thay thế kiểm tra vị trí trích dẫn khi phê duyệt.</p>
    <p className="draft-dates">
      Ngày ban hành đọc được: {draft.detected_issue_date ?? "chưa đọc được"} · Ngày hiệu lực
      đọc được: {draft.detected_effective_from ?? "chưa đọc được"}. Phê duyệt nguồn đồng thời
      xác nhận hai ngày này.
      {draft.detected_effective_quote && <q> {draft.detected_effective_quote}</q>}
    </p>
    {contentCheckAvailable === false && <p>Chưa thể so sánh trùng theo lớp chữ của tài liệu này.</p>}
    {duplicates.length > 0 && <div>
      <p>Có thể trùng nội dung; hãy đối chiếu nguồn, chữ ký và phiên bản:</p>
      <ul>{duplicates.map((item) => <li key={item.document_version_id}>
        {[item.document_number, item.title].filter(Boolean).join(" · ")}
      </li>)}</ul>
    </div>}
    {canReextract && <button className="secondary-button" type="button" disabled={busy || !pdfUrl}
      onClick={() => void reextract()}>Trích xuất lại PDF gốc</button>}
    {canResolve && <label className="field-label">Ghi nhận đã kiểm tra / hướng xử lý
      <textarea value={note} onChange={(event) => setNote(event.target.value)} maxLength={2000} disabled={busy} />
    </label>}
    {tasks.map((task) => <div className="compact-admin-item" key={task.id}>
      <p>{pageTaskLabel(task) ?? REVIEW_REASON_LABELS[task.reason] ?? task.reason} · Mức rủi ro: {task.risk}</p>
      <OcrPageCheck task={task} onShowPage={setPdfPage} />
      {canResolve && <button className="secondary-button" type="button" disabled={busy || !note.trim() || !pdfUrl}
        onClick={() => void resolve(task)}>
        {task.page ? `Xác nhận chữ trang ${task.page.page_number} khớp bản gốc` : "Ghi nhận đã xử lý tác vụ"}
      </button>}
    </div>)}
    {tasks.length === 0 && <p>Không còn tác vụ mở trong danh sách đã tải.</p>}
  </section>;
}
