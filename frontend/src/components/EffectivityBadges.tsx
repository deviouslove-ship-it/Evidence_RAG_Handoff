import type { AmendmentState, EffectivityView } from "../types";
import { STATUS_LABELS, VERIFICATION_LABELS } from "./effectivityLabels";

function formatDate(value?: string | null): string {
  if (!value) return "";
  const day = value.slice(0, 10).split("-");
  return day.length === 3 ? `${day[2]}/${day[1]}/${day[0]}` : value;
}

interface EffectivityBadgesProps {
  view?: EffectivityView | null;
  /** Fallback when the server sent only axis A (older payloads). */
  status?: AmendmentState | null;
  compact?: boolean;
}

export function EffectivityBadges({ view, status, compact = false }: EffectivityBadgesProps) {
  const axisA = view?.status ?? status ?? "unknown";
  const axisB = view?.verification ?? "not_found";
  const verifiedBy =
    axisB === "verified" && view?.verified_by
      ? ` · ${view.verified_by}${view.verified_at ? `, ${formatDate(view.verified_at)}` : ""}`
      : "";
  return (
    <span className="effectivity-badges">
      <span className="tag effectivity-tag" data-state={axisA}>
        {STATUS_LABELS[axisA] ?? STATUS_LABELS.unknown}
        {view?.as_of_date ? ` (tại ${formatDate(view.as_of_date)})` : ""}
      </span>
      <span className="tag verification-tag" data-verification={axisB}>
        {VERIFICATION_LABELS[axisB]}
        {verifiedBy}
      </span>
      {view && view.pending_proposals > 0 && (
        <span className="tag verification-tag" data-verification="pending">
          Có đề xuất chưa xác nhận
        </span>
      )}
      {!compact && view && (view.notes.length > 0 || view.data_date) && (
        <details className="effectivity-notes">
          <summary>Căn cứ hiệu lực</summary>
          <ul>
            {view.notes.map((note, index) => (
              <li key={index}>{note}</li>
            ))}
            {view.data_date && <li>Kho dữ liệu đến ngày {formatDate(view.data_date)}.</li>}
          </ul>
        </details>
      )}
    </span>
  );
}
