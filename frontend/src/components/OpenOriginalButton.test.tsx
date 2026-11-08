import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { OpenOriginalButton } from "./OpenOriginalButton";

const URL_OK = "/api/v1/citations/ev_aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/original?as_of_date=2026-11-08";

beforeEach(() => {
  vi.stubGlobal("URL", Object.assign(URL, {
    createObjectURL: vi.fn(() => "blob:test/1"), revokeObjectURL: vi.fn(),
  }));
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

it("opens the original PDF in a separate tab at the cited page with the caller's token", async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response(new Blob(["%PDF-1.4"]), {
    status: 200, headers: { "Content-Type": "application/pdf", "X-Source-Format": "pdf",
                            "Content-Disposition": "inline; filename=\"a.pdf\"" },
  }));
  vi.stubGlobal("fetch", fetcher);
  const tab = { closed: false, opener: {}, document: { title: "", body: { textContent: "" } },
                location: { href: "" }, close: vi.fn() };
  const open = vi.spyOn(window, "open").mockReturnValue(tab as unknown as Window);
  render(<OpenOriginalButton accessToken="token" page={7} sourceFormat="pdf" url={URL_OK} />);
  fireEvent.click(screen.getByRole("button", { name: "Mở văn bản gốc" }));
  await waitFor(() => expect(tab.location.href).toBe("blob:test/1#page=7"));
  expect(open).toHaveBeenCalledWith("", "_blank");
  expect(tab.opener).toBeNull();
  const init = fetcher.mock.calls[0][1] as RequestInit;
  expect(new Headers(init.headers).get("Authorization")).toBe("Bearer token");
});

it("downloads a Word original under its own name instead of a converted PDF", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(new Blob(["doc"]), {
    status: 200, headers: {
      "Content-Type": "application/msword", "X-Source-Format": "doc",
      "Content-Disposition": "attachment; filename=\"x.doc\"; filename*=UTF-8''Th%C3%B4ng%20t%C6%B0.doc",
    },
  })));
  const open = vi.spyOn(window, "open");
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    expect(this.download).toBe("Thông tư.doc");
  });
  render(<OpenOriginalButton accessToken="token" sourceFormat="doc" url={URL_OK} />);
  expect(screen.getByText("Tải tệp gốc Word (.doc)")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Mở văn bản gốc" }));
  await waitFor(() => expect(click).toHaveBeenCalled());
  expect(open).not.toHaveBeenCalled();
});

it("refuses to send credentials outside the citation route", async () => {
  const fetcher = vi.fn();
  vi.stubGlobal("fetch", fetcher);
  render(<OpenOriginalButton accessToken="token" sourceFormat="doc" url="https://evil.example/x" />);
  fireEvent.click(screen.getByRole("button", { name: "Mở văn bản gốc" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Đường dẫn tệp gốc không hợp lệ.");
  expect(fetcher).not.toHaveBeenCalled();
});
