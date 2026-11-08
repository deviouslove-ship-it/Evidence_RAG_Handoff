import { useState } from "react";

import { runSynthesis, type SynthesisPoint, type SynthesisResult } from "../api/client";
import { AiAnswerView } from "./AiAnswerView";
import { EffectivityBadges } from "./EffectivityBadges";

/**
 * G4: three separate layers — Nguyên văn (database), Diễn giải (AI, each point cites
 * evidence and passed the code checks), Gợi ý tham khảo (what to read next).  The
 * panel never states a business conclusion; it reports "N trong M căn cứ".
 */
export function SynthesisPanel({ accessToken, resultSetId, onlyRelevant = false }: {
  accessToken: string; resultSetId: string;
  /** Summarise only clauses relevant to the query (not the partial matches). */
  onlyRelevant?: boolean;
}) {
  const [result, setResult] = useState<SynthesisResult>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();

  async function run(options: { restart?: boolean; deep_analysis?: boolean; expand?: boolean }) {
    setBusy(true);
    setError(undefined);
    try {
      setResult(await runSynthesis(accessToken, {
        result_set_id: resultSetId, ...options, ...(onlyRelevant ? { only_relevant: true } : {}),
      }));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Không tổng hợp được.");
    } finally {
      setBusy(false);
    }
  }

  const points = (items: SynthesisPoint[]) => (
    <ul>
      {items.map((point, index) => (
        <li key={index}>
          {point.text}{" "}
          <small>
            [{point.evidence_ids.map((id) => id.slice(3, 11)).join(", ")}]
            {point.status === "unverified" ? " · chưa kiểm chứng" : " · đã kiểm bằng mã"}
          </small>
        </li>
      ))}
    </ul>
  );

  return (
    <section className="synthesis-panel admin-card" aria-label="Tổng hợp căn cứ">
      <h2>{onlyRelevant ? "Diễn giải AI theo nội dung tìm kiếm" : "Tổng hợp theo nhóm nội dung (AI)"}</h2>
      <div className="pager">
        <button className="primary-button" disabled={busy}
                onClick={() => void run({ restart: true })} type="button">
          {onlyRelevant ? "Diễn giải AI" : "Tổng hợp"}
        </button>
        <button className="secondary-button" disabled={busy}
                onClick={() => void run({ restart: true, deep_analysis: true })} type="button">
          Phân tích sâu
        </button>
        {result?.can_continue && (
          <>
            <button className="secondary-button" disabled={busy} onClick={() => void run({})}
                    type="button">
              {onlyRelevant ? "Diễn giải tiếp" : "Tổng hợp tiếp"}
            </button>
            <button className="secondary-button" disabled={busy}
                    onClick={() => void run({ expand: true })} type="button">
              Mở rộng phạm vi tổng hợp
            </button>
          </>
        )}
      </div>
      {busy && <p role="status">Đang tổng hợp…</p>}
      {error && <p className="status-pill status-danger" role="alert">{error}</p>}
      {result?.answer && (
        <AiAnswerView accessToken={accessToken} anchorPrefix="search-ai-" busy={busy}
                      result={result} />
      )}
      {result && !result.answer && (
        <>
          <p className="status-pill status-warning" role="status">{result.coverage.message}</p>
          {result.external_ai_used && <p role="note">Đã dùng API ngoài cho lượt này.</p>}
          {result.ai_limited && (
            <p role="note">Đã chạm trần chi phí; phần diễn giải dừng, nguyên văn vẫn đủ.</p>
          )}
          <div className="synthesis-layer" data-layer="interpretation">
            <h3>Diễn giải (AI, mỗi ý gắn căn cứ)</h3>
            {result.layers.interpretation.length > 0
              ? points(result.layers.interpretation)
              : <p>Chưa có diễn giải qua kiểm tra; xem nguyên văn bên dưới.</p>}
          </div>
          {result.layers.suggestions.length > 0 && (
            <div className="synthesis-layer" data-layer="suggestion">
              <h3>Gợi ý tham khảo (không phải khẳng định)</h3>
              {points(result.layers.suggestions)}
            </div>
          )}
          <div className="synthesis-layer" data-layer="verbatim">
            <h3>Nguyên văn</h3>
            {result.layers.verbatim.map((group) => (
              <details key={group.group} open={result.layers.verbatim.length <= 3}>
                <summary>{group.group} ({group.evidence.length})</summary>
                <ul>
                  {group.evidence.map((item) => (
                    <li key={item.evidence_id}>
                      <strong>{item.document_number ?? item.title}</strong> · {item.label}
                      {item.page ? ` · Trang ${item.page}` : ""}{" "}
                      <EffectivityBadges view={item.effectivity} compact />
                      <blockquote className="quote">
                        {item.quote_exact.length > 600
                          ? `${item.quote_exact.slice(0, 600).trimEnd()} …`
                          : item.quote_exact}
                      </blockquote>
                    </li>
                  ))}
                </ul>
              </details>
            ))}
          </div>
          <p className="admin-hint">{result.disclaimer}</p>
        </>
      )}
    </section>
  );
}
