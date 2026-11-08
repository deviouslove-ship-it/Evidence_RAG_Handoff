import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { EvidenceChat } from "./EvidenceChat";

const SESSION = {
  session_id: "11111111-1111-4111-8111-111111111111",
  persistence_state: "ephemeral",
  expires_at: "2099-01-01T00:00:00+00:00",
  facts_revision: "factrev_1",
  memory_revision: "memoryrev_1",
};

const QUESTION = "Điều 1 Nghị định 351/2026/NĐ-CP quy định gì?";

function sse(events: Array<[string, Record<string, unknown>]>): string {
  return events
    .map(
      ([name, data], index) =>
        `id: q:r:${index + 1}\nevent: ${name}\ndata: ${JSON.stringify(data)}\n\n`,
    )
    .join("");
}

function baseRoutes(url: string): Response | undefined {
  if (url.endsWith("/api/v1/categories")) return new Response("[]", { status: 200 });
  if (url.endsWith("/api/v1/agent/sessions")) {
    return new Response(JSON.stringify(SESSION), { status: 201 });
  }
  if (url.includes("/api/v1/memory/preferences")) {
    return new Response(
      JSON.stringify({ enabled: false, default_category_ids: [], default_as_of_date: null }),
      { status: 200 },
    );
  }
  if (url.includes("/api/v1/memory")) {
    return new Response(JSON.stringify({ items: [] }), { status: 200 });
  }
  return undefined;
}

const evidence = {
  evidence_id: "ev_1",
  document_id: "d",
  document_version_id: "v",
  node_id: "n",
  document_number: "351/2026/NĐ-CP",
  title: "Nghị định",
  label: "Điều 1",
  quote_exact: "Nội dung điều 1",
  page: 1,
  source_hash: "h",
  as_of_date: "2026-01-01",
  amendment_state: "active",
  viewer_url: "/x",
  outside_scope: false,
};

const base = { query_id: "q", run_id: "r", facts_revision: "factrev_1", snapshot_revision: null };

const turnBody = sse([
  ["retrieval_started", { ...base, event_sequence: 1 }],
  ["evidence_verified", { ...base, event_sequence: 2, evidence: [evidence] }],
  ["evidence_complete", { ...base, event_sequence: 3, evidence_count: 1 }],
  [
    "analysis_ready",
    {
      ...base,
      event_sequence: 4,
      status: "evidence_found",
      claims: [{ text: "Nội dung điều 1", evidence_ids: ["ev_1"], status: "supported" }],
      suggestions: [],
      missing_information: [],
      coverage_checks: {},
      answer_generated: false,
      explanation_unavailable: false,
      evidence_groups: [],
      disclaimer: "Chỉ hỗ trợ tra cứu.",
    },
  ],
  ["answer_complete", { ...base, event_sequence: 5, status: "evidence_found" }],
]);

function installFetcher() {
  const fetcher = vi.fn().mockImplementation((url: string) => {
    const known = baseRoutes(String(url));
    if (known) return Promise.resolve(known);
    return Promise.resolve(
      new Response(turnBody, {
        status: 200,
        headers: { "Content-Type": "text/event-stream", "X-Turn-Id": "turn_1" },
      }),
    );
  });
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}

const onViewAll = vi.fn();

afterEach(() => {
  vi.unstubAllGlobals();
  onViewAll.mockReset();
});

async function submitQuestion() {
  fireEvent.change(screen.getByRole("textbox", { name: "Câu hỏi tra cứu" }), {
    target: { value: QUESTION },
  });
  const submit = screen.getByRole("button", { name: "Tra cứu" });
  await waitFor(() => expect(submit).toBeEnabled());
  fireEvent.click(submit);
  await waitFor(() => expect(screen.getByText("1 căn cứ")).toBeInTheDocument());
}

it("opens the search page with the submitted question after a chat result", async () => {
  installFetcher();
  render(<EvidenceChat accessToken="fixture-token" onViewAllResults={onViewAll} />);
  await submitQuestion();
  fireEvent.click(screen.getByRole("button", { name: "Xem tất cả kết quả tìm kiếm" }));
  expect(onViewAll).toHaveBeenCalledWith(QUESTION);
});
