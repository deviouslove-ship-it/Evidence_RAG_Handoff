import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { detectPageTextIntent } from "../components/pageTextIntent";
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

it("synchronizes dynamic docPageSize with visible cards, navigates on [n] click, and preserves active document page on resize", async () => {
  const base = { query_id: "q", run_id: "r", facts_revision: "f", snapshot_revision: null };
  const docs = [1, 2, 3, 4, 5].map((idx) => ({
    evidence_id: `ev_${idx}`,
    document_id: `doc_${idx}`,
    document_version_id: `ver_${idx}`,
    node_id: `node_${idx}`,
    document_number: `0${idx}/2025/TT-BCA`,
    title: `Thông tư số 0${idx}/2025/TT-BCA`,
    label: `Điều ${idx}`,
    quote_exact: `Nội dung chi tiết của Điều ${idx} tại Thông tư 0${idx}/2025/TT-BCA.`,
    page: 1,
    source_hash: `hash_${idx}`,
    as_of_date: "2026-01-01",
    amendment_state: "active",
    viewer_url: `/v/${idx}`,
    outside_scope: false,
  }));
  const body = sse([
    ["retrieval_started", { ...base, event_sequence: 1 }],
    ["evidence_verified", { ...base, event_sequence: 2, evidence: docs }],
    ["evidence_complete", { ...base, event_sequence: 3, evidence_count: 5 }],
    ["analysis_ready", {
      ...base,
      event_sequence: 4,
      status: "evidence_found",
      claims: [],
      suggestions: [],
      missing_information: [],
      coverage_checks: {},
      answer_generated: true,
      answer: {
        outcome: "grounded",
        summary: "Tổng hợp 5 văn bản liên quan.",
        points: [
          "Theo Điều 1 Thông tư 01/2025/TT-BCA quy định hồ sơ ban đầu.",
          "Theo Điều 5 Thông tư 05/2025/TT-BCA quy định thẩm quyền phê duyệt.",
        ],
        topics: [],
        notes: [],
        understood_phrases: [],
      },
      evidence_groups: [],
      disclaimer: "",
    }],
    ["answer_complete", { ...base, event_sequence: 5, status: "evidence_found" }],
  ]);

  let simulatedPaneHeight = 500;
  vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockImplementation(function (this: HTMLElement) {
    if (this.classList?.contains("chat-results-scroll")) {
      return simulatedPaneHeight;
    }
    return 0;
  });
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    if (this.classList?.contains("chat-results-scroll")) {
      return {
        top: 0, bottom: simulatedPaneHeight, left: 0, right: 600,
        width: 600, height: simulatedPaneHeight, x: 0, y: 0, toJSON: () => ({}),
      };
    }
    if (this.classList?.contains("doc-list")) {
      return {
        top: 70, bottom: simulatedPaneHeight, left: 0, right: 600,
        width: 600, height: simulatedPaneHeight - 70, x: 0, y: 70, toJSON: () => ({}),
      };
    }
    if (this.classList?.contains("doc-card-slot")) {
      return {
        top: 0, bottom: 185, left: 0, right: 600,
        width: 600, height: 185, x: 0, y: 0, toJSON: () => ({}),
      };
    }
    return {
      top: 0, bottom: 0, left: 0, right: 0, width: 0, height: 0, x: 0, y: 0, toJSON: () => ({}),
    };
  });

  vi.stubGlobal("fetch", vi.fn().mockImplementation((url: string) => {
    const known = baseRoutes(url);
    if (known) return Promise.resolve(known);
    return Promise.resolve(new Response(body, {
      status: 200, headers: { "Content-Type": "text/event-stream", "X-Turn-Id": "turn_page" },
    }));
  }));

  const { container } = render(<EvidenceChat accessToken="fixture-token" />);
  fireEvent.change(screen.getByRole("textbox", { name: "Câu hỏi tra cứu" }), {
    target: { value: "Tra cứu 5 văn bản" },
  });
  const submit = screen.getByRole("button", { name: "Tra cứu" });
  await waitFor(() => expect(submit).toBeEnabled());
  fireEvent.click(submit);

  await screen.findByText("5 căn cứ");
  act(() => {
    window.dispatchEvent(new Event("resize"));
  });

  const pagination = await screen.findByRole("navigation", { name: "Phân trang kết quả" });
  await waitFor(() => {
    expect(pagination).toHaveAttribute("data-doc-page-size", "2");
    expect(pagination).toHaveTextContent("Trang 1 / 3 (1–2 / 5 văn bản)");
  });
  expect(container.querySelectorAll(".doc-card-slot")).toHaveLength(2);

  // Point 2 explicitly cites 05/2025/TT-BCA -> badge [5] (aria-label="Căn cứ 5", not [2])
  const citeFiveButtons = screen.getAllByRole("button", { name: "Căn cứ 5" });
  expect(citeFiveButtons.length).toBeGreaterThanOrEqual(2);
  fireEvent.click(citeFiveButtons[0]);

  await waitFor(() => {
    expect(pagination).toHaveAttribute("data-doc-page", "3");
    expect(pagination).toHaveTextContent("Trang 3 / 3 (5–5 / 5 văn bản)");
  });
  expect(container.querySelectorAll(".doc-card-slot")).toHaveLength(1);
  expect(container.querySelector(".doc-card-slot.is-cited")).not.toBeNull();

  // Resize taller so 3 cards fit per page: doc #5 should now stay visible on page 2 of 2 (4–5 / 5)
  simulatedPaneHeight = 720;
  act(() => {
    window.dispatchEvent(new Event("resize"));
  });
  await waitFor(() => {
    expect(pagination).toHaveAttribute("data-doc-page-size", "3");
    expect(pagination).toHaveAttribute("data-doc-page", "2");
    expect(pagination).toHaveTextContent("Trang 2 / 2 (4–5 / 5 văn bản)");
  });
  expect(container.querySelectorAll(".doc-card-slot")).toHaveLength(2);
});

it("detects page-text intent only for explicit page reading requests", () => {
  expect(detectPageTextIntent("Điều 17 Nghị định 351/2026/NĐ-CP quy định gì?")).toBeNull();
  expect(detectPageTextIntent("Đọc nội dung trang 17 Nghị định 351/2026/NĐ-CP")).toEqual({
    pageNumber: 17,
    isPrintedPage: false,
    docHint: "Nghị định 351/2026/NĐ-CP",
    preferAi: false,
  });
  expect(detectPageTextIntent("Trang 17 của Nghị định 351/2026 viết gì?")).toEqual({
    pageNumber: 17,
    isPrintedPage: false,
    docHint: "Nghị định 351/2026",
    preferAi: false,
  });
  expect(detectPageTextIntent("Xem trang in 15 Thông tư 10")).toEqual({
    pageNumber: 15,
    isPrintedPage: true,
    docHint: "Thông tư 10",
    preferAi: false,
  });
});

it.each(["stop", "clear"])("%s during a page read cancels the server task", async (action) => {
  const fetcher = vi.fn((url: string) => {
    const known = baseRoutes(url);
    if (known) return Promise.resolve(known);
    if (url.startsWith("/api/v1/search?")) return Promise.resolve(new Response(JSON.stringify({
      results: [{ document_id: "doc-1", document_version_id: "ver-1", title: "Báo cáo HƯ CẤU" }],
    })));
    return Promise.resolve(new Response(JSON.stringify({
      task_id: "queued-page-task", status: "queued", document_id: "doc-1", version_id: "ver-1",
      document_title: "Báo cáo HƯ CẤU", page_number: 17, total_pages: 20,
      source_kind: "ocr_ai_unverified", verified: false,
    }), { status: 202 }));
  });
  vi.stubGlobal("fetch", fetcher);
  render(<EvidenceChat accessToken="fixture-token" />);
  fireEvent.change(screen.getByRole("textbox", { name: "Câu hỏi tra cứu" }), {
    target: { value: "Đọc text trang 17 Báo cáo HƯ CẤU" },
  });
  const submit = screen.getByRole("button", { name: "Tra cứu" });
  await waitFor(() => expect(submit).toBeEnabled());
  fireEvent.click(submit);
  await screen.findByRole("button", { name: "Hủy đọc trang" });
  fireEvent.click(screen.getByRole("button", {
    name: action === "stop" ? "Dừng" : /^Xóa dữ liệu tạm/,
  }));
  await waitFor(() => expect(fetcher.mock.calls.some(([url]) => url.endsWith("/queued-page-task/cancel"))).toBe(true));
  expect(screen.queryByRole("button", { name: "Hủy đọc trang" })).not.toBeInTheDocument();
});

it("test_chat_page17_reads_only_requested_page", async () => {
  let turnCalled = false;
  let pollCount = 0;
  const fetcher = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    const known = baseRoutes(url);
    if (known) return Promise.resolve(known);
    if (url.startsWith("/api/v1/search?")) {
      return Promise.resolve(new Response(JSON.stringify({
        query: { original: "351/2026/NĐ-CP", mode: "auto" },
        totals: { documents: 1, clauses: 1, approximate_matches_hidden: 0 },
        page: 1,
        page_size: 5,
        has_more: false,
        effectivity_snapshot_status: "ready",
        results: [{
          document_id: "doc-1",
          document_version_id: "ver-1",
          document_number: "351/2026/NĐ-CP",
          title: "Nghị định kiểm thử trang 17",
          doc_type: "decree",
          matched_clause_count: 1,
          clause_page: 1,
          clause_page_size: 5,
          has_more_clauses: false,
          clauses: [],
        }],
      }), { status: 200 }));
    }
    if (url === "/api/v1/documents/doc-1/versions/ver-1/page-text") {
      expect(JSON.parse(String(init?.body))).toMatchObject({ page_number: 17 });
      return Promise.resolve(new Response(JSON.stringify({
        task_id: "task-17",
        status: "queued",
        document_id: "doc-1",
        version_id: "ver-1",
        document_title: "Nghị định kiểm thử trang 17",
        document_number: "351/2026/NĐ-CP",
        page_number: 17,
        total_pages: 25,
        source_kind: "ocr_ai_unverified",
        verified: false,
        warning: "AI đọc từ ảnh trang 17 — chưa đối chiếu thủ công",
        page_text: null,
        pdf_url: "/api/v1/documents/doc-1/versions/ver-1/pdf",
      }), { status: 202 }));
    }
    if (url === "/api/v1/page-text-tasks/task-17") {
      pollCount += 1;
      return Promise.resolve(new Response(JSON.stringify({
        task_id: "task-17",
        status: "ready",
        document_id: "doc-1",
        version_id: "ver-1",
        document_title: "Nghị định kiểm thử trang 17",
        document_number: "351/2026/NĐ-CP",
        page_number: 17,
        total_pages: 25,
        source_kind: "ocr_ai_unverified",
        verified: false,
        warning: "AI đọc từ ảnh trang 17 — chưa đối chiếu thủ công",
        page_text: "Điều 17. Nội dung nguyên văn của trang 17.",
        pdf_url: "/api/v1/documents/doc-1/versions/ver-1/pdf",
      }), { status: 200 }));
    }
    if (url.includes("/turns")) {
      turnCalled = true;
    }
    return Promise.resolve(new Response("{}", { status: 200 }));
  });
  vi.stubGlobal("fetch", fetcher);

  render(<EvidenceChat accessToken="fixture-token" />);
  const composer = screen.getByRole("textbox", { name: "Câu hỏi tra cứu" });
  fireEvent.change(composer, {
    target: { value: "Đọc nội dung trang 17 Nghị định 351/2026/NĐ-CP" },
  });
  const submit = screen.getByRole("button", { name: "Tra cứu" });
  await waitFor(() => expect(submit).toBeEnabled());
  fireEvent.click(submit);

  await screen.findByText("Trang PDF 17/25", {}, { timeout: 4000 });
  expect(screen.getByText("Điều 17. Nội dung nguyên văn của trang 17.")).toBeInTheDocument();
  expect(screen.getAllByText(/AI đọc từ ảnh trang 17 — chưa đối chiếu thủ công/).length).toBeGreaterThanOrEqual(1);
  expect(turnCalled).toBe(false);
  expect(pollCount).toBe(1);
});

it("test_ambiguous_document_and_invalid_page_do_not_infer", async () => {
  let pageTextRequested = false;
  const fetcher = vi.fn().mockImplementation((url: string) => {
    const known = baseRoutes(url);
    if (known) return Promise.resolve(known);
    if (url.startsWith("/api/v1/search?")) {
      return Promise.resolve(new Response(JSON.stringify({
        query: { original: "thuế", mode: "auto" },
        totals: { documents: 2, clauses: 2, approximate_matches_hidden: 0 },
        page: 1,
        page_size: 5,
        has_more: false,
        effectivity_snapshot_status: "ready",
        results: [
          {
            document_id: "doc-a",
            document_version_id: "ver-a",
            document_number: "01/2025/NĐ-CP",
            title: "Nghị định A về thuế",
            doc_type: "decree",
            matched_clause_count: 1,
            clause_page: 1,
            clause_page_size: 5,
            has_more_clauses: false,
            clauses: [],
          },
          {
            document_id: "doc-b",
            document_version_id: "ver-b",
            document_number: "02/2026/TT-BTC",
            title: "Thông tư B về thuế",
            doc_type: "circular",
            matched_clause_count: 1,
            clause_page: 1,
            clause_page_size: 5,
            has_more_clauses: false,
            clauses: [],
          },
        ],
      }), { status: 200 }));
    }
    if (url.includes("/page-text")) {
      pageTextRequested = true;
      return Promise.resolve(new Response(JSON.stringify({
        code: "PAGE_OUT_OF_RANGE",
        message: "Số trang PDF không hợp lệ hoặc vượt quá tổng số trang của tài liệu.",
      }), { status: 422 }));
    }
    return Promise.resolve(new Response("{}", { status: 200 }));
  });
  vi.stubGlobal("fetch", fetcher);

  render(<EvidenceChat accessToken="fixture-token" />);
  const composer = screen.getByRole("textbox", { name: "Câu hỏi tra cứu" });
  fireEvent.change(composer, {
    target: { value: "Xem trang in 999 về thuế" },
  });
  const submit = screen.getByRole("button", { name: "Tra cứu" });
  await waitFor(() => expect(submit).toBeEnabled());
  fireEvent.click(submit);

  await screen.findByText("Chọn văn bản cần đọc trang 999");
  expect(pageTextRequested).toBe(false);

  fireEvent.click(screen.getByRole("button", { name: /Thông tư B về thuế/ }));
  await screen.findByText("Xác nhận số trang PDF");
  expect(pageTextRequested).toBe(false);

  fireEvent.click(screen.getByRole("button", { name: "Đọc Trang PDF 999" }));
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent(/Số trang PDF không hợp lệ/);
  expect(pageTextRequested).toBe(true);
});
