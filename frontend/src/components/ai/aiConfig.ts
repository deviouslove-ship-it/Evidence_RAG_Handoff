import type { ModelRegistryState } from "../../types";

/**
 * Model Registry settings as the Admin Portal sees them.
 *
 * The backend contract is unchanged: a profile is adapter + endpoint + model id + roles
 * (capabilities) + privacy zone + parameters.  The simple forms ask only for what a person
 * knows (name, runtime or provider, model, address, key); everything else is derived here
 * from the choice made, and shown again only under "Nâng cao".  Editing a saved profile
 * never recomputes its stored values: they are loaded as they are and sent back unchanged.
 */

export type RegistryProfile = ModelRegistryState["profiles"][number];
export type ProfileKind = "local" | "api";

export interface ModelProfilePayload {
  profile_id: string;
  adapter: string;
  endpoint: string;
  model_id: string;
  capabilities: string[];
  privacy_zone: string;
  revision: string;
  secret_ref?: string;
  api_key?: string;
  fallback: string[];
  provider_approved: boolean;
  params: {
    temperature?: number;
    top_p?: number;
    max_tokens?: number;
    json_mode: boolean;
    reasoning_effort?: string;
    token_limit_field?: string;
    embedding_dimensions?: number;
  };
  input_price_per_mtok?: number;
  output_price_per_mtok?: number;
  daily_cost_limit?: number;
  monthly_cost_limit?: number;
}

// ---------------------------------------------------------------- functions (stages)
export interface AiFunction {
  stage: string;
  label: string;
  hint: string;
  /** Assigned here; the embedding model is changed in "Embedding" (it needs a new index). */
  editable: boolean;
  /** Hybrid Auto: an API model may be tried when the local result fails the checks. */
  escalation: boolean;
  /** Needs a private (non-public) model: never sent outside. */
  localOnly: boolean;
}

export const AI_FUNCTIONS: AiFunction[] = [
  { stage: "answer", label: "Hỏi đáp: chọn căn cứ",
    hint: "Chọn điều khoản trả lời câu hỏi của người dùng.", editable: true, escalation: true,
    localOnly: false },
  { stage: "summarize", label: "Diễn giải AI",
    hint: "Viết câu trả lời ngắn từ các căn cứ đã chọn.", editable: true, escalation: true,
    localOnly: false },
  { stage: "expand", label: "Tìm kiếm: mở rộng khái niệm",
    hint: "Gợi ý từ đồng nghĩa cho câu hỏi để tìm đủ hơn.", editable: true, escalation: false,
    localOnly: false },
  { stage: "relation", label: "Hiệu lực: nhận diện quan hệ văn bản",
    hint: "Đề xuất văn bản sửa đổi, thay thế để người duyệt xác nhận.", editable: true,
    escalation: false, localOnly: false },
  { stage: "label", label: "Phân nhóm nội dung",
    hint: "Đề xuất nhóm nội dung cho điều khoản.", editable: true, escalation: false,
    localOnly: false },
  { stage: "rerank", label: "Xếp hạng lại kết quả",
    hint: "Sắp xếp lại kết quả tìm kiếm; mặc định đang tắt.", editable: true, escalation: false,
    localOnly: true },
  { stage: "embedding", label: "Tìm theo nghĩa (embedding)",
    hint: "Tạo vector cho văn bản; đổi model ở mục Embedding để dựng lại chỉ mục.",
    editable: false, escalation: false, localOnly: true },
];

export const GENERATION_STAGES = AI_FUNCTIONS
  .filter((item) => item.stage !== "embedding").map((item) => item.stage);
/** Roles of a new API model: not rerank (reranking always runs on a local model). */
const API_STAGES = GENERATION_STAGES.filter((stage) => stage !== "rerank");

export function functionLabel(stage: string): string {
  return AI_FUNCTIONS.find((item) => item.stage === stage)?.label ?? stage;
}

// ---------------------------------------------------------------- runtimes and providers
export interface Choice { value: string; label: string; baseUrl: string }

export const LOCAL_RUNTIMES: Choice[] = [
  { value: "ollama_local", label: "Ollama", baseUrl: "http://127.0.0.1:11434/v1" },
  { value: "vllm_local", label: "vLLM", baseUrl: "http://127.0.0.1:8000/v1" },
  { value: "llama_cpp_local", label: "llama.cpp", baseUrl: "http://127.0.0.1:8080/v1" },
];
const LEGACY_RUNTIME: Choice = {
  value: "openai_compatible", label: "Khác (tương thích OpenAI)", baseUrl: "",
};

export const API_PROVIDERS: Choice[] = [
  { value: "openai", label: "OpenAI", baseUrl: "https://api.openai.com/v1" },
  { value: "gemini", label: "Google Gemini",
    baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai" },
  { value: "custom", label: "Tùy chỉnh (tương thích OpenAI)", baseUrl: "" },
];

export function runtimeChoices(current: string): Choice[] {
  return LOCAL_RUNTIMES.some((item) => item.value === current)
    ? LOCAL_RUNTIMES : [...LOCAL_RUNTIMES, LEGACY_RUNTIME];
}

export function providerFromUrl(url: string): string {
  try {
    const host = new URL(url).hostname.toLowerCase();
    if (host === "api.openai.com") return "openai";
    if (host === "generativelanguage.googleapis.com") return "gemini";
  } catch {
    // an unfinished address is a custom one
  }
  return "custom";
}

export function kindOf(profile: Pick<RegistryProfile, "privacy_zone">): ProfileKind {
  return profile.privacy_zone === "public" ? "api" : "local";
}

export function describeProfile(profile: RegistryProfile): string {
  if (kindOf(profile) === "api") {
    return API_PROVIDERS.find((item) => item.value === providerFromUrl(profile.endpoint))?.label
      ?? "API";
  }
  return [...LOCAL_RUNTIMES, LEGACY_RUNTIME].find((item) => item.value === profile.adapter)?.label
    ?? profile.adapter;
}

// ---------------------------------------------------------------- derived defaults
export interface AdvancedForm {
  role: "text" | "embedding";
  functions: string[];
  temperature: string;
  topP: number | null;
  maxTokens: string;
  reasoningEffort: string;
  tokenField: string;
  jsonMode: boolean;
  embeddingDimensions: string;
  revision: string;
  fallback: string;
  secretEnv: string;
  privacyZone: string;
  inputPrice: string;
  outputPrice: string;
  dailyLimit: string;
  monthlyLimit: string;
}

/** Models that think before answering and reject sampling parameters (GPT-5, o-series). */
const OPENAI_REASONING = /^(gpt-5|o[1-9])/i;
/** Gemini versions that accept `reasoning_effort` on the OpenAI-compatible endpoint. */
const GEMINI_THINKING = /gemini-(2\.5|[3-9])/i;

/** What the system chooses for a provider or runtime and a model id (nothing is asked). */
export function defaultAdvanced(kind: ProfileKind, key: string, modelId: string): AdvancedForm {
  const base: AdvancedForm = {
    role: "text", functions: kind === "api" ? [...API_STAGES] : [...GENERATION_STAGES],
    temperature: "0", topP: null, maxTokens: "1024", reasoningEffort: "",
    tokenField: "max_tokens", jsonMode: true, embeddingDimensions: "", revision: "v1",
    fallback: "", secretEnv: "", privacyZone: kind === "api" ? "public" : "internal",
    inputPrice: "", outputPrice: "", dailyLimit: "", monthlyLimit: "",
  };
  if (kind === "local") {
    // Ollama starts thinking models in thinking mode; short JSON answers need it off.
    return { ...base, reasoningEffort: key === "ollama_local" ? "none" : "" };
  }
  if (key === "openai") {
    const thinking = OPENAI_REASONING.test(modelId.trim());
    return { ...base, tokenField: "max_completion_tokens",
      temperature: thinking ? "" : "0", reasoningEffort: thinking ? "low" : "" };
  }
  if (key === "gemini") {
    return { ...base, reasoningEffort: GEMINI_THINKING.test(modelId.trim()) ? "low" : "" };
  }
  // An unknown service may not understand the JSON response format: do not require it.
  return { ...base, jsonMode: false };
}

// ---------------------------------------------------------------- form state
export interface ProfileForm {
  kind: ProfileKind;
  editing: boolean;
  name: string;
  /** Local: the adapter (ollama_local, vllm_local, llama_cpp_local).  API: the provider. */
  choice: string;
  baseUrl: string;
  modelId: string;
  apiKey: string;
  advanced: AdvancedForm;
  /** Once the person changed an advanced value, choices no longer rewrite it. */
  advancedTouched: boolean;
  /** Fields kept as saved when editing: reference of the stored key, adapter of an API model. */
  secretRef: string | null;
  adapter: string | null;
}

export function defaultBaseUrl(kind: ProfileKind, choice: string): string {
  return (kind === "local" ? LOCAL_RUNTIMES : API_PROVIDERS)
    .find((item) => item.value === choice)?.baseUrl ?? "";
}

export function emptyForm(kind: ProfileKind): ProfileForm {
  const choice = kind === "local" ? LOCAL_RUNTIMES[0].value : API_PROVIDERS[0].value;
  return {
    kind, editing: false, name: "", choice, baseUrl: defaultBaseUrl(kind, choice), modelId: "",
    apiKey: "", advanced: defaultAdvanced(kind, choice, ""), advancedTouched: false,
    secretRef: null, adapter: null,
  };
}

/** Profile names are identifiers: no accents, no spaces. */
export function slugName(value: string): string {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/đ/g, "d")
    .replace(/Đ/g, "D").replace(/\s+/g, "-").replace(/[^A-Za-z0-9_.:-]/g, "").slice(0, 100);
}

function withDerived(form: ProfileForm, choice: string, modelId: string): ProfileForm {
  return form.advancedTouched || form.editing
    ? form : { ...form, advanced: defaultAdvanced(form.kind, choice, modelId) };
}

/** A new runtime or provider fills the address, unless the person wrote a different one. */
export function chooseService(form: ProfileForm, choice: string): ProfileForm {
  const untouched = !form.baseUrl.trim()
    || form.baseUrl.trim() === defaultBaseUrl(form.kind, form.choice);
  return withDerived({
    ...form, choice, baseUrl: untouched ? defaultBaseUrl(form.kind, choice) : form.baseUrl,
  }, choice, form.modelId);
}

export function chooseModel(form: ProfileForm, modelId: string): ProfileForm {
  return withDerived({ ...form, modelId }, form.choice, modelId);
}

export function formFromProfile(profile: RegistryProfile): ProfileForm {
  const kind = kindOf(profile);
  const params = profile.params ?? {};
  const embedding = profile.capabilities.length === 1 && profile.capabilities[0] === "embedding";
  const str = (value: number | null | undefined) => (value != null ? String(value) : "");
  return {
    kind, editing: true, name: profile.profile_id,
    choice: kind === "local" ? profile.adapter : providerFromUrl(profile.endpoint),
    baseUrl: profile.endpoint, modelId: profile.model_id, apiKey: "",
    advancedTouched: true, secretRef: profile.secret_ref ?? null,
    adapter: profile.adapter,
    advanced: {
      role: embedding ? "embedding" : "text",
      functions: embedding ? [] : [...profile.capabilities],
      temperature: str(params.temperature), topP: params.top_p ?? null,
      maxTokens: str(params.max_tokens), reasoningEffort: params.reasoning_effort ?? "",
      tokenField: params.token_limit_field ?? "max_tokens",
      jsonMode: Boolean(params.response_format), embeddingDimensions: str(params.dimensions),
      revision: profile.revision, fallback: profile.fallback.join(", "),
      secretEnv: "", privacyZone: profile.privacy_zone,
      inputPrice: str(profile.input_price_per_mtok), outputPrice: str(profile.output_price_per_mtok),
      dailyLimit: str(profile.daily_cost_limit), monthlyLimit: str(profile.monthly_cost_limit),
    },
  };
}

function numberField<K extends string>(key: K, value: string): Partial<Record<K, number>> {
  return value.trim() ? ({ [key]: Number(value) } as Record<K, number>) : {};
}

export function buildPayload(form: ProfileForm): ModelProfilePayload {
  const adv = form.advanced;
  const embedding = adv.role === "embedding";
  const params: ModelProfilePayload["params"] = { json_mode: embedding ? false : adv.jsonMode };
  if (embedding) {
    Object.assign(params, numberField("embedding_dimensions", adv.embeddingDimensions));
  } else {
    Object.assign(params, numberField("temperature", adv.temperature),
      numberField("max_tokens", adv.maxTokens));
    if (adv.topP != null) params.top_p = adv.topP;
    if (adv.reasoningEffort) params.reasoning_effort = adv.reasoningEffort;
    if (adv.tokenField !== "max_tokens") params.token_limit_field = adv.tokenField;
  }
  const payload: ModelProfilePayload = {
    profile_id: form.name.trim(),
    adapter: form.kind === "local" ? form.choice : (form.adapter ?? "openai_compatible"),
    endpoint: form.baseUrl.trim(),
    model_id: form.modelId.trim(),
    capabilities: embedding ? ["embedding"] : adv.functions,
    privacy_zone: adv.privacyZone,
    revision: adv.revision.trim() || "v1",
    fallback: adv.fallback.split(",").map((item) => item.trim()).filter(Boolean),
    // Saving a profile from these forms is the administrator's approval of the service;
    // the server still applies its address, category and user rules on every call.
    provider_approved: true,
    params,
    ...numberField("input_price_per_mtok", adv.inputPrice),
    ...numberField("output_price_per_mtok", adv.outputPrice),
    ...numberField("daily_cost_limit", adv.dailyLimit),
    ...numberField("monthly_cost_limit", adv.monthlyLimit),
  };
  if (form.kind === "api" && form.apiKey.trim()) payload.api_key = form.apiKey.trim();
  else if (form.kind === "api" && adv.secretEnv.trim()) payload.secret_ref = adv.secretEnv.trim();
  else if (form.secretRef) payload.secret_ref = form.secretRef;
  return payload;
}

const NAME_PATTERN = /^[A-Za-z0-9_.:-]{1,100}$/;

/** First problem a person can fix before anything is sent, or null. */
export function formProblem(form: ProfileForm): string | null {
  if (!NAME_PATTERN.test(form.name)) {
    return "Nhập tên hồ sơ (chữ không dấu, số, - _ . :).";
  }
  if (!/^https?:\/\/[^\s/]+/i.test(form.baseUrl.trim())) {
    return form.kind === "local"
      ? "Địa chỉ máy chủ cần dạng http://máy:cổng/v1." : "Base URL cần dạng https://…/v1.";
  }
  if (!form.modelId.trim()) return "Nhập Model ID.";
  const adv = form.advanced;
  if (adv.role === "text" && adv.functions.length === 0) {
    return "Chọn ít nhất một chức năng cho model (Nâng cao).";
  }
  const temperature = adv.temperature.trim();
  if (adv.role === "text" && temperature && !(Number(temperature) >= 0 && Number(temperature) <= 2)) {
    return "Nhiệt độ phải từ 0 đến 2 (Nâng cao).";
  }
  const tokens = adv.maxTokens.trim();
  if (adv.role === "text" && tokens && !(Number(tokens) >= 1 && Number(tokens) <= 2048)) {
    return "Giới hạn token phải từ 1 đến 2048 (Nâng cao).";
  }
  const dims = adv.embeddingDimensions.trim();
  if (adv.role === "embedding" && dims && !(Number(dims) >= 1 && Number(dims) <= 4000)) {
    return "Số chiều vector phải từ 1 đến 4000 (Nâng cao).";
  }
  const env = adv.secretEnv.trim();
  if (env && !/^env:[A-Za-z_][A-Za-z0-9_]{0,127}$/.test(env)) {
    return "Biến môi trường cần dạng env:TEN_BIEN (Nâng cao).";
  }
  return null;
}

// ---------------------------------------------------------------- status and assignments
export type ProfileStatus = "ready" | "unchecked" | "error" | "unapproved";

export function profileStatus(profile: RegistryProfile): ProfileStatus {
  if (!profile.provider_approved) return "unapproved";
  if (profile.health === "ready") return "ready";
  return profile.health === "unhealthy" ? "error" : "unchecked";
}

export const STATUS_TEXT: Record<ProfileStatus, string> = {
  ready: "Sẵn sàng", unchecked: "Chưa kiểm tra", error: "Lỗi kết nối",
  unapproved: "Chưa cho phép",
};

/** Profiles that may be assigned to ``stage`` in ``mode``. */
export function eligibleProfiles(
  registry: ModelRegistryState, stage: string, mode: string,
): RegistryProfile[] {
  return registry.profiles.filter((profile) =>
    profile.capabilities.includes(stage)
    && (mode !== "LOCAL" || profile.privacy_zone !== "public")
    && (stage !== "embedding" || profile.privacy_zone !== "public"));
}

export function routeOf(registry: ModelRegistryState, mode: string, stage: string) {
  return registry.routes.find((route) => route.mode === mode && route.stage === stage);
}

/** Where a profile is used: ["Hỏi đáp: chọn căn cứ (LOCAL)", …]. */
export function usedBy(registry: ModelRegistryState, profileId: string): string[] {
  return registry.routes
    .filter((route) => route.profile_id === profileId
      || route.escalation_profile_id === profileId
      || route.fallback.includes(profileId))
    .map((route) => `${functionLabel(route.stage)} (${route.mode})`);
}

// ---------------------------------------------------------------- check results
export const CHECK_TITLES: Record<string, string> = {
  config: "Cấu hình hợp lệ", mode: "Chế độ máy chủ", approval: "Cho phép sử dụng",
  secret: "Khóa API", connect: "Kết nối máy chủ", model: "Có model này",
  generate: "Gọi thử model", json: "Trả lời đúng JSON", embed: "Tạo vector",
};

const CODE_TEXT: Record<string, string> = {
  ADAPTER_UNSUPPORTED: "Loại runtime/nhà cung cấp này chưa được hỗ trợ.",
  AI_ENDPOINT_INVALID: "Địa chỉ không hợp lệ: cần dạng http(s)://máy:cổng/v1 (hoặc /v1beta/openai, /openai/v1, /api/v1).",
  AI_EGRESS_DENIED: "Máy chủ chưa cho phép gọi địa chỉ này: cần HTTPS, tên miền nằm trong EVIDENCE_AI_ALLOWED_REMOTE_DOMAINS và EVIDENCE_REMOTE_PROCESSING_ALLOWED=true.",
  AI_LOCAL_ENDPOINT_DENIED: "Địa chỉ nội bộ chưa được cho phép: localhost và 127.0.0.1 luôn dùng được; máy khác trong LAN cần khai trong EVIDENCE_AI_ALLOWED_LAN_ENDPOINTS.",
  PROFILE_INVALID: "Tên hồ sơ, Model ID hoặc phiên bản không hợp lệ.",
  MODEL_CAPABILITY_UNAVAILABLE: "Hồ sơ chưa gắn chức năng nào.",
  MODEL_SECRET_REF_INVALID: "Khóa tham chiếu không hợp lệ.",
  MODEL_SECRET_UNAVAILABLE: "Không đọc được khóa API (chưa lưu, biến môi trường chưa có giá trị, hoặc khóa lưu bởi tài khoản khác). Nhập lại khóa.",
  "NO_API_KEY": "Chưa nhập khóa API; chỉ phù hợp nếu dịch vụ không yêu cầu khóa.",
  API_MODE_INACTIVE: "Máy chủ đang chạy chế độ LOCAL nên model API chưa được dùng cho đến khi chuyển sang chế độ API.",
  CONNECTION_FAILED: "Không kết nối được tới máy chủ. Kiểm tra địa chỉ, cổng và dịch vụ đã chạy chưa.",
  AUTH_FAILED: "Khóa API bị từ chối: sai khóa hoặc khóa không đủ quyền.",
  ENDPOINT_NOT_FOUND: "Không tìm thấy đường dẫn dịch vụ. Địa chỉ thường kết thúc bằng /v1.",
  MODELS_LIST_UNSUPPORTED: "Dịch vụ không có danh sách model nên chưa xác nhận được tên model; vẫn gọi thử.",
  RATE_LIMITED: "Dịch vụ giới hạn tần suất hoặc hạn mức. Thử lại sau.",
  REQUEST_REFUSED: "Dịch vụ từ chối yêu cầu.",
  RESPONSE_INVALID: "Dịch vụ trả về dữ liệu không đúng định dạng tương thích OpenAI.",
  RESPONSE_TOO_LARGE: "Phản hồi quá lớn.",
  MODEL_NOT_FOUND: "Dịch vụ không có model này. Kiểm tra lại Model ID.",
  REQUEST_PARAMS_REJECTED: "Dịch vụ từ chối tham số gọi model. Xem mục Nâng cao: mức suy luận, trường giới hạn token, ép đầu ra JSON.",
  CHAT_ENDPOINT_NOT_FOUND: "Dịch vụ không có điểm gọi chat (/chat/completions). Kiểm tra địa chỉ.",
  EMPTY_ANSWER: "Model trả lời rỗng, thường do model suy luận dùng hết số token. Tăng giới hạn token hoặc giảm mức suy luận (Nâng cao).",
  JSON_NOT_RETURNED: "Lần thử này model chưa trả JSON hợp lệ; các chức năng cần JSON có thể chập chờn.",
  PROVIDER_UNAPPROVED: "Hồ sơ chưa được cho phép sử dụng. Lưu lại hồ sơ bằng form để cho phép.",
  MODEL_STAGE_UNSUPPORTED: "Chức năng gắn cho model không hợp lệ (embedding không đi chung với chức năng khác).",
  SECRET_STORE_UNAVAILABLE: "Máy chủ chưa có kho lưu khóa (EVIDENCE_SECRET_STORE_DIR) nên không lưu được khóa nhập tay. Dùng biến môi trường ở Nâng cao.",
};

export function codeText(code: string | undefined): string {
  return (code && CODE_TEXT[code]) || (code ? `Mã lỗi: ${code}` : "");
}

export interface ModelCheck {
  id: string;
  status: "ok" | "fail" | "warn" | "skip";
  code?: string;
  ms?: number;
  info?: { dimensions?: number; count?: number };
}

export interface ModelCheckResult {
  ok: boolean;
  usable: boolean;
  checks: ModelCheck[];
  stage?: string;
  latency_ms?: number | null;
  dimensions?: number | null;
  models?: string[];
  /** Saved-profile checks only. */
  health?: string;
  status?: string;
  profile_id?: string;
}
