import { EffectivityBadges } from "./EffectivityBadges";
import { OpenOriginalButton } from "./OpenOriginalButton";
import type {
  AmendmentState,
  ConflictFindingView,
  EffectivityView,
} from "../types";
import {
  CONFLICT_FINDING_TYPE_LABELS,
  CONFLICT_PRECEDENCE_LABELS,
  CONFLICT_REVIEW_STATUS_LABELS,
  CONFLICT_SEVERITY_LABELS,
  CONTENT_TAXONOMY_LABELS,
} from "../types";

export interface ConflictFindingCardProps {
  finding: ConflictFindingView;
  accessToken?: string;
  onCompareDocuments?: (leftDocumentId: string, rightDocumentId: string) => void;
}

const VALID_AMENDMENT_STATES = new Set<string>([
  "active",
  "modified",
  "repealed",
  "replaced",
  "suspended",
  "not_yet_effective",
  "unknown",
]);

interface PrecedenceTierInfo {
  rule_code?: string;
  doc_type?: string;
  authority_rank?: number;
  authority_tier_label?: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function parseTierInfo(value: unknown): PrecedenceTierInfo | undefined {
  if (!isRecord(value)) return undefined;
  return {
    rule_code: typeof value.rule_code === "string" ? value.rule_code : undefined,
    doc_type: typeof value.doc_type === "string" ? value.doc_type : undefined,
    authority_rank: typeof value.authority_rank === "number" ? value.authority_rank : undefined,
    authority_tier_label:
      typeof value.authority_tier_label === "string" ? value.authority_tier_label : undefined,
  };
}

function buildMinimalEffectivity(rawStatus: unknown, asOfDate: unknown): EffectivityView {
  const status: AmendmentState =
    typeof rawStatus === "string" && VALID_AMENDMENT_STATES.has(rawStatus)
      ? (rawStatus as AmendmentState)
      : "unknown";
  return {
    status,
    verification: status === "unknown" ? "not_found" : "verified",
    level: "document",
    as_of_date: typeof asOfDate === "string" ? asOfDate : null,
    notes: [],
    pending_proposals: 0,
    clause_level_reviewed: false,
  };
}

function formatTierText(sideLabel: string, tier: PrecedenceTierInfo | undefined): string | undefined {
  if (!tier?.authority_tier_label) return undefined;
  if (typeof tier.authority_rank === "number") {
    return `${sideLabel}: ${tier.authority_tier_label} (bậc ${tier.authority_rank})`;
  }
  return `${sideLabel}: ${tier.authority_tier_label}`;
}

export function ConflictFindingCard({
  finding,
  accessToken,
  onCompareDocuments,
}: ConflictFindingCardProps) {
  const basisJson = isRecord(finding.precedence_basis_json)
    ? finding.precedence_basis_json
    : {};
  const asOfDate = basisJson.as_of_date;
  const effectivityA = buildMinimalEffectivity(basisJson.status_a, asOfDate);
  const effectivityB = buildMinimalEffectivity(basisJson.status_b, asOfDate);
  const tierA = parseTierInfo(basisJson.tier_a);
  const tierB = parseTierInfo(basisJson.tier_b);
  const basisText = typeof basisJson.basis === "string" ? basisJson.basis : undefined;
  const caveats = Array.isArray(basisJson.caveats)
    ? basisJson.caveats.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    : [];
  const showWarning =
    finding.precedence_result === "undetermined_requires_review" || caveats.length > 0;

  const tierALabel = formatTierText("Vế A", tierA);
  const tierBLabel = formatTierText("Vế B", tierB);

  const sideAHeading =
    [finding.document_a_number, finding.document_a_title].filter(Boolean).join(" · ") ||
    finding.document_a_id;
  const sideBHeading =
    [finding.document_b_number, finding.document_b_title].filter(Boolean).join(" · ") ||
    finding.document_b_id;

  return (
    <article
      className="conflict-finding-card"
      data-severity={finding.severity}
      data-type={finding.finding_type}
    >
      <p className="conflict-disclaimer status-pill status-warning" role="note">
        {finding.reference_notice || "Gợi ý tự động — cần chuyên viên thẩm định trước khi áp dụng."}
      </p>

      <header className="conflict-finding-head">
        <div className="conflict-finding-tags">
          <span className="tag conflict-type-tag" data-type={finding.finding_type}>
            {CONFLICT_FINDING_TYPE_LABELS[finding.finding_type] ?? finding.finding_type}
          </span>
          <span className="tag conflict-severity-tag" data-severity={finding.severity}>
            {CONFLICT_SEVERITY_LABELS[finding.severity] ?? finding.severity}
          </span>
          <span className="tag">
            {finding.detection_method === "rule_plus_ai" ? "Quy tắc + AI" : "Quy tắc xác định"}
          </span>
          <span className="tag conflict-review-tag" data-status={finding.review_status}>
            {CONFLICT_REVIEW_STATUS_LABELS[finding.review_status] ?? finding.review_status}
          </span>
          {finding.shared_labels.map((code) => (
            <span className="tag" key={code}>
              {CONTENT_TAXONOMY_LABELS[code] ?? code}
            </span>
          ))}
        </div>
        {onCompareDocuments && (
          <button
            className="secondary-button"
            onClick={() => onCompareDocuments(finding.document_a_id, finding.document_b_id)}
            type="button"
          >
            So sánh chi tiết 2 văn bản này
          </button>
        )}
      </header>

      <p className="conflict-explanation">{finding.explanation}</p>

      {(finding.ai_confidence !== null || finding.ai_verified !== null) && (
        <p className="evidence-meta">
          {finding.ai_verified !== null && (
            <>Kiểm chứng AI: {finding.ai_verified ? "Đã đối chiếu" : "Cần kiểm tra lại"}</>
          )}
          {finding.ai_confidence !== null && (
            <>
              {finding.ai_verified !== null ? " · " : ""}
              Độ tin cậy gợi ý: {Math.round(finding.ai_confidence * 100)}%
            </>
          )}
        </p>
      )}

      <div className="conflict-sides">
        <section className="conflict-side" data-side="a" aria-label="Vế A">
          <div className="conflict-side-head">
            <strong className="conflict-doc-title">{sideAHeading}</strong>
            <span className="tag">
              {finding.node_a_label || finding.node_a_path || "Đoạn văn"}
            </span>
            {finding.node_a_page_start != null && (
              <span className="tag page-tag">Trang {finding.node_a_page_start}</span>
            )}
            <EffectivityBadges compact view={effectivityA} />
          </div>
          <p className="conflict-node-text">
            {finding.node_a_text ?? "(Không có nội dung trích dẫn)"}
          </p>
          <div className="conflict-side-actions">
            <OpenOriginalButton
              accessToken={accessToken}
              className="link-button"
              label={
                finding.node_a_page_start != null
                  ? `Mở gốc vế A (trang ${finding.node_a_page_start})`
                  : "Mở gốc vế A"
              }
              page={finding.node_a_page_start}
              showHint={false}
              sourceFormat="pdf"
              url={`/api/v1/citations/ev_${finding.node_a_id}/original`}
            />
          </div>
        </section>

        <section className="conflict-side" data-side="b" aria-label="Vế B">
          <div className="conflict-side-head">
            <strong className="conflict-doc-title">{sideBHeading}</strong>
            <span className="tag">
              {finding.node_b_label || finding.node_b_path || "Đoạn văn"}
            </span>
            {finding.node_b_page_start != null && (
              <span className="tag page-tag">Trang {finding.node_b_page_start}</span>
            )}
            <EffectivityBadges compact view={effectivityB} />
          </div>
          <p className="conflict-node-text">
            {finding.node_b_text ?? "(Không có nội dung trích dẫn)"}
          </p>
          <div className="conflict-side-actions">
            <OpenOriginalButton
              accessToken={accessToken}
              className="link-button"
              label={
                finding.node_b_page_start != null
                  ? `Mở gốc vế B (trang ${finding.node_b_page_start})`
                  : "Mở gốc vế B"
              }
              page={finding.node_b_page_start}
              showHint={false}
              sourceFormat="pdf"
              url={`/api/v1/citations/ev_${finding.node_b_id}/original`}
            />
          </div>
        </section>
      </div>

      <section className="conflict-precedence" aria-label="Đánh giá thứ bậc hiệu lực tham khảo">
        <h4>Đánh giá thứ bậc hiệu lực tham khảo</h4>
        <p className="conflict-precedence-result">
          <strong>
            {CONFLICT_PRECEDENCE_LABELS[finding.precedence_result] ?? finding.precedence_result}
          </strong>
        </p>
        {basisText && <p className="conflict-precedence-basis">{basisText}</p>}
        {(tierALabel || tierBLabel) && (
          <p className="evidence-meta">
            {[tierALabel, tierBLabel].filter(Boolean).join(" · ")}
          </p>
        )}
        {showWarning && (
          <div className="conflict-precedence-warning" role="note">
            {finding.precedence_result === "undetermined_requires_review" && (
              <p>
                Chưa đủ căn cứ tự động xác định văn bản nào ưu tiên áp dụng — bắt buộc chuyên viên
                kiểm tra thẩm quyền, ngày hiệu lực và quan hệ sửa đổi.
              </p>
            )}
            {caveats.length > 0 && (
              <ul>
                {caveats.map((caveat, index) => (
                  <li key={index}>{caveat}</li>
                ))}
              </ul>
            )}
          </div>
        )}
      </section>
    </article>
  );
}
