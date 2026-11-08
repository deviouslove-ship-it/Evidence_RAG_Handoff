import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiRequestError,
  controlAdminEmbeddingJob,
  createAdminEmbeddingJob,
  getAdminEmbeddings,
  preflightAdminEmbedding,
} from "../api/client";
import type { EmbeddingJob, EmbeddingOverview, EmbeddingPreflight } from "../types";

interface EmbeddingManagerProps {
  accessToken: string;
  /** Called after a check changed profile health, so the registry list can refresh. */
  onRegistryChanged?: () => void;
}

const INDEX_STATE_LABELS: Record<string, string> = {
  active: "Đang sử dụng",
  building: "Đang tạo",
  paused: "Tạm dừng",
  failed: "Lỗi",
  ready: "Hoàn thành",
  retired: "Đã thay thế",
};

const JOB_STATUS_LABELS: Record<string, string> = {
  queued: "Đang chờ trong hàng đợi",
  running: "Đang chạy",
  paused: "Tạm dừng",
  failed: "Lỗi",
  completed: "Hoàn thành",
  cancelled: "Đã hủy",
};

const PHASE_LABELS: Record<string, string> = {
  embedding: "Tạo vector",
  indexing: "Xây chỉ mục HNSW",
  verifying: "Kiểm tra toàn vẹn",
  switching: "Chuyển chỉ mục",
  done: "Xong",
};

const CHECK_LABELS: Record<string, string> = {
  capability: "Vai trò embedding",
  approved: "Phê duyệt dịch vụ",
  data_policy: "Chính sách gửi dữ liệu ra ngoài",
  configuration: "Cấu hình địa chỉ và khóa",
  connection: "Kết nối và danh sách model",
  test_vector: "Vector thử",
  vector_values: "Giá trị vector",
  requested_dimensions: "Số chiều yêu cầu",
  storage: "Số chiều và lưu trữ",
  documents_policy: "Văn bản được phép gửi ra ngoài",
};

const ERROR_LABELS: Record<string, string> = {
  MODEL_UNREACHABLE: "không kết nối được dịch vụ model (hoặc quá thời gian chờ)",
  MODEL_REQUEST_FAILED: "dịch vụ model trả lỗi",
  MODEL_RESPONSE_INVALID: "dịch vụ trả dữ liệu không đúng định dạng embedding",
  MODEL_RESPONSE_TOO_LARGE: "phản hồi quá lớn (giảm số nút mỗi lô)",
  PROFILE_NOT_FOUND: "không tìm thấy hồ sơ model",
  PROFILE_UNAPPROVED: "dịch vụ chưa được phê duyệt",
  PROFILE_UNHEALTHY: "hồ sơ đang ở trạng thái lỗi; hãy kiểm tra kết nối lại",
  MODEL_CAPABILITY_UNAVAILABLE: "hồ sơ không có vai trò embedding",
  MODEL_SECRET_UNAVAILABLE: "chưa đặt biến môi trường chứa khóa API",
  MODEL_SECRET_REF_INVALID: "tham chiếu khóa API không hợp lệ",
  AI_EGRESS_DENIED: "tên miền API chưa được cho phép trên máy chủ",
  AI_LOCAL_ENDPOINT_DENIED: "địa chỉ local/LAN chưa được cho phép trên máy chủ",
  AI_ENDPOINT_INVALID: "địa chỉ dịch vụ không hợp lệ",
  REMOTE_EMBEDDING_DENIED: "chính sách máy chủ chưa cho phép embedding qua API bên ngoài",
  REMOTE_EMBEDDING_DOCUMENTS_DENIED: "có văn bản không được phép gửi ra ngoài",
  EMBEDDING_MODEL_CHANGED: "hồ sơ model đã đổi trong lúc tạo; hãy kiểm tra lại và tạo mới",
  EMBEDDING_INVALID: "model trả vector không hợp lệ (số không hữu hạn hoặc toàn 0)",
  EMBEDDING_DIMENSIONS_UNSUPPORTED: "số chiều vượt giới hạn chỉ mục (tối đa 4000)",
  EMBEDDING_DIMENSION_MISMATCH: "số chiều trả về khác số chiều yêu cầu",
  EMBEDDING_SAMPLE_MISMATCH: "model không tạo lại được vector giống lần trước (không ổn định)",
  EMBEDDING_PENDING_NODES: "còn nút chưa có vector",
  EMBEDDING_VECTOR_INDEX_INVALID: "chỉ mục HNSW chưa hợp lệ",
  EMBEDDING_INDEX_EMPTY: "chỉ mục chưa có vector",
  EMBEDDING_UNAVAILABLE: "model embedding không phản hồi",
  EMBEDDING_NOT_CONFIGURED: "chưa cấu hình model embedding",
  EMBEDDING_WORKER_ERROR: "lỗi của tiến trình nền",
};

function errorText(code: string | null | undefined): string {
  if (!code) return "";
  if (code.startsWith("EMBEDDING_PROBE_")) {
    return `kiểm tra kết nối không đạt (${code.slice("EMBEDDING_PROBE_".length).toLowerCase()})`;
  }
  return ERROR_LABELS[code] ? `${ERROR_LABELS[code]} (${code})` : code;
}

function duration(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (hours > 0) return `${hours} giờ ${minutes} phút`;
  if (minutes > 0) return `${minutes} phút ${total % 60} giây`;
  return `${total} giây`;
}

function when(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString("vi-VN") : "—";
}

function stateClass(state: string): string {
  if (state === "active" || state === "completed" || state === "ready") return "status-pill status-success";
  if (state === "failed") return "status-pill status-danger";
  return "status-pill status-warning";
}

const ACTIVE_JOB = new Set(["queued", "running"]);

export function EmbeddingManager({ accessToken, onRegistryChanged }: EmbeddingManagerProps) {
  const [overview, setOverview] = useState<EmbeddingOverview>();
  const [profileId, setProfileId] = useState("");
  const [batchSize, setBatchSize] = useState("16");
  const [rebuild, setRebuild] = useState(false);
  const [check, setCheck] = useState<EmbeddingPreflight>();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string>();
  const [errorMsg, setErrorMsg] = useState<string>();
  const pending = useRef(false);

  const load = useCallback(async () => {
    try {
      const data = await getAdminEmbeddings(accessToken);
      setOverview(data);
      setProfileId((current) => current || data.change.profile_id || data.route_profile_id
        || data.active_index?.profile_id || data.profiles[0]?.profile_id || "");
    } catch (caught) {
      setErrorMsg(caught instanceof Error ? caught.message : "Không tải được trạng thái embedding.");
    }
  }, [accessToken]);

  useEffect(() => {
    void load();
  }, [load]);

  const hasActiveJob = Boolean(overview?.jobs.some((job) => ACTIVE_JOB.has(job.status)));
  useEffect(() => {
    if (!hasActiveJob) return undefined;
    const timer = setInterval(() => void load(), 3000);
    return () => clearInterval(timer);
  }, [hasActiveJob, load]);

  async function run(action: () => Promise<void>) {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setErrorMsg(undefined);
    try {
      await action();
    } catch (caught) {
      const problems = caught instanceof ApiRequestError && Array.isArray(caught.details?.problems)
        ? ` (${(caught.details.problems as string[]).map(errorText).join("; ")})` : "";
      setErrorMsg((caught instanceof Error ? caught.message : "Không thể hoàn tất yêu cầu.") + problems);
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }

  function selectedBatch(): number {
    const value = Number(batchSize);
    return Number.isInteger(value) && value >= 1 && value <= 256 ? value : 16;
  }

  async function runPreflight(id: string, fresh: boolean) {
    setConfirming(false);
    setCheck(undefined);
    setStatusMsg(undefined);
    const result = await preflightAdminEmbedding(accessToken, {
      profile_id: id, rebuild: fresh, batch_size: selectedBatch(),
    });
    setCheck(result);
    onRegistryChanged?.();
    await load();
  }

  async function startJob() {
    if (!check) return;
    const job = await createAdminEmbeddingJob(accessToken, {
      profile_id: check.profile_id, rebuild: check.rebuild, batch_size: selectedBatch(),
      confirmed: true,
    });
    setConfirming(false);
    setCheck(undefined);
    setStatusMsg(`Đã xếp hàng tác vụ tạo vector cho ${job.remaining_nodes} nút bằng model ${job.model_id ?? check.model_id}. `
      + "Chỉ mục hiện tại vẫn phục vụ tìm kiếm đến khi tác vụ hoàn tất và được kiểm tra.");
    await load();
  }

  async function control(job: EmbeddingJob, action: "pause" | "resume" | "retry" | "cancel") {
    await controlAdminEmbeddingJob(accessToken, job.id, action);
    const labels = { pause: "tạm dừng", resume: "tiếp tục", retry: "thử lại", cancel: "hủy" };
    setStatusMsg(`Đã ${labels[action]} tác vụ ${job.profile_id}.`);
    await load();
  }

  if (!overview) {
    return (
      <section className="admin-card" aria-label="Quản lý embedding">
        <h2>Embedding và chỉ mục vector</h2>
        {errorMsg ? <p className="admin-banner error" role="alert">{errorMsg}</p>
          : <p className="evidence-meta">Đang tải…</p>}
      </section>
    );
  }

  const active = overview.active_index;
  const change = overview.change;
  const selectedProfile = overview.profiles.find((item) => item.profile_id === profileId);

  return (
    <div className="admin-grid" aria-label="Quản lý embedding">
      <section className="admin-card" aria-label="Chỉ mục vector đang phục vụ">
        <div className="admin-card-title-row">
          <h2>Chỉ mục vector đang phục vụ tìm kiếm</h2>
          <button className="secondary-button" disabled={busy} onClick={() => void run(load)} type="button">
            Làm mới
          </button>
        </div>
        {statusMsg && <p className="admin-banner status" role="status">{statusMsg}</p>}
        {errorMsg && <p className="admin-banner error" role="alert">{errorMsg}</p>}
        {active ? (
          <>
            <p className="evidence-meta">
              Model <code>{active.model_id}</code> (phiên bản {active.revision}) · hồ sơ{" "}
              <code>{active.profile_id ?? "—"}</code> · {active.dimensions} chiều ({active.storage ?? "?"})
            </p>
            <p className="evidence-meta">
              {active.node_count} vector · kích hoạt {when(active.activated_at ?? active.completed_at)} ·
              {" "}{overview.eligible_nodes} nút Điều/Khoản/Điểm đã duyệt trong kho
            </p>
            {(overview.missing_in_active ?? 0) > 0 && (
              <div className="form-actions">
                <span className="status-pill status-warning">
                  {overview.missing_in_active} nút mới chưa có vector
                </span>
                <button
                  className="secondary-button"
                  disabled={busy || !active.profile_id}
                  onClick={() => {
                    if (!active.profile_id) return;
                    setProfileId(active.profile_id);
                    setRebuild(false);
                    void run(() => runPreflight(active.profile_id as string, false));
                  }}
                  type="button"
                >
                  Kiểm tra và bổ sung vector còn thiếu
                </button>
              </div>
            )}
          </>
        ) : (
          <p className="evidence-meta">
            Chưa có chỉ mục vector: kênh tìm theo nghĩa chưa chạy; các kênh khác vẫn hoạt động.
          </p>
        )}
        {change.detected && (
          <p className="admin-banner error" role="status">
            {change.reason === "no_active_index"
              ? "Chưa có chỉ mục vector cho kho văn bản."
              : change.reason === "profile_model_changed"
                ? `Hồ sơ ${change.profile_id} đã đổi sang model ${change.model_id}; chỉ mục đang dùng thuộc model cũ.`
                : `Model embedding đã chọn (${change.profile_id} → ${change.model_id}) khác model của chỉ mục đang dùng.`}
            {" "}Khoảng {change.pending_nodes ?? overview.eligible_nodes} nút cần tạo vector.
            {change.open_job_id ? " Đã có tác vụ cho model này (xem bên dưới)." : " Hãy kiểm tra model rồi xác nhận để tạo lại."}
          </p>
        )}
        <p className="evidence-meta">
          Tiến trình nền: {overview.worker.alive ? "đang hoạt động" : overview.worker.enabled ? "không chạy" : "đã tắt (EVIDENCE_EMBEDDING_WORKER)"}
          {overview.worker.last_poll_at ? ` · kiểm tra hàng đợi lúc ${when(overview.worker.last_poll_at)}` : ""}
          {" "}· Chế độ {overview.mode}
          {overview.remote_embedding_allowed ? " · cho phép embedding qua API bên ngoài" : " · chỉ dùng model local"}
        </p>
      </section>

      <section className="admin-card" aria-label="Chọn hoặc đổi model embedding">
        <h2>Chọn / đổi model embedding</h2>
        {overview.profiles.length === 0 ? (
          <p className="evidence-meta">
            Chưa có hồ sơ model vai trò embedding. Vào “1. Hồ sơ Mô hình”, chọn vai trò “Tạo vector
            (embedding)”, lưu, phê duyệt rồi quay lại đây.
          </p>
        ) : (
          <form className="form-stack" onSubmit={(event) => {
            event.preventDefault();
            void run(() => runPreflight(profileId, rebuild));
          }}>
            <div className="admin-form-grid-2">
              <label className="field-label">
                Hồ sơ model embedding
                <select aria-label="Hồ sơ model embedding" onChange={(e) => { setProfileId(e.target.value); setCheck(undefined); }} value={profileId}>
                  {overview.profiles.map((item) => (
                    <option key={item.profile_id} value={item.profile_id}>
                      {item.profile_id} — {item.model_id} ({item.privacy_zone === "public" ? "API" : "local"})
                    </option>
                  ))}
                </select>
              </label>
              <label className="field-label">
                Số nút mỗi lô (1–256)
                <input aria-label="Số nút mỗi lô" max={256} min={1} onChange={(e) => setBatchSize(e.target.value)} type="number" value={batchSize} />
              </label>
            </div>
            {selectedProfile && (
              <p className="evidence-meta">
                Model <code>{selectedProfile.model_id}</code> · phiên bản {selectedProfile.revision} ·
                {selectedProfile.provider_approved ? " đã duyệt" : " chưa duyệt"} · kết nối: {selectedProfile.health}
                {selectedProfile.requested_dimensions ? ` · yêu cầu ${selectedProfile.requested_dimensions} chiều` : ""}
              </p>
            )}
            <label className="checkbox-row">
              <input checked={rebuild} onChange={(e) => { setRebuild(e.target.checked); setCheck(undefined); }} type="checkbox" />
              <span>Tạo chỉ mục mới từ đầu (không dùng lại vector đã có của cùng model)</span>
            </label>
            <div className="form-actions">
              <button className="primary-button" disabled={busy || !profileId} type="submit">
                {busy && !check ? "Đang kiểm tra…" : "Kiểm tra model"}
              </button>
            </div>
          </form>
        )}

        {check && (
          <div className="admin-list" aria-label="Kết quả kiểm tra model embedding">
            {check.checks.map((item) => (
              <p className="evidence-meta" key={item.key}>
                <span className={item.ok ? "status-pill status-success" : "status-pill status-danger"}>
                  {item.ok ? "Đạt" : "Không đạt"}
                </span>{" "}
                {CHECK_LABELS[item.key] ?? item.key}
                {item.detail ? `: ${item.detail}` : ""}
                {!item.ok && item.code ? ` — ${errorText(item.code)}` : ""}
              </p>
            ))}
            {check.ok && check.to_embed !== undefined && (
              <>
                <p className="evidence-meta">
                  {check.dimensions} chiều · phản hồi thử {check.latency_ms} ms ·
                  {" "}{check.eligible_nodes} nút trong kho, {check.already_embedded} đã có vector của model này,
                  {" "}<strong>{check.to_embed} nút cần tạo</strong> · ước tính thô {duration(check.estimated_seconds)}
                </p>
                <p className="evidence-meta">
                  {check.kind === "catch_up"
                    ? "Bổ sung vào chỉ mục đang dùng; tìm kiếm không bị gián đoạn."
                    : "Tạo chỉ mục mới. Model và chỉ mục hiện tại tiếp tục phục vụ tìm kiếm; chỉ chuyển khi mọi vector và chỉ mục mới đã kiểm tra xong. Nếu lỗi, hệ thống giữ chỉ mục cũ."}
                </p>
                {check.open_job ? (
                  <p className="admin-banner error">
                    Đã có tác vụ ({JOB_STATUS_LABELS[check.open_job.status]}) cho model này; hãy tiếp tục
                    hoặc thử lại tác vụ đó ở danh sách bên dưới.
                  </p>
                ) : confirming ? (
                  <div className="evidence-card compact-admin-item" role="alertdialog" aria-label="Xác nhận tạo lại vector">
                    <p>
                      Xác nhận tạo embedding cho <strong>{check.to_embed}</strong> nút bằng model{" "}
                      <code>{check.model_id}</code> ({check.dimensions} chiều)? Tác vụ chạy nền, có thể
                      tạm dừng, tiếp tục và tự phục hồi khi máy chủ khởi động lại.
                    </p>
                    <div className="form-actions">
                      <button className="primary-button" disabled={busy} onClick={() => void run(startJob)} type="button">
                        Xác nhận và bắt đầu
                      </button>
                      <button className="secondary-button" disabled={busy} onClick={() => setConfirming(false)} type="button">
                        Hủy
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="form-actions">
                    <button
                      className="primary-button"
                      disabled={busy || (check.kind === "catch_up" && check.to_embed === 0)}
                      onClick={() => setConfirming(true)}
                      type="button"
                    >
                      {check.kind === "catch_up" && check.to_embed === 0
                        ? "Chỉ mục đã đầy đủ"
                        : `Tạo vector cho ${check.to_embed} nút…`}
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </section>

      <section className="admin-card" aria-label="Tác vụ tạo vector">
        <h2>Tác vụ tạo vector ({overview.jobs.length})</h2>
        <div className="admin-list">
          {overview.jobs.length === 0 && <p className="evidence-meta">Chưa có tác vụ.</p>}
          {overview.jobs.map((job) => (
            <div className="evidence-card compact-admin-item" key={job.id}>
              <div className="compact-admin-row">
                <div>
                  <strong>{job.profile_id}</strong> <code>{job.model_id}</code>{" "}
                  <span className={stateClass(job.status)}>{JOB_STATUS_LABELS[job.status] ?? job.status}</span>
                  {job.status === "running" && <> · {PHASE_LABELS[job.phase] ?? job.phase}</>}
                </div>
                <div className="form-actions">
                  {ACTIVE_JOB.has(job.status) && (
                    <button className="secondary-button" disabled={busy} onClick={() => void run(() => control(job, "pause"))} type="button">
                      Tạm dừng
                    </button>
                  )}
                  {job.status === "paused" && (
                    <button className="secondary-button" disabled={busy} onClick={() => void run(() => control(job, "resume"))} type="button">
                      Tiếp tục
                    </button>
                  )}
                  {job.status === "failed" && (
                    <button className="secondary-button" disabled={busy} onClick={() => void run(() => control(job, "retry"))} type="button">
                      Thử lại
                    </button>
                  )}
                  {(job.status === "paused" || job.status === "failed" || job.status === "queued") && (
                    <button className="secondary-button" disabled={busy} onClick={() => void run(() => control(job, "cancel"))} type="button">
                      Hủy tác vụ
                    </button>
                  )}
                </div>
              </div>
              <progress aria-label={`Tiến độ ${job.profile_id}`} className="embedding-progress" max={100} value={job.percent} />
              <p className="evidence-meta">
                {job.done_nodes}/{job.total_nodes} nút ({job.percent}%) · còn {job.remaining_nodes} ·
                {" "}tốc độ {job.rate_per_minute != null ? `${job.rate_per_minute} nút/phút` : "—"} ·
                {" "}còn khoảng {duration(job.eta_seconds)} · {job.kind === "catch_up" ? "bổ sung" : "tạo lại"} ·
                {" "}lô {job.batch_size}
              </p>
              <p className="evidence-meta">
                Tạo lúc {when(job.created_at)}
                {job.finished_at ? ` · kết thúc ${when(job.finished_at)}` : ""}
                {job.failed_batches > 0 ? ` · ${job.failed_batches} lô lỗi` : ""}
                {job.next_attempt_at && job.status === "running" ? ` · thử lại lúc ${when(job.next_attempt_at)}` : ""}
              </p>
              {job.last_error && job.status !== "completed" && (
                <p className="evidence-meta" role={job.status === "failed" ? "alert" : undefined}>
                  Lỗi gần nhất: {errorText(job.last_error)}
                </p>
              )}
              {job.errors.length > 0 && (
                <details>
                  <summary className="evidence-meta">Nhật ký lỗi ({job.errors.length})</summary>
                  {job.errors.slice().reverse().map((item, position) => (
                    <p className="evidence-meta" key={`${item.at}-${position}`}>
                      {when(item.at)}: {errorText(item.code)}{item.detail ? ` — ${item.detail}` : ""}
                    </p>
                  ))}
                </details>
              )}
            </div>
          ))}
        </div>
      </section>

      <section className="admin-card" aria-label="Các chỉ mục vector">
        <h2>Các chỉ mục vector ({overview.indices.length})</h2>
        <p className="evidence-meta">Chỉ mục cũ và vector của nó được giữ lại; hệ thống không tự xóa.</p>
        <div className="admin-list">
          {overview.indices.map((index) => (
            <div className="evidence-card compact-admin-item" key={index.id}>
              <div className="compact-admin-row">
                <div>
                  <code>{index.model_id}</code> · {index.dimensions} chiều · bản #{index.index_revision}
                </div>
                <span className={stateClass(index.state)}>{INDEX_STATE_LABELS[index.state] ?? index.state}</span>
              </div>
              <p className="evidence-meta">
                Hồ sơ {index.profile_id ?? "—"} · {index.vectors ?? index.node_count} vector · tạo {when(index.created_at)}
                {index.activated_at ? ` · kích hoạt ${when(index.activated_at)}` : ""}
                {index.retired_at ? ` · thay thế ${when(index.retired_at)}` : ""}
                {index.last_error ? ` · lỗi: ${errorText(index.last_error)}` : ""}
              </p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
