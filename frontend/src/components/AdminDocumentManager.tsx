import { useEffect, useRef, useState } from "react";
import { changeAdminDocumentAvailability, listAdminDocuments, submitAdminDraft } from "../api/client";
import type {
  AdminDocumentAction, AdminDocumentList, AdminDocumentSummary, AuthorizedCategory,
} from "../types";
import { AdminDocumentDetailPanel } from "./AdminDocumentDetail";
import {
  DOC_TYPE_LABELS, DOCUMENT_AVAILABILITY_LABELS, DOCUMENT_REVIEW_LABELS, formatVnDate,
} from "./documentDisplay";
import { STATUS_LABELS } from "./effectivityLabels";

const ACTION_LABELS: Record<AdminDocumentAction | "submit", string> = {
  suspend: "Tạm ngừng",
  resume: "Mở lại tra cứu",
  delete: "Xóa mềm",
  restore: "Khôi phục văn bản",
  submit: "Gửi duyệt các bản đã chọn",
};

const CONFIRM_LABELS: Record<AdminDocumentAction | "submit", string> = {
  suspend: "Xác nhận tạm ngừng",
  resume: "Xác nhận mở lại",
  delete: "Xác nhận xóa mềm",
  restore: "Xác nhận khôi phục",
  submit: "Xác nhận gửi duyệt",
};

const ACTION_HELP: Record<AdminDocumentAction | "submit", string> = {
  suspend: "Văn bản sẽ được ẩn khỏi Hỏi đáp, Tìm kiếm và Diễn giải AI.",
  resume: "Các phiên bản đã được phê duyệt sẽ trở lại phạm vi tra cứu theo quyền.",
  delete: "Văn bản sẽ bị ẩn khỏi tra cứu. Tệp gốc và lịch sử vẫn được lưu.",
  restore: "Văn bản trở lại danh sách quản lý. Kiểm tra trạng thái tra cứu sau khi khôi phục.",
  submit: "Những bản nháp đã chọn sẽ chuyển sang hàng đợi thẩm định.",
};

const FILTERS: Array<{ key: string; label: string; type?: string; options?: Record<string, string> }> = [
  { key: "q", label: "Tìm theo số hiệu hoặc trích yếu", type: "search" },
  { key: "doc_type", label: "Loại văn bản", options: DOC_TYPE_LABELS },
  { key: "issuing_body", label: "Cơ quan ban hành" },
  { key: "date_from", label: "Ban hành từ ngày", type: "date" },
  { key: "date_to", label: "Ban hành đến ngày", type: "date" },
  { key: "review_status", label: "Trạng thái xử lý", options: DOCUMENT_REVIEW_LABELS },
  { key: "effectivity", label: "Hiệu lực pháp lý", options: STATUS_LABELS },
  { key: "availability", label: "Trạng thái tra cứu", options: DOCUMENT_AVAILABILITY_LABELS },
];

export function AdminDocumentManager({ accessToken, categories, canCurate, isSysAdmin, onChanged }: {
  accessToken: string;
  categories: AuthorizedCategory[];
  canCurate: boolean;
  isSysAdmin: boolean;
  onChanged: () => Promise<void>;
}) {
  const [input, setInput] = useState<Record<string, string>>({});
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<AdminDocumentList>();
  const [refresh, setRefresh] = useState(0);
  const [selected, setSelected] = useState<string[]>([]);
  const [open, setOpen] = useState<AdminDocumentSummary>();
  const [pending, setPending] = useState<AdminDocumentAction | "submit">();
  const [reason, setReason] = useState("");
  const [status, setStatus] = useState<string>();
  const [error, setError] = useState<string>();
  const [loadError, setLoadError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const mutating = useRef(false);
  const confirmInput = useRef<HTMLInputElement>(null);
  const cancelButton = useRef<HTMLButtonElement>(null);
  const confirmationOrigin = useRef<HTMLButtonElement>();
  const listHeading = useRef<HTMLHeadingElement>(null);
  const actionSummary = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    setResult(undefined);
    setLoadError(undefined);
    listAdminDocuments(accessToken, filters, page, controller.signal).then((next) => {
      if (controller.signal.aborted) return;
      const lastPage = Math.max(1, Math.ceil(next.total / next.page_size));
      if (page > lastPage) setPage(lastPage);
      else setResult(next);
    }).catch((caught: unknown) => {
      if (!controller.signal.aborted) {
        setLoadError(caught instanceof Error ? caught.message : "Không thể tải danh sách văn bản.");
      }
    });
    return () => controller.abort();
  }, [accessToken, filters, page, refresh]);

  useEffect(() => {
    if (pending === "submit") cancelButton.current?.focus();
    else if (pending) confirmInput.current?.focus();
  }, [pending]);

  const items = result?.items ?? [];
  const selectedItems = items.filter((item) => selected.includes(item.id));
  const actions: Array<AdminDocumentAction | "submit"> = [];
  if (selectedItems.length) {
    if (isSysAdmin) {
      if (selectedItems.every((item) => item.availability === "active")) actions.push("suspend");
      if (selectedItems.every((item) => item.availability === "suspended")) actions.push("resume");
      if (selectedItems.every((item) => item.availability !== "deleted")) actions.push("delete");
      if (selectedItems.every((item) => item.availability === "deleted")) actions.push("restore");
    }
    if (canCurate && selectedItems.every((item) =>
      item.can_edit && item.availability !== "deleted" && item.review_status === "draft")) {
      actions.push("submit");
    }
  }
  const eligible = items.filter((item) => isSysAdmin || (canCurate && item.can_edit
    && item.availability !== "deleted" && item.review_status === "draft"));

  function applyFilters(next: Record<string, string>) {
    setStatus(undefined);
    if (next.date_from && next.date_to && next.date_from > next.date_to) {
      setError("Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.");
      return;
    }
    setSelected([]);
    setError(undefined);
    setPending(undefined);
    setPage(1);
    setFilters(next);
  }

  function turnPage(next: number) {
    setSelected([]);
    setPending(undefined);
    setPage(next);
    listHeading.current?.focus();
  }

  async function refreshDocuments() {
    setRefresh((value) => value + 1);
    await onChanged();
  }

  async function executeSelection() {
    if (!pending || mutating.current || !actions.includes(pending)) return;
    mutating.current = true;
    setBusy(true);
    setStatus(undefined);
    setError(undefined);
    try {
      if (pending === "submit") {
        const failed: string[] = [];
        const messages: string[] = [];
        for (const item of selectedItems) {
          try {
            await submitAdminDraft(accessToken, item.version_id);
          } catch (caught) {
            failed.push(item.id);
            messages.push(`${item.document_number || item.title}: ${caught instanceof Error
              ? caught.message : "Không thể gửi duyệt."}`);
          }
        }
        setSelected(failed);
        setStatus(`Đã gửi duyệt ${selectedItems.length - failed.length}/${selectedItems.length} bản nháp.`);
        if (messages.length) setError(messages.join(" "));
      } else {
        if (!reason.trim()) return;
        const { updated } = await changeAdminDocumentAvailability(
          accessToken, selectedItems.map((item) => item.id), pending, reason.trim(),
        );
        setSelected([]);
        setStatus(`Đã cập nhật ${updated} văn bản.`);
      }
      setPending(undefined);
      await refreshDocuments();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Không thể thực hiện thao tác.");
    } finally {
      setBusy(false);
      mutating.current = false;
    }
  }

  useEffect(() => { if (status) actionSummary.current?.focus(); }, [status]);

  if (open) return <AdminDocumentDetailPanel
    key={open.id} accessToken={accessToken} item={open} categories={categories}
    onChanged={refreshDocuments}
    onBack={() => {
      setOpen(undefined);
      requestAnimationFrame(() => listHeading.current?.focus());
    }}
  />;

  return <section className="admin-card admin-document-manager" aria-label="Kho văn bản quản trị">
    <h2 tabIndex={-1} ref={listHeading}>Quản lý văn bản</h2>
    <p>Tra cứu toàn bộ hồ sơ đã nhập trong phạm vi quản trị, xem từng phiên bản và xử lý trước khi phát hành.</p>
    <form aria-label="Lọc văn bản" className="form-stack" onSubmit={(event) => {
      event.preventDefault();
      applyFilters({ ...input });
    }}>
      <div className="document-filter-grid">
        {FILTERS.map(({ key, label, type, options }) => <label className="field-label" key={key}>
          {label}
          {options ? <select value={input[key] ?? ""} disabled={busy}
            onChange={(event) => setInput({ ...input, [key]: event.target.value })}>
            <option value="">{key === "availability" ? "Chưa xóa mềm" : "Tất cả"}</option>
            {Object.entries(options).map(([value, name]) => <option key={value} value={value}>{name}</option>)}
          </select> : <input type={type ?? "text"} value={input[key] ?? ""} maxLength={200} disabled={busy}
            onChange={(event) => setInput({ ...input, [key]: event.target.value })} />}
        </label>)}
      </div>
      <div className="action-group">
        <button className="primary-button" disabled={busy} type="submit">Áp dụng bộ lọc</button>
        <button className="secondary-button" disabled={busy} type="button"
          onClick={() => { setInput({}); applyFilters({}); }}>Bỏ bộ lọc</button>
      </div>
    </form>
    <hr className="section-divider" />
    {status && <p ref={actionSummary} tabIndex={-1} className="admin-banner status" role="status">{status}</p>}
    {error && <p className="admin-banner error" role="alert">{error}</p>}
    {loadError && <p className="admin-banner error" role="alert">{loadError}</p>}
    {!result && !loadError && <p role="status">Đang tải danh sách văn bản…</p>}
    {loadError && <button className="secondary-button" type="button"
      onClick={() => setRefresh((value) => value + 1)}>Tải lại danh sách</button>}
    {result && <>
      <div className="compact-admin-row document-bulk-toolbar">
        <strong>{result.total} văn bản</strong>
        {eligible.length > 0 && <label className="checkbox-row">
          <input type="checkbox" checked={eligible.every((item) => selected.includes(item.id))}
            disabled={busy || Boolean(pending)} onChange={(event) =>
              setSelected(event.target.checked ? eligible.map((item) => item.id) : [])} />
          Chọn tất cả mục có thể thao tác trên trang
        </label>}
      </div>
      {selectedItems.length > 0 && <div className="document-bulk-toolbar">
        <p>Đã chọn {selectedItems.length} văn bản trên trang.</p>
        <div className="action-group">
          {actions.map((action) => <button className="secondary-button" key={action} type="button" disabled={Boolean(pending)}
            onClick={(event) => {
              confirmationOrigin.current = event.currentTarget;
              setReason("");
              setPending(action);
            }}>{ACTION_LABELS[action]}</button>)}
          {!actions.length && <p>Hãy chọn các văn bản có cùng trạng thái để thao tác.</p>}
        </div>
      </div>}
      {pending && <form className="document-confirmation form-stack" onSubmit={(event) => {
        event.preventDefault();
        void executeSelection();
      }} aria-label={CONFIRM_LABELS[pending]}>
        <strong>{ACTION_LABELS[pending]} · {selectedItems.length} văn bản</strong>
        <p>{ACTION_HELP[pending]}</p>
        {pending !== "submit" && <label className="field-label">Lý do thao tác
          <input ref={confirmInput} value={reason} onChange={(event) => setReason(event.target.value)}
            maxLength={2000} disabled={busy} required />
        </label>}
        <div className="action-group">
          <button className="primary-button" type="submit"
            disabled={busy || (pending !== "submit" && !reason.trim())}>{CONFIRM_LABELS[pending]}</button>
          <button className="secondary-button" ref={cancelButton} type="button" disabled={busy}
            onClick={() => {
              setPending(undefined);
              requestAnimationFrame(() => confirmationOrigin.current?.focus());
            }}>Hủy thao tác</button>
        </div>
      </form>}
      {items.length === 0 && <p>Không tìm thấy văn bản theo bộ lọc.</p>}
      <ul className="document-records">
        {items.map((item) => <li key={item.id} className="document-record">
          {eligible.includes(item) && <input aria-label={`Chọn ${item.document_number || item.title}`}
            type="checkbox" checked={selected.includes(item.id)} disabled={busy || Boolean(pending)}
            onChange={(event) => setSelected((previous) => event.target.checked
              ? [...previous, item.id] : previous.filter((id) => id !== item.id))} />}
          <div className="compact-admin-main">
            <strong>{item.title}</strong>
            <span className="compact-admin-sub">
              {[item.document_number, DOC_TYPE_LABELS[item.doc_type] ?? "Văn bản khác",
                item.issuing_body, formatVnDate(item.publication_date)].filter(Boolean).join(" · ")}
            </span>
            <div className="capability-pills">
              <span className="compact-badge">{DOCUMENT_REVIEW_LABELS[item.review_status]}</span>
              <span className="compact-badge">{STATUS_LABELS[item.effectivity ?? "unknown"]}</span>
              {item.availability !== "active" &&
                <span className="compact-badge">{DOCUMENT_AVAILABILITY_LABELS[item.availability]}</span>}
            </div>
          </div>
          <button type="button" className="secondary-button" disabled={busy || Boolean(pending)}
            aria-label={`Chi tiết ${item.document_number || item.title}`} onClick={() => setOpen(item)}>Chi tiết</button>
        </li>)}
      </ul>
      {result.total > result.page_size && <nav className="document-pagination" aria-label="Phân trang văn bản">
        <button type="button" className="secondary-button" disabled={page === 1 || busy || Boolean(pending)}
          onClick={() => turnPage(page - 1)}>Trang trước</button>
        <span>Trang {page}/{Math.ceil(result.total / result.page_size)}</span>
        <button type="button" className="secondary-button"
          disabled={page * result.page_size >= result.total || busy || Boolean(pending)}
          onClick={() => turnPage(page + 1)}>Trang sau</button>
      </nav>}
    </>}
  </section>;
}
