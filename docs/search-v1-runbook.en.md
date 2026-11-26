**Language / Ngôn ngữ:** [Tiếng Việt](search-v1-runbook.md) · English

English counterpart of `docs/search-v1-runbook.md`. The Vietnamese file is the original.

# Runbook — Search for administrative documents (văn bản) and evidence (căn cứ) retrieval for chat

Updated 2026-11-05. Applies to `GET /api/v1/search`, `GET /api/v1/search/approximate`, the “Tìm kiếm văn bản” (“Search administrative documents”) page, and the evidence-retrieval step of chat. Architecture decisions: `docs/architecture-decisions/ADR-005-search-v1.md` and `docs/architecture-decisions/ADR-006-retrieval-accuracy-bounds-and-ai-resilience.md`.

## 1. Prerequisites

- PostgreSQL is running, and migrations apply themselves when the backend starts (`apply_migrations`). Check:

```sql
SELECT name FROM schema_migrations ORDER BY name;      -- 0001 … 0016 (Search v1: 0006, 0007)
SELECT indexname FROM pg_indexes WHERE tablename = 'document_nodes';
-- phải có document_nodes_search_word_gin, document_nodes_search_folded_gin
```

- There must be an approved administrative document (văn bản): `document_versions.review_status='approved'`, `document_nodes.review_status='approved'`, `source_provenance.verified_at IS NOT NULL`, and the user has permission on the category or the administrative document. If any of that is missing, the response is `NO_AUTHORIZED_DOCUMENTS` — that is the design, not a fault.
- Each administrative document uses **one version**: the `approved` copy with the greatest `version_number` that is still in effect (hiệu lực) at `as_of_date` (an empty `valid_from`/`valid_to` means there is no bound) and that has verified provenance. This applies to search and to chat.

## 2. Configuration

| Environment variable | Default | Range | Meaning |
|---|---|---|---|
| `EVIDENCE_SEARCH_STATEMENT_TIMEOUT_MS` | `5000` | 100–60000 | The database budget of one search, and of chat retrieval |
| `EVIDENCE_SEARCH_COUNT_CAP` | `8000` | 500–100000 | The maximum number of clauses (Khoản) that are source-checked, scored, and counted (the owner set this on 2026-11-05) |
| `EVIDENCE_SEARCH_RATE_PER_MINUTE` | `30` | 1–600 | Searches per minute per user, per process |
| `EVIDENCE_SEARCH_MAX_PAGE_DEPTH` | `1000` | 50–10000 | The maximum of `page × page_size` |
| `EVIDENCE_QUERY_TIMEOUT_SECONDS` | `45` | ≤ 300 | The budget of a whole chat turn (AI selection of evidence (căn cứ) uses 70%) |
| `DATABASE_URL` | — | — | Required; in-memory is for tests only |

Limits fixed in code:

- A search is ≤ 500 characters and ≤ 20 words, and a phrase is ≤ 200 characters; `page_size` and `clause_page_size` are ≤ 50 (the defaults are 20 and 5).
- At most 4 concurrent database searches per process; a wait past 100 ms returns `SEARCH_BUSY` (429).
- `approximate_matches_hidden` counts at most 500, and it is computed only when a keyword search has ≤ 200 clauses.
- Chat: 12 evidence items per turn; at most 1,500 candidates per channel; 4 concurrent database retrievals per process (a later one waits, and is not rejected).
- The `search.query` audit has a limit of 250 ms; when that expires, only a warning is written, and the result is still returned.
- Every search and chat transaction sets `plan_cache_mode = force_custom_plan`.

## 3. Behavior worth knowing

### 3.1. The search page

- Quotation marks mean a phrase search: `exact_phrase` (diacritics kept) and `phrase_folded` (diacritics folded); if the phrase is absent, the search falls through to all-words and returns `PHRASE_NOT_FOUND`. Without quotation marks the search is all-words, with diacritics or without. A document number (`15/2020/NĐ-CP`, `ND`, lowercase) brings that administrative document (văn bản) to the top.
- Under `EVIDENCE_SEARCH_COUNT_CAP`: `totals` and the order are exact. Over the threshold: `totals.capped=true` and `totals.clauses=N`; ranking is inside the first N clauses (Khoản); the interface shows “hơn N khoản” (“more than N clauses”), pagination states only the current page, and the clause count of each administrative document shows “ít nhất” (“at least”). Once the threshold has been passed, `PHRASE_NOT_FOUND` is not returned.
- The audit records `capped` so that N can be adjusted: the target is that about 95% of real searches are counted in full.

### 3.2. Chat

- A query in quotation marks uses the phrase search of the search page. A query without quotation marks uses these channels: the document number (together with the Article (Điều) when one is present), “Điều N” (“Article N”) (when no document number matches), all keywords (with diacritics and without), and the title of the administrative document (văn bản). The “one of the words” channel and the label of a legacy record run only when results are short.
- Question words (“là gì” (“what is it”), “như thế nào” (“how”)…) are dropped. The Article/clause/point portion and the document number are split out of the keywords once they already have their own channel.
- Evidence (căn cứ) that is no longer in effect: see ADR-006 §2.5 (option C).

## 4. Operations

### Starting

```powershell
.\scripts\start-local-stack.ps1 -ProgramsRoot E:\Programs
Invoke-RestMethod http://127.0.0.1:8000/health
```

In Local Mode, the search page calls only the same-origin API.

### An empty state

| `empty_reason` | Meaning | What to do |
|---|---|---|
| `NO_AUTHORIZED_DOCUMENTS` | There is no approved administrative document (văn bản) the user is allowed to see | Approve the administrative document; check the category ACL |
| `NO_RESULTS` | There are administrative documents, and none of them match | Drop keywords or filters |
| `PHRASE_NOT_FOUND` | The exact phrase is not present; the accompanying results are all-words | Turn off “Tìm chính xác cụm từ” (Search for the exact phrase) to search for separate words |

### Common errors

| Code | HTTP | What to do |
|---|---|---|
| `QUERY_EMPTY` | 422 | Enter a keyword or a phrase |
| `QUERY_TOO_LONG` | 422 | Shorten it to under 500 characters (a phrase to under 200) |
| `TOO_MANY_TERMS` | 422 | At most 20 words |
| `PAGE_TOO_DEEP` | 422 | Narrow the search with a filter or a more specific keyword |
| `RATE_LIMITED` | 429 | Wait a few seconds; the limit is per process |
| `SEARCH_BUSY` | 429 | The server is already handling 4 searches; try again in a few seconds |
| `SEARCH_TIMEOUT` | 504 | Narrow the keywords or the filters; check the database load and `statement_timeout` |
| `QUERY_TIMEOUT` (chat over SSE) | — | Retrieval, or the evidence (căn cứ) re-check, went over the budget; try again |
| `DATABASE_NOT_CONFIGURED` | 503 | The database has not been configured |
| `INVALID_REQUEST` | 422 | A parameter is wrong (`page_size` > 50, a bad UUID, …) |

### Check that the index is used

```sql
SET enable_seqscan = off;
EXPLAIN (COSTS OFF)
SELECT 1 FROM document_nodes n
WHERE to_tsvector('simple'::regconfig, n.text_indexed)
      @@ plainto_tsquery('simple'::regconfig, 'báo cáo');
-- plan phải chứa document_nodes_search_word_gin
```

Do not add a b-tree on `document_nodes(document_version_id)`: the planner will use it instead of the GIN index and the query will take seconds (ADR-006 §2.3).

### Normalizing the data

- `GET /api/v1/system/mode` returns `search_normalization_status` (`current|stale|unavailable`), the revision, and the count of old nodes. `stale` means some nodes were normalized with the old diacritic-variant table; search can miss a variant.
- Backfill: `python scripts/backfill_search_normalization.py --dry-run`, then run it without `--dry-run`. It only recomputes `text_normalized`/`text_folded`. It does not change the original source evidence.
- After every large load or approval batch, run `ANALYZE document_nodes;` so the planner has the right statistics.

## 5. Reference performance

Measured on the dev machine, on FICTIONAL (HƯ CẤU) data of 1,000 administrative documents (văn bản) × 100 clauses (Khoản), without forcing seqscan off:

| Flow | p50 |
|---|---:|
| A keyword search, 1,000 matching clauses | about 100–140 ms |
| A search with no results | 15–40 ms |
| A search for a word present in 99% of clauses (it hits the limit of 8,000) | 1.1–1.3 s |
| Chat retrieval | 0.15–0.35 s |

The provisional p95 target of 300 ms is fixed only after a measurement on the target Windows machine. Run it again with `python scripts/benchmark_search.py --documents 1000 --nodes-per-document 100`.

## 6. Tests

```powershell
$env:PYTHONPATH = "E:\Source\Evidence_RAG_Handoff\backend"
$env:EVIDENCE_TEST_DATABASE_URL = "postgresql://evidence_dev_admin:<password>@127.0.0.1:55432/postgres"
E:\Programs\EvidenceRAG\backend-venv\Scripts\python.exe -m pytest backend/tests -q

$node = "E:\Programs\EvidenceRAG\runtimes\node\node.exe"
$pnpm = "E:\Programs\EvidenceRAG\tools\pnpm\node_modules\pnpm\bin\pnpm.cjs"
& $node $pnpm --dir frontend test
& $node $pnpm --dir frontend build
& $node $pnpm --dir frontend lint
```

The PostgreSQL tests create a temporary schema and then drop it; they do not write business data. CI has to set `EVIDENCE_TEST_DATABASE_URL`; if the DSN is missing, `verify.ps1` and conftest stop. Browser end-to-end tests (the API fixture): set `$env:CHROME_PATH="<chrome.exe>"` and then run `pnpm --dir frontend run e2e:search`.

## 7. Quality evaluation

Run this only when there is Gold [Not implemented — see ADR-010] that the person who holds the business knowledge has approved, and the administrative documents (văn bản) have been approved:

```powershell
python evaluation/scripts/evaluate_search.py `
  --base-url http://127.0.0.1:8000 --token-env EVIDENCE_ACCESS_TOKEN `
  --queries evaluation/search_eval/queries_gold.json --output evaluation/search_eval/reports
```

A case with `approved_by=null` is split into `hucau_metrics`. If no case has been approved, `quality_status=not_evaluated`. Do not report “đúng/đủ” (“correct/complete”) before there is a Gold [Not implemented — see ADR-010] report.

## 8. Backup and rollback

- Migration 0006 only adds indexes. Roll it back with `0006_search_index.down.sql`. Do not roll the schema back before there is a backup.
- Do not delete `document_nodes`, `source_spans`, or `source_pages` in order to “clean up” search.
- To turn the search page off for a while: hide the navigation item in the frontend, or block `/api/v1/search` at the reverse proxy. Chat keeps working.

## 9. Still waiting on the owner

- Approve Gold [Not implemented — see ADR-010], and fix p95 on the target machine. Define `exact_phrase_precision` (the numerator: clauses (Khoản) tagged `exact_phrase` that contain the exact phrase; the denominator: every clause tagged `exact_phrase`; a negative case = 0).
- Normalize the old free-text `doc_type` values (the new intake screen already chooses from `decree/circular/decision/other`).
- OCR for a scanned PDF (Tesseract OCR is wired, with a review of each page, in migration `0015_ocr_page_review.sql` and `documents/ocr.py` as of 2026-11-08). Highlighting a bbox inside the PDF is **[Not implemented]** — the viewer opens the correct PDF page together with the verbatim excerpt.
- Put the rate limit and the concurrency limit in a shared store before running more than one worker.
