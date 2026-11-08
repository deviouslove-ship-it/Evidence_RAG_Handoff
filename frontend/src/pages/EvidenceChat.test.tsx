import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import * as localDate from "../localDate";
import { EvidenceChat } from "./EvidenceChat";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const SESSION = {
  session_id: "11111111-1111-4111-8111-111111111111",
  persistence_state: "ephemeral",
  expires_at: "2099-01-01T00:00:00+00:00",
  facts_revision: "factrev_1",
  memory_revision: "memoryrev_1",
};

function sse(events: Array<[string, Record<string, unknown>]>): string {
  return events
    .map(([name, data], index) =>
      `id: q:r:${index + 1}\nevent: ${name}\ndata: ${JSON.stringify(data)}\n\n`)
    .join("");
}

function baseRoutes(url: string): Response | undefined {
  if (url.endsWith("/api/v1/categories")) return new Response("[]", { status: 200 });
  if (url.includes("/api/v1/agent/sessions") && url.endsWith("/api/v1/agent/sessions")) {
    return new Response(JSON.stringify(SESSION), { status: 201 });
  }
  if (url.includes("/api/v1/memory/preferences")) {
    return new Response(JSON.stringify({
      enabled: false, default_category_ids: [], default_as_of_date: null,
    }), { status: 200 });
  }
  if (url.includes("/api/v1/memory")) {
    return new Response(JSON.stringify({ items: [] }), { status: 200 });
  }
  return undefined;
}

it("refreshes the default date across days but keeps a date the user chose", async () => {
  const today = vi.spyOn(localDate, "localDateISO").mockReturnValue("2026-10-27");
  vi.stubGlobal("fetch", vi.fn().mockImplementation((url: string) => {
    if (url.endsWith("/api/v1/categories")) return Promise.resolve(new Response(JSON.stringify([
      { id: "cat-1", code: "C1", name: "Danh mục A", remote_processing_allowed: false },
    ]), { status: 200 }));
    return Promise.resolve(baseRoutes(url) ?? new Response("{}", { status: 200 }));
  }));
  render(<EvidenceChat accessToken="fixture-token" />);
  const date = await screen.findByLabelText("Ngày hiệu lực");
  expect(date).toHaveValue("2026-10-27");
  today.mockReturnValue("2026-10-28");
  fireEvent.focus(window);
  expect(date).toHaveValue("2026-10-28");
  fireEvent.change(date, { target: { value: "2025-04-10" } });
  today.mockReturnValue("2026-10-29");
  fireEvent.focus(window);
  expect(date).toHaveValue("2025-04-10");
});

it("uses today's date on submit even if the window was not refocused", async () => {
  const today = vi.spyOn(localDate, "localDateISO").mockReturnValue("2026-10-27");
  const fetcher = vi.fn().mockImplementation((url: string) => {
    if (url.endsWith("/api/v1/categories")) return Promise.resolve(new Response(JSON.stringify([
      { id: "cat-1", code: "C1", name: "Danh mục A", remote_processing_allowed: false },
    ]), { status: 200 }));
    return Promise.resolve(baseRoutes(url) ?? new Response("{}", { status: 500 }));
  });
  vi.stubGlobal("fetch", fetcher);
  render(<EvidenceChat accessToken="fixture-token" />);
  await screen.findByLabelText("Ngày hiệu lực");
  today.mockReturnValue("2026-10-28");
  fireEvent.change(screen.getByRole("textbox", { name: "Câu hỏi tra cứu" }), {
    target: { value: "Quy định hôm nay" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Tra cứu" }));
  await waitFor(() => expect(fetcher.mock.calls.some(([url]) => String(url).endsWith("/turns"))).toBe(true));
  const turnCall = fetcher.mock.calls.find(([url]) => String(url).endsWith("/turns"));
  expect(JSON.parse(String((turnCall?.[1] as RequestInit).body)).scope.as_of_date).toBe("2026-10-28");
});

it("clears the previous account's category scope and manually chosen date", async () => {
  vi.spyOn(localDate, "localDateISO").mockReturnValue("2026-10-27");
  vi.stubGlobal("fetch", vi.fn().mockImplementation((url: string) => {
    if (url.endsWith("/api/v1/categories")) return Promise.resolve(new Response(JSON.stringify([
      { id: "cat-1", code: "C1", name: "Danh mục A", remote_processing_allowed: false },
    ]), { status: 200 }));
    return Promise.resolve(baseRoutes(url) ?? new Response("{}", { status: 200 }));
  }));
  const { rerender } = render(<EvidenceChat accessToken="account-one" />);
  await screen.findByLabelText("Chọn danh mục");
  fireEvent.click(screen.getByLabelText("Chọn danh mục"));
  fireEvent.click(screen.getByLabelText("Danh mục A"));
  fireEvent.change(screen.getByLabelText("Ngày hiệu lực"), { target: { value: "2025-04-10" } });
  expect(screen.getByText(/Phạm vi:/)).toHaveTextContent("Đã chọn 1 danh mục");
  rerender(<EvidenceChat accessToken="account-two" />);
  await waitFor(() => expect(screen.getByText(/Phạm vi:/)).toHaveTextContent("Tất cả danh mục"));
  expect(screen.getByLabelText("Ngày hiệu lực")).toHaveValue("2026-10-27");
});

it("unlocks controls when a session expires while refreshing preferences", async () => {
  vi.stubGlobal("fetch", vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    if (url.endsWith("/api/v1/categories")) return Promise.resolve(new Response(JSON.stringify([
      { id: "cat-1", code: "C1", name: "Danh mục A", remote_processing_allowed: false },
    ]), { status: 200 }));
    if (url.includes("/api/v1/memory?") && init?.method === "GET") {
      return Promise.resolve(new Response(JSON.stringify({
        code: "SESSION_EXPIRED", message: "Phiên đã hết hạn",
      }), { status: 410 }));
    }
    const known = baseRoutes(url);
    return Promise.resolve(known ?? new Response("{}", { status: 200 }));
  }));
  render(<EvidenceChat accessToken="fixture-token" />);
  await screen.findByLabelText("Chọn danh mục");
  fireEvent.click(screen.getByLabelText("Chọn danh mục"));
  fireEvent.click(screen.getByLabelText("Danh mục A"));
  fireEvent.click(screen.getByText(/^Bộ nhớ phiên \(\d+\)$/));
  fireEvent.click(screen.getByRole("checkbox", { name: /Dùng phạm vi danh mục hiện tại/ }));
  await screen.findByText(/Phiên bộ nhớ đã hết hạn/);
  fireEvent.change(screen.getByRole("textbox", { name: "Câu hỏi tra cứu" }), {
    target: { value: "Câu hỏi sau khi hết hạn" },
  });
  expect(screen.getByRole("button", { name: "Tra cứu" })).toBeEnabled();
});

it("does not let a stopped turn's late expiry erase a newer result", async () => {
  let resolveOld!: (response: Response) => void;
  const oldResponse = new Promise<Response>((resolve) => { resolveOld = resolve; });
  const base = { query_id: "q", run_id: "r", facts_revision: "f", snapshot_revision: null };
  const evidence = {
    evidence_id: "ev_new", document_id: "d", document_version_id: "v", node_id: "n",
    document_number: "351/2026/NĐ-CP", title: "Văn bản", label: "Điều 1",
    quote_exact: "Nội dung", page: 1, source_hash: "hash", as_of_date: "2026-01-01",
    amendment_state: "unknown", viewer_url: "/invalid", outside_scope: false,
  };
  const body = sse([
    ["retrieval_started", { ...base, event_sequence: 1 }],
    ["evidence_verified", { ...base, event_sequence: 2, evidence: [evidence] }],
    ["analysis_ready", { ...base, event_sequence: 3, status: "conditional", claims: [], suggestions: [] }],
    ["answer_complete", { ...base, event_sequence: 4 }],
  ]);
  let turns = 0;
  const fetcher = vi.fn().mockImplementation((url: string) => {
    if (url.endsWith("/turns")) {
      turns += 1;
      if (turns === 1) return oldResponse;
      return Promise.resolve(new Response(body, { status: 200, headers: { "X-Turn-Id": "new" } }));
    }
    return Promise.resolve(baseRoutes(url) ?? new Response("{}", { status: 200 }));
  });
  vi.stubGlobal("fetch", fetcher);
  render(<EvidenceChat accessToken="fixture-token" />);
  const composer = screen.getByRole("textbox", { name: "Câu hỏi tra cứu" });
  fireEvent.change(composer, { target: { value: "Câu hỏi cũ" } });
  const submit = screen.getByRole("button", { name: "Tra cứu" });
  await waitFor(() => expect(submit).toBeEnabled());
  fireEvent.click(submit);
  await waitFor(() => expect(turns).toBe(1));
  fireEvent.click(screen.getByRole("button", { name: "Dừng" }));
  fireEvent.change(composer, { target: { value: "Câu hỏi mới" } });
  await waitFor(() => expect(submit).toBeEnabled());
  fireEvent.click(submit);
  await screen.findByText("1 căn cứ");
  await act(async () => {
    resolveOld(new Response(JSON.stringify({ code: "SESSION_EXPIRED", message: "Hết hạn" }), { status: 410 }));
  });
  expect(screen.getByText("1 căn cứ")).toBeInTheDocument();
});

it("submits a question through a memory session and surfaces authentication errors", async () => {
  const fetcher = vi.fn().mockImplementation((url: string) => {
    const known = baseRoutes(url);
    if (known) return Promise.resolve(known);
    return Promise.resolve(new Response(JSON.stringify({
      code: "AUTH_REQUIRED", message: "Bạn cần đăng nhập để tra cứu.",
    }), { status: 401 }));
  });
  vi.stubGlobal("fetch", fetcher);
  render(<EvidenceChat accessToken="fixture-token" />);
  fireEvent.change(screen.getByRole("textbox", { name: "Câu hỏi tra cứu" }), {
    target: { value: "Câu hỏi mới" },
  });
  const submit = screen.getByRole("button", { name: "Tra cứu" });
  await waitFor(() => expect(submit).toBeEnabled());
  fireEvent.click(submit);
  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Phiên đăng nhập đã hết hạn"));
  const turnCall = fetcher.mock.calls.find(([url]) => String(url).endsWith("/turns"));
  expect(turnCall).toBeDefined();
  const init = turnCall?.[1] as RequestInit;
  expect(JSON.parse(init.body as string).facts).toEqual([]);
  const headers = new Headers(init.headers);
  expect(headers.has("X-Principal-Id")).toBe(false);
  expect(headers.get("Idempotency-Key")).toBeTruthy();
});

it("renders evidence, claims and suggestions streamed from a turn", async () => {
  const evidence = {
    evidence_id: "ev_1", document_id: "d", document_version_id: "v", node_id: "n",
    document_number: "351/2026/NĐ-CP", title: "Nghị định", label: "Điều 1",
    quote_exact: "Nội dung điều 1", page: 1, source_hash: "h", as_of_date: "2026-01-01",
    amendment_state: "active", viewer_url: "/x", outside_scope: false,
  };
  const base = { query_id: "q", run_id: "r", facts_revision: "factrev_1", snapshot_revision: null };
  const body = sse([
    ["retrieval_started", { ...base, event_sequence: 1 }],
    ["evidence_verified", { ...base, event_sequence: 2, evidence: [evidence] }],
    ["evidence_complete", { ...base, event_sequence: 3, evidence_count: 1 }],
    ["analysis_ready", {
      ...base, event_sequence: 4, status: "evidence_found",
      claims: [{ text: "Nội dung điều 1", evidence_ids: ["ev_1"], status: "supported" }],
      suggestions: [], missing_information: ["Thiếu thời điểm"], coverage_checks: {},
      answer_generated: false, ai_selection_applied: true, explanation_unavailable: true,
      evidence_groups: [], disclaimer: "Chỉ hỗ trợ tra cứu.",
    }],
    ["answer_complete", { ...base, event_sequence: 5, status: "evidence_found" }],
  ]);
  vi.stubGlobal("fetch", vi.fn().mockImplementation((url: string) => {
    const known = baseRoutes(url);
    if (known) return Promise.resolve(known);
    return Promise.resolve(new Response(body, {
      status: 200, headers: { "Content-Type": "text/event-stream", "X-Turn-Id": "turn_1" },
    }));
  }));
  render(<EvidenceChat accessToken="fixture-token" />);
  fireEvent.change(screen.getByRole("textbox", { name: "Câu hỏi tra cứu" }), {
    target: { value: "Điều 1 Nghị định 351/2026/NĐ-CP quy định gì?" },
  });
  const submit = screen.getByRole("button", { name: "Tra cứu" });
  await waitFor(() => expect(submit).toBeEnabled());
  fireEvent.click(submit);
  await waitFor(() => expect(screen.getByText("1 căn cứ")).toBeInTheDocument());
  expect(screen.getByText("Thiếu thời điểm")).toBeInTheDocument();
  expect(screen.getByText(/Model đã hỗ trợ chọn căn cứ/)).toBeInTheDocument();
});

it("sends deep analysis only in API mode and labels external API use", async () => {
  const base = { query_id: "q", run_id: "r", facts_revision: "factrev_1", snapshot_revision: null };
  const body = sse([
    ["retrieval_started", { ...base, event_sequence: 1 }],
    ["evidence_verified", { ...base, event_sequence: 2, evidence: [] }],
    ["evidence_complete", { ...base, event_sequence: 3, evidence_count: 0 }],
    ["analysis_ready", {
      ...base, event_sequence: 4, status: "insufficient", claims: [], suggestions: [],
      missing_information: [], coverage_checks: {}, answer_generated: false,
      external_ai_used: true, explanation_unavailable: true, evidence_groups: [],
      disclaimer: "",
    }],
    ["answer_complete", { ...base, event_sequence: 5, status: "insufficient" }],
  ]);
  const fetcher = vi.fn().mockImplementation((url: string) => {
    const known = baseRoutes(url);
    if (known) return Promise.resolve(known);
    return Promise.resolve(new Response(body, {
      status: 200, headers: { "Content-Type": "text/event-stream", "X-Turn-Id": "turn_3" },
    }));
  });
  vi.stubGlobal("fetch", fetcher);
  const { unmount } = render(<EvidenceChat accessToken="fixture-token" operatingMode="LOCAL" />);
  await screen.findByRole("button", { name: "Tra cứu" });
  expect(screen.queryByRole("checkbox", { name: "Phân tích sâu" })).not.toBeInTheDocument();
  unmount();

  render(<EvidenceChat accessToken="fixture-token" operatingMode="API" />);
  fireEvent.change(screen.getByRole("textbox", { name: "Câu hỏi tra cứu" }), {
    target: { value: "Phân tích quy định" },
  });
  fireEvent.click(await screen.findByRole("checkbox", { name: "Phân tích sâu" }));
  const submit = screen.getByRole("button", { name: "Tra cứu" });
  await waitFor(() => expect(submit).toBeEnabled());
  fireEvent.click(submit);
  await waitFor(() => expect(screen.getByText("Đã dùng API ngoài cho lượt này.")).toBeInTheDocument());
  const turnCall = fetcher.mock.calls.find(([url]) => String(url).endsWith("/turns"));
  expect(JSON.parse((turnCall?.[1] as RequestInit).body as string).deep_analysis).toBe(true);
});

it("shows a terminal error when the stream reports one", async () => {
  const body = sse([
    ["retrieval_started", { query_id: "q", run_id: "r", event_sequence: 1 }],
    ["turn_error", { query_id: "q", run_id: "r", event_sequence: 2, code: "QUERY_TIMEOUT" }],
  ]);
  vi.stubGlobal("fetch", vi.fn().mockImplementation((url: string) => {
    const known = baseRoutes(url);
    if (known) return Promise.resolve(known);
    return Promise.resolve(new Response(body, { status: 200, headers: { "X-Turn-Id": "turn_2" } }));
  }));
  render(<EvidenceChat accessToken="fixture-token" />);
  fireEvent.change(screen.getByRole("textbox", { name: "Câu hỏi tra cứu" }), {
    target: { value: "Câu hỏi chậm" },
  });
  const submit = screen.getByRole("button", { name: "Tra cứu" });
  await waitFor(() => expect(submit).toBeEnabled());
  fireEvent.click(submit);
  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("mất quá nhiều thời gian"));
});

it("keeps the submitted question attached to its result while editing a draft", async () => {
  const base = { query_id: "q", run_id: "r", facts_revision: "factrev_1", snapshot_revision: null };
  const body = sse([
    ["retrieval_started", { ...base, event_sequence: 1 }],
    ["evidence_verified", { ...base, event_sequence: 2, evidence: [] }],
    ["evidence_complete", { ...base, event_sequence: 3, evidence_count: 0 }],
    ["analysis_ready", { ...base, event_sequence: 4, status: "insufficient", claims: [], suggestions: [] }],
    ["answer_complete", { ...base, event_sequence: 5, status: "insufficient" }],
  ]);
  vi.stubGlobal("fetch", vi.fn().mockImplementation((url: string) => {
    const known = baseRoutes(url);
    if (known) return Promise.resolve(known);
    return Promise.resolve(new Response(body, { status: 200, headers: { "X-Turn-Id": "turn_3" } }));
  }));
  render(<EvidenceChat accessToken="fixture-token" />);
  const composer = screen.getByRole("textbox", { name: "Câu hỏi tra cứu" });
  fireEvent.change(composer, { target: { value: "Câu hỏi A" } });
  const submit = screen.getByRole("button", { name: "Tra cứu" });
  await waitFor(() => expect(submit).toBeEnabled());
  fireEvent.click(submit);
  await waitFor(() => expect(screen.getByRole("button", { name: "Tra cứu" })).toBeEnabled());
  fireEvent.change(composer, { target: { value: "Câu hỏi B" } });
  expect(screen.getByText("Câu hỏi A")).toBeInTheDocument();
  expect(composer).toHaveValue("Câu hỏi B");
});

it("clears derived facts and results when a remembered message is deleted", async () => {
  const base = { query_id: "q", run_id: "r", facts_revision: "f", snapshot_revision: null };
  const evidence = {
    evidence_id: "ev_1", document_id: "d", document_version_id: "v", node_id: "n",
    document_number: "351/2026/NĐ-CP", title: "Văn bản", label: "Điều 1",
    quote_exact: "Nội dung gốc", page: 1, source_hash: "hash", as_of_date: "2026-01-01",
    amendment_state: "unknown", viewer_url: "/invalid", outside_scope: false,
  };
  const body = sse([
    ["retrieval_started", { ...base, event_sequence: 1 }],
    ["evidence_verified", { ...base, event_sequence: 2, evidence: [evidence] }],
    ["analysis_ready", { ...base, event_sequence: 3, status: "conditional", claims: [], suggestions: [] }],
    ["answer_complete", { ...base, event_sequence: 4 }],
  ]);
  let deleted = false;
  const fetcher = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    if (url.includes("/api/v1/memory/") && init?.method === "DELETE") {
      deleted = true;
      return Promise.resolve(new Response(null, { status: 204 }));
    }
    if (url.includes("/api/v1/memory?") && init?.method === "GET") {
      return Promise.resolve(new Response(JSON.stringify({ items: deleted ? [] : [
        { id: "message-1", kind: "message", content: "Câu hỏi cũ", created_at: "2026-10-27" },
      ] }), { status: 200 }));
    }
    const known = baseRoutes(url);
    if (known) return Promise.resolve(known);
    return Promise.resolve(new Response(body, { status: 200, headers: { "X-Turn-Id": "turn_old" } }));
  });
  vi.stubGlobal("fetch", fetcher);
  render(<EvidenceChat accessToken="fixture-token" />);
  fireEvent.change(screen.getByRole("textbox", { name: "Câu hỏi tra cứu" }), {
    target: { value: "Câu hỏi cũ về Nghị định 351/2026/NĐ-CP" },
  });
  const submit = screen.getByRole("button", { name: "Tra cứu" });
  await waitFor(() => expect(submit).toBeEnabled());
  fireEvent.click(submit);
  await screen.findByRole("textbox", { name: "Sửa Số hiệu văn bản" });
  fireEvent.click(screen.getByRole("button", { name: "Xác nhận Số hiệu văn bản" }));
  const panel = screen.getByText(/Bộ nhớ phiên \(1\)/).closest("details");
  expect(panel).not.toBeNull();
  fireEvent.click(within(panel!).getByText(/Bộ nhớ phiên/));
  fireEvent.click(within(panel!).getByRole("button", { name: "Xóa" }));
  await waitFor(() => expect(deleted).toBe(true));
  await waitFor(() => expect(screen.queryByRole("textbox", { name: "Sửa Số hiệu văn bản" })).not.toBeInTheDocument());
  expect(screen.queryByText("1 căn cứ")).not.toBeInTheDocument();
});

it("only offers a category preference after a category is selected and displays its active scope", async () => {
  let preferences = { enabled: false, default_category_ids: [] as string[], default_as_of_date: null };
  const fetcher = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    if (url.endsWith("/api/v1/categories")) return Promise.resolve(new Response(JSON.stringify([
      { id: "cat-1", code: "C1", name: "Danh mục A", remote_processing_allowed: false },
    ]), { status: 200 }));
    if (url.includes("/memory/preferences")) {
      if (init?.method === "PUT") preferences = JSON.parse(String(init.body));
      return Promise.resolve(new Response(JSON.stringify(preferences), { status: 200 }));
    }
    const known = baseRoutes(url);
    if (known) return Promise.resolve(known);
    return Promise.resolve(new Response("{}", { status: 200 }));
  });
  vi.stubGlobal("fetch", fetcher);
  render(<EvidenceChat accessToken="fixture-token" />);
  await screen.findByLabelText("Chọn danh mục");
  fireEvent.click(screen.getByText(/^Bộ nhớ phiên \(\d+\)$/));
  const setting = screen.getByRole("checkbox", { name: /Dùng phạm vi danh mục hiện tại/ });
  expect(setting).toBeDisabled();
  fireEvent.click(screen.getByLabelText("Chọn danh mục"));
  fireEvent.click(screen.getByLabelText("Danh mục A"));
  expect(setting).toBeEnabled();
  fireEvent.click(setting);
  await waitFor(() => expect(setting).toBeChecked());
  fireEvent.click(screen.getByRole("radio", { name: /Tất cả danh mục|Danh mục mặc định/ }));
  expect(screen.getByText(/Phạm vi:/).textContent).toMatch(/mặc định/i);
});

it("uses a new turn when the scope changes before retry", async () => {
  const base = { query_id: "q", run_id: "r", event_sequence: 1 };
  const failed = sse([["retrieval_started", base], ["turn_error", { ...base, event_sequence: 2, code: "QUERY_TIMEOUT" }]]);
  const fetcher = vi.fn().mockImplementation((url: string) => {
    if (url.endsWith("/api/v1/categories")) return Promise.resolve(new Response(JSON.stringify([
      { id: "cat-1", code: "C1", name: "Danh mục A", remote_processing_allowed: false },
    ]), { status: 200 }));
    const known = baseRoutes(url);
    if (known) return Promise.resolve(known);
    return Promise.resolve(new Response(failed, { status: 200, headers: { "X-Turn-Id": "turn_old" } }));
  });
  vi.stubGlobal("fetch", fetcher);
  render(<EvidenceChat accessToken="fixture-token" />);
  await screen.findByLabelText("Ngày hiệu lực");
  fireEvent.change(screen.getByRole("textbox", { name: "Câu hỏi tra cứu" }), { target: { value: "Câu hỏi" } });
  fireEvent.click(screen.getByRole("button", { name: "Tra cứu" }));
  await screen.findByRole("button", { name: "Thử lại" });
  fireEvent.change(screen.getByLabelText("Ngày hiệu lực"), { target: { value: "2026-01-15" } });
  fireEvent.click(screen.getByRole("button", { name: "Thử lại" }));
  await waitFor(() => expect(fetcher.mock.calls.filter(([url]) => String(url).endsWith("/turns"))).toHaveLength(2));
  expect(fetcher.mock.calls.some(([url]) => String(url).endsWith("/retry"))).toBe(false);
});

it("deletes a session that finishes being created after the user stops the query", async () => {
  let resolveSession!: (response: Response) => void;
  const pendingSession = new Promise<Response>((resolve) => { resolveSession = resolve; });
  const fetcher = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    if (url.endsWith("/api/v1/agent/sessions") && init?.method === "POST") return pendingSession;
    if (url.includes("/api/v1/agent/sessions/") && init?.method === "DELETE") {
      return Promise.resolve(new Response(null, { status: 204 }));
    }
    const known = baseRoutes(url);
    if (known) return Promise.resolve(known);
    return Promise.reject(new DOMException("Stopped", "AbortError"));
  });
  vi.stubGlobal("fetch", fetcher);
  render(<EvidenceChat accessToken="fixture-token" />);
  fireEvent.change(screen.getByRole("textbox", { name: "Câu hỏi tra cứu" }), { target: { value: "Câu hỏi" } });
  const submit = screen.getByRole("button", { name: "Tra cứu" });
  await waitFor(() => expect(submit).toBeEnabled());
  fireEvent.click(submit);
  fireEvent.click(screen.getByRole("button", { name: "Dừng" }));
  await act(async () => resolveSession(new Response(JSON.stringify(SESSION), { status: 201 })));
  await waitFor(() => expect(fetcher.mock.calls.some(([url, init]) =>
    String(url).endsWith(`/sessions/${SESSION.session_id}`) && (init as RequestInit)?.method === "DELETE",
  )).toBe(true));
});

it("removes a confirmed fact from the server before removing it from the screen", async () => {
  const base = { query_id: "q", run_id: "r", facts_revision: "f", snapshot_revision: null };
  const evidence = {
    evidence_id: "ev_1", document_id: "d", document_version_id: "v", node_id: "n",
    document_number: "351/2026/NĐ-CP", title: "Văn bản", label: "Điều 1",
    quote_exact: "Nội dung gốc", page: 1, source_hash: "hash", as_of_date: "2026-01-01",
    amendment_state: "unknown", viewer_url: "/invalid", outside_scope: false,
  };
  const body = sse([
    ["retrieval_started", { ...base, event_sequence: 1 }],
    ["evidence_verified", { ...base, event_sequence: 2, evidence: [evidence] }],
    ["analysis_ready", { ...base, event_sequence: 3, status: "conditional", claims: [], suggestions: [] }],
    ["answer_complete", { ...base, event_sequence: 4 }],
  ]);
  const fetcher = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    if (url.includes("/facts?") && init?.method === "DELETE") {
      return Promise.resolve(new Response(null, { status: 204 }));
    }
    const known = baseRoutes(url);
    if (known) return Promise.resolve(known);
    return Promise.resolve(new Response(body, { status: 200, headers: { "X-Turn-Id": "turn_one" } }));
  });
  vi.stubGlobal("fetch", fetcher);
  render(<EvidenceChat accessToken="fixture-token" />);
  fireEvent.change(screen.getByRole("textbox", { name: "Câu hỏi tra cứu" }), {
    target: { value: "Điều 1 Nghị định 351/2026/NĐ-CP quy định gì?" },
  });
  const submit = screen.getByRole("button", { name: "Tra cứu" });
  await waitFor(() => expect(submit).toBeEnabled());
  fireEvent.click(submit);
  await screen.findByRole("textbox", { name: "Sửa Số hiệu văn bản" });
  fireEvent.click(screen.getByRole("button", { name: "Xác nhận Số hiệu văn bản" }));
  fireEvent.click(screen.getByRole("button", { name: "Xóa dữ kiện Số hiệu văn bản" }));
  await waitFor(() => expect(fetcher.mock.calls.some(([url, init]) =>
    String(url).includes("/facts?") && (init as RequestInit)?.method === "DELETE",
  )).toBe(true));
  await waitFor(() => expect(screen.queryByRole("textbox", { name: "Sửa Số hiệu văn bản" })).not.toBeInTheDocument());
  expect(screen.queryByText("1 căn cứ")).not.toBeInTheDocument();
});

it("keeps the memory visible and reports failure when deleting the session fails", async () => {
  const base = { query_id: "q", run_id: "r", facts_revision: "f", snapshot_revision: null };
  const body = sse([
    ["retrieval_started", { ...base, event_sequence: 1 }],
    ["evidence_verified", { ...base, event_sequence: 2, evidence: [] }],
    ["analysis_ready", { ...base, event_sequence: 3, status: "insufficient", claims: [], suggestions: [] }],
    ["answer_complete", { ...base, event_sequence: 4 }],
  ]);
  vi.stubGlobal("fetch", vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    if (url.includes("/api/v1/memory?") && init?.method === "DELETE") {
      return Promise.resolve(new Response(JSON.stringify({ message: "Database unavailable" }), { status: 503 }));
    }
    if (url.includes("/api/v1/memory?") && init?.method === "GET") {
      return Promise.resolve(new Response(JSON.stringify({ items: [
        { id: "message-1", kind: "message", content: "Câu hỏi", created_at: "2026-10-27" },
      ] }), { status: 200 }));
    }
    const known = baseRoutes(url);
    if (known) return Promise.resolve(known);
    return Promise.resolve(new Response(body, { status: 200, headers: { "X-Turn-Id": "turn_one" } }));
  }));
  render(<EvidenceChat accessToken="fixture-token" />);
  fireEvent.change(screen.getByRole("textbox", { name: "Câu hỏi tra cứu" }), { target: { value: "Câu hỏi" } });
  const submit = screen.getByRole("button", { name: "Tra cứu" });
  await waitFor(() => expect(submit).toBeEnabled());
  fireEvent.click(submit);
  await screen.findByText(/^Bộ nhớ phiên \(1\)$/);
  fireEvent.click(screen.getByRole("button", { name: /Xóa dữ liệu tạm/ }));
  expect(await screen.findByText(/Không thể xác nhận việc xóa bộ nhớ trên máy chủ/)).toBeInTheDocument();
  expect(screen.getByText(/^Bộ nhớ phiên \(1\)$/)).toBeInTheDocument();
});
