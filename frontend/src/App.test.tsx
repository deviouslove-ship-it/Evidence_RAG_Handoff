import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import App from "./App";

afterEach(() => {
  window.location.hash = "";
  vi.unstubAllGlobals();
});

it("shows the operating mode reported by the backend", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ effective_mode: "API" }), { status: 200 }),
    ),
  );
  render(<App />);
  expect(await screen.findByText("Chế độ API")).toBeInTheDocument();
  expect(screen.queryByText(/offline/)).not.toBeInTheDocument();
});

it("does not claim an offline mode when the backend is unavailable", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network unavailable")));
  render(<App />);
  expect(await screen.findByText("Chưa xác nhận chế độ")).toBeInTheDocument();
});

it("renders the circular desktop Orb when hash is #/orb", () => {
  window.location.hash = "#/orb";
  render(<App />);
  expect(
    screen.getByRole("button", { name: "Mở hoặc thu trợ lý Evidence RAG" }),
  ).toBeInTheDocument();
});

it("requires an explicit login before the standalone Desktop Orb can query", async () => {
  window.location.hash = "#/orb";
  const fetcher = vi.fn().mockImplementation(() => {
    return Promise.resolve(new Response("{}", { status: 200 }));
  });
  vi.stubGlobal("fetch", fetcher);

  render(<App />);
  const fab = await screen.findByRole("button", { name: "Mở hoặc thu trợ lý Evidence RAG" });
  expect(fab).toBeInTheDocument();
  fireEvent.click(fab);
  const drawer = screen.getByRole("region", { name: "Khung hỏi đáp nhanh Chat Agent" });
  expect(drawer).toBeInTheDocument();
  expect(
    within(drawer).getByText(/Cần đăng nhập tài khoản trước khi tra cứu/),
  ).toBeInTheDocument();

  const sampleBtn = within(drawer).getByRole("button", {
    name: "Mức xử phạt vi phạm hành chính được quy định như thế nào?",
  });
  fireEvent.click(sampleBtn);

  expect(await within(drawer).findByRole("alert")).toHaveTextContent(
    "Hãy đăng nhập tài khoản để tra cứu bằng Orb.",
  );
  expect(fetcher.mock.calls.some(([url]) => String(url).endsWith("/api/v1/auth/agent-session"))).toBe(
    false,
  );
  expect(fetcher.mock.calls.some(([url]) => String(url).endsWith("/api/v1/query/evidence"))).toBe(
    false,
  );
});

it("keeps Admin Portal hidden for a pure USER and exposes it for SYS_ADMIN", async () => {
  const fetcher = vi.fn().mockImplementation((url: string) => {
    if (url.endsWith("/api/v1/system/mode")) {
      return Promise.resolve(
        new Response(JSON.stringify({ effective_mode: "LOCAL" }), { status: 200 }),
      );
    }
    if (url.endsWith("/api/v1/auth/login")) {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            access_token: "tok_admin",
            token_type: "bearer",
            expires_at: "2026-10-23T00:00:00Z",
            user: {
              id: "00000000-0000-0000-0000-000000000001",
              username: "sysadmin",
              display_name: "Quản trị viên",
              roles: ["SYS_ADMIN", "USER"],
              permissions: ["admin.config", "rag.query"],
              must_change_password: false,
            },
          }),
          { status: 200 },
        ),
      );
    }
    if (url.endsWith("/api/v1/categories") || url.endsWith("/api/v1/admin/categories")) {
      return Promise.resolve(new Response(JSON.stringify([]), { status: 200 }));
    }
    if (url.endsWith("/api/v1/admin/users")) {
      return Promise.resolve(new Response(JSON.stringify([]), { status: 200 }));
    }
    if (url.endsWith("/api/v1/admin/model-registry")) {
      return Promise.resolve(
        new Response(JSON.stringify({ profiles: [], routes: [] }), { status: 200 }),
      );
    }
    if (url.endsWith("/api/v1/admin/audit-events")) {
      return Promise.resolve(
        new Response(
          JSON.stringify({ chain: { valid: true, checked: 1 }, events: [] }),
          { status: 200 },
        ),
      );
    }
    return Promise.resolve(new Response("{}", { status: 200 }));
  });
  vi.stubGlobal("fetch", fetcher);

  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "Đăng nhập" }));
  fireEvent.change(screen.getByLabelText("Tên đăng nhập"), { target: { value: "sysadmin" } });
  fireEvent.change(screen.getByLabelText("Mật khẩu"), { target: { value: "AdminPassword!2026" } });
  fireEvent.click(screen.getByRole("button", { name: "Đăng nhập" }));

  const adminBtn = await screen.findByRole("button", { name: "Admin Portal" });
  fireEvent.click(adminBtn);
  await waitFor(() =>
    expect(screen.getByRole("region", { name: "Tạo danh mục" })).toBeInTheDocument(),
  );
});
