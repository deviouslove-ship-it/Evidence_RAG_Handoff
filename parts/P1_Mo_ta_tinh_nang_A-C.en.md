**Language / Ngôn ngữ:** [Tiếng Việt](P1_Mo_ta_tinh_nang_A-C.md) · English

English counterpart of `parts/P1_Mo_ta_tinh_nang_A-C.md`. The Vietnamese file is the original. These parts are extracts of `docs/HOSO_BAN_GIAO.md`.

# IMPLEMENTATION HANDOFF DOSSIER — Vietnamese Evidence RAG Agent

Dossier version 1.1 · updated 2026-10-21
Basis: SRS v1.3 + the owner's decisions of 2026-10-17 and 2026-10-21; cross-checked against the history of the project “Agent tra cuu”, in particular the requirement to separate the portal from the USER application on Windows.

**This dossier contains:** A. How to use this dossier · B. Product overview and decisions already locked · C. Feature description · D. Detailed UX/UI design · E. Supplementary API contract · F. Detailed implementation plan · G. Startup prompt and appendix.

---

## A. How to use this dossier

**Required companion file:** `02_Vietnamese_Evidence_RAG_Agent_SRS_v1_3.md` — the current technical source (draft DDL, retrieval algorithm, API, benchmark, repository structure). The file `02_Vietnamese_Evidence_RAG_Agent_SRS_v1_2_1.md` is kept unchanged as history and is not used to take current operational decisions.

**Priority when sources conflict:** (1) new direction from the owner → (2) B.4, B.7, and B.8 → (3) this dossier → (4) SRS v1.3. The accompanying ADR-000 records the decisions; when placed in the repository, use `docs/SRS_v1.3.md`, `docs/HOSO_BAN_GIAO.md`, and `docs/architecture-decisions/ADR-000.md`. Do not create an additional competing specification. This update is documentation only. It does not prove that any work package (WP) or release gate is complete.

**Working rules for the implementing AI**

1. Work autonomously, with few questions back. For a point that is not yet locked: use the default in B.6 or F.3, record an ADR under `docs/architecture-decisions/`, and continue. Stop and wait for a person only for four groups: **business rules, access rights, security, and correctness of evidence (căn cứ)** (F.11).
2. A work package (WP) counts as done only when all of the following are present: code + migration + green tests + updated documentation + a report in the F.10 template.
3. Do the maximum amount of technical work that can be verified by code or tests (ERD design, migrations, database tests, parser, retrieval, UI, CI, benchmark).
4. Do not add heavy dependencies: PyTorch, full Docling, LiteLLM (both the SDK and the Gateway), Redis, Elasticsearch, Qdrant, Neo4j, RAGFlow, GraphRAG, or a mandatory LlamaIndex/Haystack. Pin every dependency by version and hash, and record the license and footprint in `dependency-manifest`.
5. Do not invent legal administrative documents (văn bản). UI fixtures carry the label "HƯ CẤU" (FICTIONAL). Benchmarks use only real public administrative documents, kept in a separate corpus.
6. Do not state figures that have not been measured ("<2ms", "giảm 60–70%" (a 60–70% reduction), "100% chính xác" (100% accurate)). Every number records the environment, the version, and the data.
7. Report unfinished parts honestly. Do not change acceptance criteria in order to make tests green.

**How to split the work across several AIs** (at the owner's discretion): the seven streams A–G in F.4 may be assigned to different AIs. To work in parallel: (a) the backend stream publishes **OpenAPI** at the start of Sprint 1; (b) the frontend stream uses a mock server generated from OpenAPI and the design-token module (D.2) until the backend is ready; (c) the evaluation stream shares `corpus_public_real`; (d) every stream submits ADRs and WP reports using the same template.

---

## B. Product overview and decisions already locked

### B.1 What the product is

A **Vietnamese question-answering platform with citations** over an approved repository of administrative documents (văn bản): laws (Luật), decrees (Nghị định), circulars (Thông tư), charters, procedures, and internal administrative documents. The user asks in natural language. The system finds the correct administrative document and the correct Article (Điều)/Clause (Khoản)/Point (Điểm), displays the **verbatim evidence (căn cứ) together with the original PDF page first**, and only then explains conditions of application, exceptions, effectivity (hiệu lực), and transitional provisions. When the evidence is not sufficient, the system says outright "chưa đủ căn cứ" (insufficient evidence) instead of guessing.

The system is **read-only advisory (tham mưu)**: it does not approve, it does not issue a decision, and it does not write business data.

Deployment is internal (LAN) on **Windows**, with two independent operating modes: **API Mode** and **Local Mode (fully offline)**.

### B.2 Users and roles

| Role | Does | Does not |
|---|---|---|
| USER (the person asking) | Signs in inside the Windows app, uses the Orb/chat/workspace, selects a category or everything within their rights, and views sources and their own memory | Does not see documents outside their rights; does not upload into the repository, manage accounts, configure models, or edit repository data |
| CURATOR | Ingests documents, assigns categories, checks extraction, saves draft nodes, and accepts/edits/rejects suggestions at draft level | Does not approve documents, versions, effectivity, or amendments (sửa đổi) unless also granted the REVIEWER right |
| REVIEWER | Approves documents/versions, amendment relations, and node effectivity | Does not change system configuration |
| SYS_ADMIN | Configuration, accounts, rights, the Model Registry, and the domain allowlist | **Does not by default read business content or confidential documents** |
| AUDITOR | Views logs and evidence within the permitted scope | Does not modify data |

Rights in the RAG module are **separate**. They are not inferred from a role in another application (for example a personnel-management app). A mapping must be granted explicitly.

### B.3 Invariants (a violation is a release-blocking defect)

- The agent is advisory only and READ-ONLY. It has no tool that writes, approves, or sends. It calls only allowlisted read services: `search_authorized_nodes`, `get_node_history`, `get_precomputed_references`, `validate_evidence`, `read_original_span`, `get_viewer_anchor`.
- **The LLM does not write the quote, and it does not create an ID or an article/clause number.** The backend hydrates `quote_exact` from approved `text_original`.
- **The ACL filters in SQL before** lexical search, vector search, rerank, cache, citation, and the viewer. The system does not reveal that a document exists when the user has no right to it.
- **Remote AI fails closed** (`remote_processing_allowed` defaults to FALSE). Local Mode does not connect to the Internet. It uses only approved loopback or internal-LAN endpoints, and it does not switch to the API on its own when the Local LLM fails.
- **Effectivity is at node level**, and the default is `unknown`. The CURATOR prepares the draft. The REVIEWER approves documents/versions and amendment/effectivity relations. The system does not infer "still in effect" from the issue date.
- Two-hop retrieval is not the effectivity resolver. The resolver walks the whole verified amendment chain to a fixed point. If it exceeds a guard, or if an edge is missing, it fails closed.
- Effectivity snapshot: atomic publish, with the revision pinned. If the snapshot is stale or failed, the result is `SNAPSHOT_STALE`. An old snapshot is not used to assert effectivity.
- The pre-gate has three branches (pass / uncertain → expand or rerank / insufficient → refuse). A min-max score or an RRF score is not used as an absolute threshold.
- The UI has two phases. "Sources/quotes have been checked" is not the same as "the claim has been verified". The sentence "Đã xác minh X căn cứ" (Verified X pieces of evidence) is not used when effectivity and coverage have not been proven.
- The original PDF is immutable (bytes are not changed, and new text is not overlaid). A different hash means a new version.
- PostgreSQL is the only database. There is no semantic answer cache, no auto-crawl, and no GraphRAG/ColBERT in the MVP.
- Color goes through design tokens. HEX is not hardcoded. Color is not the only signal.
- **Memory is never evidence.** The validator rejects a claim that points at memory.
- **The AI does not certify a Gold answer by itself.** Only a case approved by a person who holds the business knowledge becomes a standard. The held-out set is not used to tune thresholds.
- Arbitrary URLs are blocked by default. Only an approved document enters the repository. A valid domain does not mean the administrative document is still in effect.
- Windows is the official operating system. Do not add a mandatory dependency on Linux, WSL, or Docker.
- **Do not hardcode rights, a provider, an endpoint, a model ID, an API key, a model path, or a machine path.** The LLM is configured as API or Local through the Registry/Router. A POC model is only experimental configuration data.
- **Do not hardcode PATH or the LLM.** Every project tool and runtime that must be installed lives under `E:\Programs` through the `EVIDENCE_PROGRAMS_ROOT` configuration. Do not place a literal root in application logic. The mandatory policy is in B.8.
- The User Portal, the Admin Portal, and the desktop shell share authentication, the backend API, PostgreSQL, the document repository, and the RAG pipeline. Do not create a separate chatbot, database, or pipeline for the desktop.

### B.4 Owner decisions already locked (already synchronized into SRS v1.3)

| # | Topic | Decision |
|---|---|---|
| 1 | ERD | The AI designs the entire ERD, the tables, the relations, the foreign keys, and the constraints. It creates the migrations and the database tests itself. It checks consistency, integrity, authorization, and version history itself, in particular relations of effectivity, amendment, supplement (bổ sung), and repeal (bãi bỏ) down to each Article/Clause/Point. It presents to the owner only the important business principles |
| 2 | Sources and domains | Arbitrary URL downloads are blocked by default. An admin adds, edits, or disables a domain in the administration UI after verification. PDF upload from the local machine is allowed. Origin, file structure, hash, metadata, and content are checked before approval. Only an approved document enters the official repository. A valid domain does not mean the document is still in effect |
| 3 | Gold v0 | 150–200 questions drawn from PDFs of real official administrative documents. The agent drafts them, and a person who holds the business knowledge approves them. The AI does not certify them itself. Calibration is used to tune thresholds. Held-out is independent of threshold tuning and of training data. The split is by situation group and by rephrasing, not only by case ID |
| 4 | AI modes | The architecture is Hybrid Multi-LLM, but there are **only two operating modes**. **API Mode:** Internet is available; the LLM is reached through an API; embedding/reranker are local or through an API; only data the policy allows is sent; fallback stays inside the permitted API scope. **Local Mode:** the Internet is disconnected completely; the LLM, embedding, and reranker are 100% local; fallback uses only internal models; models and updates arrive by offline media |
| 5 | Operating system | Windows is official: PostgreSQL + pgvector, FastAPI, the frontend, the worker, and the local LLM run on Windows. Linux/WSL/Docker are not required. Sprint 0 only checks the pgvector installation, performance, backup/restore, and Windows services. If pgvector has a problem, propose a remedy on Windows before discussing an architecture change |
| 6 | AI memory | Memory for queries and long context (C.4) |
| 7 | Chat Agent | The USER uses the Windows app: open the shortcut, sign in inside the app, use the round Orb at the right corner of the desktop, click to open or collapse the chat, and open the workspace in the same session. A browser is not required. User and Admin are separate portals and share the RAG stack (C.3, C.12, D.5 S14) |
| 8 | Anti-hallucination | Add the eight layers L0–L7 and a trap set (C.6) |
| 9 | Accuracy and speed | Improvements sit behind flags and are measured. The cache has a gate (C.7) |
| 10 | Analysis and suggestions | 12 features A1–A10, C1, and D1. The P0 package is in the MVP. The P1 package follows the owner's priority (C.5) |
| 11 | LLM configuration | The admin configures API or Local: adapter, an approved endpoint or runtime, model ID or artifact, parameters, a secret reference, a route per stage, and fallback. The vendor, model, and endpoint are not fixed. The owner enters the API key later. Secrets do not go into the dossier |
| 12 | Scope and portals | The USER selects one or more categories, or “Tất cả danh mục được phép” (All categories I am allowed to use). In every case the ACL is filtered in SQL. SYS_ADMIN does not automatically have search rights. An account with several rights switches portals deliberately |
| 13 | PATH/LLM and tool installation | PATH and the LLM are not hardcoded. Every tool and runtime the project must install lives under `E:\Programs`. The root comes from the deployment profile or from `EVIDENCE_PROGRAMS_ROOT`. It is not embedded in code or scripts. Detail is in B.8 |

The automation/approval boundary: the agent does every technical task that can be verified. A person approves only business rules, access rights, security, and correctness of evidence.

**Changes already brought into SRS v1.3** (a historical crosswalk, not work waiting for the AI to redo)

| SRS item | Old | New |
|---|---|---|
| §0.1 D02, §8.1, §13.1 | Three modes HYBRID / API_ONLY / LOCAL_ONLY, with Hybrid as the default | Two modes, API Mode / Local Mode. Hybrid is the Registry/Router architecture that selects a model per stage. Profiles A/B/C remain deployment profiles. Remote still fails closed according to policy |
| §8.4 | `mode != LOCAL_ONLY` | `mode == API`; the remaining conditions stay as they are |
| §9.1 (top bar) | Choose `[Hybrid ▼]` | Show a read-only mode badge (see B.6) |
| §10, §13, §18 Sprint 0, §22 | Postgres on Windows or Linux, with the OS chosen in Sprint 0 | Windows is locked. `deploy/windows` is the baseline |
| §11.2, §12.3 | `import-url` according to a configured allowlist | The allowlist is a database table the admin manages in the UI, blocked by default |
| §15.1, §16, §18 Sprint 1 | Gold v0 of 50–100 questions | 150–200 questions, split into a calibration set and a held-out set |
| New items | — | Add the items: Memory, Chat Agent, Anti-hallucination layers, Analysis and suggestions |
| §9, §17–18, §25 | The in-browser widget is the primary description | Add the USER desktop shell according to history the owner has approved. Keep the backend and RAG unchanged. Turn the eight comments into contract and acceptance criteria |

### B.5 Scope that is not in this work

No auto-crawl. No semantic answer cache. No GraphRAG, ColBERT, Neo4j, Elasticsearch, Qdrant, or Redis in the MVP. No LiteLLM. SQLite is not the primary database. This module does not process business transactions (approval, discipline, commendation, or payment). Dark Mode is not in the MVP (it is P1). OCR is an exception plugin only, and its runtime is not installed by default.

### B.6 Assumptions the agent uses by default; the owner may change them

| Issue | Default | Change when |
|---|---|---|
| Mode shown in the UI | A read-only badge "API Mode" / "Local Mode". Only an admin changes it through configuration. The user does not switch it | The owner allows the user to choose, according to policy |
| PDF library | pypdfium2 | pdfplumber is clearly better on bounding boxes and tables in the POC |
| Viewer highlight | PDF.js plus an overlay layer drawn from quads | react-pdf-highlighter-extended passes the POC |
| Job queue | Procrastinate if the overhead is low | If it does not meet the bar: write `SKIP LOCKED` directly |
| Running Windows services | NSSM or a pywin32 service, chosen through an ADR | Another approach is required |
| Embedding/reranker | Chosen through the POC from the candidates in SRS §14.3. Local Mode uses only a model that runs locally | If no model passes: turn dense off with a flag and run profile B (lexical + extractive) |
| Contextual dense prefix | OFF | The POC shows a quality gain and does not increase missed exceptions |
| Auth | Local accounts plus the RAG module's role/ABAC | Integration with the personnel-management app comes later, with an explicit rights mapping |
| Tokenizer | Underthesea | Compare PyVi only in P1 |
| Number of recent conversation turns sent to the LLM | Configurable; the proposal is 3 | According to the benchmark |
| Gold split | A proposal of about 30% calibration / 70% held-out, recorded in an ADR | The owner locks it |
| Trap set | A proposal of 40–60 questions | The owner locks it |
| Retention period for conversation memory | The owner locks the policy. Until an approved policy exists, long-term conversation storage is OFF, and the session uses RAM only with a temporary TTL | Turn storage on after a valid retention policy and opt-in exist |
| Font | `Inter, system-ui, Arial, sans-serif`. Bundle Inter only after the license is checked. Local Mode does not download an external font | — |
| USER desktop shell | Tauri 2, following the desktop approach already approved in the history. Lock the version and runtime in the POC. Do not create a separate backend | Change the shell technology only by an ADR and an owner decision |
| Session that is not stored | RAM on the backend. Idle TTL of 30 minutes, configurable. Do not write content into PostgreSQL, logs, or a durable cache | The owner has a different session policy. Do not turn storage on quietly |
| Analysis cache | OFF. Turn it on only after a test whose key covers the whole context, and after a user-isolation check | Turn it on with a feature flag, an ADR, and invalidation |
| P0 conversation summary | A template or extraction done in code. Do not call a separate LLM | An LLM summary is P1, with its own job and quota, and it does not sit on the evidence-response path |
| Tool-install root | Locked as `E:\Programs` in the configuration `EVIDENCE_PROGRAMS_ROOT` / installation.programs_root. Every project tool and runtime that is installed lives under that root (B.8) | Change it only under new direction from the owner. Do not choose another folder on your own |

### B.7 Unified approach for the eight comments

| # | Approach chosen for the document | Where it lives, and how it is accepted |
|---|---|---|
| 1 | The CURATOR creates the draft. The REVIEWER approves. Accepting a suggestion does not publish by itself | C.8, E, WP 1.7/3.14. Test for 403, and test that the snapshot does not change when the right is missing |
| 2 | Separate the embedding, analysis, and retrieval caches. Analysis is OFF. The key contains every input that affects the result | C.7, WP 4.6. The same question with a different user, session, or facts must not hit the wrong cache |
| 3 | Incognito is RAM only. On restore, delete operational data and reapply the deletion-request ledger | C.4, E, WP 3.7/4.4/4.8. Deleted content must not come back |
| 4 | Profile B is accepted as a feasible offline core with the limitation stated publicly. It does not replace the gate for a real AI | C.9, WP 0.4/0.7/3.2. Models and APIs come from configuration and are not hardcoded |
| 5 | Split Gold by situation group. Regression is used regularly. Held-out stays locked until a lock-in round | C.10, S11, WP 1.9/2.8/3.11 |
| 6 | At most two LLM call attempts in one turn, counting retry and fallback. The P0 summary is done in code | C.3/C.4/C.9, WP 3.3. When the budget is exhausted, return evidence or an extractive answer |
| 7 | Assign one accountable lead for every WP. Backend leads 4.8. Retrieval/eval leads 4.9 | F.4, and the prompt for each stream. Collaboration does not replace the person who is accountable |
| 8 | The panel and the viewer sit side by side only when the width is sufficient. When space is short, switch to a single frame | D.4/S3/S14, WP 4.7. Check 320/768/1024/1280px, DPI, and multiple monitors |

**History read on 2026-10-21:** the chats “Thiết kế AI Agent tra cứu”, “Mô tả AI Widget”, “Tiếp tục triển khai dang dở”, and “Khôi phục project RAG”. Keep the product intent: separate User and Admin; the USER has a desktop app; an Orb toggle; keep the session when collapsing and opening; stop and retry; analysis that has evidence; the owner configures API or Local; text that is easy to read; and no window defects. Defects that were raised become acceptance cases. Do not inherit test accounts, secrets, machine paths, or treat an old test claim as a current result. The Navy/Blue palette and the motion constraints of the current dossier remain the standard.

---

### B.8 No hardcoded PATH or LLM, and the mandatory tool-install location

**Owner decision:** every tool, utility, and runtime that the project must install or package so the app can run lives under `E:\Programs`. This is the value of the deployment configuration `installation.programs_root` / `EVIDENCE_PROGRAMS_ROOT`. **It is not a path constant in source code.** Do not hardcode PATH, an executable path, a model path, a provider, an endpoint, a model ID, or an API key.

- The installer, launcher, and service read the root from an approved deployment profile or from an environment variable supplied by the deployment configuration. The two sources must agree. Source code, install and run scripts, migrations, the UI, and tests do not embed a literal drive or machine path. Change the root only when the owner gives new direction and the deployment profile is updated. Do not edit source in order to move the path.
- Each component has a subdirectory determined by the manifest under `<PROGRAMS_ROOT>/<product_id>/`: the app, runtimes, the database, tools, models, and tool caches. Use a path-join function or a platform API. Do not concatenate a drive string by hand. Provider and model names, and artifacts, always come from the Registry or the Model Pack manifest.
- The scope covers the Python and backend environment, PostgreSQL + pgvector, the LLM/embedding/reranker runtime, PDF/OCR tools when they are enabled, the desktop runtime, and the service wrapper. Extra build, install, and operations tools, if they must be installed, follow the same root. Install only the components a machine role and its capabilities actually need. Do not require a USER machine to install its own database or backend.
- Executables, DLLs and plugins, the package and model store, and tool caches that the project manages must be resolved from the dependency manifest under the configured root. Check that the real path is inside the root, and check version, hash, and license. Do not quietly use a copy from the global PATH, Program Files, AppData, Downloads, or the source folder. If a tool needs a PATH, build the PATH for the child process from the manifest. Do not modify the system-wide PATH.
- If the drive, the folder, or write permission is missing, or if a dependency does not support this location, report the error, block that component, and state an approach. Do not move to drive C or install globally on your own. The rule applies to what the project installs or packages. It does not require moving components that Windows already has.
- Source PDFs, PostgreSQL data, business logs, and backups have their own configured paths, separate from binaries and tools. Do not move data only because a tool-install rule was added. Locally installed models and runtimes, and tool caches, still belong under the root above. Configuration and manifests do not contain a plaintext API key.
- Each Windows machine installs project components under the same policy. A client installs only the client and runtime it needs. A server or inference node installs the matching components. A remote API provider is a configured service. It does not become a requirement to install a local model.
- Local Model Registry and runtime: load configuration from the database together with generation parameters (`params`: `temperature`, `max_tokens`, `json_mode`). Support a safe-endpoint check (`is_safe_endpoint`) that allows loopback/localhost (`127.0.0.1`, `localhost`, `::1`) when the flag `EVIDENCE_ALLOW_LOCAL_AI=true` is on, for local Ollama/vLLM. Filter the denylist of sensitive environment variables (`_SECRET_DENIED`) for `secret_ref`. Strip the reasoning tag (`<think>`) of reasoning models. Wrap AI-selection timeout at 70% of the query timeout, and degrade gracefully so the application does not hang.
- Acceptance: the dependency inventory records the root and the relative path or real path of each tool. A clean install and startup do not depend on the global PATH. A missing root or dependency reports the correct error and does not fall back to another path. Changing model, API, or Local configuration does not require a source edit. Check that code and scripts contain no hardcoded PATH or LLM. The literal `E:\Programs` appears only in approved deployment configuration data or policy, not in application logic.

---

## C. Application feature description

Priority marks: **P0** = mandatory in the MVP and in the release gate; **P1** = after the MVP, and it has a measurement. Feature codes are used as references in the plan (F) and in the design (D).

### C.1 Question answering with evidence (căn cứ) (USER)

| Code | Feature | Behavior | Constraints and safety | Priority |
|---|---|---|---|---|
| Q1 | Choose scope | Choose one or more categories, or “Tất cả danh mục được phép” (All categories I am allowed to use). A valid scope is required before a question. The administrative-document-type (văn bản) filter is independent. `as_of_date` defaults to today in the configured timezone | `scope_mode=SELECTED` needs valid `category_ids`. `ALL_AUTHORIZED` is resolved by the server into the categories currently granted. The ACL is still filtered in SQL. There is no wildcard that drops rights | P0 |
| Q2 | Enter a question and Analyze | The user enters natural-language text. `analyze` produces fact chips (subject, act/event, time, locality, dossier type, conditions) and query rewrites. It does not conclude | Rules first. A total maximum of 2 LLM call attempts per run, counting retry and fallback | P0 |
| Q3 | Fact-chip dirty state and requery | Editing, deleting, or adding a chip does not call again by itself. Show "Đã chỉnh sửa dữ kiện — kết quả bên dưới dựa trên dữ kiện trước đó" (Facts have been edited — the results below are based on the previous facts). The button "Cập nhật dữ kiện & Tra cứu lại" (Update facts and search again) sends one request with `base_query_id` and `base_facts_revision`. The old result keeps the label `stale` until new evidence (căn cứ) exists | A fact the AI inferred is not treated as confirmed by itself: `user_confirmed` / `extracted_unconfirmed` / `inferred_uncertain` | P0 |
| Q4 | Ask directly for an Article (Điều)/Clause (Khoản)/symbol number | The Legal Reference Router skips Analyze when the match is unique, approved, inside the ACL, and matches `as_of_date` | If the match is ambiguous, return to Analyze. Do not promise 100% | P0 |
| Q5 | Evidence first | Validated evidence cards appear first. The explanation appears after them (SSE). Cards are grouped by role: principal provision / subject / condition / exception / transitional / authority | Auto-merge is only UI organization. It does not turn independent clauses into new evidence | P0 |
| Q6 | Result-status labels | **Đã xác định căn cứ (Evidence identified) / Có điều kiện (Conditional) / Thiếu căn cứ (Insufficient evidence) / Nguồn xung đột (Conflicting sources)**. When no suitable document exists: "Chưa tìm thấy tài liệu được phép truy cập" (No document you are allowed to access was found) | The status is computed from rules. There is no decorative color badge and no self-scored percentage | P0 |
| Q7 | Evidence-coverage checklist | Separate `source_verified`, `effective_checked`, `applicability_checked`, and `claim_supported` (and the details `transition_checked`, `required_facts_complete`, `scope_expansion`, `citation_verified`) | Do not claim that something is verified while `temporal_unknown` remains, or when there are only candidates | P0 |
| Q8 | A finding with citations, and a reference suggestion | Claims and suggestions follow the schema in SRS §6.2. Each item has `evidence_ids`. Three content layers are clearly distinct: verbatim text / a finding with citations / a reference suggestion | A claim with no source is lowered to "chưa xác minh" (not yet verified) or is blocked | P0 |
| Q9 | Refuse correctly and ask again | When evidence is missing, say clearly that the evidence is not sufficient. When an essential fact is missing, ask for at most 1–3 facts | Do not fabricate an article or a clause | P0 |
| Q10 | Controlled expansion outside the category | When a clause cites something outside the category: (a) do not expand, and report the gap; (b) open one related administrative document at a time that the user is authorized to see, with the label "Nguồn ngoài danh mục" (Source outside the category) | Do not open an administrative document the user has no right to | P0 |
| Q11 | Copy, print, export | Keep the scope, `as_of_date`, the data-repository date, the source symbol number, and the amendment (sửa đổi) warning | Refresh, print, and copy do not drop the warning | P0 |
| Q12 | Feedback | Four types: Căn cứ sai (Wrong evidence) · Thiếu căn cứ (Missing evidence) · Văn bản hết hiệu lực (Administrative document no longer in effect) · Trích dẫn sai đoạn (Wrong cited passage). They enter the curator queue and link to an evaluation case | Feedback that has not been approved does not change ranking | P0 |
| Q13 | My history | Review one's own questions and results when policy allows. Reopening a citation must recheck rights and effectivity (hiệu lực) | The citation snapshot follows audit rights | P0 |

### C.2 Viewing the source and effectivity

| Code | Feature | Behavior | Constraints and safety | Priority |
|---|---|---|---|---|
| V1 | Original PDF viewer | Open the exact immutable PDF bytes, the correct version and page, and scroll to the span. When the bounding box is not reliable, fall back to opening the correct page and showing the quote for comparison, with the warning "chưa tô chính xác" (not highlighted precisely) | Do not overlay new text. Do not paint color over PDF content | P0 |
| V2 | Article tree | Built from the database: Chapter (Chương) > Section (Mục) > Article (Điều) > Clause (Khoản) > Point (Điểm). Clicking a node jumps to the PDF | Do not build the tree from the PDF at view time | P0 |
| V3 | Sticky Amendment Banner | The node status is **correct for `as_of_date`**: `active`, `modified`, `repealed`, `suspended`, `not_yet_effective`, `unknown`. A fixed warning sits in the toolbar, and a badge sits next to the highlight, with a link that opens the correct approved PDF, version, page, and replacement node (thay thế) | A text label, an icon, and a description by date. Color is not the only change. `modified` does not mean the whole administrative document has lost effectivity | P0 |
| V4 | Amendment chain | The chain A ← B ← C displays the related amendments (sửa đổi) correctly. The button "Xem nội dung áp dụng tại ngày tra cứu" (View the text applicable on the search date). When `as_of_date` is before the amendment date, phrase it as "Quy định được thay đổi từ [ngày]" (The provision is changed from [date]), and always consider transitional provisions and suspension | Missing metadata means "Hiệu lực chưa xác minh" (Effectivity not yet verified). Do not mark the provision as no longer in effect on your own | P0 |
| V5 | Official source and file download | A link to the official publication page when the curator has verified it. Download the PDF according to rights | This does not replace the internal viewer | P0 |

### C.3 Chat Agent for the user (icon at the right corner of the screen)

| Code | Feature | Behavior | Constraint | Priority |
|---|---|---|---|---|
| G1 | Launcher | A round Orb of 56–64px, defaulting to the bottom-right corner. Click to open; click again to collapse the panel. Respect the safe area and the work area. On the desktop only the circular region is shown and receives interaction. There is no square background and no stray shadow | State is based on the backend. Motion is light, with reduced motion. Desktop follows C.12/S14 | P0 |
| G2 | Conversation panel | A sliding pane on desktop, and full screen on a phone. The top of the panel has a scope chip, `as_of_date`, and FactChips. Evidence cards are compact. Tabs are Trả lời (Answer) / Phân tích (Analysis) / Liên quan (Related) | Use the same two-phase SSE contract as the full page | P0 |
| G3 | Page context | When opened from an administrative-document page or a category page, suggest a scope from that page. The user can dismiss it. Label clearly when the query expands outside the scope | Do not expand quietly on your own | P0 |
| G4 | Open the full page in the same session | The button "Mở trang đầy đủ" (Open the full page) keeps the session, the FactChips, and the results | Session state lives on the server. The browser keeps only the session id | P0 |
| G5 | Suggestion chips | A row of next-question chips under the answer (A2) | Each suggestion has been trial-run through retrieval | P0 |
| G6 | The viewer does not drop the conversation | Clicking a citation opens the PDF viewer at the correct anchor without leaving the conversation. On a phone, the viewer is full screen and has a back button | Recheck the ACL when opening | P0 |
| G7 | Advisory only | There is no button that executes or approves business work. The workflow is fixed. At most 2 LLM call attempts per turn, counting errors, retry, and fallback under C.9 | Invariant B.3. There is no autonomous agent loop | P0 |
| G8 | Stop and retry | Stop the turn that is running. Keep valid evidence and the label that the result is not complete. Retry is an explicit action. It creates a new `run_id` and does not duplicate the user message | Idempotency is per turn. Do not mix events or claims from two runs. Recheck ACL, policy, and revision | P0 |
| G9 | Conversation content | Markdown, tables, and code blocks are rendered safely. Copy includes the source. History is separate, and the composer keeps the draft when there is an error | Do not execute HTML or script from the model or the PDF. An attachment into the repository is still limited to a CURATOR who has the right | P0 |

### C.4 AI memory for queries and long context

Principle: **memory helps the system understand the question. It does not help the system answer.** A legal answer is based only on evidence retrieved again from the repository at the time of the question.

| Code | Layer | What it stores | Used for | Safety limit |
|---|---|---|---|---|
| M1 | Session state | Facts with a source label, the scope, `as_of_date`, resolved references ("điều đó" (that) → node_id), and questions that are still open | Rewrite a follow-up sentence, and display FactChips | Attach `facts_revision` and `snapshot_revision`. If the snapshot changes, the state is "cần kiểm lại" (needs recheck) and is not used automatically |
| M2 | Rolling conversation summary | P0: a template or extraction done in code. An LLM summary is P1 only, as a separate job with quota, egress, and audit, and it does not block evidence | Keep long context: the LLM sees only the state, the summary, and a few recent turns | The label is "không phải căn cứ" (not evidence). The validator rejects a claim that points at it. It does not contain a legal quote |
| M3 | User preferences (opt-in) | A default category, a frequently used scope, and a display style | Pre-fill the scope | Do not store legal content or sensitive identifiers. The user can view and delete them |
| M4 | Retrieval hints | An alias, a legal synonym, or a common way of referring to something, mapped to a standard symbol number or node | Expand the query, and route to an administrative document | Only curator approval makes a hint take effect. User feedback does not change ranking by itself |
| M5 | Administrative-document map | A table of contents determined from the node tree, and a list of related administrative documents | Route across several administrative documents, and explain scope | Generated by code. An LLM summary of an administrative document is P1 and carries the label "không phải căn cứ" (not evidence) |

**Rules that apply to all memory**

- Every use must recheck the ACL, the approved status, and effectivity at `as_of_date`. A node the user no longer has a right to is removed from the state. Its existence is not revealed.
- Memory is private to each user. An admin does not read the content by default. A long-term conversation is written only when an approved retention policy exists and the user has opted in. Before that, use a temporary RAM session.
- `incognito=true`: session content, facts, the summary, and events live only in backend RAM. The default idle TTL is 30 minutes and is configurable. When the TTL ends, the user signs out, or the session exits, the data is destroyed. Do not write content into PostgreSQL, the query/answer log, a temporary file, a durable cache, or a durable SSE replay. Audit records only minimal metadata, not the question, the quote, or the summary. Restarting the backend loses the temporary session. The UI says so clearly. Do not load an old conversation into a session that is not stored.
- The user views, edits, or deletes one item or all items in "Bộ nhớ của tôi" (My memory). A real delete removes operational data, including messages, the summary, facts, derivatives, and cache that belong to the session or the user. Cancel a job that is using that content. Increment `memory_revision` so an old result or job does not write the deleted data back. A citation or an audit record that policy requires to be kept must be separated from memory and must not keep a copy of a confidential question.
- **UI connection and flow control:** `EphemeralMemoryService` connects directly to the `EvidenceChat` UI through two-phase SSE streaming. The user views the list of session-memory items in the drawer "Bộ nhớ phiên (RAM)" (Session memory (RAM)), deletes one item (`DELETE /api/v1/memory/{item_id}`), deletes all RAM (`DELETE /api/v1/memory`), presses Dừng (Stop) (`POST /turns/{id}/cancel`) or Thử lại (Retry) (`POST /turns/{id}/retry`). Turning on the switch "Lưu vào sở thích tra cứu" (Save to search preferences) (`GET/PUT /api/v1/memory/preferences`) allows the default category to be saved and applied automatically through the function `_with_preferences`.
- Backups have a finite retention period and a published destruction schedule. Do not promise that content is deleted immediately from every immutable backup. On restore, reapply the latest minimum deletion-request ledger before opening the service. If the reconciliation ledger is missing, do not open access yet. Deleted content must not return in history, the summary, the cache, or suggestions.
- Local Mode: memory lives in local PostgreSQL. API Mode: a summary is also data, and it is sent outside only when policy allows.
- There is no semantic answer cache. The system does not learn from conversation into ranking on its own.

**Long context**

- The LLM does not receive the whole history. It receives the session state, the summary, a few recent turns, and the evidence that was selected.
- A follow-up question is rewritten conservatively into a standalone question and **shown as "Đang hiểu là: …" (Understood as: …)** for the user to edit. If a key condition is missing, ask at most one question using chip choices. Do not guess.
- Evidence packing: the token budget is per stage. The principal condition and the exception are placed at the start and at the end. Cut on node boundaries. Do not cut in the middle of a Clause (Khoản). Do not compress the quote.
- A question with many aspects or many administrative documents is processed by aspect and then merged. Each claim still goes through the validator. Over budget, the result is `partial`, and the part that is not sufficient is stated clearly.

### C.5 Analysis and suggestions by AI

Three labels are clearly distinct in the UI: **Căn cứ** (Evidence: a verbatim quotation) · **Phân tích** (Analysis: inferred from the evidence, with conditions that are not yet verified) · **Gợi ý** (Suggestion: what should be asked or checked next; it is not an assertion). Each analysis item is attached to at least one `evidence_id` that has passed the validator. An item with no evidence is not displayed. Reference suggestions are filtered automatically to exclude evidence already cited in the main findings (claims), so they are not repeated. PostgreSQL full-text search is optimized with `LATERAL` syntax in `authorized_search.py`, computing `to_tsvector` once per candidate row and filtering Vietnamese question function words, so the query does not congest when the number of administrative documents is large. This runs on request or asynchronously, and **it does not slow `evidence_ready_ms`**. Rules come first. The LLM is used only to phrase the result. Local Mode always has a rules-based or extractive version. For the curator, the AI only **suggests**. The curator presses accept, edit, or reject.

| Code | Feature | For whom | How it works | Guard against error | Package |
|---|---|---|---|---|---|
| A1 | Structured situation analysis | USER | Extract facts from the description (subject, act, time, figures) and then arrange them against the evidence: conditions already met / not yet verified, exceptions, time markers, and consequences stated in the administrative document | Every row has an `evidence_id`. Facts that are not confirmed appear as chips the user can edit. If a condition is missing, do not conclude that something is permitted or not permitted | P0 |
| A2 | Suggested next questions | USER | Generate them from gaps that are already known: an `uncovered` aspect, a condition not yet verified, an exception, a related amending administrative document. Do not generate freely | Trial-run retrieval (dry-run): there must be evidence inside the ACL; otherwise drop the suggestion | P0 |
| A3 | Information still missing | USER | List the facts that decide the scope of application and that the user has not provided, as chips that can be filled quickly. After they are filled, requery only once | Ask only for facts that the evidence actually uses as conditions | P0 |
| A4 | Points to notice inside the evidence | USER | Rules recognize time limits, numbers, subjects, exceptions ("trừ trường hợp" (except where)), and attached conditions. Emphasize them in the evidence card and in the PDF viewer | Mark only a span that already exists in `text_original`. Do not add an interpretation | P0 |
| A5 | Compare versions of one Article | USER | A deterministic diff between versions or amendments of the same node according to `as_of_date`. The AI only phrases the change briefly | The diff comes from approved text. If the previous version is missing, say that it is not available | P0 |
| A6 | Related administrative documents and Articles | USER | A graph from `node_references` plus `node_amendments`: guiding administrative documents, amendments, two-way references, and the amendment chain | Entirely deterministic, with no LLM. Show only nodes inside the ACL. A relation that is not yet approved has its own label | P0 |
| A7 | An easier explanation | USER | Turn on "giải thích đơn giản" (simple explanation) for each claim, shown beside the quote | It is a claim, and it goes through the validator like an ordinary claim. Adding meaning is forbidden | P1 |
| A8 | Summarize a Chapter or Section | USER | Extractive first (the title plus the key sentence). An LLM is optional | The label is "không phải căn cứ" (not evidence). It is not used as evidence | P1 |
| A9 | Watch for changes | USER | Subscribe to a question or an Article. When a snapshot change affects that node, notify inside the application and reopen with the new `as_of_date` | Notify only inside the application. Do not send content outside | P1 |
| A10 | Compare two administrative documents | USER | Align by chapter and article structure, diff, and list the main differences | List only a difference that has a pair of quotes. Do not conclude which one is better | P1 |
| C1 | AI suggestions for the curator | CURATOR | (a) amendment/supplement/repeal (sửa đổi/bổ sung/bãi bỏ) relations detected from sentence patterns ("sửa đổi, bổ sung khoản 2 Điều 5 của …"); (b) references that are not yet resolved; (c) duplicate or similar administrative documents; (d) a page or node whose parse is abnormal; (e) retrieval hints drawn from feedback | Each suggestion includes the source span and a confidence level, ranked by risk. A rejection is recorded so precision can be measured. Suggestions are not applied by themselves | P0 for a, b, and d; P1 for c and e |
| D1 | Gap analysis of the knowledge repository | ADMIN, CURATOR | Group questions that "do not have enough evidence" by topic, and suggest the kind of administrative document that should be added. Statistics of wrong feedback by administrative document | Use aggregate figures. Question content is shown according to rights. Do not download an administrative document automatically | P1 |

### C.6 Layers against hallucination and against wrong retrieval

These are added to the validators that already exist (ACL, span, node effectivity, ID allowlist, numeric/date, polarity/modality).

| Layer | What it does | Measured by |
|---|---|---|
| L0. False premise | If the question mentions an Article/Clause/administrative document that does not exist, or a wrong symbol number, answer "không có" (does not exist) together with the actual list (for example, the administrative document only has Articles 1 through N). Do not search for a near match and then answer at random | `false_premise_detection_rate` |
| L1. Retrieve the correct object | Constraints extracted from the question (symbol number, administrative-document type, year, issuing body, time marker, numbers) must match the evidence. Guard against a neighbor mix-up (Article 15 and 150, Clause 1 and 11) and against a version mix-up. Produce `retrieval_diagnostics`. On a mismatch, expand, ask again, or refuse | `wrong_doc_rate`, `wrong_node_rate` |
| L2. Route to the administrative document before the node | Choose candidate administrative documents by symbol number, title, type, category, and the administrative-document map, and only then search for the node. Deduplicate across versions, and prefer the version in effect at `as_of_date` | A separate ablation |
| L3. Conflict and exception | If the selected nodes say different things about the same object (a number, a time limit, a subject, "trừ trường hợp" (except where)), state both. Do not pick one | `missed_exception` |
| L4. Constrained generation | Only claims whose `evidence_ids` are on the allowlist. Use a deterministic setting or a low temperature if the adapter supports it. Forbid a number, a date, or a name that is not in the evidence. Do not use outside knowledge | `validator_reject_rate` |
| L5. Whether a claim is supported by evidence | Tier 1 is deterministic: match of entities, numbers, dates, negation, and modality. Tier 2 (P1): a local entailment model, turned on only when it passes the POC and does not increase false rejection. A claim that does not pass is removed or shown as "chưa xác minh" (not yet verified) | `unsupported_claim_rate` |
| L6. Honest UI | Labels come from the evidence status and from the validator, not from the LLM's "confidence". Do not use "chắc chắn" (certain) or "đã xác minh" (verified) when the proof is not sufficient | UI test |
| L7. Feedback loop | "Wrong / missing / effectivity error" enters the curator queue. An approved case enters the regression suite. It does not enter the calibration set or the held-out set | A process that has a test |

**Trap set** (a proposal of 40–60 questions, kept separate from Gold v0): the agent drafts them from real PDFs, and a person who holds the business knowledge approves them. The set includes false premises, an Article that does not exist, a symbol number that is nearly the same, an administrative document that is no longer in effect, a question outside the scope, an injection command inside a PDF, a request to ignore the source, and a request for advice that goes beyond the evidence. The owner locks the acceptance threshold after the baseline. The dossier does not claim that hallucination is eliminated entirely. The goal is to measure it, to reduce it, and to say clearly whenever the evidence is not sufficient.

### C.7 Accuracy and speed

**Accuracy** (each step below sits behind a feature flag and is turned on only when the benchmark does not regress): expand the query with approved retrieval hints; split a multi-aspect sentence with rules first and the LLM after; filter by metadata extracted from the question (administrative-document type, issuing body, year, category); route to the administrative document before the node (L2); rerank conditionally. Each step has an ablation.

**Speed** (safety invariants do not change):

- Compute at index time: `text_folded`, `tsvector`, the embedding, the breadcrumb, the applicability header, and the administrative-document map. Load the model once at startup and keep the ONNX session.
- Use a connection pool and prepared statements. Run lexical and dense search in parallel, and compare them with sequential execution and with a CTE, following the SRS benchmark.
- Short path: when the Legal Reference Router has a unique match, skip Analyze.
- Embedding cache: separate it from the analysis cache. The key includes a hash of the exact input, the model/tokenizer/prefix revision, and the security partition. Do not merge users by default. An incognito session does not write a durable cache. Use an in-session RAM cache only if needed.
- **The analysis cache is OFF by default.** Turn it on only when the key covers the principal and the session, the rewritten question, `facts_revision`, `memory_revision`, the scope, `as_of_date`, the ACL and policy revision, the model/tokenizer/prompt-schema/hints revision, and every input that is actually read. If any fingerprint that affects the output is missing, skip the cache. Recheck rights on read.
- **The retrieval cache is OFF by default.** If it is turned on, the key includes the ACL fingerprint, the policy revision, `snapshot_revision` or the source-review revision, `index_revision`, the model/tokenizer/hints revision, the scope, `as_of_date`, and the query and facts. A change of rights, data, model, policy, or snapshot must invalidate the cache. There is no semantic answer cache. A cached result is not used to bypass a rights check.
- Evidence first: show the evidence as soon as it is ready, and stream the claim afterward. The UI prefetches the cited PDF page on hover.
- Measure `retrieval_ms`, `evidence_ready_ms`, `first_claim_ms`, and `final_answer_ms` (P50/P95) on the target Windows machine. The baseline is at WP 2.13. The owner locks numeric targets after the baseline. CI checks performance regression with a tolerance.

### C.8 Document-repository administration (CURATOR, REVIEWER)

| Code | Feature | Behavior | Constraints and safety | Priority |
|---|---|---|---|---|
| K1 | Categories | Create, edit, hide, soft-delete, and restore. Parent–child depth is configurable (for example 3). Many-to-many with documents. Move a document between categories. Import and export JSON/CSV with validation | Prevent cycles. A soft delete does not delete the original file or an embedding that is still used elsewhere. A hard delete goes only through an approval process | P0 |
| K2 | Document record | Standard metadata (SRS §2.4): symbol number, issuing body, issue date and effectivity date, status, source, hash, version, and so on. Effectivity status at Article/Clause level | Do not infer "still in effect" from the issue date. Distinguish `valid_time` and `recorded_time` | P0 |
| K3 | PDF upload | Drag and drop or choose a file. Check magic bytes, quota, and SHA-256. Store an immutable copy. Ingest progress follows the job | A file with bad structure, hash, or metadata cannot become `approved` | P0 |
| K4 | URL import | Only a domain on the allowlist. DNS pin and recheck. Block private and local addresses. Limit redirects and size | A URL outside the allowlist is blocked, with a reason. A hash change at the same URL means a new version waiting for approval | P0 |
| K5 | Domain allowlist management | An admin adds, edits, or disables a domain after verification (DNS/HTTPS check, the person who verified, and a note). Every change is audited | If a domain is disabled, import stops | P0 |
| K6 | Ingestion pipeline | Native parse of each page. Page diagnostics (the character `�`, the rate of valid syllables, text coverage, reading order). Detect TCVN3/VNI and convert the encoding with a reverse check. `needs_ocr` plus an OCR-plugin interface | A bad page never becomes a verified quote | P0 |
| K7 | Parse the node tree | Chapter/Section/Article/Clause/Point/Appendix. An unstructured administrative document is handled by heading or by page. `text_indexed` has a breadcrumb. An applicability header. `node_references`. `parse_confidence` | Do not invent an Article or a Clause | P0 |
| K8 | Risk-prioritized review queue | Low parser confidence, a skipped clause, an encoding conversion, a misaligned bounding box, effectivity that is not yet approved, or an AI suggestion enters the queue and is ranked by risk | Effectivity metadata always needs a person to approve it | P0 |
| K9 | Curator Split-View | Left: PDF.js of the immutable copy, with page selection and span highlight. Right: the `document_nodes` tree plus a form (label, position, the node's effectivity window, an amendment link). Clicking a node jumps to the PDF, and the reverse also works | Autosave of a draft is not Approve. Use `If-Match` and the revision. Audit the actor. A shortcut does not approve while the user is typing. Confirm when effectivity or an amendment is edited | P0 |
| K10 | Amendment relations and node effectivity | The CURATOR creates or edits a draft `node_amendments`. The REVIEWER approves with a revision and an audit. Node status follows `as_of_date` | Accepting an AI suggestion only creates or updates a draft. It does not publish, and it does not raise the approved revision, when the REVIEWER right is missing | P0 |
| K11 | Effectivity snapshot | The resolver runs to a fixed point (it detects a cycle, a broken edge, an overlap, or a conflict), then staged content is published atomically by `snapshot_revision`. Stale fails closed. Invalidate the cache | Do not leak an administrative document outside the ACL | P0 |
| K12 | Document versions | A different hash means a new version. Choose the copy as of a date. Compare versions (A5) | The old PDF is kept unchanged | P0 |
| K13 | AI suggestions for the curator | See C1 in C.5 | Suggestions only | P0/P1 |

### C.9 AI models, policy, and operating mode (SYS_ADMIN)

| Code | Feature | Behavior | Constraint | Priority |
|---|---|---|---|---|
| R1 | Model Registry | The admin configures API or Local: adapter/provider, an approved endpoint or runtime, model ID or artifact, capability, parameters, revision, secret reference, status, and a quota | Do not hardcode a provider, model, endpoint, key, or model path. Do not use LiteLLM. Changing a model inside a supported capability or adapter does not require a code change | P0 |
| R2 | Stage routes | Each stage chooses a model for API Mode and for Local Mode. A model change goes through the Registry | Changing the embedding model means a new index in parallel, then a cutover | P0 |
| R3 | Two operating modes | API Mode / Local Mode, set by system configuration and by category policy | Local Mode is fully offline (search, embedding, rerank, analysis, and PDF viewing). Login, licensing, and startup do not call an outside service | P0 |
| R4 | Egress policy | `remote_allowed` follows the formula in SRS §8.4 with `mode == API`. The default is to block. Audit every route decision | Remote denied means `REMOTE_AI_DENIED`. Fallback stays inside the same privacy zone | P0 |
| R5 | Secret management | A key is entered once, encrypted, and masked. The raw key cannot be read back | Do not log the key | P0 |
| R6 | Egress control in Local Mode | An egress guard inside the application, a sample Windows Firewall rule, and a `verify-egress` script | Truly disconnecting the Internet is additionally guaranteed by infrastructure and the operating system | P0 |

**LLM configuration contract and budget**

- There are only two operating values, `API` and `LOCAL`. The admin configures a route per stage for both modes. The USER sees a read-only badge and does not enter a key or an endpoint in the chat. API Mode uses an LLM through an approved API. Local Mode uses an internal LLM and has no fallback path to the Internet. A new provider outside the supported adapter protocol needs an adapter that has tests. Do not assume that every API is compatible.
- Embedding, reranker, and LLM are independently configured capabilities. The POC does not turn an experimental model into the product's fixed model. An ONNX requirement in the embedding/reranker POC does not forbid a GGUF LLM, or another format, running on a local runtime that has been verified. The model path and the runtime path are obtained through configuration, the manifest, or a platform API.
- When no model or key exists yet, the system still returns real evidence or a real extractive answer. The UI states “Chưa cấu hình mô hình AI” (AI model not yet configured), `answer_generated=false`, and it does not simulate an AI analysis. The owner enters the secret later through the administration UI. Do not put a secret into a prompt, a fixture, or a log.
- Each `run_id` has `llm_attempt_budget=2` for Analyze and Generate. Every request sent to the LLM, including a timeout, an error, a retry, or a fallback, consumes one attempt. A hidden retry does not exceed the budget. If only one attempt remains, prefer the stage that is required, or return an extractive answer. The P0 summary, the A2 suggestions, and aspect splitting do not create an extra LLM call outside the budget.
- Stop cancels work that can still be cancelled. It cannot recall a request the provider has already processed, and it does not refund the budget by itself. When the user presses Thử lại (Retry), a new run is created, with a rate limit and a quota. It does not loop forever on its own.
- Profile B, lexical plus extractive, is a publicly documented degraded capability. It is not a third mode. S0 may accept offline-core feasibility under this profile when the model is not yet adequate, and it must state clearly which of dense, rerank, and generation have not been checked. The S3 gate for an AI configuration must check the real provider and model that were selected. A mock, a FakeAdapter, or profile B does not stand in for that evidence.

### C.10 Quality, operations, and security

| Code | Feature | Behavior | Priority |
|---|---|---|---|
| Z1 | Gold Dataset v0 | 150–200 questions from real PDFs, approved by a reviewer. Each case has evidence, version, date, and source hash, plus `scenario_group_id` and `split_revision`. Rephrasings, or questions about the same situation, stay in the same split | P0 |
| Z2 | Benchmarks B0–B7 and ablation | Run on approved Gold. Use `ranx` and bootstrap. Pin the corpus hash and the model/tokenizer revision. The report includes a confidence interval | P0 |
| Z3 | Trap set and anti-hallucination metrics | See C.6 | P0 |
| Z4 | Quality dashboard | `retrieval_ms`, `evidence_ready_ms`, `generation_ms`, tokens, cost, `fallback_reason`, abstention rate, and the L0–L7 metrics. Chain-of-thought is not displayed | P0 |
| Z5 | Audit | Append-only. Record document access, route decisions, approvals, configuration changes, and the opening of an old citation. The retention period is configurable (default 2 years) | P0 |
| Z6 | Backup and restore | Encrypted backup, with a restore drill onto a clean machine | P0 |
| Z7 | Windows distribution package | Core Pack, a Model Pack manifest (id, sha256, license, revision, dimension, RAM/disk), and a Data Pack. A clean demo install is under 10 GB, measured in CI | P0 |
| Z8 | RBAC + ABAC | Rights by role and by attribute (category, confidentiality level). SYS_ADMIN does not read content by default | P0 |
| Z9 | Input security | SSRF, fake MIME, prompt injection through a PDF or metadata, XSS from a PDF, CSP, and ACL leakage through the cache or the tokenizer | P0 |

Calibration is used to tune thresholds. Regression is used repeatedly during development. Held-out and the trap hold-out lock content and answer access against the person who tunes, and they run only after the candidate and the config are frozen for a lock-in round. The split manifest is immutable per revision, and group and semantic-duplication checks are reviewed by a person. A zero overlap of case IDs alone is not enough. If held-out results are used to edit or tune, mark that set as used, and do not report it as an independent evaluation of the later candidate. A new unseen set is required. The source corpus must still sit in the benchmark index so retrieval can find it. Do not confuse separating evaluation questions with removing sources from the benchmark repository.

### C.11 Primary usage flows

**L-1. First question (USER).** Choose a category → (optional) change the application date → enter the situation → see FactChips and the skeleton "Đang tìm căn cứ…" (Searching for evidence…) → grouped evidence cards appear (Phase 1) → the neutral sentence "Đã tìm thấy và kiểm tra nguồn của X căn cứ. Đang phân tích điều kiện áp dụng, hiệu lực, quy định chuyển tiếp và ngoại lệ…" (Found and checked the source of X pieces of evidence. Analyzing conditions of application, effectivity, transitional provisions, and exceptions…) → claims and the status label (Phase 2) → the coverage checklist → suggested next questions.

**L-2. Edit facts.** Edit one or more chips → show the bar "Đã chỉnh sửa dữ kiện…" (Facts have been edited…) → press "Cập nhật dữ kiện & Tra cứu lại" (Update facts and search again) → the old result is marked `stale` → the new result replaces it.

**L-3. Open evidence that has been amended.** Press `[1]` → the viewer opens the correct page, with the highlight and the fixed banner "Khoản này … đã được sửa đổi bởi … từ ngày …" (This clause … was amended by … from …) → "Xem văn bản sửa đổi" (View the amending administrative document) opens the replacement PDF at the correct page and node → "Xem nội dung áp dụng tại ngày tra cứu" (View the text applicable on the search date).

**L-4. A quick question with the Chat Agent.** Press the icon at the right corner → the panel slides out with a scope suggested from the page → ask → compact evidence cards → press a piece of evidence to open the viewer → return to the conversation → "Mở trang đầy đủ" (Open the full page).

**L-5. The curator ingests a document.** Upload a PDF or import a URL (a domain that is already allowed) → the job runs and progress is visible → the review queue (by risk) → the CURATOR saves a draft of the node, the metadata, and the suggestion → the REVIEWER approves the document, the version, the effectivity metadata, and the amendment relation → the effectivity snapshot is published.

**L-6. An admin adds a source domain.** Administration → Domain cho phép (Allowed domains) → Thêm (Add) → enter the domain name → the system checks (DNS, HTTPS, and that it is not an internal address) → confirm the person who verified it, plus a note → turn it on.

**L-7. Local Mode.** Administration sets the mode → run `verify-egress` → the whole question-and-answer flow and PDF viewing run without the Internet. Every operation uses a local model. If the Local LLM fails, return the verified evidence together with "Giải thích tạm thời không khả dụng" (Explanation temporarily unavailable). Do not call the API.

**L-8. The USER on Windows.** Open the app shortcut → sign in inside the app → the sign-in window disappears completely → the round Orb at the right corner of the desktop → click to open the chat, and click again to collapse it → open a PDF or the workspace in the same session → collapsing back to the Orb does not lose the conversation → sign out, or Thoát (Exit) through the system-tray menu. A browser is not required, and a console window is not shown.

### C.12 The USER application on Windows, and the portal boundary

| Code | P0 behavior | Acceptance |
|---|---|---|
| W1 | The Tauri 2 desktop shell reuses the User Portal, its components, the API, auth, and RAG. The Admin Portal is a separate layout | One backend, one database, and one pipeline. Do not fork a chatbot. A LAN client connects to the configured server and does not install a database of its own on each USER machine |
| W2 | A shortcut and sign-in inside the app. The backend endpoint comes from the deployment configuration | When the session ends, return to sign-in. Do not open a browser on your own. Do not hardcode host or port. Do not take over or stop an unrelated service |
| W3 | The round Orb, the panel, and login each have their own window state. Login and the panel are opaque. Only the region outside the Orb is transparent | No leftover login frame, square box, or stray shadow. A hit-test outside the Orb does not block the app underneath |
| W4 | Click toggles. Collapse and open, the workspace, and the viewer keep the same session, turn, facts, and revisions | Do not duplicate a turn, and do not lose a draft. Closing the panel only collapses to the Orb. It does not delete the session |
| W5 | Drag and resize have their own regions and can be turned off. Buttons and the title are not covered by the drag region | A drag does not fire an open or close click. There is no drag layer covering the composer or a citation. Restore the position inside the work area when DPI or the monitor changes |
| W6 | System tray: Hiện/Ẩn trợ lý (Show/Hide the assistant), Đăng xuất (Sign out), Thoát (Exit). Always-on-top is a user choice | Hide does not mean sign out. Sign-out stops the stream and clears state and the session secret. Exit does not stop the shared LAN backend |
| W7 | Real analysis, suggestions, and citations follow the shared pipeline. Stop and retry, and the disconnected state and the no-model-yet state are clear | No fake progress, and do not label a template as AI on your own. The native build and the web build use the same contract |
| W8 | Type and responsive behavior are aligned across User, Admin, and desktop. The USER UI has no repository upload, no ingestion, and no user or model administration | Check several sizes and DPI settings, the keyboard, contrast, and reduced motion. Server-side rights are still checked |

The web User Portal is a surface for the same functions when it is deployed. On Windows, the desktop is the USER's primary way in. The Admin Portal has Dashboard, Tài liệu (Documents), Danh mục (Categories), Ingestion/jobs, Tài khoản/quyền (Accounts and rights), Cấu hình AI (AI configuration), Monitoring/audit, and Evaluation. Each module must have a screen, or a clear state for when there is no data yet. The sidebar must not lead to a fake page. Administration roles see only the modules they have been granted. They do not by default view a private conversation or business content.
