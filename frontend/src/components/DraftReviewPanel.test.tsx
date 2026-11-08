import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { DraftReviewPanel } from "./DraftReviewPanel";

afterEach(() => vi.unstubAllGlobals());

it("requires the source PDF and a review note before resolving a real task", async () => {
  URL.createObjectURL = vi.fn(() => "blob:review-fixture");
  URL.revokeObjectURL = vi.fn();
  let resolved = false;
  const fetcher = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    if (url.endsWith("/pdf")) return Promise.resolve(new Response("%PDF-", {
      status: 200, headers: { "Content-Type": "application/pdf" },
    }));
    if (url.endsWith("/resolve")) {
      resolved = true;
      expect(JSON.parse(String(init?.body)).resolution_note).toBe("Đã kiểm tra từng trang.");
      return Promise.resolve(new Response("{}", { status: 200 }));
    }
    return Promise.resolve(new Response(JSON.stringify(resolved ? [] : [{
      id: "task-one", reason: "source_review_required", risk: "high", status: "open",
    }]), { status: 200 }));
  });
  vi.stubGlobal("fetch", fetcher);
  const updated = vi.fn().mockResolvedValue(undefined);
  render(<DraftReviewPanel accessToken="reviewer-fixture" canResolve canReextract={false} onUpdated={updated} draft={{
    document_id: "doc", document_version_id: "version", title: "Nguồn chờ duyệt",
    doc_type: "decree", status: "pending_review", sha256: "a".repeat(64), page_count: 1,
    open_review_tasks: 1,
  }} />);
  const resolve = await screen.findByRole("button", { name: "Ghi nhận đã xử lý tác vụ" });
  expect(resolve).toBeDisabled();
  await screen.findByTitle("PDF chờ duyệt: Nguồn chờ duyệt");
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "Đã kiểm tra từng trang." } });
  await waitFor(() => expect(resolve).toBeEnabled());
  fireEvent.click(resolve);
  await waitFor(() => expect(updated).toHaveBeenCalledOnce());
  expect(screen.queryByRole("button", { name: "Ghi nhận đã xử lý tác vụ" })).not.toBeInTheDocument();
});

it("lets a curator re-extract the stored PDF without approving its source", async () => {
  URL.createObjectURL = vi.fn(() => "blob:review-fixture");
  URL.revokeObjectURL = vi.fn();
  const fetcher = vi.fn().mockImplementation((url: string) => {
    if (url.endsWith("/pdf")) return Promise.resolve(new Response("%PDF-", {
      status: 200, headers: { "Content-Type": "application/pdf" },
    }));
    if (url.endsWith("/reextract")) return Promise.resolve(new Response(JSON.stringify({
      status: "draft_updated", pages_restored: 1, nodes_anchored: 10,
      nodes_unresolved: 2, possible_duplicates: 0,
    }), { status: 200 }));
    return Promise.resolve(new Response("[]", { status: 200 }));
  });
  vi.stubGlobal("fetch", fetcher);
  const updated = vi.fn().mockResolvedValue(undefined);
  render(<DraftReviewPanel accessToken="curator-fixture" canResolve={false} canReextract onUpdated={updated} draft={{
    document_id: "doc", document_version_id: "version", title: "Nguồn cũ",
    doc_type: "decree", status: "draft", sha256: "a".repeat(64), page_count: 1,
    open_review_tasks: 1,
  }} />);
  await screen.findByTitle("PDF chờ duyệt: Nguồn cũ");
  fireEvent.click(screen.getByRole("button", { name: "Trích xuất lại PDF gốc" }));
  expect(await screen.findByText(/còn 2 đoạn chưa gắn trang/i)).toBeInTheDocument();
  expect(updated).toHaveBeenCalledOnce();
  expect(fetcher.mock.calls.some(([url]) => String(url).endsWith("/reextract"))).toBe(true);
});

it("shows the OCR text, its warnings and the scan page before a page is confirmed", async () => {
  URL.createObjectURL = vi.fn(() => "blob:review-fixture");
  URL.revokeObjectURL = vi.fn();
  vi.stubGlobal("fetch", vi.fn().mockImplementation((url: string) => {
    if (url.endsWith("/pdf")) return Promise.resolve(new Response("%PDF-", {
      status: 200, headers: { "Content-Type": "application/pdf" },
    }));
    if (url.includes("/review-tasks")) return Promise.resolve(new Response(JSON.stringify([{
      id: "page-task", reason: "page_2_needs_review", risk: "high", status: "open",
      page: { page_number: 2, extraction_method: "local_ocr", text_quality: "needs_review",
              text: "1. B6 sung khoản 3", text_truncated: false,
              ocr_diagnostics: { words: 4, mean_confidence: 94.6, low_confidence_share: 0.01,
                                 suspect_tokens: ["B6"], suspect_markers: ["1) Buộc nộp"],
                                 flags: ["SUSPECT_CHARACTERS", "SUSPECT_POINT_MARKERS"] } },
    }]), { status: 200 }));
    return Promise.resolve(new Response("[]", { status: 200 }));
  }));
  render(<DraftReviewPanel accessToken="reviewer-fixture" canResolve canReextract={false}
    onUpdated={vi.fn().mockResolvedValue(undefined)} draft={{
      document_id: "doc", document_version_id: "version", title: "Bản scan",
      doc_type: "decree", status: "pending_review", sha256: "a".repeat(64), page_count: 2,
      open_review_tasks: 1,
    }} />);
  expect(await screen.findByText(/Trang 2: chữ do OCR đọc từ bản scan/)).toBeInTheDocument();
  expect(screen.getByText(/Từ nghi đọc sai: B6/)).toBeInTheDocument();
  expect(screen.getByText(/ký hiệu điểm có thể bị đọc nhầm/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Xác nhận chữ trang 2 khớp bản gốc" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Xem trang 2 của bản scan" }));
  expect(await screen.findByTitle("PDF chờ duyệt: Bản scan"))
    .toHaveAttribute("src", "blob:review-fixture#page=2");
});

it("shows authorized potential duplicate sources for review", async () => {
  URL.createObjectURL = vi.fn(() => "blob:review-fixture");
  URL.revokeObjectURL = vi.fn();
  vi.stubGlobal("fetch", vi.fn().mockImplementation((url: string) => {
    if (url.endsWith("/pdf")) return Promise.resolve(new Response("%PDF-", {
      status: 200, headers: { "Content-Type": "application/pdf" },
    }));
    if (url.endsWith("/duplicates")) return Promise.resolve(new Response(JSON.stringify({
      content_check_available: true,
      potential_duplicates: [{ document_version_id: "other", title: "Nguồn tương tự",
        document_number: "02/2026", status: "draft" }],
    }), { status: 200 }));
    return Promise.resolve(new Response("[]", { status: 200 }));
  }));
  render(<DraftReviewPanel accessToken="reviewer-fixture" canResolve canReextract={false}
    onUpdated={vi.fn().mockResolvedValue(undefined)} draft={{
      document_id: "doc", document_version_id: "version", title: "Nguồn đang duyệt",
      doc_type: "decree", status: "pending_review", sha256: "a".repeat(64), page_count: 1,
      open_review_tasks: 1,
    }} />);
  expect(await screen.findByText(/Nguồn tương tự/)).toHaveTextContent("02/2026");
});
