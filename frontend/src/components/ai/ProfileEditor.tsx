import { useState } from "react";

import { testAdminModelDraft, testAdminModelProfile, upsertAdminModelProfile } from "../../api/client";
import {
  API_PROVIDERS,
  AI_FUNCTIONS,
  buildPayload,
  chooseModel,
  chooseService,
  formProblem,
  runtimeChoices,
  slugName,
  type AdvancedForm,
  type ModelCheckResult,
  type ProfileForm,
} from "./aiConfig";
import { CheckResult } from "./CheckResult";

interface ProfileEditorProps {
  accessToken: string;
  initial: ProfileForm;
  /** The server can keep a key typed here; without it only a variable reference works. */
  secretStoreAvailable: boolean;
  onSaved: (message: string) => Promise<void> | void;
  onCancel: () => void;
}

const EFFORTS: Array<[string, string]> = [
  ["", "Mặc định của model"], ["none", "none: tắt suy luận"], ["minimal", "minimal"],
  ["low", "low"], ["medium", "medium"], ["high", "high"],
];

/**
 * One profile, in the form of its kind: AI Local (name, runtime, model, address) or AI API
 * (name, provider, base URL, model, key).  Everything else is derived and lives under
 * "Nâng cao".  "Kiểm tra & Lưu" first checks the connection and the model; a profile that
 * fails is saved only on an explicit "Vẫn lưu".
 */
export function ProfileEditor({
  accessToken, initial, secretStoreAvailable, onSaved, onCancel,
}: ProfileEditorProps) {
  const [form, setForm] = useState<ProfileForm>(initial);
  const [busy, setBusy] = useState<"test" | "save" | undefined>();
  const [check, setCheck] = useState<ModelCheckResult>();
  const [error, setError] = useState<string>();
  const [forceOffered, setForceOffered] = useState(false);
  const local = form.kind === "local";
  const adv = form.advanced;
  const embedding = adv.role === "embedding";
  const problem = formProblem(form);

  /** Any change invalidates the last check: the next save checks again. */
  function update(change: (current: ProfileForm) => ProfileForm) {
    setForm(change);
    setCheck(undefined);
    setForceOffered(false);
  }
  function edit(change: Partial<ProfileForm>) {
    update((current) => ({ ...current, ...change }));
  }
  function editAdvanced(change: Partial<AdvancedForm>) {
    update((current) => ({
      ...current, advanced: { ...current.advanced, ...change }, advancedTouched: true,
    }));
  }
  function toggleFunction(stage: string, on: boolean) {
    const next = on ? [...adv.functions, stage] : adv.functions.filter((item) => item !== stage);
    editAdvanced({ functions: next });
  }

  async function runCheck(): Promise<ModelCheckResult | undefined> {
    setBusy("test");
    setError(undefined);
    try {
      const result = await testAdminModelDraft(accessToken, buildPayload(form));
      setCheck(result);
      return result;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Không kiểm tra được.");
      return undefined;
    } finally {
      setBusy(undefined);
    }
  }

  async function save(force: boolean) {
    if (problem) { setError(problem); return; }
    setError(undefined);
    if (!force) {
      const result = await runCheck();
      if (!result) return;
      if (!result.usable) { setForceOffered(true); return; }
    }
    setBusy("save");
    try {
      const payload = buildPayload(form);
      await upsertAdminModelProfile(accessToken, payload);
      // The runtime uses a profile only once its health is recorded as ready.
      const saved = await testAdminModelProfile(accessToken, payload.profile_id);
      const message = saved.usable && saved.health === "ready"
        ? `Đã lưu hồ sơ ${payload.profile_id}: sẵn sàng. Gán cho chức năng ở mục “Phân công AI”.`
        : `Đã lưu hồ sơ ${payload.profile_id} nhưng chưa dùng được (${saved.status ?? "chưa kiểm tra"}). Sửa cấu hình rồi kiểm tra lại.`;
      await onSaved(message);
    } catch (caught) {
      const text = caught instanceof Error ? caught.message : "Không lưu được hồ sơ.";
      setError(text);
    } finally {
      setBusy(undefined);
    }
  }

  const keyHint = form.secretRef?.startsWith("secret:")
    ? "Đã lưu một khóa (đã che). Để trống để giữ khóa hiện tại."
    : form.secretRef ? `Đang dùng biến môi trường ${form.secretRef.slice(4)}. Nhập khóa mới để thay.`
      : "Khóa được lưu mã hóa trên máy chủ, không hiển thị lại.";

  return (
    <form
      aria-label={local ? "Cấu hình AI Local" : "Cấu hình AI API"}
      className="form-stack ai-form"
      onSubmit={(event) => { event.preventDefault(); void save(false); }}
    >
      <label className="field-label">
        Tên hồ sơ
        <input
          disabled={form.editing}
          onChange={(e) => edit({ name: slugName(e.target.value) })}
          placeholder={local ? "vd: ollama-qwen3" : "vd: openai-gpt"}
          required
          value={form.name}
        />
      </label>

      {local ? (
        <label className="field-label">
          Runtime
          <select onChange={(e) => update((current) => chooseService(current, e.target.value))}
                  value={form.choice}>
            {runtimeChoices(form.choice).map((item) => (
              <option key={item.value} value={item.value}>{item.label}</option>
            ))}
          </select>
        </label>
      ) : (
        <label className="field-label">
          Nhà cung cấp
          <select onChange={(e) => update((current) => chooseService(current, e.target.value))}
                  value={form.choice}>
            {API_PROVIDERS.map((item) => (
              <option key={item.value} value={item.value}>{item.label}</option>
            ))}
          </select>
        </label>
      )}

      <label className="field-label">
        {local ? "Địa chỉ máy chủ" : "Base URL"}
        <input onChange={(e) => edit({ baseUrl: e.target.value })}
               placeholder={local ? "http://127.0.0.1:11434/v1" : "https://…/v1"}
               required value={form.baseUrl} />
      </label>

      <label className="field-label">
        Model ID
        <input onChange={(e) => update((current) => chooseModel(current, e.target.value))}
               placeholder={local ? "vd: qwen3:1.7b" : "vd: gpt-5.5, gemini-3.5-flash"}
               required value={form.modelId} />
      </label>

      {!local && (
        <label className="field-label">
          API Key
          <input
            autoComplete="off"
            disabled={!secretStoreAvailable}
            onChange={(e) => edit({ apiKey: e.target.value })}
            placeholder={secretStoreAvailable ? "Dán khóa API" : "Máy chủ chưa có kho lưu khóa"}
            type="password"
            value={form.apiKey}
          />
          <small className="evidence-meta">
            {secretStoreAvailable ? keyHint
              : "Máy chủ chưa cấu hình kho khóa: đặt khóa bằng biến môi trường ở mục Nâng cao."}
          </small>
        </label>
      )}

      <details className="ai-advanced">
        <summary>Nâng cao</summary>
        <div className="ai-advanced-body">
          <p className="evidence-meta">
            Hệ thống đã tự chọn các giá trị này theo {local ? "runtime" : "nhà cung cấp"} và model.
            Chỉ đổi khi dịch vụ yêu cầu.
          </p>
          <label className="field-label">
            Vai trò
            <select
              onChange={(e) => editAdvanced({ role: e.target.value as "text" | "embedding" })}
              value={adv.role}
            >
              <option value="text">Sinh văn bản (hỏi đáp, diễn giải, mở rộng…)</option>
              <option value="embedding">Tạo vector (embedding) cho tìm theo nghĩa</option>
            </select>
          </label>

          {embedding ? (
            <label className="field-label">
              Số chiều vector (1–4000; trống = số chiều gốc của model)
              <input max={4000} min={1} onChange={(e) => editAdvanced({
                embeddingDimensions: e.target.value })} type="number"
                value={adv.embeddingDimensions} />
            </label>
          ) : (
            <>
              <fieldset className="ai-functions">
                <legend>Chức năng được dùng</legend>
                {AI_FUNCTIONS.filter((item) => item.stage !== "embedding").map((item) => (
                  <label className="checkbox-row" key={item.stage}>
                    <input checked={adv.functions.includes(item.stage)}
                           onChange={(e) => toggleFunction(item.stage, e.target.checked)}
                           type="checkbox" />
                    <span>{item.label}</span>
                  </label>
                ))}
              </fieldset>
              <div className="admin-form-grid-2">
                <label className="field-label">
                  Nhiệt độ (0–2)
                  <input max={2} min={0} onChange={(e) => editAdvanced({
                    temperature: e.target.value })} step="0.1" type="number"
                    value={adv.temperature} />
                </label>
                <label className="field-label">
                  Token trả về tối đa (≤ 2048)
                  <input max={2048} min={1} onChange={(e) => editAdvanced({
                    maxTokens: e.target.value })} type="number" value={adv.maxTokens} />
                </label>
                <label className="field-label">
                  Mức suy luận
                  <select onChange={(e) => editAdvanced({ reasoningEffort: e.target.value })}
                          value={adv.reasoningEffort}>
                    {EFFORTS.map(([value, label]) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                </label>
                <label className="field-label">
                  Tên trường giới hạn token
                  <select onChange={(e) => editAdvanced({ tokenField: e.target.value })}
                          value={adv.tokenField}>
                    <option value="max_tokens">max_tokens</option>
                    <option value="max_completion_tokens">max_completion_tokens</option>
                  </select>
                </label>
              </div>
              <label className="checkbox-row">
                <input checked={adv.jsonMode}
                       onChange={(e) => editAdvanced({ jsonMode: e.target.checked })}
                       type="checkbox" />
                <span>Yêu cầu đầu ra JSON (chỉ bật nếu dịch vụ hỗ trợ)</span>
              </label>
            </>
          )}

          <div className="admin-form-grid-2">
            <label className="field-label">
              Phiên bản cấu hình
              <input onChange={(e) => editAdvanced({ revision: e.target.value })}
                     value={adv.revision} />
            </label>
            <label className="field-label">
              Hồ sơ dự phòng (cách nhau bằng dấu phẩy)
              <input onChange={(e) => editAdvanced({ fallback: e.target.value })}
                     value={adv.fallback} />
            </label>
          </div>
          {!local && (
            <>
              <label className="field-label">
                Dùng biến môi trường thay cho khóa nhập tay
                <input onChange={(e) => editAdvanced({ secretEnv: e.target.value })}
                       pattern="env:[A-Za-z_][A-Za-z0-9_]{0,127}"
                       placeholder="env:TEN_BIEN_MOI_TRUONG" value={adv.secretEnv} />
              </label>
              <div className="admin-form-grid-2">
                <label className="field-label">
                  Giá token vào (mỗi triệu)
                  <input min={0} onChange={(e) => editAdvanced({ inputPrice: e.target.value })}
                         step="any" type="number" value={adv.inputPrice} />
                </label>
                <label className="field-label">
                  Giá token ra (mỗi triệu)
                  <input min={0} onChange={(e) => editAdvanced({ outputPrice: e.target.value })}
                         step="any" type="number" value={adv.outputPrice} />
                </label>
                <label className="field-label">
                  Trần chi phí ngày
                  <input min={0} onChange={(e) => editAdvanced({ dailyLimit: e.target.value })}
                         step="any" type="number" value={adv.dailyLimit} />
                </label>
                <label className="field-label">
                  Trần chi phí tháng
                  <input min={0} onChange={(e) => editAdvanced({ monthlyLimit: e.target.value })}
                         step="any" type="number" value={adv.monthlyLimit} />
                </label>
              </div>
            </>
          )}
        </div>
      </details>

      {!local && (
        <p className="evidence-meta">
          Lưu hồ sơ là cho phép gửi tới nhà cung cấp này những dữ liệu đã được phép (còn phụ
          thuộc cấu hình máy chủ, danh mục và quyền của người dùng).
        </p>
      )}

      {error && <p className="status-pill status-danger" role="alert">{error}</p>}
      {busy === "test" && <p className="evidence-meta" role="status">Đang kiểm tra kết nối và gọi thử model…</p>}
      {check && <CheckResult result={check} />}

      <div className="form-actions">
        <button className="secondary-button" disabled={Boolean(busy) || Boolean(problem)}
                onClick={() => void runCheck()} type="button">
          Kiểm tra kết nối
        </button>
        <button className="primary-button" disabled={Boolean(busy) || Boolean(problem)}
                type="submit">
          {busy === "save" ? "Đang lưu…" : "Kiểm tra & Lưu"}
        </button>
        {forceOffered && (
          <button className="secondary-button" disabled={Boolean(busy)}
                  onClick={() => void save(true)} type="button">
            Vẫn lưu (chưa dùng được)
          </button>
        )}
        <button className="link-button" onClick={onCancel} type="button">Hủy</button>
      </div>
      {problem && <p className="evidence-meta">{problem}</p>}
    </form>
  );
}
