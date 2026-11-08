import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AdminPortal } from "./AdminPortal";

afterEach(() => vi.unstubAllGlobals());

const ADMIN = {
  id: "admin", username: "admin", display_name: "Quản trị", roles: ["SYS_ADMIN"],
  permissions: [], must_change_password: false,
};
const PASSED = {
  ok: true, usable: true, latency_ms: 80, health: "ready", status: "ready",
  checks: [{ id: "config", status: "ok" }, { id: "connect", status: "ok" }],
};

function registryFetcher(): ReturnType<typeof vi.fn> {
  return vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    const reply = (value: unknown, status = 200) =>
      Promise.resolve(new Response(JSON.stringify(value), { status }));
    if (url.endsWith("model-registry/test")) return reply(PASSED);
    if (url.endsWith("/test")) return reply(PASSED);
    if (url.endsWith("model-registry") && init?.method === "POST") return reply({ profile_id: "x" }, 201);
    if (url.endsWith("model-registry")) {
      return reply({ profiles: [], routes: [], secret_store: { available: true } });
    }
    if (url.endsWith("audit-events")) return reply({ chain: { valid: true, checked: 0 }, events: [] });
    return reply([]);
  });
}

async function openAiTab(fetcher: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetcher);
  render(<AdminPortal accessToken="admin-fixture" currentUser={ADMIN} />);
  await waitFor(() => expect(fetcher.mock.calls.length).toBeGreaterThanOrEqual(4));
  fireEvent.click(screen.getByRole("button", { name: "Mô hình AI & Kiểm toán" }));
}

function postedPayloads(fetcher: ReturnType<typeof vi.fn>): Record<string, unknown>[] {
  return fetcher.mock.calls
    .filter(([url, init]) => String(url).endsWith("model-registry") && (init as RequestInit)?.method === "POST")
    .map(([, init]) => JSON.parse(String((init as RequestInit).body)) as Record<string, unknown>);
}

it("splits AI setup into models, assignments and embedding, and saves a local model after checking it", async () => {
  const fetcher = registryFetcher();
  await openAiTab(fetcher);
  expect(screen.getByRole("button", { name: /1\. Mô hình AI/ })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "2. Phân công AI" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /^Embedding/ })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Thêm AI Local" }));
  const form = screen.getByRole("form", { name: "Cấu hình AI Local" });
  expect(screen.queryByRole("option", { name: /Anthropic/ })).not.toBeInTheDocument();
  fireEvent.change(within(form).getByLabelText("Tên hồ sơ"), { target: { value: "configured-profile" } });
  fireEvent.change(within(form).getByLabelText("Model ID"), { target: { value: "configured-model" } });
  fireEvent.change(within(form).getByLabelText("Địa chỉ máy chủ"), { target: { value: "http://127.0.0.1:9000/v1" } });
  fireEvent.click(within(form).getByRole("button", { name: "Kiểm tra & Lưu" }));
  await waitFor(() => expect(postedPayloads(fetcher)).toHaveLength(1));
  const urls = fetcher.mock.calls.map(([url]) => String(url));
  const test = urls.findIndex((url) => url.endsWith("model-registry/test"));
  const save = fetcher.mock.calls.findIndex(([url, init]) =>
    String(url).endsWith("model-registry") && (init as RequestInit)?.method === "POST");
  expect(test).toBeGreaterThan(-1);
  expect(test).toBeLessThan(save);
  expect(postedPayloads(fetcher)[0]).toMatchObject({
    profile_id: "configured-profile", model_id: "configured-model",
    endpoint: "http://127.0.0.1:9000/v1", provider_approved: true,
  });
});

it("saves an embedding profile from the advanced role with no chat parameters", async () => {
  const fetcher = registryFetcher();
  await openAiTab(fetcher);
  fireEvent.click(screen.getByRole("button", { name: "Thêm AI Local" }));
  const form = screen.getByRole("form", { name: "Cấu hình AI Local" });
  fireEvent.change(within(form).getByLabelText("Vai trò"), { target: { value: "embedding" } });
  expect(within(form).queryByLabelText("Mức suy luận")).not.toBeInTheDocument();
  fireEvent.change(within(form).getByLabelText("Tên hồ sơ"), { target: { value: "embed-profile" } });
  fireEvent.change(within(form).getByLabelText("Model ID"), { target: { value: "embed-model" } });
  fireEvent.change(within(form).getByLabelText("Địa chỉ máy chủ"), { target: { value: "http://127.0.0.1:9001/v1" } });
  fireEvent.change(within(form).getByLabelText(/Số chiều vector/), { target: { value: "512" } });
  fireEvent.click(within(form).getByRole("button", { name: "Kiểm tra & Lưu" }));
  await waitFor(() => expect(postedPayloads(fetcher)).toHaveLength(1));
  const payload = postedPayloads(fetcher)[0] as { params: Record<string, unknown> };
  expect(payload).toMatchObject({ capabilities: ["embedding"], model_id: "embed-model" });
  expect(payload.params).toMatchObject({ json_mode: false, embedding_dimensions: 512 });
});

it("warns about a possible content duplicate after creating a PDF draft", async () => {
  const fetcher = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    if (url.endsWith("/documents/drafts") && init?.method === "POST") {
      return Promise.resolve(new Response(JSON.stringify({
        document_id: "new-doc", document_version_id: "new-version", sha256: "a".repeat(64),
        page_count: 1, node_count: 2, review_required_pages: 0, content_check_available: true,
        potential_duplicates: [{ document_version_id: "old-version", title: "Văn bản đã có",
          document_number: "01/2026", status: "draft" }],
      }), { status: 201 }));
    }
    return Promise.resolve(new Response("[]", { status: 200 }));
  });
  vi.stubGlobal("fetch", fetcher);
  render(<AdminPortal accessToken="curator-fixture" currentUser={{
    id: "curator", username: "curator", display_name: "Biên tập", roles: ["CURATOR"],
    permissions: [], must_change_password: false,
  }} />);
  fireEvent.change(screen.getByLabelText("Tiêu đề văn bản"), { target: { value: "Văn bản mới" } });
  fireEvent.change(screen.getByLabelText("Tệp văn bản gốc (PDF, Word, TXT)"), {
    target: { files: [new File(["%PDF-"], "source.pdf", { type: "application/pdf" })] },
  });
  fireEvent.submit(screen.getByRole("button", { name: "Tạo bản nháp" }).closest("form")!);
  expect(await screen.findByText(/có thể trùng nội dung/i)).toHaveTextContent("Văn bản đã có");
});

it("uploads several PDFs one at a time, keeps their metadata separate, and retries failures only", async () => {
  let releaseFirst!: (response: Response) => void;
  const firstResponse = new Promise<Response>((resolve) => { releaseFirst = resolve; });
  const sent: Array<{ filename: string; title: string; number: string | null; source: string | null }> = [];
  const fetcher = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    if (url.endsWith("/documents/drafts") && init?.method === "POST") {
      const form = init.body as FormData;
      sent.push({ filename: (form.get("file") as File).name, title: String(form.get("title")),
        number: form.get("document_number") as string | null, source: form.get("official_url") as string | null });
      if (sent.length === 1) return firstResponse;
      if (sent.length === 2) return Promise.resolve(new Response(JSON.stringify({
        code: "DUPLICATE_PDF_HASH", message: "Bản PDF này đã được nhập.",
      }), { status: 409 }));
      return Promise.resolve(new Response(JSON.stringify({
        document_id: `doc-${sent.length}`, document_version_id: `version-${sent.length}`,
        sha256: "a".repeat(64), page_count: 1, node_count: 2, review_required_pages: 0,
        content_check_available: true, potential_duplicates: [],
      }), { status: 201 }));
    }
    return Promise.resolve(new Response("[]", { status: 200 }));
  });
  vi.stubGlobal("fetch", fetcher);
  render(<AdminPortal accessToken="curator-fixture" currentUser={{
    id: "curator", username: "curator", display_name: "Biên tập", roles: ["CURATOR"],
    permissions: [], must_change_password: false,
  }} />);
  const chooser = screen.getByLabelText("Tệp văn bản gốc (PDF, Word, TXT)");
  expect(chooser).toHaveAttribute("multiple");
  fireEvent.change(chooser, { target: { files: [
    new File(["one"], "mot.pdf", { type: "application/pdf" }),
    new File(["two"], "hai.pdf", { type: "application/pdf" }),
    new File(["three"], "ba.pdf", { type: "application/pdf" }),
  ] } });
  fireEvent.change(screen.getByLabelText("Tiêu đề tệp 1"), { target: { value: "Văn bản một" } });
  fireEvent.change(screen.getByLabelText("Số hiệu tệp 1"), { target: { value: "01/2026" } });
  fireEvent.change(screen.getByLabelText("Đường dẫn nguồn tệp 2"), { target: { value: "https://example.org/two" } });
  fireEvent.submit(screen.getByRole("button", { name: /Tạo.*bản nháp/ }).closest("form")!);
  await waitFor(() => expect(sent).toHaveLength(1));
  expect(sent[0]).toEqual({ filename: "mot.pdf", title: "Văn bản một", number: "01/2026", source: null });
  releaseFirst(new Response(JSON.stringify({
    document_id: "doc-1", document_version_id: "version-1", sha256: "a".repeat(64),
    page_count: 1, node_count: 2, review_required_pages: 0, content_check_available: true,
    potential_duplicates: [],
  }), { status: 201 }));
  await waitFor(() => expect(sent).toHaveLength(3));
  expect(sent[1]).toEqual({ filename: "hai.pdf", title: "hai", number: null,
    source: "https://example.org/two" });
  expect(sent[2].filename).toBe("ba.pdf");
  const second = screen.getByRole("group", { name: "Tệp 2: hai.pdf" });
  await within(second).findByText(/Bản PDF này đã được nhập/);
  expect(within(screen.getByRole("group", { name: "Tệp 1: mot.pdf" })).getByText(/Đã lưu nháp/)).toBeInTheDocument();
  expect(within(screen.getByRole("group", { name: "Tệp 3: ba.pdf" })).getByText(/Đã lưu nháp/)).toBeInTheDocument();
  fireEvent.submit(screen.getByRole("button", { name: /Thử lại các tệp chưa thành công/ }).closest("form")!);
  await waitFor(() => expect(sent).toHaveLength(4));
  expect(sent[3].filename).toBe("hai.pdf");
});
