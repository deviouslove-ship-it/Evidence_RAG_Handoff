**Language / Ngôn ngữ:** [Tiếng Việt](P3_API_va_Plan_trien_khai_E-G.md) · English

English counterpart of `parts/P3_API_va_Plan_trien_khai_E-G.md`. The Vietnamese file is the original. These parts are extracts of `docs/HOSO_BAN_GIAO.md`.

---

## E. Supplementary API contract

SRS §11 keeps the original APIs (`/query/analyze`, `/query/requery`, `/query/evidence`, `/citations/*`, `/feedback`, `/admin/*`). The endpoint `/query/evidence` is responsible for returning the evidence (căn cứ), the evidence groups, the findings, and the reference suggestions. The earlier mock `/query/answer` and `/analysis/situation` have been removed. The complete two-phase streaming flow runs through `/agent/sessions/{id}/turns`. Below is the **supplementary API that is mandatory at the behavior level**. The agent locks the OpenAPI schema at the start of Sprint 1 and reconciles it with SRS v1.3. Every endpoint checks the ACL on the server. **No endpoint allows the Agent to write business data.**

| Group | Proposed endpoint | Purpose |
|---|---|---|
| Chat Agent session | `POST /api/v1/agent/sessions` (with the `incognito` flag) · `GET /api/v1/agent/sessions/{id}` · `DELETE /api/v1/agent/sessions/{id}` | Create a session, read its state (facts, scope, revision), and delete a session |
| Conversation turn | `POST /api/v1/agent/sessions/{id}/turns` (SSE) | Send a turn. It uses the shared two-phase SSE contract |
| Turn control | `POST /api/v1/agent/sessions/{id}/turns/{turn_id}/cancel` · `…/retry` · `GET …/{turn_id}/events?run_id=…` | Stop, retry on purpose, and resume the event stream for a run |
| Memory | `GET /api/v1/memory` · `DELETE /api/v1/memory/{item_id}` · `DELETE /api/v1/memory` · `GET/PUT /api/v1/memory/preferences` | View, delete one item or all items, and read and save default-category search preferences (opt-in) |
| Analysis and suggestions | Integrated in `POST /api/v1/query/evidence` and in the SSE `/turns` · `POST /api/v1/query/followups` (A2) | Structured situation analysis (A1); suggested next questions (already dry-run, and deduplicated against claims). The mock endpoint `/analysis/situation` has been removed. |
| Source and comparison | `GET /api/v1/nodes/{id}/notes` (A4) · `GET /api/v1/nodes/{id}/diff?as_of=…` (A5) · `GET /api/v1/nodes/{id}/related` (A6) | Points to notice, version comparison, and related administrative documents (văn bản) |
| AI suggestions for the curator | `GET /api/v1/admin/ai-suggestions` · `POST /api/v1/admin/ai-suggestions/{id}/accept` · `…/reject` · `…/edit` | The suggestion queue. Accept is an action by the curator, with an audit record |
| Source domains | `GET/POST /api/v1/admin/source-domains` · `PATCH /api/v1/admin/source-domains/{id}` | Manage the allowlist |
| Test suite | `GET /api/v1/admin/evaluation/cases` · `POST /api/v1/admin/evaluation/cases/{id}/review` · `GET /api/v1/admin/evaluation/splits` | Approve Gold and the trap set. View the calibration/held-out split |
| Watch (P1) | `POST /api/v1/watches` · `GET /api/v1/notifications` | A9 |

**Additional SSE events:** `retrieval_started`, `evidence_verified`, `evidence_complete`, `analysis_ready`, `answer_complete`, `explanation_unavailable`, `understood_as`, `clarify_needed`, `analysis_item`, `followup_suggestions`, `memory_state_changed`, `turn_cancelled`, and `turn_error` (with an error code: `SESSION_EXPIRED`, `MEMORY_CAPACITY_EXCEEDED`, `QUERY_FAILED`). These are added to the original event list in SRS §11.4. The frontend does not guess progress on its own.

**Shared contract that must go into OpenAPI at the start of Sprint 1**

- Scope: `scope_mode=SELECTED|ALL_AUTHORIZED`. SELECTED needs category IDs that have been granted. ALL_AUTHORIZED is resolved again by the server according to the current rights on every run. The search right is a separate right. It is not inferred from the SYS_ADMIN role.
- A session belongs to one principal. Creating a session defaults to `incognito=true`. `incognito=false` is allowed only when an approved retention policy exists and the user has opted in. If that is not sufficient, return `RETENTION_NOT_APPROVED`. Do not write quietly. The response states `persistence_state=ephemeral|retained`, `expires_at`, and the revisions. It does not contain a secret. Incognito uses RAM as in C.4. A sensitive HTTP cache is set to no-store. Do not store the question or the token in local storage.
- POST turn and retry accept an idempotency key. The server assigns `turn_id`, `query_id`, and `run_id`. Retry keeps one user message, creates a new run, and a new budget with a rate limit. The response and the events state clearly which run is in effect. Cancel stops only a turn owned by that user. It does not call a business tool.
- Every event has `query_id`, `run_id`, `facts_revision`, `snapshot_revision`, and `event_sequence`. The snapshot may be null before it is pinned. From the moment evidence exists, the same snapshot must be used inside the run. The SSE ID is the combination of query, run, and sequence. Last-Event-ID resumes the correct run. It does not create a new generation on its own. The client accepts only the current run, drops a duplicate or old event, and does not stitch claims from two runs. A reconnect must authenticate again and check the ACL and policy before replaying. Incognito replays only what is still in RAM. When the TTL ends or the process restarts, return `SESSION_EXPIRED`.
- DELETE of memory or of a session deletes operational data and invalidates derivatives, cache, and jobs under C.4. The audit record and the deletion-request ledger keep only the metadata that is required. Do not return another person's content or session name. Deletion does not remove an approved source PDF, or a business audit record that has its own retention policy.
- The checklist uses the enum `passed/failed/unknown` and the standard names in D.7. The finding schema distinguishes conditional, needs_review, and blocked. Do not stream a raw claim that has not been validated. Passing a number check or a negation check is not treated as proof of meaning.
- **CORS security:** the development identity headers `X-Principal-Id` and `X-Roles` are removed completely from the CORS configuration when running in the standard or production configuration. They are opened only when the POC flag `DEV_ALLOW_IN_MEMORY_STORE=true` is on, so a client cannot forge rights.
- **Model Registry and runtime:** `is_safe_endpoint` allows loopback/localhost (`127.0.0.1`, `localhost`, `::1`) when `EVIDENCE_ALLOW_LOCAL_AI=true`, for Ollama/vLLM. Filter the denylist of sensitive environment variables (`_SECRET_DENIED`) for `secret_ref`. Automatically strip the reasoning tag (`<think>...</think>`) and markdown fences for reasoning models. Limit the AI-selection timeout to 70% of the query timeout, and degrade gracefully to the fixed pipeline when the model responds slowly.

| Operation | Required right or subject | Allowed effect |
|---|---|---|
| Query, session, history, memory, cancel/retry | USER or the right rag.query, plus the owner of the session, plus the ACL scope | Write technical state when a policy exists. Do not write business data |
| Upload/import, edit a node, accept/edit/reject an AI suggestion | CURATOR plus the document scope | Create or edit a draft only. Accept does not publish |
| Approve a document, version, amendment, or effectivity (hiệu lực) | REVIEWER plus the scope plus If-Match | Write the approved revision, then build and publish the snapshot atomically |
| Configure an account, role, provider, route, or domain | SYS_ADMIN plus the corresponding configuration right | Audit. Do not grant a right to read content by default |
| Approve Gold or the trap set | A REVIEWER or a designated specialist | Only confirm a case whose source has been read. Do not grant the right to tune held-out |
| Read the audit | AUDITOR plus the audit scope | Read metadata and evidence inside the right. Do not modify it |

A role is not inferred from the `/admin` prefix by itself. For a CURATOR-only account, a call to approve must be rejected and the snapshot must not change. An account with several roles has only the rights that were granted explicitly. A service that writes a session or an audit record does not become a tool the LLM can call on its own.

---

## F. Detailed implementation plan

### F.1 How to read the plan

- Each sprint has **work packages (WP)**: the work, the output, and the acceptance. It ends with a **gate**. Recognize a gate only after its preconditions have been met. Independent work may be done early, but a missing gate must be reported. Do not turn a mock, or a degraded state, into full acceptance.
- The plan **does not estimate time**. The SRS does not commit to a duration, and speed depends on the POC results. The owner sets the schedule after Sprint 0.
- Feature codes (Q, V, G, M, A, C, K, R, Z) refer to section C. Screen codes (S1–S14) refer to section D.
- Technical defaults are in B.6. Invariants are in B.3.

### F.2 Sprint and gate summary

| Sprint | Goal | Gate |
|---|---|---|
| 0 | A POC on real Windows: pgvector, PDF anchor, model, offline Local Mode, ADR-000/001/002 | ADRs locked; SRS v1.3; a footprint measured for real; pgvector, backup/restore, and Windows services running on the target machine |
| 1 | Document repository, node effectivity (hiệu lực), the ERD (including memory), the foundation frontend, Gold v0 | Import → parse → review → approve → snapshot runs on a real PDF; the resolver passes the full set of cases; Gold v0 (150–200 questions) is approved by a person who holds the business knowledge; tokens and the contrast test are green |
| 2 | Retrieval, evidence-first, guards against wrong retrieval, A4–A6, a performance baseline | BFS 2-hop versus the full chain; a pre-gate with 3 states; a stale snapshot; B0–B7 with real measurements; `wrong_doc_rate` / `wrong_node_rate`; a performance baseline; C1 at the rules tier |
| 3 | Model Router, Local/API Mode, claims, the two-phase UI, the Chat Agent, memory, and the P0 analysis and suggestions | Both API and Local modes run (Local is checked on a machine whose Internet is really disconnected); polarity/numeric/temporal regression is green; the widget, memory, and the trap set meet the threshold the owner locked; A1–A3 |
| 4 | Hardening, performance, Windows packaging, and the P1 items the owner chooses | Red team (memory, prompt injection, ACL leakage); performance regression; a successful restore on a clean machine; the footprint inside the demo ceiling |

### F.3 Default decisions

Use the table in B.6. The agent does not stop to wait on those points. Record an ADR when a different choice is made.

### F.4 Work streams and dependencies

Seven streams: **A** DB/ACL/effectivity · **B** Ingestion/Parsing · **C** Retrieval/Eval · **D** Validator/Workflow · **E** Model Router · **F** Frontend · **G** Platform/CI.

- Sprint 0 checks feasibility on Windows and on representative configurations. The POC chooses a compatible library and runtime. It does not fix a provider or a model. Profile B only proves the offline core. AI or local-model gates that are still missing must be reported separately.
- A (schema) blocks B, C, and D. B (nodes plus span) blocks C and the viewer display. The effectivity resolver (A) blocks the effectivity validator (D).
- Gold v0 (C) runs in parallel from the start of Sprint 1, but it needs real PDFs from Sprint 0 and a person to approve them.
- F starts design tokens, the viewer, and the split view when the OpenAPI schema is stable (end of Sprint 1). Before that, use a mock server.
- E (the router) is independent of retrieval. It only needs the schema `providers/model_profiles/stage_routes`.
- The widget and the USER desktop (WP 3.9) need an SSE contract that has a run_id (WP 3.4), EvidenceCards (WP 2.9), auth/ACL, and the shell POC in WP 0.5. The frontend and the native shell do not create a separate workflow or backend.
- One accountable lead is responsible for each WP. Backend/data leads 4.8 (red team, coordinating with retrieval and frontend). Retrieval/eval leads 4.9 (the P1 items the owner chooses, coordinating with backend and frontend). The UI part of a backend WP is a frontend contribution. The interface is not treated as a second owner in place of the lead.

### F.5 Sprint 0 — POC on real Windows

| WP | Work | Output | Acceptance |
|---|---|---|---|
| 0.0 | Place dossier 1.1, SRS v1.3, and the existing ADR-000 onto the prescribed repository paths. Keep v1.2.1 as history. Review the B.7 matrix | The current document set links correctly | Do not rewrite the specification or re-choose decisions that are already locked. Do not treat the presence of documents as completion of the technical WPs |
| 0.1 | The repository skeleton according to SRS §17. CI (prefer a Windows runner): lint, typing, unit tests, a migration check, a secret scan, and an SBOM. `dependency-manifest` (license, version, SHA-256, footprint). Declare the deployment profile installation.programs_root / EVIDENCE_PROGRAMS_ROOT and the dependency manifest according to B.8 | Repository + CI | CI is green on an empty repository. Source and scripts do not hardcode PATH or the LLM. The install root is read from configuration. The inventory records the relative path and the real path |
| 0.2 | PostgreSQL + pgvector **on Windows**: install an approved build, configure it, and run it as a Windows service. Measure exact-query performance. Backup and restore. The API and the worker run as Windows services. Install PostgreSQL/pgvector and the service wrapper under the tool-install root according to B.8 | ADR-001 (how to install and operate on Windows) plus an install script | `CREATE EXTENSION vector` and an exact `<=>` query run on the target Windows machine. A clean install can be reproduced. Backup and then restore onto a clean machine succeed. The service starts again by itself after a failure. If pgvector fails: the ADR proposes a remedy on Windows (which build, how to compile). The architecture is not changed yet. Binaries and helpers resolve through the manifest under the root. Do not use a global PostgreSQL outside the manifest. Do not hardcode an executable path |
| 0.3 | A native-PDF POC on 10–20 real PDFs: many clause levels, old files and TCVN3, scans, landscape rotation, CropBox. Compare pypdfium2 and pdfplumber | `pdf-anchor-coordinate-contract.md` plus a report | The highlight is correct across multiple lines, rotation, and CropBox. An uncertain mapping falls back to the page plus the quote. Record the correct rate on each file |
| 0.4 | A configurable NLP/model POC: Underthesea; an ONNX embedding/reranker without PyTorch if that is compatible; an LLM API or a local runtime according to the Registry, with no hardcoded model, provider, or endpoint; check the license, the prefix, the hash, and the trust_remote_code policy; install the runtime, tools, and the model/package cache under the configured root according to B.8 | ADR-002 plus a footprint report plus a trial configuration with secrets masked | Check each capability, format, and runtime. A GGUF model, or a local LLM format that has been verified, is allowed. A missing model or key is recorded as MODEL_NOT_CONFIGURED, or as a capability not yet checked. Do not simulate AI, and do not require one fixed model. The POC does not use a tool or model store outside the manifest or the global PATH. The model and the provider can still be changed by configuration |
| 0.5 | A thin E2E: auth, SQL ACL, upload of one PDF plus SHA-256, a viewer of the original bytes, FakeAdapter. A USER desktop-shell POC: login → Orb → panel → collapse/open, tray, DPI, and the hit-test region. verify-egress. The shell, helper, and runtime use only components already installed under the B.8 root | A shared backend skeleton plus a shell report | A user without the right does not see the document. There is no square background, stray shadow, or drag region covering text. There is no console. FakeAdapter tests the contract only. It does not count as real AI. Startup from the shortcut or the service does not depend on the global PATH or on a tool inside the source folder |
| 0.6 | A POC parser for legal references (`Điều X khoản Y điểm Z`, symbol number) — Article (Điều)/Clause (Khoản)/Point (Điểm) — plus the chain A→B→C on real PDFs | A report plus sample tests | The parse is correct on the sample set. An ambiguous case returns "không chắc" (not sure). It does not guess |
| 0.7 | A Local Mode POC with the Internet really disconnected: sign-in, PDF, lexical/extractive; add embedding, rerank, and LLM for each local capability that is configured; an egress guard plus a sample firewall rule; check the inventory of local runtime, tools, and the model store under the B.8 root | verify-egress plus a matrix of capabilities that have been checked and not checked, and a configuration with no secrets | There is no DNS or HTTP to the Internet. An internal LAN endpoint is used only according to the allowlist. Profile B is accepted as a feasible offline core with the limitation stated publicly. Missing dense, rerank, or generation must not be recorded as those stages having been checked, and it does not replace the S3 AI gate. A missing root or dependency reports an error. It does not fall back to another location, and it does not download or install online on its own |

**Gate S0:** ADR-000/001/002, SRS v1.3, the footprint, and pgvector/backup/restore/Windows services have evidence on the target machine. The USER shell POC has a report. PDFs and hashes are in `evaluation/corpus_public_real`. The offline-core portion may be met under profile B when the model is not yet ready, but the AI capabilities that have not been checked are reported separately and are not recognized as passed. A platform failure means an ADR with an approach that fits Windows. Do not change the requirement, and do not lower the S3 AI gate.

### F.6 Sprint 1 — Document repository, node effectivity, Gold v0

**Stream A/B (data foundation)**

| WP | Work | Acceptance |
|---|---|---|
| 1.1 | The AI designs the entire ERD (tables, relations, foreign keys, constraints, and version history) and creates the migration plus database tests according to SRS §10. It checks consistency, integrity, and authorization itself. This includes principal/ACL, categories, documents/versions, `source_provenance`, pages/spans, nodes, references, amendments, reviews, snapshots, jobs, and audit. **Add** foreign keys, RLS or a security view, exclusion/check constraints for intervals, `unresolved_targets`, and append-only audit. Fix the illustrative DDL: `evidence_groups.query_id` and `citation_id` must have real foreign keys | Migration up and down have tests. The ACL test does not leak. Do not copy the illustrative DDL into production. Separate tests for relations of effectivity, amend (sửa đổi), supplement (bổ sung), and repeal (bãi bỏ) down to each Article/Clause/Point, and for version history. The ERD is accompanied by a self-check report. Present to the owner only the important business principles |
| 1.2 | Auth with RBAC+ABAC. Category CRUD: create, edit, hide, soft-delete, restore, a tree of configurable depth, cycle prevention, many-to-many, and JSON/CSV import/export with validation | SYS_ADMIN does not read content by default. A soft delete does not delete the original file. A document whose right was lost is not revealed |
| 1.3 | Source ingestion (arbitrary URLs are blocked by default; the `domain_allowlist` table is added, edited, or disabled by an admin in the UI after verification, and every change is audited; PDF upload from the machine supports a single file or selecting many files in a sequential batch, with independent metadata and a two-layer duplicate check of SHA-256 bytes plus an NFC content fingerprint; only an `approved` document enters the repository; a valid domain does not mean the document is still in effect): `import-url` (DNS pin/recheck, block private/local, limit redirects and size), `upload` (magic bytes, quota, SHA-256), an immutable copy, and provenance | Test SSRF, a redirect into the internal network, and a fake-MIME file. A hash change at the same URL means a new version waiting for approval. A URL outside the allowlist is blocked. If a domain is disabled, import stops. A byte-identical duplicate is blocked with 409. A content duplicate warns on the draft. A file with bad structure, hash, or metadata cannot become approved |
| 1.4 | Job queue: `SKIP LOCKED`, lease, heartbeat, a retry cap, cancel, an idempotency key, and backpressure | Two workers do not parse the same version. Cancel stops the right job. Errors are redacted |
| 1.5 | Native parse of each page. Diagnostics (the character `�`, the rate of valid syllables, text coverage, reading order). Detect TCVN3/VNI and convert the encoding with a reverse check. The status `needs_ocr` plus an OCR-plugin interface (the runtime is not installed). `extraction_method` per page | A bad page **never** becomes a verified quote. A scanned page goes to `needs_ocr` |
| 1.6 | Tree parser: Chapter/Section/Article/Clause/Point/Appendix. An unstructured administrative document (văn bản) is handled by heading or by page (do not invent an Article or a Clause). `text_indexed` has a breadcrumb. An applicability header. `node_references` are resolved at ingest, and unresolved ones are flagged. `parse_confidence`. A review queue prioritized by risk | Tests on real PDFs: a skipped clause, a reference "khoản 1 Điều này" (clause 1 of this Article), and an official dispatch (công văn) that has no Article |
| 1.7 | **Effectivity:** `node_amendments` (the CURATOR prepares the draft, the REVIEWER approves), an amendment-chain resolver that runs to a fixed point (it detects a cycle, a break, an overlap, or a conflict; a resource guard fails closed; it does not leak an administrative document outside the ACL), a snapshot staged and then published atomically by `snapshot_revision`, `source_review_revision`, stale fails closed, a cache-invalidation hook, and audit | Test: A→B→C→D beyond 2 hops is still correct. A cycle, a missing edge, or a conflict means `temporal_unknown`. A worker failure means `SNAPSHOT_STALE`. Roll back when the cutover fails |
| 1.10 | Memory ERD: session, state, summary, user memory, retrieval hints, and the administrative-document map. Constraints for a real delete and for retention | Tests for ACL, delete, and expiry. There is no path that turns memory into a citation |

**Stream F (foundation frontend)**

| WP | Work | Acceptance |
|---|---|---|
| 1.8 | A design-token module according to D.2 (including the additional tokens). An automatic WCAG 2.2 AA contrast test. Lint that forbids hardcoded HEX. `PdfViewer` (original bytes, anchor, an honest fallback). `AmendmentBanner` in two positions (toolbar plus next to the highlight). `CuratorSplitView` (autosave of a draft is not Approve, `If-Match`, a shortcut does not approve while typing, confirmation when editing effectivity or a batch). `CategoryAdmin`. `CuratorQueue`. The Allowed domains screen (S8). A mock server from OpenAPI | Image snapshots for `active/modified/repealed/suspended/not_yet_effective/unknown`. Keyboard and screen reader. The banner has a text label and an icon, not color alone |

**Stream C (evaluation)**

| WP | Work | Acceptance |
|---|---|---|
| 1.9 | **Gold v0 of 150–200 questions** (replacing the target of 50–100) from PDFs of real official administrative documents. The agent reads the PDFs itself and drafts the question, the reference answer, and the evidence (căn cứ). Each question has the administrative-document symbol number, the article/clause/point, the excerpt, the version, the time of application when that is relevant, and the source URL or hash. Coverage: a direct question, a situation with many conditions, an exception, an amending administrative document (including the chain A→B→C→D), transitional provisions, a repealed administrative document, insufficient evidence, outside the ACL, ordinary wording, text without diacritics, an abbreviated symbol number, and a PDF with a broken font. The agent checks structure, citations (the quote matches `text_original`), and duplicates itself. Split calibration and held-out by scenario_group_id. Rephrasings, or questions about the same situation, are not split across the two sets. The proposed ratio of about 30/70 is by case count, but it does not break a group. Operational regression is separate from held-out. The manifest, corpus, and split revision are frozen before tuning. The review screen is S11 | Each case has a status from draft to reviewed by a person who holds the business knowledge. **Only an approved case may be used as a standard.** The AI does not certify an answer itself. The duplicate report and the citation check pass on every case. A script checks case ID, scenario_group_id, and near-duplicate paraphrases or situations between calibration and held-out. Freeze split_revision before tuning. The corpus is separate from the business repository. UI fixtures live in `synthetic_ui_fixtures` |

**Gate S1:** import → parse → review → approve → snapshot runs through on a real PDF. The resolver passes the full set of cases in WP 1.7. Gold v0 (150–200 questions) has been approved by a person who holds the business knowledge. Tokens and the contrast test are green.

### F.7 Sprint 2 — Retrieval and evidence-first

| WP | Work | Acceptance |
|---|---|---|
| 2.1 | `vietnamese_nlp`: NFC plus a tone-mark mapping table (`hòa/hoà`, `thúy/thuý`) checked both ways and versioned, `đ→d` separately, an offset map back to the original, canonicalization of symbol numbers (keep the original value plus a standard key), and an alias dictionary managed by the curator | A two-way test. `text_original` is never modified |
| 2.2 | Lexical: `L1_WORD` (Underthesea, fixed words), `L2_SYLLABLE` (uni/bigram), `text_folded` at a low weight. FTS with `tsvector` plus `setweight` A/B/C, and GIN. The ACL is in SQL. Store the tokenizer and index revision. **Do not call `ts_rank` BM25** | `EXPLAIN ANALYZE` shows the index being used. An ACL test does not leak through the tokenizer |
| 2.3 | A deterministic Legal Reference Router (B0): bypass Analyze only when the match is **unique, approved, inside the ACL, and matches as_of_date** | Tests for a correct, incorrect, duplicate, and ambiguous symbol number and Article/Clause/Point. Ambiguous means return to Analyze |
| 2.4 | Dense: `EmbeddingAdapter`, `embedding_indices` plus `node_embeddings` with their own revision, an exact `<=>` on `authorized_nodes`. Changing the model means a new index in parallel, then a cutover. The contextual prefix stays behind a flag and OFF | Do not mix vectors from different models. Test a model switch. HNSW is only a POC for ACL-filtered recall, and it is off by default |
| 2.5 | Fusion: RRF. Grouped RRF by aspect (a missing `required` aspect means `uncovered`). A 3-branch pre-gate calibrated by model, category, and query type on the calibration set (do not touch held-out). Conditional rerank of the top 12, with a window that keeps negation, exceptions, and transitional provisions | Test false refusal, no-answer, and a low cosine whose source is correct and must not be dropped early. Do not use RRF as a threshold |
| 2.6 | Context expansion: auto-merge when there are at least 2 clauses of the same Article. A bounded BFS with `max_hops=2` (visited, `max_expanded_nodes/tokens`, a deadline, ACL plus a time filter **on every step**, `partial_graph`). Expansion outside the category only when policy allows it, and it is displayed clearly | Test a cycle, depth, the token cap, and cross-scope. When the budget is exhausted, `coverage.partial_graph=true` |
| 2.7 | Evidence: `citation_records`, a quote hydrator, a citation validator (ACL at retrieval, at generation, and when a citation is opened; the span matches the version, node, page, and hash), a numeric/date/period validator, a Polarity and Modality validator (tested equivalents are allowed, `không quá ≈ tối đa`), the claim schema in §6.2, and an allowlist of `evidence_ids` | Test `15→30 ngày`, `không quá↔ít nhất`, `có thể↔phải`, and dropping `trừ trường hợp`. Measure false positives. Do not claim that the validator guarantees absolute correctness |
| 2.8 | Benchmarks B0–B7 plus ablation on calibration and regression. Pin the corpus, the split, the model/tokenizer/prompt/config revision, the protocol, and the candidate before the lock-in evaluation | Report the confidence interval, missed exceptions, false abstention, over-expansion, and ACL leakage. Held-out runs only in a lock-in round, according to the protocol. Do not tune after seeing the results and then report the same set as independent |
| 2.9 | The API `/query/evidence` and `/citations/*`. `EvidenceCards`, `NodeToc`, a click that opens the correct PDF, version, and anchor, and 4 kinds of feedback into the curator queue | The click opens the correct page. The banner matches the node and `as_of_date`. The link goes to an amending administrative document that has been approved |
| 2.10 | A session service, plus rewriting a follow-up sentence, plus displaying "Đang hiểu là" (Understood as), plus asking one question again | A follow-up sentence points at the correct object. A missing condition means ask again. Do not guess |
| 2.11 | Administrative-document routing, metadata filters, version deduplication, and `retrieval_diagnostics` (L0–L2) | Measure `wrong_doc_rate` / `wrong_node_rate` on Gold. There is an ablation |
| 2.12 | Retrieval hints approved by the curator, plus alias expansion with an audit | A suggestion that has not been approved does not affect ranking |
| 2.13 | A performance baseline, precomputation at index time, and a connection pool | A P50/P95 report by stage on the target machine |
| 2.14 | Rules for points to notice (A4), a deterministic diff (A5), and a relatedness graph (A6) | Tests on real PDFs. The diff matches approved text. A6 does not reveal a node outside the ACL |
| 2.15 | A rules-tier suggestion detector for the curator: amendment relations, unresolved references, and abnormal nodes (C1 a, b, d) | Precision and recall on a labeled set taken from real PDFs. The curator approves the labeled set |

**Gate S2 (a release gate, not P1):** BFS 2-hop versus the full-chain resolver; a pre-gate with 3 states; a stale snapshot plus a worker failure; Gold v0 runs B0–B7 (approved cases only; the final evaluation is on held-out) with real measurements; a performance baseline; `wrong_doc_rate` / `wrong_node_rate`; A4–A6 and C1 at the rules tier.

### F.8 Sprint 3 — Model Router, claims, Chat Agent, memory, analysis

| WP | Work | Acceptance |
|---|---|---|
| 3.1 | A Model Registry by capability, a Hybrid Multi-LLM architecture (each stage chooses a model through the Registry), and two operating modes, API Mode / Local Mode: `OpenAICompatibleAdapter`, `AnthropicNativeAdapter`, and `LocalInferenceAdapter` written in-house (timeout, idempotent backoff, a circuit breaker, and limits on redirects and endpoints). Secrets are encrypted and masked, and cannot be read back. An endpoint test uses only synthetic data | Do not use LiteLLM. Test each compatibility feature. Do not assume rerank or JSON-schema support |
| 3.2 | API Mode (Internet is available; embedding/reranker are local or through an API; only data the policy allows is sent; fallback stays inside the permitted API scope) and Local Mode (the Internet is disconnected completely; the LLM, embedding, and reranker are 100% local; fallback uses only internal models). Egress policy follows the formula in §8.4 with the condition `mode == API`. Fallback stays inside the same privacy zone. Audit every route decision | Remote denied means `REMOTE_AI_DENIED`. Local Mode has no DNS or HTTP to the Internet, and it uses only an approved internal endpoint (an egress guard plus a Windows Firewall rule). Search, embedding, rerank, analysis, and PDF viewing run fully when the machine has no Internet. Sign-in and startup do not call an outside service. Models and updates are imported by offline media with a hash check. A local failure does not turn remote on by itself |
| 3.3 | A fixed Analyze/Generate workflow, with a total llm_attempt_budget=2 per run, counting errors, timeouts, retries, and fallback. Rules first. Extractive when the model or the budget is missing. Evidence is in EVIDENCE_DATA | Test the counter in the adapter: no more than two LLM requests. The P0 summary is in code. A2 does not add a call. On an error or an exhausted budget, valid evidence is still returned. There is no loop |
| 3.4 | OpenAPI/SSE according to E: query_id + run_id + facts_revision + snapshot_revision + event_sequence; idempotency, cancel, an explicit retry, and reconnect. The snapshot is null before it is pinned, and consistent after evidence | An old event or replay does not overwrite a new run. Reconnect does not call the model again. Recheck the ACL and policy when emitting an event. Incognito replays RAM only. Do not stream a raw claim that has not been validated |
| 3.5 | Frontend S1: `FactChips` dirty state, `DirtyFactBar`, `EvidenceGroupTabs`, `TwoPhaseSkeleton` (a neutral sentence), `CoverageChecklist` split into `source_verified / effective_checked / applicability_checked / claim_supported`, status labels, and the `stale` label | Editing 3 chips produces only 1 requery. Copy and print keep the scope, `as_of_date`, and the warning. The UI does not use "Đã xác minh X căn cứ" (Verified X pieces of evidence) |
| 3.6 | A complete Admin AI Configuration according to S9: API/Local configuration, provider/adapter/endpoint/model/runtime/artifact/secret/stage routes, a synthetic test, and key masking. Dashboard S12 | Changing a model inside a supported adapter is done through configuration, without a code change. No secret reaches the frontend or the log. When no model or key exists yet, the status is real, and the owner enters it later. The USER has no AI-configuration form |
| 3.7 | Memory service M1–M5. The P0 rolling summary is in code. Retention plus opt-in, an incognito RAM TTL, the Memory Center, invalidation, deletion of messages/summary/facts/cache, and cancellation of derivative jobs | Test that incognito content is not persisted, that the session is lost when the TTL ends, cross-user ACL, and that a delete is not written back by an old job. A claim does not point at memory. Deleted data does not return after a restore that applies the deletion ledger |
| 3.8 | A long-context manager: a token budget, evidence packing, processing by aspect, and `partial` | A question about many administrative documents still cites correctly. Over budget, the result reports `partial` |
| 3.9 | The User Portal is separate from the Admin Portal. AgentLauncher/Panel plus a viewer/workspace in the same session. The USER desktop shell is Tauri 2 according to W1–W8/S14: sign-in inside the app, Orb toggle, drag/resize, tray, logout/exit, and shared backend state | Native and web E2E, and server-side rights. No square background, stray shadow, transparent login, console, or drag region covering text. Collapse, open, PDF, and workspace do not lose the session. The USER has no administration menu. Local does not download an outside resource |
| 3.10 | L3–L5: conflict and exception, tier-1 claim checks, and a tier-2 POC | `unsupported_claim_rate` falls relative to the baseline, and false rejection does not rise |
| 3.11 | A trap set approved by a person who holds the business knowledge, with paraphrase and situation groups split correctly. A metrics dashboard. Freeze the candidate and the config before the lock-in evaluation round | Regression is used during development. The trap hold-out is only for the lock-in evaluation. Do not reveal the answers to the person who tunes. A set that has been used to make a fix is marked, and an unseen set replaces it for a later claim of independence |
| 3.12 | Situation analysis (A1) and information still missing (A3) on FactChips | Every row has an `evidence_id`. A missing condition does not produce a conclusion. The trap set is not broken |
| 3.13 | Suggested next questions (A2) with a retrieval dry-run | Every suggestion that is displayed has evidence inside the ACL (checked by a test). Measure the click rate |
| 3.14 | The interface: the Analysis/Related tabs in the Chat Agent, and the AI-suggestions tab for the curator (S6) | E2E. Accept and reject write an audit record. The AI has no API that writes business data |

**Gate S3:** API Mode / Local Mode are checked with the real provider and model that were configured. Local is checked with the Internet disconnected, and an approved internal LAN endpoint is allowed. Polarity/numeric/temporal regression, the two-phase UI, memory, the trap set, and A1–A3 pass. The USER desktop goes through login → Orb → chat → viewer/workspace → collapse/open → logout. If a real key or model is not yet available, record that the AI gate has not passed. Independent work may be completed with a mock, but it must not be recorded as a real AI run.

### F.9 Sprint 4 — Hardening and Windows packaging

| WP | Work | Acceptance |
|---|---|---|
| 4.1 | A security and regression test set: ACL through the cache and `as_of_date`, cross-scope, prompt injection, XSS from a PDF, CSP, KV-cache isolation (if there is a local LLM), PDF mojibake, a curator missing approval, and zero-answer | Every bug from feedback has a gold test that reproduces it |
| 4.2 | Load and backpressure: a concurrency gate for LLM CPU, job position, and cancel. A test of 30–60 sessions. Measure `evidence_ready_ms` P50/P95 separately from `final_answer_ms`. Compare parallel versus serial versus CTE under load | The measurement records the environment. Evidence-first is still shown when inference is stuck |
| 4.3 | Packaging for Windows (installer, Windows services): Core Pack, a Model Pack manifest (id, sha256, license, revision, dimension, RAM/disk), and a Data Pack. A clean demo install **< 10 GB**, checked in CI. Report the size of Core, Model, PostgreSQL, and data separately. The installer places every tool and runtime that must be installed under `E:\Programs` through the deployment configuration, including caches and stores the project manages | `measure-footprint` runs in CI. PyTorch and full ML extras are not included by default. Preflight the root, permissions, and disk space. The inventory's real path is the correct root. There is no hardcoded PATH or LLM, no global install, no AppData or Program Files install, and no quiet drive change |
| 4.4 | Encrypted backup plus restore onto a clean machine. Retention for audit, memory, and backup, the latest deletion-request ledger, SBOM, license, an offline runbook, the API, and the desktop client. The runbook records the install root, the dependency manifest, and how configuration is loaded. Data and backups follow their own configuration | A restore that contains sample data which was deleted: apply the deletion ledger before opening the service, and do not restore that content into history or the cache. If reconciliation is missing, do not open access yet. Endpoints and paths are configured through the deployment environment. Secrets are entered or restored by the operator according to policy. Do not copy a secret from the old machine. Restore and reinstall keep the correct tool-install root. Do not copy an old machine path into source, and do not move data on your own |
| 4.5 | Gold extended beyond v0 (150–200 questions) **when a reviewer is available**. P1 (PyVi, BM25 re-score, ParadeDB, HNSW, ONNX INT8, KV prefix) is opened only if a benchmark or an ADR proves it | Do not turn it on by default before it passes non-regression |
| 4.6 | Optimize and separate the embedding, analysis, and retrieval caches according to C.7. Analysis and retrieval stay OFF until the fingerprint and invalidation are sufficient. Measure regression | Test the same question with a different user, session, facts, memory, scope, as_of_date, ACL, policy, index, or model. Incognito has no durable cache. Accuracy does not regress. Measurements include the environment |
| 4.7 | Check the widget and the desktop against W1–W8/S14: auth, Orb toggle, opaque login and panel, the drag region, resize, tray, workspace/viewer, stop/retry, and logout. Responsive at 320/768/1024/1280px, DPI at 100/125/150/200%, multiple monitors, keyboard, contrast, and reduced motion. Check the native build after install at the B.8 root, with a tool outside the manifest not present on the test process's PATH | There are images and logs on the target Windows machine. The two interactive regions do not overlap. There is no square background, stray shadow, or console, and content is not lost on collapse or open. Measure page load before and after. A unit test or a build does not replace real native acceptance. The Orb, the chat, and the viewer still run on the declared dependencies. A missing root or tool is shown clearly. There is no path fallback |
| 4.8 | Backend/data leads the red team: prompt injection, memory poisoning, a cross-user leak, context-cache leakage, incognito persistence, delete/restore, and an old job. Retrieval and frontend coordinate | There is no leak. Deleted content does not come back. Feedback that has not been approved does not change ranking. The report names the lead, the test cases, the data, and the part that was not checked |
| 4.9 | Retrieval/eval leads the P1 list the owner chooses: A7–A10, D1, C1 (c, e). Backend and frontend coordinate, and items that are not chosen are stated clearly | Each chosen feature has a test or a metric, and the owner locks it. `unsupported_claim_rate` does not rise. Do not turn P1 on by itself, and do not use a held-out set that has already been seen in order to tune |

**Gate S4:** red team, cache, and memory pass; restore does not revive deleted content; performance regression and real desktop acceptance pass; the footprint is inside the demo ceiling; the P1 items the owner chose pass acceptance. Do not use an old test or build from a project that was lost as current evidence.

### F.10 End-of-WP report template (mandatory)

```text
WP: <id> — <tên>
Trạng thái: Xong / Xong một phần / Bị chặn
Đã làm: <danh sách ngắn>
Test: <tên test + kết quả thật, số pass/fail>
Số đo: <nếu có; ghi môi trường, phiên bản, corpus hash>
Quyết định/ADR mới: <id>
CHƯA XONG / bị hoãn: <liệt kê rõ, kèm lý do>
Rủi ro / cần người quyết: <nếu có>
```

The section "CHƯA XONG" (NOT DONE) must not be left empty by omitting it. Do not change the acceptance criteria in order to make tests green.

### F.11 Work that needs a person (the agent cannot substitute)

- **Business rules:** approve the important business principles in the ERD (relations of effectivity, amend, supplement, and repeal down to Article/Clause/Point; node status) and the sequence `ingest → review → retrieve → evidence → claims → citation-click`, at the start of Sprint 1. Approval of every technical detail is not required.
- **Correctness of evidence:** a person who holds the business knowledge approves the Gold v0 sample answers (150–200 questions) and the trap set before they are used as a standard. The CURATOR handles drafts and hints. The REVIEWER approves documents, effectivity metadata, and amendment relations that affect the evidence.
- **Access rights:** approve the remote-AI policy per category (API Mode); who may see the Chat Agent, by role; the rights mapping to the personnel-management app if it is integrated.
- **Security and privacy:** an admin verifies and approves each domain that enters the allowlist; confirm the Local Mode configuration and the Internet disconnect at the network infrastructure; lock the default retention period for conversation memory and the kinds of data that may be stored.
- **Acceptance thresholds:** the owner locks the thresholds for the anti-hallucination metrics and the latency target after a baseline exists; chooses which P1 features to do first (C.5); the curator decides to accept or reject each AI suggestion.
- **Confirm the assumptions in B.6**, in particular: whether the user may choose the mode, the Gold split ratio, and the trap-set size.
- **Provide (this is not an approval):** a target Windows machine on which to measure footprint, latency, and backup/restore.

### F.12 Principal risks

| Risk | How the plan handles it |
|---|---|
| pgvector has a problem on Windows | WP 0.2. The ADR proposes a remedy on Windows (which build, how to compile) before an architecture change is discussed |
| Blocking a connection inside the application cannot replace a real network disconnect | WP 0.7 and 3.2. The agent provides an egress guard and a sample firewall rule. Disconnecting the Internet at the infrastructure is guaranteed by the operator |
| A Vietnamese embedding or reranker model does not run on ONNX, or it is blocked by a license | WP 0.4. Profile B does not need an LLM or dense search |
| An old PDF has a broken font, or the bounding box is misaligned under rotation or CropBox | WP 0.3 and 1.5. Fall back to the page plus the quote. Do not highlight the wrong place |
| An amendment chain is missing an administrative document that is not in the repository | The resolver reports `temporal_unknown`. It does not assert "không sót sửa đổi" (no amendment was missed) |
| Gold of 150–200 questions needs a lot of review time from the person who holds the business knowledge | The agent drafts the citations in full and self-checks first. Review is done in batches. A case that is not yet approved does not count toward the standard. Report clearly how many cases have been approved |
| Mixing Gold with threshold tuning biases the evaluation | Separate calibration and held-out. A script checks that they do not intersect |
| Local LLM CPU congests at 30–60 sessions | Evidence is separated from generation. Use a queue and backpressure. Use an extractive template |
| Dependencies and disk use grow | The manifest plus CI measure the footprint. The demo ceiling is < 10 GB |
| Old memory after the snapshot changes | Attach the revision plus the label "cần kiểm lại" (needs recheck) |
| Poisoned memory or hints | Only curator approval makes them take effect. User feedback does not change ranking by itself |
| A new check layer over-refuses or slows the system | Watch false rejection and `evidence_ready_ms` after each layer. Each layer sits behind a flag |
| Analysis is read as legal advice | Three labels, Căn cứ (Evidence) / Phân tích (Analysis) / Gợi ý (Suggestion). Do not conclude when a condition is missing. A notice sits at the end of the result |
| The curator is overloaded by AI suggestions | Rank by risk, limit the number of suggestions per turn, and measure `suggestion_acceptance_rate` |

### F.13 Mandatory release-gate cases (summary; the full P0 list is in SRS §16)

- ACL leakage: through lexical search, vector search, rerank, cache, tokenizer, citation, viewer, memory, suggestions, and the relatedness graph.
- SSRF, redirects, and fake MIME; a URL outside the allowlist; prompt injection and XSS from a PDF.
- Effectivity: the chain A→B→C→D; a cycle; a missing edge; a conflict; a stale snapshot; cutover rollback; `as_of_date` before the amendment date.
- Retrieval: a pre-gate with 3 branches; no-answer; a low cosine whose source is correct; a neighbor mix-up (Article 15/150); a false premise.
- Claims: numeric/date, polarity/modality, a quote hydrated by the backend, and a claim that points at memory is rejected.
- Local Mode: no Internet connection; an internal endpoint only according to the allowlist; a full run when the Internet is disconnected; no automatic switch to the API when the Local LLM fails.
- Viewer: the highlight is correct (multiple lines, rotation, CropBox); an honest fallback; the PDF bytes do not change.
- Operations: backup/restore onto a clean machine with reconciliation against the deletion ledger; the Windows service starts again by itself; footprint < 10 GB.
- The LLM is configured as API or Local, with no fixed provider, model, endpoint, key, or path. Try changing two representative configurations inside a supported adapter. Count retry and fallback inside the budget.
- PATH and installation: every project tool and runtime that is installed, and the corresponding cache and store, are at `E:\Programs` through configuration. Check that the real path is inside the root. Do not hardcode PATH or the LLM, and do not depend on a global tool. A missing root or dependency does not fall back to another path.
- Desktop: User and Admin are separate, the Orb is a round toggle, login and the panel are not transparent, there is no console or stray shadow, drag and resize do not cover content, collapse/open/PDF/workspace keep the session, and tray, logout, and exit behave correctly.
- Gold: check the split by situation group. Held-out content is not used to tune. Record the candidate, config, corpus, and split revision.

---

## G. Startup prompt and appendix

### G.1 Prompt given to the implementing AI

> You are the coding agent implementing the Vietnamese Evidence RAG Agent on Windows. Read `docs/SRS_v1.3.md`, `docs/HOSO_BAN_GIAO.md`, and `docs/architecture-decisions/ADR-000.md`. If you are in the handoff package, use the mapping in the README. SRS v1.3 and ADR-000 already exist: WP 0.0 integrates and reconciles them. Do not rewrite the specification or re-choose an owner decision.
>
> Implement the WPs in section F in order, including memory, anti-hallucination, analysis and suggestions, and the USER desktop. The USER opens the shortcut, signs in inside the Windows app, uses the round Orb at the right corner of the desktop, clicks to open or collapse the chat, and opens a PDF or the workspace in the same session. Drag, resize, tray, stop, retry, logout, and exit follow S14. The Admin Portal is separate from the User Portal and shares auth, the backend, PostgreSQL, the document repository, and RAG. Do not create a chatbot, or a database on each USER machine. Keep the theme, the tokens, and text that is easy to read. The Orb has no square background and no stray shadow. Login and the panel are opaque. The drag region does not cover text. Do not show a console.
>
> Configure the LLM as API or Local through the Registry/Router, per stage: adapter/provider, an approved endpoint or runtime, model ID or artifact, params, revision, secret reference, and fallback. Do not hardcode rights, provider, model, endpoint, key, host, port, or path. Use configuration, the manifest, and a platform API. API Mode has the Internet and permitted egress. Local Mode disconnects the Internet, uses only an approved internal runtime or endpoint, and does not switch to the API on its own. A POC model is not a mandatory model. The owner enters the key later. When no model or key exists yet, finish the feature and the contract tests, return real evidence (căn cứ) or a real extractive answer, and do not simulate AI or recognize a provider gate as passed.
>
> Do not hardcode PATH or the LLM. Every tool and runtime the project installs in order to build, install, or operate the app must live under the root `E:\Programs` that the owner locked. The root is only the value of the deployment profile `installation.programs_root` / `EVIDENCE_PROGRAMS_ROOT`. It is not embedded in code or scripts. Resolve the executable, model, artifact, and tool cache from the manifest under the root. Do not use a fallback to PATH, a global location, AppData, or Program Files. If the root or a dependency is missing, report the error. Do not change the drive on your own. Each machine installs only the components for its role. Business data and backups have their own configured paths. Do not move them on your own. Follow B.8 and SRS §25.9.
>
> Follow B.3, B.7, B.8, and SRS §25: the CURATOR drafts, and the REVIEWER approves. The analysis and retrieval caches stay OFF until the fingerprint and the tests are sufficient. Incognito is RAM only. Storage happens only with retention plus opt-in. Delete derivatives, cache, and jobs. On restore, apply the deletion ledger. Gold is 150–200 cases approved by a person who holds the business knowledge, split by situation group, with regression separate from held-out. llm_attempt_budget=2 counts timeout, retry, and fallback. The P0 summary is in code. Scope is SELECTED or ALL_AUTHORIZED, and the server always checks the ACL. SSE uses query_id, run_id, revisions, and sequence. An explicit retry does not mix turns.
>
> The AI builds the ERD, the migrations, and the database tests itself, and it does the maximum amount of technical work that can be verified. A person is needed only for business principles, access rights, security, and correctness of the evidence. Do not certify Gold yourself. Do not invent a legal administrative document (văn bản). Do not add a forbidden dependency. Do not use an old result as current evidence. If a key, a model, a reviewer, or a machine is missing, report the gate that is still missing and continue the independent work. At the end of each WP, report with F.10, including measurements and the environment, and the section CHƯA XONG (NOT DONE).

### G.2 Handoff file list

| File | Role |
|---|---|
| `01_HOSO_BAN_GIAO_Vietnamese_Evidence_RAG_Agent.md` | This dossier: features, UX/UI, API, plan, and prompt |
| `02_Vietnamese_Evidence_RAG_Agent_SRS_v1_3.md` | The current technical SRS, including §25 |
| `03_ADR_000_QUYET_DINH_BAN_GIAO.md` | Records the decisions, the defaults, and the acceptance boundary |
| `02_Vietnamese_Evidence_RAG_Agent_SRS_v1_2_1.md` | The historical copy, kept unchanged, and not used as the current requirement |

### G.3 Short glossary

**as_of_date:** the application date of the search. **Evidence:** a verified source passage together with its location. **Node:** one unit of an administrative document (Chapter/Section/Article (Điều)/Clause (Khoản)/Point (Điểm)). **Effectivity snapshot (Snapshot hiệu lực):** the computed result of the amendment chain, published atomically by revision. **Fail-closed:** when the system is not sure, it blocks or refuses instead of letting the item through. **Held-out:** an evaluation set that is not used to tune thresholds. **Dry-run retrieval:** a trial retrieval to check whether a suggestion has evidence (căn cứ) inside the user's rights.
