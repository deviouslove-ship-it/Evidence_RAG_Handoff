**Language / Ngôn ngữ:** [Tiếng Việt](REPORT.md) · English

English counterpart of `docs/evidence/2026-10-31-search-v1/REPORT.md`. The Vietnamese file is the original.

# Search v1 implementation report — 2026-10-31

Source plan: `KE_HOACH_TRIEN_KHAI_TIM_KIEM_V1_Evidence_RAG.md`
(the version the owner finalized; the adjustments relative to the previous option are in section 2 of the plan).

## 1. Honest summary

- The **Search v1 module** was implemented on PostgreSQL: the index migration, `SearchService`, the APIs `GET /api/v1/search` and `/api/v1/search/approximate`, the Search page in the User Portal, backend and frontend tests, and an evaluation harness (FICTIONAL (HƯ CẤU) fixtures).
- **Quality has not been accepted**: 0 approved administrative documents (văn bản) in the dev database, 0 Gold cases approved by a domain owner, and recall, precision, and p95 have not been measured on real data. Every test result below is a **technical test on FICTIONAL (HƯ CẤU) fixtures**, not a quality figure.
- Chat keeps its previous behavior: the golden test is green (12 evidence items (căn cứ), 8 claims, 3 suggestions, `answer_generated=false`, a chain of 6 SSE events).

## 2. Work-package status

| WP | Status | Evidence / notes |
|---|---|---|
| SR-0 | Done | Compared with the current state; ADR-005 section 2; the chat golden test, 5 tests green |
| SR-1 | Done | `0006_search_index.sql` and `.down.sql`; up on the dev database; up/down in the PG test; `EXPLAIN` in the test confirms that `document_nodes_search_word_gin` is used |
| SR-2 | Done | `storage/search.py`: safe parsing, T1–T4, phrase verification against the content, ACL by allowed document ids, version by `as_of_date`, effectivity (hiệu lực) of each clause (Khoản), grouping by administrative document (văn bản), pagination; chat delegates to the legacy path when there is no quote |
| SR-3 | Done (no real HTTP server) | Route, schema, OpenAPI, error codes, rate limit, timeout, and hash-only audit; API E2E runs through ASGI (`httpx.ASGITransport`), and has not yet run through uvicorn or a browser |
| SR-4 | Partially done | `SearchPage.tsx`, navigation, and a button from chat; 52 frontend tests green; build and lint green. No browser E2E yet, no contrast test or image snapshot, and no "see more matching clauses" ("xem thêm khoản khớp") yet |
| SR-5 | Partially done | The backend returns `amendment_state` per clause (Khoản) and `effectivity_snapshot_status`; the PG test covers `modified` and `unknown`, and stale before a snapshot exists. The effectivity (hiệu lực) label in the UI is tested only with a mock; there is no real snapshot builder yet |
| SR-6 | Partially done | `evaluation/search_eval/` and `evaluation/scripts/evaluate_search.py`; 12 FICTIONAL (HƯ CẤU) cases; self-test of 22 tests, 47 value checks, and 4 latency checks. **No real Gold yet**, `official_metrics=null`, `quality_status=not_evaluated` |
| SR-7 | Partially done | An ACL test (a different principal ⇒ 0 results), special-character input, limits on length, word count, page, and rate, and timeout mapping; **p95 and load have not been measured**, and Local Mode packets have not been captured |
| SR-8 | Partially done | ADR-005, the runbook, this report, SRS §26, and the implementation-status update; there is no separate changelog file (the project has no CHANGELOG) |

## 3. Technical verification (real figures, 2026-10-31)

Environment: Windows, Python 3.11.15 (venv `E:\Programs\EvidenceRAG\backend-venv`),
local PostgreSQL 18.6 (port 55432), the Node bundled with the repo, vitest 2.1.3.

### Full verification (12/12)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1 `
  -ProgramsRoot E:\Programs `
  -OutputDirectory .\docs\evidence\2026-10-31-search-v1\verification
```

Result: **12/12 checks exit 0** (dependency-check, backend-lint, backend-typing,
backend-tests, source-policy, migration-pairs, openapi, polarity-fixtures,
temporal-fixtures, frontend-lint, frontend-tests, frontend-build). The logs and
`summary.json` are in `docs/evidence/2026-10-31-search-v1/verification/`.
Backend without a DSN: **171 passed, 16 skipped** (the PG tests were skipped); with a DSN:
**187 passed**.

### Backend

```powershell
$env:EVIDENCE_TEST_DATABASE_URL = "postgresql://...:55432/postgres"
python -m pytest backend/tests -q
```

Result: **187 passed, 0 failed, 1 warning** (ran 25.38 s), including the PG integration tests.
New tests: **26** (`test_search_parser.py`, `test_search_api.py`, `test_search_postgres.py`,
`test_chat_characterization.py`).

Notable checks in `test_search_postgres.py` (a temporary schema, FICTIONAL (HƯ CẤU) fixtures):

1. A phrase present in **2 administrative documents (văn bản)** ⇒ both documents are returned, and every clause is `exact_phrase`; `phrase_found=true`.
2. A phrase that does not exist ⇒ `phrase_found=false`, `empty_reason=PHRASE_NOT_FOUND`, and no clause is `exact_phrase`.
3. Every loose word is present ⇒ only `all_terms`, with no "exact phrase" ("đúng cụm từ") label.
4. Typing without diacritics ("periodic and regular reports", `bao cao dinh ky va thuong xuyen`) ⇒ a match on the folded channel, the label `phrase_folded`, and `phrase_found=false`; typing `kì` instead of `kỳ` still returns `exact_phrase` for the accented copy (normalization `kì→kỳ`, revision `vietnamese-tone-v3`).
5. A phrase joined across the **boundary between the breadcrumb/title and the content** (matching only inside `text_indexed`) ⇒ is **not** tagged `exact_phrase` (the boundary document is not in the phrase results).
6. Pagination: `page_size=1`, `totals.documents=2`, page 1 `has_more=true`, page 2 `has_more=false`.
7. ACL: a principal with no `category_acl` ⇒ 0 results, `empty_reason=NO_AUTHORIZED_DOCUMENTS`.
8. Effectivity (hiệu lực): before an active snapshot ⇒ `effectivity_snapshot_status="stale"`; after an active snapshot and an interval are created for one clause (Khoản) ⇒ status `ok`, that clause `modified`, and a clause with no interval `unknown`.
9. Highlight: `highlights` are absolute offsets on `quote_exact`; every sliced range contains "periodic report" ("báo cáo định kỳ").
10. API E2E in the same event loop (`httpx.ASGITransport`): the JSON matches the contract, `viewer_url` has the form `/api/v1/citations/ev_<uuid>/pdf?as_of_date=...`, and `source_hash` is present.
11. Migration `0006` up and down in a temporary schema: the index is dropped correctly.
12. `EXPLAIN` with `enable_seqscan=off` contains `document_nodes_search_word_gin`.

### Frontend

```powershell
pnpm run test   # 14 files, 65 passed, 0 failed
pnpm run build  # tsc --noEmit + vite build OK; JS 252.12 kB (gzip 76.80), CSS 33.25 kB (gzip 6.25)
pnpm run lint   # eslint --max-warnings=0 OK
```

14 new tests: `SearchPage.test.tsx` (12), `App.search.test.tsx` (1), and `EvidenceChat.searchLink.test.tsx` (1). The old tests are still green, including 3 `PdfViewer` tests (chat behavior is unchanged).

### OpenAPI

```powershell
python scripts/export_openapi.py
python scripts/export_openapi.py --check
```

Result: export and check are OK; `docs/openapi.json` contains `/api/v1/search` and `/api/v1/search/approximate`.

### Evaluation suite

```powershell
python evaluation/search_eval/self_test.py       # 22 test OK
python evaluation/scripts/evaluate_search.py --self-test
# {"self_test":"pass","label":"HU_CAU","cases_checked":6,"value_checks":47,"latency_checks":4,"failures":[]}
```

An end-to-end run against a real HTTP API is not possible yet because (a) there is no approved administrative document (văn bản) and (b) there is no USER token in the test environment. The harness already accepts `--base-url` and `--token-env`, so it can be run when those two conditions exist.

### Current dev data

A `SearchService` probe on the dev database (`postgres`) with the query "periodic and regular reports" ("báo cáo định kỳ và thường xuyên"):

```json
{ "phrase_found": false, "totals": {"documents": 0, "clauses": 0,
  "approximate_matches_hidden": 0}, "effectivity_snapshot_status": "stale",
  "results": [], "empty_reason": "NO_AUTHORIZED_DOCUMENTS" }
```

This is the behavior the design specifies when there are 0 approved nodes and 0 verified provenance records. It is **not** evidence that search runs correctly on real data.

## 4. Comparison with the acceptance criteria (plan section 9-A)

| # | Criterion | Status | Notes |
|---|---|---|---|
| 1 | A phrase in 3 approved administrative documents (văn bản) ⇒ all 3 are returned | Partial | The fixture test uses 2 exact documents plus 1 boundary document; there are not yet 3 real approved administrative documents (văn bản) to prove it |
| 2 | A phrase that is absent ⇒ `phrase_found=false`, no exact label, and the correct message | Met (fixture) | PG test |
| 3 | A match on loose words only ⇒ no "Exact phrase" ("Đúng cụm từ") label | Met (fixture) | PG test and UI mock |
| 4 | No diacritics / kì–kỳ / hòa–hoà finds the accented copy; label `phrase_folded` | Partially met | No diacritics plus kì/kỳ: PG test; hòa/hoà: a normalization unit test; no PG test yet for hòa/hoà |
| 5 | A phrase that straddles the breadcrumb/title and the content is not counted as exact | Met (fixture) | PG test `boundary` |
| 6 | Totals and pagination are accurate, with a depth limit | Met (fixture) | PG test; API service test PAGE_TOO_DEEP |
| 7 | ACL: revoking permission ⇒ 0 results, with no leak through the total, an empty result, or an error | Partially met | PG test with a different principal, plus the API rate; revocation mid-flight, and leakage through errors or timing, have not been tested |
| 8 | Effectivity (hiệu lực) of each clause (Khoản) has the correct label; stale has a warning; unknown shows "not yet verified" ("chưa xác minh") | Partially met | Backend test of `modified`, `unknown`, and stale; the UI labels are tested only with a mock |
| 9 | Highlight offsets are correct on `text_original`; if unsure, do not highlight | Met (fixture) | Unit and PG tests; the frontend test clamps and does not highlight |
| 10 | Open the PDF on the correct page, check ACL and the hash, lazy citation | Partially met | `viewer_url` matches the contract, and the existing citation test passes; a real PDF has not been opened from search because the fixture has no PDF file in the document store |
| 11 | Special-character input does not error and does not change the meaning | Met (fixture) | Parser and PG `báo "cáo - | & :* <-> ' % _` |
| 12 | Too long, too many words, over the rate, or over time ⇒ the correct error code | Partially met | Length, words, page, and rate: real tests; timeout: error mapping with a fake, and a real database timeout was not created |
| 13 | No chat regression | Met | Golden test of 5 tests, plus all of the old tests |
| 14 | Local Mode makes no request outside | Not checked with evidence | Code review only; packets were not captured |
| 15 | The audit does not store the raw query content | Met per the code | Metadata has only the SHA-256, the length, the filters, and the result count; there is no automated test yet |

## 5. Measured metrics (plan section 9-B)

**None yet.** recall@k, precision@k, `exact_phrase_precision`, `wrong_doc_rate`, `wrong_node_rate`, no-result, and p50/p95 are not reported, because there is no real Gold and no approved administrative document (văn bản). The evaluation harness is ready; when Gold exists, run:

```powershell
python evaluation/scripts/evaluate_search.py `
  --base-url http://127.0.0.1:8000 `
  --token-env EVIDENCE_ACCESS_TOKEN `
  --queries evaluation/search_eval/queries_gold.json `
  --output evaluation/search_eval/reports
```

## 6. Main files changed

Backend:

- `backend/app/storage/search.py` (new)
- `backend/app/schemas.py` (Search schema added)
- `backend/app/api/v1/user.py` (2 routes)
- `backend/app/api/v1/errors.py` (error codes)
- `backend/app/main.py` (service and rate wiring)
- `backend/app/config.py` (3 search settings)
- `backend/app/migrations/0006_search_index.sql` and `.down.sql` (new)
- `backend/tests/test_search_parser.py`, `test_search_api.py`, `test_search_postgres.py`, and `test_chat_characterization.py` (new); `test_auth_and_admin_portal.py` (migration list updated)

Frontend:

- `frontend/src/pages/SearchPage.tsx` and its test (new)
- `frontend/src/App.tsx`, `types.ts`, `api/client.ts`, `components/PdfViewer.tsx`, `pages/EvidenceChat.tsx`, `styles.css`, `App.search.test.tsx`, and `pages/EvidenceChat.searchLink.test.tsx`

Evaluation:

- `evaluation/search_eval/` (README, schema, 12 FICTIONAL (HƯ CẤU) cases, fixture, self-test)
- `evaluation/scripts/evaluate_search.py`

Documents:

- `docs/architecture-decisions/ADR-005-search-v1.md` (new)
- `docs/search-v1-runbook.md` (new)
- `docs/evidence/2026-10-31-search-v1/REPORT.md` (this file)
- `docs/SRS_v1.3.md` (§26), `docs/implementation-status.md`, `docs/openapi.json`

## 7. Remaining work / blocked

1. **Data**: a reviewer approves the 3 administrative documents (văn bản) in `pending_review` (or a real corpus is loaded), and provenance and spans are verified. Without this step, Search always returns `NO_AUTHORIZED_DOCUMENTS`.
2. **Search Gold**: a domain owner approves 30–50 cases; only after that are the official metrics run.
3. **Measure p50/p95** on the target Windows machine, at a scale of about 100,000 nodes; currently there are only functional tests.
4. **PDF highlight (bbox/quads)** and OCR: a separate work package, not done.
5. **"See more matching clauses" ("Xem thêm khoản khớp")** inside each administrative document (văn bản): an API parameter has to be added if that is wanted.
6. **Browser E2E, automated contrast and accessibility, and Local Mode packet capture**: the current environment does not have the dependency or the means.
7. **Owner decisions**: the `exact_phrase_precision` convention for a case with no exact phrase, the p95 threshold, the wording of PAGE_TOO_DEEP, normalization of `doc_type`, and the OCR ADR.

## 8. Round-2 update — 2026-10-31 (following owner feedback)

### 8.1. Reindex and normalization (supplement to SR-0/SR-1)

- Migration `0007_normalization_revision.sql`: adds `document_nodes.normalization_revision`; old data is assigned `vietnamese-tone-v2`, and new data is written as `vietnamese-tone-v3` (the pair `kì→kỳ` is included).
- The backend checks at startup; `/api/v1/system/mode` returns `search_normalization_status` (`current|stale|unavailable`), the revision, and the number of stale nodes.
- `scripts/backfill_search_normalization.py` (dry-run and batch) recomputes `text_normalized` and `text_folded` and does not change `text_original` or `text_indexed`. It was run on the dev database: **648 v2 nodes → 0 stale** (log `normalization-backfill.log`).
- A new PG test: a simulated v2 node (`định kì`, "periodic", folded `dinh ki`) does not match before backfill; after backfill it matches `phrase_folded` (and is not tagged `exact_phrase`). If the revision changes and there is no backfill, stale status is reported instead of silence.

### 8.2. Benchmark on 100,000 generated nodes

The script `scripts/benchmark_search.py` (FICTIONAL (HƯ CẤU); 1,000 administrative documents (văn bản) × 100 nodes; with fake page, span, provenance, and category ACL; `enable_seqscan=off` is not set). The default planner is `enable_seqscan=on`, `random_page_cost=4`, `work_mem=4MB`, JIT on. EXPLAIN ANALYZE: the plan contains `document_nodes_search_word_gin`; execution is 66–423 ms depending on the run.

| Query | p50 | p95 |
|---|---:|---:|
| Phrase "periodic and regular reports" (`"báo cáo định kỳ và thường xuyên"`) | 243.62 ms | **324.31 ms** |
| Keyword "periodic report" (`báo cáo định kỳ`) | 255.57 ms | 268.95 ms |
| No results | 62.61 ms | 62.61 ms |
| Default API (with the approximate cap) | — | 338.66 ms (one run) |

The provisional p95 target is 300 ms: the phrase **exceeds it by 24.31 ms**, and the keyword meets it; it is locked only after a measurement on the target Windows machine. Plan and configuration details: `benchmark/benchmark.json`, `benchmark/benchmark.md`.
Accompanying optimizations: read the ACL by document (do not scan 100k nodes on every request); skip the all-terms count when the phrase tier already has results; cap the approximate count at 500 and compute it only when needed (previously the default API took 42 s at 100k nodes, and now takes about 0.34 s).

### 8.3. Pagination of matching clauses (Khoản)

- The API adds `clause_page` and `clause_page_size` (maximum 50), and the fields `clause_page`, `clause_page_size`, and `has_more_clauses` on each document.
- The UI shows "Showing X/Y clauses" ("Hiển thị X/Y khoản") and a "See more matching clauses" ("Xem thêm khoản khớp") button; the client accumulates by `node_id` because the API returns an offset window. Limit: reloading a URL with `clause_page>1` loads only the current clause page and does not rebuild the buffer of the earlier pages.

### 8.4. Accessibility, contrast, Local Mode, browser E2E, and CI

- Frontend: **65 tests in 14 files**, with build and lint green. Added:
  - Accessibility: role and label, `aria-live="polite"` on the result region, `aria-expanded` and `aria-controls`, and a heading per administrative document (văn bản).
  - Contrast: the real tokens are read from `tokens.css` and `styles.css` and scored with WCAG; the lowest is **5.21:1** (`<mark>` is 14.26:1), and every pair is at least 4.5:1.
  - Local Mode: every fetch is `/api/v1/...`, with no external host; `dist/index.html` has no external resource.
  - Browser E2E: headless Chrome 156 over CDP, plus a same-origin fixture API (no new dependency); login, then phrase search, then badge/mark/stale, then clause_page=2, then approximate lazy load, then the PDF iframe; **10–12 requests, 0 external http(s) origin**. The harness is in the repo at `frontend/e2e/search.e2e.mjs` (plus a README) and is run with `pnpm run e2e:search` and `CHROME_PATH`. This is **not** yet a real backend plus approved data.
- CI: the workflow sets `EVIDENCE_TEST_DATABASE_URL` from a secret and `CI=true`; `verify.ps1` and `backend/tests/conftest.py` stop if the DSN is missing, so a PG test is not left skipped. Browser E2E is not in CI yet, because it needs a stable Chrome runner.

### 8.5. Defaults waiting on the owner (applied provisionally)

- `PAGE_TOO_DEEP`: "You have reached the result limit. Narrow the results with a filter, or use a more specific keyword." ("Bạn đã xem tới giới hạn kết quả. Hãy thu hẹp bằng bộ lọc hoặc dùng từ khóa cụ thể hơn.") (backend and frontend).
- `doc_type`: a controlled list managed by the curator; the UI provisionally uses `decree/circular/decision/other`; the old free-text data needs to be normalized.
- `exact_phrase_precision`: the numerator is the number of clauses (Khoản) tagged exact_phrase that actually contain the phrase, divided by the total number of clauses tagged exact_phrase; a negative case is 0; a denominator of 0 on a positive case is null; the harness self-test has 27 tests.
- A provisional p95 of 300 ms on 100,000 generated nodes; locked after the target machine.
- The rate limit is currently correct for a single process only; multiple workers need a shared store.

### 8.6. Verification repeated

- Backend: **187 passed** with PostgreSQL (after migration 0007 and the other changes); 171 passed and 16 skipped when there is no DSN.
- Frontend: 65 passed; build and lint are green.
- Evaluation: a self-test of 27 tests, and `--self-test` with 8 cases, 75 value checks, and 4 latency checks; `quality_status=not_evaluated` still holds (0 Gold, 0 approved).
- `scripts/verify.ps1`: **12/12 checks exit 0** (new logs in `docs/evidence/2026-10-31-search-v1/verification/`).

### 8.7. Not done

- Real Gold, and approval of the administrative documents (văn bản) and of provenance; recall, precision, and a quality p95 have not been measured.
- PDF bbox highlight and OCR; browser E2E against the real backend; a CI browser runner.
- Reloading `clause_page>1` does not rebuild the buffer; there is no test yet that resets clause_page when the filter changes.
- Free-text `doc_type` has not been normalized; a multi-worker rate limit has not been built.
