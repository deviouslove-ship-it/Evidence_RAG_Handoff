import { afterEach, expect, it, vi } from "vitest";

import { ApiRequestError, queryEvidence, runAgentTurn } from "./client";

const payload = {
  question: "Câu hỏi kiểm thử",
  scope: {
    scope_mode: "ALL_AUTHORIZED" as const,
    category_ids: [],
    document_types: [],
    as_of_date: "2026-10-22",
  },
  facts: [],
};

afterEach(() => vi.unstubAllGlobals());

it("sends the request without inventing a principal or role", async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
  vi.stubGlobal("fetch", fetcher);
  await queryEvidence(payload);
  const [url, init] = fetcher.mock.calls[0] as [string, RequestInit];
  expect(url).toBe("/api/v1/query/evidence");
  expect(JSON.parse(init.body as string)).toEqual(payload);
  const headers = new Headers(init.headers);
  expect(headers.has("X-Principal-Id")).toBe(false);
  expect(headers.has("X-Roles")).toBe(false);
});

it("accepts a bearer credential from the authenticated caller", async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
  vi.stubGlobal("fetch", fetcher);
  await queryEvidence(payload, { accessToken: "fixture" });
  const headers = new Headers((fetcher.mock.calls[0][1] as RequestInit).headers);
  expect(headers.get("Authorization")).toBe("Bearer fixture");
});

it("shows the backend message and preserves the error identity", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
    code: "AUTH_REQUIRED",
    message: "Bạn cần đăng nhập để tra cứu.",
    trace_id: "trace_fixture",
  }), { status: 401 })));
  await expect(queryEvidence(payload)).rejects.toMatchObject({
    message: "Bạn cần đăng nhập để tra cứu.",
    status: 401,
    code: "AUTH_REQUIRED",
    traceId: "trace_fixture",
  } satisfies Partial<ApiRequestError>);
});

function streamResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Response(body, { status: 200, headers: { "X-Turn-Id": "turn_1" } });
}

function event(name: string, sequence: number, data: Record<string, unknown> = {}): string {
  return `event: ${name}\ndata: ${JSON.stringify({ query_id: "q", run_id: "r", event_sequence: sequence, ...data })}\n\n`;
}

it("rejects a completed stream that omitted the result analysis", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(streamResponse([
    event("retrieval_started", 1) + event("evidence_verified", 2, { evidence: [] }) +
    event("answer_complete", 3),
  ])));
  await expect(runAgentTurn("fixture", "session", payload, { idempotencyKey: "one" }))
    .rejects.toMatchObject({ code: "STREAM_INCOMPLETE" });
});

it("reads an SSE event boundary split between carriage return and newline", async () => {
  const wire = (
    event("retrieval_started", 1) + event("evidence_verified", 2, { evidence: [{ evidence_id: "ev_1" }] }) +
    event("analysis_ready", 3, { status: "conditional", claims: [], suggestions: [] }) +
    event("answer_complete", 4)
  ).replace(/\n/g, "\r\n");
  const boundary = wire.indexOf("\r\n\r\n") + 3;
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(streamResponse([wire.slice(0, boundary), wire.slice(boundary)])));
  const result = await runAgentTurn("fixture", "session", payload, { idempotencyKey: "one" });
  expect(result.evidence.map((item) => item.evidence_id)).toEqual(["ev_1"]);
});

it("rejects events mixed from different runs", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(streamResponse([
    event("retrieval_started", 1) + event("evidence_verified", 2, { evidence: [] }) +
    event("analysis_ready", 3, { run_id: "other", status: "conditional", claims: [], suggestions: [] }) +
    event("answer_complete", 4, { run_id: "other" }),
  ])));
  await expect(runAgentTurn("fixture", "session", payload, { idempotencyKey: "one" }))
    .rejects.toMatchObject({ code: "STREAM_INVALID" });
});

it("finishes a completed turn without waiting for the server to close the SSE connection", async () => {
  const cancelled = vi.fn();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(
        event("retrieval_started", 1) + event("evidence_verified", 2, { evidence: [] }) +
        event("analysis_ready", 3, { status: "insufficient", claims: [], suggestions: [] }) +
        event("answer_complete", 4),
      ));
    },
    cancel: cancelled,
  });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body)));
  const result = await Promise.race([
    runAgentTurn("fixture", "session", payload, { idempotencyKey: "one" }),
    new Promise<never>((_, reject) => setTimeout(() => reject(new Error("stream still waiting")), 200)),
  ]);
  expect(result.status).toBe("insufficient");
  expect(cancelled).toHaveBeenCalledOnce();
});
