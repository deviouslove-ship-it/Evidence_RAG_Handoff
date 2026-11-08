import { useState } from "react";

import {
  testAdminModelProfile,
  upsertAdminStagePolicy,
  upsertAdminStageRoute,
} from "../../api/client";
import type { ModelRegistryState } from "../../types";
import {
  AI_FUNCTIONS,
  STATUS_TEXT,
  eligibleProfiles,
  profileStatus,
  routeOf,
  type AiFunction,
  type ModelCheckResult,
} from "./aiConfig";
import { CheckResult } from "./CheckResult";

interface AssignmentsPanelProps {
  accessToken: string;
  registry: ModelRegistryState;
  onChanged: () => Promise<void>;
  onOpenEmbedding: () => void;
}

const STATUS_CLASS = {
  ready: "status-success", unchecked: "status-warning", error: "status-danger",
  unapproved: "status-warning",
} as const;

function Limits({ accessToken, registry, mode, stage, onChanged }: {
  accessToken: string; registry: ModelRegistryState; mode: string; stage: string;
  onChanged: () => Promise<void>;
}) {
  const current = registry.stage_policies?.find((item) => item.mode === mode && item.stage === stage);
  const [attempts, setAttempts] = useState(String(current?.max_attempts ?? 2));
  const [tokens, setTokens] = useState(current?.max_output_tokens != null ? String(current.max_output_tokens) : "");
  const [timeout, setTimeoutValue] = useState(current?.timeout_seconds != null ? String(current.timeout_seconds) : "");
  const [concurrency, setConcurrency] = useState(current?.max_concurrency != null ? String(current.max_concurrency) : "");
  const [message, setMessage] = useState<string>();

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setMessage(undefined);
    try {
      await upsertAdminStagePolicy(accessToken, {
        mode, stage, max_attempts: Number(attempts),
        max_output_tokens: tokens.trim() ? Number(tokens) : null,
        timeout_seconds: timeout.trim() ? Number(timeout) : null,
        max_concurrency: concurrency.trim() ? Number(concurrency) : null,
      });
      setMessage("Đã lưu giới hạn.");
      await onChanged();
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Không lưu được giới hạn.");
    }
  }

  return (
    <form className="ai-limits" onSubmit={(event) => void save(event)}>
      <div className="admin-form-grid-2">
        <label className="field-label">Số lần gửi tối đa (1–10)
          <input max={10} min={1} onChange={(e) => setAttempts(e.target.value)} required
                 type="number" value={attempts} />
        </label>
        <label className="field-label">Token trả về tối đa
          <input max={2048} min={1} onChange={(e) => setTokens(e.target.value)} type="number"
                 value={tokens} />
        </label>
        <label className="field-label">Thời gian chờ (giây, ≤ 30)
          <input max={30} min={0.1} onChange={(e) => setTimeoutValue(e.target.value)}
                 step="any" type="number" value={timeout} />
        </label>
        <label className="field-label">Số yêu cầu đồng thời
          <input max={64} min={1} onChange={(e) => setConcurrency(e.target.value)} type="number"
                 value={concurrency} />
        </label>
      </div>
      <div className="form-actions">
        <button className="secondary-button" type="submit">Lưu giới hạn</button>
        {message && <small className="evidence-meta" role="status">{message}</small>}
      </div>
      <p className="evidence-meta">Ô để trống dùng mặc định của máy chủ.</p>
    </form>
  );
}

function Row({ accessToken, registry, mode, fn, onChanged }: {
  accessToken: string; registry: ModelRegistryState; mode: string; fn: AiFunction;
  onChanged: () => Promise<void>;
}) {
  const route = routeOf(registry, mode, fn.stage);
  const options = eligibleProfiles(registry, fn.stage, mode);
  const [choice, setChoice] = useState(route?.profile_id ?? "");
  const [fallback, setFallback] = useState(route?.fallback[0] ?? "");
  const [escalation, setEscalation] = useState(route?.escalation_profile_id ?? "");
  const [busy, setBusy] = useState(false);
  const [check, setCheck] = useState<ModelCheckResult>();
  const [offerForce, setOfferForce] = useState(false);
  const [message, setMessage] = useState<string>();
  const [error, setError] = useState<string>();
  const assigned = registry.profiles.find((item) => item.profile_id === route?.profile_id);
  const chosen = registry.profiles.find((item) => item.profile_id === choice);
  const dirty = Boolean(choice)
    && (choice !== (route?.profile_id ?? "") || fallback !== (route?.fallback[0] ?? "")
      || escalation !== (route?.escalation_profile_id ?? ""));
  const publicProfiles = registry.profiles.filter((item) =>
    item.privacy_zone === "public" && item.capabilities.includes(fn.stage));

  async function apply(force: boolean) {
    setError(undefined);
    setMessage(undefined);
    setBusy(true);
    try {
      if (!force) {
        // A model is activated only after it connects and answers.
        const result = await testAdminModelProfile(accessToken, choice);
        setCheck(result);
        if (!result.usable) { setOfferForce(true); await onChanged(); return; }
      }
      await upsertAdminStageRoute(accessToken, {
        mode, stage: fn.stage, profile_id: choice, fallback: fallback ? [fallback] : [],
        escalation_profile_id: mode === "API" && fn.escalation && escalation ? escalation : null,
      });
      setOfferForce(false);
      setMessage(`Đã phân công ${choice} cho “${fn.label}” (${mode}).`);
      await onChanged();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Không phân công được.");
    } finally {
      setBusy(false);
    }
  }

  const select = (
    value: string, onChange: (next: string) => void, label: string,
    items: typeof options, empty: string,
  ) => (
    <label className="field-label">
      {label}
      <select onChange={(e) => { onChange(e.target.value); setCheck(undefined); setOfferForce(false); }}
              value={value}>
        <option value="">{empty}</option>
        {items.map((item) => (
          <option key={item.profile_id} value={item.profile_id}>
            {item.profile_id} · {item.model_id}
          </option>
        ))}
      </select>
    </label>
  );

  return (
    <div className="ai-assignment" data-stage={fn.stage}>
      <div className="ai-assignment-head">
        <div>
          <strong>{fn.label}</strong>
          <p className="evidence-meta">{fn.hint}</p>
        </div>
        {assigned ? (
          <span className={`status-pill ${STATUS_CLASS[profileStatus(assigned)]}`}>
            {STATUS_TEXT[profileStatus(assigned)]}
          </span>
        ) : (
          <span className="status-pill status-warning">Chưa phân công</span>
        )}
      </div>
      <div className="ai-assignment-pick">
        {select(choice, setChoice, `Model cho ${fn.label}`, options, "Chọn model…")}
        <button className="primary-button" disabled={busy || !dirty}
                onClick={() => void apply(false)} type="button">
          {busy ? "Đang kiểm tra…" : "Kiểm tra & Áp dụng"}
        </button>
        {offerForce && (
          <button className="secondary-button" disabled={busy}
                  onClick={() => void apply(true)} type="button">
            Vẫn áp dụng (chưa dùng được)
          </button>
        )}
      </div>
      {!assigned && (
        <p className="evidence-meta">
          Chưa phân công: chức năng này chạy không dùng AI (kết quả vẫn có, ít được hỗ trợ hơn).
        </p>
      )}
      {assigned && profileStatus(assigned) !== "ready" && (
        <p className="evidence-meta">
          Model đang gán chưa sẵn sàng nên chức năng đang chạy không dùng AI. Bấm “Kiểm tra &
          Áp dụng” để kiểm tra lại.
        </p>
      )}
      {check && <CheckResult result={check} title={`Kết quả kiểm tra ${fn.label}`} />}
      {message && <p className="status-pill status-success" role="status">{message}</p>}
      {error && <p className="status-pill status-danger" role="alert">{error}</p>}
      <details className="ai-advanced">
        <summary>Nâng cao</summary>
        <div className="ai-advanced-body">
          {select(fallback, setFallback, `Model dự phòng cho ${fn.label}`,
            options.filter((item) => item.profile_id !== choice
              && (item.privacy_zone === "public") === (chosen?.privacy_zone === "public")),
            "Không dùng dự phòng")}
          {mode === "API" && fn.escalation && select(
            escalation, setEscalation, `Model API nâng cấp cho ${fn.label}`,
            publicProfiles, "Không nâng cấp")}
          {mode === "API" && fn.escalation && (
            <p className="evidence-meta">
              Model nâng cấp chỉ được gọi khi kết quả của model chính không qua kiểm tra, hoặc
              người dùng chọn “Phân tích sâu”, và chỉ với dữ liệu được phép gửi ra ngoài.
            </p>
          )}
          <Limits accessToken={accessToken} mode={mode} onChanged={onChanged}
                  registry={registry} stage={fn.stage} />
        </div>
      </details>
    </div>
  );
}

/**
 * "Phân công AI": which model serves which function, per operating mode.  A model is
 * applied only after it passes the connection and usability check (or the administrator
 * overrides it), because the runtime uses a profile only when it is recorded as ready.
 */
export function AssignmentsPanel({
  accessToken, registry, onChanged, onOpenEmbedding,
}: AssignmentsPanelProps) {
  const serverMode = registry.effective_mode === "API" ? "API" : "LOCAL";
  const [mode, setMode] = useState(serverMode);
  const embeddingRoute = routeOf(registry, mode, "embedding");

  return (
    <div className="admin-card ai-assignments" aria-label="Phân công AI">
      <div className="admin-card-title-row">
        <h2>Phân công AI</h2>
        <div className="form-actions" role="group" aria-label="Chế độ vận hành">
          {["LOCAL", "API"].map((item) => (
            <button
              aria-pressed={mode === item}
              className={mode === item ? "primary-button" : "secondary-button"}
              key={item}
              onClick={() => setMode(item)}
              type="button"
            >
              {item === "LOCAL" ? "Chế độ LOCAL" : "Chế độ API"}
            </button>
          ))}
        </div>
      </div>
      <p className="evidence-meta">
        Máy chủ đang chạy chế độ <strong>{serverMode}</strong>; chỉ phân công của chế độ này được
        dùng.
        {mode === "LOCAL"
          ? " Chế độ LOCAL chỉ dùng model chạy nội bộ, không gọi API bên ngoài."
          : " Chế độ API dùng model chính và có thể nâng cấp lên model API khi cần."}
      </p>
      <div className="ai-assignment-list">
        {AI_FUNCTIONS.filter((item) => item.editable).map((fn) => (
          <Row accessToken={accessToken} fn={fn} key={`${mode}:${fn.stage}`} mode={mode}
               onChanged={onChanged} registry={registry} />
        ))}
        <div className="ai-assignment" data-stage="embedding">
          <div className="ai-assignment-head">
            <div>
              <strong>{AI_FUNCTIONS.find((item) => item.stage === "embedding")?.label}</strong>
              <p className="evidence-meta">
                Model embedding gắn với chỉ mục vector đang dùng; chỉ đổi được ở mục Embedding,
                nơi chỉ mục mới được dựng và chuyển sang an toàn.
              </p>
            </div>
            <span className="status-pill status-success">
              {embeddingRoute?.profile_id ?? "Chưa chọn"}
            </span>
          </div>
          <button className="secondary-button" onClick={onOpenEmbedding} type="button">
            Mở mục Embedding
          </button>
        </div>
      </div>
      {(registry.usage ?? []).length > 0 && (
        <details className="ai-advanced">
          <summary>Mức dùng model tháng này</summary>
          <div className="ai-advanced-body">
            {(registry.usage ?? []).map((item) => (
              <p className="evidence-meta" key={item.profile_id}>
                {item.profile_id}: hôm nay {item.calls_today} lượt (chi phí ước tính{" "}
                {item.cost_today.toFixed(4)}); tháng này {item.calls_month} lượt, trong đó{" "}
                {item.escalations_month} lượt nâng cấp, {item.cost_month.toFixed(4)}
              </p>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
