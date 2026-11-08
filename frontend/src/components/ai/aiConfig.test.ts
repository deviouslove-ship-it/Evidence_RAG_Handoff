import { expect, it } from "vitest";

import type { ModelRegistryState } from "../../types";
import {
  buildPayload,
  chooseModel,
  chooseService,
  defaultAdvanced,
  eligibleProfiles,
  emptyForm,
  formFromProfile,
  formProblem,
  profileStatus,
  providerFromUrl,
  slugName,
  usedBy,
  type RegistryProfile,
} from "./aiConfig";

function profile(extra: Partial<RegistryProfile> = {}): RegistryProfile {
  return {
    id: "1", profile_id: "p", adapter: "ollama_local", endpoint: "http://127.0.0.1:11434/v1",
    provider_approved: true, model_id: "m", revision: "v1", capabilities: ["answer"],
    privacy_zone: "internal", fallback: [], health: "ready", ...extra,
  };
}

it("derives hidden settings from the runtime or provider and the model id", () => {
  expect(defaultAdvanced("local", "ollama_local", "qwen3:1.7b")).toMatchObject({
    reasoningEffort: "none", temperature: "0", maxTokens: "1024", jsonMode: true,
    tokenField: "max_tokens", privacyZone: "internal", revision: "v1" });
  expect(defaultAdvanced("local", "vllm_local", "x").reasoningEffort).toBe("");
  expect(defaultAdvanced("local", "llama_cpp_local", "x").reasoningEffort).toBe("");
  // OpenAI: GPT-5 and o-series think and refuse temperature; older chat models do not.
  expect(defaultAdvanced("api", "openai", "gpt-5.5")).toMatchObject({
    tokenField: "max_completion_tokens", reasoningEffort: "low", temperature: "" });
  expect(defaultAdvanced("api", "openai", "o3-mini").reasoningEffort).toBe("low");
  expect(defaultAdvanced("api", "openai", "gpt-4o")).toMatchObject({
    tokenField: "max_completion_tokens", reasoningEffort: "", temperature: "0" });
  expect(defaultAdvanced("api", "gemini", "gemini-3.5-flash").reasoningEffort).toBe("low");
  expect(defaultAdvanced("api", "gemini", "gemini-2.0-flash").reasoningEffort).toBe("");
  expect(defaultAdvanced("api", "custom", "any")).toMatchObject({
    jsonMode: false, privacyZone: "public" });
  expect(defaultAdvanced("api", "openai", "x").functions).not.toContain("rerank");
  expect(defaultAdvanced("local", "ollama_local", "x").functions).toContain("rerank");
});

it("fills the address from the provider but never overwrites one the person wrote", () => {
  let form = emptyForm("api");
  expect(form.baseUrl).toBe("https://api.openai.com/v1");
  form = chooseService(form, "gemini");
  expect(form.baseUrl).toBe("https://generativelanguage.googleapis.com/v1beta/openai");
  form = { ...form, baseUrl: "https://proxy.example.org/v1" };
  expect(chooseService(form, "openai").baseUrl).toBe("https://proxy.example.org/v1");
  expect(chooseService({ ...form, baseUrl: "" }, "openai").baseUrl).toBe("https://api.openai.com/v1");
  const local = chooseService(emptyForm("local"), "vllm_local");
  expect(local.baseUrl).toBe("http://127.0.0.1:8000/v1");
  expect(chooseService(local, "llama_cpp_local").baseUrl).toBe("http://127.0.0.1:8080/v1");
});

it("recomputes hidden settings from the model only until the person touches them", () => {
  const form = chooseModel(chooseService(emptyForm("api"), "openai"), "gpt-5.5");
  expect(form.advanced.reasoningEffort).toBe("low");
  const touched = { ...form, advancedTouched: true,
    advanced: { ...form.advanced, reasoningEffort: "high" } };
  expect(chooseModel(touched, "gpt-4o").advanced.reasoningEffort).toBe("high");
  const editing = formFromProfile(profile({ params: { reasoning_effort: "none" } }));
  expect(chooseModel(editing, "another").advanced.reasoningEffort).toBe("none");
});

it("turns a profile name into a valid identifier", () => {
  expect(slugName("Máy Ollama số 1 – Đà Nẵng")).toBe("May-Ollama-so-1--Da-Nang");
  expect(slugName("a:b_c.d-e")).toBe("a:b_c.d-e");
});

it("builds the payload of a new local profile with nothing asked beyond the four fields", () => {
  const form = { ...emptyForm("local"), name: "ollama-qwen", modelId: "qwen3:1.7b" };
  expect(buildPayload(form)).toEqual({
    profile_id: "ollama-qwen", adapter: "ollama_local", endpoint: "http://127.0.0.1:11434/v1",
    model_id: "qwen3:1.7b", capabilities: ["answer", "summarize", "expand", "relation", "label", "rerank"],
    privacy_zone: "internal", revision: "v1", fallback: [], provider_approved: true,
    params: { json_mode: true, temperature: 0, max_tokens: 1024, reasoning_effort: "none" },
  });
});

const TYPED_KEY = "sk-test";

it("sends a typed key as api_key and otherwise keeps the stored reference", () => {
  const base = { ...chooseModel(emptyForm("api"), "gpt-5.5"), name: "openai-main" };
  const typed = buildPayload({ ...base, apiKey: `  ${TYPED_KEY}  ` });
  expect(typed).toMatchObject({ adapter: "openai_compatible", privacy_zone: "public",
    endpoint: "https://api.openai.com/v1", api_key: TYPED_KEY });
  expect(typed.secret_ref).toBeUndefined();
  expect(typed.capabilities).not.toContain("rerank");
  expect(typed.params).toEqual({ json_mode: true, max_tokens: 1024,
    reasoning_effort: "low", token_limit_field: "max_completion_tokens" });
  const env = buildPayload({ ...base, advanced: { ...base.advanced, secretEnv: "env:MY_KEY" } });
  expect(env.secret_ref).toBe("env:MY_KEY");
  expect(env.api_key).toBeUndefined();
  const kept = buildPayload({ ...base, secretRef: "secret:openai-main-1a2b3c4d" });
  expect(kept.secret_ref).toBe("secret:openai-main-1a2b3c4d");
  expect(kept.api_key).toBeUndefined();
});

it("loads a saved profile as stored and sends it back unchanged", () => {
  const legacy = profile({
    profile_id: "local-summarize", capabilities: ["summarize"], privacy_zone: "restricted",
    adapter: "openai_compatible", revision: "r7", fallback: ["other"],
    secret_ref: "env:LAN_KEY",
    params: { temperature: 0, top_p: 0.9, max_tokens: 777, response_format: { type: "json_object" },
      reasoning_effort: "none" },
    input_price_per_mtok: 1.5,
  });
  const form = formFromProfile(legacy);
  expect(form).toMatchObject({ kind: "local", editing: true, choice: "openai_compatible" });
  expect(buildPayload(form)).toEqual({
    profile_id: "local-summarize", adapter: "openai_compatible", endpoint: legacy.endpoint,
    model_id: "m", capabilities: ["summarize"], privacy_zone: "restricted", revision: "r7",
    fallback: ["other"], provider_approved: true, secret_ref: "env:LAN_KEY",
    params: { json_mode: true, temperature: 0, top_p: 0.9, max_tokens: 777,
      reasoning_effort: "none" },
    input_price_per_mtok: 1.5,
  });
  const embedding = formFromProfile(profile({
    capabilities: ["embedding"], params: { dimensions: 1024 } }));
  expect(buildPayload(embedding)).toMatchObject({
    capabilities: ["embedding"], params: { json_mode: false, embedding_dimensions: 1024 } });
});

it("names the first problem a person can fix", () => {
  const ok = { ...emptyForm("local"), name: "a", modelId: "m" };
  expect(formProblem(ok)).toBeNull();
  expect(formProblem({ ...ok, name: "" })).toMatch(/tên hồ sơ/i);
  expect(formProblem({ ...ok, baseUrl: "127.0.0.1:11434" })).toMatch(/http/);
  expect(formProblem({ ...emptyForm("api"), name: "a", modelId: "m", baseUrl: "x" }))
    .toMatch(/Base URL/);
  expect(formProblem({ ...ok, modelId: " " })).toMatch(/Model ID/);
  expect(formProblem({ ...ok, advanced: { ...ok.advanced, functions: [] } })).toMatch(/chức năng/);
  expect(formProblem({ ...ok, advanced: { ...ok.advanced, temperature: "3" } })).toMatch(/Nhiệt độ/);
  expect(formProblem({ ...ok, advanced: { ...ok.advanced, maxTokens: "9999" } })).toMatch(/token/);
  expect(formProblem({ ...ok, advanced: { ...ok.advanced, secretEnv: "sk-raw" } })).toMatch(/env:/);
});

it("classifies services, status, eligibility and usage", () => {
  expect(providerFromUrl("https://api.openai.com/v1")).toBe("openai");
  expect(providerFromUrl("https://generativelanguage.googleapis.com/v1beta/openai")).toBe("gemini");
  expect(providerFromUrl("https://llm.example.org/v1")).toBe("custom");
  expect(providerFromUrl("not a url")).toBe("custom");
  expect(profileStatus(profile())).toBe("ready");
  expect(profileStatus(profile({ health: "unknown" }))).toBe("unchecked");
  expect(profileStatus(profile({ health: "unhealthy" }))).toBe("error");
  expect(profileStatus(profile({ provider_approved: false }))).toBe("unapproved");
  const registry: ModelRegistryState = {
    profiles: [
      profile({ profile_id: "local", capabilities: ["answer", "summarize"] }),
      profile({ profile_id: "cloud", privacy_zone: "public", capabilities: ["answer"] }),
      profile({ profile_id: "emb", capabilities: ["embedding"] }),
    ],
    routes: [{ mode: "LOCAL", stage: "answer", profile_id: "local", fallback: [] },
      { mode: "API", stage: "summarize", profile_id: "cloud", fallback: ["local"],
        escalation_profile_id: null }],
  };
  expect(eligibleProfiles(registry, "answer", "LOCAL").map((p) => p.profile_id)).toEqual(["local"]);
  expect(eligibleProfiles(registry, "answer", "API").map((p) => p.profile_id))
    .toEqual(["local", "cloud"]);
  expect(eligibleProfiles(registry, "embedding", "API").map((p) => p.profile_id)).toEqual(["emb"]);
  expect(usedBy(registry, "local")).toEqual([
    "Hỏi đáp: chọn căn cứ (LOCAL)", "Diễn giải AI (API)"]);
});
