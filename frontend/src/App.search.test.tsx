import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import App from "./App";

afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
  window.location.hash = "";
});

it("opens the document search view from the user portal navigation", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) => {
      if (String(url).endsWith("/api/v1/system/mode")) {
        return Promise.resolve(
          new Response(JSON.stringify({ effective_mode: "LOCAL" }), { status: 200 }),
        );
      }
      return Promise.resolve(new Response("{}", { status: 200 }));
    }),
  );
  render(<App />);

  fireEvent.click(await screen.findByRole("button", { name: "Tìm kiếm văn bản" }));

  expect(screen.getByRole("heading", { name: "Tìm kiếm văn bản" })).toBeInTheDocument();
  expect(
    screen.getByText("Đăng nhập để tìm kiếm trong văn bản đã duyệt."),
  ).toBeInTheDocument();
});
