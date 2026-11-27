**Language / Ngôn ngữ:** [Tiếng Việt](eval-gold-protocol.md) · English

English counterpart of `docs/history/eval-gold-protocol.md`. The Vietnamese file is the original.

> **Not implemented — see [ADR-010](../architecture-decisions/ADR-010-khong-trien-khai-bo-cau-hoi-gold.md).** This protocol is kept for historical lookup. It does not apply.

> **Kh么ng tri峄僴 khai 鈥?xem [ADR-010](../architecture-decisions/ADR-010-khong-trien-khai-bo-cau-hoi-gold.md).** Giao th峄ヽ n脿y 膽瓢峄 gi峄?膽峄?tra c峄﹗ l峄媍h s峄? kh么ng 谩p d峄g.

# Gold evaluation protocol

## Corpus

- Use only real public PDFs from official sources.
- Each corpus stores the URL, publisher, license, hash, and captured timestamp.
- UI fixtures are kept separate and labeled **FICTIONAL (HƯ CẤU)**.

## Review and split

- Each case has a question, a reference answer, evidence, a source hash, `scenario_group_id`, and a review status.
- Only cases `approved` by the person who holds the business domain are used as the standard.
- Paraphrases, or cases about the same situation, must share one `scenario_group_id` and must not be split between calibration and held-out.
- `split_revision` is locked before the candidate is tuned.

## Report

Report the candidate, the config/model/tokenizer revision, the corpus/split hash, the case count, the environment, recall/precision, `wrong_doc_rate`, `wrong_node_rate`, abstention, missed exception, and the confidence interval. Do not tune on held-out and then report the result again as an independent evaluation.

Gold v0 has not been created and there is no reviewer yet. Gates S1/S2/S3 are still open.

## Search v1 — definition of exact_phrase_precision (locked by the owner on 2026-10-31)

- Numerator = the number of clauses the backend labeled `match_type="exact_phrase"` whose `quote_exact` **self-verifies** (NFC + lowercase + punctuation turned into separators, consecutive words) that the quote actually contains the phrase. Do not trust the backend label. Do not use `expected_documents`/`expected_nodes` to compute the numerator.
- Denominator = the total number of clauses labeled `exact_phrase` in `results[:k]`.
- A negative case (`expected_no_result`) must be **0.0**, even when the denominator is greater than 0 or the quote happens to contain the phrase.
- A positive case with a denominator of 0 → **null** (excluded from the average), not 1.0.
- The phrase used for comparison prefers `response.query.phrase`, and falls back to the case's question.
- Do not claim “correct/sufficient” when there is no Gold approved by the person who holds the business domain.
