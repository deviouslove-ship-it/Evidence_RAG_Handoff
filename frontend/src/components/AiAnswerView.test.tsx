import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import type { SynthesisResult } from "../api/client";
import type { AnswerDocument } from "../types";
import { AiAnswerView } from "./AiAnswerView";

const NODE = "11111111-1111-1111-1111-111111111111";

function document(number: string, clauseText: string, extra: Partial<AnswerDocument> = {}):
  AnswerDocument {
  return {
    document_id: `doc-${number}`, document_version_id: "v", doc_type: "circular",
    doc_type_label: "Thông tư", document_number: number, title: "Quy định HƯ CẤU",
    issuing_body: null, publication_date: "2030-01-02", source_format: "pdf",
    original_filename: "scan.pdf", original_url: `/api/v1/citations/ev_${NODE}/original`,
    viewer_url: "/v", role: "direct", kind_label: null, relations: [], effectivity: null,
    more_clauses: 0,
    clauses: [{
      evidence_id: `ev_${NODE}`, node_id: NODE, label: "Khoản 1 Điều 5", heading: "Điều 5. Thời hạn",
      page: 3, tier: "direct", match: "phrase", matched_terms: [], topics: [], same_as: [],
      also_matched: [], ocr: true,
      excerpt: { start: 0, end: clauseText.length, text: clauseText, truncated_before: false,
                 truncated_after: false, highlights: [] },
    }],
    ...extra,
  };
}

function result(answer: Partial<NonNullable<SynthesisResult["answer"]>>, extra: Partial<SynthesisResult> = {}):
  SynthesisResult {
  return {
    result_set_id: "rs_12345678", mode: "focused",
    layers: { verbatim: [], interpretation: [], suggestions: [] },
    coverage: { used: 1, total: 1, groups_remaining: 0, partial: false, message: "Đã diễn giải toàn bộ 1 văn bản." },
    can_continue: false, model_calls: 1, external_ai_used: false, ai_limited: false,
    disclaimer: "AI chỉ diễn giải căn cứ gắn kèm.",
    answer: {
      status: "answered", question: "Thời hạn HƯ CẤU", lead: { text: "", evidence_ids: [], notes: [] },
      focus: { aspects: ["thời hạn"], subject: ["HƯ CẤU"], strict: true }, points: [], gaps: [],
      notes: [], documents: [], reviewed_documents: [], evidence: [], other_documents: [],
      excluded: { other_aspect: 0, off_topic: 0, mentioned: 0 }, rejected: [],
      ...answer,
    },
    ...extra,
  };
}

it("says a penalty was not found and keeps same-subject documents apart", () => {
  render(<AiAnswerView accessToken="t" result={result({
    status: "not_found",
    lead: { text: "Chưa tìm thấy trong kho điều khoản quy định xử phạt về “nồng độ cồn”.",
            evidence_ids: [], notes: [], source: "system" },
    gaps: ["Kho có 1 văn bản nêu “nồng độ cồn” ở nội dung khác."],
    other_documents: [document("63/2030/TT-BCA", "d) Kiểm tra ngay nồng độ cồn tại hiện trường;")],
  }, { model_calls: 0 })} />);
  const answer = screen.getByRole("region", { name: "Diễn giải bằng AI" });
  expect(answer).toHaveAttribute("data-status", "not_found");
  expect(within(answer).getByText(/Chưa tìm thấy trong kho điều khoản quy định xử phạt/))
    .toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Căn cứ hỗ trợ" })).not.toBeInTheDocument();
  expect(screen.getByText(/không trả lời câu hỏi \(1 văn bản\)/)).toBeInTheDocument();
  expect(screen.getByText(/không được dùng để diễn giải hay suy ra/)).toBeInTheDocument();
});

it("puts the answer first and links each statement to a numbered supporting clause", () => {
  const onContinue = vi.fn();
  render(<AiAnswerView accessToken="t" onContinue={onContinue} result={result({
    lead: { text: "Thời hạn là 10 ngày làm việc.", evidence_ids: [`ev_${NODE}`], notes: [],
            source: "ai", status: "verified" },
    points: [{ text: "Cá nhân gửi báo cáo bằng văn bản.", evidence_ids: [`ev_${NODE}`],
               status: "needs_review", notes: ["căn cứ có điều kiện áp dụng chưa được nêu"] }],
    documents: [document("9/2030/TT-BCA", "1. Thời hạn là 10 ngày làm việc kể từ ngày nhận.")],
  }, { can_continue: true })} />);
  const lead = screen.getByText(/Thời hạn là 10 ngày làm việc\./, { selector: "p" });
  expect(within(lead).getByRole("link", { name: "[1]" }))
    .toHaveAttribute("href", "#ai-rs_12345-ev_" + NODE);
  expect(screen.getByText(/Cần đối chiếu: căn cứ có điều kiện áp dụng chưa được nêu/))
    .toBeInTheDocument();
  const support = screen.getByRole("region", { name: "Căn cứ hỗ trợ" });
  expect(within(support).getByText("Thông tư 9/2030/TT-BCA")).toBeInTheDocument();
  expect(within(support).getByText(/Hiệu lực: Chưa xác minh trong kho/)).toBeInTheDocument();
  expect(within(support).getByText(/Trích từ bản scan qua OCR đã duyệt/)).toBeInTheDocument();
  expect(within(support).getByRole("button", { name: "Mở văn bản gốc" })).toBeEnabled();
  fireEvent.click(screen.getByRole("button", { name: "Diễn giải tiếp" }));
  expect(onContinue).toHaveBeenCalledOnce();
});
