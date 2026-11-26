**Language / Ngôn ngữ:** [Tiếng Việt](REPORT.md) · English

English counterpart of `docs/evidence/2026-11-05-retrieval-accuracy-performance/REPORT.md`. The Vietnamese file is the original.

# Accuracy, completeness, and retrieval-time review — 2026-11-05

Scope: the administrative document (văn bản) search backend (Search v1), evidence (căn cứ)
retrieval for chat, re-checking evidence (căn cứ) after each turn, and the audit log; the
frontend/desktop side was read again for hang risks. Every measurement uses **FICTIONAL (HƯ CẤU)**
data on PostgreSQL 18.6 dev, on the same machine, in a temporary schema (created and then
dropped). This is not business acceptance, and it is not a measurement on the target Windows
machine.

## Confirmed defects and fixes

| # | Defect (reproduced) | Cause | Fix |
|---|---|---|---|
| 1 | Chat selects the wrong administrative document (văn bản) when the question is asked by document number (Article (Điều) 5 of Decree (Nghị định) 15/2020/NĐ-CP (`Điều 5 Nghị định 15/2020/NĐ-CP`), lowercase/without diacritics, or only the document number) | SQL matches `d.document_number = '15/2020/nđ-cp'` (the string is already lowercased), so it never matches `15/2020/NĐ-CP`; a document number with no prefix is not recognized | Use the normalized document-number key shared with Search v1 (`query_document_number_key`, `number_key_sql`) |
| 2 | Chat cannot find a question without diacritics (penalty for a violation (`xu phat vi pham`)) | Chat uses only the diacritic index | Add a folded channel (GIN `text_folded`); rank diacritic-correct results first |
| 3 | Vietnamese uppercase does not match (COMMITTEE (`ỦY BAN`), DECISION (`QUYẾT ĐỊNH`), ARTICLE 2 (`ĐIỀU 2`)) | The DB uses locale `C`: `lower()`/`to_tsvector` lowercase only ASCII (`'Định'` ≠ `'định'`), and `~*` does not fold `Đ/đ` | Lowercase Unicode in SQL (`pg_c_utf8` when available, `translate` when not); the `Điều N` pattern uses the character class `[ĐđÐ][Ii][Ềề][Uu]` |
| 4 | Chat can quote an administrative document (văn bản) version that has already been replaced (thay thế) | Chat does not filter versions by effectivity (hiệu lực) date the way Search v1 does | Select the latest approved version that is still in effectivity (hiệu lực) at `as_of_date` and has verified provenance (same as Search v1) |
| 5 | One clause (Khoản) can appear more than once when several effectivity (hiệu lực) intervals share a date | The effectivity (hiệu lực) `LEFT JOIN` is not bounded | `LATERAL … LIMIT 1`, as in Search v1 |
| 6 | Chat takes 1.8–6.8 s/turn on 100,000 nodes; there is no concurrency limit and no `statement_timeout`, so it can take the whole pool of 10 connections and slow login, search, and opening a PDF | The planner scans every node and computes `to_tsvector` for every row; the title OR channel pulls the whole administrative document (văn bản) into the candidate set | Bounded candidate channels (1,500/channel); the OR channel runs only when the main channel is short; scoring and the span check run only on the candidate set; 4 concurrent DB turns; `statement_timeout`; on expiry return `QUERY_TIMEOUT` instead of `QUERY_FAILED` |
| 7 | Search v1 with a common word: ~30 s of execution (50 s of waiting), always `SEARCH_TIMEOUT` | The `selected_versions` join is scanned again for every node (99,000 times), and the `document_order` window repeats for every clause (Khoản) | Compute the version list in a separate statement and pass an array; limit to one page of administrative documents (văn bản) before joining clauses (Khoản) |
| 8 | After the same statement runs 5 times on one connection, search can slow from ~15 ms to ~2.8 s (reproduced while fixing; not measured enough to confirm that the original code is affected) | asyncpg uses a prepared statement; PostgreSQL can switch to a generic plan that ignores parameter values | `SET LOCAL plan_cache_mode = force_custom_plan` inside the search/chat transaction |
| 9 | Each chat turn reads every PDF in full (≤ 32 MB/file) into RAM in order to hash it again; a 5 s expiry is reported wrongly as `CITATION_INVALID` | The re-check uses `read_immutable_pdf` | Hash in 1 MB blocks; skip when size/mtime/ctime are unchanged since the previous match; opening a PDF for the user still hashes the whole file again. Expiry returns `QUERY_TIMEOUT`. Check the ACL of the evidence (căn cứ) items with 1 query instead of 12 |
| 10 | Opening the audit log blocks the event loop while re-hashing up to 10,000 events | Hashing runs on the async thread | Move it to `asyncio.to_thread` |

ACL rules, the original evidence content, and migrations are unchanged. The API only adds
`totals.capped` and `totals.count_cap` in round 2 (OpenAPI is already updated).
A b-tree index on `document_nodes(document_version_id)` was tried, but the planner used it
instead of GIN and slowed Search v1 from ~15 ms to ~2.8 s, so it was removed.

## Chat accuracy (8 FICTIONAL (HƯ CẤU) cases, same data)

| Case | Before | After |
|---|---|---|
| What does Article (Điều) 5 of Decree (Nghị định) 15/2020/NĐ-CP provide (`Điều 5 Nghị định 15/2020/NĐ-CP quy định gì`) → the correct Article (Điều) 5 of the correct administrative document (văn bản) | Pass | Pass |
| article 5 of decree 15/2020/nd-cp (`điều 5 nghị định 15/2020/nd-cp`) | Wrong administrative document (văn bản) | Pass |
| Document number only `15/2020/NĐ-CP` → every result belongs to that administrative document (văn bản) | Mixed with other administrative documents (văn bản) | Pass |
| Without diacritics, postal administrative-violation penalties (`xu phat vi pham hanh chinh buu chinh`) | Pass | Pass |
| the provincial People’s Committee is responsible (`ủy ban nhân dân cấp tỉnh chịu trách nhiệm`) (the content is written in uppercase) | Wrong | Pass |
| a decision on decentralization (`quyết định về phân cấp`) (the title is written in uppercase) | Wrong | Pass |
| telecommunications licensing (`cấp phép viễn thông`) (distinguishes `cấp`/`cáp`) | Pass | Pass |
| house and land registration fee (`lệ phí trước bạ nhà đất`) → only the version still in effectivity (hiệu lực) | Mixed with the old version | Pass |

Total: **3/8 → 8/8**. These are defect-check cases built by the person who carried out the
review, not business Gold.

## Timing (100,000 FICTIONAL (HƯ CẤU) nodes, p50, ≥ 5 measurements after warm-up)

| Flow | Before | After |
|---|---:|---:|
| Chat periodic report (`báo cáo định kỳ`) (1,000 matching clauses (Khoản)) | 1,874 ms | 151 ms |
| Chat state management (`quản lý nhà nước`) (99,000 matching clauses (Khoản)) | 4,313 ms | 226–321 ms |
| Chat what does Article (Điều) 1 of Decree (Nghị định) … provide (`Điều 1 Nghị định … quy định gì`) | 6,773 ms | 342 ms |
| Chat what is administrative reform (`cải cách hành chính là gì`) | 3,863 ms | 311 ms |
| Search v1, a narrow keyword (1,000 clauses (Khoản)) | 66 ms | 55–59 ms |
| Search v1 with no results (after ≥ 5 runs) | — | 15 ms |
| Search v1, a keyword present in 99% of nodes | ~30,000 ms execution (timeout) | 3,500–6,500 ms |

24 concurrent chat turns: all of them finished, wall 1.8 s, the largest event-loop gap was
36 ms, slots returned to 4/4, and the DB was still responding. Real HTTP (uvicorn): 35 chat
turns in a row with no errors, the longest 26 ms, and the server was still up.

## Verification

- Backend: **193 passed** with real PostgreSQL (nothing skipped); `ruff`, `mypy`
  (`backend/pyproject.toml`), `export_openapi.py --check`, and `validate_migrations.py` passed.
- 1 test was updated (`test_replay_rechecks_current_acl`) because evidence (căn cứ) re-checking
  now calls `get_authorized_citations` (by batch).
- Frontend: 73 passed; lint/build passed after the UI changes (the “Đợt 2” (Round 2) section).
- Rust: the code is unchanged; 17 tests passed; the release build was rebuilt so it embeds the
  new web bundle.

## Remaining limits

- Search v1: a very broad query now stops at the count limit of 8,000 clauses (Khoản) (about
  1.1–1.3 s on the dev machine) and ranks inside the portion that was examined; ranking the
  whole corpus and staying fast requires P1-1.
- Chat: for an overly broad query, each channel takes at most 1,500 candidates and only then
  ranks, so the order inside the “khớp đủ từ” (all words matched) group may not be the absolute
  best. A document number/Article (Điều) is always preferred.
- The dev DB still has 0 approved administrative documents (văn bản) and 0 verified provenance;
  there is no Gold yet, so there are no business recall/precision figures.

## Upgrade options

Ordered by value/risk. Items that need an owner decision are stated as such.

### P1 — search time

1. **Store tsvector in advance**: add generated columns `search_tsv` and `search_tsv_folded`
   (Unicode lowercasing at ingest) and GIN on those columns; SQL uses the columns instead of
   calling `to_tsvector` for each row. The estimate (not measured) is that a query hitting 99%
   of nodes goes from ~4–6 s down to ~1 s, and this also fixes the uppercase defect on Search
   v1’s diacritic channel. It needs a migration plus reindex, and an update to ADR-005 (which
   currently requires an expression index).
2. **Cache result order by page**: each “trang sau/xem thêm khoản” (next page/see more clauses)
   currently recomputes the whole candidate set. Cache the list of administrative document
   (văn bản) ids by (user, query, filters, normalized revision/ACL) for 60 s.
3. **Totals for an overly broad query** — *the owner chose option B with N = 8,000, implemented
   on 2026-11-05* (the “Đợt 2” (Round 2) section).
4. **A shared admission/rate limit** (PostgreSQL/Redis) before running multiple workers.

### P2 — accuracy

5. **Syllable phrases**: a Vietnamese word has several syllables (`quản lý`, `nhà nước`); the
   `simple` analyzer splits each syllable. Add score for an adjacent syllable pair
   (`quản <-> lý`), or segment Vietnamese words at ingest.
6. **A dictionary of legal abbreviations and synonyms**: `UBND`↔`Ủy ban nhân dân`,
   `NĐ`↔`Nghị định`, `TT`, `QĐ`, `HĐND`… controlled query expansion, managed by the curator.
7. **Hybrid retrieval**: the schema already has `embedding_indices`/`node_embeddings`
   (pgvector). Add an embedding channel (a local model through Model Registry), merge it with
   lexical by RRF, and rerank the top 50. Turn it on only when a model exists and Gold shows
   that it is better.
8. **Effectivity (hiệu lực) in the pipeline** — *the owner chose option C, implemented on
   2026-11-05*: stop the whole conclusion only when the top-ranked evidence (căn cứ), or
   evidence (căn cứ) that matches an Article (Điều) plus a document number asked for by name,
   has been repealed (bãi bỏ), temporarily suspended, or is not yet in effectivity (hiệu lực).
   In every other case, remove only that evidence (căn cứ) from the conclusion and the
   suggestions; the result is at most “có điều kiện” (conditional), with a note that names the
   evidence (căn cứ) that was removed (the “Lưu ý khi áp dụng thực tế” (Notes for applying in
   practice) section). The API is unchanged.
9. **Evaluation with Gold**: extend `evaluate_search.py` to chat retrieval (recall@k, MRR, and
   the rate of a correct document number/Article (Điều)) so weights are adjusted from figures
   rather than from impression.

### P3 — operations

10. Record the time of each step (ACL, version, candidates, ranking, span check) and turn on
    `pg_stat_statements` and the slow-query log.
11. `ANALYZE` after every large ingest or approval batch so the planner has correct statistics.
12. Ingest stores `text_indexed` already normalized to NFC and lowercased (with a backfill), so
    every channel matches uppercase without lowercasing at query time.

## Run again

```text
$env:EVIDENCE_TEST_DATABASE_URL = "<DSN disposable>"
python -m pytest backend/tests -q
python scripts/smoke_app_runtime.py --output <dir> --soak-turns 35
python scripts/benchmark_search.py --documents 1000 --nodes-per-document 100 --output <dir>
```

The originals of the files that were edited are in `.agents/backup-2026-11-05-original/` (they
are not part of the release; delete them when there is no further need to restore).

## Round 2 (2026-11-05): count limit, effectivity (hiệu lực), AI, UI, documents

### Owner decisions that are already implemented

- **Count limit N = 8,000** (`EVIDENCE_SEARCH_COUNT_CAP`): below the threshold, the count and
  the ranking are exact; above the threshold the response returns `totals.capped`, the UI
  writes “hơn 8.000 khoản” (more than 8,000 clauses), it does not write a total page count,
  and the clause (Khoản) count of each administrative document (văn bản) writes “ít nhất”
  (at least). The basis for choosing N is the time measured by N (1,000 ≈ 0.16 s; 2,000 ≈
  0.25 s; 5,000 ≈ 0.83 s; 10,000 ≈ 1.6 s; 20,000 ≈ 2.6 s) and the share of clauses (Khoản)
  that contain common words in 3 real administrative documents (văn bản) in the dev DB
  (“quy định” (regulation) 36%, “cơ quan” (agency) 23%, “trách nhiệm” (responsibility) 7%,
  “báo cáo” (report) 3%). The audit records `capped` so N can be adjusted from real data.
- Accompanying fix: the “gần đúng” (approximate) count uses one indexed OR tsquery instead of
  scanning each word across every clause (Khoản) (before: the 5 s wait expired for a query
  with no results on 100,000 nodes; after: about 40 ms).
- **Effectivity (hiệu lực), option C**: see ADR-006 §2.5; 4 situations were tried (the 12th
  clause (Khoản) repealed (bãi bỏ), the first clause (Khoản) repealed (bãi bỏ), the Article
  (Điều) plus document number that was asked temporarily suspended, and an Article (Điều)
  with no document number).

### AI (API and Local)

| Issue | Fix |
|---|---|
| A model that was already `ready` then stopped running: every chat turn waits out the timeout (up to about 30 s) | A profile that cannot be connected, that times out, or that is cancelled for going over budget is skipped for 60 s; a successful connection check clears that immediately |
| A connection to a machine that does not respond uses the whole read timeout | Connection limit of 5 s |
| A prompt of 12 evidence (căn cứ) items × 2,000 characters; a model running on CPU has trouble finishing inside the budget | The first 8 evidence (căn cứ) items (exactly the number used for the conclusion) × 1,200 characters |

Check: an endpoint that cannot be connected → turn 1 tries once, turn 2 sends no request
(0.1 ms), and after a successful “Kiểm tra kết nối” (Check connection) turn 3 calls the model
again. Configuration check: read-only, from the environment; `LOCAL` allows only
loopback/`localhost` and a LAN that has been declared; `API` requires HTTPS, an allowed
domain, and that the user and every source catalog are allowed; fallback stays in the same
data region; each turn sends at most 2 times. No other defect was found in this flow.

As confirmed by the owner, the old Model Registry data of the dev DB (20 providers, 10
profiles, 12 routes) was deleted in one transaction that writes an audit record; the JSON
backup is in the backup directory.

### UI

Chrome headless captures with the real backend (FICTIONAL (HƯ CẤU) data) at 1024/1366/1920 px:

| Issue | Fix |
|---|---|
| Fact cards (document number, articles and clauses) in the 1024 px column broke into vertical text, one character per line | Full-width cards, with sensible wrapping |
| Technical codes were shown: “Trạng thái lượt tra cứu: conditional” (Lookup-turn status: conditional), “source_verified=passed”, “Trạng thái claim: …” (Claim status: …), “Kết nối: unknown” (Connection: unknown), “Vai trò: answer” (Role: answer) | Vietnamese labels |
| Before any question was asked it already reported “Chưa tìm thấy tài liệu được phép truy cập” (No document the user is allowed to access was found) | “Chưa có căn cứ — nhập câu hỏi…” (No evidence (căn cứ) yet — enter a question…); the old message appears only after a lookup |
| Column titles were cut off with “…” | Shorter wording, with the full text in a tooltip |
| Some CSS classes had no rule: the change-password box on the top bar, Admin notices, the account list (name/username/status ran together), the form grid | CSS was added from the tokens already in use |
| “Loại văn bản” (Administrative document (văn bản) type), when loading a PDF, was a free-text field (`decree`), while the search filters use 4 codes | A select list: Nghị định (Decree)/Thông tư (Circular)/Quyết định (Decision)/Văn bản khác (Other administrative document) |

After the fix: no horizontal overflow, and no console errors. The PDF in the screenshots
reports a display error because the fixture is only a minimal PDF used to check the hash; it
is not a UI defect. The sample questions (chat and Orb) were changed to general questions that
do not depend on a specific administrative document (văn bản)
(`frontend/src/samplePrompts.ts`).

### Documents and files that were cleaned up

- Rewrote `README.md`, `00_README.md`, `docs/implementation-status.md`,
  `docs/search-v1-runbook.md`, `backend/app/migrations/README.md`, and
  `configs/ai-runtime.env.example`; added ADR-006; update notes in ADR-005 and SRS §26.8. The
  old README already contained account passwords, had the roles wrong (`curator`/`reviewer`
  had `USER`), and said “bố cục 2 cột” (2-column layout) and “định tuyến 6 giai đoạn”
  (6-stage routing) — those were removed.
- Deleted the copies, in the root directory, of the profile, SRS v1.2.1, ADR-000, and the
  prompt (byte-identical to `docs/`); the SRS v1.3 at the root is an old copy missing §26, so
  it contradicts `docs/SRS_v1.3.md`. The Search v1 plan was moved into `docs/`.
- Deleted temporary and cache files: `.mypy_cache`, `.ruff_cache`, `.pytest_cache`,
  `__pycache__`, `backend-lint-baseline.local`, `ui-server.local` (an old PID), the previous
  session’s old plan under `docs/superpowers/`, and three intermediate benchmark directories
  from the 2026-11-01 round that no report cites.
