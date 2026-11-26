import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { OcrAiPanel } from "./OcrAiPanel";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

it("ignores a late apply response after switching documents", async () => {
  let resolveApply!: (response: Response) => void;
  const pendingApply = new Promise<Response>((resolve) => { resolveApply = resolve; });
  vi.stubGlobal("fetch", vi.fn((url: string) => url.endsWith("/apply")
    ? pendingApply
    : Promise.resolve(new Response(JSON.stringify({
      proposal_id: "old-proposal", status: "ready", stale: false,
      candidate_text: "Chữ trang cũ", current_page_text: "Chữ cũ",
    })))));
  const onApplied = vi.fn();
  const props = { accessToken: "curator", documentId: "doc-1", versionId: "ver-1",
    pageNumber: 1, revision: 1, currentText: "Chữ cũ", onApplied };
  const { rerender } = render(<OcrAiPanel {...props} />);
  fireEvent.click(screen.getByRole("button", { name: "Đọc lại trang này bằng OCR AI" }));
  await screen.findByLabelText("Chữ OCR AI để áp dụng");
  fireEvent.click(screen.getByRole("button", { name: "Áp dụng đề xuất vào bản nháp" }));
  rerender(<OcrAiPanel {...props} documentId="doc-2" versionId="ver-2" />);
  await act(async () => { resolveApply(new Response(JSON.stringify({
    version_id: "old-result", revision: 2, status: "draft",
    proposal: { status: "applied", proposal_id: "old-proposal" },
  }))); });
  expect(onApplied).not.toHaveBeenCalled();
  expect(screen.queryByLabelText("Chữ OCR AI để áp dụng")).not.toBeInTheDocument();
});

it("sends a valid UUID on HTTP LAN without crypto.randomUUID", async () => {
  vi.stubGlobal("crypto", { getRandomValues: crypto.getRandomValues.bind(crypto) });
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: "failed" })));
  vi.stubGlobal("fetch", fetcher);
  render(<OcrAiPanel accessToken="curator" documentId="doc" versionId="ver" pageNumber={1}
    revision={1} currentText="Chữ cũ" onApplied={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "Đọc lại trang này bằng OCR AI" }));
  await waitFor(() => expect(fetcher).toHaveBeenCalled());
  const payload = JSON.parse(fetcher.mock.calls[0][1].body);
  expect(payload.request_id).toMatch(/^[\da-f]{8}-[\da-f]{4}-4[\da-f]{3}-[89ab][\da-f]{3}-[\da-f]{12}$/i);
});

it("OcrAiPanel: escapes model text and handles logout", async () => {
  const xssText = '<img src=x onerror="window.__xss=1"> Điều 1. Văn bản sạch';
  const xssWarning = '<script>window.__xssWarn=1</script> Chữ mờ góc phải';
  const xssUnreadable = '<b>[mất chữ]</b>';
  let pollCalls = 0;

  const fetcher = vi.fn().mockImplementation((url: string) => {
    if (url.endsWith("/ocr-ai")) {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            proposal_id: "prop-1",
            purpose: "admin_correction",
            document_id: "doc-1",
            version_id: "ver-1",
            page_number: 1,
            source_review_revision: 3,
            status: "queued",
            stale: false,
          }),
          { status: 202 },
        ),
      );
    }
    if (url === "/api/v1/admin/ocr-ai/prop-1") {
      pollCalls += 1;
      if (pollCalls === 1) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              proposal_id: "prop-1",
              purpose: "admin_correction",
              document_id: "doc-1",
              version_id: "ver-1",
              page_number: 1,
              source_review_revision: 3,
              status: "queued",
              stale: false,
            }),
            { status: 200 },
          ),
        );
      }
      return Promise.resolve(
        new Response(
          JSON.stringify({
            proposal_id: "prop-1",
            purpose: "admin_correction",
            document_id: "doc-1",
            version_id: "ver-1",
            page_number: 1,
            source_review_revision: 3,
            status: "ready",
            stale: false,
            candidate: {
              blocks: [{ kind: "text", text: xssText }],
              warnings: [xssWarning],
              unreadable: [xssUnreadable],
            },
            candidate_text: xssText,
            current_page_text: "Chữ cũ",
            diff: [
              { op: "delete", text: "Chữ cũ" },
              { op: "insert", text: xssText },
            ],
          }),
          { status: 200 },
        ),
      );
    }
    if (url === "/api/v1/admin/ocr-ai/prop-1/apply") {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            version_id: "ver-2",
            revision: 4,
            status: "draft",
            proposal: {
              proposal_id: "prop-1",
              purpose: "admin_correction",
              document_id: "doc-1",
              version_id: "ver-1",
              page_number: 1,
              source_review_revision: 3,
              status: "applied",
              stale: false,
              applied_version_id: "ver-2",
            },
          }),
          { status: 200 },
        ),
      );
    }
    return Promise.resolve(new Response("{}", { status: 200 }));
  });
  vi.stubGlobal("fetch", fetcher);

  const onApplied = vi.fn();
  const { container, rerender } = render(
    <OcrAiPanel
      accessToken="curator-token"
      currentText="Chữ cũ"
      documentId="doc-1"
      onApplied={onApplied}
      pageNumber={1}
      revision={3}
      versionId="ver-1"
    />,
  );

  // Trigger OCR AI proposal while checking logout cleanup from queued state first.
  fireEvent.click(screen.getByRole("button", { name: "Đọc lại trang này bằng OCR AI" }));
  await screen.findByText(/Đang đọc ảnh trang 1 bằng OCR AI/);

  // Simulate logout (accessToken cleared): resets panel state and stops pending polling.
  rerender(
    <OcrAiPanel
      accessToken=""
      currentText="Chữ cũ"
      documentId="doc-1"
      onApplied={onApplied}
      pageNumber={1}
      revision={3}
      versionId="ver-1"
    />,
  );
  expect(screen.queryByRole("status")).not.toBeInTheDocument();

  // Re-login and drive to ready -> apply, checking escaped DOM rendering.
  rerender(
    <OcrAiPanel
      accessToken="curator-token-2"
      currentText="Chữ cũ"
      documentId="doc-1"
      onApplied={onApplied}
      pageNumber={1}
      revision={3}
      versionId="ver-1"
    />,
  );
  pollCalls = 0;
  fireEvent.click(screen.getByRole("button", { name: "Đọc lại trang này bằng OCR AI" }));
  await screen.findByLabelText("Chữ OCR AI để áp dụng", {}, { timeout: 4000 });

  // Verify raw HTML strings were escaped and zero <script> or <img> elements were injected.
  expect(container.querySelector("script")).toBeNull();
  expect(container.querySelector("img")).toBeNull();
  expect(container.textContent).toContain(xssText);
  expect(container.textContent).toContain(xssWarning);
  expect(container.textContent).toContain(xssUnreadable);

  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Áp dụng đề xuất vào bản nháp" }));
  });
  await waitFor(() => expect(onApplied).toHaveBeenCalledTimes(1));
  expect(onApplied).toHaveBeenCalledWith(expect.objectContaining({ version_id: "ver-2", revision: 4 }));
});
