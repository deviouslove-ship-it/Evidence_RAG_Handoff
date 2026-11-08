import type { ComprehensiveDocument, ComprehensiveItem } from "../api/client";
import type {
  AnswerDocument,
  DocumentRelation,
  EffectivityView,
  EvidenceRef,
  Excerpt,
} from "../types";

/** One clause of a document card, whatever page produced it (chat or search). */
export interface DocClauseView {
  key: string;
  label: string;
  heading?: string | null;
  page?: number | null;
  pageEnd?: number | null;
  tier: string;
  match: string;
  matchedTerms: string[];
  excerpt: Excerpt;
  fullText?: string;
  sameAsLabel?: string;
  alsoMatched: string[];
  originalUrl?: string | null;
  topics: string[];
  effectivity?: EffectivityView | null;
  /** Quote is OCR text of a scanned page (reviewed); the scan is the original. */
  ocr?: boolean;
}

export interface DocView {
  key: string;
  docTypeLabel: string;
  kindLabel?: string | null;
  number?: string | null;
  title: string;
  issuingBody?: string | null;
  publicationDate?: string | null;
  sourceFormat: string;
  originalFilename?: string | null;
  originalUrl?: string | null;
  role: string;
  relations: DocumentRelation[];
  effectivity?: EffectivityView | null;
  clauses: DocClauseView[];
  moreClauses: number;
}

export const DOC_TYPE_LABELS: Record<string, string> = {
  law: "Luật",
  code: "Bộ luật",
  ordinance: "Pháp lệnh",
  resolution: "Nghị quyết",
  decree: "Nghị định",
  circular: "Thông tư",
  joint_circular: "Thông tư liên tịch",
  decision: "Quyết định",
  directive: "Chỉ thị",
  consolidated: "Văn bản hợp nhất",
  other: "Văn bản khác",
};

export const MATCH_LABELS: Record<string, string> = {
  phrase: "Khớp đúng cụm từ",
  terms: "Khớp đủ từ khóa",
  number: "Đúng số hiệu được hỏi",
  article: "Đúng điều khoản được hỏi",
  semantic: "Khớp theo nghĩa",
  concept: "Khớp khái niệm mở rộng",
  relation: "Văn bản có quan hệ",
  partial: "Khớp một phần",
  none: "Khớp rời rạc",
};

export const TIER_LABELS: Record<string, string> = {
  direct: "Liên quan trực tiếp",
  related: "Có liên quan",
  reference: "Chỉ nhắc đến",
  weak: "Khớp một phần",
  unscored: "Chưa phân loại",
};

export const SOURCE_FORMAT_LABELS: Record<string, string> = {
  pdf: "PDF",
  docx: "Word (.docx)",
  doc: "Word (.doc)",
  txt: "Văn bản thuần (.txt)",
};

/** Citation numbers [1], [2], … in the order the supporting clauses are listed. */
export function citationNumbers(documents: AnswerDocument[]): Map<string, number> {
  const numbers = new Map<string, number>();
  for (const document of documents) {
    for (const clause of document.clauses) {
      if (!numbers.has(clause.evidence_id)) numbers.set(clause.evidence_id, numbers.size + 1);
    }
  }
  return numbers;
}

export function formatVnDate(value?: string | null): string | undefined {
  if (!value) return undefined;
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  return match ? `${match[3]}/${match[2]}/${match[1]}` : undefined;
}

const LEADING_TYPE = [
  "Thông tư liên tịch", "Văn bản hợp nhất", "Thông tư", "Nghị định", "Quyết định", "Chỉ thị",
  "Nghị quyết", "Pháp lệnh", "Bộ luật", "Luật",
];

function fold(value: string): string {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/đ/g, "d")
    .replace(/Đ/g, "D").toLowerCase();
}

/** Trích yếu without a title-cased copy of the type ("Thông Tư Quy định…" → "Quy định…"). */
export function cleanTitle(title: string): string {
  const clean = title.replace(/\s+/g, " ").trim();
  const folded = fold(clean);
  for (const kind of LEADING_TYPE) {
    const key = fold(kind);
    if (folded.startsWith(`${key} `)) {
      const rest = clean.split(" ").slice(kind.split(" ").length).join(" ");
      if (rest && rest[0] === rest[0].toUpperCase() && rest[0] !== rest[0].toLowerCase()) {
        return rest;
      }
    }
  }
  return clean;
}

const ARTICLE_LABEL = /^\s*(Điều\s+\d+[a-zđ]?)\s*[.:]?\s*(.*)$/is;

/** Short citation label and the Điều title, for clauses of older payloads. */
export function splitLabel(
  label: string, nodeType?: string, path?: string,
): { label: string; heading?: string } {
  const text = label.replace(/\s+/g, " ").trim();
  const part = /\s*\((phần\s+\d+)\)\s*$/i.exec(text);
  const suffix = part ? ` (${part[1]})` : "";
  const base = part ? text.slice(0, part.index) : text;
  if (nodeType === "paragraph" || base === "paragraph" || base === "") {
    return { label: ((path ?? "").startsWith("000001:") ? "Phần mở đầu" : "Đoạn không đánh số") + suffix };
  }
  const article = ARTICLE_LABEL.exec(base);
  if (article && (!nodeType || nodeType === "article")) {
    return { label: article[1] + suffix, heading: article[2] || undefined };
  }
  return { label: base + suffix };
}

export function fromAnswerDocument(
  document: AnswerDocument, quotes: Map<string, string>, labels: Map<string, string>,
): DocView {
  return {
    key: document.document_id,
    docTypeLabel: document.doc_type_label,
    kindLabel: document.kind_label,
    number: document.document_number,
    title: document.title,
    issuingBody: document.issuing_body,
    publicationDate: document.publication_date,
    sourceFormat: document.source_format,
    originalFilename: document.original_filename,
    originalUrl: document.original_url,
    role: document.role,
    relations: document.relations,
    effectivity: document.effectivity,
    moreClauses: document.more_clauses,
    clauses: document.clauses.map((clause) => ({
      key: clause.evidence_id,
      label: clause.label,
      heading: clause.heading,
      page: clause.page,
      pageEnd: clause.page_end,
      tier: clause.tier,
      match: clause.match,
      matchedTerms: clause.matched_terms,
      excerpt: clause.excerpt,
      fullText: quotes.get(clause.evidence_id),
      sameAsLabel: clause.same_as.length ? labels.get(clause.same_as[0]) : undefined,
      alsoMatched: clause.also_matched,
      originalUrl: document.original_url,
      topics: clause.topics,
      effectivity: clause.effectivity,
      ocr: clause.ocr,
    })),
  };
}

/** Older payloads (and the development profile) carry only the evidence list. */
export function fromEvidence(evidence: EvidenceRef[]): DocView[] {
  const groups = new Map<string, EvidenceRef[]>();
  for (const item of evidence) {
    const list = groups.get(item.document_id) ?? [];
    list.push(item);
    groups.set(item.document_id, list);
  }
  return Array.from(groups.values()).map((items) => {
    const first = items[0];
    return {
      key: first.document_id,
      docTypeLabel: "Văn bản",
      number: first.document_number,
      title: cleanTitle(first.title),
      sourceFormat: "pdf",
      originalUrl: first.original_url,
      role: "related",
      relations: [],
      effectivity: first.effectivity,
      moreClauses: 0,
      clauses: items.map((item) => {
        const split = splitLabel(item.label);
        const text = item.quote_exact;
        const end = text.length > 480 ? text.lastIndexOf(" ", 420) : text.length;
        const cut = end > 200 ? end : Math.min(text.length, 480);
        return {
          key: item.evidence_id,
          label: split.label,
          heading: split.heading,
          page: item.page,
          tier: "related",
          match: "partial",
          matchedTerms: [],
          excerpt: {
            start: 0, end: cut, text: text.slice(0, cut), truncated_before: false,
            truncated_after: cut < text.length, highlights: [],
          },
          fullText: text,
          alsoMatched: [],
          originalUrl: item.original_url,
          topics: [],
          effectivity: item.effectivity,
        };
      }),
    };
  });
}

function itemExcerpt(item: ComprehensiveItem): Excerpt {
  if (item.excerpt) return item.excerpt;
  const text = item.quote_exact.slice(0, 480);
  return {
    start: 0, end: text.length, text, truncated_before: false,
    truncated_after: text.length < item.quote_exact.length, highlights: [],
  };
}

export function fromSearchItem(item: ComprehensiveItem): DocClauseView {
  const split = splitLabel(item.label, item.node_type, item.path);
  return {
    key: item.node_id,
    label: split.label,
    heading: item.heading ?? split.heading,
    page: item.page,
    pageEnd: item.page_end,
    tier: item.listing ? "reference" : item.tier ?? "unscored",
    match: item.match ?? "none",
    matchedTerms: item.matched_terms ?? [],
    excerpt: itemExcerpt(item),
    fullText: item.quote_exact,
    alsoMatched: [],
    originalUrl: item.original_url,
    topics: [],
    effectivity: item.effectivity,
    ocr: item.extraction_method === "local_ocr",
  };
}

export function fromSearchDocument(document: ComprehensiveDocument): DocView {
  return {
    key: document.document_id,
    docTypeLabel: DOC_TYPE_LABELS[document.doc_type] ?? "Văn bản",
    kindLabel: document.listing ? "Danh mục, liệt kê văn bản" : document.kind_label,
    number: document.document_number,
    title: document.display_title ?? cleanTitle(document.title),
    issuingBody: document.issuing_body,
    publicationDate: document.publication_date,
    sourceFormat: document.source_format ?? "pdf",
    originalFilename: document.original_filename,
    originalUrl: document.original_url,
    role: document.listing ? "reference" : document.best_tier,
    relations: [],
    effectivity: document.effectivity,
    moreClauses: Math.max(0, document.matched_clause_count - document.clauses.length),
    clauses: document.clauses.map(fromSearchItem),
  };
}
