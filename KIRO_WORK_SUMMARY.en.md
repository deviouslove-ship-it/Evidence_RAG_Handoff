# KIRO_WORK_SUMMARY — Work Kiro took part in on the Evidence RAG project

**Language / Ngôn ngữ:** [Tiếng Việt](KIRO_WORK_SUMMARY.vi.md) · English

Prepared for the **Kiroween 2026** submission. Written on 2026-11-09 from the Kiro session records still stored on the author's machine, the Git history, the source code and the repository documents, then updated the same day with the project owner's confirmation. All times are Vietnam time (UTC+7). This is an English counterpart of `KIRO_WORK_SUMMARY.vi.md`; if they differ, report it as a defect.

## 0. Owner confirmation and how to read the evidence

**Confirmation by the project owner (Vu Tuan Anh):** the project was developed with Kiro **from 2026-10-30 to the end of 2026-11-09**, on **both the office machine and the home machine**. Kiro IDE used **Claude Sonnet 5.5** and **Claude Opus 5.5**; work done by these models inside Kiro is recorded as Kiro-assisted work.

This is the owner's statement, not a log. The Kiro logs kept locally exist on **one machine** and only from 2026-11-05 (section 2). For the rest of 30 Oct – 9 Nov there are no logs on hand to check individual files or commits.

> **Principle.** This document does not claim that all source code was produced by Kiro. Every item carries one of three evidence types:
> **A** – **Kiro log**: session records, file write/edit commands, end-of-session reports;
> **B** – **owner confirmation, no log**: present in the source and within the period the owner confirms Kiro was used, but no record allows attributing a file to Kiro or to the author;
> **C** – **reconstructed from code or documents**: described from the existing code, not from session records.
>
> File and line counts in sections 1 and 8 come from type A only. The owner's confirmation does not increase them.

## 1. Summary

| Measure | Value | Source |
|---|---|---|
| Kiro sessions for this workspace stored locally | **7** (5 chat sessions + 2 steps of the `wf-coder` workflow agent) | the user's Kiro session folder |
| Period with records | **2026-11-05 17:27 → 2026-11-09** (this review session) | `session.json`, `messages.jsonl` |
| Models in the sessions | `claude-sonnet-5.5` (5 sessions), `claude-opus-5.5` (3 sessions: 2 workflows + 1 chat) | `session.json` |
| Turns / tool calls | 62 turns, 3,924 calls up to the time of this count (shell 1,403, file reads 723, `str_replace` 993, `fs_write` 358, searches 319…): **3,704 calls (1,274 write/edit)** in the historical records before 11-09 17:19 and **220 calls (95 write/edit)** in the current turn | counted from `messages.jsonl`; the current-turn count keeps growing |
| Kiro workflows run | 2 × `bundled://goal` (G1.0 and G1→G5), agent `wf-coder`, `claude-opus-5.5`, effort `high` | `workflow-state.json` |
| Product files in Git with at least one Kiro write/edit | **257 / 471** (55%): code 161/300, documents `.md`/`.txt` 88/142, configuration 8/29. Of these, **194** come from the historical records and **63** were first touched by Kiro in the current turn (59 newly created). **208** files have an `fs_write` call (created or overwritten whole); 49 were edited locally only | section 8; the denominator excludes 9 non-product files |
| Lines in those files | 54,957 / 76,975 lines (71%) — an **upper bound**; 29,926 lines (39%) are in files with `fs_write`. Code alone: 46,189 / 60,609 (76%); documents: 8,364 / 14,620 (57%) | section 8; editing a file does not mean writing all of it |
| Specs / steering / hooks in `.kiro/` | No session recorded spec mode. On 2026-11-09 the repository gained 10 spec groups and 3 steering files **reconstructed from code** (`Spec reconstructed from the implemented code on 2026-11-09`) and 2 hooks. They are **not** historical Kiro artefacts | section 7 |

Two points to read before using this document in a submission:

1. **Local Kiro logs start on 2026-11-05 17:27 and cover one machine only.** The owner confirms Kiro was used from 30 Oct to the end of 9 Nov on both the office and home machines. For 30 Oct – 4 Nov, and for the work on the other machine, **no logs are on hand**; that work is type **B** (owner confirmation) and is not attributed to individual files.
2. **Git does not record Kiro.** All 9 commits come from one GitHub account (`deviouslove-ship-it`) with no co-author line; the first commit (2026-11-08 20:32) is a snapshot of 404 files from the working folder. Git therefore cannot show who wrote what.

## 2. Kiro sessions still accessible

| Session | Title (set by Kiro) | Time | Mode / model | Turns | Tool calls | Files written | Main result |
|---|---|---|---|---|---|---|---|
| `4c10b6e7` | Kiroween record review (root session, renamed for the current request) | 11-05 17:35 → now | vibe, Autopilot, Sonnet 5.5 | 46 | 1,668 | 143 | Many rounds: search accuracy/performance, LAN package v1, Word/TXT, effectivity design, G0, reranker benchmark, 50-question set, RRF tie-break key, UI test `.bat` files |
| `b63f6d04` | Migrate Project Data From C To E Drive | 11-07 08:51–09:16 | vibe, Sonnet 5.5 | 3 | 72 | 24 | Inventory of drive C data, permissions config; one mistake, reverted (section 3, A24) |
| `4c237fbe` | goal · work #1 (workflow G1.0) | 11-07 10:54–11:55 | `wf-coder`, Opus 5.5 | 2 | 181 | 20 | G1.0 AI stage policy + Hybrid Auto |
| `79b7dcee` | goal-g1-g5-tra-cuu-hieu-luc · work #1 | 11-07 11:57–15:20 | `wf-coder`, Opus 5.5 | 2 | 419 | 82 | G1→G5: effectivity, comprehensive search, content groups, synthesis, coverage measurement |
| `f6f39653` | Embedding management in Admin Portal | 11-07 19:41–21:22 | vibe, Autopilot, Opus 5.5 | 2 | 192 | 30 | Background embedding management in the Admin Portal |
| `201bebb1` | Fix AI interpretation and OCR | 11-08 10:22–15:35 | vibe, Autopilot, Sonnet 5.5 | 4 | 972 | 114 | USER lookup fixes, AI interpretation, scanned-PDF OCR, Model Registry UI |
| `d0b73228` | Package Evidence RAG As Portable Windows LAN | 11-08 16:00–17:21 | vibe, Autopilot, Sonnet 5.5 | 1 | 223 | 26 | Offline Windows LAN Portable package |

Two more Kiro sessions on 2026-11-05 (16:59–17:26) belong to a different working folder, are unrelated to the project and are not counted.

## 3. Work with direct Kiro evidence (type A)

The "Evidence" column gives the session ID (first 8 characters) and files that can be checked in the repository. "Done" means the end-of-session report says it was checked, **not** domain acceptance. Figures are those reported by Kiro at the end of each session; this review did not re-run them (section 9).

| # | Feature | What Kiro did | Reported result | Files / commits | Status | Evidence |
|---|---|---|---|---|---|---|
| A1 | Review of search/chat accuracy and performance (11-05) | Reviewed the backend: search, evidence retrieval for chat, evidence re-check, audit log. Fixed normalisation of document numbers (`15/2020/nđ-cp` vs `NĐ-CP`), queries without diacritics, Vietnamese capitals when the database uses locale `C`, chat citing a superseded version, duplicated clauses when validity intervals share a date | 8 self-built cases: 3/8 → 8/8; 35 consecutive chat turns without error; 193 backend tests pass | `backend/app/storage/search.py`, `authorized_search.py`, `search_paging.py`, `citations.py`, `workflow/fixed_pipeline.py`, `scripts/benchmark_search.py`, `ADR-006`, `docs/evidence/2026-11-05-retrieval-accuracy-performance/REPORT.md` | Done | `4c10b6e7`, 11-05 |
| A2 | Result count cap N = 8,000 and handling of expired grounds (option C) | The user chose the option and N; Kiro implemented `EVIDENCE_SEARCH_COUNT_CAP`, the "more than 8,000 clauses" display; the whole conclusion is dropped only when the first/exactly-asked Article is expired, otherwise only that clause is excluded and noted in "practical-use caveats" | Query hitting 99% of clauses: 1.1–1.3 s (previously timed out); "approximate results" count 5 s → 40 ms; 4 effectivity scenarios follow the rule | `backend/app/config.py`, `storage/search.py`, `workflow/fixed_pipeline.py`, `docs/search-v1-runbook.md` | Done | `4c10b6e7`, 11-05 |
| A3 | Review of AI Local/API flow and hangs | Checked the connection policy (Local: internal/LAN only; API needs HTTPS and permission). Fixed a model marked "ready" but stopped that made each chat turn wait about 30 s: an unreachable model is skipped for 60 s | No hang in the tested scenario | `backend/app/model_registry/runtime.py`, `adapters/openai_compatible.py`, `workflow/ai_selection.py` | Done | `4c10b6e7`, 11-05 |
| A4 | Clean-up of old AI data, sample questions, documents; rebuild web and desktop | Deleted 20 providers, 10 model profiles, 12 old routes (audit event `maintenance.delete_legacy_model_registry` and a backup exist); replaced sample questions with 3 generic ones; removed contradictory document text; rebuilt `frontend/dist` and the desktop file | 73 frontend and 193 backend tests pass; 17/17 native tests pass | `frontend/src/samplePrompts.ts`, `README.md`, `00_README.md`, `docs/SRS_v1.3.md` | Done | `4c10b6e7`, 11-05 |
| A5 | LAN/portable package v1 | Start script derives paths from script location, detects IP at run time, creates an empty database, 4 bootstrap accounts forced to change password, opens/closes firewall | Package 216 MB (zip 77 MB), run on the development machine | `deploy/portable/*`, `scripts/package-portable.ps1`, `scripts/start-local-stack.ps1` (`-Lan`) | Done; **not tried on a second machine** | `4c10b6e7`, 11-06 |
| A6 | Survey and import of a trial corpus; Word/TXT; Gemini config | Surveyed 717 files (324/378 PDFs are scans); copied 295 text-layer files to `test-data/van-ban` (not in Git); added `.docx`, `.doc`, `.txt` by rendering to a text-layer PDF (no Word needed); `/v1beta/openai` path; folder import script | 242 Word files ran without error; `.doc` extraction matched Word 99.9% on 3 files; first import only 14/293 documents approvable (led to A8) | `backend/app/documents/convert.py`, migration `0008_source_format`, `scripts/import_official_corpus.py`, `docs/ai-model-recommendations.md`, `test-data/README.md` | Done | `4c10b6e7`, 11-06 |
| A7 | Design of "comprehensive lookup + effectivity + synthesis" | Discussed and fixed with the user 8 architecture issues, the two effectivity axes (validity × verification), document groups, Hybrid Auto, attestation rights, synthesis cap; wrote the final design and a 15-question test set | Design approved by the user | `docs/thiet-ke-tra-cuu-hieu-luc.md`, `test-data/cau-hoi-kiem-thu-vong-1.md` | Done (design) | `4c10b6e7`, 11-06–07; six session "artifact" files |
| A8 | G0 — multi-page clause anchoring | Each clause stores per-page source spans, Article–Clause–Point tree with `parent_id`/`path`/`citation_label`, split clauses over 4,000 characters, suspect text-layer flag, tree rebuild tool | From 14/293 to 286/293 approvable documents; 0/21,724 clauses unanchored; 193 backend tests | `documents/node_writer.py`, `tree_parser.py`, `spans.py`, migration `0009_node_structure`, `scripts/rebuild_node_tree.py` | Done | `4c10b6e7`, 11-07 |
| A9 | G1.0 — AI stage policy, Hybrid Auto | Per-stage model call count set by the administrator (replacing a hard limit of 2), Local→API when local fails or "deep analysis", Local Only never calls an API, usage log and cost caps | `verify.ps1` 12/12 (backend 206, frontend 74, 10 migration pairs) | migration `0010_ai_policy`, `model_registry/runtime.py`, `stages.py`, ADR-007 | Done | workflow `wf_9ba3807d…`, session `4c237fbe`, 11-07 |
| A10 | G1 — document effectivity | Reads effective dates and amend/repeal relations by rules; proposals for reviewers; two status axes; "In force + Verified" only from a human attestation | HTTP 27/27 | `backend/app/effectivity/*`, migration `0011_effectivity`, ADR-008, `frontend/src/components/EffectivityReviewPanel.tsx` | Done | workflow `wf_ffe44206…`, session `79b7dcee`, 11-07 |
| A11 | G2 — four-channel comprehensive search + embedding | Exact, semantic (vector), concept and relation channels; fused with RRF; result set fixed per request; vector index without fixed dimension | HTTP 17/17 | `storage/comprehensive.py`, `embeddings.py`, `scripts/build_embeddings.py`, migration `0012_comprehensive_search`, ADR-009 | Done | `79b7dcee`, 11-07 |
| A12 | G3 — Article/Clause/Point relations | Detects amend/repeal at provision level, inherited into search results | 31/31 relations match the reference (reference drafted by an agent, not confirmed by staff); HTTP 11/11 | `effectivity/node_paths.py`, `evaluation/coverage/g3_relations_reference.json` | Done (no domain acceptance) | `79b7dcee`, 11-07 |
| A13 | G4 — content groups and verified synthesis | 11 initial content groups, labels by rules and model, batch synthesis, code checks before statements are shown | Local 10/10; API 11/11 (including 3 real API calls, 12/12 statements passed checks) | `synthesis/*`, migration `0013_content_groups`, `api/v1/synthesis.py` | Done | `79b7dcee`, 11-07 |
| A14 | G5 — coverage measurement | 8 topics, 24 questions, 42 required grounds; measured per channel | 40/42 found; `verify.ps1` 12/12 (backend 218, frontend 74, 13 migration pairs) | `evaluation/coverage/*`, `docs/implementation-status.md` | Done (required grounds drafted by an agent, unconfirmed) | `79b7dcee`, 11-07 |
| A15 | Reranker comparison | Measured plain RRF, LLM rerank, Qwen3-Reranker-0.6B on CPU (Recall@k, MRR, NDCG, time, RAM); diagnosed that the two missing grounds are retrieval, not ranking, failures; the user decided to keep RRF as default | RRF R@10 0.762; LLM 0.691; Qwen3 0.810 — MRR/NDCG differences lie within confidence intervals containing 0; 32–48 s per question for the two rerankers | `evaluation/coverage/*`, `scripts/local_reranker_server.py`, `storage/cross_encoder.py`, `docs/evidence/2026-11-07-g5-rerank/REPORT.md` | Done | `4c10b6e7`, 11-07 |
| A16 | 50-question set, rebuild of data and backup | Added 26 questions; rebuilt the 100-document database (7,230 vectors, 42 min); `pg_dump` and restore check (row counts, text and vector checksums, 98 indexes, HNSW) | RRF 50 questions: R@10/20/50/all 0.865/0.892/0.932/0.960, MRR 0.790 | `scripts/verify_db_restore.py`, `evaluation/coverage/topics.json`, `…/REPORT-50-cau.md` | Done | `4c10b6e7`, 11-07 |
| A17 | Stable RRF tie-break key | Replaced random UUIDs with a key (document number, file SHA-256, clause position) in `_rrf`, the exact channel and the relation channel | Two independently imported databases: identical order for 50/50 questions (before 45/50 and 41/50); backend 225, frontend 77 | `storage/search_paging.py`, `storage/comprehensive.py`, `evaluation/coverage/check_tiebreak_stability.py` | Done | `4c10b6e7`, 11-08 08:07 |
| A18 | Embedding management in the Admin Portal | Change/add an embedding model in the UI, compatibility check, rebuild vectors as a background job with progress, switch the index only after verification, keep old vectors | `verify.ps1` 12/12 and a run with real Ollama | migration `0014_embedding_jobs`, `storage/embedding_jobs.py`, `frontend/src/components/EmbeddingManager.tsx` | Done | `f6f39653`, 11-07 |
| A19 | USER lookup fixes | Failing case "appointment and dismissal procedure": phrase-level relevance scoring, drop long/repeated list blocks, query analysis that does not split syllables, short assessment, open the right source PDF | Checked on the real 100-document database via HTTP and headless Chrome; 12/12 | `storage/relevance.py`, `storage/chat_retrieval.py`, `workflow/chat_answer.py`, `docs/evidence/2026-11-08-user-lookup/REPORT.md` | Done; TXT and Tauri desktop not checked | `201bebb1`, 11-08 |
| A20 | AI interpretation and scanned-PDF OCR | The model receives the question and only filtered evidence; stricter code verification; page-by-page reviewed OCR workflow | "Blood-alcohol penalty" returns "not found" instead of an off-topic point; "Open original" opens the right file, page and permission | `synthesis/focus.py`, `focused.py`, `checks.py`, `documents/ocr.py`, `native_pdf.py`, migration `0015_ocr_page_review`, `docs/evidence/2026-11-08-ai-ocr/REPORT.md` | Done; Tauri/TXT not checked | `201bebb1`, 11-08 |
| A21 | Model Registry UI redesign | Two forms (AI Local, AI API), DPAPI-encrypted API key store (key never returned), connection test before save/apply, per-function model assignment | `verify.ps1` 12/12; backend 288, frontend 86 | `model_registry/secret_store.py`, `diagnostics.py`, `frontend/src/components/ai/*`, `docs/evidence/2026-11-08-model-registry-ui/REPORT.md` | Done; real OpenAI/Gemini not called | `201bebb1`, 11-08 |
| A22 | Windows LAN Portable offline | One-command `Start-Server.bat` package with backup/restore, package check, firewall helper; builder in the repository | Package 4.5 GB (zip 3.6 GB) kept outside the repository; acceptance run on the development machine | `deploy/lan-portable/*`, `scripts/build-lan-portable.ps1` | Done; **not tried on another physical Windows machine** | `d0b73228`, 11-08 |
| A23 | `.bat` files to open the app for UI testing | Start/stop PostgreSQL, Ollama and web on loopback ports; login and search checks | Start–stop checked, no leftover processes | `Mo-ung-dung-test.bat`, `Dung-ung-dung-test.bat`, `ung-dung-test.ps1` | Done | `4c10b6e7`, 11-08 08:50 |
| A24 | Drive C data inventory, Kiro permissions | Inventoried data, drafted workspace permissions; `.kiro/settings/permissions.yaml` in the repository is **byte-identical** to the file Kiro drafted at 09:08 (SHA-256 `58EF3EDA…C95C209`) and applied by the user at 09:17. **Mistake:** Kiro changed another tool's environment variable, the user objected, Kiro reverted it | Permissions applied; Kiro data moved to drive E | `.kiro/settings/permissions.yaml` | Partly done (the user ran the user-settings part) | `b63f6d04`, 11-07 |
| A25 | Kiroween record review (phase 1) | Inventory of Git, `~/.kiro`, sessions, specs/steering/hooks/MCP; wrote this document | — | `KIRO_WORK_SUMMARY.vi.md`, `KIRO_WORK_SUMMARY.en.md` | Done | `4c10b6e7`, 11-09 |
| A26 | Kiroween record: specs, steering, hooks, bilingual documents (**current turn**) | Reconstructed 10 spec groups (30 EARS/design/tasks files), 3 steering files, 2 hooks via `createHook` (hook commands run directly), 14 Vietnamese translations, and Vietnamese/English versions of the README, Kiro summary, timeline, system description, guide, deployment notes, architecture overview | Commit `34cff8b`: 66 files (59 new, 7 modified). Tests not re-run; the IDE has not triggered the hooks yet | `.kiro/*`, `docs/en/*`, `docs/vi/*`, `*.en.md`, `*.vi.md` | Done | `4c10b6e7`, 11-09 from 17:19 |
| A27 | Recount of Kiro's contribution (**current turn**) | Recomputed the statistics under the principles of section 8.1: Markdown and configuration included, only input data and non-product files excluded; files affected separated from files with `fs_write`; history separated from the current turn | Section 8, statistics appendix | `KIRO_STATS_APPENDIX.vi.md`, `KIRO_STATS_APPENDIX.en.md` | Done | `4c10b6e7`, 11-09 |

## 4. Work in the source without Kiro logs (type B)

These items exist in the repository but have **no Kiro write/edit command in the stored session records**. The owner confirms Kiro was used from 30 Oct to 9 Nov 2026 on two machines, so part of this may be Kiro-assisted; individual files cannot be attributed to Kiro or the author, and this document does not try. Files dated before 30 Oct (requirements, initial skeleton) are outside the confirmed period.

| Component | Why it is "in the source" | Why it is not attributed |
|---|---|---|
| Original requirements and design: `docs/HOSO_BAN_GIAO.md`, `docs/SRS_v1.3.md` (initial version), `docs/history/SRS_v1.2.1.md`, `docs/PROMPT_KHOI_DONG.md`, `parts/*`, ADR-000…004 | Earliest files date 21–22 Oct 2026; `PROJECT_TIMELINE.md` says the author wrote the description, specification and plan before 30 Oct | Before any Kiro record; Kiro only edited some SRS passages on 11-05 |
| Initial skeleton: `backend/app/auth_acl/*`, `evidence/*`, `memory/*`, `vietnamese_nlp/*`, `api/v1/auth.py`, `execution.py`, `guards.py`; migrations `0001…0007`; `src-tauri/*` (Tauri 2, 12 files); base UI components (`LoginPanel`, `DesktopOrb`, …) | In the repository; earliest edit 22 Oct | 0/4 `auth_acl`, 0/3 `evidence`, 0/2 `memory`, 0/3 `vietnamese_nlp`, 0/12 `src-tauri` files and migrations 0001–0007 have Kiro write commands |
| First Search v1 (ADR-005, `storage/search.py`) and reports `docs/evidence/2026-10-22-*`, `2026-10-26-*`, `2026-10-27-*`, `2026-10-31-*`, `2026-11-01-app-audit` | Reports and benchmarks in the repository, dated 22 Oct–1 Nov | No Kiro session recorded for this period; Kiro edited `search.py`, `search_paging.py` only from 11-05 (A1, A2) |
| Admin Portal document management and lookup visibility (commit `ba596ce`, 11-09): `documents/management_{access,read,write}.py`, migration `0016_document_management`, `storage/lookup_visibility.py`, `AdminDocumentManager.tsx`, `AdminDocumentDetail.tsx`, related tests | In the repository and Git | **17 of the 52 files in this commit have no Kiro write command**; between 11-08 17:21 and 11-09 17:19 no Kiro session is recorded, while 3 commits (09:25, 10:00, 12:04) fall in that window |
| System description and user guide: `docs/TAI_LIEU_MO_TA_HE_THONG.md`, `docs/HUONG_DAN_SU_DUNG_VA_CAU_HINH_AI.md` (commits `74e7e60`, `caa2e7a`) | In Git | No Kiro write command |
| CI, license, disclosure: `.github/workflows/ci.yml`, `LICENSE`, `NOTICE`, `PROJECT_TIMELINE.md` | In Git (committed by the author) | Written by the author; outside Kiro's scope |
| UI design through Stitch: `.stitch/DESIGN.md`, `SITE.md`, `metadata.json` | In Git; the machine has a `stitch` MCP config | No Kiro write command; creating session unknown |
| Small tools: `tools/*`, `scripts/seed_local_runtime.py`, `smoke_app_runtime.py`, `validate_*`, `evaluation/scripts/*` | In the repository | No Kiro write command |

Note: changes without a Kiro record are **not** counted as Kiro's, even when they fall inside the period the owner confirmed.

## 5. Information reconstructed from code and documents (type C)

These descriptions come from reading existing code and documents, not from session records. They describe the system as it exists, not who built it.

| Content | Basis in the source |
|---|---|
| Roles `SYS_ADMIN`, `AUDITOR`, `CURATOR`, `REVIEWER`, `USER`; permissions by category (`category_acl`, `can_query`, `can_review`) | `backend/app/auth_acl/*`, `migrations/0002_auth_admin`, `0011_effectivity` |
| Flow ingest → draft → approval by another person → approved document; duplicate upload blocked by SHA-256 | `documents/draft.py`, `review.py`, `deduplication.py`, migrations `0001`, `0005` |
| Source-pinned citations: document number, Article/Clause/Point label, page, file hash, quote matching the source character for character | `storage/citations.py`, `docs/citation-contract.md`, `docs/pdf-anchor-coordinate-contract.md` |
| PDF intake: pypdfium2 extracts text and character boxes in an isolated child process; OCR (Tesseract) only for empty pages or suspect text layers | `documents/native_pdf.py`, `pdf_worker.py`, `isolated.py`, `ocr.py` |
| Runs fully locally: Local Only never calls external APIs; API only when configured and allowed | `model_registry/*`, `docs/threat-model.md` |
| React 18 + Vite 5 + TypeScript 5 web app; FastAPI + asyncpg backend; PostgreSQL with pgvector; Tauri 2 desktop shell | `frontend/package.json`, `backend/pyproject.toml`, `src-tauri/*`, migrations |
| Admin Portal document management (commit `ba596ce` and the guide) | `documents/management_*.py`, `AdminDocumentManager.tsx` — functions inferred from code, actor unknown |
| 10 spec groups, 3 steering files, 2 hooks added 2026-11-09 | `.kiro/specs/*`, `.kiro/steering/*`, `.kiro/hooks/*`; each states it was reconstructed from code |

## 6. Development timeline

Dates before 11-05 are inferred from file modification times and are **indicative only**: files in the working folder were re-synchronised at 17:14 on 11-09, so modification times are no longer reliable for them.

| Date | Event | Type |
|---|---|---|
| 21–22 Oct 2026 | Requirements (SRS 1.2.1, startup prompt), first code skeleton, first audit/"takeover" reports | B |
| 26–27 Oct | Code audit report, content de-duplication; a `pg_dump` of the dev database exists | B |
| 30 Oct | **Start of the period in which the owner confirms Kiro use** (no local log) | B |
| 31 Oct | Search v1, benchmark and review; CI file | B |
| 1 Nov | App audit report | B |
| **11-05 17:27** | **Earliest Kiro record for the project.** 17:35: accuracy/performance review; N = 8,000 and effectivity option C fixed; AI flow review; clean-up of old AI data; web and desktop build | A1–A4 |
| 6 Nov | LAN/portable package v1; survey of 717 files; Word/TXT support; batch answers to architecture questions; test-round plan | A5–A6 |
| 7 Nov morning | Design fixed; G0 (09:19–10:47); Kiro data moved to drive E (08:51–09:16) | A7, A8, A24 |
| 7 Nov 10:54–11:55 | Workflow G1.0 | A9 |
| 7 Nov 11:57–15:20 | Workflow G1→G5 (paused and resumed at 14:27) | A10–A14 |
| 7 Nov 15:29 → 21:00 | Reranker benchmark; 100-document data check; 50-question set; database rebuild, `pg_dump` | A15, A16 |
| 7 Nov 19:41–21:22 | Embedding management in the Admin Portal | A18 |
| 8 Nov 08:07 | Stable RRF tie-break key | A17 |
| 8 Nov 08:50 | `.bat` files for UI testing | A23 |
| 8 Nov 10:22–15:35 | USER lookup fixes, AI interpretation, OCR, Model Registry UI | A19–A21 |
| 8 Nov 16:00–17:21 | Windows LAN Portable offline | A22 |
| 8 Nov 20:32 | **First Git commit**: snapshot of 404 files (289bf62); 20:34–21:02 documents, CI added | B |
| 9 Nov 09:25–12:04 | Commits: document management (`ba596ce`), documentation clarifications (`caa2e7a`), license and disclosure (`08b0021`); **no Kiro session recorded in this window** | B |
| 9 Nov (end of confirmed period) | Last day of Kiro use confirmed by the owner | B |
| 9 Nov 17:19 onward | This record-review session; `.kiro` specs/steering/hooks and bilingual documents added | A25, C |

## 7. Inventory of Kiro material in the project

| Item | Result |
|---|---|
| `.kiro/specs`, `.kiro/steering`, `.kiro/hooks` before 2026-11-09 | **None** found in the repository, backups or `~/.kiro` |
| `.kiro/settings/permissions.yaml` | Present (on GitHub since the first commit); drafted by Kiro and applied by the user (A24). Left unchanged |
| `.kiro/specs` (10 groups), `.kiro/steering` (3 files), `.kiro/hooks` (2 hooks) from 2026-11-09 | **Reconstructed from code** (type C), in English so Kiro reads them directly; Vietnamese translations in `docs/vi/kiro/`. The hook commands were run directly; automatic triggering by the IDE only takes effect from the next Kiro session and has not been observed |
| Project copy `Evidence_RAG_Handoff-20261109-171404` | Contains `.kiro/settings/permissions.yaml`, byte-identical; nothing else |
| MCP configuration | Only at user level (`~/.kiro/settings/mcp.json`), 9 servers; only `stitch` relates to UI design; the rest are personal tools. Not copied into the repository (machine paths and personal configuration) |
| Working mode | All stored sessions ran in free chat mode (`vibe`) or workflow; session settings record `specPlanEnabled = false`. **The specs, steering and hooks added on 2026-11-09 are reconstructed documents, not Kiro history.** |

## 8. Method and statistics

### 8.1 Counting principles (adjusted at the project owner's request, 2026-11-09)

1. **Only the input business documents of Evidence RAG are excluded** (PDF, DOC, DOCX, TXT of laws, decrees, circulars, decisions, official letters downloaded or imported into the store), together with files downloaded from the Internet, model weights, dependencies, runtimes, caches and auto-generated data. No input file is in Git (they sit in folders ignored by `.gitignore`); only {NX} files in Git are excluded (fonts, dependency lock files, binary icons, the auto-generated `docs/openapi.json`, the public-corpus manifest). The list is in the appendix.
2. **A file is not excluded merely because it is Markdown.** Documents Kiro wrote to develop the project (requirements, design, tasks, SRS, ADRs, READMEs, reports, guides, specs, steering) count like code. Documents imported for lookup do not.
3. A file counts when it is in Git at commit `34cff8b` and has at least one Kiro write/edit command (`fs_write`, `str_replace`, `fs_append`, `delete_file`, `semantic_rename`, `smart_relocate`, `createHook`) in the session records, whatever its extension.
4. **Two different measures:** *files affected* (at least one write/edit command) and *files with an `fs_write` call* (Kiro created or overwrote the whole file at that moment). A file with only `str_replace`/`fs_append` is affected, not written whole.
5. **Historical evidence and current-turn work are separated.** The current turn starts at the Kiroween record-review request (2026-11-09 17:19). Specs, steering, hooks and bilingual documents created in this turn are Kiro work **in the current turn**; they are not evidence about the earlier development history.
6. 30 Oct – 9 Nov 2026 is the period of Kiro use confirmed by the owner on two machines. Work without logs is **not** added to the figures here.

### 8.2 Sources and definitions

- **Sources:** `session.json` and `messages.jsonl` of the 7 sessions; `workflow-state.json`; `git ls-tree` at commit `34cff8b`; current code and documents.
- **Files counted:** 471 of 480 tracked files (9 excluded).
- **File counts are a lower bound:** files created by shell commands are not counted. 29 files are mentioned in shell commands containing a write verb but have no edit-tool call; a mention does not prove a write, so they are **not counted** (list in the appendix).
- **Line counts are an upper bound on authorship:** editing a file does not mean writing all of it, and later changes by others cannot be separated. Lines in files with `fs_write` are closer to "written whole by Kiro" but are still an upper bound.
- Lines are counted at commit `34cff8b`. The statistics/summary files updated after that commit belong to the current turn and are not in the figures.

### 8.3 Totals by file type

| Group | Files counted | With a Kiro command | With `fs_write` | Lines | Lines in files with a Kiro command | Lines in files with `fs_write` |
|---|---:|---:|---:|---:|---:|---:|
| **Total** | 471 | 257 | 208 | 76,975 | 54,957 (71%) | 29,926 (39%) |
| Code (`.py`, `.ts`, `.tsx`, `.sql`, `.ps1`, `.bat`, `.cmd`, `.rs`, `.css`, `.js`, `.mjs`, `.html`) | 300 | 161 | 120 | 60,609 | 46,189 (76%) | 23,659 (39%) |
| Documents (`.md`, `.txt`) | 142 | 88 | 81 | 14,620 | 8,364 (57%) | 5,914 (40%) |
| Configuration and technical data (`.json`, `.yaml`, `.toml`, `.env`, `.example`, extension-less) | 29 | 8 | 7 | 1,746 | 404 (23%) | 353 (20%) |

### 8.4 History and current turn

| Period | Files | Tool calls | Write/edit calls | Note |
|---|---:|---:|---:|---|
| Historical records (11-05 → 11-09 17:19) | 194 (code 161, documents 27, configuration 6) | 3,704 | 1,274 | The previously published 194/421 is unchanged; the denominator is now 412 counted files of the 421 at commit `08b0021` (9 excluded) |
| Current turn (from 11-09 17:19, up to the time of this count) | 63 files first touched by Kiro (59 created, 4 existing) and 3 historical files edited again | 220 | 95 | Specs, steering, hooks, bilingual documents, statistics. The call count keeps growing while the session continues |
| **Total** | **257** / 471 (55%) | 3,924 | 1,369 | |

Tool-call distribution (total): `execute_pwsh` 1,403, `str_replace` 993, `read_file` 723, `fs_write` 358, `grep_search` 319, `list_directory` 29, `update_session_information` 16, `remote_web_search` 13.

### 8.5 By area

| Area | Files counted | With a Kiro command | With `fs_write` | Lines | Lines in files with a Kiro command | Lines in files with `fs_write` |
|---|---:|---:|---:|---:|---:|---:|
| `(root)` | 15 | 10 | 10 | 1,296 | 971 (75%) | 971 (75%) |
| `.github` | 1 | 0 | 0 | 29 | 0 (0%) | 0 (0%) |
| `.kiro` | 36 | 35 | 35 | 1,349 | 1,274 (94%) | 1,274 (94%) |
| `.stitch` | 3 | 0 | 0 | 69 | 0 (0%) | 0 (0%) |
| `backend/(root)` | 1 | 1 | 0 | 51 | 51 (100%) | 0 (0%) |
| `backend/app/(root)` | 7 | 5 | 0 | 2,871 | 2,865 (100%) | 0 (0%) |
| `backend/app/api` | 13 | 5 | 3 | 2,737 | 2,163 (79%) | 731 (27%) |
| `backend/app/auth_acl` | 4 | 0 | 0 | 347 | 0 (0%) | 0 (0%) |
| `backend/app/documents` | 20 | 11 | 4 | 3,487 | 2,581 (74%) | 1,085 (31%) |
| `backend/app/effectivity` | 7 | 7 | 7 | 2,372 | 2,372 (100%) | 2,372 (100%) |
| `backend/app/evidence` | 3 | 0 | 0 | 197 | 0 (0%) | 0 (0%) |
| `backend/app/memory` | 2 | 0 | 0 | 579 | 0 (0%) | 0 (0%) |
| `backend/app/migrations` | 35 | 17 | 17 | 1,432 | 570 (40%) | 570 (40%) |
| `backend/app/model_registry` | 9 | 7 | 4 | 2,099 | 2,080 (99%) | 486 (23%) |
| `backend/app/storage` | 14 | 10 | 6 | 5,726 | 5,553 (97%) | 3,544 (62%) |
| `backend/app/synthesis` | 6 | 6 | 6 | 1,793 | 1,793 (100%) | 1,793 (100%) |
| `backend/app/vietnamese_nlp` | 3 | 0 | 0 | 186 | 0 (0%) | 0 (0%) |
| `backend/app/workflow` | 6 | 3 | 2 | 1,425 | 1,304 (92%) | 625 (44%) |
| `backend/tests` | 48 | 17 | 11 | 8,832 | 4,541 (51%) | 2,498 (28%) |
| `configs` | 5 | 1 | 1 | 72 | 28 (39%) | 28 (39%) |
| `deploy` | 22 | 22 | 21 | 2,363 | 2,363 (100%) | 2,304 (98%) |
| `docs` | 82 | 39 | 34 | 10,542 | 5,675 (54%) | 3,404 (32%) |
| `evaluation` | 28 | 13 | 12 | 4,456 | 1,536 (34%) | 1,416 (32%) |
| `frontend/(root)` | 7 | 0 | 0 | 136 | 0 (0%) | 0 (0%) |
| `frontend/e2e` | 2 | 0 | 0 | 304 | 0 (0%) | 0 (0%) |
| `frontend/public` | 1 | 0 | 0 | 5 | 0 (0%) | 0 (0%) |
| `frontend/src` | 56 | 38 | 26 | 17,013 | 15,068 (89%) | 5,148 (30%) |
| `parts` | 3 | 0 | 0 | 1,180 | 0 (0%) | 0 (0%) |
| `scripts` | 17 | 9 | 8 | 2,901 | 2,130 (73%) | 1,638 (56%) |
| `src-tauri` | 9 | 0 | 0 | 852 | 0 (0%) | 0 (0%) |
| `test-data` | 2 | 1 | 1 | 131 | 39 (30%) | 39 (30%) |
| `tools` | 4 | 0 | 0 | 143 | 0 (0%) | 0 (0%) |

### 8.6 By extension

| Extension | Files counted | With a Kiro command | With `fs_write` | Lines | Lines in files with a Kiro command | Lines in files with `fs_write` |
|---|---:|---:|---:|---:|---:|---:|
| `(none)` | 3 | 0 | 0 | 276 | 0 (0%) | 0 (0%) |
| `.bat` | 9 | 9 | 9 | 107 | 107 (100%) | 107 (100%) |
| `.cmd` | 5 | 5 | 5 | 42 | 42 (100%) | 42 (100%) |
| `.css` | 2 | 1 | 0 | 3,537 | 3,493 (99%) | 0 (0%) |
| `.env` | 2 | 2 | 2 | 100 | 100 (100%) | 100 (100%) |
| `.example` | 2 | 1 | 1 | 29 | 28 (97%) | 28 (97%) |
| `.html` | 1 | 0 | 0 | 13 | 0 (0%) | 0 (0%) |
| `.js` | 1 | 0 | 0 | 25 | 0 (0%) | 0 (0%) |
| `.json` | 15 | 4 | 4 | 1,131 | 225 (20%) | 225 (20%) |
| `.md` | 139 | 85 | 78 | 14,326 | 8,070 (56%) | 5,620 (39%) |
| `.mjs` | 1 | 0 | 0 | 279 | 0 (0%) | 0 (0%) |
| `.ps1` | 8 | 6 | 6 | 2,730 | 2,472 (91%) | 2,472 (91%) |
| `.py` | 180 | 87 | 58 | 38,306 | 27,973 (73%) | 15,363 (40%) |
| `.rs` | 5 | 0 | 0 | 725 | 0 (0%) | 0 (0%) |
| `.sql` | 32 | 16 | 16 | 1,329 | 527 (40%) | 527 (40%) |
| `.toml` | 2 | 1 | 0 | 73 | 51 (70%) | 0 (0%) |
| `.ts` | 16 | 7 | 5 | 3,495 | 3,000 (86%) | 939 (27%) |
| `.tsx` | 40 | 30 | 21 | 10,021 | 8,575 (86%) | 4,209 (42%) |
| `.txt` | 3 | 3 | 3 | 294 | 294 (100%) | 294 (100%) |
| `.yaml` | 4 | 0 | 0 | 108 | 0 (0%) | 0 (0%) |
| `.yml` | 1 | 0 | 0 | 29 | 0 (0%) | 0 (0%) |

File-by-file list, excluded files and uncounted candidates: [`KIRO_STATS_APPENDIX.en.md`](KIRO_STATS_APPENDIX.en.md).

**Sensitive data:** a user message in the records contains an API key (given temporarily for testing); it is not quoted here and no key was written to the repository.

## 9. Unverified limits

- The test suites were not re-run in this review; all test results in section 3 are figures Kiro reported at the end of sessions, together with reports in `docs/evidence/` (part of that folder is not in Git).
- Required grounds, reference relations and question sets were drafted by an agent and have **not been confirmed by domain staff**.
- The portable packages (A5, A22) have not been tried on a second physical Windows machine; the Tauri desktop app and TXT files were not checked in session `201bebb1`.
- 30 Oct – 4 Nov, the work on the second machine and the changes between 11-08 17:21 and 11-09 17:19 have no Kiro records to check against; they rest on the owner's confirmation.
- The Kiro sessions in section 2 cover one machine; the statistics exclude the other.
- Specs, steering and hooks of 2026-11-09 are reconstructed from code; automatic triggering of the hooks by the IDE has not been observed.
- Some other generated files (reports, files in `.agents/`) are outside Git per `.gitignore` and are not in the file statistics.
- The current-turn tool-call count is a snapshot at the time of this count and keeps growing while the session continues.
- The "files with `fs_write`" measure and the line counts are upper bounds on Kiro's authorship; the file count is a lower bound because files created by shell commands are not counted (29 uncounted candidates, see the appendix).
- Work in 30 Oct – 4 Nov, on the other machine and between 11-08 17:21 and 11-09 17:19 rests on the owner's confirmation and is not added to the figures.
