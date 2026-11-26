**Language / Ngôn ngữ:** [Tiếng Việt](README.md) · English

English counterpart of `evaluation/search_eval/README.md`. The Vietnamese file is the original.

# Search v1 evaluation — FICTIONAL (HƯ CẤU) case set and metrics harness

> ⚠️ **FICTIONAL (HƯ CẤU) & [Gold not implemented — see ADR-010]** — Every case in this directory uses **fictional administrative-document (văn bản) numbers/identifiers, nodes, and content** (`HU-CAU/2026/ND-CP`, `HC-ND-CP-N01`, …). They are **not legal administrative documents (văn bản pháp luật)** and they are **not Gold**. Per [ADR-010](../../docs/architecture-decisions/ADR-010-khong-trien-khai-bo-cau-hoi-gold.md), the project does not implement the Gold question set. Every case that exists has `approved_by = null`, so `evaluate_search.py` reports only `hucau_metrics` and writes `quality_status = "not_evaluated"`. Do not use figures in the report to claim search quality.

## Purpose

Prepare the infrastructure that measures the metrics in **section 9-B** of [`docs/KE_HOACH_TRIEN_KHAI_TIM_KIEM_V1_Evidence_RAG.md`](../../docs/KE_HOACH_TRIEN_KHAI_TIM_KIEM_V1_Evidence_RAG.md) for the endpoint `GET /api/v1/search`:

- recall@k (administrative-document (văn bản) level), precision@k (Clause (Khoản) level), `exact_phrase_precision`, `wrong_doc_rate`, `wrong_node_rate`, correct-when-there-is-no-result, and p50/p95 latency.
- Check the formulas and metrics on a simulated response, so CI does not depend on the backend.
- Be ready to accept real Gold: only a case with `approved_by != null` is counted in `official_metrics`.

Data context (section 10 of the plan): there are currently **0 approved administrative documents (văn bản)**, and 0 Gold cases approved by the person who holds the business domain. This set does **not yet** measure real quality. It only proves that the harness and the metrics run correctly.

## Components

| File | Role |
|---|---|
| `queries_hucau.json` | 12 FICTIONAL (HƯ CẤU) cases: an exact phrase present or absent, keywords that include every word, typing without diacritics, the spelling variants kì/kỳ and hòa/hoà, administrative-document (văn bản) numbers, negative cases (`expected_no_result`), multiple administrative documents, and filters. |
| `schema.json` | JSON Schema (draft 2020-12) for the queries file. |
| `fixtures/sample_responses.json` | Simulated responses plus the expected metric values for `--self-test` and `self_test.py`. Not a real API response. |
| `self_test.py` | 21 stdlib `unittest` tests: metric formulas, schema/queries, percentile, URL, an end-to-end mock HTTP server, and exit codes. |
| `reports/` | Where `evaluate_search.py` writes `report.json` and `report.md` by default (generated files; they may be deleted and created again). |
| `../scripts/evaluate_search.py` | The harness that calls the API, measures latency, computes the metrics, and exports the report. |

## Case schema

The queries file is a JSON object: `schema_version = 1`, `label = "HU_CAU"`, `description`, `corpus = "HU_CAU"`, `cases[]`. Each case:

| Field | Type | Meaning |
|---|---|---|
| `id` | string, unique | Case id, used in the report. |
| `query` | string | The query sent to the API. |
| `mode` | `auto` \| `phrase` \| `keywords` | The `mode` parameter. |
| `filters` | object | `category_id` (array of strings), `doc_type`, `issuing_body`, `as_of_date` (YYYY-MM-DD), `only_active` (bool), `group_by` (`document`). Leave it empty when not filtering. |
| `expected_documents` | string[] | Expected administrative-document (văn bản) numbers (they match `document_number` returned by the API). Empty ⇔ `expected_no_result = true`. |
| `expected_nodes` | string[] | Expected nodes. **`node_id` or a label** (`label`) is accepted, because real Gold may not yet have a UUID. |
| `expected_no_result` | bool | `true` when the API is expected to return no results. |
| `notes` | string | Notes for the case. |
| `approved_by` | string \| null | `null` = not yet approved by the person who holds the business domain → goes **only** into `hucau_metrics`. |
| `corpus` | string | `"HU_CAU"` for the fictional fixture. |

`validate_queries()` in the harness checks, at minimum: required fields, `mode`, the `filters` keys, the date format, that `expected_no_result` is consistent with `expected_documents`, that `id` is not duplicated, that `approved_by` is null or non-empty, and that `corpus = HU_CAU`. `self_test.py` also cross-checks the required-field list between `schema.json` and the code.

## Metric formulas

With `k` = `--k` (default 10), the first k administrative documents (văn bản) in `results`:

- **recall@k (document)** = `|expected_documents ∩ returned_documents[:k]| / |expected_documents|`. A negative case (no expected administrative document) has no recall → `null`, and is excluded from the average.
- **precision@k (clause)** = the number of clauses that belong to `expected_documents` **or** `expected_nodes`, divided by the total number of clauses returned in `results[:k]`. If there are no clauses → `null`.
- **exact_phrase_precision** (the definition locked by the owner — self-verifying; do not trust the label):
  - Numerator = the number of clauses the backend labeled `match_type = "exact_phrase"` whose `quote_exact` **actually contains the phrase** after NFC normalization, lowercasing, treating every character that is not a letter or digit as a separator, and matching consecutive words.
  - Denominator = the total number of clauses labeled `exact_phrase` in `results[:k]` (the same scope as the other clause metrics).
  - The phrase used for comparison = `query.phrase` in the response when it is present, otherwise `case.query`.
  - A negative case (`expected_no_result = true`) always scores **0.0**, even when the quote contains the phrase and the denominator is greater than 0 (it must not be treated as 1.0).
  - Denominator = 0: a positive case → **`null`** (excluded from the average; not treated as 1.0); a negative case → **0.0**.
  - `expected_documents`/`expected_nodes` do **not** take part in `exact_phrase_precision`. They are used only for recall, precision, and the wrong rate.
  - The report also records `exact_phrase_returned` (the denominator), `exact_phrase_verified` (the raw numerator), and `exact_phrase_phrase`. The aggregate has `exact_phrase_cases_scored`, `exact_phrase_cases_null`, `exact_phrase_negative_cases`, `exact_phrase_total_labeled`, and `exact_phrase_total_verified`.
- **wrong_doc_rate** = returned administrative documents that are not in `expected_documents`, divided by the total number of returned administrative documents (within `results[:k]`).
- **wrong_node_rate** = clauses that match neither `expected_documents` nor `expected_nodes`, divided by the total number of returned clauses (the complement of precision@k).
- **no-result correctness** = for a case with `expected_no_result`, correct when `results` is empty **and** `empty_reason ∈ {NO_AUTHORIZED_DOCUMENTS, NO_RESULTS, PHRASE_NOT_FOUND}`.
- **p50/p95** = the median and nearest-rank over the latency of **successful** requests (HTTP 200, valid JSON), in milliseconds.
- The average of the metrics (except p50/p95) is the average over **each case** that actually ran. Cases with an HTTP error or a timeout are excluded from the numerator and the denominator and are counted separately in `cases_error`.
- How cases are split: `approved_by != null` → `official_metrics`; `approved_by = null` → `hucau_metrics`. When there is no approved case, `official_metrics = null` and `quality_status = "not_evaluated"`. When approved cases exist, `quality_status = "measured_on_approved_cases"` (the figures must still be reported together with the environment and the scale; do not conclude "passed" on your own).

## How to run

Use the backend venv's Python (the standard library only; install nothing extra):

```powershell
$py = 'E:\Programs\EvidenceRAG\backend-venv\Scripts\python.exe'

# 1) Test công thức/schema/mock HTTP (không cần API, không cần token)
& $py E:\Source\Evidence_RAG_Handoff\evaluation\search_eval\self_test.py

# 2) Tự kiểm tra công thức ngay trong harness (cùng fixture)
& $py E:\Source\Evidence_RAG_Handoff\evaluation\scripts\evaluate_search.py --self-test

# 3) Xem trợ giúp
& $py E:\Source\Evidence_RAG_Handoff\evaluation\scripts\evaluate_search.py --help

# 4) Chạy với API (khi backend đã có GET /api/v1/search và có token USER)
$env:EVIDENCE_ACCESS_TOKEN = '<token>'
& $py E:\Source\Evidence_RAG_Handoff\evaluation\scripts\evaluate_search.py `
    --base-url http://127.0.0.1:8000 `
    --queries E:\Source\Evidence_RAG_Handoff\evaluation\search_eval\queries_hucau.json `
    --output E:\Source\Evidence_RAG_Handoff\evaluation\search_eval\reports
```

Main parameters: `--base-url` (default `http://127.0.0.1:8000`), `--token` or `--token-env` (default `EVIDENCE_ACCESS_TOKEN`), `--queries`, `--k` (10), `--page-size` (50, the maximum per the contract), `--output` (a directory), `--timeout` (seconds), `--self-test`, `--fixtures`.

The report that is produced:

- `report.json`: the environment (OS, Python, base_url, time), `queries_sha256`, the size of the case set, `quality_status`, `official_metrics`, `hucau_metrics`, per-case detail (metrics, latency, response summary or error), and a FICTIONAL (HƯ CẤU) note.
- `report.md`: a metrics table, a per-case table, and a FICTIONAL (HƯ CẤU) / `not_evaluated` warning.

Exit codes:

| Code | When |
|---|---|
| `0` | The run finished and the report was written (including when the metrics are poor); `--self-test` passes. |
| `1` | `--self-test` fails (wrong formula or fixtures). |
| `2` | A configuration or token error (missing token, the token receives 401/403, invalid `--k` / `--page-size` / `--timeout`, invalid queries), or the API is not running or returns no valid response; **a report is not written**. |

## Procedure when real Gold exists

1. The person who holds the business domain approves each case, and **only then** is `approved_by` filled in (the approver's name or ID). The AI must not fill it in itself.
2. A real Gold case must use an approved corpus and approved administrative documents (văn bản), and must **not** be mixed into the file `queries_hucau.json`. Create a separate queries file (for example `queries_gold_v1.json`) with the corresponding `label` and `corpus`. If a different corpus needs to be run, update the constants `CORPUS_LABEL` and `LABEL` in the harness according to the owner's ADR or decision (currently only the label `HU_CAU` is supported).
3. Lock `split_revision` before tuning. Do not tune on held-out and then report the result again as an independent evaluation ([`docs/history/eval-gold-protocol.md`](../../docs/history/eval-gold-protocol.md)).
4. Run the harness on the Gold file. Report `official_metrics` together with the environment, the version, the data scale, and the number of approved cases. Do not claim "correct/sufficient" when there is no approved Gold.

## Limits / not yet done

- **Not yet run end-to-end against the real API at the time this README was written:** when this evaluation set was created, the backend did not yet have the route `GET /api/v1/search`, so `self_test.py` uses simulated responses (the route `GET /api/v1/search` was implemented later in `backend/app/api/v1/search.py` per [ADR-005](../../docs/architecture-decisions/ADR-005-search-v1.md)).
- **Real Gold is not implemented ([ADR-010](../../docs/architecture-decisions/ADR-010-khong-trien-khai-bo-cau-hoi-gold.md)):** 0 cases have `approved_by != null`. Every report will have `quality_status = "not_evaluated"` and `official_metrics = null`.
- The "hard checks" ("kiểm tra cứng") of section 9-A have not been checked (ACL, the effectivity (hiệu lực) label, highlight offset, the pagination limit, special characters, and standard errors). Those items need separate backend/API tests.
- Load and p95 have not been measured on the target Windows machine with ~100k nodes. The current p95 is only the latency of the requests in an actual run.
- The metric `exact_phrase_precision` uses the owner's definition (self-verify the quote; a negative case = 0; a positive case whose denominator is 0 = null). When Gold exists, a human approver confirms this convention again. There is no real Gold yet, so there are no official figures.
- Self-verification of `exact_phrase` only checks that the quote contains the phrase. It does not yet check a phrase that crosses a breadcrumb or heading boundary (section 9-A #5). That needs a separate backend/API test.
- The fictional fixture does not verify legal content and must not be used as citation (trích dẫn) evidence.
