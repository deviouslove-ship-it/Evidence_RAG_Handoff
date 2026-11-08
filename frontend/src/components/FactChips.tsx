interface Fact {
  key: string;
  value: string;
  status: "user_confirmed" | "extracted_unconfirmed" | "inferred_uncertain";
  dirty?: boolean;
}

interface FactChipsProps {
  facts: Fact[];
  onChange?: (next: Fact[]) => void;
}

const labels = {
  user_confirmed: "Đã xác nhận",
  extracted_unconfirmed: "Đã trích xuất",
  inferred_uncertain: "Cần xác nhận",
};

export function FactChips({ facts, onChange }: FactChipsProps) {
  function update(index: number, value: string) {
    if (!onChange) return;
    const next = facts.map((fact, factIndex) =>
      factIndex === index ? { ...fact, value, dirty: true } : fact,
    );
    onChange(next);
  }

  function confirm(index: number) {
    if (!onChange) return;
    const next = facts.map((fact, factIndex) =>
      factIndex === index ? { ...fact, status: "user_confirmed" as const, dirty: true } : fact,
    );
    onChange(next);
  }

  function remove(index: number) {
    if (!onChange) return;
    onChange(facts.filter((_, factIndex) => factIndex !== index));
  }

  return (
    <div className="fact-chips" aria-label="Dữ kiện dùng để tra cứu">
      {facts.map((fact, index) => (
        <label className="fact-chip" data-dirty={fact.dirty ? "true" : "false"} key={fact.key}>
          <span>{fact.key}:</span>
          <input
            aria-label={`Sửa ${fact.key}`}
            readOnly={!onChange}
            onChange={(event) => update(index, event.target.value)}
            value={fact.value}
          />
          <span>{labels[fact.status]}</span>
          {onChange && fact.status !== "user_confirmed" && (
            <button
                aria-label={`Xác nhận ${fact.key}`}
              className="fact-chip-confirm"
              onClick={(event) => {
                event.preventDefault();
                confirm(index);
              }}
              title="Xác nhận dữ kiện này trước lượt tra cứu tiếp theo"
              type="button"
            >
              Xác nhận
            </button>
          )}
          {onChange && (
            <button
              aria-label={`Xóa dữ kiện ${fact.key}`}
              className="fact-chip-remove"
              onClick={(event) => {
                event.preventDefault();
                remove(index);
              }}
              title="Xóa dữ kiện tạm khỏi lượt tra cứu"
              type="button"
            >
              ×
            </button>
          )}
        </label>
      ))}
    </div>
  );
}
