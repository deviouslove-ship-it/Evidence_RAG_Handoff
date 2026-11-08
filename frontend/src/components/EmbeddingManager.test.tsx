import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { EmbeddingManager } from "./EmbeddingManager";

afterEach(() => vi.unstubAllGlobals());

const job = {
  id: "job-1", index_id: "index-new", profile_id: "embed-new", model_id: "model-new",
  dimensions: 12, kind: "rebuild", status: "failed", phase: "embedding", batch_size: 16,
  total_nodes: 40, done_nodes: 10, remaining_nodes: 30, embedded_nodes: 10, percent: 25,
  rate_per_minute: 120, eta_seconds: null, failed_batches: 5, consecutive_failures: 5,
  last_error: "MODEL_UNREACHABLE",
  errors: [{ at: "2026-11-07T10:00:00Z", code: "MODEL_UNREACHABLE", detail: "16 nút" }],
  next_attempt_at: null, created_at: "2026-11-07T09:00:00Z", started_at: null,
  updated_at: null, finished_at: null,
};

function overview(jobs: unknown[]) {
  return {
    mode: "LOCAL", remote_embedding_allowed: false, route_profile_id: "embed-new",
    active_index: {
      id: "index-old", model_id: "model-old", revision: "v1", dimensions: 8,
      profile_id: "embed-old", status: "ready", is_active: true, state: "active",
      node_count: 40, storage: "vector",
    },
    eligible_nodes: 40, missing_in_active: 0,
    change: { detected: true, reason: "route_changed", profile_id: "embed-new",
      model_id: "model-new", pending_nodes: 30, open_job_id: "job-1" },
    profiles: [
      { profile_id: "embed-new", model_id: "model-new", revision: "v1",
        privacy_zone: "internal", health: "ready", provider_approved: true },
      { profile_id: "embed-old", model_id: "model-old", revision: "v1",
        privacy_zone: "internal", health: "ready", provider_approved: true },
    ],
    indices: [
      { id: "index-new", model_id: "model-new", revision: "v1", dimensions: 12,
        profile_id: "embed-new", status: "failed", is_active: false, state: "failed",
        node_count: 0, vectors: 10, storage: "vector", index_revision: 2 },
      { id: "index-old", model_id: "model-old", revision: "v1", dimensions: 8,
        profile_id: "embed-old", status: "ready", is_active: true, state: "active",
        node_count: 40, vectors: 40, storage: "vector", index_revision: 1 },
    ],
    jobs,
    worker: { enabled: true, alive: true },
  };
}

it("shows the serving index, the detected change, job progress and index states", async () => {
  const fetcher = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    if (url.endsWith("/jobs/job-1/retry") && init?.method === "POST") {
      return Promise.resolve(new Response(JSON.stringify({ ...job, status: "queued" }), { status: 200 }));
    }
    return Promise.resolve(new Response(JSON.stringify(overview([job])), { status: 200 }));
  });
  vi.stubGlobal("fetch", fetcher);
  render(<EmbeddingManager accessToken="admin" />);
  const serving = await screen.findByRole("region", { name: "Chỉ mục vector đang phục vụ" });
  expect(within(serving).getByText("model-old")).toBeInTheDocument();
  expect(within(serving).getByText(/khác model của chỉ mục đang dùng/)).toHaveTextContent("30 nút");
  const jobs = screen.getByRole("region", { name: "Tác vụ tạo vector" });
  expect(within(jobs).getByText("Lỗi")).toBeInTheDocument();
  expect(within(jobs).getByText(/10\/40 nút \(25%\)/)).toHaveTextContent("120 nút/phút");
  expect(within(jobs).getByRole("alert")).toHaveTextContent("không kết nối được dịch vụ model");
  expect(within(jobs).getByLabelText("Tiến độ embed-new")).toHaveAttribute("value", "25");
  const indices = screen.getByRole("region", { name: "Các chỉ mục vector" });
  expect(within(indices).getByText("Đang sử dụng")).toBeInTheDocument();
  expect(within(indices).getByText("Lỗi")).toBeInTheDocument();
  fireEvent.click(within(jobs).getByRole("button", { name: "Thử lại" }));
  await screen.findByText("Đã thử lại tác vụ embed-new.");
  expect(fetcher.mock.calls.some(([url, init]) => String(url).endsWith("/jobs/job-1/retry")
    && (init as RequestInit).method === "POST")).toBe(true);
});

it("requires a passing check and an explicit confirmation before queuing a rebuild", async () => {
  const preflight = {
    ok: true, profile_id: "embed-new", model_id: "model-new", revision: "v1",
    privacy_zone: "internal", rebuild: false, problems: [],
    checks: [
      { key: "connection", ok: true, detail: "Dịch vụ phản hồi", code: null },
      { key: "storage", ok: true, detail: "12 chiều", code: null },
    ],
    dimensions: 12, storage: "vector", latency_ms: 40, eligible_nodes: 40,
    already_embedded: 0, to_embed: 40, kind: "rebuild", estimated_seconds: 90, open_job: null,
  };
  const posted: Array<{ url: string; body: unknown }> = [];
  const fetcher = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      posted.push({ url, body: JSON.parse(String(init.body)) });
      if (url.endsWith("/embeddings/preflight")) {
        return Promise.resolve(new Response(JSON.stringify(preflight), { status: 200 }));
      }
      return Promise.resolve(new Response(JSON.stringify({ ...job, status: "queued",
        done_nodes: 0, remaining_nodes: 40, percent: 0 }), { status: 201 }));
    }
    return Promise.resolve(new Response(JSON.stringify(overview([])), { status: 200 }));
  });
  vi.stubGlobal("fetch", fetcher);
  render(<EmbeddingManager accessToken="admin" />);
  const form = await screen.findByRole("region", { name: "Chọn hoặc đổi model embedding" });
  expect(within(form).getByLabelText("Hồ sơ model embedding")).toHaveValue("embed-new");
  fireEvent.change(within(form).getByLabelText("Số nút mỗi lô"), { target: { value: "8" } });
  fireEvent.click(within(form).getByRole("button", { name: "Kiểm tra model" }));
  const start = await within(form).findByRole("button", { name: "Tạo vector cho 40 nút…" });
  expect(within(form).getByText(/40 nút cần tạo/)).toBeInTheDocument();
  expect(posted.filter((item) => item.url.endsWith("/embeddings/jobs"))).toHaveLength(0);
  fireEvent.click(start);
  const dialog = within(form).getByRole("alertdialog", { name: "Xác nhận tạo lại vector" });
  fireEvent.click(within(dialog).getByRole("button", { name: "Xác nhận và bắt đầu" }));
  await screen.findByText(/Đã xếp hàng tác vụ tạo vector cho 40 nút/);
  await waitFor(() => expect(posted.map((item) => item.url.split("/admin/")[1])).toEqual([
    "embeddings/preflight", "embeddings/jobs"]));
  expect(posted[0].body).toEqual({ profile_id: "embed-new", rebuild: false, batch_size: 8 });
  expect(posted[1].body).toEqual({ profile_id: "embed-new", rebuild: false, batch_size: 8,
    confirmed: true });
});
