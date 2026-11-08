import { useState } from "react";

import { runSynthesis, type SynthesisResult } from "../api/client";
import { AiAnswerView } from "./AiAnswerView";

interface AiInterpretationProps {
  accessToken?: string;
  resultSetId?: string | null;
  deepAnalysis?: boolean;
}

/**
 * Optional "Diễn giải AI" (G4) for the question just asked.  The server picks only the
 * clauses that answer what is asked, the configured model explains them, and every
 * statement passes the code checks before it is shown.  "Diễn giải tiếp" interprets
 * the next documents only.
 */
export function AiInterpretation({ accessToken, resultSetId, deepAnalysis = false }:
  AiInterpretationProps) {
  const [result, setResult] = useState<SynthesisResult>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  if (!resultSetId || !accessToken) return null;

  async function run(next: boolean) {
    if (!resultSetId || !accessToken) return;
    setBusy(true);
    setError(undefined);
    try {
      setResult(await runSynthesis(accessToken, {
        result_set_id: resultSetId, only_relevant: true, restart: !next,
        ...(deepAnalysis ? { deep_analysis: true } : {}),
      }));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Không diễn giải được lúc này.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ai-interpretation">
      {!result && (
        <button className="secondary-button" disabled={busy} onClick={() => void run(false)}
                type="button">
          {busy ? "Đang diễn giải…" : "Diễn giải AI"}
        </button>
      )}
      {busy && !result && (
        <p className="evidence-meta" role="status">
          Đang chọn điều khoản trả lời đúng câu hỏi và diễn giải; có thể mất đến một phút với
          mô hình chạy trên máy.
        </p>
      )}
      {error && <p className="status-pill status-danger" role="alert">{error}</p>}
      {result?.answer && (
        <AiAnswerView accessToken={accessToken} busy={busy} onContinue={() => void run(true)}
                      result={result} />
      )}
      {result && !result.answer && (
        <p className="evidence-meta">{result.coverage.message}</p>
      )}
    </div>
  );
}
