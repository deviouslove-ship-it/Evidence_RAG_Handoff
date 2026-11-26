import type { PageTextResponse } from "../types";

export interface PageTextIntent {
  pageNumber: number;
  isPrintedPage: boolean;
  docHint: string;
  preferAi: boolean;
}

export interface PageTextCandidateDoc {
  document_id: string;
  document_version_id: string;
  title: string;
  document_number?: string | null;
}

export type PageTextEntryState =
  | {
      kind: "choose_doc";
      pageNumber: number;
      isPrintedPage: boolean;
      preferAi?: boolean;
      candidates: PageTextCandidateDoc[];
    }
  | { kind: "confirm_pdf_page"; pageNumber: number; candidate: PageTextCandidateDoc; preferAi?: boolean }
  | { kind: "missing_doc"; pageNumber: number }
  | { kind: "not_found"; query: string }
  | {
      kind: "loading";
      candidate: PageTextCandidateDoc;
      pageNumber: number;
      response?: PageTextResponse;
    }
  | { kind: "ready"; candidate: PageTextCandidateDoc; response: PageTextResponse }
  | { kind: "error"; candidate?: PageTextCandidateDoc; pageNumber: number; message: string };

const PAGE_TOKEN = /(?:^|[\s,.;:!?()"])trang(?:\s+(in|sách|giấy|tài\s+liệu|pdf))?\s+(\d{1,4})(?=$|[\s,.;:!?()"])/iu;
const READING_HINT =
  /(?:^|[\s,.;:!?()"])(?:nội\s+dung|đọc|xem|lấy|text|chép|toàn\s+bộ|nguyên\s+văn|viết\s+gì|có\s+gì|nói\s+gì|là\s+gì|chữ)(?=$|[\s,.;:!?()"])/iu;
const STOP_PHRASES =
  /(?:^|\s)(?:(?:văn\s+bản|tài\s+liệu|báo\s+cáo)\s+(?:này|đó)|nội\s+dung|đọc(?:\s+nguyên\s+văn|\s+lại)?|xem(?:\s+lại)?|lấy|text|chép|toàn\s+bộ|nguyên\s+văn|viết\s+gì|có\s+gì|nói\s+gì|là\s+gì|của|trong|ở|cho\s+tôi|tôi\s+cần|vui\s+lòng|từ\s+ảnh|bằng\s+(?:OCR\s+)?AI)(?=$|\s)/giu;

export function detectPageTextIntent(rawQuery: string): PageTextIntent | null {
  const clean = rawQuery.trim();
  if (!clean) return null;
  const match = clean.match(PAGE_TOKEN);
  if (!match) return null;
  const startsWithPage = /^trang(?:\s+(?:in|sách|giấy|tài\s+liệu|pdf))?\s+\d{1,4}/iu.test(clean);
  if (!startsWithPage && !READING_HINT.test(clean)) return null;
  const modifier = (match[1] ?? "").toLowerCase();
  const pageNumber = Number.parseInt(match[2], 10);
  if (!Number.isFinite(pageNumber) || pageNumber < 1) return null;
  const isPrintedPage = modifier === "in" || modifier === "sách" || modifier === "giấy";

  const idx = match.index ?? 0;
  let remainder = (clean.slice(0, idx) + " " + clean.slice(idx + match[0].length))
    .replace(/[?!.,;:()"]/g, " ")
    .replace(STOP_PHRASES, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (/^(?:văn\s+bản|tài\s+liệu)$/iu.test(remainder)) {
    remainder = "";
  }
  const preferAi = /đọc\s+lại|từ\s+ảnh|(?:OCR\s+)?AI/iu.test(clean);
  return { pageNumber, isPrintedPage, docHint: remainder, preferAi };
}
