import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import type { ModelRegistryState } from "../../types";
import type { ModelCheckResult } from "./aiConfig";
import { ModelProfilesPanel } from "./ModelProfilesPanel";

afterEach(() => vi.unstubAllGlobals());

const GEMINI_KEY = "AIza-test-key";

const PASS: ModelCheckResult = {
  ok: true, usable: true, latency_ms: 420, health: "ready", status: "ready",
  checks: [{ id: "config", status: "ok" }, { id: "connect", status: "ok", ms: 12 },
    { id: "model", status: "ok" }, { id: "generate", status: "ok", ms: 420 },
    { id: "json", status: "ok" }],
};
const AUTH_FAILED: ModelCheckResult = {
  ok: false, usable: false,
  checks: [{ id: "config", status: "ok" }, { id: "secret", status: "ok" },
    { id: "connect", status: "fail", code: "AUTH_FAILED" }],
};

interface Call { method: string; url: string; body: Record<string, unknown> | null }

function server(
  drafts: ModelCheckResult[], saved: ModelCheckResult = PASS,
): { fetcher: ReturnType<typeof vi.fn>; calls: Call[] } {
  const calls: Call[] = [];
  const queue = [...drafts];
  const fetcher = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    const body = init?.body ? JSON.parse(String(init.body)) as Record<string, unknown> : null;
    const path = url.replace(/^.*\/api\/v1\/admin\/model-registry/, "");
    calls.push({ method: init?.method ?? "GET", url: path, body });
    const reply = (value: unknown, status = 200) =>
      Promise.resolve(new Response(JSON.stringify(value), { status }));
    if (path === "/test") return reply(queue.shift() ?? PASS);
    if (path.endsWith("/test")) return reply(saved);
    return reply({ profile_id: "x", status: "saved_unverified" }, 201);
  });
  vi.stubGlobal("fetch", fetcher);
  return { fetcher, calls };
}

const EMPTY: ModelRegistryState = { profiles: [], routes: [], secret_store: { available: true } };

function mount(registry: ModelRegistryState = EMPTY) {
  const changed = vi.fn().mockResolvedValue(undefined);
  render(<ModelProfilesPanel accessToken="admin" onChanged={changed}
                             onOpenEmbedding={vi.fn()} registry={registry} />);
  return changed;
}

it("shows only name, runtime, model and address in the AI Local form", async () => {
  const { calls } = server([PASS]);
  const changed = mount();
  fireEvent.click(screen.getByRole("button", { name: "Thêm AI Local" }));
  const form = screen.getByRole("form", { name: "Cấu hình AI Local" });
  expect(within(form).getByLabelText("Tên hồ sơ")).toBeVisible();
  expect(within(form).getByLabelText("Runtime")).toHaveValue("ollama_local");
  expect(within(form).getByLabelText("Địa chỉ máy chủ")).toHaveValue("http://127.0.0.1:11434/v1");
  expect(within(form).getByLabelText("Model ID")).toBeVisible();
  expect(within(form).queryByLabelText(/API Key/)).not.toBeInTheDocument();
  // Parameters the system chooses are behind "Nâng cao".
  for (const hidden of ["Nhiệt độ (0–2)", "Mức suy luận", "Tên trường giới hạn token",
    "Vai trò", "Phiên bản cấu hình"]) {
    expect(within(form).getByLabelText(hidden)).not.toBeVisible();
  }
  expect(within(form).queryByLabelText(/privacy|vùng dữ liệu|Adapter/i)).not.toBeInTheDocument();

  fireEvent.change(within(form).getByLabelText("Runtime"), { target: { value: "vllm_local" } });
  expect(within(form).getByLabelText("Địa chỉ máy chủ")).toHaveValue("http://127.0.0.1:8000/v1");
  fireEvent.change(within(form).getByLabelText("Tên hồ sơ"), { target: { value: "Máy GPU 1" } });
  expect(within(form).getByLabelText("Tên hồ sơ")).toHaveValue("May-GPU-1");
  fireEvent.change(within(form).getByLabelText("Model ID"), { target: { value: "qwen3-8b" } });
  fireEvent.click(within(form).getByRole("button", { name: "Kiểm tra & Lưu" }));

  await waitFor(() => expect(changed).toHaveBeenCalled());
  expect(calls.map((item) => `${item.method} ${item.url}`)).toEqual([
    "POST /test", "POST ", "POST /May-GPU-1/test"]);
  expect(calls[0].body).toEqual(calls[1].body);
  expect(calls[1].body).toMatchObject({
    profile_id: "May-GPU-1", adapter: "vllm_local", endpoint: "http://127.0.0.1:8000/v1",
    model_id: "qwen3-8b", privacy_zone: "internal", provider_approved: true,
    params: { json_mode: true, temperature: 0, max_tokens: 1024 },
  });
  expect(calls[1].body).not.toHaveProperty("api_key");
  expect(await screen.findByText(/Đã lưu hồ sơ May-GPU-1: sẵn sàng/)).toBeInTheDocument();
});

it("fills the base URL by provider, lets it be edited and sends the typed key once", async () => {
  const { calls } = server([PASS]);
  mount();
  fireEvent.click(screen.getByRole("button", { name: "Thêm AI API" }));
  const form = screen.getByRole("form", { name: "Cấu hình AI API" });
  expect(within(form).getByLabelText("Nhà cung cấp")).toHaveValue("openai");
  expect(within(form).getByLabelText("Base URL")).toHaveValue("https://api.openai.com/v1");
  expect(within(form).getByLabelText(/API Key/)).toHaveAttribute("type", "password");
  expect(within(form).queryByLabelText("Runtime")).not.toBeInTheDocument();
  fireEvent.change(within(form).getByLabelText("Nhà cung cấp"), { target: { value: "gemini" } });
  expect(within(form).getByLabelText("Base URL"))
    .toHaveValue("https://generativelanguage.googleapis.com/v1beta/openai");
  fireEvent.change(within(form).getByLabelText("Base URL"),
    { target: { value: "https://gateway.example.org/v1beta/openai" } });
  fireEvent.change(within(form).getByLabelText("Tên hồ sơ"), { target: { value: "gemini-main" } });
  fireEvent.change(within(form).getByLabelText("Model ID"), { target: { value: "gemini-3.5-flash" } });
  fireEvent.change(within(form).getByLabelText(/API Key/), { target: { value: GEMINI_KEY } });
  fireEvent.click(within(form).getByRole("button", { name: "Kiểm tra & Lưu" }));
  await waitFor(() => expect(calls).toHaveLength(3));
  const saved = calls[1].body as Record<string, unknown>;
  expect(saved).toMatchObject({
    endpoint: "https://gateway.example.org/v1beta/openai", adapter: "openai_compatible",
    privacy_zone: "public", api_key: GEMINI_KEY,
    params: { reasoning_effort: "low", json_mode: true },
  });
  expect(saved).not.toHaveProperty("secret_ref");
  // The saved-profile check that records its health sends no key.
  expect(JSON.stringify(calls[2])).not.toContain(GEMINI_KEY);
});

it("does not save a model that fails the check unless the administrator insists", async () => {
  const { calls } = server([AUTH_FAILED, AUTH_FAILED]);
  mount();
  fireEvent.click(screen.getByRole("button", { name: "Thêm AI API" }));
  const form = screen.getByRole("form", { name: "Cấu hình AI API" });
  fireEvent.change(within(form).getByLabelText("Tên hồ sơ"), { target: { value: "bad-key" } });
  fireEvent.change(within(form).getByLabelText("Model ID"), { target: { value: "gpt-5.5" } });
  fireEvent.change(within(form).getByLabelText(/API Key/), { target: { value: "wrong" } });
  fireEvent.click(within(form).getByRole("button", { name: "Kiểm tra & Lưu" }));
  expect(await screen.findByText(/Khóa API bị từ chối/)).toBeInTheDocument();
  expect(screen.getByText("Chưa dùng được")).toBeInTheDocument();
  expect(calls.map((item) => item.url)).toEqual(["/test"]);
  fireEvent.click(screen.getByRole("button", { name: "Vẫn lưu (chưa dùng được)" }));
  await waitFor(() => expect(calls.map((item) => item.url)).toEqual(["/test", "", "/bad-key/test"]));
  // Changing a field invalidates the last result and the override.
  expect(screen.queryByRole("button", { name: "Vẫn lưu (chưa dùng được)" })).not.toBeInTheDocument();
});

it("tests without saving and explains a missing model", async () => {
  const { calls } = server([{
    ok: false, usable: false, models: ["a-1", "b-2"],
    checks: [{ id: "config", status: "ok" }, { id: "connect", status: "ok", ms: 5 },
      { id: "model", status: "fail", code: "MODEL_NOT_FOUND", info: { count: 2 } }],
  }]);
  mount();
  fireEvent.click(screen.getByRole("button", { name: "Thêm AI Local" }));
  fireEvent.change(screen.getByLabelText("Tên hồ sơ"), { target: { value: "x" } });
  fireEvent.change(screen.getByLabelText("Model ID"), { target: { value: "nope" } });
  fireEvent.click(screen.getByRole("button", { name: "Kiểm tra kết nối" }));
  expect(await screen.findByText(/Model dịch vụ đang có: a-1, b-2/)).toBeInTheDocument();
  expect(calls.map((item) => item.url)).toEqual(["/test"]);
});

it("blocks saving until the fields are valid and says what is missing", () => {
  server([]);
  mount();
  fireEvent.click(screen.getByRole("button", { name: "Thêm AI Local" }));
  expect(screen.getByRole("button", { name: "Kiểm tra & Lưu" })).toBeDisabled();
  expect(screen.getByText(/Nhập tên hồ sơ/)).toBeInTheDocument();
});

it("cannot take a typed key when the server has no key store", () => {
  server([]);
  mount({ ...EMPTY, secret_store: { available: false } });
  fireEvent.click(screen.getByRole("button", { name: "Thêm AI API" }));
  expect(screen.getByLabelText(/API Key/)).toBeDisabled();
  expect(screen.getByText(/biến môi trường ở mục Nâng cao/)).toBeInTheDocument();
});

const LEGACY: ModelRegistryState = {
  secret_store: { available: true },
  profiles: [
    { id: "1", profile_id: "local-summarize", adapter: "ollama_local",
      endpoint: "http://127.0.0.1:11434/v1", provider_approved: true, model_id: "qwen3:1.7b",
      revision: "r2", capabilities: ["summarize"], privacy_zone: "internal", fallback: [],
      health: "ready", params: { temperature: 0, max_tokens: 1024,
        response_format: { type: "json_object" }, reasoning_effort: "none" } },
    { id: "2", profile_id: "cloud", adapter: "openai_compatible",
      endpoint: "https://api.openai.com/v1", provider_approved: true, model_id: "gpt-5.5",
      revision: "v1", capabilities: ["answer"], privacy_zone: "public", fallback: [],
      health: "unhealthy", secret_ref: "secret:cloud-1a2b3c4d" },
    { id: "3", profile_id: "emb", adapter: "ollama_local",
      endpoint: "http://127.0.0.1:11434/v1", provider_approved: true,
      model_id: "qwen3-embedding:0.6b", revision: "v1", capabilities: ["embedding"],
      privacy_zone: "internal", fallback: [], health: "ready" },
  ],
  routes: [{ mode: "LOCAL", stage: "summarize", profile_id: "local-summarize", fallback: [] }],
};

it("lists saved profiles by kind with status and usage", () => {
  server([]);
  mount(LEGACY);
  const local = screen.getByText("local-summarize").closest("article")!;
  expect(within(local).getByText("Sẵn sàng")).toBeInTheDocument();
  expect(local).toHaveTextContent("Ollama");
  expect(local).toHaveTextContent("đang dùng cho: Diễn giải AI (LOCAL)");
  const cloud = screen.getByText("cloud").closest("article")!;
  expect(within(cloud).getByText("Lỗi kết nối")).toBeInTheDocument();
  expect(cloud).toHaveTextContent("OpenAI");
  expect(cloud).toHaveTextContent("chưa được phân công");
  expect(screen.getByText("emb").closest("article")).toHaveTextContent("tạo vector (embedding)");
});

it("edits a saved profile without changing what was stored", async () => {
  const { calls } = server([PASS]);
  mount(LEGACY);
  fireEvent.click(within(screen.getByText("local-summarize").closest("article")!)
    .getByRole("button", { name: "Sửa" }));
  const form = screen.getByRole("form", { name: "Cấu hình AI Local" });
  expect(within(form).getByLabelText("Tên hồ sơ")).toBeDisabled();
  fireEvent.change(within(form).getByLabelText("Model ID"), { target: { value: "qwen3:4b" } });
  fireEvent.click(within(form).getByRole("button", { name: "Kiểm tra & Lưu" }));
  await waitFor(() => expect(calls).toHaveLength(3));
  expect(calls[1].body).toEqual({
    profile_id: "local-summarize", adapter: "ollama_local", endpoint: "http://127.0.0.1:11434/v1",
    model_id: "qwen3:4b", capabilities: ["summarize"], privacy_zone: "internal", revision: "r2",
    fallback: [], provider_approved: true,
    params: { json_mode: true, temperature: 0, max_tokens: 1024, reasoning_effort: "none" },
  });
});

it("keeps a stored key when an API profile is edited without retyping it", async () => {
  const { calls } = server([PASS]);
  mount(LEGACY);
  fireEvent.click(within(screen.getByText("cloud").closest("article")!)
    .getByRole("button", { name: "Sửa" }));
  const form = screen.getByRole("form", { name: "Cấu hình AI API" });
  expect(within(form).getByText(/Đã lưu một khóa \(đã che\)/)).toBeInTheDocument();
  expect(within(form).getByLabelText(/API Key/)).toHaveValue("");
  fireEvent.click(within(form).getByRole("button", { name: "Kiểm tra & Lưu" }));
  await waitFor(() => expect(calls).toHaveLength(3));
  expect(calls[1].body).toMatchObject({ secret_ref: "secret:cloud-1a2b3c4d", capabilities: ["answer"] });
  expect(calls[1].body).not.toHaveProperty("api_key");
});

it("checks a saved profile from its card and refreshes the list", async () => {
  const { calls } = server([], AUTH_FAILED);
  const changed = mount(LEGACY);
  fireEvent.click(within(screen.getByText("cloud").closest("article")!)
    .getByRole("button", { name: "Kiểm tra" }));
  expect(await screen.findByText(/Khóa API bị từ chối/)).toBeInTheDocument();
  expect(calls[0]).toMatchObject({ method: "POST", url: "/cloud/test" });
  expect(changed).toHaveBeenCalled();
});
