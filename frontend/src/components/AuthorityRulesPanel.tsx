import { useCallback, useEffect, useRef, useState } from "react";

import {
  createAuthorityRule,
  listAuthorityRules,
  updateAuthorityRule,
} from "../api/client";
import { DOC_TYPE_LABELS } from "./documentDisplay";
import type { AuthorityRuleView } from "../types";

export interface AuthorityRulesPanelProps {
  accessToken: string;
}

function isAbortError(caught: unknown): boolean {
  return caught instanceof DOMException
    ? caught.name === "AbortError"
    : caught instanceof Error && caught.name === "AbortError";
}

export function AuthorityRulesPanel({ accessToken }: AuthorityRulesPanelProps) {
  const [rules, setRules] = useState<AuthorityRuleView[]>([]);
  const [includeInactive, setIncludeInactive] = useState(true);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string>();
  const [errorMsg, setErrorMsg] = useState<string>();

  // Create rule state
  const [ruleCode, setRuleCode] = useState("");
  const [docType, setDocType] = useState("decree");
  const [issuingPattern, setIssuingPattern] = useState("");
  const [authorityRank, setAuthorityRank] = useState("45");
  const [tierLabel, setTierLabel] = useState("");
  const [matchPriority, setMatchPriority] = useState("100");
  const [ambiguousWithoutIssuer, setAmbiguousWithoutIssuer] = useState(false);
  const [note, setNote] = useState("");
  const [isActive, setIsActive] = useState(true);

  // Edit rule state
  const [editingRule, setEditingRule] = useState<AuthorityRuleView | null>(null);
  const [editPattern, setEditPattern] = useState("");
  const [editRank, setEditRank] = useState("45");
  const [editTierLabel, setEditTierLabel] = useState("");
  const [editPriority, setEditPriority] = useState("100");
  const [editAmbiguous, setEditAmbiguous] = useState(false);
  const [editNote, setEditNote] = useState("");
  const [editActive, setEditActive] = useState(true);

  const controllerRef = useRef<AbortController | null>(null);

  const loadRules = useCallback(async () => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setLoading(true);
    setErrorMsg(undefined);
    try {
      const response = await listAuthorityRules(accessToken, {
        include_inactive: includeInactive,
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      setRules(response.items);
    } catch (caught) {
      if (controller.signal.aborted || isAbortError(caught)) return;
      setErrorMsg(
        caught instanceof Error ? caught.message : "Không tải được danh sách quy tắc thứ bậc.",
      );
    } finally {
      if (controllerRef.current === controller) {
        controllerRef.current = null;
      }
      if (!controller.signal.aborted) {
        setLoading(false);
      }
    }
  }, [accessToken, includeInactive]);

  useEffect(() => {
    void loadRules();
    return () => {
      controllerRef.current?.abort();
      controllerRef.current = null;
    };
  }, [loadRules]);

  async function handleCreateRule(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    const rankNum = Number.parseInt(authorityRank, 10);
    const priorityNum = Number.parseInt(matchPriority, 10);
    if (!Number.isFinite(rankNum) || rankNum < 1 || rankNum > 1000) {
      setErrorMsg("Bậc hiệu lực phải nằm trong khoảng 1–1000.");
      return;
    }
    if (!Number.isFinite(priorityNum) || priorityNum < 0 || priorityNum > 10000) {
      setErrorMsg("Độ ưu tiên khớp mẫu phải nằm trong khoảng 0–10000.");
      return;
    }
    setBusy(true);
    setErrorMsg(undefined);
    setStatusMsg(undefined);
    try {
      const created = await createAuthorityRule(accessToken, {
        rule_code: ruleCode.trim(),
        doc_type: docType,
        issuing_body_pattern: issuingPattern.trim() || null,
        authority_rank: rankNum,
        authority_tier_label: tierLabel.trim(),
        is_ambiguous_without_issuer: ambiguousWithoutIssuer,
        match_priority: priorityNum,
        note: note.trim() || null,
        is_active: isActive,
      });
      setStatusMsg(`Đã thêm quy tắc thứ bậc "${created.rule_code}".`);
      setRuleCode("");
      setIssuingPattern("");
      setAuthorityRank("45");
      setTierLabel("");
      setMatchPriority("100");
      setAmbiguousWithoutIssuer(false);
      setNote("");
      setIsActive(true);
      await loadRules();
    } catch (caught) {
      setErrorMsg(caught instanceof Error ? caught.message : "Không thể tạo quy tắc thứ bậc.");
    } finally {
      setBusy(false);
    }
  }

  function startEdit(rule: AuthorityRuleView) {
    setEditingRule(rule);
    setEditPattern(rule.issuing_body_pattern ?? "");
    setEditRank(String(rule.authority_rank));
    setEditTierLabel(rule.authority_tier_label);
    setEditPriority(String(rule.match_priority));
    setEditAmbiguous(rule.is_ambiguous_without_issuer);
    setEditNote(rule.note ?? "");
    setEditActive(rule.is_active);
    setErrorMsg(undefined);
    setStatusMsg(undefined);
  }

  async function handleUpdateRule(event: React.FormEvent) {
    event.preventDefault();
    if (!editingRule || busy) return;
    const rankNum = Number.parseInt(editRank, 10);
    const priorityNum = Number.parseInt(editPriority, 10);
    if (!Number.isFinite(rankNum) || rankNum < 1 || rankNum > 1000) {
      setErrorMsg("Bậc hiệu lực phải nằm trong khoảng 1–1000.");
      return;
    }
    if (!Number.isFinite(priorityNum) || priorityNum < 0 || priorityNum > 10000) {
      setErrorMsg("Độ ưu tiên khớp mẫu phải nằm trong khoảng 0–10000.");
      return;
    }
    setBusy(true);
    setErrorMsg(undefined);
    setStatusMsg(undefined);
    const trimmedPattern = editPattern.trim();
    const trimmedNote = editNote.trim();
    try {
      const updated = await updateAuthorityRule(accessToken, editingRule.id, {
        authority_rank: rankNum,
        authority_tier_label: editTierLabel.trim(),
        issuing_body_pattern: trimmedPattern || null,
        clear_pattern: trimmedPattern.length === 0,
        is_ambiguous_without_issuer: editAmbiguous,
        match_priority: priorityNum,
        note: trimmedNote || null,
        is_active: editActive,
      });
      setStatusMsg(`Đã cập nhật quy tắc "${updated.rule_code}".`);
      setEditingRule(null);
      await loadRules();
    } catch (caught) {
      setErrorMsg(caught instanceof Error ? caught.message : "Không thể cập nhật quy tắc thứ bậc.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="admin-grid conflict-authority-panel" aria-label="Quản lý thứ bậc văn bản">
      <section className="admin-card" aria-label="Thêm quy tắc thứ bậc văn bản">
        <h2>Thêm quy tắc thứ bậc hiệu lực</h2>
        <p className="admin-hint">
          Số bậc nhỏ hơn biểu thị thẩm quyền cao hơn (VD: Hiến pháp/Luật 10–20, Nghị định 30, Thông tư
          40). Hệ thống dùng mẫu regex cơ quan ban hành để phân biệt văn bản VBQPPL và văn bản nội bộ.
        </p>

        {statusMsg && (
          <p className="status-pill status-success" role="status">
            {statusMsg}
          </p>
        )}
        {errorMsg && (
          <p className="status-pill status-danger" role="alert">
            {errorMsg}
          </p>
        )}

        <form className="form-stack" onSubmit={(event) => void handleCreateRule(event)}>
          <div className="compact-form-grid">
            <label className="field-label">
              Mã quy tắc
              <input
                disabled={busy}
                onChange={(event) => setRuleCode(event.target.value)}
                placeholder="decision_internal_board"
                required
                type="text"
                value={ruleCode}
              />
            </label>
            <label className="field-label">
              Loại văn bản
              <select
                disabled={busy}
                onChange={(event) => setDocType(event.target.value)}
                required
                value={docType}
              >
                {Object.entries(DOC_TYPE_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <label className="field-label">
            Mẫu cơ quan ban hành (regex, tùy chọn)
            <input
              disabled={busy}
              onChange={(event) => setIssuingPattern(event.target.value)}
              placeholder="hoi dong quan tri|tong giam doc"
              type="text"
              value={issuingPattern}
            />
          </label>

          <div className="compact-form-grid">
            <label className="field-label">
              Bậc hiệu lực (1–1000)
              <input
                disabled={busy}
                max={1000}
                min={1}
                onChange={(event) => setAuthorityRank(event.target.value)}
                required
                type="number"
                value={authorityRank}
              />
            </label>
            <label className="field-label">
              Độ ưu tiên khớp mẫu (0–10000)
              <input
                disabled={busy}
                max={10000}
                min={0}
                onChange={(event) => setMatchPriority(event.target.value)}
                required
                type="number"
                value={matchPriority}
              />
            </label>
          </div>

          <label className="field-label">
            Nhãn bậc hiệu lực hiển thị
            <input
              disabled={busy}
              onChange={(event) => setTierLabel(event.target.value)}
              placeholder="Quyết định Hội đồng quản trị"
              required
              type="text"
              value={tierLabel}
            />
          </label>

          <label className="field-label">
            Ghi chú
            <input
              disabled={busy}
              onChange={(event) => setNote(event.target.value)}
              placeholder="Mô tả phạm vi áp dụng..."
              type="text"
              value={note}
            />
          </label>

          <label className="checkbox-row">
            <input
              checked={ambiguousWithoutIssuer}
              disabled={busy}
              onChange={(event) => setAmbiguousWithoutIssuer(event.target.checked)}
              type="checkbox"
            />
            <span>Đánh dấu mơ hồ nếu văn bản thiếu cơ quan ban hành</span>
          </label>

          <label className="checkbox-row">
            <input
              checked={isActive}
              disabled={busy}
              onChange={(event) => setIsActive(event.target.checked)}
              type="checkbox"
            />
            <span>Kích hoạt quy tắc ngay</span>
          </label>

          <div className="form-actions">
            <button className="primary-button" disabled={busy} type="submit">
              Thêm quy tắc
            </button>
          </div>
        </form>
      </section>

      <section className="admin-card" aria-label="Danh sách quy tắc thứ bậc">
        <div className="compact-card-header">
          <div>
            <h2>Quy tắc thứ bậc hiện có ({rules.length})</h2>
            <p className="evidence-meta">
              Thứ tự ưu tiên khớp: mẫu cơ quan ban hành cụ thể, sau đó đến độ ưu tiên thấp hơn.
            </p>
          </div>
          <label className="checkbox-row">
            <input
              checked={includeInactive}
              onChange={(event) => setIncludeInactive(event.target.checked)}
              type="checkbox"
            />
            <span>Hiển thị cả quy tắc đã tắt</span>
          </label>
        </div>

        {editingRule && (
          <form
            aria-label={`Chỉnh sửa quy tắc ${editingRule.rule_code}`}
            className="conflict-edit-rule form-stack"
            onSubmit={(event) => void handleUpdateRule(event)}
          >
            <h3>Chỉnh sửa: {editingRule.rule_code}</h3>
            <div className="compact-form-grid">
              <label className="field-label">
                Sửa bậc hiệu lực (1–1000)
                <input
                  disabled={busy}
                  max={1000}
                  min={1}
                  onChange={(event) => setEditRank(event.target.value)}
                  required
                  type="number"
                  value={editRank}
                />
              </label>
              <label className="field-label">
                Sửa độ ưu tiên khớp (0–10000)
                <input
                  disabled={busy}
                  max={10000}
                  min={0}
                  onChange={(event) => setEditPriority(event.target.value)}
                  required
                  type="number"
                  value={editPriority}
                />
              </label>
            </div>
            <label className="field-label">
              Sửa nhãn bậc hiệu lực
              <input
                disabled={busy}
                onChange={(event) => setEditTierLabel(event.target.value)}
                required
                type="text"
                value={editTierLabel}
              />
            </label>
            <label className="field-label">
              Sửa mẫu cơ quan ban hành (để trống để xóa mẫu)
              <input
                disabled={busy}
                onChange={(event) => setEditPattern(event.target.value)}
                type="text"
                value={editPattern}
              />
            </label>
            <label className="field-label">
              Sửa ghi chú
              <input
                disabled={busy}
                onChange={(event) => setEditNote(event.target.value)}
                type="text"
                value={editNote}
              />
            </label>
            <label className="checkbox-row">
              <input
                checked={editAmbiguous}
                disabled={busy}
                onChange={(event) => setEditAmbiguous(event.target.checked)}
                type="checkbox"
              />
              <span>Mơ hồ nếu thiếu cơ quan ban hành</span>
            </label>
            <label className="checkbox-row">
              <input
                checked={editActive}
                disabled={busy}
                onChange={(event) => setEditActive(event.target.checked)}
                type="checkbox"
              />
              <span>Đang kích hoạt</span>
            </label>
            <div className="form-actions">
              <button className="primary-button" disabled={busy} type="submit">
                Lưu thay đổi
              </button>
              <button
                className="secondary-button"
                disabled={busy}
                onClick={() => setEditingRule(null)}
                type="button"
              >
                Hủy chỉnh sửa
              </button>
            </div>
          </form>
        )}

        {loading ? (
          <p className="evidence-meta">Đang tải quy tắc thứ bậc…</p>
        ) : rules.length === 0 ? (
          <p className="evidence-meta">Chưa có quy tắc thứ bậc nào.</p>
        ) : (
          <div className="admin-list">
            {rules.map((rule) => (
              <div className="compact-admin-item" key={rule.id}>
                <div className="compact-admin-main">
                  <div className="compact-admin-title">
                    <strong>{rule.authority_tier_label}</strong>
                    <span className="compact-badge">{rule.rule_code}</span>
                    <span className="compact-badge">Bậc {rule.authority_rank}</span>
                    <span className={rule.is_active ? "compact-badge local" : "compact-badge api"}>
                      {rule.is_active ? "Đang bật" : "Đã tắt"}
                    </span>
                  </div>
                  <div className="compact-admin-sub">
                    Loại: <strong>{DOC_TYPE_LABELS[rule.doc_type] ?? rule.doc_type}</strong>
                    {rule.issuing_body_pattern ? (
                      <>
                        {" · "}Mẫu cơ quan: <code>{rule.issuing_body_pattern}</code>
                      </>
                    ) : (
                      " · Quy tắc mặc định theo loại văn bản"
                    )}
                    {" · "}Ưu tiên: {rule.match_priority}
                    {rule.is_ambiguous_without_issuer ? " · Cần rõ cơ quan ban hành" : ""}
                  </div>
                  {rule.note && <div className="compact-admin-sub">{rule.note}</div>}
                </div>
                <div className="form-actions">
                  <button
                    className="secondary-button"
                    disabled={busy}
                    onClick={() => startEdit(rule)}
                    type="button"
                  >
                    Sửa
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
