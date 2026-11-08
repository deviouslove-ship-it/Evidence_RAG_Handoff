import { useCallback, useEffect, useState } from "react";

import { listLabelProposals, reviewLabels, type LabelProposal } from "../api/client";

/** G4: AI-proposed content groups, reviewed in batches by a REVIEWER with can_review. */
export function LabelReviewPanel({ accessToken }: { accessToken: string }) {
  const [items, setItems] = useState<LabelProposal[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [message, setMessage] = useState<string>();

  const load = useCallback(async () => {
    try {
      setItems(await listLabelProposals(accessToken));
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Không tải được nhãn đề xuất.");
    }
  }, [accessToken]);

  useEffect(() => {
    void load();
  }, [load]);

  const key = (item: LabelProposal) => `${item.node_id}|${item.code}`;

  async function decide(decision: "approve" | "reject") {
    const chosen = items.filter((item) => selected.has(key(item)));
    if (!chosen.length) return;
    try {
      const result = await reviewLabels(accessToken, {
        decision, items: chosen.map((item) => ({ node_id: item.node_id, taxonomy_code: item.code })),
      });
      setMessage(`Đã ${decision === "approve" ? "duyệt" : "từ chối"} ${result.updated} nhãn.`);
      setSelected(new Set());
      await load();
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Không lưu được.");
    }
  }

  return (
    <section className="admin-panel" aria-label="Rà soát nhóm nội dung">
      <h2>Nhóm nội dung do AI đề xuất ({items.length})</h2>
      <p className="admin-hint">
        Nhãn theo quy tắc cụm từ được gán ngay; nhãn AI chỉ là đề xuất. Khoản chưa có nhóm
        vẫn hiện trong tìm kiếm và tổng hợp.
      </p>
      {message && <p role="status">{message}</p>}
      <div className="effectivity-review-actions">
        <button className="secondary-button" onClick={() =>
          setSelected(new Set(items.map(key)))} type="button">Chọn tất cả</button>
        <button className="primary-button" onClick={() => void decide("approve")} type="button">
          Duyệt đã chọn
        </button>
        <button className="secondary-button" onClick={() => void decide("reject")} type="button">
          Từ chối đã chọn
        </button>
      </div>
      <ul>
        {items.map((item) => (
          <li key={key(item)}>
            <label>
              <input
                checked={selected.has(key(item))}
                onChange={() => setSelected((current) => {
                  const next = new Set(current);
                  if (next.has(key(item))) next.delete(key(item));
                  else next.add(key(item));
                  return next;
                })}
                type="checkbox"
              />
              <strong>{item.name}</strong> — {item.document_number} · {item.label}
            </label>
            <blockquote className="quote">“{item.text}”</blockquote>
          </li>
        ))}
      </ul>
    </section>
  );
}
