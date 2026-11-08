import { useState } from "react";

import type { Excerpt, TextSpan } from "../types";
import { EffectivityBadges } from "./EffectivityBadges";
import {
  MATCH_LABELS,
  SOURCE_FORMAT_LABELS,
  TIER_LABELS,
  formatVnDate,
  type DocClauseView,
  type DocView,
} from "./documentDisplay";
import { OpenOriginalButton } from "./OpenOriginalButton";

function Marked({ text, highlights }: { text: string; highlights: TextSpan[] }) {
  const ranges = highlights
    .filter((span) => Number.isFinite(span.start) && Number.isFinite(span.end))
    .map((span) => ({ start: Math.max(0, span.start), end: Math.min(text.length, span.end) }))
    .filter((span) => span.end > span.start)
    .sort((a, b) => a.start - b.start);
  const parts: Array<{ text: string; marked: boolean }> = [];
  let cursor = 0;
  for (const range of ranges) {
    if (range.start < cursor) continue;
    if (range.start > cursor) parts.push({ text: text.slice(cursor, range.start), marked: false });
    parts.push({ text: text.slice(range.start, range.end), marked: true });
    cursor = range.end;
  }
  if (cursor < text.length) parts.push({ text: text.slice(cursor), marked: false });
  return (
    <>
      {parts.map((part, index) =>
        part.marked ? <mark key={index}>{part.text}</mark> : <span key={index}>{part.text}</span>,
      )}
    </>
  );
}

export function ExcerptQuote({ excerpt, fullText, expanded }: {
  excerpt: Excerpt; fullText?: string; expanded: boolean;
}) {
  if (expanded && fullText) {
    const shifted = excerpt.highlights.map((span) => ({
      start: span.start + excerpt.start, end: span.end + excerpt.start,
    }));
    return (
      <blockquote className="clause-quote clause-quote-full">
        <Marked highlights={shifted} text={fullText} />
      </blockquote>
    );
  }
  return (
    <blockquote className="clause-quote">
      {excerpt.truncated_before && <span aria-hidden="true">… </span>}
      <Marked highlights={excerpt.highlights} text={excerpt.text} />
      {excerpt.truncated_after && <span aria-hidden="true"> …</span>}
    </blockquote>
  );
}

function ClauseItem({ clause, sourceFormat, accessToken }: {
  clause: DocClauseView; sourceFormat: string; accessToken?: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const canExpand = Boolean(clause.fullText) &&
    (clause.excerpt.truncated_before || clause.excerpt.truncated_after);
  const pageText = sourceFormat === "pdf" && clause.page
    ? clause.pageEnd && clause.pageEnd > clause.page
      ? `Trang ${clause.page}–${clause.pageEnd}`
      : `Trang ${clause.page}`
    : undefined;
  return (
    <li className="doc-clause" data-tier={clause.tier}>
      <div className="doc-clause-head">
        <strong className="doc-clause-label">{clause.label}</strong>
        {clause.heading && <span className="doc-clause-heading">{clause.heading}</span>}
      </div>
      <div className="doc-clause-tags">
        <span className="tag match-tag" data-match={clause.match}>
          {MATCH_LABELS[clause.match] ?? MATCH_LABELS.none}
        </span>
        {clause.tier !== "direct" && (
          <span className="tag tier-tag" data-tier={clause.tier}>
            {TIER_LABELS[clause.tier] ?? clause.tier}
          </span>
        )}
        {pageText && <span className="tag page-tag">{pageText}</span>}
        {clause.effectivity?.level === "node" && (
          <EffectivityBadges compact view={clause.effectivity} />
        )}
      </div>
      {clause.sameAsLabel ? (
        <p className="doc-clause-same">
          Nội dung giống {clause.sameAsLabel} (đã trích ở trên).
          {clause.fullText && (
            <button className="link-button" onClick={() => setExpanded((value) => !value)}
                    type="button">
              {expanded ? "Ẩn" : "Xem nguyên văn"}
            </button>
          )}
        </p>
      ) : null}
      {(!clause.sameAsLabel || expanded) && (
        <ExcerptQuote excerpt={clause.excerpt} expanded={expanded} fullText={clause.fullText} />
      )}
      {clause.alsoMatched.length > 0 && (
        <p className="doc-clause-also">Cùng điều còn khớp: {clause.alsoMatched.join("; ")}.</p>
      )}
      {clause.ocr && (
        <p className="doc-clause-also">
          Trích từ bản scan qua OCR đã được duyệt; vị trí chỉ xác định đến trang. Đối chiếu
          bản gốc khi cần.
        </p>
      )}
      <div className="doc-clause-actions">
        {canExpand && !clause.sameAsLabel && (
          <button className="link-button" onClick={() => setExpanded((value) => !value)}
                  type="button">
            {expanded ? "Thu gọn trích dẫn" : "Xem toàn văn điều khoản"}
          </button>
        )}
        {sourceFormat === "pdf" && clause.page && clause.originalUrl && (
          <OpenOriginalButton
            accessToken={accessToken}
            className="link-button"
            label={`Mở PDF gốc tại trang ${clause.page}`}
            page={clause.page}
            showHint={false}
            sourceFormat={sourceFormat}
            url={clause.originalUrl}
          />
        )}
      </div>
    </li>
  );
}

interface DocumentCardProps {
  document: DocView;
  accessToken?: string;
  index?: number;
  onLoadMore?: () => void;
  loadingMore?: boolean;
}

export function DocumentCard({
  document, accessToken, index, onLoadMore, loadingMore,
}: DocumentCardProps) {
  const date = formatVnDate(document.publicationDate);
  const firstPage = document.clauses.find((clause) => clause.page)?.page;
  const headingId = `doc-${document.key}`;
  return (
    <article aria-labelledby={headingId} className="doc-card" data-role={document.role}>
      <header className="doc-card-header">
        <div className="doc-card-ident">
          <p className="doc-card-type">
            {index !== undefined && <span className="doc-card-index">{index}.</span>}
            {document.docTypeLabel}
            {document.kindLabel && <span className="tag kind-tag">{document.kindLabel}</span>}
            {document.role !== "direct" && (
              <span className="tag tier-tag" data-tier={document.role}>
                {TIER_LABELS[document.role] ?? document.role}
              </span>
            )}
          </p>
          <h3 className="doc-card-number" id={headingId}>
            {document.number ?? "Chưa có số hiệu trong kho"}
          </h3>
        </div>
        <OpenOriginalButton
          accessToken={accessToken}
          page={document.sourceFormat === "pdf" ? firstPage : undefined}
          sourceFormat={document.sourceFormat}
          url={document.originalUrl}
        />
      </header>
      <p className="doc-card-title">{document.title}</p>
      <dl className="doc-card-meta">
        <div>
          <dt>Ngày ban hành</dt>
          <dd>{date ?? "Chưa xác định"}</dd>
        </div>
        <div>
          <dt>Cơ quan ban hành</dt>
          <dd>{document.issuingBody ?? "Chưa xác định"}</dd>
        </div>
        <div>
          <dt>Tệp gốc</dt>
          <dd>{SOURCE_FORMAT_LABELS[document.sourceFormat] ?? document.sourceFormat}</dd>
        </div>
        <div>
          <dt>Hiệu lực</dt>
          <dd><EffectivityBadges compact view={document.effectivity} /></dd>
        </div>
      </dl>
      {document.relations.length > 0 && (
        <ul className="doc-card-relations" aria-label="Quan hệ văn bản">
          {document.relations.map((relation) => (
            <li key={`${relation.kind}-${relation.label}`}>
              {relation.label}
              <small> · {relation.verified ? "đã xác minh" : relation.source.toLowerCase()}</small>
            </li>
          ))}
        </ul>
      )}
      <ol className="doc-clauses">
        {document.clauses.map((clause) => (
          <ClauseItem
            accessToken={accessToken}
            clause={clause}
            key={clause.key}
            sourceFormat={document.sourceFormat}
          />
        ))}
      </ol>
      {document.moreClauses > 0 && (
        <div className="doc-card-more">
          {onLoadMore ? (
            <button className="secondary-button" disabled={loadingMore} onClick={onLoadMore}
                    type="button">
              {loadingMore ? "Đang tải…" : `Xem thêm ${document.moreClauses} điều khoản khớp`}
            </button>
          ) : (
            <span className="evidence-meta">
              Còn {document.moreClauses} điều khoản khớp khác trong văn bản này.
            </span>
          )}
        </div>
      )}
    </article>
  );
}
