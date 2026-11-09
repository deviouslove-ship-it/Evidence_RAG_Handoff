import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { EvidenceChat } from "./EvidenceChat";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const SESSION = {
  session_id: "11111111-1111-4111-8111-111111111111", persistence_state: "ephemeral",
  expires_at: "2099-01-01T00:00:00+00:00", facts_revision: "f", memory_revision: "m",
};
const NODE_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const NODE_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const QUOTE_A = "4. Trong thời hạn 10 ngày làm việc, kể từ ngày bổ nhiệm, miễn nhiệm giám định "
  + "viên kỹ thuật hình sự, Bộ Công an có trách nhiệm lập danh sách.";

function sse(events: Array<[string, Record<string, unknown>]>): string {
  return events.map(([name, data], index) =>
    `id: q:r:${index + 1}\nevent: ${name}\ndata: ${JSON.stringify(data)}\n\n`).join("");
}

function evidence(node: string, label: string, quote: string, number: string) {
  return {
    evidence_id: `ev_${node}`, document_id: `doc-${number}`, document_version_id: "v",
    node_id: node, document_number: number, title: "Thông tư", label, quote_exact: quote,
    page: 4, source_hash: "h", as_of_date: "2026-11-08", amendment_state: "unknown",
    viewer_url: `/api/v1/citations/ev_${node}/pdf`, outside_scope: false,
    original_url: `/api/v1/citations/ev_${node}/original?as_of_date=2026-11-08`,
  };
}

const documents = [
  {
    document_id: "doc-01/VBHN-BCA", document_version_id: "v", doc_type: "circular",
    doc_type_label: "Thông tư", document_number: "01/VBHN-BCA",
    title: "Quy định chi tiết tiêu chuẩn, trình tự, thủ tục bổ nhiệm, miễn nhiệm",
    issuing_body: null, publication_date: null, source_format: "doc",
    original_filename: "01.doc",
    original_url: `/api/v1/citations/ev_${NODE_A}/original?as_of_date=2026-11-08`,
    viewer_url: `/api/v1/citations/ev_${NODE_A}/pdf`, role: "direct",
    kind_label: "Văn bản hợp nhất", relations: [], effectivity: null, more_clauses: 2,
    clauses: [{
      evidence_id: `ev_${NODE_A}`, node_id: NODE_A, label: "Khoản 4 Điều 5",
      heading: "Điều 5. Thẩm quyền, trình tự, thủ tục bổ nhiệm, miễn nhiệm", page: 4,
      page_end: 4, tier: "direct", match: "phrase", matched_terms: ["bổ nhiệm"],
      excerpt: { start: 0, end: 70, text: QUOTE_A.slice(0, 70), truncated_before: false,
                 truncated_after: true,
                 highlights: [{ start: QUOTE_A.indexOf("bổ nhiệm"),
                                end: QUOTE_A.indexOf("bổ nhiệm") + "bổ nhiệm".length }] },
      topics: [], same_as: [], also_matched: ["Khoản 3 Điều 5"], effectivity: null,
    }],
  },
  {
    document_id: "doc-540/QD-BCA", document_version_id: "v2", doc_type: "decision",
    doc_type_label: "Quyết định", document_number: "540/QD-BCA", title: "Công bố danh mục",
    source_format: "doc", original_url: `/api/v1/citations/ev_${NODE_B}/original`,
    viewer_url: `/api/v1/citations/ev_${NODE_B}/pdf`, role: "reference",
    kind_label: "Danh mục, liệt kê văn bản", relations: [], more_clauses: 0,
    clauses: [{
      evidence_id: `ev_${NODE_B}`, node_id: NODE_B, label: "Đoạn không đánh số", tier: "reference",
      match: "phrase", matched_terms: [], topics: [], same_as: [], also_matched: [],
      excerpt: { start: 0, end: 20, text: "Thông tư số 33/2014", truncated_before: false,
                 truncated_after: false, highlights: [] },
    }],
  },
];

function routes(body: string, turns: RequestInit[]) {
  return vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    if (url.endsWith("/api/v1/categories")) return Promise.resolve(new Response("[]", { status: 200 }));
    if (url.endsWith("/api/v1/agent/sessions")) return Promise.resolve(new Response(JSON.stringify(SESSION), { status: 201 }));
    if (url.includes("/api/v1/memory/preferences")) {
      return Promise.resolve(new Response(JSON.stringify({ enabled: false, default_category_ids: [] }), { status: 200 }));
    }
    if (url.includes("/api/v1/memory")) return Promise.resolve(new Response(JSON.stringify({ items: [] }), { status: 200 }));
    if (url.endsWith("/turns")) {
      turns.push(init ?? {});
      return Promise.resolve(new Response(body, { status: 200, headers: { "X-Turn-Id": "t" } }));
    }
    return Promise.resolve(new Response("{}", { status: 200 }));
  });
}

const base = { query_id: "q", run_id: "r", facts_revision: "f", snapshot_revision: null };
const BODY = sse([
  ["retrieval_started", { ...base, event_sequence: 1 }],
  ["evidence_verified", { ...base, event_sequence: 2, evidence: [
    evidence(NODE_A, "Khoản 4 Điều 5", QUOTE_A, "01/VBHN-BCA"),
    evidence(NODE_B, "paragraph", "Thông tư số 33/2014", "540/QD-BCA"),
  ] }],
  ["analysis_ready", {
    ...base, event_sequence: 3, status: "conditional", claims: [], suggestions: [],
    missing_information: [], coverage_checks: {}, disclaimer: "Chỉ hỗ trợ tra cứu.",
    documents,
    answer: {
      outcome: "direct", understood_phrases: ["thủ tục bổ nhiệm", "miễn nhiệm"],
      summary: "Tìm thấy 1 văn bản có điều khoản nêu trực tiếp nội dung “Thủ tục bổ nhiệm”.",
      points: ["Văn bản hợp nhất 01/VBHN-BCA: Quy định chi tiết — Điều 5 (Thẩm quyền)."],
      topics: [], notes: ["Hiệu lực của các văn bản này chưa được xác minh trong kho."],
      counts: { direct: 1 }, result_set_id: "rs_1",
    },
  }],
  ["answer_complete", { ...base, event_sequence: 4 }],
]);

async function ask(text: string) {
  fireEvent.change(screen.getByRole("textbox", { name: "Câu hỏi tra cứu" }), { target: { value: text } });
  const submit = screen.getByRole("button", { name: "Tra cứu" });
  await waitFor(() => expect(submit).toBeEnabled());
  fireEvent.click(submit);
  await screen.findByRole("region", { name: "Câu trả lời" });
}

it("shows a short answer and one card per document with a verbatim excerpt", async () => {
  vi.stubGlobal("fetch", routes(BODY, []));
  render(<EvidenceChat accessToken="token" />);
  await ask("Thủ tục bổ nhiệm, miễn nhiệm trong Công an nhân dân");
  expect(screen.getByText(/Tìm thấy 1 văn bản có điều khoản nêu trực tiếp/)).toBeInTheDocument();
  const list = screen.getByRole("region", { name: "Văn bản liên quan" });
  const card = within(list).getByRole("article", { name: "01/VBHN-BCA" });
  expect(within(card).getByText("Văn bản hợp nhất")).toBeInTheDocument();
  expect(within(card).getByText("Khoản 4 Điều 5")).toBeInTheDocument();
  expect(within(card).getByText("bổ nhiệm", { selector: "mark" })).toBeInTheDocument();
  expect(within(card).getByText("Ngày ban hành")).toBeInTheDocument();
  expect(within(card).getAllByText("Chưa xác định").length).toBeGreaterThan(0);
  expect(within(card).getByRole("button", { name: "Mở văn bản gốc" })).toBeEnabled();
  expect(within(card).getByText("Tải tệp gốc Word (.doc)")).toBeInTheDocument();
  expect(within(card).getByText(/Cùng điều còn khớp: Khoản 3 Điều 5/)).toBeInTheDocument();
  // Expanding shows the full quote of the clause, not a different text.
  fireEvent.click(within(card).getByRole("button", { name: "Xem toàn văn điều khoản" }));
  expect(card.querySelector(".clause-quote-full")?.textContent).toBe(QUOTE_A);
  // Lists of documents are kept out of the main list.
  expect(within(list).queryByRole("article", { name: "540/QD-BCA" })).not.toBeInTheDocument();
  expect(screen.getByText(/Văn bản chỉ nhắc đến nội dung này/)).toBeInTheDocument();
});

it("never turns numbers from the evidence into facts and starts a new question without facts", async () => {
  const turns: RequestInit[] = [];
  vi.stubGlobal("fetch", routes(BODY, turns));
  render(<EvidenceChat accessToken="token" />);
  await ask("Thủ tục bổ nhiệm, miễn nhiệm trong Công an nhân dân");
  expect(screen.queryByRole("textbox", { name: "Sửa Số hiệu văn bản" })).not.toBeInTheDocument();
  await ask("Điều 5 Thông tư 77/2019/TT-BCA quy định gì?");
  expect(screen.getByRole("textbox", { name: "Sửa Số hiệu văn bản" })).toHaveValue("77/2019/TT-BCA");
  fireEvent.click(screen.getByRole("button", { name: "Xác nhận Số hiệu văn bản" }));
  await ask("chế độ báo cáo định kỳ");
  expect(JSON.parse(String(turns[2].body)).facts).toEqual([]);
  expect(screen.queryByRole("textbox", { name: "Sửa Số hiệu văn bản" })).not.toBeInTheDocument();
});

it("removes a cached answer when AI reports that its evidence set expired", async () => {
  const fetcher = routes(BODY, []);
  const fallback = fetcher.getMockImplementation()!;
  fetcher.mockImplementation((url: string, init?: RequestInit) =>
    url.endsWith("/api/v1/synthesis")
      ? Promise.resolve(new Response(JSON.stringify({ code: "RESULT_SET_EXPIRED" }), { status: 410 }))
      : fallback(url, init));
  vi.stubGlobal("fetch", fetcher);
  render(<EvidenceChat accessToken="token" />);
  const question = "Thủ tục bổ nhiệm, miễn nhiệm trong Công an nhân dân";
  await ask(question);
  fireEvent.click(screen.getByRole("button", { name: "Diễn giải AI" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Hãy tra cứu lại");
  expect(screen.queryByRole("region", { name: "Câu trả lời" })).not.toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Văn bản liên quan" })).not.toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "Câu hỏi tra cứu" })).toHaveValue(question);
});
