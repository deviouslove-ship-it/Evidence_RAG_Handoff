import type {
  ComparisonItem,
  DiffSegmentView,
  DocumentSide,
  SideView,
  SpanView,
} from "../types";
import {
  COMPARE_AMENDMENT_ACTION_LABELS,
  COMPARE_ALIGNMENT_LABELS,
  COMPARE_IMPACT_LABELS,
  COMPARE_KIND_LABELS,
} from "../types";
import { formatVnDate } from "./documentDisplay";
import { EffectivityBadges } from "./EffectivityBadges";
import { OpenOriginalButton } from "./OpenOriginalButton";

/**
 * Renders one comparison result list entirely with safe React elements: every
 * diff segment becomes a <span>/<del className="diff-del">/<ins className="diff-ins">
 * text node — never dangerouslySetInnerHTML. Each item card carries the change-kind
 * and alignment badges, signal chips, the approved amendment link (if any) and, per
 * side, the page citation, EffectivityBadges and an OpenOriginalButton pointing at
 * `/api/v1/compare/nodes/<primary node_id>/original`.
 */

export interface CompareDiffViewProps {
  items: ComparisonItem[];
  leftDoc: DocumentSide;
  rightDoc: DocumentSide;
  /** Carried from the document picker metadata; a mismatch degrades to download. */
  leftSourceFormat: string;
  rightSourceFormat: string;
  accessToken?: string;
  displayMode: "side_by_side" | "inline";
}

function alignmentLabel(item: ComparisonItem): string | undefined {
  if (!item.alignment_method) return undefined;
  if (item.alignment_method === "semantic_lexical" && item.change_kind === "moved_or_renumbered") {
    return "Khớp nội dung — đổi số hiệu";
  }
  return COMPARE_ALIGNMENT_LABELS[item.alignment_method];
}

/** Same NFC + horizontal-whitespace normalization the backend extractor applies. */
function normalizeForMatch(text: string): string {
  return text.normalize("NFC").replace(/[ \t]+/g, " ");
}

/**
 * Chip text for deadline/amount spans. The contract lists left-only spans first, then
 * right-only spans, without side tags; an "old → new" arrow is shown only when every
 * span can be attributed to exactly one side by its raw text (a literal slice of that
 * side's normalized text). Anything ambiguous degrades to the flat list the server's
 * own deterministic highlights use — no direction is ever invented.
 */
function spanChipText(
  label: string,
  spans: SpanView[],
  left: SideView | null,
  right: SideView | null,
): string {
  if (left && right) {
    const leftText = normalizeForMatch(left.text_original);
    const rightText = normalizeForMatch(right.text_original);
    const leftOnly: string[] = [];
    const rightOnly: string[] = [];
    let ambiguous = false;
    for (const span of spans) {
      const raw = normalizeForMatch(span.raw_text);
      const inLeft = leftText.includes(raw);
      const inRight = rightText.includes(raw);
      if (inLeft && !inRight) leftOnly.push(span.raw_text);
      else if (inRight && !inLeft) rightOnly.push(span.raw_text);
      else ambiguous = true;
    }
    if (!ambiguous && leftOnly.length > 0 && rightOnly.length > 0) {
      return `${label}: ${leftOnly.join(", ")} → ${rightOnly.join(", ")}`;
    }
  }
  return `${label}: ${spans.map((span) => span.raw_text).join(", ")}`;
}

function dateChipText(dates: Array<[number, number, number]>): string {
  return `Ngày: ${dates
    .map(([day, month, year]) =>
      `${String(day).padStart(2, "0")}/${String(month).padStart(2, "0")}/${year}`)
    .join(", ")}`;
}

function signalChips(item: ComparisonItem): string[] {
  const signals = item.signals;
  const chips: string[] = [];
  if (signals.deadlines_changed.length > 0) {
    chips.push(spanChipText("Thời hạn", signals.deadlines_changed, item.left, item.right));
  }
  if (signals.amounts_changed.length > 0) {
    chips.push(spanChipText("Mức tiền/số lượng", signals.amounts_changed, item.left, item.right));
  }
  if (signals.dates_changed.length > 0) chips.push(dateChipText(signals.dates_changed));
  if (signals.modality_shifted) chips.push("Tính bắt buộc thay đổi");
  if (signals.exception_changed) chips.push("Thay đổi ngoại lệ");
  return chips;
}

function sideLabel(side: SideView): string {
  return side.citation_label || side.structural_key || "Đoạn văn";
}

function pageText(side: SideView): string | undefined {
  if (side.page_start == null) return undefined;
  return side.page_end != null && side.page_end > side.page_start
    ? `Trang ${side.page_start}–${side.page_end}`
    : `Trang ${side.page_start}`;
}

/**
 * One side's diff text. "left" keeps equal+delete segments, "right" keeps equal+insert,
 * "inline" keeps all three ops in order. All text is rendered as React text nodes.
 */
function DiffText({ segments, mode }: { segments: DiffSegmentView[]; mode: "left" | "right" | "inline" }) {
  return (
    <p className="compare-text">
      {segments.map((segment, index) => {
        if (segment.op === "equal") return <span key={index}>{segment.text}</span>;
        if (segment.op === "delete") {
          if (mode === "right") return null;
          return <del className="diff-del" key={index}>{segment.text}</del>;
        }
        if (mode === "left") return null;
        return <ins className="diff-ins" key={index}>{segment.text}</ins>;
      })}
    </p>
  );
}

function SideHeader({ side, doc, sourceFormat, accessToken, sideName }: {
  side: SideView;
  doc: DocumentSide;
  sourceFormat: string;
  accessToken?: string;
  sideName: string;
}) {
  const pages = pageText(side);
  return (
    <div className="compare-side-head">
      <strong className="compare-side-label">{sideLabel(side)}</strong>
      {pages && <span className="tag page-tag">{pages}</span>}
      <EffectivityBadges compact view={doc.effectivity} />
      <OpenOriginalButton
        accessToken={accessToken}
        className="link-button"
        label={`Mở gốc ${sideName}${side.page_start != null ? ` (trang ${side.page_start})` : ""}`}
        page={side.page_start}
        showHint={false}
        sourceFormat={sourceFormat}
        url={`/api/v1/compare/nodes/${side.node_id}/original`}
      />
    </div>
  );
}

function ItemCard({ item, leftDoc, rightDoc, leftSourceFormat, rightSourceFormat, accessToken, displayMode }: {
  item: ComparisonItem;
  leftDoc: DocumentSide;
  rightDoc: DocumentSide;
  leftSourceFormat: string;
  rightSourceFormat: string;
  accessToken?: string;
  displayMode: "side_by_side" | "inline";
}) {
  const chips = signalChips(item);
  const alignment = alignmentLabel(item);
  const link = item.amendment_link;
  return (
    <li
      className="compare-item"
      data-impact={item.impact_level}
      data-kind={item.change_kind}
      id={`compare-item-${item.item_key}`}
    >
      <div className="compare-item-tags">
        <span className="tag compare-kind-tag" data-kind={item.change_kind}>
          {COMPARE_KIND_LABELS[item.change_kind]}
        </span>
        {alignment && (
          <span className="tag compare-alignment-tag" data-method={item.alignment_method ?? undefined}>
            {alignment}
          </span>
        )}
        {item.change_kind !== "unchanged" && item.impact_level !== "low" && (
          <span className="tag compare-impact-tag" data-impact={item.impact_level}>
            {COMPARE_IMPACT_LABELS[item.impact_level]}
          </span>
        )}
        {item.change_kind === "moved_or_renumbered" && item.content_also_modified && (
          <span className="tag compare-impact-tag" data-impact="medium">Kèm sửa nội dung</span>
        )}
      </div>
      {chips.length > 0 && (
        <div className="compare-signals">
          {chips.map((chip, index) => (
            <span className="tag compare-signal-tag" key={index}>{chip}</span>
          ))}
        </div>
      )}
      {link && (
        <div className="compare-amendment-link">
          <span>
            Liên kết sửa đổi đã duyệt:{" "}
            {link.action ? COMPARE_AMENDMENT_ACTION_LABELS[link.action] ?? link.action : "sửa đổi"}
            {link.valid_from ? ` — hiệu lực từ ${formatVnDate(link.valid_from) ?? link.valid_from}` : ""}
          </span>
          {link.source_quote && <blockquote className="quote">«{link.source_quote}»</blockquote>}
        </div>
      )}
      {displayMode === "side_by_side" ? (
        <div className="compare-columns">
          <div className="compare-side" data-side="left">
            {item.left ? (
              <>
                <SideHeader
                  accessToken={accessToken}
                  doc={leftDoc}
                  side={item.left}
                  sideName="vế A"
                  sourceFormat={leftSourceFormat}
                />
                <DiffText mode="left" segments={item.diff_segments} />
              </>
            ) : (
              <p className="compare-side-empty">Không có nội dung tương ứng ở vế A.</p>
            )}
          </div>
          <div className="compare-side" data-side="right">
            {item.right ? (
              <>
                <SideHeader
                  accessToken={accessToken}
                  doc={rightDoc}
                  side={item.right}
                  sideName="vế B"
                  sourceFormat={rightSourceFormat}
                />
                <DiffText mode="right" segments={item.diff_segments} />
              </>
            ) : (
              <p className="compare-side-empty">Không có nội dung tương ứng ở vế B.</p>
            )}
          </div>
        </div>
      ) : (
        <div className="compare-inline-body">
          <div className="compare-inline-heads">
            {item.left && (
              <SideHeader
                accessToken={accessToken}
                doc={leftDoc}
                side={item.left}
                sideName="vế A"
                sourceFormat={leftSourceFormat}
              />
            )}
            {item.right && (
              <SideHeader
                accessToken={accessToken}
                doc={rightDoc}
                side={item.right}
                sideName="vế B"
                sourceFormat={rightSourceFormat}
              />
            )}
          </div>
          <DiffText mode="inline" segments={item.diff_segments} />
        </div>
      )}
    </li>
  );
}

export function CompareDiffView({
  items, leftDoc, rightDoc, leftSourceFormat, rightSourceFormat, accessToken, displayMode,
}: CompareDiffViewProps) {
  if (items.length === 0) {
    return <p className="compare-empty">Không có mục so sánh nào để hiển thị.</p>;
  }
  return (
    <ol className="compare-items" data-display={displayMode}>
      {items.map((item) => (
        <ItemCard
          accessToken={accessToken}
          displayMode={displayMode}
          item={item}
          key={item.item_key}
          leftDoc={leftDoc}
          leftSourceFormat={leftSourceFormat}
          rightDoc={rightDoc}
          rightSourceFormat={rightSourceFormat}
        />
      ))}
    </ol>
  );
}