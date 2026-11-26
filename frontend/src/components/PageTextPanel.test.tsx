import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { PageTextEntryState } from "./pageTextIntent";
import { PageTextPanel } from "./PageTextPanel";

const state: PageTextEntryState = {
  kind: "ready",
  candidate: { document_id: "doc", document_version_id: "ver", title: "Báo cáo" },
  response: {
    status: "ready", document_id: "doc", version_id: "ver", document_title: "Báo cáo",
    page_number: 17, total_pages: 20, source_kind: "ocr_reviewed", verified: true,
    page_text: "Nội dung trang 17", pdf_url: "/api/v1/documents/doc/versions/ver/pdf",
  },
};
const callbacks = {
  onSelectCandidate: vi.fn(), onConfirmPdfPage: vi.fn(), onCancelTask: vi.fn(),
  onRequestAiRetry: vi.fn(),
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  Reflect.deleteProperty(document, "execCommand");
});

it("copies on HTTP LAN when the secure clipboard API is unavailable", async () => {
  vi.stubGlobal("navigator", { clipboard: undefined });
  const copy = vi.fn(() => true);
  Object.defineProperty(document, "execCommand", { value: copy, configurable: true });
  render(<PageTextPanel {...callbacks} accessToken="reader" state={state} />);
  fireEvent.click(screen.getByRole("button", { name: "Sao chép nội dung trang" }));
  await waitFor(() => expect(copy).toHaveBeenCalledWith("copy"));
  expect(screen.getByRole("status")).toHaveTextContent("Đã sao chép");
});

it("discards a PDF download completed after logout", async () => {
  let resolve!: (response: Response) => void;
  vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((done) => { resolve = done; })));
  const createUrl = vi.fn(() => "blob:private-page");
  vi.stubGlobal("URL", { createObjectURL: createUrl, revokeObjectURL: vi.fn() });
  const { rerender } = render(<PageTextPanel {...callbacks} accessToken="reader" state={state} />);
  fireEvent.click(screen.getByRole("button", { name: "Mở trang gốc" }));
  rerender(<PageTextPanel {...callbacks} accessToken={undefined} state={state} />);
  await act(async () => resolve(new Response("pdf", { headers: { "Content-Type": "application/pdf" } })));
  expect(createUrl).not.toHaveBeenCalled();
  expect(screen.queryByTitle("Trang gốc 17")).not.toBeInTheDocument();
});
