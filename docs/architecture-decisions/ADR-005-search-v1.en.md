**Language / Ngôn ngữ:** [Tiếng Việt](ADR-005-search-v1.md) · English

English counterpart of `docs/architecture-decisions/ADR-005-search-v1.md`. The Vietnamese file is the original.

# ADR-005 — Administrative-document (văn bản) search (Search v1): PostgreSQL FTS, match tiers, and lazy citation

- Date: 2026-10-31
- Status: Partially implemented (P0 backend + frontend + tests; see the section "Consequences")
- Scope: `GET /api/v1/search` + `/api/v1/search/approximate`, `SearchService`, migration `0006`, the Search page (`Tìm kiếm`, "Search") in the User Portal
- Source documents: `docs/KE_HOACH_TRIEN_KHAI_TIM_KIEM_V1_Evidence_RAG.md` (the version the owner finalized), `SRS_v1.3.md`
- Update: pagination and totals are computed in PostgreSQL from 2026-11-01 (the cap of 5,000 is dropped); from 2026-11-05, [ADR-006](ADR-006-retrieval-accuracy-bounds-and-ai-resilience.md) applies — the count limit `EVIDENCE_SEARCH_COUNT_CAP` (the owner finalized it at 8,000), version selection in a separate statement, chat without double quotes has a bounded candidate channel and `statement_timeout`. The items in section 4.3 about the cap of 5,000 and about legacy chat having no timeout are no longer correct.

## 1. Context

Before Search v1, the backend had only one crude lexical channel in `authorized_search.py`: `to_tsvector('simple', ...)` was recomputed on each row, AND of every word and then a fallback OR of each word, no phrase/adjacency, a ceiling of 12 nodes, no pagination, and no grouping by administrative document (văn bản). The tables `lexical_search_index` and `embedding_indices` exist in migration 0001, but no piece of code uses them. There was no search API, and no Gold [Not implemented — see ADR-010]/metric.

The owner's requirement: add Search v1 on PostgreSQL, do not use an external search engine, integrate it into the existing app, keep chat behavior unchanged, and do not use an AI model in search (`KE_HOACH...` sections 1–3).

## 2. SR-0 results — current state compared with the plan

| What the plan describes | Actual source | Conclusion |
|---|---|---|
| FTS `simple`, bag of words, no phrase | `authorized_search.py` lines 193–231 | Matches |
| `tsvector` recomputed per row, no index | No expression index before 0006 | Matches |
| Ceiling of 12 nodes | `fixed_pipeline.py` calls search without passing `limit`; the default is 12 | Matches |
| Only approved nodes + provenance verified | Correct in the search SQL and in citation | Matches |
| `text_indexed` = breadcrumb + title + number + label + content | `draft.py`: `indexed = title + document_number + label + exact_text` | Matches; therefore the index only needs `text_indexed`, and does not concatenate again |
| `text_folded`/`text_normalized` generated at ingest | `draft.py` calls `normalize_text`/`fold_text`; `unicode_norm.NORMALIZER_REVISION = vietnamese-tone-v3` (hoà→hòa, thuý→thúy, kì→kỳ) | Matches; no new normalization function is needed; changing the map requires backfill/reingest (there is no approved data yet) |
| Legal Reference Router | There is no class with that name; `vietnamese_nlp/legal_citation_parser.py` + `canonical_document_number` are sufficient | Reuse them, and add recognition of a bare document number (số hiệu trần) |
| `official_url` stored but not yet exposed | `document_versions.official_url` + `source_provenance.official_url` | Correct; Search v1 returns `document_versions.official_url` |
| `pg_trgm`/`unaccent` | Extension files exist in the bundled PostgreSQL 18.6 (check `share/extension`) | Present; trigram is **not yet enabled** (see section 4.2) |
| 0 approved data | Probe on 2026-10-31: 0 approved nodes, 0 verified provenance | Matches; see section 6 |

An important difference found in SR-0/SR-1: `authorized_nodes` is a `UNION` + `DISTINCT`; when the query has the form `n.id IN (SELECT id FROM authorized_nodes)`, the planner materializes the view and then filters with `document_nodes_pkey`, and **does not use GIN** (EXPLAIN was captured during development). The design therefore changed the way ACL is filtered (section 4.1).

## 3. Decision

### 3.1. Search channel

- Search v1 uses only PostgreSQL FTS (L2 syllable, `simple`); no Vietnamese tokenizer, no embedding, no reranker, and no AI model. Option B (dense + RRF) is left for later.
- Add migration `0006_search_index.sql` with two GIN expression indexes:

```sql
CREATE INDEX document_nodes_search_word_gin
  ON document_nodes USING GIN (to_tsvector('simple'::regconfig, text_indexed));
CREATE INDEX document_nodes_search_folded_gin
  ON document_nodes USING GIN (to_tsvector('simple'::regconfig, text_folded));
```

- Raise `NORMALIZER_REVISION` to `vietnamese-tone-v3` and add the pair `kì→kỳ` (meeting the kì–kỳ criterion); changing the diacritic-variant table requires reingest/backfill of `text_normalized`/`text_folded`. There is currently no approved administrative document (văn bản), so data is not yet affected.
- Do not use `pg_trgm` in v1: `phraseto_tsquery` already preserves word position; add trigram only when a benchmark confirms it is needed (the condition in plan section 2, item 5). Therefore there is no LIKE/`%`/`_` on the query path, and LIKE does not have to be escaped.
- Do not add a generated column; the index uses exactly the expression that the query uses. The migration has `.down.sql`; up has been run on the dev DB, and down/up has been run in a temporary PG test.

### 3.2. ACL and allowed document ids

- Inside the same transaction (after `set_config('app.user_id', ...)`), SearchService first takes `SELECT DISTINCT document_id FROM authorized_nodes`, then passes that array into the main query as `n.document_id = ANY($11::uuid[])`.
- Reason: a `UNION DISTINCT` view does not let the planner use GIN when it stands behind `IN (view)`; this approach keeps the ACL boundary at the view (the single source), while the query on `document_nodes` can use the expression index. A temporary PG test confirms that the plan contains `document_nodes_search_word_gin` (`test_search_postgres.py`, `EXPLAIN` with `enable_seqscan=off`).
- Do not cache the allowed-document list; each request reads it again inside the transaction so that a permission revocation takes effect immediately. If `allowed_documents` is empty, return `NO_AUTHORIZED_DOCUMENTS` without running the administrative-document query.

### 3.3. Match tiers

| Tier | `match_type` | How it is determined |
|---|---|---|
| T1 | `exact_phrase` | `phraseto_tsquery` on `text_indexed`, then **re-verified on that node's own `text_normalized`** (not using `text_indexed`) |
| T2 | `phrase_folded` | `phraseto_tsquery` on `text_folded`, verified on `text_folded`; present only when T1 does not match |
| T3 | `all_terms` | `plainto_tsquery` on `text_indexed` (every word is present; the words do not have to be adjacent) |
| T4 | `any_term` | returned only through `GET /api/v1/search/approximate`; not mixed into the main page |

- When the query has at least one T1/T2, the main list contains only T1/T2; T3 is not mixed in. When there is no T1/T2, T3 is returned together with `empty_reason=PHRASE_NOT_FOUND` so the user sees “không đúng cụm từ, đây là các khoản đủ từ” (`không đúng cụm từ, đây là các khoản đủ từ`, "not the exact phrase; these are the clauses that contain every word").
- Do not build a tsquery string by concatenating the input: phrase/terms are passed as parameters into `phraseto_tsquery`/`plainto_tsquery`; the input is tokenized only with a letter-and-digit regex.
- T2 is never tagged `exact_phrase`; the corresponding UI label is “Cụm từ (không dấu)” (`Cụm từ (không dấu)`, "Phrase (without diacritics)").

### 3.4. Version, effectivity (hiệu lực), and scope

- Select the approved version by `as_of_date`: `valid_from <= as_of` and (`valid_to IS NULL` or `valid_to > as_of`), preferring the largest `version_number`.
- `amendment_state` is taken from `node_effective_intervals` plus the snapshot that has `is_active`, **per clause (Khoản)**. No interval ⇒ `unknown`.
- `effectivity_snapshot_status` = `ok` if an active snapshot exists, otherwise `stale`. The definition of `stale` is simple because the current code has no job that creates a snapshot; this point needs to be clarified when there is an Effective Snapshot builder (see “Consequences”).
- `only_active=true` keeps only clauses with `active`; by default it also shows `modified` (amend (sửa đổi)) / `repealed` (repeal (bãi bỏ)) / `suspended` / `not_yet_effective` / `unknown`, together with labels.

### 3.5. Lazy citation and highlight

- Results return `node_id`, `label`, `page`, `quote_exact`, `snippet`, `snippet_start`, `highlights` (absolute offsets on `quote_exact`), `viewer_url`, and `source_hash`. An `evidence_id` record is not created on every search.
- `viewer_url` = `/api/v1/citations/ev_<node_id>/pdf?as_of_date=...`. When the user opens it, the existing citation API re-checks ACL/provenance and the PDF hash. The citation contract does not change.
- A highlight is returned only when the exact span is found on `text_original`; if it is uncertain (no direct match, or the phrase matches only on the folded text) then `highlights=[]` — do not paint.
- There is no PDF overlay (PDF.js text layer/bbox); that is a separate WP, outside Search v1.

### 3.6. Chat compatibility

- `SearchService.search_clauses` is the adapter for chat: if the question has no phrase in double quotes, delegate entirely to `PostgresAuthorizedNodeSearch.search` (keep the old behavior: 12 evidence items (căn cứ), stopwords, ranking by document number/Article (Điều)). If there are double quotes, use the new phrase path; if there are no results, fall back to legacy.
- The golden test `test_chat_characterization.py` locks in: 12 evidence, 8 claims, 3 suggestions, the status, `answer_generated=False`, and a sequence of 6 SSE events. This test is green before and after the refactor.
- Consequence: chat **does not** automatically benefit from the new ranking/tiers outside quote mode; this is an intentional backward-compatibility choice.

### 3.7. API, safety, and performance

- `GET /api/v1/search` and `GET /api/v1/search/approximate`; parameters follow plan section 6.
- Limits: q ≤ 500 characters, ≤ 20 words, `page_size` ≤ 50, `page*page_size` ≤ 1000 (defaults configured through `EVIDENCE_SEARCH_*`).
- `statement_timeout` is set inside the search transaction (`EVIDENCE_SEARCH_STATEMENT_TIMEOUT_MS`, default 5000 ms); a timeout error maps to `SEARCH_TIMEOUT` (504).
- Rate limit: an in-memory sliding window per principal (`EVIDENCE_SEARCH_RATE_PER_MINUTE`, default 30/minute). This limit is **per process** and is not shared among multiple workers; it is accepted for single-process Local Mode, and it needs to be replaced by Redis/DB if the system runs multiple workers.
- Audit: after a search, append `audit_events` with the **SHA-256 hash of the query**, the length, the mode, page/page_size, the result count, and the duration; do not store the raw content. An audit failure does not break the search request.
- Do not log or return the names of documents the caller is not allowed to see; `NO_AUTHORIZED_DOCUMENTS` uses a single sentence.

### 3.8. Frontend

- The Search page is a separate surface in the User Portal; chat stays mounted when the user changes pages.
- Query state lives in the URL query string (`history.replaceState`), with a fallback to internal state when the shell does not support history.
- The `doc_type` filter uses the codes `decree` (Decree (Nghị định)) / `circular` (Circular (Thông tư)) / `decision` (Decision (Quyết định)) / `other`; current data stores doc_type as free text, so the vocabulary needs to be normalized at data entry (see “Consequences”).
- `viewer_url` accepts only the citation regex `/api/v1/citations/ev_<uuid>/pdf...`; the backend returns exactly this form.
- No dependency is added; colors use the existing tokens.

## 4. Consequences

### 4.1. Evidence already in hand

- Backend: `187 passed` when run against real PostgreSQL (`EVIDENCE_TEST_DATABASE_URL`), including a temporary PG test for migration 0006 up/down, EXPLAIN of the index, T1/T2/T3, ACL, pagination, effectivity (hiệu lực) per clause (Khoản), a phrase that straddles the breadcrumb and is not tagged T1, and API E2E over ASGI (`test_search_postgres.py`).
- Frontend: `65 passed` (14 files), `tsc --noEmit` + `vite build` OK, `eslint --max-warnings=0` OK.
- OpenAPI: `scripts/export_openapi.py --check` OK; `/api/v1/search` and `/api/v1/search/approximate` are present.
- Dev data status: 0 approved administrative documents (văn bản); the probe returns `empty_reason=NO_AUTHORIZED_DOCUMENTS` (correct by design, not a search error).

### 4.2. Not yet evidenced / still owed

- There is not yet a Gold [Not implemented — see ADR-010] search set approved by the person who owns the business domain; recall/precision/`wrong_doc_rate`/`wrong_node_rate`/no-result have not been measured on real administrative documents. The new eval harness has only a FICTIONAL (`HƯ CẤU`) self-test (22 tests), `quality_status=not_evaluated`.
- p50/p95 have not been measured on the target Windows machine / at a scale of ~100k nodes; a load test has not been run.
- A real HTTP server plus browser E2E has not been run; so far there is only ASGI E2E (TestClient/ASGITransport) and a UI test with mock fetch.
- There is no highlight inside the PDF (only a snippet/HTML plus opening the correct page); there is no OCR.
- “xem thêm khoản khớp trong từng văn bản” (`xem thêm khoản khớp trong từng văn bản`, "see more matching clauses within each administrative document") has not been built (the API returns at most 5 clauses per administrative document, and there is no clause-pagination parameter).
- There is no automated contrast/a11y test; “Local Mode không request ra ngoài” (`Local Mode không request ra ngoài`, "Local Mode makes no outbound request") has not been measured by capturing packets.
- `pg_trgm` is left open: if a benchmark confirms that faster phrase verification is needed, add it later under a separate decision (including LIKE escaping).
- The convention for `phrase_found`/`empty_reason`, and the way T3 is hidden when T1 is present, need confirmation from the owner/reviewer when the Gold [Not implemented — see ADR-010] is produced.

### 4.3. Known risks

- Totals and pagination come from a SQL count statement on the same predicate; if T1 verification drops a candidate but that node is not present in T3, `totals.clauses` can be higher than the number displayed. This has not occurred with the current data; it needs a test on a large corpus.
- ~~Candidate cap of 5,000 for each tier~~ — removed on 2026-11-01; replaced by a count limit with the flag `totals.capped` (ADR-006).
- The in-memory rate limit cannot be used when running multiple workers.
- ~~Legacy chat search has no timeout~~ — from 2026-11-05, chat shares `statement_timeout` and at most 4 concurrent DB rounds (ADR-006).
- On upload, `doc_type` is now chosen from 4 codes (`decree` (Decree (Nghị định)) / `circular` (Circular (Thông tư)) / `decision` (Decision (Quyết định)) / `other`); old free-text data still needs to be normalized before filtering is complete.

## 5. Rejected options

- **B (dense + RRF + reranker):** there is not yet a model running locally plus a Gold [Not implemented — see ADR-010]; do it later, plugging in an additional channel through the `SearchService` interface (expected: `LexicalChannel`, `DenseChannel`).
- **C (Elasticsearch/OpenSearch/Meilisearch/ParadeDB):** rejected according to plan section 1; it would duplicate ACL, add operational work, and collide with “PostgreSQL là DB duy nhất” (`PostgreSQL là DB duy nhất`, "PostgreSQL is the only database").

## 6. Work that needs the owner/reviewer

1. Approve 3 administrative documents (văn bản) in `pending_review` (or load a real corpus) and verify provenance/span; otherwise Search is correct in code but always empty.
2. Approve a Gold [Not implemented — see ADR-010] search set of 30–50 queries; only then may quality metrics be reported.
3. Finalize the convention for `exact_phrase_precision` on cases that have no exact phrase, the acceptable p95 threshold, and the wording of `PAGE_TOO_DEEP`.
4. Decide OCR (a separate ADR) and normalize `doc_type` at data entry.

## 7. Update of 2026-10-31 — normalization, benchmark, and clause (Khoản) pagination

### 7.1. Normalization and backfill

- Migration `0007_normalization_revision.sql` adds `document_nodes.normalization_revision`; old data is assigned `vietnamese-tone-v2`, and new data records `vietnamese-tone-v3`.
- The backend checks at startup, and `/api/v1/system/mode` returns a stale/current status; `scripts/backfill_search_normalization.py` recomputes `text_normalized`/`text_folded` (it does not change `text_original`/`text_indexed`). Backfill has been run on the dev DB: 648 v2 nodes → 0 stale; log at `docs/evidence/2026-10-31-search-v1/normalization-backfill.log`.
- The PG test creates one simulated v2 node (`định kì`, text_folded `dinh ki`) and confirms that before backfill the phrase `định kì` does not match; after backfill it matches `phrase_folded` (it is not tagged `exact_phrase`).

### 7.2. Benchmark and planner

- Script `scripts/benchmark_search.py` (generated **FICTIONAL (`HƯ CẤU`)** data: 1,000 administrative documents (văn bản) × 100 nodes = 100,000 nodes, each administrative document has 1 node that contains the phrase; with fake page/span/provenance/category ACL).
- **Do not** set `enable_seqscan=off`; the planner uses the defaults (`enable_seqscan=on`, `random_page_cost=4`, `work_mem=4MB`, JIT on). A real EXPLAIN ANALYZE for the phrase query: execution 66–423 ms depending on the run; the plan contains **`document_nodes_search_word_gin`**; the full plan/config is in `docs/evidence/2026-10-31-search-v1/benchmark/benchmark.md` and `benchmark.json`.
- Results of the last run (10 rounds, Windows dev machine): phrase p50/p95 **243.62 / 324.31 ms**; keyword **255.57 / 268.95 ms**; no result **62.61 ms**. Temporary p95 target of 300 ms: the phrase **exceeds** it by 24.31 ms, and the keyword meets it; the target is finalized only after measurement on the target machine.
- The default API (with an approximate count) takes 338.66 ms thanks to the cap: the hidden approximate count is computed with a ceiling of 500 and is dropped when a phrase tier is present or the main clause count is >200; `/search/approximate` still returns real results when expanded. If expansion always computes the approximate count, the caller must accept a higher cost (previously 42 s at 100k nodes).
- ACL is optimized with `_ALLOWED_DOCUMENTS_SQL` (it reads category_acl/document_acl and does not scan 100k nodes on every request) and a base filter `n.review_status='approved'`; this is an important performance change, and it has been tested that an ACL for a different principal returns 0 results.

### 7.3. Clause pagination and the UI

- The API adds `clause_page`/`clause_page_size` (maximum 50), and each document returns `clause_page`, `clause_page_size`, and `has_more_clauses`; `matched_clause_count` is still the total.
- The UI displays “Hiển thị X/Y khoản” (`Hiển thị X/Y khoản`, "Showing X/Y clauses") and the button “Xem thêm khoản khớp” (`Xem thêm khoản khớp`, "See more matching clauses"); the client accumulates by `node_id` because the API returns an offset window (if the API switches to cumulative, deduplication is still safe).
- The clause page size is fixed at 5 in the UI; the URL keeps `clause_page`, but a reload loads only the current clause page and does not rebuild the buffer of earlier pages (recorded as a limitation).

### 7.4. Additional tests

- Backend: 187 passed with PostgreSQL; 171 passed + 16 skipped when there is no DSN.
- Frontend: 65 tests/14 files; a11y was added (role/aria-live/aria-expanded), WCAG contrast is read from tokens (lowest 5.21:1; `<mark>` 14.26:1), Local Mode (every fetch is `/api/v1`, and `dist` has no external resource), and browser E2E on headless Chrome through CDP with a same-origin API fixture (12 requests, 0 external http(s) origins) — this is not yet a real backend or approved data.
- CI: the workflow sets `EVIDENCE_TEST_DATABASE_URL` from the secret and `CI=true`; `verify.ps1` + `backend/tests/conftest.py` stop if CI is missing a DSN, so that the PG tests are not skipped.

### 7.5. Defaults waiting for the owner to finalize

- `PAGE_TOO_DEEP`: `Bạn đã xem tới giới hạn kết quả. Hãy thu hẹp bằng bộ lọc hoặc dùng từ khóa cụ thể hơn.` ("You have reached the result limit. Narrow it with a filter or use a more specific keyword.") (already applied on the backend and the frontend).
- `doc_type`: a controlled vocabulary managed by the curator; the UI temporarily uses `decree` (Decree (Nghị định)) / `circular` (Circular (Thông tư)) / `decision` (Decision (Quyết định)) / `other`; old free-text data needs to be normalized.
- `exact_phrase_precision`: the numerator over the total number of clauses tagged `exact_phrase` that self-verify; a negative case = 0; a denominator of 0 on a positive case = null (the harness has been fixed, plus a self-test of 27 tests).
- Temporary p95 of 300 ms on 100k generated nodes; finalize it again after the target machine.
- The rate limit is currently correct only for **one process**; multiple workers must move to a shared store.

### 7.6. Remaining work

- A real Gold [Not implemented — see ADR-010], plus approval of administrative documents (văn bản) and provenance; quality has not been measured.
- PDF bbox highlight, OCR, browser E2E with a real backend and approved data, and a CI browser runner.
- A reload with `clause_page>1` does not rebuild the buffer; “xem thêm” (`xem thêm`, "see more") applies only to the current clause window.
