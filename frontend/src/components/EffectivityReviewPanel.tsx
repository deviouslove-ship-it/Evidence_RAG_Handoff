import { useCallback, useEffect, useState } from "react";

import {
  createEffectivityAttestation,
  listEffectivityProposals,
  reviewEffectivityProposals,
  type EffectivityProposal,
  type EffectivityProposalGroup,
} from "../api/client";
import { STATUS_LABELS } from "./effectivityLabels";

const ACTION_LABELS: Record<string, string> = {
  modify: "Sửa đổi, bổ sung",
  add: "Bổ sung",
  replace: "Thay thế",
  repeal: "Bãi bỏ toàn bộ",
  repeal_partial: "Bãi bỏ một phần",
  suspend: "Ngưng hiệu lực",
  commence: "Ngày hiệu lực riêng",
};
const PROPOSER_LABELS: Record<string, string> = {
  rule: "Quy tắc",
  ai: "AI đề xuất",
  person: "Cán bộ đề xuất",
};
const MATCH_LABELS: Record<string, string> = {
  resolved: "Đã khớp",
  unresolved: "Chưa có trong kho",
  ambiguous: "Khớp mơ hồ — cần chọn",
};

function formatDate(value?: string | null): string {
  if (!value) return "—";
  const [year, month, day] = value.slice(0, 10).split("-");
  return `${day}/${month}/${year}`;
}

function today(): string {
  const now = new Date();
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/**
 * G1 review queue: rule/AI proposals grouped by the amending document.  A REVIEWER
 * with can_review approves or rejects a whole batch; every relation keeps its own
 * audit record.  AI never approves.
 */
export function EffectivityReviewPanel({ accessToken }: { accessToken: string }) {
  const [groups, setGroups] = useState<EffectivityProposalGroup[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [dates, setDates] = useState<Record<string, string>>({});
  const [note, setNote] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [attestDoc, setAttestDoc] = useState("");
  const [attestResult, setAttestResult] = useState("active");
  const [attestFrom, setAttestFrom] = useState("");
  const [attestTo, setAttestTo] = useState(today());
  const [attestSource, setAttestSource] = useState("");

  const load = useCallback(async () => {
    try {
      const data = await listEffectivityProposals(accessToken);
      setGroups(data.groups);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Không tải được hàng đợi.");
    }
  }, [accessToken]);

  useEffect(() => {
    void load();
  }, [load]);

  const toggle = (proposal: EffectivityProposal) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(proposal.id)) next.delete(proposal.id);
      else next.add(proposal.id);
      return next;
    });
  };

  const selectGroup = (group: EffectivityProposalGroup) => {
    setSelected((current) => {
      const next = new Set(current);
      group.proposals
        .filter((item) => item.resolution_state === "resolved")
        .forEach((item) => next.add(item.id));
      return next;
    });
  };

  const submit = async (decision: "approve" | "reject") => {
    if (selected.size === 0 || !note.trim()) {
      setMessage("Chọn ít nhất một quan hệ và nhập ghi chú căn cứ duyệt.");
      return;
    }
    setBusy(true);
    try {
      const result = await reviewEffectivityProposals(accessToken, {
        note: note.trim(),
        decisions: [...selected].map((id) => ({
          relation_id: id,
          decision,
          ...(dates[id] ? { valid_from: dates[id] } : {}),
        })),
      });
      setMessage(
        `Đã ${decision === "approve" ? "duyệt" : "từ chối"} ${result.results.length} quan hệ` +
          ` (mã lô ${result.batch_id.slice(0, 8)}).`,
      );
      setSelected(new Set());
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Không lưu được quyết định.");
    } finally {
      setBusy(false);
    }
  };

  const attest = async () => {
    if (!attestDoc.trim() || !attestFrom || !attestTo || !attestSource.trim()) {
      setMessage("Bản xác nhận cần mã văn bản, khoảng thời gian và nguồn đối chiếu.");
      return;
    }
    setBusy(true);
    try {
      await createEffectivityAttestation(accessToken, {
        document_id: attestDoc.trim(), result: attestResult, valid_for_from: attestFrom,
        valid_for_to: attestTo, source_note: attestSource.trim(),
      });
      setMessage("Đã lưu bản xác nhận hiệu lực.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Không lưu được bản xác nhận.");
    } finally {
      setBusy(false);
    }
  };

  const total = groups.reduce((sum, group) => sum + group.proposals.length, 0);
  return (
    <section className="admin-panel effectivity-review" aria-label="Duyệt quan hệ hiệu lực">
      <h2>Quan hệ hiệu lực chờ duyệt ({total})</h2>
      <p className="admin-hint">
        Quy tắc và AI chỉ đề xuất. Quan hệ chỉ làm đổi trạng thái hiệu lực sau khi cán bộ
        được giao quyền duyệt danh mục xác nhận.
      </p>
      {message && <p className="status-pill status-warning" role="status">{message}</p>}
      <div className="effectivity-review-actions">
        <label>
          Ghi chú căn cứ duyệt
          <input value={note} onChange={(event) => setNote(event.target.value)} />
        </label>
        <button className="primary-button" disabled={busy} onClick={() => void submit("approve")}
                type="button">
          Duyệt {selected.size} quan hệ đã chọn
        </button>
        <button className="secondary-button" disabled={busy}
                onClick={() => void submit("reject")} type="button">
          Từ chối
        </button>
      </div>
      {groups.map((group) => (
        <article className="effectivity-group" key={group.source_document_id}>
          <header>
            <h3>{group.source_number ?? group.source_title}</h3>
            <span>{group.source_title}</span>
            <button className="secondary-button" onClick={() => selectGroup(group)} type="button">
              Chọn các quan hệ đã khớp
            </button>
          </header>
          <table className="admin-table">
            <thead>
              <tr>
                <th scope="col">Chọn</th>
                <th scope="col">Hành động</th>
                <th scope="col">Văn bản đích</th>
                <th scope="col">Ngày áp dụng</th>
                <th scope="col">Câu gốc</th>
                <th scope="col">Nguồn đề xuất</th>
              </tr>
            </thead>
            <tbody>
              {group.proposals.map((item) => (
                <tr key={item.id}>
                  <td>
                    <input
                      aria-label={`Chọn ${item.target_number ?? item.target_path ?? item.id}`}
                      checked={selected.has(item.id)}
                      disabled={item.resolution_state !== "resolved"}
                      onChange={() => toggle(item)}
                      type="checkbox"
                    />
                  </td>
                  <td>{ACTION_LABELS[item.action] ?? item.action}</td>
                  <td>
                    {item.target_document_number ?? item.target_number ?? "—"}
                    {item.target_label ? ` · ${item.target_label}` : ""}
                    {item.target_path && !item.target_label ? ` · ${item.target_path}` : ""}
                    <br />
                    <small>{MATCH_LABELS[item.resolution_state]}</small>
                  </td>
                  <td>
                    <input
                      aria-label="Ngày áp dụng"
                      type="date"
                      value={dates[item.id] ?? item.valid_from ?? ""}
                      onChange={(event) =>
                        setDates((current) => ({ ...current, [item.id]: event.target.value }))
                      }
                    />
                    <br />
                    <small>{formatDate(item.valid_from)}</small>
                  </td>
                  <td>
                    <small>
                      {item.source_label ? `${item.source_label} · ` : ""}
                      Trang {item.source_page ?? "—"}
                    </small>
                    <blockquote className="quote">“{item.source_quote}”</blockquote>
                    {item.condition_text && (
                      <small>Có điều kiện: không tự tính hiệu lực.</small>
                    )}
                  </td>
                  <td>
                    {PROPOSER_LABELS[item.proposed_by] ?? item.proposed_by}
                    {item.confidence != null ? ` · ${Math.round(item.confidence * 100)}%` : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </article>
      ))}
      <h2>Bản xác nhận hiệu lực của cán bộ</h2>
      <p className="admin-hint">
        "Còn hiệu lực, đã xác minh" chỉ có từ bản xác nhận này, kèm nguồn đối chiếu và chỉ
        khẳng định đến ngày xác minh.
      </p>
      <div className="effectivity-attest-form">
        <label>
          Mã văn bản
          <input value={attestDoc} onChange={(event) => setAttestDoc(event.target.value)} />
        </label>
        <label>
          Kết quả
          <select value={attestResult} onChange={(event) => setAttestResult(event.target.value)}>
            {Object.entries(STATUS_LABELS)
              .filter(([key]) => key !== "unknown")
              .map(([key, label]) => (
                <option key={key} value={key}>{label}</option>
              ))}
          </select>
        </label>
        <label>
          Từ ngày
          <input type="date" value={attestFrom}
                 onChange={(event) => setAttestFrom(event.target.value)} />
        </label>
        <label>
          Đến ngày
          <input type="date" value={attestTo} onChange={(event) => setAttestTo(event.target.value)} />
        </label>
        <label>
          Nguồn đối chiếu
          <input value={attestSource} onChange={(event) => setAttestSource(event.target.value)} />
        </label>
        <button className="primary-button" disabled={busy} onClick={() => void attest()}
                type="button">
          Lưu bản xác nhận
        </button>
      </div>
    </section>
  );
}
