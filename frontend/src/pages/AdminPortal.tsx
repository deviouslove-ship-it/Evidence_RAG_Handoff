import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiRequestError,
  approveAdminDraft,
  changePassword,
  createAdminCategory,
  deleteAdminCategory,
  deleteAdminUser,
  getAdminModelRegistry,
  listAdminAuditEvents,
  listAdminCategories,
  listAdminDrafts,
  listAdminUsers,
  rejectAdminDraft,
  submitAdminDraft,
  uploadAdminDraft,
  updateAdminCategory,
  upsertAdminUser,
} from "../api/client";
import type {
  AdminUserItem,
  AuditEventsResponse,
  AuthorizedCategory,
  ModelRegistryState,
  PdfDraftListItem,
  UserInfo,
} from "../types";
import { DraftReviewPanel } from "../components/DraftReviewPanel";
import { EffectivityReviewPanel } from "../components/EffectivityReviewPanel";
import { AssignmentsPanel } from "../components/ai/AssignmentsPanel";
import { ModelProfilesPanel } from "../components/ai/ModelProfilesPanel";
import { EmbeddingManager } from "../components/EmbeddingManager";
import { LabelReviewPanel } from "../components/LabelReviewPanel";

interface AdminPortalProps {
  accessToken: string;
  currentUser: UserInfo;
}

const ALL_ROLES = ["USER", "CURATOR", "REVIEWER", "SYS_ADMIN", "AUDITOR"] as const;

const ROLE_LABELS: Record<string, string> = {
  USER: "Người tra cứu (USER)",
  CURATOR: "Biên tập nguồn (CURATOR)",
  REVIEWER: "Thẩm định nguồn (REVIEWER)",
  SYS_ADMIN: "Quản trị hệ thống (SYS_ADMIN)",
  AUDITOR: "Kiểm toán (AUDITOR)",
};

const DRAFT_STATUS_LABELS: Record<string, string> = {
  draft: "Bản nháp mới",
  pending_review: "Chờ thẩm định",
  approved: "Đã phê duyệt",
  rejected: "Đã từ chối",
};

const MAX_PDF_BATCH = 50;

// Same codes the Search page filters on; free text here made filtering unreliable.
const DOC_TYPE_OPTIONS = [
  { value: "law", label: "Luật" },
  { value: "decree", label: "Nghị định" },
  { value: "circular", label: "Thông tư" },
  { value: "joint_circular", label: "Thông tư liên tịch" },
  { value: "directive", label: "Chỉ thị" },
  { value: "decision", label: "Quyết định" },
  { value: "other", label: "Văn bản khác" },
];

interface BatchPdf {
  id: number;
  file: File;
  title: string;
  docType: string;
  docNumber: string;
  officialUrl: string;
  state: "ready" | "uploading" | "success" | "failed" | "unknown";
  message?: string;
}

function draftForm(file: File, title: string, type: string, number: string, url: string): FormData {
  const form = new FormData();
  form.append("file", file);
  form.append("title", title.trim());
  form.append("doc_type", type.trim());
  if (number.trim()) form.append("document_number", number.trim());
  if (url.trim()) form.append("official_url", url.trim());
  return form;
}

function draftOutcome(created: Awaited<ReturnType<typeof uploadAdminDraft>>): string {
  const duplicates = created.potential_duplicates ?? [];
  const notice = duplicates.length > 0
    ? `Có thể trùng nội dung với: ${duplicates.map((item) =>
      [item.document_number, item.title].filter(Boolean).join(" · ")).join("; ")}. Hãy đối chiếu nguồn và phiên bản.`
    : created.content_check_available
      ? "Chưa phát hiện nội dung trùng trong các tài liệu đã lập dấu vân tay."
      : "Chưa thể so sánh nội dung văn bản; cần kiểm tra bản scan hoặc lớp chữ. Trùng file vẫn được kiểm tra.";
  return `Đã lưu nháp (${created.page_count} trang, ${created.node_count} đoạn). Mã băm: ${created.sha256.slice(0, 12)}… ${notice}`;
}

export function AdminPortal({ accessToken, currentUser }: AdminPortalProps) {
  const canCurate = currentUser.roles.includes("CURATOR");
  const canReview = currentUser.roles.includes("REVIEWER");
  const isSysAdmin = currentUser.roles.includes("SYS_ADMIN");
  const isAuditor = currentUser.roles.includes("AUDITOR") || isSysAdmin;

  const [tab, setTab] = useState<"documents" | "effectivity" | "categories" | "users" | "ai_audit">(
    canCurate || canReview ? "documents" : isSysAdmin ? "categories" : "ai_audit",
  );
  const [drafts, setDrafts] = useState<PdfDraftListItem[]>([]);
  const [categories, setCategories] = useState<AuthorizedCategory[]>([]);
  const [users, setUsers] = useState<AdminUserItem[]>([]);
  const [registry, setRegistry] = useState<ModelRegistryState>({ profiles: [], routes: [] });
  const [audit, setAudit] = useState<AuditEventsResponse>();
  const [statusMsg, setStatusMsg] = useState<string>();
  const [errorMsg, setErrorMsg] = useState<string>();
  const [busy, setBusy] = useState(false);
  const mutationPending = useRef(false);

  // Upload draft state
  const [docTitle, setDocTitle] = useState("");
  const [docType, setDocType] = useState("decree");
  const [docNumber, setDocNumber] = useState("");
  const [officialUrl, setOfficialUrl] = useState("");
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [batchFiles, setBatchFiles] = useState<BatchPdf[]>([]);
  const [uploadProgress, setUploadProgress] = useState<{ current: number; total: number }>();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const uploadController = useRef<AbortController | null>(null);
  const uploadEpoch = useRef(0);

  // Review state
  const [reviewCategoryIds, setReviewCategoryIds] = useState<string[]>([]);
  const [reviewNote, setReviewNote] = useState("");
  const [reviewDraft, setReviewDraft] = useState<PdfDraftListItem>();

  // Category state
  const [catCode, setCatCode] = useState("");
  const [catName, setCatName] = useState("");
  const [catRemote, setCatRemote] = useState(false);
  const [editingCategoryId, setEditingCategoryId] = useState<string>();

  // User state
  const [uName, setUName] = useState("");
  const [uDisplay, setUDisplay] = useState("");
  const [uPass, setUPass] = useState("");
  const [uRoles, setURoles] = useState<string[]>(["USER"]);
  const [uCats, setUCats] = useState<string[]>([]);
  const [uReviewCats, setUReviewCats] = useState<string[]>([]);
  const [uMustChange, setUMustChange] = useState(true);
  const [uDisabled, setUDisabled] = useState(false);
  const [uRemoteAi, setURemoteAi] = useState(false);

  // Self password change state
  const [myCurrentPass, setMyCurrentPass] = useState("");
  const [myNewPass, setMyNewPass] = useState("");
  const [myConfirmPass, setMyConfirmPass] = useState("");

  // AI Registry state
  const [aiSubTab, setAiSubTab] = useState<"profiles" | "routes" | "embedding" | "audit">(
    isSysAdmin ? "profiles" : "audit",
  );
  const refreshAll = useCallback(async () => {
    setErrorMsg(undefined);
    try {
      if (canCurate || canReview || isSysAdmin) {
        const cats = await listAdminCategories(accessToken);
        setCategories(cats);
      }
      if (canCurate || canReview) {
        setDrafts(await listAdminDrafts(accessToken));
      }
      if (isSysAdmin) {
        setUsers(await listAdminUsers(accessToken));
        setRegistry(await getAdminModelRegistry(accessToken));
      }
      if (isAuditor) {
        setAudit(await listAdminAuditEvents(accessToken));
      }
    } catch (caught) {
      setErrorMsg(caught instanceof Error ? caught.message : "Không thể tải dữ liệu quản trị.");
    }
  }, [accessToken, canCurate, canReview, isAuditor, isSysAdmin]);

  useEffect(() => {
    void refreshAll();
  }, [refreshAll]);

  useEffect(() => {
    setPdfFile(null);
    setBatchFiles([]);
    setUploadProgress(undefined);
    setDocTitle("");
    setDocNumber("");
    setOfficialUrl("");
    if (fileInputRef.current) fileInputRef.current.value = "";
    return () => {
      uploadEpoch.current += 1;
      uploadController.current?.abort();
      uploadController.current = null;
    };
  }, [accessToken]);

  function choosePdfFiles(event: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    setErrorMsg(undefined);
    setStatusMsg(undefined);
    if (files.length > MAX_PDF_BATCH) {
      setPdfFile(null);
      setBatchFiles([]);
      event.target.value = "";
      setErrorMsg(`Chọn tối đa ${MAX_PDF_BATCH} tệp trong mỗi lần nhập.`);
      return;
    }
    if (files.length <= 1) {
      setBatchFiles([]);
      setPdfFile(files[0] ?? null);
      return;
    }
    setPdfFile(null);
    setBatchFiles(files.map((file, id) => ({
      id, file, title: file.name.replace(/\.(pdf|docx?|txt)$/i, "").trim() || `Tệp ${id + 1}`,
      docType, docNumber: "", officialUrl: "", state: "ready",
    })));
  }

  function updateBatchFile(id: number, update: Partial<BatchPdf>) {
    setBatchFiles((items) => items.map((item) => item.id === id ? { ...item, ...update } : item));
  }

  async function handleUploadDraft() {
    if (!pdfFile || !docTitle.trim()) return;
    setErrorMsg(undefined);
    setStatusMsg(undefined);
    try {
      const created = await uploadAdminDraft(
        accessToken, draftForm(pdfFile, docTitle, docType, docNumber, officialUrl),
      );
      setStatusMsg(draftOutcome(created));
      setDocTitle("");
      setDocNumber("");
      setOfficialUrl("");
      setPdfFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      await refreshAll();
    } catch (caught) {
      setErrorMsg(caught instanceof Error ? caught.message : "Không thể tải bản nháp.");
    }
  }

  async function handleUploadBatch() {
    const pending = batchFiles.filter((item) => item.state !== "success");
    if (pending.length === 0) return;
    if (pending.some((item) => !item.title.trim() || !item.docType.trim())) {
      setErrorMsg("Hãy điền tiêu đề và loại văn bản cho từng tệp.");
      return;
    }
    setErrorMsg(undefined);
    setStatusMsg(undefined);
    const controller = new AbortController();
    uploadController.current = controller;
    const epoch = uploadEpoch.current;
    let processed = 0;
    let succeeded = 0;
    let stopped = false;
    try {
      for (let index = 0; index < pending.length; index += 1) {
        if (controller.signal.aborted || uploadEpoch.current !== epoch) break;
        const item = pending[index];
        setUploadProgress({ current: index + 1, total: pending.length });
        updateBatchFile(item.id, { state: "uploading", message: "Đang nhập tệp…" });
        try {
          const result = await uploadAdminDraft(
            accessToken,
            draftForm(item.file, item.title, item.docType, item.docNumber, item.officialUrl),
            { signal: controller.signal },
          );
          if (uploadEpoch.current !== epoch) return;
          processed += 1;
          succeeded += 1;
          updateBatchFile(item.id, { state: "success", message: draftOutcome(result) });
        } catch (caught) {
          if (uploadEpoch.current !== epoch) return;
          processed += 1;
          const uncertain = controller.signal.aborted || !(caught instanceof ApiRequestError) ||
            caught.status === 408 || caught.status >= 500;
          const message = uncertain
            ? "Chưa xác nhận kết quả; tệp có thể đã được lưu. Hãy kiểm tra hàng đợi trước khi thử lại."
            : caught instanceof Error ? caught.message : "Không thể tải bản nháp.";
          updateBatchFile(item.id, { state: uncertain ? "unknown" : "failed", message });
          if (uncertain || caught instanceof ApiRequestError && [401, 403].includes(caught.status)) {
            stopped = true;
            break;
          }
        }
      }
      if (uploadEpoch.current !== epoch) return;
      if (controller.signal.aborted) stopped = true;
      setStatusMsg(`Đã xử lý ${processed}/${pending.length} tệp; lưu ${succeeded} bản nháp.${stopped ? " Đã dừng các tệp còn lại." : ""}`);
      await refreshAll();
    } finally {
      if (uploadController.current === controller) uploadController.current = null;
      if (uploadEpoch.current === epoch) setUploadProgress(undefined);
    }
  }

  async function handleSubmitDraft(versionId: string) {
    setErrorMsg(undefined);
    try {
      await submitAdminDraft(accessToken, versionId);
      setStatusMsg("Đã chuyển bản nháp sang hàng đợi chờ thẩm định.");
      await refreshAll();
    } catch (caught) {
      setErrorMsg(caught instanceof Error ? caught.message : "Không thể gửi duyệt.");
    }
  }

  async function handleApproveDraft(versionId: string) {
    setErrorMsg(undefined);
    if (reviewCategoryIds.length === 0) {
      setErrorMsg("Chọn ít nhất một danh mục thẩm định trước khi phê duyệt.");
      return;
    }
    try {
      const res = await approveAdminDraft(accessToken, versionId, {
        category_ids: reviewCategoryIds,
        review_note: reviewNote,
        resolve_all_tasks: false,
      });
      setStatusMsg(`Đã phê duyệt nguồn (${res.approved_nodes} điều/khoản có hiệu lực tra cứu).`);
      await refreshAll();
    } catch (caught) {
      setErrorMsg(caught instanceof Error ? caught.message : "Không thể phê duyệt.");
    }
  }

  async function handleRejectDraft(versionId: string) {
    setErrorMsg(undefined);
    try {
      await rejectAdminDraft(accessToken, versionId, reviewNote || "Không đạt yêu cầu kiểm định.");
      setStatusMsg("Đã từ chối phiên bản tài liệu.");
      await refreshAll();
    } catch (caught) {
      setErrorMsg(caught instanceof Error ? caught.message : "Không thể từ chối.");
    }
  }

  async function handleCreateCategory(event: React.FormEvent) {
    event.preventDefault();
    setErrorMsg(undefined);
    setStatusMsg(undefined);
    try {
      const saveCategory = editingCategoryId
        ? (payload: { code: string; name: string; remote_processing_allowed: boolean }) => updateAdminCategory(accessToken, editingCategoryId, payload)
        : (payload: { code: string; name: string; remote_processing_allowed: boolean }) => createAdminCategory(accessToken, payload);
      await saveCategory({
        code: catCode.trim(),
        name: catName.trim(),
        remote_processing_allowed: catRemote,
      });
      setCatCode("");
      setCatName("");
      setCatRemote(false);
      setEditingCategoryId(undefined);
      setStatusMsg("Đã lưu danh mục tài liệu.");
      await refreshAll();
    } catch (caught) {
      setErrorMsg(caught instanceof Error ? caught.message : "Không thể lưu danh mục.");
    }
  }

  async function handleDeleteCategory(categoryId: string, categoryName: string) {
    if (!window.confirm(`Xóa danh mục "${categoryName}" và thu hồi quyền truy cập danh mục này của mọi tài khoản?`)) return;
    setErrorMsg(undefined);
    setStatusMsg(undefined);
    try {
      await deleteAdminCategory(accessToken, categoryId);
      setStatusMsg(`Đã xóa danh mục "${categoryName}".`);
      await refreshAll();
    } catch (caught) {
      setErrorMsg(caught instanceof Error ? caught.message : "Không thể xóa danh mục.");
    }
  }

  async function handleUpsertUser(event: React.FormEvent) {
    event.preventDefault();
    setErrorMsg(undefined);
    setStatusMsg(undefined);
    const existing = users.some((u) => u.username.toLowerCase() === uName.trim().toLowerCase());
    if (!existing && uPass.trim().length < 12) {
      setErrorMsg("Tài khoản tạo mới bắt buộc có mật khẩu khởi tạo tối thiểu 12 ký tự.");
      return;
    }
    if (uPass.trim().length > 0 && uPass.trim().length < 12) {
      setErrorMsg("Mật khẩu đặt lại phải có tối thiểu 12 ký tự.");
      return;
    }
    try {
      await upsertAdminUser(accessToken, {
        username: uName.trim(),
        display_name: uDisplay.trim(),
        password: uPass || undefined,
        roles: uRoles,
        category_ids: uCats,
        review_category_ids: uRoles.includes("REVIEWER") ? uReviewCats : [],
        must_change_password: uMustChange,
        disabled: uDisabled,
        remote_ai_allowed: uRemoteAi,
      });
      setStatusMsg(
        uPass
          ? `Đã lưu tài khoản "${uName.trim()}" và cập nhật mật khẩu mới.`
          : `Đã cập nhật thông tin và phân quyền tài khoản "${uName.trim()}".`,
      );
      setUName("");
      setUDisplay("");
      setUPass("");
      setUDisabled(false);
      setURemoteAi(false);
      await refreshAll();
    } catch (caught) {
      setErrorMsg(caught instanceof Error ? caught.message : "Không thể lưu tài khoản.");
    }
  }

  async function handleToggleUserLock(u: AdminUserItem) {
    setErrorMsg(undefined);
    setStatusMsg(undefined);
    try {
      await upsertAdminUser(accessToken, {
        username: u.username,
        display_name: u.display_name,
        roles: u.roles,
        category_ids: u.category_ids,
        review_category_ids: u.review_category_ids ?? [],
        must_change_password: u.must_change_password,
        disabled: !u.disabled,
        remote_ai_allowed: u.remote_ai_allowed ?? false,
      });
      setStatusMsg(
        !u.disabled
          ? `Đã khóa tài khoản "${u.username}".`
          : `Đã mở khóa tài khoản "${u.username}".`,
      );
      await refreshAll();
    } catch (caught) {
      setErrorMsg(caught instanceof Error ? caught.message : "Không thể đổi trạng thái khóa tài khoản.");
    }
  }

  async function handleDeleteUser(userId: string, username: string) {
    if (!window.confirm(`Vô hiệu hóa tài khoản "${username}" và thu hồi các phiên đăng nhập đang hoạt động?`)) return;
    setErrorMsg(undefined);
    setStatusMsg(undefined);
    try {
      await deleteAdminUser(accessToken, userId);
      if (uName.trim().toLowerCase() === username.toLowerCase()) {
        setUName("");
        setUDisplay("");
        setUPass("");
      }
      setStatusMsg(`Đã vô hiệu hóa tài khoản "${username}"; lịch sử kiểm toán được giữ lại.`);
      await refreshAll();
    } catch (caught) {
      setErrorMsg(caught instanceof Error ? caught.message : "Không thể vô hiệu hóa tài khoản.");
    }
  }

  async function handleChangeOwnPassword(event: React.FormEvent) {
    event.preventDefault();
    setErrorMsg(undefined);
    setStatusMsg(undefined);
    if (myNewPass.length < 12) {
      setErrorMsg("Mật khẩu mới phải có tối thiểu 12 ký tự.");
      return;
    }
    if (myNewPass !== myConfirmPass) {
      setErrorMsg("Xác nhận mật khẩu mới không khớp.");
      return;
    }
    try {
      await changePassword(accessToken, myCurrentPass, myNewPass);
      setMyCurrentPass("");
      setMyNewPass("");
      setMyConfirmPass("");
      setStatusMsg("Đã đổi mật khẩu cá nhân thành công.");
    } catch (caught) {
      setErrorMsg(caught instanceof Error ? caught.message : "Không thể đổi mật khẩu cá nhân.");
    }
  }

  async function runMutation(action: () => Promise<void>) {
    if (mutationPending.current) return;
    mutationPending.current = true;
    setBusy(true);
    try { await action(); }
    finally { mutationPending.current = false; setBusy(false); }
  }

  return (
    <div className="admin-portal" aria-label="Cổng quản trị Admin Portal">
      <header className="admin-header">
        <div>
          <h1>Cổng quản trị hệ thống</h1>
          <p>Quản lý kho văn bản nguồn, danh mục phân quyền, tài khoản và nhật ký kiểm toán chuỗi băm.</p>
        </div>
        <nav className="admin-subnav" aria-label="Phân khu quản trị">
          {(canCurate || canReview) && (
            <button
              className={tab === "documents" ? "primary-button" : "secondary-button"}
              onClick={() => setTab("documents")}
              type="button"
            >
              Tài liệu & Duyệt nguồn ({drafts.length})
            </button>
          )}
          {canReview && (
            <button
              className={tab === "effectivity" ? "primary-button" : "secondary-button"}
              onClick={() => setTab("effectivity")}
              type="button"
            >
              Hiệu lực
            </button>
          )}
          {isSysAdmin && (
            <button
              className={tab === "categories" ? "primary-button" : "secondary-button"}
              onClick={() => setTab("categories")}
              type="button"
            >
              Danh mục ({categories.length})
            </button>
          )}
          {isSysAdmin && (
            <button
              className={tab === "users" ? "primary-button" : "secondary-button"}
              onClick={() => setTab("users")}
              type="button"
            >
              Tài khoản & Phân quyền ({users.length})
            </button>
          )}
          {(isSysAdmin || isAuditor) && (
            <button
              className={tab === "ai_audit" ? "primary-button" : "secondary-button"}
              onClick={() => setTab("ai_audit")}
              type="button"
            >
              Mô hình AI & Kiểm toán
            </button>
          )}
        </nav>
      </header>

      {statusMsg && (
        <p className="status-pill status-success admin-alert" role="status">
          {statusMsg}
        </p>
      )}
      {errorMsg && (
        <p className="status-pill status-danger admin-alert" role="alert">
          {errorMsg}
        </p>
      )}

      {tab === "documents" && (
        <div className="admin-grid">
          {canCurate && (
            <section className="admin-card" aria-label="Nhập văn bản PDF nháp">
              <h2>Nhập PDF nguồn (Biên tập viên)</h2>
              <p>Chọn tối đa {MAX_PDF_BATCH} PDF; mỗi tệp được xử lý lần lượt và lưu thành bản nháp riêng.</p>
              <form className="form-stack" onSubmit={(event) => {
                event.preventDefault();
                void runMutation(batchFiles.length > 0 ? handleUploadBatch : handleUploadDraft);
              }}>
                {batchFiles.length === 0 && <>
                <label className="field-label">
                  Tiêu đề văn bản
                  <input
                    disabled={busy}
                    onChange={(e) => setDocTitle(e.target.value)}
                    required
                    type="text"
                    value={docTitle}
                  />
                </label>
                <label className="field-label">
                  Số hiệu (ví dụ: 381/2026/NĐ-CP)
                  <input
                    disabled={busy}
                    onChange={(e) => setDocNumber(e.target.value)}
                    type="text"
                    value={docNumber}
                  />
                </label>
                <label className="field-label">
                  Loại văn bản
                  <select
                    disabled={busy}
                    onChange={(e) => setDocType(e.target.value)}
                    required
                    value={docType}
                  >
                    {DOC_TYPE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                </label>
                <label className="field-label">
                  Đường dẫn nguồn chính thức (HTTPS)
                  <input
                    disabled={busy}
                    onChange={(e) => setOfficialUrl(e.target.value)}
                    placeholder="https://vanban.chinhphu.vn/..."
                    type="url"
                    value={officialUrl}
                  />
                </label>
                </>}
                <label className="field-label">
                  Tệp văn bản gốc (PDF, Word, TXT)
                  <input
                    accept="application/pdf,.pdf,.docx,.doc,.txt,text/plain,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    disabled={busy}
                    multiple
                    onChange={choosePdfFiles}
                    ref={fileInputRef}
                    required
                    type="file"
                  />
                </label>
                {batchFiles.length > 0 && <>
                  <p>Tiêu đề tạm lấy từ tên tệp; kiểm tra thông tin riêng cho từng văn bản trước khi nhập.</p>
                  {batchFiles.map((item, index) => <fieldset className="form-stack" key={item.id}
                    aria-label={`Tệp ${index + 1}: ${item.file.name}`} disabled={busy || item.state === "success"}>
                    <legend>{item.file.name}</legend>
                    <label className="field-label">Tiêu đề văn bản
                      <input aria-label={`Tiêu đề tệp ${index + 1}`} required maxLength={500}
                        value={item.title} onChange={(event) => updateBatchFile(item.id, { title: event.target.value })} />
                    </label>
                    <label className="field-label">Loại văn bản
                      <select aria-label={`Loại văn bản tệp ${index + 1}`} required
                        value={item.docType} onChange={(event) => updateBatchFile(item.id, { docType: event.target.value })}>
                        {DOC_TYPE_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>{option.label}</option>
                        ))}
                      </select>
                    </label>
                    <label className="field-label">Số hiệu
                      <input aria-label={`Số hiệu tệp ${index + 1}`} maxLength={100}
                        value={item.docNumber} onChange={(event) => updateBatchFile(item.id, { docNumber: event.target.value })} />
                    </label>
                    <label className="field-label">Đường dẫn nguồn chính thức (HTTPS)
                      <input aria-label={`Đường dẫn nguồn tệp ${index + 1}`} type="url" maxLength={2000}
                        value={item.officialUrl} onChange={(event) => updateBatchFile(item.id, { officialUrl: event.target.value })} />
                    </label>
                    {item.message && <p>{item.message}</p>}
                  </fieldset>)}
                  <button className="secondary-button" disabled={busy} type="button" onClick={() => {
                    setBatchFiles([]);
                    if (fileInputRef.current) fileInputRef.current.value = "";
                  }}>Bỏ danh sách tệp</button>
                </>}
                {uploadProgress && <p role="status">Đang nhập tệp {uploadProgress.current}/{uploadProgress.total}…</p>}
                <div className="form-actions">
                  <button className="primary-button" disabled={busy ||
                    (batchFiles.length > 0 && batchFiles.every((item) => item.state === "success"))} type="submit">
                    {batchFiles.length === 0 ? "Tạo bản nháp" : batchFiles.some((item) => item.state !== "ready")
                      ? "Thử lại các tệp chưa thành công" : `Tạo ${batchFiles.length} bản nháp`}
                  </button>
                  {uploadProgress && <button className="secondary-button" type="button"
                    onClick={() => uploadController.current?.abort()}>Dừng nhập tệp</button>}
                </div>
              </form>
            </section>
          )}

          <section className="admin-card" aria-label="Hàng đợi rà soát và phê duyệt">
            <h2>Hàng đợi nháp & Phê duyệt (Người thẩm định)</h2>
            <p>
              Tách biệt nhiệm vụ: người tạo nháp không được tự duyệt. Phải gắn danh mục phân quyền khi phê duyệt.
            </p>
            {canReview && (
              <div className="form-stack">
                <label className="field-label">
                  Ghi chú thẩm định nguồn
                  <input
                    onChange={(e) => setReviewNote(e.target.value)}
                    type="text"
                    value={reviewNote}
                  />
                </label>
                <p className="evidence-meta">
                  Chọn rõ danh mục áp dụng trước khi phê duyệt; các tác vụ rà soát vẫn giữ nguyên để xử lý theo trạng thái thực tế.
                </p>
                <div className="category-pills">
                  {categories.map((cat) => (
                    <label className="fact-chip" key={cat.id}>
                      <input
                        checked={reviewCategoryIds.includes(cat.id)}
                        onChange={() =>
                          setReviewCategoryIds((prev) =>
                            prev.includes(cat.id)
                              ? prev.filter((id) => id !== cat.id)
                              : [...prev, cat.id],
                          )
                        }
                        type="checkbox"
                      />
                      <span>{cat.name}</span>
                    </label>
                  ))}
                </div>
              </div>
            )}
            <div className="admin-list">
              {drafts.map((item) => (
                <article className="evidence-card" key={item.document_version_id}>
                  <h3>
                    {item.document_number ? `${item.document_number} · ` : ""}
                    {item.title}
                  </h3>
                  <p className="evidence-meta">
                    Trạng thái: <strong>{DRAFT_STATUS_LABELS[item.status] ?? item.status}</strong> ·{" "}
                    {item.page_count} trang · {item.open_review_tasks} tác vụ rà soát mở · Mã băm:{" "}
                    <code>{item.sha256.slice(0, 12)}…</code>
                  </p>
                  <footer>
                    <button className="secondary-button" type="button" onClick={() => setReviewDraft(item)}>
                      Mở PDF &amp; rà soát
                    </button>
                    {canCurate && item.status === "draft" && (
                      <button
                        className="secondary-button"
                        onClick={() => void runMutation(() => handleSubmitDraft(item.document_version_id))}
                        type="button"
                      >
                        Gửi duyệt
                      </button>
                    )}
                    {canReview && item.status === "pending_review" && (
                      <div className="action-group">
                        <button
                          className="primary-button"
                          disabled={busy || reviewCategoryIds.length === 0 || item.open_review_tasks > 0 || !reviewNote.trim()}
                          onClick={() => void runMutation(() => handleApproveDraft(item.document_version_id))}
                          type="button"
                        >
                          Phê duyệt & Phát hành
                        </button>
                        <button
                          className="secondary-button"
                          onClick={() => void runMutation(() => handleRejectDraft(item.document_version_id))}
                          type="button"
                        >
                          Từ chối
                        </button>
                      </div>
                    )}
                  </footer>
                </article>
              ))}
              {drafts.length === 0 && <p>Không có bản nháp nào đang chờ xử lý.</p>}
            </div>
          </section>
          {reviewDraft && <DraftReviewPanel key={reviewDraft.document_version_id}
            draft={reviewDraft} accessToken={accessToken}
            canResolve={canReview && reviewDraft.status === "pending_review"}
            canReextract={canCurate}
            onUpdated={refreshAll} />}
        </div>
      )}

      {tab === "effectivity" && canReview && (
        <>
          <EffectivityReviewPanel accessToken={accessToken} />
          <LabelReviewPanel accessToken={accessToken} />
        </>
      )}

      {tab === "categories" && isSysAdmin && (
        <div className="admin-grid">
          <section className="admin-card" aria-label="Tạo danh mục">
            <div className="compact-card-header">
              <div>
                <h2>Tạo danh mục tài liệu</h2>
                <p>Thiết lập nhóm văn bản để kiểm soát quyền truy cập (ABAC) và chính sách gửi dữ liệu ra ngoài.</p>
              </div>
              <button
                className="secondary-button"
                onClick={() => {
                  setCatCode("");
                  setEditingCategoryId(undefined);
                  setCatName("");
                  setCatRemote(false);
                }}
                type="button"
              >
                + Tạo mới (Làm trống)
              </button>
            </div>
            <div className="category-pills" style={{ marginBottom: 10 }}>
              <button
                className="secondary-button"
                onClick={() => {
                  setCatCode("CONG_VU");
                  setCatName("Chế độ công vụ");
                  setCatRemote(false);
                }}
                type="button"
              >
                Mẫu: Chế độ công vụ
              </button>
              <button
                className="secondary-button"
                onClick={() => {
                  setCatCode("NGAN_SACH");
                  setCatName("Tài chính - Ngân sách");
                  setCatRemote(false);
                }}
                type="button"
              >
                Mẫu: Tài chính - Ngân sách
              </button>
              <button
                className="secondary-button"
                onClick={() => {
                  setCatCode("HANH_CHINH");
                  setCatName("Thủ tục hành chính công");
                  setCatRemote(true);
                }}
                type="button"
              >
                Mẫu: Thủ tục hành chính
              </button>
            </div>
            <form className="form-stack" onSubmit={(event) => { event.preventDefault(); void runMutation(() => handleCreateCategory(event)); }}>
              <label className="field-label">
                Mã danh mục
                <input
                  onChange={(e) => setCatCode(e.target.value)}
                  placeholder="CONG_VU"
                  required
                  type="text"
                  value={catCode}
                />
              </label>
              <label className="field-label">
                Tên danh mục
                <input
                  onChange={(e) => setCatName(e.target.value)}
                  placeholder="Chế độ công vụ"
                  required
                  type="text"
                  value={catName}
                />
              </label>
              <label className="checkbox-row">
                <input
                  checked={catRemote}
                  onChange={(e) => setCatRemote(e.target.checked)}
                  type="checkbox"
                />
                <span>Cho phép xử lý qua mô hình AI đám mây (Chế độ API)</span>
              </label>
              <div className="form-actions">
                <button className="primary-button" disabled={busy} type="submit">
                  {editingCategoryId ? "Cập nhật danh mục" : "Tạo danh mục"}
                </button>
              </div>
            </form>
          </section>
          <section className="admin-card" aria-label="Danh sách danh mục">
            <h2>Danh mục hiện có ({categories.length})</h2>
            <p>Danh mục được tạo và gỡ khỏi hệ thống theo quyền quản trị.</p>
            <div className="admin-list">
              {categories.map((cat) => (
                <div className="compact-admin-item" key={cat.id}>
                  <div className="compact-admin-main">
                    <div className="compact-admin-title">
                      <strong>{cat.name}</strong>
                      <span className="compact-badge">{cat.code}</span>
                      <span
                        className={
                          cat.remote_processing_allowed ? "compact-badge api" : "compact-badge local"
                        }
                      >
                        {cat.remote_processing_allowed ? "Cho phép Cloud API" : "Chỉ AI Nội bộ"}
                      </span>
                    </div>
                    <div className="compact-admin-sub">
                      Số văn bản hiệu lực: <strong>{cat.document_count ?? 0}</strong>
                    </div>
                  </div>
                  <div className="form-actions">
                    <button className="secondary-button" type="button" disabled={busy}
                      onClick={() => {
                        setEditingCategoryId(cat.id); setCatCode(cat.code); setCatName(cat.name);
                        setCatRemote(cat.remote_processing_allowed ?? false);
                      }}>Sửa danh mục</button>
                    <button
                      className="secondary-button"
                      onClick={() => void runMutation(() => handleDeleteCategory(cat.id, cat.name))}
                      type="button"
                    >
                      Xóa danh mục
                    </button>
                  </div>
                </div>
              ))}
              {categories.length === 0 && <p>Chưa có danh mục nào.</p>}
            </div>
          </section>
        </div>
      )}

      {tab === "users" && isSysAdmin && (
        <div className="admin-grid">
          <div className="form-stack">
            <section className="admin-card" aria-label="Tạo hoặc cập nhật tài khoản">
              <div className="compact-card-header">
                <div>
                  <h2>Thêm / Cập nhật tài khoản & Đặt lại mật khẩu</h2>
                  <p>Phân quyền theo vai trò (RBAC), phạm vi danh mục (ABAC) và cấp/đổi mật khẩu.</p>
                </div>
                <button
                  className="secondary-button"
                  onClick={() => {
                    setUName("");
                    setUDisplay("");
                    setUPass("");
                    setURoles(["USER"]);
                    setUCats([]);
                    setUReviewCats([]);
                    setUMustChange(true);
                    setUDisabled(false);
                    setURemoteAi(false);
                  }}
                  type="button"
                >
                  + Thêm tài khoản mới
                </button>
              </div>
              <form className="form-stack" onSubmit={(event) => { event.preventDefault(); void runMutation(() => handleUpsertUser(event)); }}>
                <div className="compact-form-grid">
                  <label className="field-label">
                    Tên đăng nhập
                    <input
                      onChange={(e) => setUName(e.target.value)}
                      placeholder="chuyen_vien_01"
                      required
                      type="text"
                      value={uName}
                    />
                  </label>
                  <label className="field-label">
                    Họ tên hiển thị
                    <input
                      onChange={(e) => setUDisplay(e.target.value)}
                      placeholder="Nguyễn Văn A"
                      required
                      type="text"
                      value={uDisplay}
                    />
                  </label>
                </div>
                <label className="field-label">
                  Mật khẩu khởi tạo / Đặt lại mật khẩu mới (tối thiểu 12 ký tự — để trống nếu giữ nguyên mật khẩu cũ)
                  <input
                    onChange={(e) => setUPass(e.target.value)}
                    placeholder="Nhập mật khẩu mới (≥ 12 ký tự)"
                    type="password"
                    value={uPass}
                  />
                </label>
                <fieldset className="field-set">
                  <legend>Vai trò hệ thống (RBAC)</legend>
                  <div className="category-pills">
                    {ALL_ROLES.map((role) => (
                      <label className="fact-chip" key={role}>
                        <input
                          checked={uRoles.includes(role)}
                          onChange={() =>
                            setURoles((prev) =>
                              prev.includes(role)
                                ? prev.filter((r) => r !== role)
                                : [...prev, role],
                            )
                          }
                          type="checkbox"
                        />
                        <span>{ROLE_LABELS[role] ?? role}</span>
                      </label>
                    ))}
                  </div>
                </fieldset>
                <fieldset className="field-set">
                  <legend>Danh mục được phép tra cứu (ABAC)</legend>
                  <div className="category-pills">
                    {categories.map((cat) => (
                      <label className="fact-chip" key={cat.id}>
                        <input
                          checked={uCats.includes(cat.id)}
                          onChange={() =>
                            setUCats((prev) =>
                              prev.includes(cat.id)
                                ? prev.filter((id) => id !== cat.id)
                                : [...prev, cat.id],
                            )
                          }
                          type="checkbox"
                        />
                        <span>{cat.name}</span>
                      </label>
                    ))}
                  </div>
                </fieldset>
                {uRoles.includes("REVIEWER") && (
                  <fieldset className="field-set">
                    <legend>Danh mục được xác nhận hiệu lực (người duyệt)</legend>
                    <div className="category-pills">
                      {categories.map((cat) => (
                        <label className="fact-chip" key={cat.id}>
                          <input
                            aria-label={`Duyệt hiệu lực ${cat.name}`}
                            checked={uReviewCats.includes(cat.id)}
                            onChange={() =>
                              setUReviewCats((prev) =>
                                prev.includes(cat.id)
                                  ? prev.filter((id) => id !== cat.id)
                                  : [...prev, cat.id],
                              )
                            }
                            type="checkbox"
                          />
                          <span>{cat.name}</span>
                        </label>
                      ))}
                    </div>
                  </fieldset>
                )}
                <label className="checkbox-row">
                  <input
                    checked={uMustChange}
                    onChange={(e) => setUMustChange(e.target.checked)}
                    type="checkbox"
                  />
                  <span>Buộc đổi mật khẩu ở lần đăng nhập kế tiếp</span>
                </label>
                <label className="checkbox-row">
                  <input checked={uRemoteAi} onChange={(e) => setURemoteAi(e.target.checked)} type="checkbox" />
                  <span>Cho phép dùng API AI bên ngoài khi chính sách hệ thống và nguồn cũng cho phép</span>
                </label>
                <label className="checkbox-row">
                  <input
                    checked={uDisabled}
                    onChange={(e) => setUDisabled(e.target.checked)}
                    type="checkbox"
                  />
                  <span>Khóa tài khoản (tạm ngừng quyền đăng nhập)</span>
                </label>
                <div className="form-actions">
                  <button className="primary-button" disabled={busy} type="submit">
                    Lưu tài khoản
                  </button>
                </div>
              </form>
            </section>

            <section className="admin-card" aria-label="Đổi mật khẩu cá nhân">
              <h2>Đổi mật khẩu cá nhân ({currentUser.username})</h2>
              <p>Thay đổi mật khẩu đăng nhập của chính tài khoản đang sử dụng.</p>
              <form className="form-stack" onSubmit={(event) => { event.preventDefault(); void runMutation(() => handleChangeOwnPassword(event)); }}>
                <label className="field-label">
                  Mật khẩu hiện tại
                  <input
                    onChange={(e) => setMyCurrentPass(e.target.value)}
                    placeholder="Nhập mật khẩu hiện tại"
                    required
                    type="password"
                    value={myCurrentPass}
                  />
                </label>
                <div className="compact-form-grid">
                  <label className="field-label">
                    Mật khẩu mới (≥ 12 ký tự)
                    <input
                      onChange={(e) => setMyNewPass(e.target.value)}
                      placeholder="Nhập mật khẩu mới"
                      required
                      type="password"
                      value={myNewPass}
                    />
                  </label>
                  <label className="field-label">
                    Xác nhận mật khẩu mới
                    <input
                      onChange={(e) => setMyConfirmPass(e.target.value)}
                      placeholder="Nhập lại mật khẩu mới"
                      required
                      type="password"
                      value={myConfirmPass}
                    />
                  </label>
                </div>
                <div className="form-actions">
                  <button className="primary-button" disabled={busy} type="submit">
                    Cập nhật mật khẩu cá nhân
                  </button>
                </div>
              </form>
            </section>
          </div>

          <section className="admin-card" aria-label="Danh sách tài khoản">
            <h2>Tài khoản trong hệ thống ({users.length})</h2>
            <p>Nhấn "Sửa / Đổi mật khẩu" để nạp vào biểu mẫu, hoặc khóa tài khoản.</p>
            <div className="admin-list">
              {users.map((u) => (
                <div className="compact-admin-item" key={u.id}>
                  <div className="compact-admin-main">
                    <div className="compact-admin-title">
                      <strong>{u.display_name}</strong>
                      <span className="compact-badge">{u.username}</span>
                      <span className={u.disabled ? "compact-badge api" : "compact-badge local"}>
                        {u.disabled ? "Đã khóa" : "Đang hoạt động"}
                      </span>
                    </div>
                    <div className="compact-admin-sub">
                      Vai trò: <strong>{u.roles.join(", ")}</strong> · Danh mục ABAC:{" "}
                      <strong>{u.category_ids.length}</strong>
                    </div>
                  </div>
                  <div className="form-actions">
                    <button
                      className="secondary-button"
                      onClick={() => {
                        setUName(u.username);
                        setUDisplay(u.display_name);
                        setUPass("");
                        setURoles(u.roles);
                        setUCats(u.category_ids);
                        setUReviewCats(u.review_category_ids ?? []);
                        setUMustChange(u.must_change_password);
                        setUDisabled(u.disabled);
                        setURemoteAi(u.remote_ai_allowed ?? false);
                      }}
                      type="button"
                    >
                      Sửa / Đổi mật khẩu
                    </button>
                    <button
                      className="secondary-button"
                      disabled={u.id === currentUser.id}
                      onClick={() => void runMutation(() => handleToggleUserLock(u))}
                      type="button"
                    >
                      {u.disabled ? "Mở khóa" : "Khóa"}
                    </button>
                    <button
                      className="secondary-button"
                      disabled={u.id === currentUser.id}
                      onClick={() => void runMutation(() => handleDeleteUser(u.id, u.username))}
                      title={
                        u.id === currentUser.id
                          ? "Không thể tự xóa tài khoản đang đăng nhập"
                          : "Vô hiệu hóa tài khoản và giữ lịch sử kiểm toán"
                      }
                      type="button"
                    >
                      Vô hiệu hóa
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>
      )}

      {tab === "ai_audit" && (
        <div className="admin-ai-section">
          <div className="admin-subtabs" role="tablist" aria-label="Chức năng AI và Kiểm toán">
            {isSysAdmin && (
              <button
                className={aiSubTab === "profiles" ? "primary-button" : "secondary-button"}
                onClick={() => setAiSubTab("profiles")}
                type="button"
              >
                1. Mô hình AI ({registry.profiles.length})
              </button>
            )}
            {isSysAdmin && (
              <button
                className={aiSubTab === "routes" ? "primary-button" : "secondary-button"}
                onClick={() => setAiSubTab("routes")}
                type="button"
              >
                2. Phân công AI
              </button>
            )}
            {isSysAdmin && (
              <button
                className={aiSubTab === "embedding" ? "primary-button" : "secondary-button"}
                onClick={() => setAiSubTab("embedding")}
                type="button"
              >
                Embedding (tìm theo nghĩa)
              </button>
            )}
            {isAuditor && (
              <button
                className={aiSubTab === "audit" ? "primary-button" : "secondary-button"}
                onClick={() => setAiSubTab("audit")}
                type="button"
              >
                3. Nhật ký Kiểm toán ({audit?.events.length ?? 0})
              </button>
            )}
          </div>

          {isSysAdmin && aiSubTab === "profiles" && (
            <ModelProfilesPanel
              accessToken={accessToken}
              onChanged={refreshAll}
              onOpenEmbedding={() => setAiSubTab("embedding")}
              registry={registry}
            />
          )}

          {isSysAdmin && aiSubTab === "routes" && (
            <AssignmentsPanel
              accessToken={accessToken}
              onChanged={refreshAll}
              onOpenEmbedding={() => setAiSubTab("embedding")}
              registry={registry}
            />
          )}

          {isSysAdmin && aiSubTab === "embedding" && (
            <EmbeddingManager accessToken={accessToken} onRegistryChanged={() => void refreshAll()} />
          )}

          {isAuditor && aiSubTab === "audit" && (
            <section className="admin-card" aria-label="Nhật ký kiểm toán bất biến">
              <div className="admin-card-title-row">
                <h2>Nhật ký Kiểm toán Chuỗi băm (Audit Log)</h2>
                <span className={audit?.chain.valid ? "status-pill status-success" : "status-pill status-danger"}>
                  {audit?.chain.valid === null || !audit
                    ? "Chưa kiểm tra đầy đủ chuỗi kiểm toán"
                    : audit.chain.valid
                    ? `Chuỗi băm hợp lệ (${audit.chain.checked} sự kiện)`
                    : "Cảnh báo đứt chuỗi"}
                </span>
              </div>
              <div className="admin-list">
                {audit?.events.map((ev) => (
                  <div className="evidence-card compact-admin-item" key={ev.id}>
                    <div className="compact-admin-row">
                      <strong>
                        {ev.action} · {ev.target_type}
                      </strong>
                      <code>#{ev.event_hash.slice(0, 10)}</code>
                    </div>
                    <p className="evidence-meta">
                      Tài khoản: {ev.username ?? ev.principal_id ?? "hệ thống"} ·{" "}
                      {ev.occurred_at}
                    </p>
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
