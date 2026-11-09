import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AdminPortal } from "./AdminPortal";

afterEach(() => vi.unstubAllGlobals());

const item = {
  id: "doc", title: "Quy định thử nghiệm", doc_type: "decree", document_number: "01/2026/NĐ-CP",
  issuing_body: "Cơ quan thử nghiệm", publication_date: "2026-10-01", review_status: "approved",
  effectivity: "active", availability: "active", version_id: "approved", version_number: 1,
  can_read: true, can_edit: true,
};

function openManagement(role: string, fetcher: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetcher);
  render(<AdminPortal accessToken="test-token" currentUser={{
    id: "staff", username: "staff", display_name: "Nhân viên", roles: [role],
    permissions: [], must_change_password: false,
  }} />);
  fireEvent.click(screen.getByRole("button", { name: "Quản lý văn bản" }));
}

function reply(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
}

it("sends document filters and page through the authenticated Admin API", async () => {
  const fetcher = vi.fn((url: string) => {
    if (url.includes("/documents?")) return reply({ items: [item], total: 26, page_size: 20 });
    if (url.endsWith("model-registry")) return reply({ profiles: [], routes: [] });
    return reply([]);
  });
  openManagement("SYS_ADMIN", fetcher);
  await screen.findByText(item.title);
  fireEvent.change(screen.getByLabelText("Tìm theo số hiệu hoặc trích yếu"), { target: { value: "01/2026" } });
  fireEvent.change(screen.getByLabelText("Cơ quan ban hành"), { target: { value: "Cơ quan thử" } });
  fireEvent.click(screen.getByRole("button", { name: "Áp dụng bộ lọc" }));
  await screen.findByText(item.title);
  fireEvent.click(screen.getByRole("button", { name: "Trang sau" }));
  await waitFor(() => expect(fetcher).toHaveBeenCalledWith(expect.stringContaining("page=2"),
    expect.objectContaining({ headers: expect.objectContaining({ Authorization: "Bearer test-token" }) })));
  const listCalls = fetcher.mock.calls.map(([url]) => url).filter((url) => url.includes("/documents?"));
  const query = new URL(listCalls.at(-1)!, "http://localhost").searchParams;
  expect(query.get("q")).toBe("01/2026");
  expect(query.get("issuing_body")).toBe("Cơ quan thử");
});

it("requires explicit confirmation and a reason before soft deleting selected documents", async () => {
  const fetcher = vi.fn((url: string, init?: RequestInit) => {
    if (url.endsWith("/documents/actions") && init?.method === "POST") return reply({ updated: 1 });
    if (url.includes("/documents?")) return reply({ items: [item], total: 1, page_size: 20 });
    if (url.endsWith("model-registry")) return reply({ profiles: [], routes: [] });
    return reply([]);
  });
  openManagement("SYS_ADMIN", fetcher);
  fireEvent.click(await screen.findByRole("checkbox", { name: `Chọn ${item.document_number}` }));
  fireEvent.click(screen.getByRole("button", { name: "Xóa mềm" }));
  const confirm = screen.getByRole("button", { name: "Xác nhận xóa mềm" });
  expect(confirm).toBeDisabled();
  expect(fetcher.mock.calls.some(([url]) => url.endsWith("/documents/actions"))).toBe(false);
  fireEvent.change(screen.getByLabelText("Lý do thao tác"), { target: { value: "Nhập nhầm" } });
  fireEvent.click(confirm);
  await screen.findByText("Đã cập nhật 1 văn bản.");
  const call = fetcher.mock.calls.find(([url]) => url.endsWith("/documents/actions"));
  expect(JSON.parse(String(call?.[1]?.body))).toEqual({
    document_ids: ["doc"], action: "delete", reason: "Nhập nhầm", confirmed: true,
  });
});

it("saves only the corrected OCR page with the current revision and opens the returned draft", async () => {
  const fetcher = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "PATCH") return reply({ version_id: "new-draft", revision: 1, status: "draft" });
    if (url.includes("/documents?")) return reply({ items: [item], total: 1, page_size: 20 });
    if (url.includes("/documents/doc?")) {
      const draft = url.includes("new-draft");
      return reply({
        document: draft ? { ...item, review_status: "draft", version_id: "new-draft", version_number: 2 } : item,
        versions: [{ id: "approved", version_number: 1, review_status: "approved" },
          ...(draft ? [{ id: "new-draft", version_number: 2, review_status: "draft" }] : [])],
        categories: [], page_count: 1, node_count: 0, nodes: [],
        page: { page_number: 1, text: draft ? "Chữ đã sửa" : "Chữ cũ", extraction_method: "local_ocr",
          text_quality: "usable", reviewed: !draft },
        embedding: { indexed_nodes: 0, total_nodes: 0, index_ready: false },
        history: [], revision: draft ? 1 : 7, open_review_tasks: 1,
        can_submit: draft, can_review: false,
      });
    }
    return reply([]);
  });
  openManagement("CURATOR", fetcher);
  fireEvent.click(await screen.findByRole("button", { name: `Chi tiết ${item.document_number}` }));
  fireEvent.click(await screen.findByRole("button", { name: "Sửa chữ OCR" }));
  fireEvent.change(screen.getByLabelText("Chữ OCR đã đối chiếu"), { target: { value: "Chữ đã sửa" } });
  fireEvent.click(screen.getByRole("button", { name: "Lưu sửa OCR" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Gửi duyệt" })).toBeEnabled());
  expect(JSON.parse(String(fetcher.mock.calls.find(([, init]) => init?.method === "PATCH")?.[1]?.body)))
    .toEqual({ revision: 7, ocr_page: { page_number: 1, text: "Chữ đã sửa" } });
});

it("keeps source controls hidden for administrative metadata-only access", async () => {
  const locked = { ...item, can_read: false, can_edit: false };
  const fetcher = vi.fn((url: string) => {
    if (url.includes("/documents?")) return reply({ items: [locked], total: 1, page_size: 20 });
    if (url.includes("/documents/doc?")) return reply({
      document: locked, versions: [], categories: [], history: [], can_submit: false, can_review: false,
    });
    if (url.endsWith("model-registry")) return reply({ profiles: [], routes: [] });
    return reply([]);
  });
  openManagement("SYS_ADMIN", fetcher);
  fireEvent.click(await screen.findByRole("button", { name: `Chi tiết ${item.document_number}` }));
  await screen.findByText("Tài khoản này chỉ có quyền xem thông tin quản lý của văn bản.");
  expect(screen.queryByRole("button", { name: "Tải tệp gốc" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Sửa thông tin" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Phê duyệt phiên bản" })).not.toBeInTheDocument();
});

it("adds a new source as a draft under the existing document and opens the new version", async () => {
  const fetcher = vi.fn((url: string, init?: RequestInit) => {
    if (url.endsWith("/documents/drafts") && init?.method === "POST") {
      return reply({ document_id: "doc", document_version_id: "new-version" });
    }
    if (url.includes("/documents?")) return reply({ items: [item], total: 1, page_size: 20 });
    if (url.includes("/documents/doc?")) {
      const created = url.includes("new-version");
      return reply({
        document: created ? { ...item, review_status: "draft", version_id: "new-version", version_number: 2 } : item,
        versions: [{ id: "approved", version_number: 1, review_status: "approved" },
          ...(created ? [{ id: "new-version", version_number: 2, review_status: "draft" }] : [])],
        categories: [], page_count: 1, node_count: 0, nodes: [], page: null, history: [], revision: 5,
        embedding: { indexed_nodes: 0, total_nodes: 0, index_ready: false }, can_submit: created, can_review: false,
      });
    }
    return reply([]);
  });
  openManagement("CURATOR", fetcher);
  fireEvent.click(await screen.findByRole("button", { name: `Chi tiết ${item.document_number}` }));
  fireEvent.click(await screen.findByRole("button", { name: "Thêm phiên bản từ tệp mới" }));
  fireEvent.change(screen.getByLabelText("Tệp nguồn của phiên bản mới (PDF, Word, TXT)"), {
    target: { files: [new File(["Điều 1"], "van-ban.txt", { type: "text/plain" })] },
  });
  const create = screen.getByRole("button", { name: "Tạo phiên bản nháp" });
  expect(create).toBeEnabled();
  fireEvent.submit(create.closest("form")!);
  await waitFor(() => expect(screen.getByLabelText("Phiên bản")).toHaveValue("new-version"));
  const form = fetcher.mock.calls.find(([, init]) => init?.method === "POST")?.[1]?.body as FormData;
  expect(form.get("document_id")).toBe("doc");
  expect(form.get("revision")).toBe("5");
  expect(form.get("title")).toBe(item.title);
  expect((form.get("file") as File).name).toBe("van-ban.txt");
});
