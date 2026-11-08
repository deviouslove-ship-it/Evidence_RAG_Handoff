import { CHECK_TITLES, codeText, type ModelCheckResult } from "./aiConfig";

const MARK: Record<string, string> = { ok: "Đạt", fail: "Lỗi", warn: "Lưu ý", skip: "Bỏ qua" };

/** Outcome of a connection and usability check, one line per step, with advice on failures. */
export function CheckResult({ result, title }: { result: ModelCheckResult; title?: string }) {
  const verdict = result.usable
    ? "Dùng được"
    : result.checks.some((item) => item.status === "fail") ? "Chưa dùng được" : "Chưa xác nhận";
  return (
    <section aria-label={title ?? "Kết quả kiểm tra"} className="ai-check"
             data-usable={result.usable}>
      <p className="ai-check-verdict">
        <strong>{verdict}</strong>
        {result.usable && result.latency_ms != null && ` · phản hồi ${result.latency_ms} ms`}
        {result.dimensions ? ` · vector ${result.dimensions} chiều` : ""}
      </p>
      <ul className="ai-check-list">
        {result.checks.filter((item) => item.status !== "skip").map((item) => (
          <li data-status={item.status} key={item.id}>
            <span className="ai-check-mark">{MARK[item.status]}</span>
            <span className="ai-check-title">{CHECK_TITLES[item.id] ?? item.id}</span>
            {item.status === "ok" && item.ms != null && (
              <small className="evidence-meta"> {item.ms} ms</small>
            )}
            {item.code && <span className="ai-check-advice">{codeText(item.code)}</span>}
            {item.code === "MODEL_NOT_FOUND" && (result.models?.length ?? 0) > 0 && (
              <span className="ai-check-advice">
                Model dịch vụ đang có: {result.models?.join(", ")}
                {(item.info?.count ?? 0) > (result.models?.length ?? 0) ? ", …" : ""}
              </span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
