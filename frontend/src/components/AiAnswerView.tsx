import type { FocusedAnswer, FocusedClaim, SynthesisResult } from "../api/client";
import type { AnswerClause, AnswerDocument } from "../types";
import { citationNumbers, formatVnDate } from "./documentDisplay";
import { STATUS_LABELS } from "./effectivityLabels";
import { OpenOriginalButton } from "./OpenOriginalButton";

const SHORT_QUOTE = 320;

function shortQuote(clause: AnswerClause): string {
  const text = clause.excerpt.text.replace(/\s+/g, " ").trim();
  if (text.length <= SHORT_QUOTE) return text;
  const cut = text.lastIndexOf(" ", SHORT_QUOTE);
  return `${text.slice(0, cut > SHORT_QUOTE * 0.6 ? cut : SHORT_QUOTE)} …`;
}

function documentName(document: AnswerDocument): string {
  const kind = document.kind_label === "Văn bản hợp nhất" ? "Văn bản hợp nhất" : document.doc_type_label;
  return `${kind} ${document.document_number ?? "chưa có số hiệu"}`;
}

/** Effectivity is stated only when a person verified it; otherwise say so. */
function effectivityText(document: AnswerDocument): string {
  const view = document.effectivity;
  if (view && view.verification === "verified") {
    return `${STATUS_LABELS[view.status] ?? "Chưa xác định"} (đã xác minh)`;
  }
  return "Chưa xác minh trong kho";
}

function Cites({ ids, numbers, anchor }: {
  ids: string[]; numbers: Map<string, number>; anchor: string;
}) {
  const known = ids.filter((id) => numbers.has(id));
  if (!known.length) return null;
  return (
    <span className="ai-cites">
      {known.map((id) => (
        <a
          className="ai-cite"
          href={`#${anchor}${id}`}
          key={id}
          onClick={(event) => {
            const target = document.getElementById(`${anchor}${id}`);
            if (target) {
              event.preventDefault();
              target.scrollIntoView({ behavior: "smooth", block: "center" });
              target.focus({ preventScroll: true });
            }
          }}
        >
          [{numbers.get(id)}]
        </a>
      ))}
    </span>
  );
}

function Claim({ claim, numbers, anchor }: {
  claim: FocusedClaim; numbers: Map<string, number>; anchor: string;
}) {
  return (
    <>
      {claim.text} <Cites anchor={anchor} ids={claim.evidence_ids} numbers={numbers} />
      {claim.status === "needs_review" && claim.notes.length > 0 && (
        <small className="ai-check-note"> Cần đối chiếu: {claim.notes.join("; ")}.</small>
      )}
    </>
  );
}

function SupportDocument({ document, numbers, anchor, accessToken, index }: {
  document: AnswerDocument; numbers: Map<string, number>; anchor: string;
  accessToken?: string; index?: number;
}) {
  const date = formatVnDate(document.publication_date);
  const firstPage = document.clauses.find((clause) => clause.page)?.page;
  return (
    <article className="ai-support-doc">
      <header className="ai-support-head">
        <div>
          <p className="ai-support-name">
            {index !== undefined && <span className="doc-card-index">{index}.</span>}
            <strong>{documentName(document)}</strong>
            {document.kind_label && document.kind_label !== "Văn bản hợp nhất" && (
              <span className="tag kind-tag">{document.kind_label}</span>
            )}
          </p>
          <p className="ai-support-title">{document.title}</p>
          <p className="ai-support-meta">
            Ngày ban hành: {date ?? "chưa xác định"} · Hiệu lực: {effectivityText(document)}
          </p>
        </div>
        <OpenOriginalButton
          accessToken={accessToken}
          className="secondary-button"
          page={document.source_format === "pdf" ? firstPage : undefined}
          showHint={false}
          sourceFormat={document.source_format}
          url={document.original_url}
        />
      </header>
      <ul className="ai-support-clauses">
        {document.clauses.map((clause) => (
          <li id={`${anchor}${clause.evidence_id}`} key={clause.evidence_id} tabIndex={-1}>
            <p className="ai-support-label">
              {numbers.has(clause.evidence_id) && (
                <span className="ai-cite-number">[{numbers.get(clause.evidence_id)}]</span>
              )}
              <strong>{clause.label}</strong>
              {clause.heading && <span className="doc-clause-heading"> {clause.heading}</span>}
              {document.source_format === "pdf" && clause.page ? (
                <span className="tag page-tag">Trang {clause.page}</span>
              ) : null}
            </p>
            {clause.same_as.length > 0 ? (
              <p className="doc-clause-same">Nội dung giống điều khoản đã trích ở trên.</p>
            ) : (
              <blockquote className="clause-quote">
                {clause.excerpt.truncated_before && <span aria-hidden="true">… </span>}
                {shortQuote(clause)}
              </blockquote>
            )}
            {clause.ocr && (
              <p className="doc-clause-also">
                Trích từ bản scan qua OCR đã duyệt; mở bản gốc để đối chiếu trang {clause.page}.
              </p>
            )}
          </li>
        ))}
      </ul>
    </article>
  );
}

interface AiAnswerViewProps {
  result: SynthesisResult;
  accessToken?: string;
  busy?: boolean;
  onContinue?: () => void;
  /** Distinguishes anchors when two answer views are on one page. */
  anchorPrefix?: string;
}

/**
 * "Diễn giải AI": the answer first (lead, then the checked points with [n] citations),
 * then what is missing, then the supporting documents with short verbatim quotes and a
 * button to open the original file.  Documents that only share the subject are listed
 * apart and never presented as answering the question.
 */
export function AiAnswerView({
  result, accessToken, busy = false, onContinue, anchorPrefix = "ai-",
}: AiAnswerViewProps) {
  const answer: FocusedAnswer | undefined = result.answer;
  if (!answer) return null;
  const anchor = `${anchorPrefix}${result.result_set_id.slice(0, 8)}-`;
  const numbers = citationNumbers(answer.documents);
  const focusText = [
    answer.focus.aspects.length ? `Vấn đề hỏi: ${answer.focus.aspects.join(", ")}` : undefined,
    answer.focus.subject.length ? `Nội dung: ${answer.focus.subject.join(", ")}` : undefined,
  ].filter(Boolean).join(" · ");
  return (
    <section aria-label="Diễn giải bằng AI" className="ai-answer" data-status={answer.status}>
      <header className="ai-answer-header">
        <h3>Diễn giải AI</h3>
        {focusText && <span className="ai-answer-focus">{focusText}</span>}
      </header>
      <p className="ai-answer-lead" data-source={answer.lead.source}>
        <Claim anchor={anchor} claim={answer.lead} numbers={numbers} />
      </p>
      {answer.points.length > 0 && (
        <ul className="ai-answer-points">
          {answer.points.map((point, index) => (
            <li data-status={point.status} key={`${index}-${point.text.slice(0, 24)}`}>
              <Claim anchor={anchor} claim={point} numbers={numbers} />
            </li>
          ))}
        </ul>
      )}
      {answer.gaps.length > 0 && (
        <div className="ai-answer-gaps" role="note">
          {answer.gaps.map((gap) => <p key={gap}>{gap}</p>)}
        </div>
      )}
      {answer.notes.length > 0 && (
        <ul className="answer-notes" aria-label="Lưu ý">
          {answer.notes.map((note) => <li key={note}>{note}</li>)}
        </ul>
      )}
      <div className="ai-answer-coverage">
        <span className="evidence-meta">{result.coverage.message}</span>
        {result.can_continue && onContinue && (
          <button className="secondary-button" disabled={busy} onClick={onContinue} type="button">
            {busy ? "Đang diễn giải…" : "Diễn giải tiếp"}
          </button>
        )}
      </div>
      {answer.documents.length > 0 && (
        <section aria-label="Căn cứ hỗ trợ" className="ai-support">
          <h4>Căn cứ hỗ trợ ({answer.documents.length} văn bản)</h4>
          {answer.documents.map((document, index) => (
            <SupportDocument
              accessToken={accessToken}
              anchor={anchor}
              document={document}
              index={index + 1}
              key={document.document_id}
              numbers={numbers}
            />
          ))}
        </section>
      )}
      {answer.reviewed_documents.length > 0 && (
        <details className="ai-more" open={answer.documents.length === 0}>
          <summary>
            {answer.documents.length === 0
              ? `Căn cứ đã đưa vào diễn giải (${answer.reviewed_documents.length} văn bản), đọc nguyên văn`
              : `Đã đọc nhưng chưa có ý diễn giải qua kiểm tra (${answer.reviewed_documents.length} văn bản)`}
          </summary>
          {answer.reviewed_documents.map((document) => (
            <SupportDocument accessToken={accessToken} anchor={`${anchor}r-`} document={document}
                             key={document.document_id} numbers={new Map()} />
          ))}
        </details>
      )}
      {answer.other_documents.length > 0 && (
        <details className="ai-more">
          <summary>
            Nêu cùng nội dung nhưng không trả lời câu hỏi ({answer.other_documents.length} văn bản)
          </summary>
          <p className="evidence-meta">
            Các điều khoản này không được dùng để diễn giải hay suy ra câu trả lời.
          </p>
          {answer.other_documents.map((document) => (
            <SupportDocument accessToken={accessToken} anchor={`${anchor}o-`} document={document}
                             key={document.document_id} numbers={new Map()} />
          ))}
        </details>
      )}
      <details className="ai-more ai-tech">
        <summary>Thông tin kiểm tra</summary>
        <ul>
          <li>
            Điều khoản không đưa vào diễn giải: {answer.excluded.other_aspect} khác vấn đề hỏi,{" "}
            {answer.excluded.off_topic} chỉ trùng từ chung, {answer.excluded.mentioned} thuộc danh
            mục liệt kê văn bản.
          </li>
          <li>Số lần gọi mô hình: {result.model_calls}{result.external_ai_used ? " (có dùng API ngoài)" : ""}.</li>
          {result.ai_limited && <li>Đã chạm trần chi phí AI; phần còn lại chưa diễn giải.</li>}
          {answer.rejected.length > 0 && (
            <li>
              Ý AI viết bị loại ({answer.rejected.length}):
              <ul>
                {answer.rejected.map((item, index) => (
                  <li key={index}>“{item.text}” — {item.reasons.join("; ")}.</li>
                ))}
              </ul>
            </li>
          )}
        </ul>
      </details>
      <p className="answer-disclaimer">{result.disclaimer}</p>
    </section>
  );
}
