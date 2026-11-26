**Language / Ngôn ngữ:** [Tiếng Việt](implementation-status.md) · English

English counterpart of `docs/implementation-status.md`. The Vietnamese file is the original.

# Implementation status

> **[Not implemented — see ADR-010]** Every passage in this document about the Gold question set, trap set, calibration and held-out is not implemented, per [ADR-010](architecture-decisions/ADR-010-khong-trien-khai-bo-cau-hoi-gold.md). The rest remains unchanged.

Updated 2026-11-11. This document records only the **current** status; the course of each round is in the reports under “History”. Do not treat the application as having passed acceptance: no business administrative document (văn bản) has been approved, and there is no Gold [Not implemented — see ADR-010]; real models have so far only been tried on a temporary database (G1–G5).

## Two-pane Q&A and the Portable r4 package (2026-11-11)

- The Q&A screen is split into two panes: the current session's question-and-answer history on the left, and the answer and evidence (căn cứ) on the right. The evidence list computes how many cards fit the pane height and recomputes when the size changes; click `[n]` in the answer to scroll to the matching evidence and mark that card.
- Article (Điều)/Clause (Khoản)/Point (Điểm)-level effectivity (hiệu lực) relations support replace (thay thế), amend (sửa đổi), supplement (bổ sung) and repeal (bãi bỏ); an authorized officer approves proposals and confirms a separate application date. Lookup can choose a date in order to see the status at that time. The effectivity date of a replace relation may be moved earlier; a yellow warning note states that the node-level status has not been verified, or that the query date is past the data date.
- The current Windows LAN Portable package: `Evidence-RAG-Portable-20261111-r4.zip`, containing 105 administrative documents and 7,447 vectors. [Download the package](https://drive.google.com/file/d/1C9bSKqt_7Rwuqe5NqtTZNzhABVqd7dj6/view?usp=sharing); SHA-256 `989848708e2c1cd3be0d4a0e8978737bc03201f6c75415a37f2a434806636ed8`.
- The source is described at commit `861fa34`. The G5 figures in the history section below use the old experimental database; they are not the figures of the Portable r4 database.

## Refining proposals and node scope for Article (Điều)/Clause (Khoản)/Point (Điểm)-level effectivity (hiệu lực) (2026-11-11)

- **Distinguish `replace` and `modify`, and preserve `source_path`/`target_path`** (`backend/app/effectivity/extract.py`, `store.py`, `node_paths.py`):
  active and passive sentence patterns that replace (thay thế) a specific unit (`"Điều X thay thế Điều Y"` — "Article X replaces Article Y", `"Thay thế khoản 2 Điều 4 như sau"` — "Replace Clause 2 of Article 4 as follows",
  `"Quy định tại Điều 5 thay thế quy định tại Điều 3"` — "The provision at Article 5 replaces the provision at Article 3", Appendix, Form) create a proposal with `action="replace"`, `scope="node"`,
  keeping both `source_path` and `target_path` in full; it is lowered to `modify` only when the sentence is `thay thế (cụm )từ` (replace the word, or replace the phrase). Two replace proposals
  for the same target from two sources or two different dates are both kept, through a distinguishing key (`|src=...|from=...`).
- **A separate effectivity date for each item**: each amend (sửa đổi)/replace (thay thế)/repeal (bãi bỏ) item prefers to read `"từ ngày D"` ("from date D") in that item's own lead-in
  (ignoring the quotation inside double quotes and the part after `"như sau"` — "as follows"), and only if that is absent uses the whole
  administrative document's (văn bản) `effective_from`; if one item states several different dates, leave `valid_from=None` so the reviewer enters it.
- **Split several targets in the same sentence**: a sentence of the form `"Điều 5 và Điều 6 thay thế Điều 3 và Điều 4"` ("Article 5 and Article 6 replace Article 3 and Article 4") or `"khoản 1 và khoản 2 Điều 4"` ("Clause 1 and Clause 2 of Article 4")
  is split into a separate proposal for each target unit, keeping the source group (`"Điều 5 và Điều 6"` — "Article 5 and Article 6").
- **A partial replace that does not name a specific Article**: a sentence `"Thay thế một phần / một số điều của Thông tư X"` ("Replace part of / some articles of Circular (Thông tư) X") (when the child clauses
  are not yet covered via `covered_by_items`) creates a `replace` draft with `scope="node"` and `target_path=None` (confidence `0.7`,
  key `|partial`); the system blocks approval (`RELATION_TARGET_REQUIRED`) until the reviewer attaches `target_node_id`.
- **`node` scope for `modify` and `repeal_partial`** (`extract.py`, `store.py`, `storage/chat_retrieval.py`, `storage/comprehensive.py`):
  when the sentence clearly names the target Article/Clause/Point (`"Sửa đổi khoản 2 Điều 4 của Thông tư X"` — "Amend Clause 2 of Article 4 of Circular X", `"Bãi bỏ Điều 3 của Thông tư X"` — "Repeal Article 3 of Circular X"), the relation
  carries `scope="node"` and is attached to the target node. After approval, a repealed node receives status `repealed` (`verified`, hidden from
  default search results via `lookup_visibility.py`), and an amended node receives `modified` (`unverified`); relation labels and administrative-document
  groups in comprehensive search and chat still count these node-level relations.
- **Tests**: the backend test suite reaches **312 passed** with PostgreSQL (`277 passed, 35 skipped` when `EVIDENCE_TEST_DATABASE_URL` is not set),
  with unit tests added in `backend/tests/test_effectivity_rules.py` and PostgreSQL integration tests in
  `backend/tests/test_effectivity_node_scope_pg.py`.

## Administrative-document (văn bản) management (2026-11-09)

- The Admin Portal has a filterable paginated list, version detail, metadata/OCR editing,
  reprocessing, submission for review, and lookup-status management according to permission. See the
  [administrative-document management guide](HUONG_DAN_SU_DUNG_VA_CAU_HINH_AI.md#quản-lý-văn-bản).
- Migration `0016` keeps the old data and adds a suspended status, a correction version,
  an OCR log and a counter that invalidates the lookup cache. Tested with PostgreSQL 18.6 and
  pgvector 0.8.7 on fictional data, including an upgrade that preserves the old hash and vectors.
- `verify.ps1` passes 12/12 steps, with backend 295 tests and frontend 94 tests passing.
  Chrome checks the Admin portal at 360, 768 and 1280 px. Retrieval quality has not been measured
  on the home machine's dataset and AI model. Tesseract OCR on real scanned documents has also
  not been verified in this environment.
- Node-level effectivity (hiệu lực) relations affected by a correction are put back on the review
  queue. The API can identify the target node, but the "Hiệu lực" (Effectivity) interface does not yet have a target-node picker.

## AI interpretation and scanned-PDF OCR (2026-11-08)

Report: [evidence/2026-11-08-ai-ocr/REPORT.md](evidence/2026-11-08-ai-ocr/REPORT.md).

- AI interpretation (`synthesis/focus.py`, `focused.py`, `checks.verify_claim`): separates the issue being asked from the
  content; only a clause with enough content and the right issue is interpreted; a “strict” issue (penalty, time limit, authority,
  condition, effectivity (hiệu lực)…) that has no clause is answered “chưa tìm thấy” (not found), and the model is not called. Each point
  passes lexical-check layers (facts, topic, level of support, negation/exception/condition, effectivity,
  duplication); a wrong number, date or Article (Điều) is rejected. The `AiAnswerView` interface shows the answer first and the supporting evidence (căn cứ) after.
- OCR (`documents/ocr.py`, migration `0015`): Tesseract through configuration, per-page diagnostics, and automatic page
  rotation; the reviewer confirms each page before OCR text becomes evidence; the parser does not split a line that wraps
  “Điều N của …” (“Article N of …”) into a new Article. Five real scanned decrees (Nghị định) were tried over HTTP.
- `verify.ps1` 12/12: backend 257 passed, frontend 60 passed. 50 G5 questions: R@toàn bộ (recall over the full set) 0.960 (unchanged).

## USER lookup after the 2026-11-08 review

Report: [evidence/2026-11-08-user-lookup/REPORT.md](evidence/2026-11-08-user-lookup/REPORT.md).

- Q&A runs on the G2 result set (a question that has a document number or an Article (Điều) keeps reference lookup); relevance by
  phrase (`storage/relevance.py`): `direct`, `related`, `weak`; a listing of administrative documents (văn bản) is “chỉ nhắc đến” (only mentioned). The structured answer is written from metadata (`workflow/chat_answer.py`), one card per administrative document,
  with a verbatim excerpt of at most 520 characters that can be expanded. AI interpretation is a separate button (G4, `only_relevant`).
- One “Tìm kiếm văn bản” (Administrative-document search) page on G2 (the “Tìm toàn diện” (Comprehensive search) page was removed); `GET /api/v1/search` is kept for compatibility.
- `GET /api/v1/citations/{id}/original`: the ingested file (PDF, including a scan) or the original Word/TXT file, with an ACL check and a
  SHA-256 check. The interface opens the PDF in a separate tab at the page and downloads Word/TXT in the correct format; the embedded PDF was removed.
- RRF, a by-meaning threshold of 0.8, and rerank off: unchanged. 50 G5 questions: R@toàn bộ (recall over the full set) 0.960 (unchanged), MRR@10
  0.780 → 0.792, NDCG@10 0.589 → 0.629, R@10 0.865 → 0.851–0.865 (variation of the `expand` step).
- `verify.ps1` 12/12: backend 239 passed, frontend 57 passed.

## Implemented components

| Item | Main location | Status |
|---|---|---|
| Authentication, RBAC/ABAC, account lifecycle | `backend/app/auth_acl/`, `admin_services.py`, `api/v1/auth.py`, `admin.py` | scrypt, lock after 5 wrong attempts, forced password change, block self-deletion |
| Categories and ACL | `admin_services.py`, Admin Portal | CRUD, soft delete together with ACL revocation, flag `remote_processing_allowed` |
| PDF intake, deduplication, source review | `documents/`, Admin Portal | Sequential batch intake; a byte-identical duplicate is blocked (409), a content duplicate is warned; `CURATOR`/`REVIEWER` are separated; the administrative-document (văn bản) type is chosen from 7 codes (Law (Luật), Directive (Chỉ thị) and joint Circular (Thông tư liên tịch) were added) |
| Word and TXT intake | `documents/convert.py`, migration `0008` | `.docx`, `.doc` (Word 97–2003, reads tables and paragraphs), `.txt` (UTF-8/UTF-16/cp1258) are rendered as a PDF with a text layer, and the same input yields the same PDF (deduplication still holds). The original file is stored under `sources/` with `source_format` and `source_file_sha256`. There is no OCR for a Word file that contains only images; RTF/HTML whose extension was changed to `.doc` is not supported |
| Bulk intake by directory tree | `scripts/import_official_corpus.py`, `test-data/` | Each directory is one category; dry-run first; a rerun does not ingest duplicates. See `test-data/README.md` |
| Gemini/OpenAI API configuration | `model_registry/runtime.py`, `adapters/openai_compatible.py`, Admin Portal | Endpoints `/v1`, `/v1beta/openai` (Gemini), `/openai/v1`, `/api/v1`; parameters `reasoning_effort`, `token_limit_field` (`max_completion_tokens` for GPT-5.x); quick configuration samples in the form. Gemini/OpenAI have not been trial-called for real (no key) |
| Administrative-document search (Search v1) | `storage/search.py`, `search_paging.py`, Search page | Phrases, keywords, unaccented text, document numbers; pagination inside PostgreSQL; a count limit of 8,000 clauses (ADR-006) |
| Evidence (căn cứ) retrieval for chat | `storage/authorized_search.py` | Bounded candidate channels, version selection by effectivity (hiệu lực), Vietnamese capitals, 4 concurrent DB round-trips, `statement_timeout` |
| Fixed pipeline | `workflow/fixed_pipeline.py` | Analyze → Retrieve → Validate → Explain; effectivity rules, option C (ADR-006) |
| AI selection of evidence (API/Local) | `model_registry/`, `workflow/ai_selection.py` | Registry/Router in the database, egress policy, a send count according to the stage policy (default 2, ADR-007), Hybrid Auto, a cost ceiling, temporarily skip a failing model for 60 s, connection timeout of at most 5 s |
| Session memory and SSE | `memory/service.py`, `main.py`, `EvidenceChat.tsx` | RAM only, a size limit, stop/retry/delete each item |
| Citations and the original PDF | `storage/citations.py`, `documents/provenance.py`, `PdfViewer.tsx` | Re-check ACL, provenance, span and SHA-256 on open |
| Hash-chain audit log | `audit.py` | `pg_advisory_xact_lock`; the chain check runs outside the event loop |
| Windows desktop (Tauri 2) | `src-tauri/` | A floating orb, drag across multi-monitor/DPI work areas, system tray |

Architecture decisions: `docs/architecture-decisions/ADR-000` … `ADR-009`. Search
and chat operation: `docs/search-v1-runbook.md`.

## Latest verification (2026-11-06)

- After Word/TXT and the Gemini configuration were added: `verify.ps1` passes 12/12 (backend **193 passed** with
  real PostgreSQL, frontend **73 passed**, `ruff`/`mypy` clean, 8 migration pairs, OpenAPI updated).
- The converter ran on 242 real `.doc`/`.docx` files without error (2 `.doc` files that were actually HTML were rejected
  clearly); text extracted from `.doc` matches Word's own export at 99.9% (3 comparison files); no
  old character-encoding files (TCVN3/VNI) were found.
- Real HTTP (uvicorn, temporary DB): preview and create a draft from `.docx`, `.doc` and `.txt`; the correct rejections
  (`INVALID_PDF_MAGIC`, `UNSUPPORTED_FILE_TYPE`, `DOCUMENT_TEXT_EMPTY`, `TXT_ENCODING_UNSUPPORTED`); re-ingesting
  the same file is blocked with `DUPLICATE_PDF_HASH` across two different processes; a TXT file is approved, found through search,
  and the citation PDF opens correctly.

## Verification on 2026-11-05

- Backend: **193 passed** with real PostgreSQL 18.6 (temporary schema), with no skips; `ruff`,
  `mypy`, the OpenAPI check and the migration pairs (7) pass.
- Frontend: **73 passed** (14 files), `eslint` with 0 warnings, `vite build` passes.
- Real HTTP through uvicorn (temporary schema, “HƯ CẤU” (FICTIONAL) data): login, search, SSE, 35 consecutive
  chat turns, 20 concurrent health checks, and logout revokes the token; no errors.
- Interface: Chrome headless screenshots with the real backend — Q&A at 1024/1366/1920 px, search
  at 1024/1366 px, and the Admin Portal tabs at 1366 px; no horizontal overflow and no console errors.
- Ready-to-run package (`scripts/package-portable.ps1`, 2026-11-06): a self-contained, clean directory, copied to
  another machine and run with `start.cmd`; the detail and the verification scope are in `deploy/windows/README.md`.
- LAN mode (`start-local-stack.ps1 -Lan`, 2026-11-06): the backend serves the web build on the same
  origin and listens on `0.0.0.0`. Checked through the dev machine's own LAN IP: the page renders in full (Chrome
  headless), hashed-name assets are cached, login/categories/search/logout pass,
  a path that escapes the directory returns 404, and PostgreSQL is not reachable through the LAN IP. **Not yet checked
  from another machine** (the firewall was not opened, because administrator rights are required).
- Native Rust: 17 tests pass; the release build was made again on 2026-11-05 (embedding the new web build) at
  `E:\Programs\EvidenceRAG\cache\cargo-target\release\vietnamese-evidence-desktop.exe`,
  and the “Evidence RAG” window opens. An NSIS installer has not been created or signed.

Technical measurements (“HƯ CẤU” (FICTIONAL), 100,000 nodes, dev machine): chat retrieval 0.15–0.35 s; a narrow keyword
search about 0.1 s; no results in 15–40 ms; a word present in 99% of clauses takes 1.1–1.3 s (the count
limit was reached). These are not figures from the target Windows machine, and they are not business-quality figures.

## G0: the Article (Điều)/Clause (Khoản)/Point (Điểm) tree and multi-page anchors (2026-11-07)

The design is locked: [thiet-ke-tra-cuu-hieu-luc.md](thiet-ke-tra-cuu-hieu-luc.md) (G0 → G5).

- A clause that spans pages is anchored to several source spans, one span per page, in reading order
  (`node_source_spans`, migration `0009`); the quotation still matches the PDF character by character. Approving an administrative document (văn bản) and
  opening a citation check every span (`node_source_text_valid`); the search path checks the first span.
- A repeated line (for example `"Điều 5"` — "Article 5") is placed according to reading order when it continues the previous clause; if it does not
  continue, it is accepted only when it is unique on the page.
- Records parent_id (Chapter → Section → Article → Clause → Point), page_end, a structured path and
  citation_label (`"Điểm a khoản 2 Điều 5"` — "Point a, Clause 2, Article 5"); this label appears on the evidence (căn cứ) card, in search results and in citations.
- A clause longer than 4,000 characters is split into `"(phần N)"` ("(part N)") so that one Q&A turn does not exceed the session-memory limit.
- A page whose text layer is almost unaccented (poor OCR from the scanner) creates a review task
  page_N_text_layer_suspect; it does not block approval.
- The character limit per administrative document becomes the setting EVIDENCE_MAX_DOCUMENT_CHARACTERS (default 2,000,000);
  the PDF-reading process no longer sends character boxes back (lower memory).
- scripts/rebuild_node_tree.py: rebuilds the tree for drafts and for versions awaiting review (a dry run, then --apply);
  old data that did not store page text is read again from the original PDF. Approved versions are not touched.

Verification: backend **193 passed** (real PostgreSQL, including rolling all 9 migrations down and then up again),
ruff/mypy clean. 293 trial administrative documents were ingested and reviewed into a temporary DB: **286 could be approved** (before G0: 14),
0 clauses that could not be anchored out of 21,724 clauses, 2,553 multi-page clauses, and the longest clause is 4,486 characters. 7 administrative
documents could not be approved because they have a page that needs OCR (DOCUMENT_TEXT_NOT_READY), which matches the rule. Real HTTP: a search
for a phrase that sits on the second page of a clause correctly returns `"Khoản 1 Điều 1"` ("Clause 1 of Article 1") (page 4); opening the citation returns the full
two-page quotation and the PDF; a Q&A turn runs normally. Dev DB: 12 old versions were read again from the PDF,
and 648 clauses that could not be anchored are now 0 (a backup was made first at .agents/backup-2026-11-07-g0/).

Not done in G0 (by design, belonging to G1 onward): effectivity (hiệu lực), administrative-document groups, search by meaning, synthesis.

## G1.0: model-call policy, Hybrid Auto, cost ceiling (2026-11-07)

Decision: [ADR-007](architecture-decisions/ADR-007-stage-policy-hybrid-auto.md) (replaces "at most 2 LLM calls").

- Migration `0010_ai_policy`: `stage_policies` (send count 1–10, output tokens, timeout, concurrency by
  mode and stage), `stage_routes.escalation_profile_id`, price and a daily/monthly cost ceiling on the profile,
  `ai_usage_events` (content is not stored). If a policy is missing, `LLM_ATTEMPT_BUDGET` is still used (default 2).
- `LOCAL` = Local Only: a LOCAL route does not accept an escalation profile; the runtime does not read it; a `public` profile is rejected.
- `API` = Hybrid Auto: the primary route may be a local model; an escalation profile (`public`) is only for `answer`/`summarize`,
  called once when the local run has finished and no result passes the application's checks, or called before the user
  turns on "Phân tích sâu" (Deep analysis). If there is no evidence (căn cứ), the model is not called. All egress conditions of ADR-004 are kept.
- When the cost ceiling is reached: that profile is not called, the result falls back to the verbatim text, and the response includes `ai_limited`.
  The response includes `external_ai_used`; the interface shows "Đã dùng API ngoài cho lượt này." (An external API was used for this turn.)
- Admin Portal: an escalation-profile field (API mode only), model-call limits by stage, the profile's price and cost ceiling,
  and daily/monthly usage. New API `POST /api/v1/admin/model-registry/policies`.

Verification: `verify.ps1` passes 12/12 (backend **206 passed** with real PostgreSQL, including
`test_ai_policy.py` and checks of the escalation route, the policy and the cost ceiling on the DB; frontend **74 passed**,
`ruff`/`mypy`/`eslint` clean, 10 migration pairs, OpenAPI updated). Real HTTP (temporary schema, “HƯ CẤU” (FICTIONAL) data):
search, SSE, 5 consecutive chat turns, 20 concurrent health checks, logout revokes the token, and there are no errors
(`docs/evidence/2026-11-07-g1-0/http-smoke.json`). A real model has not been called (no API key, and no local model yet).

After G4, every stage of the Registry is called by the application (see G1–G4 below).

## G1–G5: effectivity (hiệu lực), comprehensive search, content groups, synthesis, coverage (2026-11-07)

Decisions: [ADR-008](architecture-decisions/ADR-008-effectivity-two-axes.md) (two-axis effectivity,
G1, G3), [ADR-009](architecture-decisions/ADR-009-comprehensive-search-synthesis.md) (G2, G4, G5).
New migrations `0011_effectivity`, `0012_comprehensive_search`, `0013_content_groups` (each has `.down.sql`).

**G1 — administrative-document-level (văn bản) effectivity** (`backend/app/effectivity/`, `api/v1/effectivity.py`, the "Hiệu lực" (Effectivity)
tab in the Admin Portal). Tables `document_effective_intervals`, `effectivity_attestations`; column
`verification_state`; `node_amendments`/`node_references` extended; `category_acl.can_review` (the
"Danh mục được xác nhận hiệu lực" (Categories authorized to confirm effectivity) box when editing a REVIEWER account). Issue date, effectivity date and issuing
body are read by rules when a draft is created, shown on the source-review screen, and confirmed at the same time as approval (editable through
`publication_date`, `effective_from`). Source approval reads relations by itself (replace (thay thế), full or partial repeal (bãi bỏ),
amend (sửa đổi), catalogues of expired effectivity, the opening of a Consolidated administrative document), matches document numbers, rematches a target that is "not yet in the
store", and publishes a snapshot. The batch review queue is grouped by the source administrative document; each relation is one audit record
sharing the batch code; the proposer does not approve their own proposal. An attestation of "còn hiệu lực" (still in effect) asserts only up to
the verification date; a new relation that touches the target moves it to "cần xác minh lại" (needs re-verification) (trigger). Search, evidence (căn cứ) cards and
Q&A have an `effectivity` field (two axes, a note, the person and time of verification, the data date); search has
`clause_level_warning` and `data_date`. Q&A is not blocked when verification is still missing, and it carries a note (D12).
Script: `scripts/extract_effectivity.py` (a rerun does not add duplicates). The AI `relation`
stage (`POST /api/v1/admin/effectivity/ai-proposals`) proposes only for sentences the rules cannot read; the document number
must appear verbatim in the sentence.

**G2 — comprehensive search** (`storage/comprehensive.py`, `storage/embeddings.py`, the "Tìm toàn diện" (Comprehensive search) page).
`POST /api/v1/search/comprehensive` + `GET …/{result_set_id}`: four channels (exact, by meaning, concept,
relation) merged by RRF, a fixed result set in RAM, pagination that reads permissions again, batch rerank by a
local LLM, an honest search scope, three D9 groups, status and verification filters over the whole set, and administrative-document groups.
The concept dictionary `concept_terms` (a proposal → approved by someone else). Vectors are not fixed at 768 dimensions; an HNSW index
follows the model dimension; `scripts/build_embeddings.py` (it can resume, and `--rebuild` when the model changes). Settings:
`EVIDENCE_SEMANTIC_TOP_N` (200), `EVIDENCE_SEMANTIC_RELATIVE_THRESHOLD` (0.8), `EVIDENCE_RERANK_TOP_N`
(40), `EVIDENCE_RERANK_BATCH_SIZE` (10), `EVIDENCE_RESULT_SET_TTL_SECONDS` (1800),
`EVIDENCE_CONCEPT_MIN_TERMS` (1). Rerank is never sent to a `public` profile; an embedding is sent only when a
separate policy is on (see "Embedding management" below).

**Embedding management in the Admin Portal (2026-11-07)** (`storage/embedding_jobs.py`, `storage/embeddings.py`,
`components/EmbeddingManager.tsx`, migration `0014_embedding_jobs` with `.down.sql`; report
[evidence/2026-11-07-embedding-admin/REPORT.md](evidence/2026-11-07-embedding-admin/REPORT.md)).
A model profile has a separate "embedding" role (an optional required dimension count). The "Embedding" item: check the model (connection,
whether the model is present on the service, a trial vector, the dimension count, storage as `vector` ≤ 2000 / `halfvec` ≤ 4000, the data policy), count
the nodes that need to be created, confirm, then queue a background task in the API process (`EVIDENCE_EMBEDDING_WORKER`, on by default):
progress, speed, time remaining and errors; pause/resume/retry/cancel; retry with backoff and a smaller batch; a task
that loses its process is continued after about 60 seconds. Search by meaning always uses the profile of the index that is in use; a new index
builds HNSW `CONCURRENTLY`, is checked (enough nodes, the correct dimension, a valid HNSW, one sample vector rebuilt) and then switched inside
one transaction; on failure the old index is kept. Index states: in use, creating, paused, error, completed,
replaced; vectors and indexes are not deleted automatically; switching back to an old model reuses the vectors already stored. Embedding through an external API happens only when
the mode is API, `EVIDENCE_REMOTE_PROCESSING_ALLOWED` and `EVIDENCE_REMOTE_EMBEDDING_ALLOWED` are both on, every administrative document
is allowed to be processed remotely, and (when searching) the user is allowed external AI. `scripts/build_embeddings.py` shares these steps.

**G3 — Article (Điều)/Clause (Khoản)/Point (Điểm) level.** Reads `"Sửa đổi/Bổ sung/Bãi bỏ/Thay thế cụm từ … khoản X Điều Y như sau"` ("Amend/Supplement/Repeal/Replace the phrase … Clause X Article Y as follows"),
matches the target against the G0 tree (parent_id); a separate Article-level effectivity date (`"Điều 2 của Thông tư này có hiệu lực từ …"` — "Article 2 of this Circular (Thông tư) takes effect from …"); a node-level exception is recorded for the whole subtree; the clause-level review level is computed automatically; the general
warning and the note `"chưa xác định khoản này có bị ảnh hưởng"` ("it has not been determined whether this clause is affected") remove themselves when the data is sufficient.

**G4 — content groups and synthesis** (`backend/app/synthesis/`, `api/v1/synthesis.py`, the "Tổng hợp
theo nhóm" (Synthesize by group) frame under comprehensive-search results, and the label-review frame in the "Hiệu lực" (Effectivity) tab). 11 initial groups and 27
phrase rules in the database; AI labels are assigned lazily at synthesis time and approved in batches. Synthesis by group and by batch stays within
the administrator's ceiling (`/api/v1/admin/synthesis-settings`), and reports "Đã tổng hợp N trong M căn cứ, K nhóm còn lại" ("Synthesized N of M evidence items, K groups remaining"), with the buttons "Tổng hợp tiếp" (Continue synthesizing), "Mở rộng phạm vi" (Widen the scope) and "Phân tích sâu" (Deep analysis). Three layers, "Nguyên văn" (Verbatim) / "Diễn giải" (Interpretation) / "Gợi ý" (Suggestion);
every AI point passes a check written in code (evidence code, numbers, dates, document numbers, Article/Clause, business-conclusion words).

**G5 — quality** (`evaluation/coverage/`): 8 topics, 24 ways of asking, 42 required evidence items; measured by
channel; G3 relations are measured; tools to change the model and recompute vectors. A dedicated rerank was added on 2026-11-07 at the level
**experimental, off by default** (see the section below).

**G5 addendum — a trial of Qwen3-Reranker-0.6B on CPU** (`docs/evidence/2026-11-07-g5-rerank/REPORT.md`, 100 trial files,
the same 24 questions and 42 required evidence items, not yet confirmed by an officer). Settings: `EVIDENCE_RERANK_BACKEND`
(`llm` by default, or `cross_encoder`), `EVIDENCE_CROSS_ENCODER_URL` (loopback only),
`EVIDENCE_CROSS_ENCODER_TIMEOUT_SECONDS` (120), `EVIDENCE_CROSS_ENCODER_INSTRUCTION`. Service:
`scripts/local_reranker_server.py` (its own venv, and no package is added to the application venv). Results: pure RRF
Recall@10 0.762, MRR@10 0.674, NDCG@10 0.554, 2.5 seconds; the current LLM rerank 0.691 / 0.729 / 0.549, 47.7 seconds,
Ollama 11.2 GB; Qwen3-Reranker 0.810 / 0.713 / 0.536, 32.3 seconds, with the rerank service peaking at 4.8 GB. Every
MRR/NDCG difference from RRF has a 95% confidence interval that contains 0. The default was not changed. Two evidence items were not found
(58/2026 Article 11, 96/2026 Article 3); that is a candidate-retrieval failure caused by the by-meaning channel threshold of 0.8; lowering it to 0.6
brings 42/42 evidence items into the candidate pool, but they rank outside the top 40, and neither reranker brings them into the top 10.
The interface does not send `rerank`; previously the API defaulted to `true`.

**G5 addendum 2 — pure RRF by default, 50 questions, and the 100-file data kept long-term** (`docs/evidence/2026-11-07-g5-rerank/REPORT-50-cau.md`,
`DATA-INVENTORY.md`). `rerank` of "Tìm toàn diện" (Comprehensive search) accepts `true`/`false`/absent; when it is absent, `EVIDENCE_RERANK_DEFAULT` is used (default `false`):
the practical default is pure RRF, while LLM rerank (`EVIDENCE_RERANK_BACKEND=llm`) and Qwen3-Reranker (`cross_encoder`) remain options, and both were checked
to still run when `rerank:true`. The by-meaning threshold stays at 0.8 (`EVIDENCE_SEMANTIC_RELATIVE_THRESHOLD`; 0.6 is only for a trial). The test set has 17 topics, 50 questions
and 74 pairs (26 new questions drafted from the administrative documents, not yet confirmed for business use). Pure RRF on the 50 questions: Recall@10/20/50/toàn bộ (full set) 0.865/0.892/0.932/0.960,
MRR@10 0.790, NDCG@10 0.594, median 2.2 seconds. The old G5 experimental DB `evidence_rerank_eval` (100 administrative documents, 7,230 vectors; this is not the Portable r4 DB) was rebuilt once (embedding took 42 minutes),
backed up immediately with `pg_dump -Fc` (37 MB), and a trial restore succeeded (`scripts/verify_db_restore.py`: row counts, administrative-document and vector checksums, 98 indexes,
and HNSW all match). The DB, the document store, the models and the backup copies were not deleted. Regression `verify.ps1` 12/12 (backend 218, frontend 74).

**G5 addendum 3 — a stable tie-break key** (`docs/evidence/2026-11-07-g5-rerank/REPORT-tiebreak.md`). When two clauses have an equal score, the UUID is replaced by a key
(administrative-document number, file SHA-256, clause position by the `path` prefix) in `_rrf`, the exact channel (`candidates_sql`) and the relation channel; the RRF formula, the channels,
the thresholds and the embeddings are unchanged. Two databases imported independently from the same 100 files: the order is identical on 50/50 questions (previously 45/50 for the exact channel, and 41/50 when relations were added).
Recall@10/20/toàn bộ (full set) of the 50 questions is unchanged (0.865/0.892/0.960). Regression `verify.ps1` 12/12 (backend 225, frontend 77, including other changes in the code tree).
Not yet checked across two imports: the by-meaning channel (approximate HNSW) and the concept channel (the LLM `expand` step).

### Verification (temporary DB `evidence_scratch`, 293 trial files, 286 administrative documents that could be approved, 20,749 clauses)

- The first rule read: 671 administrative-document-level (văn bản) relation proposals, 293 related relations, 1,557 AI candidate sentences,
  8.6 seconds; the next run added 85 node-level relations. The real chain (HTTP, `docs/evidence/2026-11-07-g1/http-g1.json`,
  27/27 pass): 66/2023 amends 55/2021 and 56/2021 from 2024-01-01; 43/VBHN-BCA is recognized as the consolidation of 55, 66,
  56 and 53/2025; 110/2021 repeals (bãi bỏ) 29/2016 from 2021-11-15 (2021-11-14: "Chưa xác định" (Not determined); 2021-11-15: "Hết hiệu lực, Đã xác minh" (No longer in effect, Verified)); 58/2026 replaces (thay thế) 32/2017 and 36/2017, and 96/2026 replaces 17/2020, from 2026-07-01 (the targets are not yet
  in the store → "chưa có trong kho" (not yet in the store), waiting to be matched again); 28/2024: Article (Điều) 2 from 2024-08-01. There is no interval
  of "Còn hiệu lực + Đã xác minh" (Still in effect + Verified) when an attestation is missing (the count is 0 at both administrative-document level and node level); an attestation
  moves itself to "cần xác minh lại" (needs re-verification); an account without `can_review` sees 0 proposals; a batch of 6 relations = 6 audit
  records.
- G2 (`docs/evidence/2026-11-07-g2/http-g2.json`, 17/17 pass): the 4 channels have results (for example 7 / 62 / 213 / 53),
  pagination of 326 items with no duplicate and no omission, the order is kept, another person opening the result set receives 403, 55 clauses
  come only from the by-meaning channel, 51 clauses come only from the relation channel, turning each channel off measures its contribution, the "Hết hiệu lực" (No longer in effect) group
  counts 92 and is collapsed, "Đối chiếu lịch sử" (Historical comparison) merges one list of 732 items, and rerank covers 40/326.
- G3: 31/31 Article/Clause-level relations in the comparison set (66/2023, 28/2024) were read correctly and matched to the correct node (precision 1.0,
  recall 1.0 — `docs/evidence/2026-11-07-g5/g3-relations.json`); HTTP 11/11 pass: Article 12 (55/2021) is "Hết hiệu lực" (No longer in effect) at node level from 2024; Article 2 (28/2024) is "Chưa có hiệu lực" (Not yet in effect) on 2024-07-15, and inherits the administrative document after
  2024-08-01; the clause-level review level of 55/2021 computes itself as already sufficient, and the partial-amendment note disappears.
- G4 (`docs/evidence/2026-11-07-g4/`): Local Only passes 10/10 (including with "Phân tích sâu" (Deep analysis) on: 0 API calls);
  Hybrid Auto with DeepSeek-V4.1-Flash through `api.river.ai` passes 11/11 (3 calls, 4,103 input tokens, 2,838
  output tokens, an estimate of 0.0046 at the price that was entered; 12/12 points pass the check written in code); when there is no evidence (căn cứ) → 0 model
  calls; "N trong M" (N of M) is correct; "Tổng hợp tiếp" (Continue synthesizing) processes the next batch.
- G5 (`docs/evidence/2026-11-07-g5/coverage.json`): with every channel, 40/42 required evidence items are found (0.952); the exact
  channel alone 0.548; by meaning alone 0.786; concept alone 0.810; the relation channel cannot run on its own (it needs
  an administrative document matched by another channel as the root), so a separate measurement = 0. 7/8 topics are complete for every way of asking; missing: 58/2026 Article 11
  and 96/2026 Article 3, for two ways of asking the detention-rules topic.
- Local models: Ollama runs on its own (`E:\Programs\EvidenceRAG\tools\ollama`, with models at
  `E:\Programs\EvidenceRAG\models\ollama`), `qwen3-embedding:0.6b` (1,024 dimensions, about 2.7 clauses/second on CPU,
  20,749 clauses ≈ 2 hours), `qwen3:1.7b` for rerank/expand/label/relation/summarize; every value lives only
  in the Registry. The API key is placed only in the process environment variable when a trial is run.
- `verify.ps1 -ProgramsRoot E:\Programs` passes 12/12 (`docs/evidence/2026-11-07-g5/verify/`): backend
  **218 passed** with real PostgreSQL (including `test_effectivity_rules.py` for 5 hard rules,
  `test_synthesis_checks.py`, and rolling all 13 migrations down and then up again), frontend **74 passed**,
  ruff/mypy/eslint clean, 13 migration pairs, and OpenAPI updated.

### Not yet verified / limits

- The list of required evidence (căn cứ), the 31 G3 comparison relations and the names of the 11 content groups were compiled by the agent from the administrative documents (văn bản),
  and **have not yet been confirmed by a business officer**; the trial data was approved in bulk.
- Highlighting character-box coordinates (PDF bbox highlight) on the PDF viewer and at gates WP 0.3/1.5: **[Not implemented]** (the viewer opens the correct PDF page together with the verbatim excerpt `quote_exact`; see [pdf-anchor-coordinate-contract.md](pdf-anchor-coordinate-contract.md)).
- `qwen3:1.7b` on CPU answers slowly (some summary turns exceed 30 s, are counted as "unreachable" and are temporarily skipped for 60 s);
  local interpretation quality is lower than the API. It has not been measured on the target Windows machine, and there is no GPU yet.
- The fixed result set and the synthesis state live only in the RAM of one process; several workers need a shared store.
- The new interface (Comprehensive search, Synthesis, the Effectivity tab, labels) was checked only with the existing lint, types and tests and with the
  build; there are no screenshots yet, and there are no dedicated interface tests for these parts.
- The expired-effectivity catalogue (table form) yields proposals at confidence 0.5 with no date attached; the reviewer must fill in the date.
- The dev DB has not had migrations 0011–0013 applied (the application applies them itself on startup; a backup is at
  `.agents/backup-2026-11-08-g1-g5/dev-db-public.dump`).

## Current dev data

- 12 document versions: 9 drafts, 3 awaiting review, **0 approved**, 0 provenance verified,
  797 nodes, all of which could be anchored to a source (the tree was rebuilt on 2026-11-07). Search and chat on the dev DB
  therefore return `NO_AUTHORIZED_DOCUMENTS` — as designed. 9 old drafts have no nodes (the PDF consists only of pages
  that need OCR).
- The dev Model Registry is **empty** (0 providers, 0 profiles, 0 routes). Per the owner's direction
  on 2026-11-05, 20 providers, 10 profiles and 12 old routes were deleted (adapters or stages that are no longer
  supported, and model names that do not really exist); there is an audit event
  `maintenance.delete_legacy_model_registry`, with a backup at
  `.agents/backup-2026-11-05-original/dev-db-model-registry.json`. New model configuration is done through
  Admin Portal → "Mô hình AI & Kiểm toán" (AI models and audit).

## External-dependency gate

1. **Gold [Not implemented — see ADR-010], 150–200 cases, and approved administrative documents (văn bản)**, to be approved by the person who holds the business knowledge — not available yet;
   there are no recall/precision figures yet.
2. **Real models**: tried on a temporary DB with local Ollama (`qwen3-embedding:0.6b`, `qwen3:1.7b`) and
   DeepSeek-V4.1-Flash through `api.river.ai` (the owner's trial key); the dev DB still has no model configured.
   Q&A still quotes the verbatim text (`answer_generated: false`).
3. **Target Windows machine**: measure performance and the count limit again; digitally sign the MSI/NSIS installer.
4. The rate limit, the concurrency limit and the temporary skip-the-model state currently follow **one process**;
   running several workers needs a shared store.

## AI configuration on the Admin Portal (2026-11-08)

The "Mô hình AI & Kiểm toán" (AI models and audit) item contains: **1. Mô hình AI** (1. AI models) (a separate AI Local form and AI API form),
**2. Phân công AI** (2. AI assignment) (assign a model to each function), **Embedding**, and **3. Nhật ký** (3. Log).
Parameters that have a default value, or that the system infers, sit under "Nâng cao" (Advanced).
- Before save or apply there is a check: configuration → key → connection → the model exists → a trial call
  (JSON or an embedding). New endpoints: `POST /api/v1/admin/model-registry/test` (a draft, not saved)
  and `POST /api/v1/admin/model-registry/{profile_id}/test` (a saved profile, which records the status `ready`).
- An API key entered on the form is encrypted with DPAPI (`secret:<tên>` — `secret:<name>`, `EVIDENCE_SECRET_STORE_DIR`)
  and is not shown again. `env:NAME` can still be used. The old `/probe` is unchanged, but the interface does not use it.
- One profile can serve several text-generation functions; `embedding` always stands on its own.
  Old profiles (one function) and saved routes are unchanged.

## Suggested next work

Store a lowercased tsvector at ingest time; cache the result order by page; add a score for adjacent
syllable clusters; a dictionary of legal abbreviations; an embedding channel once a model and Gold [Not implemented — see ADR-010] exist. Detail:
[the 2026-11-05 report](evidence/2026-11-05-retrieval-accuracy-performance/REPORT.md).

## History

| Date | Report |
|---|---|
| 2026-11-08 | [Model Registry interface redesign](evidence/2026-11-08-model-registry-ui/REPORT.md) |
| 2026-11-08 | [AI interpretation and scanned-PDF OCR](evidence/2026-11-08-ai-ocr/) |
| 2026-11-05 | [Accuracy, retrieval time, AI and the interface](evidence/2026-11-05-retrieval-accuracy-performance/REPORT.md) |
| 2026-11-01 | [Review of correctness, completeness and stability](evidence/2026-11-01-app-audit/REPORT.md) |
| 2026-10-31 | [Search v1 implementation](evidence/2026-10-31-search-v1/REPORT.md), [Search review](evidence/2026-10-31-search-review/REPORT.md) |
| 2026-10-27 | [Review of session memory, SSE and models](evidence/2026-10-27-audit/REPORT.md), [content deduplication](evidence/2026-10-27-content-dedup/REPORT.md) |
| 2026-10-22 | [Takeover](evidence/2026-10-22-takeover/REPORT.md), [native desktop](evidence/2026-10-22-desktop-native/REPORT.md) |

Figures in the older reports reflect that point in time; when they differ from this document, this
document is the current version.
