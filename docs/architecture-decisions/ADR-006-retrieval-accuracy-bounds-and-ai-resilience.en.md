**Language / Ngôn ngữ:** [Tiếng Việt](ADR-006-retrieval-accuracy-bounds-and-ai-resilience.md) · English

English counterpart of `docs/architecture-decisions/ADR-006-retrieval-accuracy-bounds-and-ai-resilience.md`. The Vietnamese file is the original.

# ADR-006 — Retrieval accuracy, load limits, and AI fault tolerance

- Date: 2026-11-05
- Status: Implemented
- Partially supersedes: ADR-005 (the “Known limitations” item on the 5,000 cap, legacy chat with no timeout, and totals always being exact); ADR-004 (model timeout).
- Evidence: `docs/evidence/2026-11-05-retrieval-accuracy-performance/REPORT.md`

## 1. Context

The review of 2026-11-05 reproduced the following: chat picked the wrong administrative document (văn bản) when the question used a document number, failed to find a diacritic-free query and Vietnamese uppercase, and could cite a version that had already been replaced (thay thế); chat retrieval took 1.9–6.8 s on 100,000 nodes and had no concurrency limit; Search v1 with a common word ran for about 30 s; an AI model that had stopped working made every chat turn wait out the timeout.

## 2. Decision

### 2.1. Evidence (căn cứ) retrieval for chat (`PostgresAuthorizedNodeSearch`)

- Choose the version the way Search v1 does: each permitted administrative document (văn bản) contributes the latest `approved` version that is still in effect (hiệu lực) at `as_of_date` and has verified provenance; category scope and document type are filtered at this step.
- Candidates are taken per channel, at most 1,500 clauses (Khoản) per channel: document number (a normalized key, as in Search v1), Article (Điều) N, all keywords (the diacritic index and the diacritic-folded index), and the title. The “one of the words” channel and the legacy-record label channel run only when the channels above are short of results.
- The expensive part (tsvector, score, span/page check, effectivity) runs only on the candidate set.
- Order: document-number + Article match, document number, Article, all words, all words with the correct diacritics, `ts_rank_cd` score.
- Keywords drop the “Điều/khoản/điểm N” portion (“Article/clause/point N”) and the document number once those parts already have their own channel.
- At most 4 concurrent DB retrievals per process (they wait; they are not rejected); they share `EVIDENCE_SEARCH_STATEMENT_TIMEOUT_MS`; on expiry the response is an SSE `turn_error` with code `QUERY_TIMEOUT`.

### 2.2. Vietnamese uppercase under locale `C`

PostgreSQL `lower()`/`to_tsvector('simple')` lowercases only ASCII when the database uses locale `C`. The query lowercases with the `pg_c_utf8` collation (PostgreSQL 17+, detected at runtime); if that collation is absent, it uses `translate` with the Vietnamese uppercase table. The “Điều N” pattern (“Article N”) uses the character class `[ĐđÐ][Ii][Ềề][Uu]`.

### 2.3. A stable query plan

- The list of permitted versions is computed in a separate statement and then passed as an array into the page query; the old join was misestimated by the planner and scanned again for every node.
- Every search and chat transaction sets `plan_cache_mode = force_custom_plan`: asyncpg uses prepared statements, and a generic plan ignores the parameter values and can scan the whole table.
- Do not add a b-tree on `document_nodes(document_version_id)`: it was tried; the planner used it instead of the GIN index and a query with no results slowed from about 15 ms to about 2.8 s.

### 2.4. Count limit on the search page (the owner set N = 8,000)

- `EVIDENCE_SEARCH_COUNT_CAP` (default 8,000, allowed range 500–100,000) is the maximum number of clauses (Khoản) that are source-checked, scored, and counted for one search.
- Under the threshold: the total and the order are exact, as before. Over the threshold: `totals.capped = true`, `totals.clauses = N`, and results are ranked within the first N clauses found; the interface shows “hơn N khoản” (“more than N clauses”), pagination does not state a total page count, and the clause count of each administrative document (văn bản) shows “ít nhất” (“at least”).
- Once the threshold is passed, do not return `PHRASE_NOT_FOUND`, because the exact phrase may sit in the part not yet examined.
- The `search.query` audit records `capped`, so N can be adjusted from real data (target: about 95% of real search queries are counted in full).
- Basis for choosing N: the time budget (measured on the dev machine: 5,000 ≈ 0.8 s, 10,000 ≈ 1.6 s) and the share of queries that get cut off; measure again on the target Windows machine.

### 2.5. Evidence (căn cứ) that is no longer in effect (the owner chose option C)

Evidence with `repealed`/`suspended`/`not_yet_effective`:

- blocks the whole conclusion when it is the top-ranked evidence, or when it matches the Article (Điều) plus the document number the user asked for by name;
- in every other case it is only removed from the conclusion and the suggestions, and it still appears as an evidence card with an effectivity (hiệu lực) label; the result is at most “có điều kiện” (“conditional”); the “Lưu ý khi áp dụng thực tế” (“Notes for practical application”) section names the evidence that was removed.

### 2.6. The AI chooses evidence (căn cứ) (API and Local)

- The connection to the model is at most 5 s (`connect`); the read still follows `EVIDENCE_AI_TIMEOUT_SECONDS`.
- A model profile that cannot connect, that times out, or that is cancelled because it exceeded the evidence-selection budget is skipped for 60 s on later turns (stored in the process RAM). A successful “Kiểm tra kết nối” (Check connection) in the Admin Portal clears this state immediately.
- The prompt sends only the first 8 evidence items (the same number that may be used for the conclusion), each cut to at most 1,200 characters, so a model running on CPU still fits the budget.

### 2.7. Re-check evidence (căn cứ) after every turn

The ACL and provenance of the evidence items are checked with one query per `as_of_date`; the PDF is hashed in 1 MB blocks and skipped when the size, mtime, and ctime are unchanged since the previous match. Opening the PDF for the user still hashes the whole file. If the re-check times out, the response is `QUERY_TIMEOUT`, not `CITATION_INVALID`.

## 3. Consequences

- Migrations, ACL rules, and the original source evidence do not change. The API adds `totals.capped` and `totals.count_cap` (OpenAPI has been updated).
- A very broad query on the search page is ranked within the first N clauses (Khoản), not across the whole corpus.
- Chat with a very broad query is ranked within at most 1,500 candidates per channel.
- The concurrency limit and the temporary model-skip state are per process; several workers need a shared store.

## 4. Follow-up (proposed)

Store the lowercased tsvector at ingest (this cuts the scoring cost and fixes uppercase on the diacritic channel of Search v1), cache result order per page, add a score for a run of adjacent syllables, a dictionary of legal abbreviations, an embedding channel once a model is available, and Gold [Not implemented — see ADR-010]. Details are in the report of 2026-11-05.
