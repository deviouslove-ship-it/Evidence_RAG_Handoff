import { useEffect, useRef, useState } from "react";
import {
  approveAdminDraft, fetchAdminDocumentOriginal, fetchAdminDocumentPdf, getAdminDocument,
  patchAdminDocument, rejectAdminDraft, reprocessAdminDocument, submitAdminDraft, uploadAdminDraft,
} from "../api/client";
import type {
  AdminDocumentDetail, AdminDocumentMetadata, AdminDocumentPatch, AdminDocumentSummary,
  AuthorizedCategory,
} from "../types";
import { DraftReviewPanel } from "./DraftReviewPanel";
import {
  DOC_TYPE_LABELS, DOCUMENT_AVAILABILITY_LABELS, DOCUMENT_REVIEW_LABELS,
  SOURCE_FORMAT_LABELS, formatVnDate, splitLabel,
} from "./documentDisplay";
import { STATUS_LABELS } from "./effectivityLabels";

const METADATA_FIELDS = {
  title: "Trích yếu",
  document_number: "Số hiệu",
  doc_type: "Loại văn bản",
  issuing_body: "Cơ quan ban hành",
  publication_date: "Ngày ban hành",
  effective_from: "Ngày bắt đầu có hiệu lực",
  official_url: "Địa chỉ nguồn công bố",
};
const METADATA_KEYS = Object.keys(METADATA_FIELDS) as Array<keyof AdminDocumentMetadata>;
const METADATA_LIMITS = { title: 500, document_number: 120, issuing_body: 300, official_url: 2048 };
const HISTORY_TIME = new Intl.DateTimeFormat("vi-VN", { dateStyle: "short", timeStyle: "short" });
const HISTORY_LABELS: Record<string, string> = {
  "document.create_draft": "Nhập văn bản",
  "document.add_version": "Nhập tệp cho phiên bản mới",
  "document.submit_review": "Gửi thẩm định",
  "document.resolve_review_task": "Xử lý tác vụ thẩm định",
  "document.confirm_page_text": "Xác nhận nội dung trang",
  "document.approve_version": "Phê duyệt phiên bản",
  "document.reject_version": "Từ chối phiên bản",
  "document.reextract_source": "Trích xuất lại nguồn",
  "document.reprocess": "Xử lý lại văn bản",
  "document.edit": "Cập nhật hồ sơ",
  "document.suspend": "Tạm ngừng tra cứu",
  "document.resume": "Mở lại tra cứu",
  "document.delete": "Xóa mềm văn bản",
  "document.restore": "Khôi phục văn bản",
};

type EditMode = "metadata" | "ocr" | "reprocess" | "upload";

function metadataOf(detail: AdminDocumentDetail): AdminDocumentMetadata {
  const { title, doc_type, document_number, issuing_body, publication_date } = detail.document;
  return { title, doc_type, document_number, issuing_body, publication_date,
    effective_from: detail.effective_from ?? null, official_url: detail.official_url ?? null };
}

function metadataValue(key: keyof AdminDocumentMetadata, value: string | null): string {
  if (!value) return "Chưa có";
  if (key === "doc_type") return DOC_TYPE_LABELS[value] ?? "Văn bản khác";
  if (key === "publication_date" || key === "effective_from") return formatVnDate(value) ?? "Chưa có";
  return value;
}

function DocumentHistory({ history }: Pick<AdminDocumentDetail, "history">) {
  return <div className="document-detail-section">
    <h3>Lịch sử xử lý</h3>
    {history.length === 0 && <p className="evidence-meta">Chưa có nhật ký thao tác.</p>}
    <ul className="document-records">
      {history.map((entry, index) => {
        const date = new Date(entry.occurred_at);
        const changes = entry.metadata?.changes as
          Partial<Record<keyof AdminDocumentMetadata, { from: string | null; to: string | null }>> | undefined;
        const changedKeys = METADATA_KEYS.filter((key) => changes?.[key]);
        const pages = Array.isArray(entry.metadata?.pages)
          ? entry.metadata.pages.filter((page): page is number => typeof page === "number") : [];
        return <li className="compact-admin-item" key={`${entry.occurred_at}-${index}`}>
          <strong>{HISTORY_LABELS[entry.action] ?? "Cập nhật văn bản"}</strong>
          <span className="evidence-meta">
            {[Number.isNaN(date.valueOf()) ? null : HISTORY_TIME.format(date), entry.actor].filter(Boolean).join(" · ")}
          </span>
          {typeof entry.metadata?.reason === "string" && <span>{entry.metadata.reason}</span>}
          {pages.length > 0 && <span>Trang được xử lý · {pages.join(", ")}</span>}
          {changedKeys.length > 0 && <details>
            <summary>Thông tin đã thay đổi</summary>
            <ul>{changedKeys.map((key) => {
              const change = changes?.[key];
              return change && <li key={key}>
                <strong>{METADATA_FIELDS[key]}</strong> · {metadataValue(key, change.from)}
                {" → "}{metadataValue(key, change.to)}
              </li>;
            })}</ul>
          </details>}
        </li>;
      })}
    </ul>
  </div>;
}

export function AdminDocumentDetailPanel({ accessToken, item, categories, onBack, onChanged }: {
  accessToken: string;
  item: AdminDocumentSummary;
  categories: AuthorizedCategory[];
  onBack: () => void;
  onChanged: () => Promise<void>;
}) {
  const [detail, setDetail] = useState<AdminDocumentDetail>();
  const [versionId, setVersionId] = useState(item.version_id);
  const [pageNumber, setPageNumber] = useState(1);
  const [nodePage, setNodePage] = useState(1);
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const [status, setStatus] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState<EditMode>();
  const [showReview, setShowReview] = useState(false);
  const [metadata, setMetadata] = useState<AdminDocumentMetadata>();
  const [ocrText, setOcrText] = useState("");
  const [newSource, setNewSource] = useState<File>();
  const [preview, setPreview] = useState<string>();
  const [reviewNote, setReviewNote] = useState("");
  const [reviewCategories, setReviewCategories] = useState<string[]>();
  const heading = useRef<HTMLHeadingElement>(null);
  const editPanel = useRef<HTMLElement>(null);
  const mutating = useRef(false);
  const fileRequest = useRef<AbortController>();
  const previewUrl = useRef<string>();

  useEffect(() => { heading.current?.focus(); }, []);
  useEffect(() => { if (mode) editPanel.current?.focus(); }, [mode]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    getAdminDocument(accessToken, item.id, versionId, pageNumber, nodePage, controller.signal)
      .then((result) => { if (!controller.signal.aborted) setDetail(result); })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) {
          setDetail(undefined);
          setError(caught instanceof Error ? caught.message : "Không thể tải hồ sơ.");
        }
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [accessToken, item.id, nodePage, pageNumber, refresh, versionId]);

  useEffect(() => () => {
    fileRequest.current?.abort();
    if (previewUrl.current) URL.revokeObjectURL(previewUrl.current);
    previewUrl.current = undefined;
  }, [versionId]);

  const summary = detail?.document ?? item;
  const version = detail?.versions.find((entry) => entry.id === summary.version_id);
  const unavailable = busy || loading;

  function chooseVersion(nextId: string, nextPage = 1) {
    setMode(undefined);
    setMetadata(undefined);
    setNewSource(undefined);
    setShowReview(false);
    setReviewNote("");
    setReviewCategories(undefined);
    if (nextId !== versionId) setPreview(undefined);
    setLoading(true);
    setVersionId(nextId);
    setNodePage(1);
    setPageNumber(nextPage);
  }

  function navigatePage(next: number, kind: "ocr" | "nodes") {
    setError(undefined);
    setLoading(true);
    if (kind === "ocr") setPageNumber(next);
    else setNodePage(next);
  }

  async function runMutation(action: () => Promise<void>) {
    if (mutating.current || loading) return;
    mutating.current = true;
    setBusy(true);
    setError(undefined);
    setStatus(undefined);
    try {
      await action();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Không thể thực hiện thao tác.");
    } finally {
      mutating.current = false;
      setBusy(false);
    }
  }

  async function reload() {
    setLoading(true);
    setRefresh((value) => value + 1);
    await onChanged();
  }

  async function savePatch(patch: AdminDocumentPatch, keepPage: boolean) {
    await runMutation(async () => {
      const result = await patchAdminDocument(accessToken, item.id, summary.version_id, patch);
      chooseVersion(result.version_id, keepPage ? pageNumber : 1);
      setStatus("Đã lưu bản nháp. Gửi duyệt để thẩm định các thay đổi.");
      await reload();
    });
  }

  function saveMetadata() {
    if (!detail || !metadata) return;
    const previous = metadataOf(detail);
    const patch: AdminDocumentPatch = { revision: detail.revision };
    for (const key of METADATA_KEYS) {
      if (metadata[key] === previous[key]) continue;
      const next = metadata[key]?.trim() || null;
      if (next !== previous[key]) Object.assign(patch, { [key]: next });
    }
    if (Object.keys(patch).length === 1) {
      setMode(undefined);
      return;
    }
    void savePatch(patch, false);
  }

  async function uploadVersion() {
    if (!detail || !newSource) return;
    await runMutation(async () => {
      const form = new FormData();
      form.append("file", newSource);
      form.append("document_id", item.id);
      form.append("revision", String(detail.revision));
      for (const [key, value] of Object.entries(metadataOf(detail))) {
        if (value && key !== "effective_from") form.append(key, value);
      }
      const created = await uploadAdminDraft(accessToken, form);
      chooseVersion(created.document_version_id);
      setStatus(created.potential_duplicates?.length
        ? "Đã thêm bản nháp. Có thể trùng nội dung, cần đối chiếu nguồn khi thẩm định."
        : "Đã thêm phiên bản từ tệp mới. Bản nháp cần được thẩm định.");
      await reload();
    });
  }

  async function openSource(asPdf: boolean) {
    if (fileRequest.current || unavailable) return;
    const controller = new AbortController();
    fileRequest.current = controller;
    await runMutation(async () => {
      try {
        if (asPdf) {
          const blob = await fetchAdminDocumentPdf(accessToken, item.id, summary.version_id, controller.signal);
          if (controller.signal.aborted) return;
          if (previewUrl.current) URL.revokeObjectURL(previewUrl.current);
          previewUrl.current = URL.createObjectURL(blob);
          setPreview(previewUrl.current);
        } else {
          const file = await fetchAdminDocumentOriginal(accessToken, item.id, summary.version_id, controller.signal);
          if (controller.signal.aborted) return;
          const url = URL.createObjectURL(file.blob);
          const link = document.createElement("a");
          link.href = url;
          link.download = file.filename;
          document.body.appendChild(link);
          link.click();
          link.remove();
          window.setTimeout(() => URL.revokeObjectURL(url), 15000);
        }
      } catch (caught) {
        if (!controller.signal.aborted) throw caught;
      } finally {
        if (fileRequest.current === controller) fileRequest.current = undefined;
      }
    });
  }

  async function decide(approved: boolean) {
    if (!detail || !reviewNote.trim()) return;
    await runMutation(async () => {
      if (approved) {
        await approveAdminDraft(accessToken, summary.version_id, {
          category_ids: reviewCategories ?? detail.categories.map((category) => category.id),
          review_note: reviewNote.trim(), resolve_all_tasks: false, revision: detail.revision,
        });
      } else {
        await rejectAdminDraft(accessToken, summary.version_id, reviewNote.trim(), detail.revision);
      }
      setReviewNote("");
      setShowReview(false);
      setStatus(approved ? "Đã phê duyệt phiên bản." : "Đã từ chối phiên bản.");
      await reload();
    });
  }

  const categoryIds = reviewCategories ?? detail?.categories.map((category) => category.id) ?? [];
  const availableCategories = categories.length ? categories : detail?.categories ?? [];
  const ocr = detail?.page;
  const ocrEditable = ocr && (ocr.extraction_method === "local_ocr" || ocr.text_quality === "needs_ocr");
  const pageSize = detail?.node_page_size ?? 25;

  return <section className="admin-card admin-document-detail" aria-label="Hồ sơ văn bản">
    <button type="button" className="secondary-button" onClick={onBack} disabled={busy}>Về danh sách văn bản</button>
    <header className="document-detail-header">
      <p className="evidence-meta">{summary.document_number ?? "Chưa có số hiệu"}</p>
      <h2 tabIndex={-1} ref={heading}>{summary.title}</h2>
      <div className="capability-pills">
        <span className="compact-badge">{DOCUMENT_REVIEW_LABELS[summary.review_status]}</span>
        <span className="compact-badge">{STATUS_LABELS[summary.effectivity ?? "unknown"]}</span>
        <span className="compact-badge">{DOCUMENT_AVAILABILITY_LABELS[summary.availability]}</span>
        {version?.retired && <span className="compact-badge">Đã được thay bằng bản sửa</span>}
      </div>
    </header>
    {error && <div className="admin-banner error" role="alert">
      <p>{error}</p>
      <button className="secondary-button" type="button" disabled={unavailable} onClick={() => {
        setMode(undefined);
        setError(undefined);
        void reload();
      }}>Tải lại hồ sơ</button>
    </div>}
    {status && <p className="admin-banner status" role="status">{status}</p>}
    {loading && <p role="status">Đang tải hồ sơ văn bản…</p>}
    {detail && <div className="document-detail-content" aria-busy={loading}>
      <label className="field-label document-version">Phiên bản
        <select value={versionId} disabled={unavailable || Boolean(mode)} onChange={(event) => {
          setError(undefined);
          setStatus(undefined);
          chooseVersion(event.target.value);
        }}>
          {detail.versions.map((entry) => <option key={entry.id} value={entry.id}>
            Bản {entry.version_number} · {DOCUMENT_REVIEW_LABELS[entry.review_status]}
            {entry.retired ? " · Đã thay bằng bản sửa" : ""}
          </option>)}
        </select>
      </label>
      <div className="document-detail-section">
        <h3>Thông tin văn bản</h3>
        <dl className="document-metadata">
          {METADATA_KEYS.filter((key) => key !== "title" && key !== "document_number").map((key) =>
            <div key={key}>
              <dt>{METADATA_FIELDS[key]}</dt><dd>{metadataValue(key, metadataOf(detail)[key])}</dd>
            </div>)}
          <div><dt>Danh mục</dt><dd>{detail.categories.map((category) => category.name).join(", ") || "Chưa gắn"}</dd></div>
        </dl>
        {summary.can_edit && !mode && <div className="action-group">
          <button className="secondary-button" type="button" disabled={unavailable}
            onClick={() => { setMetadata(metadataOf(detail)); setMode("metadata"); }}>Sửa thông tin</button>
          <button className="secondary-button" type="button" disabled={unavailable}
            onClick={() => setMode("reprocess")}>Xử lý lại từ tệp gốc</button>
          {(summary.review_status === "approved" || summary.review_status === "rejected") &&
            <button className="secondary-button" type="button" disabled={unavailable}
              onClick={() => setMode("upload")}>Thêm phiên bản từ tệp mới</button>}
        </div>}
        {mode === "metadata" && metadata && <section className="document-confirmation" tabIndex={-1} ref={editPanel}>
          <h3>Sửa thông tin phiên bản</h3>
          <p>Thay đổi được lưu dưới trạng thái bản nháp và cần thẩm định lại.</p>
          <form className="form-stack" onSubmit={(event) => { event.preventDefault(); saveMetadata(); }}>
            <div className="compact-form-grid">
              {METADATA_KEYS.map((key) => <label className="field-label" key={key}>
                {METADATA_FIELDS[key]}
                {key === "doc_type" ? <select value={metadata[key]} disabled={unavailable}
                  onChange={(event) => setMetadata({ ...metadata, [key]: event.target.value })}>
                  {!DOC_TYPE_LABELS[metadata[key]] && <option value={metadata[key]}>Loại hiện tại</option>}
                  {Object.entries(DOC_TYPE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select> : <input value={metadata[key] ?? ""} required={key === "title"} disabled={unavailable}
                  maxLength={METADATA_LIMITS[key as keyof typeof METADATA_LIMITS]}
                  type={key === "publication_date" || key === "effective_from" ? "date" : key === "official_url" ? "url" : "text"}
                  onChange={(event) => setMetadata({ ...metadata, [key]: event.target.value })} />}
              </label>)}
            </div>
            <div className="action-group">
              <button className="primary-button" type="submit" disabled={unavailable || !metadata.title.trim()}>
                Lưu thông tin
              </button>
              <button className="secondary-button" type="button" disabled={busy} onClick={() => setMode(undefined)}>Hủy sửa</button>
            </div>
          </form>
        </section>}
        {mode === "reprocess" && <section className="document-confirmation" tabIndex={-1} ref={editPanel}>
          <h3>Xử lý lại từ tệp gốc</h3>
          <p>Hệ thống trích xuất lại nội dung để thẩm định. Kết quả có thể thay thế chữ OCR đã chỉnh trong bản nháp.</p>
          <div className="action-group">
            <button className="primary-button" type="button" disabled={unavailable} onClick={() => void runMutation(async () => {
              const next = await reprocessAdminDocument(accessToken, item.id, summary.version_id, detail.revision);
              chooseVersion(next.version_id);
              setStatus("Đã xử lý lại nguồn. Cần thẩm định bản nháp.");
              await reload();
            })}>Xác nhận xử lý lại</button>
            <button className="secondary-button" type="button" disabled={busy} onClick={() => setMode(undefined)}>Hủy thao tác</button>
          </div>
        </section>}
        {mode === "upload" && <section className="document-confirmation" tabIndex={-1} ref={editPanel}>
          <h3>Thêm phiên bản từ tệp mới</h3>
          <p>Hệ thống lưu tệp mới thành bản nháp của văn bản này và giữ lại các phiên bản trước.</p>
          <form className="form-stack" onSubmit={(event) => {
            event.preventDefault();
            void uploadVersion();
          }}>
            <label className="field-label">Tệp nguồn của phiên bản mới (PDF, Word, TXT)
              <input type="file" required disabled={unavailable} accept=".pdf,.docx,.doc,.txt"
                onChange={(event) => setNewSource(event.target.files?.[0])} />
            </label>
            <div className="action-group">
              <button className="primary-button" type="submit" disabled={unavailable || !newSource}>Tạo phiên bản nháp</button>
              <button className="secondary-button" type="button" disabled={busy}
                onClick={() => { setNewSource(undefined); setMode(undefined); }}>Hủy thao tác</button>
            </div>
          </form>
        </section>}
      </div>
      {summary.can_read ? <>
        <div className="document-detail-section">
          <h3>Tệp nguồn và nội dung OCR</h3>
          <p className="evidence-meta">{detail.original_filename ?? version?.original_filename}
            {version?.source_format && ` · ${SOURCE_FORMAT_LABELS[version.source_format] ?? "Tệp nguồn"}`}
            {` · ${detail.page_count} trang`}</p>
          <div className="action-group">
            <button className="secondary-button" type="button" disabled={unavailable}
              onClick={() => void openSource(false)}>Tải tệp gốc</button>
            <button className="secondary-button" type="button" disabled={unavailable}
              onClick={() => {
                if (preview) {
                  if (previewUrl.current) URL.revokeObjectURL(previewUrl.current);
                  previewUrl.current = undefined;
                  setPreview(undefined);
                } else void openSource(true);
              }}>{preview ? "Đóng bản xem PDF" : "Xem bản PDF"}</button>
          </div>
          {preview && <iframe className="pdf-frame document-source-preview" title="PDF đối chiếu nội dung"
            src={`${preview}#page=${pageNumber}`} />}
          {detail.page_count > 0 && <nav className="document-pagination" aria-label="Phân trang OCR">
            <button className="secondary-button" type="button" disabled={unavailable || Boolean(mode) || pageNumber <= 1}
              onClick={() => navigatePage(pageNumber - 1, "ocr")}>Trang OCR trước</button>
            <span>Trang {pageNumber}/{detail.page_count}</span>
            <button className="secondary-button" type="button"
              disabled={unavailable || Boolean(mode) || pageNumber >= detail.page_count}
              onClick={() => navigatePage(pageNumber + 1, "ocr")}>Trang OCR sau</button>
          </nav>}
          {ocr && <>
            <p className="evidence-meta">
              {ocr.extraction_method === "local_ocr" ? "Chữ OCR từ bản scan" : "Chữ trích xuất từ PDF"}
              {" · "}{ocr.reviewed ? "Đã đối chiếu trang" : ocr.text_quality !== "usable"
                ? "Cần đối chiếu với bản gốc" : "Chưa xác nhận riêng"}
              {Boolean(ocr.diagnostics?.flags?.length) && " · Có cảnh báo nhận dạng"}
            </p>
            {mode === "ocr" ? <section className="document-confirmation" tabIndex={-1} ref={editPanel}>
              <form className="form-stack" onSubmit={(event) => {
                event.preventDefault();
                void savePatch({ revision: detail.revision, ocr_page: {
                  page_number: ocr.page_number, text: ocrText,
                } }, true);
              }}>
                <label className="field-label">Chữ OCR đã đối chiếu
                  <textarea rows={10} value={ocrText} maxLength={50000} disabled={unavailable}
                    onChange={(event) => setOcrText(event.target.value)} />
                </label>
                <p>Trang đã sửa cần được thẩm định lại với bản gốc.</p>
                <div className="action-group">
                  <button className="primary-button" type="submit"
                    disabled={unavailable || ocrText === (ocr.text ?? "")}>Lưu sửa OCR</button>
                  <button className="secondary-button" type="button" disabled={busy} onClick={() => setMode(undefined)}>Hủy sửa</button>
                </div>
              </form>
            </section> : <details>
              <summary>Xem chữ trích xuất của trang {ocr.page_number}</summary>
              <pre className="ocr-page-text">{ocr.text || "(Chưa có chữ trích xuất)"}</pre>
            </details>}
            {summary.can_edit && ocrEditable && !mode && <button type="button" className="secondary-button"
              disabled={unavailable} onClick={() => { setOcrText(ocr.text ?? ""); setMode("ocr"); }}>Sửa chữ OCR</button>}
          </>}
        </div>
        <div className="document-detail-section">
          <h3>Điều, khoản và điểm</h3>
          <p className="evidence-meta">{detail.node_count} mục trích xuất</p>
          <ul className="document-records">
            {detail.nodes.map((node) => {
              const { label, heading: nodeHeading } = splitLabel(node.label ?? "", node.node_type, node.path);
              return <li key={node.id} className={`document-node document-node--${node.node_type}`}>
                <details>
                  <summary><strong>{label}</strong>{nodeHeading ? ` · ${nodeHeading}` : ""}
                    {node.page_start ? ` · trang ${node.page_start}${node.page_end && node.page_end !== node.page_start
                      ? `–${node.page_end}` : ""}` : ""}
                  </summary>
                  <pre className="ocr-page-text">{node.text}</pre>
                </details>
              </li>;
            })}
          </ul>
          {detail.node_count > pageSize && <nav className="document-pagination" aria-label="Phân trang điều khoản">
            <button className="secondary-button" type="button" disabled={unavailable || Boolean(mode) || nodePage <= 1}
              onClick={() => navigatePage(nodePage - 1, "nodes")}>Mục trước</button>
            <span>Trang {nodePage}/{Math.ceil(detail.node_count / pageSize)}</span>
            <button className="secondary-button" type="button"
              disabled={unavailable || Boolean(mode) || nodePage * pageSize >= detail.node_count}
              onClick={() => navigatePage(nodePage + 1, "nodes")}>Mục sau</button>
          </nav>}
          <p className="evidence-meta">Chỉ mục theo nghĩa: {detail.embedding.index_ready
            ? `${detail.embedding.indexed_nodes}/${detail.embedding.total_nodes} mục đã lập chỉ mục`
            : "Chưa có chỉ mục hoạt động"}</p>
        </div>
      </> : <p className="evidence-meta">Tài khoản này chỉ có quyền xem thông tin quản lý của văn bản.</p>}
      {(detail.can_review || detail.can_submit) && <div className="document-detail-section">
        <h3>Thẩm định phiên bản</h3>
        <p className="evidence-meta">{detail.open_review_tasks} tác vụ cần xử lý</p>
        {detail.can_submit && <button className="primary-button" type="button" disabled={unavailable || Boolean(mode)}
          onClick={() => void runMutation(async () => {
            await submitAdminDraft(accessToken, summary.version_id);
            setStatus("Đã gửi phiên bản sang hàng đợi thẩm định.");
            await reload();
          })}>Gửi duyệt</button>}
        {detail.can_review && <>
          <button className="secondary-button" type="button" disabled={unavailable || Boolean(mode)}
            aria-expanded={showReview} onClick={() => setShowReview(!showReview)}>
            {showReview ? "Thu phần thẩm định" : "Mở PDF và thẩm định"}
          </button>
          {showReview && <>
            <DraftReviewPanel draft={{
              document_id: summary.id, document_version_id: summary.version_id, title: summary.title,
              doc_type: summary.doc_type, document_number: summary.document_number, status: summary.review_status,
              sha256: "", page_count: detail.page_count, open_review_tasks: detail.open_review_tasks,
              detected_issue_date: summary.publication_date, detected_effective_from: detail.effective_from,
            }} accessToken={accessToken} canResolve canReextract={false} onUpdated={reload} />
            <label className="field-label">Ghi chú quyết định
              <textarea value={reviewNote} maxLength={2000} disabled={unavailable}
                onChange={(event) => setReviewNote(event.target.value)} />
            </label>
            <fieldset className="field-set" disabled={unavailable}>
              <legend>Danh mục áp dụng</legend>
              <div className="category-pills">
                {availableCategories.map((category) => <label className="fact-chip" key={category.id}>
                  <input type="checkbox" checked={categoryIds.includes(category.id)} onChange={(event) =>
                    setReviewCategories(event.target.checked
                      ? [...categoryIds, category.id] : categoryIds.filter((id) => id !== category.id))} />
                  <span>{category.name}</span>
                </label>)}
              </div>
            </fieldset>
            <div className="action-group">
              <button className="primary-button" type="button"
                disabled={unavailable || !reviewNote.trim() || !categoryIds.length || detail.open_review_tasks > 0}
                onClick={() => void decide(true)}>Phê duyệt phiên bản</button>
              <button className="secondary-button" type="button" disabled={unavailable || !reviewNote.trim()}
                onClick={() => void decide(false)}>Từ chối phiên bản</button>
            </div>
          </>}
        </>}
      </div>}
      <DocumentHistory history={detail.history} />
    </div>}
  </section>;
}
