import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import type { ModelRegistryState } from "../../types";
import type { ModelCheckResult } from "./aiConfig";
import { AssignmentsPanel } from "./AssignmentsPanel";

afterEach(() => vi.unstubAllGlobals());

const PASS: ModelCheckResult = {
  ok: true, usable: true, health: "ready", status: "ready",
  checks: [{ id: "config", status: "ok" }, { id: "connect", status: "ok" },
    { id: "generate", status: "ok" }],
};
const DOWN: ModelCheckResult = {
  ok: false, usable: false, health: "unhealthy", status: "unhealthy",
  checks: [{ id: "config", status: "ok" }, { id: "connect", status: "fail", code: "CONNECTION_FAILED" }],
};

const REGISTRY: ModelRegistryState = {
  effective_mode: "LOCAL",
  profiles: [
    { id: "1", profile_id: "local-a", adapter: "ollama_local", endpoint: "http://127.0.0.1:11434/v1",
      provider_approved: true, model_id: "qwen3:1.7b", revision: "v1", fallback: [],
      capabilities: ["answer", "summarize", "expand", "relation", "label", "rerank"],
      privacy_zone: "internal", health: "ready" },
    { id: "2", profile_id: "local-b", adapter: "vllm_local", endpoint: "http://127.0.0.1:8000/v1",
      provider_approved: true, model_id: "qwen3-8b", revision: "v1", fallback: [],
      capabilities: ["answer", "summarize"], privacy_zone: "internal", health: "unknown" },
    { id: "3", profile_id: "cloud-a", adapter: "openai_compatible",
      endpoint: "https://api.openai.com/v1", provider_approved: true, model_id: "gpt-5.5",
      revision: "v1", fallback: [], capabilities: ["answer", "summarize"],
      privacy_zone: "public", health: "ready" },
    { id: "4", profile_id: "emb", adapter: "ollama_local", endpoint: "http://127.0.0.1:11434/v1",
      provider_approved: true, model_id: "qwen3-embedding:0.6b", revision: "v1", fallback: [],
      capabilities: ["embedding"], privacy_zone: "internal", health: "ready" },
  ],
  routes: [
    { mode: "LOCAL", stage: "answer", profile_id: "local-a", fallback: [] },
    { mode: "LOCAL", stage: "embedding", profile_id: "emb", fallback: [] },
    { mode: "API", stage: "answer", profile_id: "local-a", fallback: ["local-b"],
      escalation_profile_id: "cloud-a" },
  ],
  stage_policies: [{ mode: "LOCAL", stage: "answer", max_attempts: 3, timeout_seconds: 12 }],
};

interface Call { method: string; url: string; body: Record<string, unknown> | null }

function server(check: ModelCheckResult) {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    const path = url.replace(/^.*\/api\/v1\/admin\/model-registry/, "");
    calls.push({ method: init?.method ?? "GET", url: path,
      body: init?.body ? JSON.parse(String(init.body)) : null });
    return Promise.resolve(new Response(JSON.stringify(path.endsWith("/test") ? check : {}),
      { status: 200 }));
  }));
  return calls;
}

function mount(registry = REGISTRY) {
  const changed = vi.fn().mockResolvedValue(undefined);
  const embedding = vi.fn();
  render(<AssignmentsPanel accessToken="admin" onChanged={changed}
                           onOpenEmbedding={embedding} registry={registry} />);
  return { changed, embedding };
}

function row(stage: string): HTMLElement {
  return document.querySelector(`.ai-assignment[data-stage="${stage}"]`) as HTMLElement;
}

it("lists every function with its model and status, in the mode the server runs", () => {
  server(PASS);
  mount();
  expect(screen.getByText(/Máy chủ đang chạy chế độ/)).toHaveTextContent("LOCAL");
  const answer = row("answer");
  expect(within(answer).getByLabelText("Model cho Hỏi đáp: chọn căn cứ")).toHaveValue("local-a");
  expect(within(answer).getByText("Sẵn sàng")).toBeInTheDocument();
  expect(within(row("summarize")).getByText("Chưa phân công")).toBeInTheDocument();
  expect(row("summarize")).toHaveTextContent("chạy không dùng AI");
});

it("offers only models that can do the function and may run in the mode", () => {
  server(PASS);
  mount();
  const options = (label: string) => within(screen.getByLabelText(label))
    .getAllByRole("option").map((item) => (item as HTMLOptionElement).value);
  expect(options("Model cho Hỏi đáp: chọn căn cứ")).toEqual(["", "local-a", "local-b"]);
  expect(options("Model cho Xếp hạng lại kết quả")).toEqual(["", "local-a"]);
  fireEvent.click(screen.getByRole("button", { name: "Chế độ API" }));
  expect(options("Model cho Hỏi đáp: chọn căn cứ")).toEqual(["", "local-a", "local-b", "cloud-a"]);
});

it("keeps the embedding model out of reach: it is changed in Embedding", () => {
  server(PASS);
  const { embedding } = mount();
  const card = row("embedding");
  expect(card).toHaveTextContent("emb");
  expect(within(card).queryByRole("combobox")).not.toBeInTheDocument();
  fireEvent.click(within(card).getByRole("button", { name: "Mở mục Embedding" }));
  expect(embedding).toHaveBeenCalledOnce();
});

it("checks the model first and applies it only if it works", async () => {
  const calls = server(PASS);
  const { changed } = mount();
  const apply = within(row("summarize")).getByRole("button", { name: "Kiểm tra & Áp dụng" });
  expect(apply).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Model cho Diễn giải AI"), { target: { value: "local-b" } });
  fireEvent.click(apply);
  await waitFor(() => expect(changed).toHaveBeenCalled());
  expect(calls).toEqual([
    { method: "POST", url: "/local-b/test", body: null },
    { method: "POST", url: "/routes", body: { mode: "LOCAL", stage: "summarize",
      profile_id: "local-b", fallback: [], escalation_profile_id: null } },
  ]);
  expect(await screen.findByText(/Đã phân công local-b cho “Diễn giải AI” \(LOCAL\)/))
    .toBeInTheDocument();
});

it("does not activate a model that is down, unless the administrator overrides", async () => {
  const calls = server(DOWN);
  mount();
  fireEvent.change(screen.getByLabelText("Model cho Diễn giải AI"), { target: { value: "local-b" } });
  fireEvent.click(within(row("summarize")).getByRole("button", { name: "Kiểm tra & Áp dụng" }));
  expect(await screen.findByText(/Không kết nối được tới máy chủ/)).toBeInTheDocument();
  expect(calls.map((item) => item.url)).toEqual(["/local-b/test"]);
  fireEvent.click(screen.getByRole("button", { name: "Vẫn áp dụng (chưa dùng được)" }));
  await waitFor(() => expect(calls.map((item) => item.url)).toEqual(["/local-b/test", "/routes"]));
});

it("shows fallback and API escalation only where they apply, and keeps the saved ones", async () => {
  const calls = server(PASS);
  mount({ ...REGISTRY, effective_mode: "API" });
  const answer = row("answer");
  expect(within(answer).getByLabelText("Model API nâng cấp cho Hỏi đáp: chọn căn cứ"))
    .toHaveValue("cloud-a");
  expect(within(answer).getByLabelText("Model dự phòng cho Hỏi đáp: chọn căn cứ"))
    .toHaveValue("local-b");
  expect(within(row("expand")).queryByLabelText(/nâng cấp/)).not.toBeInTheDocument();
  // Changing the main model sends the stored fallback and escalation along.
  fireEvent.change(within(answer).getByLabelText("Model cho Hỏi đáp: chọn căn cứ"),
    { target: { value: "cloud-a" } });
  fireEvent.change(within(answer).getByLabelText("Model API nâng cấp cho Hỏi đáp: chọn căn cứ"),
    { target: { value: "" } });
  fireEvent.click(within(answer).getByRole("button", { name: "Kiểm tra & Áp dụng" }));
  await waitFor(() => expect(calls.map((item) => item.url)).toEqual(["/cloud-a/test", "/routes"]));
  expect(calls[1].body).toEqual({
    mode: "API", stage: "answer", profile_id: "cloud-a", fallback: ["local-b"],
    escalation_profile_id: null });
});

it("saves call limits of one function", async () => {
  const calls = server(PASS);
  mount();
  const answer = row("answer");
  const attempts = within(answer).getByLabelText("Số lần gửi tối đa (1–10)");
  expect(attempts).toHaveValue(3);
  expect(within(answer).getByLabelText("Thời gian chờ (giây, ≤ 30)")).toHaveValue(12);
  fireEvent.change(attempts, { target: { value: "4" } });
  fireEvent.click(within(answer).getByRole("button", { name: "Lưu giới hạn" }));
  await waitFor(() => expect(calls).toHaveLength(1));
  expect(calls[0]).toEqual({ method: "POST", url: "/policies", body: {
    mode: "LOCAL", stage: "answer", max_attempts: 4, max_output_tokens: null,
    timeout_seconds: 12, max_concurrency: null } });
});
