**Language / Ngôn ngữ:** [Tiếng Việt](HOSO_BAN_GIAO.md) · English

English counterpart of `docs/HOSO_BAN_GIAO.md`. The Vietnamese file is the original.

# IMPLEMENTATION HANDOVER DOSSIER — Vietnamese Evidence RAG Agent

> **[Not implemented — see ADR-010]** Everything in this document about the Gold question set, the trap set, calibration, and held-out must not be implemented, per [ADR-010](architecture-decisions/ADR-010-khong-trien-khai-bo-cau-hoi-gold.md). The rest stands as written.

Dossier version 1.1 · updated 2026-10-21
Basis: SRS v1.3 + the owner's decisions of 2026-10-17 and 2026-10-21; checked against the history of the project “Agent tra cuu”, in particular the requirement to separate the portal from the USER application on Windows.

**This dossier contains:** A. How to use it · B. Product overview and decisions already locked · C. Feature description · D. Detailed UX/UI design · E. Supplementary API contract · F. Detailed implementation plan · G. Kickoff prompt and appendices.

---

## A. How to use this dossier

**Required companion file:** `02_Vietnamese_Evidence_RAG_Agent_SRS_v1_3.md` — the current technical source (draft DDL, retrieval algorithms, API, benchmark, repository layout). `02_Vietnamese_Evidence_RAG_Agent_SRS_v1_2_1.md` is kept unchanged as history and is not used for current operational decisions.

**Precedence when sources conflict:** (1) a new instruction from the owner → (2) B.4, B.7, and B.8 → (3) this dossier → (4) SRS v1.3. The accompanying ADR-000 records the decisions; once placed in the repository, use `docs/SRS_v1.3.md`, `docs/HOSO_BAN_GIAO.md`, and `docs/architecture-decisions/ADR-000.md`. Do not create a competing specification. This update is documentation only; it does not prove that any work package (WP) or release gate is complete.

**Working rules for the implementing AI**

1. Work autonomously and ask little. Where a point is not yet locked: use the default in B.6 or F.3, record an ADR under `docs/architecture-decisions/`, and continue. Stop and wait for a person only for four groups: **business rules, access rights, security, and correctness of evidence (căn cứ)** (F.11).
2. A work package (WP) counts as done only when: code + migration + green tests + updated documentation + a report in the F.10 template.
3. Do as much as possible of the technical work that can be verified by code or tests (ERD design, migrations, database tests, parser, retrieval, UI, CI, benchmark).
4. Do not add heavy dependencies: PyTorch, full Docling, LiteLLM (SDK or Gateway), Redis, Elasticsearch, Qdrant, Neo4j, RAGFlow, GraphRAG, or a mandatory LlamaIndex/Haystack. Pin every dependency by version + hash, and record the license and footprint in `dependency-manifest`.
5. Do not fabricate legal administrative documents (văn bản). UI fixtures are labeled "HƯ CẤU" (FICTIONAL). Benchmarks use only real public administrative documents, in a separate corpus.
6. Do not state figures that have not been measured ("<2ms", "giảm 60–70%" (a 60–70% reduction), "100% chính xác" (100% accurate)). Every number records the environment, version, and data.
7. Report honestly what is not done; do not change acceptance criteria to make tests green.

**How to split the work across multiple AIs** (the owner's choice): the seven streams A–G in F.4 may be assigned to different AIs. To work in parallel: (a) the backend stream publishes **OpenAPI** at the start of Sprint 1; (b) the frontend stream uses a mock server generated from OpenAPI and the design-token module (D.2) until the backend is ready; (c) the evaluation stream shares `corpus_public_real`; (d) every stream submits ADRs and WP reports in the same template.

---

## B. Product overview and decisions already locked

### B.1 What the product is

A **Vietnamese question-answering platform with citations** over an approved corpus of administrative documents (văn bản) (laws (Luật), decrees (Nghị định), circulars (Thông tư), charters, procedures, and internal administrative documents). The user asks in natural language; the system finds the right administrative document and the right Article (Điều)/Clause (Khoản)/Point (Điểm), shows the **verbatim evidence (căn cứ) together with the original PDF page first**, and only then explains conditions of application, exceptions, effectivity (hiệu lực), and transitional provisions. When evidence is insufficient, the system says so plainly — "chưa đủ căn cứ" (insufficient evidence) — instead of guessing.

The system is **read-only advisory (tham mưu)**: it does not approve, it does not issue decisions, and it does not write business data.

Internal (LAN) deployment on **Windows**, with two independent operating modes: **API Mode** and **Local Mode (fully offline)**.

### B.2 Users and roles

| Role | Does | Does not |
|---|---|---|
| USER (the person asking) | Signs in inside the Windows app, uses the Orb/chat/workspace, selects a category or everything within their rights, views sources and their own memory | Does not see documents outside their rights; does not upload into the corpus, manage accounts, configure models, or edit corpus data |
| CURATOR | Ingests documents, assigns categories, checks extraction, saves draft nodes, accepts/edits/rejects suggestions at draft level | Does not approve documents, versions, effectivity, or amendments (sửa đổi) unless additionally granted the REVIEWER right |
| REVIEWER | Approves documents/versions, amendment relationships, and node effectivity | Does not change system configuration |
| SYS_ADMIN | Configuration, accounts, rights, Model Registry, domain allowlist | **Does not by default read business content or confidential documents** |
| AUDITOR | Views logs and evidence within the permitted scope | Does not modify data |

RAG-module rights are **separate**; they are not inferred from a role in another application (for example, a personnel-management app). The mapping must be granted explicitly.

### B.3 Invariants (a violation is a release-blocking defect)

- The agent is advisory only, READ-ONLY; it has no tool that writes, approves, or sends. It calls only allowlisted read services: `search_authorized_nodes`, `get_node_history`, `get_precomputed_references`, `validate_evidence`, `read_original_span`, `get_viewer_anchor`.
- **The LLM does not write quotes, and does not create IDs or article/clause numbers.** The backend hydrates `quote_exact` from approved `text_original`.
- **ACL is filtered in SQL before** lexical search, vector search, rerank, cache, citation, and viewer. The existence of a document the caller may not access is not revealed.
- **Remote AI is fail-closed** (`remote_processing_allowed` defaults to FALSE). Local Mode does not connect to the Internet; only approved loopback/internal-LAN endpoints are allowed, and the system does not switch to the API on its own when the local LLM fails.
- **Effectivity is at node level**, default `unknown`; the CURATOR prepares a draft, and the REVIEWER approves documents/versions and amendment/effectivity relationships. "Still in effect" is not inferred from the issue date.
- Two-hop retrieval is not the effectivity resolver. The resolver walks the entire verified amendment chain to a fixed point; if it exceeds a guard or an edge is missing, it fails closed.
- Effectivity snapshot: atomic publish, pin the revision; stale/failed ⇒ `SNAPSHOT_STALE`. An old snapshot is not used to assert effectivity.
- Pre-gate with 3 branches (pass / uncertain → expand or rerank / insufficient → refuse). Min-max or an RRF score is not used as an absolute threshold.
- Two UI phases: "source/quote checked" is not "claim verified". Do not use the sentence "Đã xác minh X căn cứ" (Verified X pieces of evidence) when effectivity and coverage have not been established.
- The original PDF is immutable (bytes do not change, no new text is overlaid); a different hash ⇒ a new version.
- PostgreSQL is the only database; no semantic answer cache; no auto-crawl; no GraphRAG/ColBERT in the MVP.
- Color goes through design tokens; HEX is not hardcoded; color is not the only signal.
- **Memory is never evidence**; the validator rejects a claim that points at memory.
- **Do not use the Gold question set to score the AI (ADR-010)**: the AI only assists, and a specialist officer decides. [Not implemented — see ADR-010]
- Arbitrary URLs are blocked by default; only approved documents enter the corpus; a valid domain does not mean the administrative document is still in effect.
- Windows is the official OS; do not add a mandatory dependency on Linux, WSL, or Docker.
- **Do not hardcode rights, provider, endpoint, model ID, API key, model path, or machine path.** The LLM is configured as API or Local through the Registry/Router; a POC model is only trial configuration data.
- **Do not hardcode PATH or the LLM.** Every tool/runtime the project must install lives under `E:\Programs` via the `EVIDENCE_PROGRAMS_ROOT` configuration; do not place a literal root in application logic. The mandatory policy is in B.8.
- The User Portal, the Admin Portal, and the desktop shell share authentication, the backend API, PostgreSQL, the document corpus, and the RAG pipeline. Do not create a separate chatbot, database, or pipeline for the desktop.

### B.4 Owner decisions already locked (synchronized into SRS v1.3)

| # | Topic | Decision |
|---|---|---|
| 1 | ERD | The AI designs the entire ERD, tables, relationships, foreign keys, and constraints; creates migrations and database tests itself; checks consistency, integrity, authorization, and version history itself; in particular effectivity, amend, supplement (bổ sung), and repeal (bãi bỏ) relationships down to each Article/Clause/Point. Present the owner only with the important business principles |
| 2 | Sources and domains | Block arbitrary URL downloads by default. The admin adds/edits/disables domains in the administration interface after verification. Allow PDF upload from the machine. Check origin, file structure, hash, metadata, and content before approval; only approved documents enter the official corpus. A valid domain does not mean the document is still in effect |
| 3 | Gold [Not implemented — see ADR-010] v0 | 150–200 questions from PDFs of real official administrative documents. The agent drafts them, and a person who knows the business approves them; the AI does not accept them on its own. Calibration is used to tune thresholds; held-out is independent of threshold tuning and of training data; split by situation group / rephrased question, not only by case ID |
| 4 | AI mode | Hybrid Multi-LLM architecture, but **only two operating modes**. **API Mode:** Internet is available; LLM via API; embedding/reranker local or via API; send only data the policy allows; fallback stays within the permitted API scope. **Local Mode:** Internet fully disconnected; LLM, embedding, and reranker 100% local; fallback is internal models only; models and updates arrive by offline media |
| 5 | Operating system | Windows is official: PostgreSQL + pgvector, FastAPI, frontend, worker, and local LLM run on Windows; Linux/WSL/Docker are not required. Sprint 0 only checks the pgvector install, performance, backup/restore, and Windows services. If pgvector has a problem, propose a fix on Windows before discussing an architecture change |
| 6 | AI memory | Memory for queries and long context (C.4) |
| 7 | Chat Agent | The USER uses the Windows app: open the shortcut, sign in inside the app, a round Orb at the right corner of the desktop, click to open/collapse chat, open the workspace in the same session; no need to open a browser. User and Admin are separate portals and share RAG (C.3, C.12, D.5 S14) |
| 8 | Anti-hallucination | Add 8 layers L0–L7 and a trap set (C.6) |
| 9 | Accuracy and speed | Flagged improvements + measurement; cache has a gate (C.7) |
| 10 | Analysis and suggestions | 12 features A1–A10, C1, D1; the P0 bundle is in the MVP, the P1 bundle follows the owner's priority (C.5) |
| 11 | LLM configuration | The admin configures API or Local: adapter, approved endpoint/runtime, model ID or artifact, parameters, secret reference, per-stage route, and fallback. Do not fix a vendor/model/endpoint; the owner enters the API key later, and secrets do not go into the dossier |
| 12 | Scope and portals | The USER selects one/many categories or “Tất cả danh mục được phép” (All authorized categories); every case filters ACL in SQL. SYS_ADMIN does not automatically have query rights; an account with several rights switches portals deliberately |
| 13 | PATH/LLM and tool installation | Do not hardcode PATH or the LLM. Every project tool/runtime that must be installed lives under `E:\Programs`; the root comes from the deployment profile or `EVIDENCE_PROGRAMS_ROOT`, and is not embedded in code/scripts; details in B.8 |

The automatic/approval boundary: the agent does every technical task that can be verified; a person approves only business rules, access rights, security, and correctness of evidence.

**Changes already brought into SRS v1.3** (a historical crosswalk, not work waiting for the AI to redo)

| SRS item | Old | New |
|---|---|---|
| §0.1 D02, §8.1, §13.1 | Three modes HYBRID / API_ONLY / LOCAL_ONLY, Hybrid by default | Two modes, API Mode / Local Mode; Hybrid is the Registry/Router architecture that selects a model per stage; profiles A/B/C remain deployment profiles; remote remains fail-closed under policy |
| §8.4 | `mode != LOCAL_ONLY` | `mode == API`; the remaining conditions stay the same |
| §9.1 (top bar) | Select `[Hybrid ▼]` | Show a read-only mode badge (see B.6) |
| §10, §13, §18 Sprint 0, §22 | Postgres on Windows or Linux, OS chosen in Sprint 0 | Windows is locked; `deploy/windows` is the baseline |
| §11.2, §12.3 | `import-url` against a configured allowlist | The allowlist is a database table the admin manages in the interface, blocked by default |
| §15.1, §16, §18 Sprint 1 | Gold [Not implemented — see ADR-010] v0 of 50–100 questions | 150–200 questions, with calibration and held-out sets separated |
| New items | — | Add the items: Memory, Chat Agent, Anti-hallucination layers, Analysis and suggestions |
| §9, §17–18, §25 | The in-browser widget is the primary description | Add the USER desktop shell from history the owner has approved; keep the backend/RAG unchanged; turn the 8 comments into a contract and acceptance criteria |

### B.5 Out of scope

No auto-crawl; no semantic answer cache; no GraphRAG, ColBERT, Neo4j, Elasticsearch, Qdrant, or Redis in the MVP; no LiteLLM; no SQLite as the primary database; no business processing (approval, discipline, commendation, payment) in this module; no Dark Mode in the MVP (P1); OCR is an exceptional plugin only, and its runtime is not installed by default.

### B.6 Defaults the agent may use; the owner may change them

| Issue | Default | Change when |
|---|---|---|
| Mode display in the interface | Read-only badge "API Mode"/"Local Mode"; only an admin changes it through configuration, and the user does not switch it | The owner allows the user to choose under policy |
| PDF library | pypdfium2 | pdfplumber is clearly better on bbox/tables in the POC |
| Highlight viewer | PDF.js + a self-drawn overlay from quads | react-pdf-highlighter-extended passes the POC |
| Job queue | Procrastinate if overhead is low | If it does not meet the bar: write `SKIP LOCKED` yourself |
| Running Windows services | NSSM or a pywin32 service, chosen by ADR | Another approach is required |
| Embedding/reranker | Chosen by POC from the candidates in SRS §14.3; Local Mode uses only models that run locally | If no model passes: turn dense off by flag, and run profile B (lexical + extractive) |
| Contextual dense prefix | OFF | The POC shows a quality gain and does not increase missed-exception |
| Auth | Local accounts + role/ABAC of the RAG module | Integrate the personnel-management app later, with an explicit rights mapping |
| Tokenizer | Underthesea | Compare with PyVi only in P1 |
| Number of recent conversation turns sent to the LLM | Configurable, suggested 3 | According to the benchmark |
| Gold [Not implemented — see ADR-010] split | Suggest about 30% calibration / 70% held-out, recorded in an ADR | The owner locks it |
| Trap set | Suggest 40–60 questions | The owner locks it |
| Conversation-memory retention period | The owner locks the policy; until an approved policy exists, long-term conversation storage is OFF, and the session uses RAM only with a temporary TTL | Turn storage on after valid retention and opt-in exist |
| Font | `Inter, system-ui, Arial, sans-serif`; bundle Inter only after a license check; Local Mode does not download external fonts | — |
| USER desktop shell | Tauri 2, following the desktop option already approved in the history; pin the version/runtime in the POC, and do not create a separate backend | Change shell technology only by ADR and an owner decision |
| Session that is not stored | Backend RAM; idle TTL 30 minutes, configurable; do not write content into PostgreSQL/logs/durable cache | The owner has a different session policy; do not silently turn storage on |
| Analysis cache | OFF; turn it on only after a test whose key covers the entire context and a user-isolation check | Turn it on by feature flag, with an ADR and invalidation |
| P0 conversation summary | Template/extraction in code; do not call a separate LLM | LLM summary is P1, with its own job/quota, and is not on the evidence-response path |
| Tool-install root | Locked as `E:\Programs` in the `EVIDENCE_PROGRAMS_ROOT` / installation.programs_root configuration; every project tool/runtime that is installed sits under that root (B.8) | Change it only on a new instruction from the owner; do not pick another directory on your own |

### B.7 Unified approach for the eight comments

| # | Approach chosen for the documents | Where it lives, and acceptance |
|---|---|---|
| 1 | The CURATOR creates the draft; the REVIEWER approves; accepting a suggestion does not publish on its own | C.8, E, WP 1.7/3.14; test 403 and that the snapshot does not change when the right is missing |
| 2 | Separate embedding/analysis/retrieval caches; analysis OFF; the key contains every input that affects the result | C.7, WP 4.6; the same question but a different user/session/facts must not hit the wrong cache |
| 3 | Incognito is RAM only; delete operational data and re-apply the deletion ledger on restore | C.4, E, WP 3.7/4.4/4.8; deleted content is not revived |
| 4 | Profile B is accepted as a feasible offline core with the limits stated in public; it does not replace the real-AI gate | C.9, WP 0.4/0.7/3.2; models and APIs come from configuration, and are not hardcoded |
| 5 | Split Gold [Not implemented — see ADR-010] by situation group; regression runs regularly, held-out stays locked until the lock-in round | C.10, S11, WP 1.9/2.8/3.11 |
| 6 | At most 2 LLM call attempts per turn, counting retry/fallback; P0 summary is in code | C.3/C.4/C.9, WP 3.3; when the budget is exhausted, return evidence/extractive |
| 7 | Assign one lead to every WP; backend leads 4.8, retrieval/eval leads 4.9 | F.4, the per-stream prompt; collaboration does not replace the person who is accountable |
| 8 | Panel and viewer sit side by side only when there is enough width; if space is short, switch to a single frame | D.4/S3/S14, WP 4.7; check 320/768/1024/1280px, DPI, and multiple monitors |

**Historical basis read on 2026-10-21:** the chats “Thiết kế AI Agent tra cứu”, “Mô tả AI Widget”, “Tiếp tục triển khai dang dở”, and “Khôi phục project RAG”. Keep the product intent: separate User/Admin, the USER has a desktop app, an Orb toggle, the session is kept when collapsing/opening, stop/retry, analysis with evidence, the owner configures API/Local themselves, text is easy to read, and windows are not broken. Defects that were raised become acceptance cases; do not inherit test accounts, secrets, machine paths, or treat old test claims as current results. The Navy/Blue palette and the motion constraints of the current dossier remain the standard.

---

### B.8 Do not hardcode PATH/LLM, and the required tool-install location

**Owner decision:** every tool, utility, and runtime the project needs to install or bundle so the app can run must live under `E:\Programs`. This is the value of the deployment configuration `installation.programs_root` / `EVIDENCE_PROGRAMS_ROOT`, **not a path constant in source code**. Do not hardcode PATH, an executable path, a model path, a provider, an endpoint, a model ID, or an API key.

- The installer/launcher/service reads the root from an approved deployment profile or from an environment variable supplied by the deployment configuration; the two sources must agree. Source code, install/run scripts, migrations, UI, and tests do not embed a literal drive or machine path. Change the root only when the owner issues a new instruction and the deployment profile is updated; do not edit source to move the path.
- Each component has a subdirectory determined by the manifest under `<PROGRAMS_ROOT>/<product_id>/`: app, runtimes, database, tools, models, and tool cache. Use a path-join function or a platform API; do not concatenate drive strings by hand. Provider/model names and artifacts always come from the Registry/Model Pack manifest.
- The scope covers the Python/backend environment, PostgreSQL + pgvector, the LLM/embedding/reranker runtime, PDF/OCR tools when enabled, the desktop runtime, and the service wrapper. Extra build/install/operations tools, if they must be installed, follow the same root; install only the components a machine role and its capabilities actually need, and do not force a USER machine to install its own database/backend.
- Executables, DLLs/plugins, the package/model store, and the tool cache managed by the project must be resolved from the dependency-manifest under the configured root. Check that the real path lies inside the root, and check version/hash/license; do not silently use a copy on the global PATH, in Program Files, AppData, Downloads, or the source directory. If a tool needs PATH, build a PATH for the child process from the manifest, and do not modify the system-wide PATH.
- If the drive/directory/write permission is missing, or a dependency does not support this location, report an error, block that component, and state the options; do not move to drive C or install globally on your own. The rule applies to what the project installs or bundles; it does not require moving components that already ship with Windows.
- Source PDFs, PostgreSQL data, business logs, and backups have their own configured paths, separate from binaries/tools; do not move data on your own merely because a tool-install rule was added. Locally installed models/runtimes and the tool cache still belong to the root above. Configuration/manifests do not contain plaintext API keys.
- Each Windows machine installs project components under the same policy; a client installs only the client/runtime it needs, and a server/inference node installs the matching components. A remote API provider is a configured service, and does not become a requirement to install a local model.
- Local Model Registry & Runtime: load configuration from the database together with generation parameters (`params`: `temperature`, `max_tokens`, `json_mode`); support a safe-endpoint check (`is_safe_endpoint`) that allows loopback/localhost (`127.0.0.1`, `localhost`, `::1`) when the flag `EVIDENCE_ALLOW_LOCAL_AI=true` is on, for local Ollama/vLLM; filter the denylist of sensitive environment variables (`_SECRET_DENIED`) against `secret_ref`; strip reasoning tags (`<think>`) from reasoning models; wrap the AI-selection timeout at 70% of the query timeout, with graceful degradation so the application does not hang.
- Acceptance: the dependency inventory records the root and the relative path/real path of each tool; a clean install and startup do not depend on the global PATH; a missing root/dependency reports the correct error and does not fall back to another path; changing model/API/Local configuration does not require a source edit. Check that code/scripts contain no hardcoded PATH/LLM; the literal `E:\Programs` appears only in approved deployment-configuration data/policy, not in application logic.

---

## C. Application feature description

Priority marks: **P0** = mandatory in the MVP/release gate; **P1** = after the MVP, with a measurement. Feature codes are used for reference in the plan (F) and the design (D).

### C.1 Evidence-based question answering (USER)

| Code | Feature | Behavior | Constraints and safety | Priority |
|---|---|---|---|---|
| Q1 | Select scope | Select one/many categories or “Tất cả danh mục được phép” (All authorized categories); a valid scope is required before asking. The administrative-document (văn bản) type filter is independent; `as_of_date` defaults to today in the configured timezone | `scope_mode=SELECTED` needs valid `category_ids`; `ALL_AUTHORIZED` is resolved by the server into the categories currently granted, and still filters ACL in SQL, with no wildcard that drops rights | P0 |
| Q2 | Enter a question and Analyze | The user enters natural-language text; `analyze` produces fact chips (subject, act/event, time, locality, dossier type, conditions) and query rewrites; it does not conclude | Rules-first; a maximum of 2 LLM call attempts per run in total, counting retry/fallback | P0 |
| Q3 | Fact-chip dirty state and requery | Editing/deleting/adding a chip does not call again on its own; show "Đã chỉnh sửa dữ kiện — kết quả bên dưới dựa trên dữ kiện trước đó" (Facts were edited — the result below is based on the previous facts); the button "Cập nhật dữ kiện & Tra cứu lại" (Update facts & search again) sends one request with `base_query_id`, `base_facts_revision`; the old result keeps the `stale` label until new evidence (căn cứ) arrives | Facts inferred by the AI are not treated as confirmed on their own: `user_confirmed` / `extracted_unconfirmed` / `inferred_uncertain` | P0 |
| Q4 | Ask directly for an Article/Clause/symbol number | The Legal Reference Router skips Analyze when the match is unique + approved + ACL + `as_of_date` | If it is ambiguous, return to Analyze; do not promise 100% | P0 |
| Q5 | Evidence-first | Validated evidence cards appear first, the explanation appears after (SSE). Cards are grouped by role: principal provision / subject / condition / exception / transition / authority | Auto-merge is only UI organization; it does not turn independent clauses into new evidence | P0 |
| Q6 | Result status labels | **Đã xác định căn cứ (Evidence identified) / Có điều kiện (Conditional) / Thiếu căn cứ (Insufficient evidence) / Nguồn xung đột (Conflicting sources)**; when no suitable document exists: "Chưa tìm thấy tài liệu được phép truy cập" (No document you are allowed to access was found) | Status is computed from rules; no decorative color badge, no self-assessed percentage | P0 |
| Q7 | Evidence-coverage checklist | Separate `source_verified`, `effective_checked`, `applicability_checked`, `claim_supported` (and the details `transition_checked`, `required_facts_complete`, `scope_expansion`, `citation_verified`) | Do not claim verification while `temporal_unknown` remains, or when there are only candidates | P0 |
| Q8 | A finding with citations, and a reference suggestion | Claims + suggestions follow the schema in SRS §6.2, and each item has `evidence_ids`; three content layers are clearly distinguished: verbatim / finding with citations / reference suggestion | A claim with no source ⇒ downgrade it to "chưa xác minh" (not yet verified) or block it | P0 |
| Q9 | Refuse correctly and ask again | If evidence is missing, say clearly that evidence is insufficient; if an essential fact is missing, ask for at most 1–3 facts | Do not invent an article or clause | P0 |
| Q10 | Controlled expansion outside the category | When a clause cites outside the category: (a) do not expand, and report the gap; (b) open each related administrative document the caller is allowed to access, labeled "Nguồn ngoài danh mục" (Source outside the category) | Do not open an administrative document the caller may not access | P0 |
| Q11 | Copy, print, export | Preserve scope, `as_of_date`, the corpus date, the source symbol number, and the amendment (sửa đổi) warning | Refresh/print/copy does not drop the warning | P0 |
| Q12 | Feedback | Four types: Căn cứ sai (Wrong evidence) · Thiếu căn cứ (Missing evidence) · Văn bản hết hiệu lực (Administrative document no longer in effect) · Trích dẫn sai đoạn (Wrong passage cited); they enter the curator queue and link to an evaluation case | Feedback that is not yet approved does not change ranking | P0 |
| Q13 | My history | Review one's own questions and results if policy allows; reopening a citation must recheck rights and effectivity (hiệu lực) | The citation snapshot follows audit rights | P0 |

### C.2 Viewing sources and effectivity

| Code | Feature | Behavior | Constraints and safety | Priority |
|---|---|---|---|---|
| V1 | Original PDF viewer | Open the exact bytes of the immutable PDF, the correct version/page, and scroll to the span; if the bbox is not trustworthy, fall back to opening the correct page and showing the quote for comparison, with the warning "chưa tô chính xác" (not highlighted precisely) | Do not overlay new text, and do not paint color over PDF content | P0 |
| V2 | Article tree | Built from the database: Chương (Chapter) > Mục (Section) > Điều (Article) > Khoản (Clause) > Điểm (Point); clicking a node jumps to the PDF | Do not build it from the PDF at view time | P0 |
| V3 | Sticky Amendment Banner | Node state **correct for `as_of_date`**: `active`, `modified`, `repealed`, `suspended`, `not_yet_effective`, `unknown`; a fixed warning in the toolbar + a badge right at the highlight region, with a link that opens the correct approved replacement (thay thế) PDF/version/page/node | Text label + icon + description by date; not color alone; `modified` does not mean the whole administrative document has lost effectivity | P0 |
| V4 | Amendment chain | The chain A ← B ← C shows the related amendments correctly; a button "Xem nội dung áp dụng tại ngày tra cứu" (View the text applicable on the query date); when `as_of_date` is before the amendment date, phrase it as "Quy định được thay đổi từ [ngày]" (The provision is changed from [date]) and always consider transition/suspension | Missing metadata ⇒ "Hiệu lực chưa xác minh" (Effectivity not yet verified); do not mark the whole document as no longer in effect on your own | P0 |
| V5 | Official source and file download | A link to the official publication page if the curator has verified it; download the PDF according to rights | Does not replace the internal viewer | P0 |

### C.3 Chat Agent for the user (icon at the right corner of the screen)

| Code | Feature | Behavior | Constraint | Priority |
|---|---|---|---|---|
| G1 | Launcher | A round Orb, 56–64px, default bottom-right corner; click to open, click again to collapse the panel; respect the safe area/work area. On the desktop only the round region is shown and receives interaction; there is no square background or leftover shadow | State comes from the backend; light motion, reduced-motion; desktop follows C.12/S14 | P0 |
| G2 | Conversation panel | A sliding pane on desktop, full screen on a phone; the panel header has a scope chip, `as_of_date`, and FactChips; compact evidence cards; tabs Trả lời (Answer) / Phân tích (Analysis) / Liên quan (Related) | Uses the same two-phase SSE contract as the full page | P0 |
| G3 | Page context | Opened from an administrative-document or category page, it suggests a scope from the page, and the user can dismiss it; a clear label when the query expands outside the scope | Does not expand silently on its own | P0 |
| G4 | Open the full page in the same session | The button "Mở trang đầy đủ" (Open the full page) keeps the session, FactChips, and results | Session state is on the server; the browser keeps only the session id | P0 |
| G5 | Suggestion chips | A row of next-question chips under the answer (A2) | Each suggestion has been trial-run through retrieval | P0 |
| G6 | Viewer without losing the conversation | Clicking a citation opens the PDF viewer at the correct anchor without leaving the conversation; on a phone: a full-screen viewer with a back button | Recheck ACL on open | P0 |
| G7 | Advisory only (tham mưu) | There is no button that executes or approves business work; the workflow is fixed, at most 2 LLM call attempts per turn, counting errors/retry/fallback under C.9 | Invariant B.3; no autonomous agent loop | P0 |
| G8 | Stop and try again | Stop the turn that is running; keep valid evidence and the label that the result is not finished. Try again is an explicit action, creates a new `run_id`, and does not duplicate the user message | Idempotency per turn; do not mix events/claims from two runs; recheck ACL/policy/revision | P0 |
| G9 | Conversation content | Markdown/tables/code blocks are rendered safely; copy includes the source, history is separate, and the composer keeps the draft when there is an error | Do not execute HTML/script from the model/PDF; attachments into the corpus remain limited to a CURATOR who has the right | P0 |

### C.4 AI memory for queries and long context

Principle: **memory helps understand the question; it does not help answer it.** A legal answer is based only on evidence retrieved again from the corpus at the time of the question.

| Code | Layer | What is stored | Used for | Safety limit |
|---|---|---|---|---|
| M1 | Session state | Facts with a source label, scope, `as_of_date`, resolved references ("điều đó" (that) → node_id), questions still open | Rewrite a follow-up question, display FactChips | Attach `facts_revision` and `snapshot_revision`; if the snapshot changes ⇒ "cần kiểm lại" (needs rechecking), and do not use it automatically |
| M2 | Rolling conversation summary | P0: template/extraction in code; LLM summary is P1 only, a separate job with quota/egress/audit, and it does not block evidence | Keep long context: the LLM sees only state + summary + a few recent turns | Label "không phải căn cứ" (not evidence); the validator rejects a claim that points at it; it does not contain a legal quote |
| M3 | User preferences (opt-in) | Default category, frequently used scope, display style | Pre-fill scope | Do not store legal content or sensitive identifiers; it can be viewed and deleted |
| M4 | Retrieval hints | Aliases, legal synonyms, common ways of referring → a standard symbol number/node | Expand the query, route to an administrative document | Only a curator-approved hint takes effect; user feedback does not change ranking on its own |
| M5 | Administrative-document map | A table of contents determined from the node tree, a list of related administrative documents | Route across many administrative documents, explain scope | Generated in code; an LLM summary of an administrative document is P1 and labeled "không phải căn cứ" (not evidence) |

**Shared rules for memory**

- Every use must recheck ACL, approved status, and effectivity at `as_of_date`; a node that no longer has rights is dropped from state, and its existence is not revealed.
- Memory is per user; an admin does not read the content by default. A long-term conversation is written only when an approved retention policy exists and the user has opted in; before that, use a temporary RAM session.
- `incognito=true`: session content, facts, summary, and events stay only in backend RAM, with a default idle TTL of 30 minutes / configurable; when the TTL expires, the user signs out, or the session ends, it is destroyed. Do not write content into PostgreSQL, the query/answer log, a temp file, a durable cache, or durable SSE replay; audit records only minimal metadata, not the question/quote/summary. Restarting the backend loses the temporary session; the UI says so clearly. Do not load an old conversation into a session that is not stored.
- The user views/edits/deletes each item or all of them in "Bộ nhớ của tôi" (My memory); a real delete removes it from operational data, including messages, summary, facts, derivatives, and cache belonging to the session/user. Cancel jobs that are using that content; increment `memory_revision` so an old result/job does not write the deleted data back. Citations/audit that must be kept under policy are separated from memory and do not keep a copy of a confidential question.
- **Interface connection and flow control:** `EphemeralMemoryService` connects directly to the `EvidenceChat` interface over two-phase SSE streaming. The user views the list of session-memory items in the drawer "Bộ nhớ phiên (RAM)" (Session memory (RAM)), deletes one item (`DELETE /api/v1/memory/{item_id}`), deletes all RAM (`DELETE /api/v1/memory`), presses the Stop button (Dừng) (`POST /turns/{id}/cancel`) or Try again (Thử lại) (`POST /turns/{id}/retry`). Turning on the switch "Lưu vào sở thích tra cứu" (Save to search preferences) (`GET/PUT /api/v1/memory/preferences`) allows saving and automatically applying the default category through the function `_with_preferences`.
- Backups have a finite retention period and a published destruction schedule; do not promise that content is deleted immediately from every immutable backup. On restore, re-apply the latest minimum deletion-request ledger before opening the service; if the reconciliation ledger is missing, do not open access yet. Do not let deleted content return to history, summary, cache, or suggestions.
- Local Mode: memory lives in local PostgreSQL. API Mode: the summary is data too, and it is sent outside only when policy allows.
- No semantic answer cache; do not learn from the conversation into ranking on your own.

**Long context**

- The LLM does not receive the entire history, only session state + summary + a few recent turns + the evidence that was selected.
- A follow-up question is rewritten conservatively into a standalone question and **shown as "Đang hiểu là: …" (Understood as: …)** for the user to correct; if a decisive condition is missing, ask again with at most one question using chip choices, and do not guess.
- Evidence packing: a token budget per stage; principal conditions and exceptions are placed at the start and the end; cut on node boundaries, and do not cut in the middle of a Clause (Khoản); do not compress quotes.
- A question with many aspects/many administrative documents: handle it by aspect and then merge; each claim still goes through the validator; exceeding the budget ⇒ `partial`, and say clearly which part is not yet sufficient.

### C.5 AI analysis and suggestions

Three labels are clearly distinguished in the interface: **Căn cứ (Evidence)** (a verbatim quotation) · **Phân tích (Analysis)** (inferred from evidence, with conditions not yet verified) · **Gợi ý (Suggestion)** (what should be asked or checked next, not an assertion). Each analysis item is attached to at least one `evidence_id` that has passed the validator; an item with no evidence is not displayed. Reference suggestions are filtered automatically to exclude evidence already cited in the main findings (claims), so they are not repeated. PostgreSQL FTS query optimization uses `LATERAL` syntax in `authorized_search.py` to compute `to_tsvector` once per candidate row, combined with filtering Vietnamese question function-words, to prevent query congestion when the number of administrative documents is large. It runs on demand or asynchronously, and **does not slow `evidence_ready_ms`**; rules come first, and the LLM is only for phrasing; Local Mode always has a rules/extractive version. For the curator, the AI only **suggests**; the curator presses accept, edit, or reject.

| Code | Feature | For whom | How it works | Against error | Bundle |
|---|---|---|---|---|---|
| A1 | Structured situation analysis | USER | Extract facts from the description (subject, act, time, figures) and then arrange them against evidence: conditions already satisfied / not yet verified, exceptions, time milestones, consequences stated in the administrative document | Every row has an `evidence_id`; unconfirmed facts appear as chips to edit; if a condition is missing, do not conclude that it is allowed or not allowed | P0 |
| A2 | Suggest the next question | USER | Generate from known gaps: an `uncovered` aspect, a condition not yet verified, an exception, a related amending administrative document; do not generate freely | Trial-run retrieval (dry-run): there must be evidence inside the ACL, otherwise drop it | P0 |
| A3 | Information still missing | USER | List the facts that decide the scope of application and that the user has not provided, as quick-fill chips; once filled, requery only once | Ask only for facts that the evidence actually uses as conditions | P0 |
| A4 | Points to note inside the evidence | USER | Rules that recognize time limits, numbers, subjects, exceptions ("trừ trường hợp" (except where)), and attached conditions; highlight them in the evidence card and the PDF viewer | Mark only a passage that already exists in `text_original`; do not add interpretation | P0 |
| A5 | Compare versions of one Article | USER | A deterministic diff between versions/amendments of the same node by `as_of_date`; the AI only phrases the change briefly | The diff comes from approved text; if the previous version is missing, say it is not available | P0 |
| A6 | Related administrative documents and Articles | USER | A graph from `node_references` + `node_amendments`: guiding administrative documents, amendments, two-way references, the amendment chain | Entirely deterministic, no LLM; show only nodes inside the ACL; a relationship not yet approved has its own label | P0 |
| A7 | Plain-language explanation | USER | Turn on "giải thích đơn giản" (simple explanation) for each claim, shown beside the quote | It is a claim, and it goes through the validator like an ordinary claim; adding meaning is forbidden | P1 |
| A8 | Summarize a Chapter/Section | USER | Extractive first (title + key sentence), LLM optional | Label "không phải căn cứ" (not evidence); do not use it as evidence | P1 |
| A9 | Follow changes | USER | Subscribe to a question or an Article; if a snapshot change affects that node ⇒ notify inside the application, and reopen with the new `as_of_date` | Notify only inside the application; do not send content outside | P1 |
| A10 | Compare two administrative documents | USER | Align by chapter/article structure, diff, and list the main differences | List only differences that have a quote pair; do not conclude which is better | P1 |
| C1 | AI suggestions for the curator | CURATOR | (a) amend/supplement (bổ sung)/repeal (bãi bỏ) relationships detected from sentence patterns ("sửa đổi, bổ sung khoản 2 Điều 5 của …" (amend and supplement clause 2 of Article 5 of …)); (b) unresolved references; (c) duplicate/similar administrative documents; (d) pages/nodes parsed abnormally; (e) retrieval hints drawn from feedback | Each suggestion includes the source span and a confidence level, ranked by risk; a rejection is recorded so precision can be measured; nothing is applied on its own | P0 for a, b, d; P1 for c, e |
| D1 | Knowledge-corpus gap analysis | ADMIN, CURATOR | Group "không đủ căn cứ" (insufficient evidence) questions by topic ⇒ suggest the kind of administrative document that should be added; statistics of wrong feedback by administrative document | Use aggregate figures; question content is shown according to rights; do not download administrative documents on your own | P1 |

### C.6 Layers against hallucination and wrong retrieval

Added on top of the validators that already exist (ACL, span, node effectivity, ID allowlist, numeric/date, polarity/modality).

| Layer | What it does | Measured by |
|---|---|---|
| L0. False premise | The question mentions an Article/Clause/administrative document that does not exist or has the wrong symbol number ⇒ answer "không có" (does not exist), with the actual list (for example, the administrative document only has Articles 1–N); do not search for a near match and then answer at random | `false_premise_detection_rate` |
| L1. Retrieve the right object | Constraints extracted from the question (symbol number, administrative-document type, year, agency, time milestone, numbers) must match the evidence; guard against confusing "neighbors" (Article 15 and 150, Clause 1 and 11) and against confusing versions; produce `retrieval_diagnostics`; a mismatch ⇒ expand, ask again, or refuse | `wrong_doc_rate`, `wrong_node_rate` |
| L2. Route to the administrative document before the node | Select candidate administrative documents by symbol number, title, type, category, and the administrative-document map, and only then search for the node; deduplicate across versions, and prefer the version in effect at `as_of_date` | A separate ablation |
| L3. Contradiction and exception | The selected nodes say different things about the same object (number, time limit, subject, "trừ trường hợp" (except where)) ⇒ state both, and do not pick one | `missed_exception` |
| L4. Constrained generation | Only claims with `evidence_ids` on the allowlist; deterministic configuration/low temperature if the adapter supports it; forbid numbers, dates, and names that are not in the evidence; do not use outside knowledge | `validator_reject_rate` |
| L5. Whether a claim is supported by evidence | Tier 1 is deterministic: entity overlap, numbers, dates, negation, modality. Tier 2 (P1): a local entailment model, turned on only when it passes the POC and does not increase false rejection. A claim that does not pass ⇒ drop it or show "chưa xác minh" (not yet verified) | `unsupported_claim_rate` |
| L6. Honest interface | Labels come from evidence state and the validator, not from the LLM's "confidence"; do not use "chắc chắn" (certain)/"đã xác minh" (verified) when that has not been established | UI test |
| L7. Feedback loop | "Sai/thiếu/lỗi hiệu lực" (Wrong/missing/effectivity error) enters the curator queue; an approved case enters the regression suite, and does not enter the calibration set or held-out | A process that has a test |

**Trap set** (suggested 40–60 questions, separate from Gold [Not implemented — see ADR-010] v0): the agent drafts them from real PDFs, and a person who knows the business approves them. It includes false premises, Articles that do not exist, near-similar symbol numbers, administrative documents no longer in effect, questions outside scope, injection commands inside a PDF, requests to ignore the source, and requests for advice that goes beyond the evidence. The acceptance threshold is locked by the owner after the baseline. The dossier does not claim that hallucination is eliminated completely; the goal is to measure it, reduce it, and always say clearly when evidence is insufficient.

### C.7 Accuracy and speed

**Accuracy** (each step behind a feature flag, turned on only when the benchmark does not regress): expand the query with approved retrieval hints; split a multi-aspect question with rules first, the LLM after; filter metadata extracted from the question (administrative-document type, agency, year, category); route to the administrative document before the node (L2); conditional rerank. Each step has an ablation.

**Speed** (safety invariants do not change):

- Compute at index time: `text_folded`, `tsvector`, embedding, breadcrumb, applicability header, administrative-document map; load the model once at startup and keep the ONNX session.
- Connection pool, prepared statements; lexical and dense run in parallel, compared with sequential/CTE exactly as in the SRS benchmark.
- Shortcut: if the Legal Reference Router matches uniquely, skip Analyze.
- Embedding cache: separate from analysis; the key includes a hash of the exact input + model/tokenizer/prefix revision + security partition; do not fold the user in by default. An incognito session does not write a durable cache; use a same-session RAM cache only if needed.
- **The analysis cache defaults to OFF.** Turn it on only when the key covers principal/session, the rewritten question, `facts_revision`, `memory_revision`, scope, `as_of_date`, ACL/policy revision, model/tokenizer/prompt-schema/hints revision, and every input that is actually read. If any fingerprint that affects the output is missing, skip the cache; recheck rights on read.
- **The retrieval cache defaults to OFF.** If it is turned on, the key includes the ACL fingerprint + policy revision + `snapshot_revision`/source-review revision + `index_revision` + model/tokenizer/hints revision + scope + `as_of_date` + query/facts. A change of rights, data, model, policy, or snapshot must invalidate. No semantic answer cache; do not use a cached result to bypass a rights check.
- Evidence-first: show evidence as soon as it is ready, and stream claims after; the interface prefetches the cited PDF page on hover.
- Measure `retrieval_ms`, `evidence_ready_ms`, `first_claim_ms`, `final_answer_ms` (P50/P95) on the target Windows machine; the baseline is in WP 2.13; numeric targets are locked by the owner after the baseline; CI checks performance regression with a tolerance.

### C.8 Document-corpus administration (CURATOR, REVIEWER)

| Code | Feature | Behavior | Constraints and safety | Priority |
|---|---|---|---|---|
| K1 | Categories | Create/edit/hide/soft-delete/restore; parent–child at a configured depth (for example 3); N–N with documents; move documents between categories; import/export JSON/CSV with validation | Prevent cycles; a soft delete does not delete the original file/embedding still used elsewhere; a hard delete goes only through an approval process | P0 |
| K2 | Document record | Standard metadata (SRS §2.4): symbol number, agency, issue/effectivity date, status, source, hash, version…; effectivity status at Article/Clause level | Do not infer "còn hiệu lực" (still in effect) from the issue date; distinguish `valid_time` and `recorded_time` | P0 |
| K3 | PDF upload | Drag and drop/choose a file; check magic bytes, quota, SHA-256; store an immutable copy; ingest progress by job | A file with bad structure/hash/metadata can never become `approved` | P0 |
| K4 | URL import | Only domains on the allowlist; DNS pin/recheck; block private/local addresses; limit redirects/size | A URL outside the allowlist is blocked, with a reason; a hash change at the same URL ⇒ a new version waiting for approval | P0 |
| K5 | Domain-allowlist management | The admin adds/edits/disables a domain after verification (DNS/HTTPS check, the person who verified, a note); every change is audited | If a domain is disabled, import stops | P0 |
| K6 | Ingestion pipeline | Native parse of each page; page diagnostics (the character `�`, valid-syllable ratio, text coverage, reading order); recognize TCVN3/VNI + transcode with a round-trip check; `needs_ocr` + an OCR-plugin interface | A bad page never becomes a verified quote | P0 |
| K7 | Parse the node tree | Chapter/Section/Article/Clause/Point/Appendix (Phụ lục); an unstructured administrative document is handled by heading/page; `text_indexed` has a breadcrumb; applicability header; `node_references`; `parse_confidence` | Do not invent an Article/Clause | P0 |
| K8 | Risk-prioritized approval queue | Low parser confidence, a skipped clause, transcoding, a shifted bbox, effectivity not yet approved, an AI suggestion ⇒ enter the queue, ranked by risk | Effectivity metadata always needs a person to approve | P0 |
| K9 | Curator Split-View | Left: PDF.js of the immutable copy, select a page/highlight a span. Right: the `document_nodes` tree + a form (label, position, the node's effectivity window, an amendment link). Clicking a node jumps to the PDF and the reverse | Autosave draft ≠ Approve; `If-Match`/revision; audit the actor; shortcuts do not approve while typing; confirm when editing effectivity/an amendment | P0 |
| K10 | Amendment relationships and node effectivity | The CURATOR creates/edits a draft `node_amendments`; the REVIEWER approves with a revision and an audit; node state follows `as_of_date` | Accepting an AI suggestion only creates/updates a draft; it does not publish or increment an approved revision when REVIEWER is missing | P0 |
| K11 | Effectivity snapshot | The resolver runs to a fixed point (detects a cycle/broken edge/overlap/conflict), staged → atomic publish by `snapshot_revision`; stale fails closed; invalidate the cache | Do not leak an administrative document outside the ACL | P0 |
| K12 | Document versions | A different hash ⇒ a new version; select the copy as of a date; compare versions (A5) | The old PDF stays unchanged | P0 |
| K13 | AI suggestions for the curator | See C1 in C.5 | Suggestions only | P0/P1 |

### C.9 AI models, policy, and operating modes (SYS_ADMIN)

| Code | Feature | Behavior | Constraint | Priority |
|---|---|---|---|---|
| R1 | Model Registry | The admin configures API or Local: adapter/provider, approved endpoint/runtime, model ID/artifact, capability, parameters, revision, secret reference, status, and quota | Do not hardcode provider/model/endpoint/key/model path; no LiteLLM; changing a model within a supported capability/adapter does not require a code change | P0 |
| R2 | Stage routes | Each stage selects a model for API Mode and Local Mode; switch models through the Registry | Changing the embedding model ⇒ a new index in parallel, then cutover | P0 |
| R3 | Two operating modes | API Mode / Local Mode, set by system configuration and category policy | Local Mode: fully offline (search, embedding, rerank, analysis, PDF viewing); no external service for sign-in, licensing, or startup | P0 |
| R4 | Egress policy | `remote_allowed` by the formula in SRS §8.4 with `mode == API`; blocked by default; audit every route decision | Remote denied ⇒ `REMOTE_AI_DENIED`; fallback only within the same privacy zone | P0 |
| R5 | Secret management | The key is entered once, encrypted, and masked; the raw key cannot be read back | Do not log the key | P0 |
| R6 | Egress control in Local Mode | An egress guard in the application + a sample Windows Firewall rule + a `verify-egress` script | Actually disconnecting the Internet is additionally guaranteed by infrastructure/the OS | P0 |

**LLM configuration and budget contract**

- Only two operational values, `API` / `LOCAL`. The admin configures the route of each stage for both modes; the USER sees a read-only badge, and does not enter a key/endpoint in chat. API Mode uses an LLM through an approved API; Local Mode uses an internal LLM and has no fallback path to the Internet. A new provider outside the supported adapter protocol needs an adapter that has tests; do not assume every API is compatible.
- Embedding, reranker, and LLM are independently configured capabilities. The POC does not turn a trial model into the product's fixed model. An ONNX requirement in the embedding/reranker POC does not forbid a GGUF LLM, or another format, running on a local runtime that has been verified. The model path/runtime path is obtained through configuration/manifest/platform API.
- When there is no model/key yet: the system still returns real evidence/extractive output; the UI says “Chưa cấu hình mô hình AI” (AI model not yet configured), `answer_generated=false`, and it does not fake AI analysis. The owner enters the secret later through the administration interface; do not put a secret into a prompt, a fixture, or a log.
- Each `run_id` has `llm_attempt_budget=2` for Analyze + Generate. Every request sent to the LLM, including timeout/error/retry/fallback, consumes one attempt; a hidden retry does not exceed the budget. If only one attempt remains, prefer the stage that is needed, or return extractive output. The P0 summary, A2 suggestions, and aspect splitting do not create extra LLM calls outside the budget.
- Stop cancels work that can still be cancelled, does not recall a request the provider has already processed, and does not refund the budget on its own. When the user presses Thử lại (Try again), a new run is created, with a rate limit and a quota; it does not loop forever on its own.
- Profile B, lexical + extractive, is a publicly stated degraded capability, not a third mode. S0 may accept offline-core feasibility under this profile if the model is not yet good enough, and must state clearly which of dense/rerank/generation has not been checked. The S3 gate for an AI configuration must check the provider/model that was actually selected; a mock/FakeAdapter or profile B does not substitute for that evidence.

### C.10 Quality, operations, and security

| Code | Feature | Behavior | Priority |
|---|---|---|---|
| Z1 | Gold [Not implemented — see ADR-010] Dataset v0 | 150–200 questions from real PDFs, approved by a reviewer. Each case has evidence/version/date/source hash, `scenario_group_id`, and `split_revision`; rephrased questions or the same situation stay in the same split | P0 |
| Z2 | Benchmarks B0–B7 and ablation | Run on approved Gold [Not implemented — see ADR-010]; `ranx`/bootstrap; pin the corpus hash and the model/tokenizer revision; the report has a confidence interval | P0 |
| Z3 | Trap set and anti-hallucination metrics | See C.6 | P0 |
| Z4 | Quality dashboard | `retrieval_ms`, `evidence_ready_ms`, `generation_ms`, tokens, cost, `fallback_reason`, abstention rate, the L0–L7 metrics; do not display chain-of-thought | P0 |
| Z5 | Audit | Append-only; record document access, route decisions, approvals, configuration changes, and opening an old citation; a configurable retention period (default 2 years) | P0 |
| Z6 | Backup/restore | Encrypted backup, a restore drill onto a clean machine | P0 |
| Z7 | Windows distribution bundle | Core Pack, Model Pack manifest (id, sha256, license, revision, dimension, RAM/disk), Data Pack; a clean demo install under 10 GB, measured in CI | P0 |
| Z8 | RBAC + ABAC | Rights by role and by attribute (category, confidentiality level); SYS_ADMIN does not read content by default | P0 |
| Z9 | Input security | SSRF, fake MIME, prompt injection through PDF/metadata, XSS from PDF, CSP, ACL leakage through cache/tokenizer | P0 |

Calibration is used to tune thresholds; regression is used repeatedly during development; held-out and the trap hold-out lock content/answer rights against the person who tunes, and run only after the candidate/config is locked in a lock-in round. The split manifest is immutable by revision, and the group/semantic-duplicate check has a person review it; zero overlap of case IDs alone is not enough. If a held-out result is used to fix/tune, mark that set as already used and do not report it as an independent evaluation of a later candidate; a set that has not been seen is required. The source corpus must still sit in the benchmark index so retrieval can find it; do not confuse separating evaluation questions with removing the source from the benchmark corpus.

### C.11 Primary usage flows

**L-1. First question (USER).** Select a category (Danh mục) → (optional) change the application date (Ngày áp dụng) → enter the situation → see FactChips and the skeleton "Đang tìm căn cứ…" (Searching for evidence…) → grouped evidence cards appear (Phase 1) → the neutral sentence "Đã tìm thấy và kiểm tra nguồn của X căn cứ. Đang phân tích điều kiện áp dụng, hiệu lực, quy định chuyển tiếp và ngoại lệ…" (Found and checked the source of X pieces of evidence. Analyzing conditions of application, effectivity, transitional provisions, and exceptions…) → claims and the status label (Phase 2) → coverage checklist → suggested next questions.

**L-2. Edit facts.** Edit one or more chips → the bar "Đã chỉnh sửa dữ kiện…" (Facts were edited…) appears → press "Cập nhật dữ kiện & Tra cứu lại" (Update facts & search again) → the old result is marked `stale` → the new result replaces it.

**L-3. Open evidence that has been amended.** Press `[1]` → the viewer opens the correct page, with highlight, and a fixed banner "Khoản này … đã được sửa đổi bởi … từ ngày …" (This clause … has been amended by … since …) → "Xem văn bản sửa đổi" (View the amending administrative document) opens the replacement PDF at the correct page and node → "Xem nội dung áp dụng tại ngày tra cứu" (View the text applicable on the query date).

**L-4. A quick question with the Chat Agent.** Press the icon at the right corner → the panel slides out with a scope suggested from the page → ask → compact evidence cards → press evidence to open the viewer → return to the conversation → "Mở trang đầy đủ" (Open the full page).

**L-5. The curator ingests a document.** Upload a PDF or import a URL (a domain already allowed) → the job runs, and progress is visible → the approval queue (by risk) → the CURATOR saves a draft of the node/metadata and suggestions → the REVIEWER approves the document/version/effectivity metadata/amendment relationships → the effectivity snapshot is published.

**L-6. The admin adds a source domain.** Administration (Quản trị) → Allowed domains (Domain cho phép) → Add (Thêm) → enter the domain name → the system checks (DNS, HTTPS, not an internal address) → confirm the person who verified + a note → turn it on.

**L-7. Local Mode.** Administration sets the mode → run `verify-egress` → all question answering and PDF viewing run without the Internet; every operation uses the local model; if the local LLM fails ⇒ return verified evidence with "Giải thích tạm thời không khả dụng" (Explanation is temporarily unavailable), and do not call the API.

**L-8. The USER on Windows.** Open the app shortcut → sign in inside the app → the sign-in window disappears completely → a round Orb at the right corner of the desktop → click to open chat/click again to collapse → open a PDF or the workspace in the same session → collapsing back to the Orb does not lose the conversation → sign out or Exit (Thoát) through the system-tray menu. There is no need to open a browser, and no console window appears.

### C.12 The USER application on Windows and the portal boundary

| Code | P0 behavior | Acceptance |
|---|---|---|
| W1 | The Tauri 2 desktop shell reuses the User Portal/components/API/auth/RAG; the Admin Portal is a separate layout | One backend/DB/pipeline; no forked chatbot; a LAN client connects to the configured server, and does not install a database on each USER machine on its own |
| W2 | A shortcut and sign-in inside the app; the backend endpoint comes from the deployment configuration | When the session ends, return to sign-in; do not open a browser on your own; do not hardcode host/port, and do not seize or stop an unrelated service |
| W3 | The round Orb, the panel, and login each have their own window state; login/panel backgrounds are opaque, and only the region outside the Orb is transparent | No leftover login frame/square/shadow; a hit-test outside the Orb does not block the app underneath |
| W4 | Click to toggle; collapse/open, the workspace, and the viewer keep the same session/turn/facts/revisions | Do not duplicate a turn, and do not lose a draft; closing the panel only collapses to the Orb, and does not delete the session |
| W5 | Drag/resize has its own region, and can be turned off; buttons and the title are not covered by the drag region | Dragging does not fire an open/close click; there is no drag layer covering the composer/citation; restore the position inside the work area when DPI/monitor changes |
| W6 | System tray: Hiện/Ẩn trợ lý (Show/Hide the assistant), Đăng xuất (Sign out), Thoát (Exit); always-on-top is a user choice | Hide does not mean sign out; sign-out stops the stream and clears state and the session secret; Exit does not stop the shared LAN backend |
| W7 | Real analysis/suggestions/citations follow the shared pipeline; stop/retry, and clear states for lost connection and for no model yet | No fake progress, and do not label a template as AI on your own; the native build and the web build use the same contract |
| W8 | Type and responsive behavior are aligned across User/Admin/desktop; the USER UI has no corpus upload, ingestion, or user/model management | Check multiple sizes/DPI, keyboard, contrast, reduced-motion; server-side rights are still checked |

The web User Portal is a surface for the same functions when it is deployed; the desktop is the USER's primary way of using the system on Windows. The Admin Portal has Dashboard, Tài liệu (Documents), Danh mục (Categories), Ingestion/jobs, Tài khoản/quyền (Accounts/rights), Cấu hình AI (AI configuration), Monitoring/audit, and Evaluation; each module must have a screen, or a clear state for when there is no data yet, and the sidebar must not lead to a fake page. Administration roles see only the modules they have been granted, and do not by default see a private conversation or business content.

---

## D. Detailed UX/UI design

The design direction already locked: **Modern Enterprise / Evidence-First**, Light Theme by default, Navy + Blue + White + Slate. This is the application's palette; do not take the ChatGPT palette, the DIL demo, or a framework's colors as the standard. Dark Mode is P1.

### D.1 UX principles

1. **Evidence (căn cứ) first, the explanation after.** The first thing the user sees is the verbatim source and the PDF page; the explanation is the second layer.
2. **Say clearly what is known and what is not.** Every result has a scope (category, application date, corpus date), a status label, and a coverage checklist. Do not use a self-assessed percentage, and do not use decorative color to create trust.
3. **Color is not the only signal.** Every state has an icon + a text label + a description by application date.
4. **The user keeps the right to correct.** Facts inferred by the AI can always be edited; a follow-up question shows "Đang hiểu là…" (Understood as…) so it can be corrected; no silent action.
5. **Do not lose context.** Opening a PDF, opening an administrative document (văn bản) that amends (sửa đổi), and opening the full page all keep the conversation and the results.
6. **Quiet, and readable.** The one point of emphasis is the verbatim evidence card; everything around it is neutral. No background effects, no gradients, no heavy drop shadows. Motion only responds to the user's action.
7. **The same interface language for the widget and the full page.** Shared components, a shared SSE contract, shared labels.
8. **Interface copy is in plain Vietnamese, in the active voice, with sentence case at the start of a sentence**, buttons name the action exactly ("Tra cứu" (Search), "Lưu nháp" (Save draft), "Duyệt" (Approve)), and the same action keeps the same name throughout.

### D.2 Design system

**D.2.1 Color — official tokens (SRS §9.5)**

| CSS token | HEX | Use |
|---|---|---|
| `--color-brand-navy` | `#163A5F` | Sidebar, top bar, administration-area titles, Chat Agent panel header, launcher |
| `--color-brand-navy-hover` | `#102B47` | Hover on the Navy bar, launcher hover |
| `--color-action` | `#2563EB` | Primary search button, citation link `[1]`, active tab, focus ring |
| `--color-action-hover` | `#1D4ED8` | CTA hover |
| `--color-background` | `#F8FAFC` | Background of the whole app |
| `--color-surface` | `#FFFFFF` | Chat, Evidence Cards, PDF Viewer, modal |
| `--color-surface-muted` | `#F1F5F9` | Secondary information cards, skeleton, the user's message |
| `--color-text-primary` | `#0F172A` | Main content and quotations |
| `--color-text-secondary` | `#475569` | Meaningful metadata, breadcrumb |
| `--color-border` | `#CBD5E1` | Input, card, and separator borders |
| `--color-evidence-bg` | `#EFF6FF` | Evidence selected / currently shown in the viewer |
| `--color-evidence-text` | `#1E40AF` | Citation/evidence label |
| `--color-success` | `#047857` | A check passed, a source allowed to be used; always with an icon/text |
| `--color-warning` | `#92400E` | A condition not yet certain, effectivity (hiệu lực) not yet complete |
| `--color-warning-bg` | `#FFFBEB` | Sticky Amendment Banner and temporal warning |
| `--color-danger` | `#B91C1C` | Error, repeal (bãi bỏ), a right blocked, an invalid citation |
| `--color-danger-bg` | `#FEF2F2` | A serious warning region |

**Additional tokens (proposed; they must pass a contrast test; if they do not, adjust the token):**

| Token | Suggested value | Used for |
|---|---|---|
| `--color-success-bg` | `#ECFDF5` | Background of the label "Đã xác định căn cứ" (Evidence identified) |
| `--color-highlight-fill` | `rgba(37, 99, 235, 0.22)` | Paint the cited span on the PDF (only the exact span region, `mix-blend-mode: multiply`) |
| `--color-highlight-stroke` | `#2563EB` | A 2px border around the span currently selected |
| `--color-dirty-bg` / `--color-dirty-border` | `#FFF7ED` / `#C2410C` | A chip that was edited, the bar "Đã chỉnh sửa dữ kiện" (Facts were edited) (neutral/light orange) |
| `--color-overlay` | `rgba(15, 23, 42, 0.45)` | Modal backdrop |
| `--color-focus-ring` | `var(--color-action)` | A 3px focus ring, offset 2px |

**Rules for using color**

1. Top bar/Sidebar are Navy; the reading region and the Evidence Card have a white background; the whole page is a very light gray. Blue is only for interaction (citation link, the button "Tra cứu" (Search), focus). **Do not** use blue to assert that evidence is legally correct.
2. Dirty state uses neutral/light orange; a `stale` result has a text label; the skeleton is neutral, and **success green is not used before the claim has been checked**.
3. The PDF background is white or follows the original render; do not paint color over PDF content; highlight only the span that was quoted.
4. All color goes through CSS variables in **one theme module**; hardcoding HEX in a component is forbidden (lint rule). Every color/state pair has an automatic contrast test (WCAG 2.2 AA: 4.5:1 for ordinary text, 3:1 for large text and interface components).

**D.2.2 Type**

Preferred font family `Inter, system-ui, Arial, sans-serif`; a fallback compatible with Vietnamese diacritics. Local Mode does not download external fonts: bundle Inter locally only after a license check; otherwise use the system font.

| Role | Size / line-height | Weight | Note |
|---|---|---|---|
| Page title (h1) | 24 / 32 | 600 | One per screen |
| Area title (h2) | 20 / 28 | 600 | |
| Card title (h3) | 18 / 28 | 600 | |
| Interface content | 14 / 20 | 400, labels 500 | Buttons, tables, chips |
| Reading content | 15 / 24 | 400 | Answers, explanations |
| Verbatim quotations and long administrative-document text | 16 / 26 | 400 | Minimum line-height 1.5; a line is not more than about 80 characters when the layout allows |
| Meaningful metadata | 13 / 18 | 400, `--color-text-secondary` | Symbol number, date, breadcrumb; not below 13px |

**D.2.3 Spacing, corner radius, elevation, layers**

- Spacing in 4px steps: 4, 8, 12, 16, 24, 32, 48. Padding inside a card is 16; between blocks inside an answer, 12–16; between regions, 24.
- Corner radius: 6px (input, button), 8px (evidence card, table), 12px (Chat Agent panel, drawer, modal), fully round (chip, launcher, badge). Do not use one radius for everything.
- Elevation: cards use a 1px border `--color-border`, with no drop shadow; only a floating panel (`0 8px 24px rgba(15,23,42,0.16)`) and a modal (`0 16px 40px rgba(15,23,42,0.24)`) have a shadow.
- Layers (z-index): content 0 · sticky header 10 · viewer drawer 30 · launcher and Chat Agent panel 40 · confirmation modal 50 · toast 60. The confirmation modal is always above the Chat Agent.

**D.2.4 Icons and motion**

- An icon set bundled locally (proposed `lucide`, ISC license; record it in the manifest). Do not use icons from a CDN.
- Motion only responds to an action: open/close the panel (160–200ms, slide + a light fade), open an accordion, confirm. There is no self-running animation other than the skeleton and the "đang xử lý" (processing) indicator. Respect `prefers-reduced-motion` (turn off the slide, and use instant show/hide).

### D.3 Information architecture and navigation

| Area | Role | Navigation items |
|---|---|---|
| User Portal | USER, or the right `rag.query` granted explicitly + a document scope | Trang chủ Orb (Orb home) · Hỏi đáp/workspace (Question answering/workspace) · Lịch sử của tôi (My history) · Bộ nhớ của tôi (My memory) · Theo dõi (Follow) (P1) |
| Document corpus | CURATOR, REVIEWER | Tài liệu (Documents) · Hàng đợi duyệt (Approval queue) · Quan hệ sửa đổi (Amendment relationships) · Đề xuất của AI (AI suggestions) |
| Administration | SYS_ADMIN | Danh mục (Categories) · Người dùng và quyền (Users and rights) · Domain cho phép (Allowed domains) · Mô hình AI và chế độ (AI models and mode) · Cấu hình bộ nhớ (Memory configuration) |
| Quality | CURATOR, REVIEWER, SYS_ADMIN | Bộ kiểm thử (Test set) (Gold [Not implemented — see ADR-010], trap set) · Chạy benchmark (Run benchmark) · Dashboard |
| Audit | AUDITOR | Nhật ký (Log) · Bằng chứng truy cập (Access evidence) |

- **The Chat Agent (launcher at the right corner) appears on every Tra cứu (Search) page and in the Document corpus (read mode)**; it is hidden on sign-in and collapsed in the Curator Split-View.
- A navigation item the user has no right to **is not displayed** (filtered from the server, not merely hidden in the interface).
- The Search region has only a top bar (Navy). The administration region and the document corpus add a left bar (Navy, collapsible).

Standard routes: `/login` is shared; `/app/*` is the User Portal; `/admin/*` is the Admin Portal with its own layout/state/navigation; `/` routes by rights, or by the portal choice of an account with several rights. SYS_ADMIN is not admitted to Search by default. Switching portals does not raise rights and does not move private conversation content onto an administration screen. The desktop opens the User Portal inside the shell; an administration route opens only when the right exists and the action is explicit.

### D.4 Shared layout and responsive sizing

| Breakpoint | Layout |
|---|---|
| ≥ 1280px | Question answering: two regions — a left column "Hỏi và căn cứ" (Question and evidence) (about 5/12) and the PDF Viewer (about 7/12); the split can be dragged. Split-View: two equal halves |
| 768–1279px | A single column for question/evidence; the PDF Viewer opens as a right drawer about 70% of the screen width |
| < 768px | A single column; the PDF Viewer and the Chat Agent open full screen with a back button; primary actions sit in an easy-to-tap region (≥ 44×44px) |

The panel + viewer sit side by side only if the available region is at least `panel_width + viewer_min_width + gap + safe_areas`; `viewer_min_width=480px` and a gap of 16px are the initial configuration tokens. Do not apply “viewer 60% + panel 380px” unconditionally on a tablet. If space is short: the viewer replaces the panel's content region, or opens full-frame with “Quay lại hội thoại” (Back to the conversation); keep the session/scroll, and do not stack two interactive regions. The actual width and zoom decide the layout switch, not the breakpoint name alone.

The top bar of the Question-answering page: logo/system name · **Danh mục ▼** (Category ▼) · **Loại tài liệu ▼** (Document type ▼) · **Ngày áp dụng** (Application date) (default "Hôm nay" (Today) with the specific date) · a read-only mode badge (**API Mode** or **Local Mode · offline**) · the user menu. When `as_of_date` is not today, the date field switches to an emphasized style (a light orange border + the label "Tra cứu theo ngày quá khứ" (Search by a past date)).

### D.5 Detailed screens

#### S1. Question answering (full page)

Purpose: ask, see evidence first, read the analysis, open the source.

```text
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ Evidence RAG  [Danh mục ▼] [Loại tài liệu ▼] [Ngày áp dụng: 21/10/2026 ▼] [Local Mode]  │ Navy
├───────────────────────────────────────────────┬─────────────────────────────────────────┤
│ [Trả lời] [Phân tích] [Liên quan]              │ PDF VIEWER (S2)                          │
│                                               │ Số hiệu · Cơ quan · Version · Hash       │
│ Phạm vi: Danh mục X · Ngày áp dụng 21/10/2026 │ Chương > Điều 5 > Khoản 2                │
│ · Kho dữ liệu cập nhật 20/10/2026             │ ┌──────────────────────────────────────┐ │
│                                               │ │ ⚠ Khoản này đã được sửa đổi bởi …    │ │ sticky
│ ┌ Mô tả tình huống hoặc hỏi về Điều, Khoản… ┐ │ │   từ ngày … — Xem văn bản sửa đổi    │ │
│ └───────────────────────────────  [Tra cứu] ┘ │ └──────────────────────────────────────┘ │
│                                               │   …nội dung PDF…                         │
│ Dữ kiện: [Đối tượng ✎] [Thời điểm ✎]          │   [ĐOẠN ĐƯỢC TÔ SÁNG]                   │
│          [Hồ sơ ✎ chưa xác nhận]              │                                          │
│ ▸ Đã chỉnh sửa dữ kiện — kết quả bên dưới dựa │ ‹ Trang 12/48 ›  Tìm trong văn bản       │
│   trên dữ kiện trước đó [Cập nhật dữ kiện &   │ Bản hiện hành │ Bản tại ngày …           │
│   Tra cứu lại]                                │ Liên kết trang công bố chính thức        │
│                                               │                                          │
│ ● Có điều kiện — cần xác minh thêm hiệu lực   │                                          │
│ CĂN CỨ  [Quy định chính][Điều kiện][Ngoại lệ] │                                          │
│  [1] Điều 5 khoản 2 · số hiệu … · bản 3        │                                          │
│      “…nguyên văn 2–3 dòng…”  [Mở trong PDF]  │                                          │
│  [2] …                                        │                                          │
│ PHÂN TÍCH CÓ DẪN CHỨNG                         │                                          │
│  • Nhận định … [1][2]                          │                                          │
│ THÔNG TIN CÒN THIẾU  [Ngày xảy ra sự việc] …   │                                          │
│ ĐÃ KIỂM TRA  ✔ Nguồn  ✔ Trích dẫn  ⚠ Hiệu lực │                                          │
│ CÂU HỎI TIẾP THEO  (chip) (chip)               │                                          │
│ Sao chép kèm phạm vi · Phản hồi                │                                          │
│ Kết quả hỗ trợ tra cứu và tham mưu, không …    │                                          │
└───────────────────────────────────────────────┴─────────────────────────────────────────┘
```

Block order in the **Trả lời** (Answer) tab: scope → question box → facts → the "đã chỉnh sửa" (edited) bar (if any) → status label → evidence grouped by role → analysis with citations → information still missing → coverage checklist → next questions → actions and the notice.

The **Phân tích** (Analysis) tab (A1, A3, A4, A5): a table "Điều kiện áp dụng" (Conditions of application) (already satisfied / not yet verified / exception / time milestone / consequence stated in the administrative document, each row has `[n]`), a list of points to note, a version comparison of the Article (Điều) currently being viewed. The **Liên quan** (Related) tab (A6, A10): guiding administrative documents, amending administrative documents, references to/from the node currently being viewed, the amendment chain.

States:

| State | Display |
|---|---|
| Empty | The question box and 3 example ways to ask (chips): "Hỏi theo Điều/Khoản" (Ask by Article/Clause (Khoản)), "Mô tả một tình huống" (Describe a situation), "So sánh với quy định cũ" (Compare with the old provision). No fake data |
| No category selected | The question box is locked; a note "Chọn danh mục để bắt đầu" (Select a category to begin); the category chips are emphasized |
| Phase 1 running | A neutral skeleton (`--color-surface-muted`) + "Đang tìm căn cứ trong danh mục đã chọn…" (Searching for evidence in the selected category…) |
| Phase 1 done | Evidence cards appear; the line "Đã tìm thấy và kiểm tra nguồn của X căn cứ. Đang phân tích điều kiện áp dụng, hiệu lực, quy định chuyển tiếp và ngoại lệ…" (Found and checked the source of X pieces of evidence. Analyzing conditions of application, effectivity, transitional provisions, and exceptions…) |
| Phase 2 done | Claims, the status label, the full checklist |
| Insufficient evidence | The label "Thiếu căn cứ" (Insufficient evidence) + an explanation + a suggestion to ask again + (if any) the nearest evidence already checked, stating clearly "chưa trả lời được câu hỏi" (the question cannot be answered yet) |
| False premise (L0) | "Không có [Điều X] trong [văn bản]. Văn bản này có Điều 1 đến Điều N." (There is no [Article X] in [the administrative document]. This administrative document has Article 1 through Article N.) |
| Explanation generation failed | Keep the valid evidence + "Giải thích tạm thời không khả dụng. Các căn cứ bên dưới đã được kiểm tra nguồn." (Explanation is temporarily unavailable. The evidence below has had its source checked.) |
| Effectivity snapshot stale | A warning bar: "Dữ liệu hiệu lực đang được cập nhật. Chưa thể khẳng định hiệu lực tại ngày này." (Effectivity data is being updated. Effectivity on this date cannot be asserted yet.) |
| Old result (`stale`) | The label "Kết quả dựa trên dữ kiện trước đó" (Result based on the previous facts) until there is a new result |
| Network/server error | A message stating what failed and a button "Thử lại" (Try again); do not clear what was entered |

#### S2. PDF Viewer

```text
┌────────────────────────────────────────────────────────────────────────────┐
│ ‹ Quay lại   Tên văn bản · Số hiệu · Cơ quan · Bản 3 ▼ · Hash 9f3a…   ⤓ ↗  │ toolbar
│ [Đang áp dụng ✔ tại 21/10/2026]  (nhãn hiệu lực của node đang xem)         │
├────────────────────────────────────────────────────────────────────────────┤
│ ⚠ Khoản này trên PDF gốc đã được sửa đổi bởi [văn bản] từ ngày [ngày]      │ sticky
│   [Xem văn bản sửa đổi] [Xem nội dung áp dụng tại ngày tra cứu]  ▾ thu gọn │
├────────────────┬───────────────────────────────────────────────────────────┤
│ MỤC LỤC        │                                                           │
│ ▸ Chương I     │   …trang PDF gốc…                                         │
│ ▾ Chương II    │   ┌─ Điều 5 ─ …                                          │
│   ▾ Điều 5     │   │ 2. [đoạn được tô sáng] ◂ huy hiệu "Đã sửa đổi"         │
│     Khoản 1    │   └────────────────────────────────────────────────────── │
│   ● Khoản 2    │                                                           │
├────────────────┴───────────────────────────────────────────────────────────┤
│ ‹ Trang 12 / 48 ›   Tìm trong văn bản [          ]   Bản hiện hành │ Bản tại ngày … │
└────────────────────────────────────────────────────────────────────────────┘
```

- The toolbar always shows the effectivity label of the node currently being viewed (collapsing the banner does not remove this label).
- The table of contents is built from the database (`document_nodes`); a click jumps to the PDF; the node currently being viewed has a ● mark and `aria-current`.
- Highlight: background `--color-highlight-fill`, border `--color-highlight-stroke`; only the span region that was quoted. Scroll automatically to the span.
- **Fallback when the bbox is not trustworthy:** open the correct page, show a pane "Đoạn trích để đối chiếu" (Passage for comparison) beside it, with the line "Chưa tô sáng chính xác vị trí đoạn này trên trang." (The position of this passage on the page has not been highlighted precisely.)
- The copy as of a date: select a version; the old PDF is still viewed intact, with the banner.
- The PDF download button appears only when the right exists. The link "Trang công bố chính thức" (Official publication page) appears only when the curator has verified it.
- Phone: full screen; the table of contents becomes a drawer; the toolbar collapses to a title + a menu.

#### S3. Chat Agent (widget at the right corner)

**Launcher.** A round button, 56px, background `--color-brand-navy`, a white conversation icon; 24px from the right edge and the bottom edge (16px on a phone) plus the safe area; hover `--color-brand-navy-hover`; focus: a 3px ring `--color-focus-ring`, 2px away. Tooltip "Hỏi về văn bản" (Ask about an administrative document). `aria-label="Mở trợ lý tra cứu"` (Open the lookup assistant). A round 12px badge with a white border: action blue = there is a new response; orange (`--color-warning`) = there is a result that needs rechecking. It does not turn itself on, and it does not open itself.

**Panel (web/desktop frame).** Desired width 420px (≥1280) or 380px (768–1279), always clamped inside the work area/safe area; maximum height `min(720px, 100vh − 96px)`, corner radius 12px. The Orb remains the toggle control with a label that matches the state; clicking again collapses the panel. The native shell follows S14, and does not create an extra square or a background window around the Orb.

```text
                                   ┌──────────────────────────────────────┐
                                   │ Trợ lý tra cứu        ⤢  ▁  ✕        │ Navy
                                   ├──────────────────────────────────────┤
                                   │ [Danh mục X ▼] [21/10/2026 ▼] [Local]│ thanh phạm vi
                                   │ Đang hiểu là: “…câu đã viết lại…” ✎  │ (khi hỏi nối tiếp)
                                   │ [Trả lời] [Phân tích] [Liên quan]    │
                                   ├──────────────────────────────────────┤
                                   │                    ┌───────────────┐ │
                                   │                    │ câu hỏi của tôi│ │
                                   │                    └───────────────┘ │
                                   │ ● Có điều kiện                       │
                                   │ ┌ [1] Điều 5 khoản 2 · số hiệu … ──┐ │
                                   │ │ “…nguyên văn…”      [Mở trong PDF]│ │
                                   │ └───────────────────────────────────┘ │
                                   │ Nhận định có dẫn chứng … [1]         │
                                   │ Còn thiếu: (Ngày xảy ra sự việc)     │
                                   │ Hỏi tiếp: (…) (…)                    │
                                   │ Sao chép kèm phạm vi · Phản hồi      │
                                   ├──────────────────────────────────────┤
                                   │ ┌ Mô tả tình huống hoặc hỏi Điều… ┐  │
                                   │ └────────────────────── [Tra cứu] ┘  │
                                   │ Hỗ trợ tra cứu, không thay quyết định │
                                   └──────────────────────────────────────┘
                                                                     (◉) launcher
```

Buttons in the header: **⤢ Mở trang đầy đủ** (Open the full page) (keeps the session) · **▁ Thu nhỏ** (Minimize) (back to the launcher, keeps state) · **✕ Đóng** (Close).

**Behavior**

- Open from the launcher or from a configurable shortcut (by default no global shortcut is assigned, to avoid conflicts; the owner may turn one on). `Esc` closes the panel when focus is inside it; focus returns to the launcher.
- Session state is kept on the server; moving between pages inside the application does not lose the conversation.
- Press `[n]` or "Mở trong PDF" (Open in PDF): if there is enough room under D.4, the viewer sits beside the panel; if room is short on a tablet/narrow window, switch to a single frame with “Quay lại hội thoại” (Back to the conversation). Do not cover the citation/composer with another panel; on native, prefer the workspace in the same session when a wide PDF needs to be read.
- The user's message: aligned right, background `--color-surface-muted`. The assistant's answer: a white block with a border, **not a chat bubble**; the blocks inside follow the same order as S1, but the evidence card is compact (symbol number, Article/Clause/Point (Điểm), 2 lines of quotation, an open button).
- A follow-up question: show the bar "Đang hiểu là: …" (Understood as: …) (with an edit button); if a decisive condition is missing, ask again with **one** question using choice chips.
- An old result after the snapshot changes: the label "Cần kiểm lại" (Needs rechecking) with a button "Tra cứu lại với dữ liệu mới" (Search again with the new data); the launcher has an orange badge.
- There is no button that approves or executes business work.
- The not-stored mode: a lock icon in the header and the line "Hội thoại này sẽ không được ghi nhớ." (This conversation will not be remembered.)
- There is a “Dừng” (Stop) button while a run is in progress; stopping affects only the question-answering turn, not an administration task. “Thử lại” (Try again) after an error is a deliberate new run; show the old result as the previous turn and do not duplicate the question.

**Phone:** a full-screen panel (a bottom sheet at 100% height), a sticky header, a composer stuck to the bottom following `visualViewport` so the keyboard does not cover it.

**Special states**

| State | Display |
|---|---|
| First time | A short greeting + 3 example chips for how to ask; no long introduction |
| No category selected | The scope bar is emphasized, and the composer is locked with a reason |
| Connection lost | "Mất kết nối tới máy chủ. Nội dung bạn nhập vẫn được giữ." (Connection to the server was lost. What you entered is still kept.) + Thử lại (Try again) |
| Local Mode, local model failed | Evidence already checked is still shown; "Giải thích tạm thời không khả dụng" (Explanation is temporarily unavailable); **does not** switch to the API |
| No right | "Chưa tìm thấy tài liệu được phép truy cập." (No document you are allowed to access was found.) (does not reveal that a document exists) |

#### S4. Document list and document record (CURATOR/REVIEWER)

```text
┌ Tài liệu ──────────────────────────────────────────────────────────────────┐
│ [Tìm theo số hiệu, tiêu đề]  [Danh mục ▼] [Loại ▼] [Trạng thái ▼]          │
│                                   [Tải PDF lên]  [Nhập từ URL]              │
├────────────────────────────────────────────────────────────────────────────┤
│ Tiêu đề / số hiệu │ Loại │ Cơ quan │ Danh mục │ Phiên bản │ Trạng thái │ ⋯ │
│ …                                                                          │
└────────────────────────────────────────────────────────────────────────────┘
```

- The **Trạng thái tài liệu** (Document status) column: Nháp (Draft) · Chờ duyệt (Waiting for approval) · Đã duyệt (Approved) · Tạm đình chỉ (Suspended) · Đã thay thế (Replaced (thay thế)) · Hết hiệu lực (No longer in effect) · Chưa rõ (Unknown) (icon + text). The **Hiệu lực node** (Node effectivity) column summarizes: "Có N node chưa xác minh" (There are N nodes not yet verified).
- **Tải PDF lên** (Upload PDF): supports selecting many PDFs at once (`multiple`); allows declaring independent metadata for each administrative document (title, symbol number, official source URL, issue date); sends files one by one to `POST /api/v1/admin/documents/upload` so the PDF processor is not overloaded; shows progress `Đang nhập tệp n/tổng…` (Importing file n/total…), a separate status for each file (`ready`, `uploading`, `success`, `failed`, `unknown`), a button "Dừng nhập tệp" (Stop importing files) (`AbortController`), and a button "Thử lại các tệp chưa thành công" (Try again the files that did not succeed); a two-tier duplicate check (block a duplicate SHA-256 byte hash with code 409 `DUPLICATE_PDF_HASH`, warn on duplicate NFC text content `possible_duplicate_content` with a list of at most 5 draft/source copies for comparison).
- **Nhập từ URL** (Import from URL): an input box; if the domain is not on the list: "Tên miền này chưa nằm trong danh sách cho phép. Nhờ quản trị viên thêm tên miền sau khi xác minh." (This domain is not yet on the allowlist. Ask an administrator to add the domain after verification.) There is no skip button.
- The document-record page has tabs: **Thông tin** (Information) (standard metadata, source, hash, a button "Mở trang công bố chính thức" (Open the official publication page) if verified) · **Phiên bản** (Versions) · **Cây điều khoản** (Article tree) · **Quan hệ** (Relationships) (amendments/references) · **Lịch sử** (History) (audit).
- The list shows only documents the user has a right to (filtered on the server).

#### S5. Approval queue (risk-prioritized)

Table: **Tài liệu và phiên bản (Document and version) · Lý do vào hàng đợi (Reason for entering the queue) · Rủi ro (Risk) · Người phụ trách (Assignee) · Hạn (Due) · Trạng thái (Status)**.

- Reasons: Độ tin cậy parse thấp (Low parse confidence) · Nhảy khoản (Skipped clause) · Chuyển mã font (Font transcoding) · Tọa độ trang lệch (Page coordinates shifted) · Hiệu lực chưa duyệt (Effectivity not yet approved) · Đề xuất của AI (AI suggestion).
- Risk: **Cao (High) / Trung bình (Medium) / Thấp (Low)** shown by icon + text (not color alone), with High sorted first by default.
- Filters by reason, risk, and assignee. Bulk action is allowed only for **assigning an assignee**; approval is always per item.
- Empty row state: "Không có mục chờ duyệt. Tài liệu mới nạp sẽ xuất hiện ở đây." (There is nothing waiting for approval. Newly ingested documents will appear here.)

#### S6. Curator Split-View

```text
┌ Tài liệu X · bản 3 · Mục 4/17 trong hàng đợi │ Đã lưu nháp 14:32 │ Revision 8 ─────────┐
├───────────────────────────────────────┬───────────────────────────────────────────────┤
│ PDF.js — bản bất biến                 │ [Cây node] [Hiệu lực] [Quan hệ] [Đề xuất của AI]│
│ [Trang 12 ▼]  tô sáng span đang chọn  │ ▾ Chương II                                   │
│                                       │   ▾ Điều 5                                     │
│   …trang PDF…                         │     ● Khoản 2  (độ tin cậy parse: thấp)        │
│   [span]                              │ ─ Form node ──────────────────────────────────│
│                                       │ Nhãn [Khoản 2]  Vị trí [5.2]                   │
│                                       │ Hiệu lực từ [..] đến [..]  Trạng thái [Chưa rõ]│
│                                       │ Quan hệ sửa đổi [+ Thêm]                       │
│                                       │              [Bỏ qua]  [Lưu nháp]  [Duyệt]     │
└───────────────────────────────────────┴───────────────────────────────────────────────┘
```

- Click a node → the PDF jumps to the span; click in the PDF → focus the corresponding node; a provision that has no node yet → open the task "Phân tích lại trang" (Analyze the page again).
- **Automatic draft save** (the indicator "Đã lưu nháp" (Draft saved)) is different from **Duyệt** (Approve): Approve uses a separate endpoint, the REVIEWER role, and checks `If-Match`/revision; on a revision conflict, show "Mục này vừa được người khác sửa. Tải lại để xem thay đổi." (Someone else just edited this item. Reload to see the change.)
- Shortcuts (next/previous node) are **disabled while text is being entered**; there is no approve shortcut.
- Approving a change to effectivity or to an amendment relationship: a confirmation dialog: "Thay đổi này ảnh hưởng cách hệ thống trả lời với các ngày từ [ngày]. Hành động được ghi nhật ký." (This change affects how the system answers for dates from [date]. The action is written to the log.) — buttons "Duyệt" (Approve) / "Quay lại" (Go back).
- The **Đề xuất của AI** (AI suggestions) tab (C1): each suggestion has a type, a source span, confidence as a label, and buttons **Chấp nhận vào nháp (Accept into the draft) / Sửa (Edit) / Từ chối (Reject)**. A CURATOR's Accept only saves a draft and an audit; approval of the document/effectivity/amendment goes through the REVIEWER and a separate endpoint, and does not publish silently. A bulk action needs confirmation.
- The Chat Agent is collapsed on this screen (it does not cover the form).

#### S7. Categories (SYS_ADMIN/CURATOR)

A drag-and-drop category tree, at a configured depth; columns: Tên (Name) · Mã cố định (Fixed code) · Người phụ trách (Assignee) · Quyền xem (View right) · Số tài liệu (Document count) · Trạng thái (Status) (Hoạt động (Active)/Ẩn (Hidden)/Đã xóa (Deleted)). Actions: Thêm (Add) · Sửa (Edit) · Ẩn (Hide) · Xóa mềm (Soft delete) · Khôi phục (Restore) · Nhập/Xuất JSON/CSV (Import/Export JSON/CSV) (with a check step before applying). A soft delete states clearly: "Tệp gốc và embedding vẫn được giữ nếu tài liệu còn thuộc danh mục khác." (The original file and the embedding are still kept if the document still belongs to another category.) Creating a cycle is forbidden: report the error right in the parent-category field.

#### S8. Allowed domains (SYS_ADMIN)

Table: **Tên miền (Domain) · Người xác minh (Person who verified) · Ngày xác minh (Verification date) · Ghi chú (Note) · Trạng thái (Bật/Tắt) (Status (On/Off)) · Lần dùng gần nhất (Most recent use)**. The button **Thêm tên miền** (Add a domain) opens a 3-step wizard: (1) enter the domain → the system checks DNS, HTTPS, and that it is not an internal address; (2) confirm the person who verified and the source note; (3) turn it on. Every change has an audit. Turning a domain off: the warning "Các lần nhập mới từ tên miền này sẽ bị chặn." (New imports from this domain will be blocked.)

#### S9. AI models and operating mode (SYS_ADMIN)

- **Mode:** two cards, **API Mode** and **Local Mode**, showing the current status and the conditions required (for Local Mode: the `verify-egress` result, the local model ready). Changing mode needs confirmation and an audit record.
- **Model Registry:** a table Provider · Endpoint · Model · Capability (chips: Phân tích/Chat (Analysis/Chat) · Embedding · Rerank · Sinh (Generation) · OCR) · Vùng riêng tư (Privacy zone) · Trạng thái (Status) · Chi phí/định mức (Cost/quota) · [Kiểm tra kết nối] (Check connection). The API key is entered only once, shown masked, and cannot be read back.
- **Stage routes:** a matrix of Stage × (API Mode, Local Mode) selecting a model; fallback only within the same privacy zone; a warning if a Local Mode stage points at a model that does not run locally.
- The API configuration form includes the supported adapter/provider, endpoint, model ID, parameters, and a secret entered once; the Local form includes the approved internal runtime/endpoint, artifact/model ID, revision, and parameters. There are states “Chưa cấu hình” (Not yet configured), “Chưa kiểm tra” (Not yet checked), “Sẵn sàng” (Ready), “Lỗi” (Error); do not prefill a mandatory model/key/host. A connection check uses aggregate data only and still follows the egress policy.
- A local runtime/model is selected by manifest ID or by a relative path inside the install root that has been checked; the server resolves it and checks containment under B.8. An API/LAN endpoint remains an endpoint configuration with a policy; do not let the form become a way to read or run an arbitrary file outside the root.
- **Policy by category:** the switch "Cho phép xử lý bằng AI từ xa" (Allow processing by remote AI) defaults to **Tắt** (Off); turning it on needs confirmation, with a warning about data sent outside.
- The model's chain-of-thought is not displayed anywhere.

#### S10. My memory (USER)

Blocks: **Chế độ không lưu** (Not-stored mode) (a switch) · **Hội thoại gần đây** (Recent conversations) (a list; view the summary, delete each session) · **Sở thích** (Preferences) (opt-in: default category, frequently used scope) · **Thời hạn lưu** (Retention period) (read-only, set by administration) · **Xóa tất cả bộ nhớ** (Delete all memory). A short explanation: "Bộ nhớ giúp trợ lý hiểu câu hỏi nối tiếp. Câu trả lời luôn lấy căn cứ lại từ kho tài liệu." (Memory helps the assistant understand a follow-up question. The answer always fetches evidence again from the document corpus.) Delete-all needs confirmation and is a real delete.

#### S11. Test set: approving Gold [Not implemented — see ADR-010] and the trap set (REVIEWER/business specialist)

```text
┌ Bộ kiểm thử · Gold v0 · Đã duyệt 62 / 180 · Calibration 54 │ Held-out 126 (khóa) ───┐
├──────────────────────┬──────────────────────────────────────────────────────────────┤
│ Danh sách case       │ Case G-0073                                                   │
│ [lọc: Chưa duyệt ▼]  │ Câu hỏi: …                          Ngày áp dụng: …           │
│ G-0071 ✔ Đã duyệt    │ Căn cứ do agent đề xuất: số hiệu · Điều/Khoản/Điểm · bản       │
│ G-0072 • Chưa duyệt  │ “…đoạn trích…”  [Mở trong PDF]                                 │
│ G-0073 • Chưa duyệt  │ Đáp án mẫu (agent soạn): …                                    │
│ …                    │ Loại: [Trực tiếp ▼]  Có cần trả lời "không đủ căn cứ"? [ ]    │
│                      │ [Duyệt]  [Yêu cầu sửa + ghi chú]  [Loại bỏ case]              │
└──────────────────────┴──────────────────────────────────────────────────────────────┘
```

- Each case has a status **Nháp (Draft) → Đã duyệt (Approved) / Cần sửa (Needs edit) / Loại bỏ (Discarded)**, the person who approved, and the time. **Only an Approved case counts toward the standard.**
- The person approving always sees the original passage and can open the PDF; there is no "duyệt tất cả" (approve all) button.
- The held-out set is locked in both the API and the interface against the person who tunes; the case/answer does not appear in their benchmark log. Show `scenario_group_id`, `split_revision`, and the locked-candidate status; a final evaluation happens only after the configuration is frozen. A set already used to decide a fix/tune is no longer called independent held-out.
- The trap set has its own tab with the same approval method.

#### S12. Quality dashboard (SYS_ADMIN, REVIEWER)

Metric tiles and charts over time: `retrieval_ms`, `evidence_ready_ms`, `first_claim_ms`, `final_answer_ms` (P50/P95, a line over time); the rate of correct/incorrect refusal; `unsupported_claim_rate`, `wrong_doc_rate`, `wrong_node_rate`, `false_premise_detection_rate`, `validator_reject_rate`; Gold [Not implemented — see ADR-010] approval progress (approved / target 150–200); benchmark-run history with a filter by model/tokenizer/corpus hash. Every metric records **the measurement environment and the time**; do not display a number when there is no data yet (show "Chưa có số đo" (No measurement yet)).

#### S13. Sign-in, rights, and error pages

- Local sign-in; do not use an external service (captcha, font, analytics). Wrong password: "Tên đăng nhập hoặc mật khẩu không đúng." (The username or password is incorrect.) A temporary lock after many failures, stating the wait time.
- No right to enter a page: "Bạn chưa có quyền vào mục này." (You do not yet have the right to enter this section.) (do not hint at what that section contains).
- 404/500: state what happened, a reference code to report to administration, and a button back to the home page.

#### S14. USER desktop shell

Reuses S3 (chat), S1 (workspace), S2 (viewer), S10 (memory), and S13 (sign-in); do not duplicate the workflow. State sequence: `SIGNED_OUT → LOGIN → ORB ↔ PANEL ↔ WORKSPACE`; a lost session returns to LOGIN, and a lost network keeps the draft and a clear error state.

- **Login:** an opaque window background, text that is easy to read, not transparent. A successful sign-in closes/hides the login frame completely before showing the Orb; do not leave a leftover shadow or an extra interactive surface behind it.
- **Orb:** a circle of 56–64px, with the background/hit-test region matching the shape; not a circle inside a square, and no outer window frame/shadow. Open/collapse by repeated click; if drag is turned on, distinguish drag from click and do not capture events outside the Orb.
- **Panel/workspace:** an opaque background following the theme; a separate drag region does not cover the assistant's name, buttons, or text; the resize region is on its own edges/corners, with a minimum size and a work-area clamp. Do not require a transparent window for reading content.
- **Position:** take the work area, DPI, and monitor from the platform API; remember the user's position/size choice if that is allowed, and do not store conversation content in local storage. After a monitor/DPI change, bring the window back into the visible region.
- **System tray:** Hiện/Ẩn trợ lý (Show/Hide the assistant), Đăng xuất (Sign out), Thoát (Exit); equivalent controls inside the app for keyboard users. Closing the panel collapses to the Orb; Hide temporarily leaves only the tray; Exit ends the client, and does not stop the LAN server.
- **Installation:** the desktop shell/helper/runtime uses the dependency-manifest under the configured root `E:\Programs` per B.8; do not hardcode PATH/LLM in the frontend, the shell, or the helper; take the executable/model from configuration/the manifest, and do not depend on the global PATH or silently install a tool into the user profile.
- **Always-on-top on/off:** a user preference, default OFF; it does not block the sign-in window or a system modal. Do not open a console/cmd window when running the app or a background helper.
- **Shared flow:** opening the full view/PDF/collapsing again does not lose the session; the backend is the source of conversation state, and presentation state is separate from business data. Do not fake AI when the model is not yet configured; do not mix User and Admin.

### D.6 Component library

Every component uses the shared design tokens and has a story/state test.

| Component | Main states and properties | Accessibility |
|---|---|---|
| `AppShell`, `TopBar`, `SideNav` | Collapsed/open; items by right | Landmarks `banner`/`navigation`/`main`; skip link |
| `ScopeBar` (`CategorySelect`, `DocTypeSelect`, `AsOfDatePicker`, `ModeBadge`) | A past `as_of_date` is emphasized; the badge is read-only | A full label for each control |
| `QueryComposer` | Empty, typing, sending, locked (no category selected yet); Enter sends, Shift+Enter inserts a new line | `aria-describedby` for the lock reason |
| `FactChip` | `user_confirmed` (solid stroke), `extracted_unconfirmed` (dashed stroke + "chưa xác nhận" (not yet confirmed)), `inferred_uncertain` (dotted stroke + "suy đoán" (inferred)); being edited; edited (dirty) | Edit/delete buttons have labels; changes are announced through `aria-live` |
| `DirtyFactBar` | Shown when a chip is dirty; the button "Cập nhật dữ kiện & Tra cứu lại" (Update facts & search again) is enabled when valid | Role `status` |
| `ResultStatus` | 4 labels + "Chưa tìm thấy tài liệu được phép truy cập" (No document you are allowed to access was found) (D.7) | Icon + text |
| `EvidenceGroupTabs` | Tabs by role (show only tabs that have cards) | The WAI-ARIA tabs pattern |
| `EvidenceCard` | Compact (2–3 lines) / expanded; selected; the label "Nguồn ngoài danh mục" (Source outside the category); `EffectiveBadge`; `stale` | The button "Mở trong PDF" (Open in PDF) has a full name |
| `CitationLink` (`[n]`) | Hover shows a 2-line preview; opens the viewer; checks rights on open | Alternative text "Căn cứ n: [số hiệu, Điều…]" (Evidence n: [symbol number, Article…]) |
| `CoverageChecklist` | Each item: Đạt (Passed) / Chưa đạt (Not passed) / Chưa xác minh (Not yet verified); collapsed "Đã kiểm tra 3/4" (Checked 3/4) | A list with status text |
| `ClaimItem` | Has `[n]`; claim state; "chưa xác minh" (not yet verified) | The claim–evidence link uses `aria-describedby` |
| `MissingInfoChips`, `FollowUpChips` | Press to fill/ask; a configured maximum number of chips | Real buttons, not `div` elements |
| `AnalysisTable` (A1) | Rows: condition · status (already satisfied/not yet verified/exception) · evidence `[n]` | A table with column headings |
| `NoteHighlights` (A4) | Turn highlighting on/off in the card and the viewer | A switch with a label |
| `VersionDiff` (A5) | Side by side/interleaved; additions/removals annotated by a mark + text | Not color alone |
| `RelatedList` (A6) | Groups: guiding administrative document · amendment · reference to · reference from; the label "chưa duyệt" (not yet approved) | A list with levels |
| `PdfViewer`, `PdfToolbar`, `ArticleTree` | Loading, error, fallback; a collapsible table of contents | Keyboard navigation; `aria-current` |
| `AmendmentBanner` | `modified`, `repealed`, `suspended`, `not_yet_effective`, `unknown`; collapsed, but the label remains on the toolbar | Role `alert` when open; text + icon |
| `TwoPhaseSkeleton` | Phase 1, transition to Phase 2 | `aria-busy`, a phase announcement |
| `StaleLabel`, `StaleResultOverlay` | A label on the old result | `aria-live` polite |
| `FeedbackDialog` | 4 types + a note | Focus management |
| `CopyWithScope` | Copy includes scope, application date, and the warning | The announcement "Đã sao chép" (Copied) |
| `AgentLauncher`, `AgentPanel` | Closed, open, minimized, full screen; a badge | See D.9 |
| `DesktopShell`, `DesktopWindowControls`, `TrayMenu` | Login/Orb/Panel/Workspace, drag/resize, DPI, show/hide/sign-out/exit | A separate drag region; keyboard menu/buttons; native does not drop focus |
| `MemoryCenter`, `SessionMemoryDrawer` | The blocks in S10 and the RAM session-memory drawer: a list of facts/items, a count badge, Stop/Try again for the turn, delete one item, delete all RAM, the switch "Lưu vào sở thích tra cứu" (Save to search preferences) | A clear switch label; role status for updates |
| `DataTable`, `ReviewQueueTable` | Sort, filter, empty, error; pagination | Column headings `scope`; a row can be selected by keyboard |
| `CuratorSplitView`, `NodeForm` | Draft/approve, revision conflict | Shortcuts only when focus is not in an input |
| `AiSuggestionPanel` | Accept/Edit/Reject, a reason for rejection | Confidence as a text label |
| `ConfirmDialog` | Describes the specific consequence, and the button names the action exactly | Modal; returns focus |
| `JobProgress` | Waiting, running, needs approval, error, cancelled, done | A progress bar with text |
| `AllowlistTable`, `DomainWizard` | 3 steps, a check | |
| `ModelRegistryTable`, `ModeCard` | The AI Provider/Model configuration table: adapter, endpoint (supports LAN/localhost), model ID, params (temperature, max_tokens, json_mode), secret_ref (denylist filter), in-place update | Mask the key; warn on a wrong route; connection check (probe) |
| `MetricTile`, `LatencyChart` | Has data / "Chưa có số đo" (No measurement yet) | A chart accompanied by an alternative data table |
| `GoldReviewList`, `GoldCaseView` | Draft/Approved/Needs edit/Discarded; held-out locked | |
| `EmptyState`, `ErrorState`, `Toast` | States the next action | `role="status"` / `alert` |

### D.7 Standard labels and states

**Question-answering results**

| Label | Icon | Color | When |
|---|---|---|---|
| Đã xác định căn cứ (Evidence identified) | check-circle | `--color-success` on `--color-success-bg` | Source, effectivity, and conditions of application have been checked by rule and coverage is sufficient |
| Có điều kiện (Conditional) | alert-triangle | `--color-warning` on `--color-warning-bg` | A condition, an exception, or effectivity is not yet verified |
| Thiếu căn cứ (Insufficient evidence) | file-search | `--color-text-secondary` on `--color-surface-muted` | There is not enough evidence to answer |
| Nguồn xung đột (Conflicting sources) | alert-octagon | `--color-danger` on `--color-danger-bg` | The sources say different things, and a person with authority needs to verify |
| Chưa tìm thấy tài liệu được phép truy cập (No document you are allowed to access was found) | lock or search | neutral | There is no document within the caller's rights; existence is not revealed |

**Node effectivity by application date**

| `amendment_state` | Vietnamese label | Icon | Color |
|---|---|---|---|
| `active` | Đang áp dụng tại [ngày] (In effect on [date]) | check-circle | success |
| `modified` | Đã sửa đổi từ [ngày] (Amended from [date]) | file-pen | warning |
| `repealed` | Đã bãi bỏ từ [ngày] (Repealed from [date]) | ban | danger |
| `suspended` | Tạm đình chỉ (Suspended) | pause-circle | warning |
| `not_yet_effective` | Chưa có hiệu lực (Not yet in effect) | clock | evidence (light blue) |
| `unknown` | Hiệu lực chưa xác minh (Effectivity not yet verified) | help-circle | neutral |

When `as_of_date` is before the amendment date, use the sentence: "Quy định được thay đổi từ [ngày] (sau ngày tra cứu). Cần xem quy định chuyển tiếp." (The provision is changed from [date] (after the query date). The transitional provision needs to be reviewed.) Do not say the old copy certainly does not apply.

**Coverage-checklist items**

| Item | Display label |
|---|---|
| `source_verified` | Nguồn và trích dẫn đã kiểm tra (Source and quotation checked) |
| `effective_checked` | Hiệu lực tại ngày áp dụng (Effectivity on the application date) |
| `applicability_checked` | Điều kiện áp dụng (Conditions of application) |
| `claim_supported` | Nhận định có căn cứ hỗ trợ (The finding has supporting evidence) |
| `transition_checked` | Quy định chuyển tiếp (Transitional provision) |
| `required_facts_complete` | Dữ kiện bắt buộc (Required facts) |
| `scope_expansion` | Mở rộng ngoài phạm vi đúng chính sách (Expansion outside scope under the correct policy) |

Each item has 3 states: **Đạt** (Passed) (check) · **Chưa đạt** (Not passed) (x) · **Chưa xác minh** (Not yet verified) (help). The default display is collapsed as "Đã kiểm tra X/Y mục" (Checked X/Y items), and it can be expanded.

The current API uses the checklist names in the table above and the enum `passed / failed / unknown`; do not use a boolean to force “not yet verified” into false. `effective_status_checked`/`node_effective_checked` are old names, and they are not emitted by API v1.3. `claim_supported=passed` requires the defined support checks to be sufficient; passing numbers/negation alone is not treated as proof of the finding's meaning.

**Ingest jobs:** Chờ (Waiting) · Đang đọc trang (Reading pages) · Phân tích cấu trúc (Analyzing structure) · Cần duyệt (Needs approval) · Lỗi (Error) · Đã hủy (Cancelled) · Xong (Done). **AI suggestions:** Đề xuất (Suggested) · Đã chấp nhận (Accepted) · Đã từ chối (Rejected) · Hết hạn (Expired). **Gold [Not implemented — see ADR-010] case:** Nháp (Draft) · Đã duyệt (Approved) · Cần sửa (Needs edit) · Loại bỏ (Discarded).

### D.8 Interface copy (microcopy)

Principles: plain Vietnamese, active voice, stating exactly what will happen; an error states **what happened and how to handle it**, and does not offer a generic apology; an empty state leads to the next action.

| Context | Copy |
|---|---|
| Question-box placeholder | "Mô tả tình huống hoặc hỏi về một Điều, Khoản…" (Describe a situation or ask about an Article, a Clause…) |
| Send button | "Tra cứu" (Search) |
| Button after editing facts | "Cập nhật dữ kiện & Tra cứu lại" (Update facts & search again) |
| Dirty bar | "Đã chỉnh sửa dữ kiện — kết quả bên dưới dựa trên dữ kiện trước đó" (Facts were edited — the result below is based on the previous facts) |
| Phase-1 skeleton | "Đang tìm căn cứ trong danh mục đã chọn…" (Searching for evidence in the selected category…) |
| Phase 2 | "Đã tìm thấy và kiểm tra nguồn của [X] căn cứ. Đang phân tích điều kiện áp dụng, hiệu lực, quy định chuyển tiếp và ngoại lệ…" (Found and checked the source of [X] pieces of evidence. Analyzing conditions of application, effectivity, transitional provisions, and exceptions…) |
| The sentence as understood | "Đang hiểu là: “…”" (Understood as: “…”) + the button "Sửa" (Edit) |
| Insufficient evidence | "Chưa đủ căn cứ để trả lời. Các tài liệu được phép truy cập chưa có quy định phù hợp với câu hỏi này." (There is not enough evidence to answer. The documents you are allowed to access do not yet contain a provision that fits this question.) |
| Not found / no right | "Chưa tìm thấy tài liệu được phép truy cập." (No document you are allowed to access was found.) |
| False premise | "Không có [Điều X] trong [tên văn bản]. Văn bản này có Điều 1 đến Điều [N]." (There is no [Article X] in [administrative-document name]. This administrative document has Article 1 through Article [N].) |
| Explanation failed | "Giải thích tạm thời không khả dụng. Các căn cứ bên dưới đã được kiểm tra nguồn." (Explanation is temporarily unavailable. The evidence below has had its source checked.) |
| Snapshot stale | "Dữ liệu hiệu lực đang được cập nhật. Chưa thể khẳng định hiệu lực tại ngày này." (Effectivity data is being updated. Effectivity on this date cannot be asserted yet.) |
| Old result | "Kết quả dựa trên dữ kiện trước đó" (Result based on the previous facts) · "Cần kiểm lại vì dữ liệu hiệu lực đã thay đổi" (Needs rechecking because the effectivity data has changed) |
| Viewer fallback | "Chưa tô sáng chính xác vị trí đoạn này trên trang." (The position of this passage on the page has not been highlighted precisely.) |
| Amendment banner | "Khoản này trên PDF gốc đã được sửa đổi/bãi bỏ bởi [văn bản] từ ngày [ngày]." (This clause on the original PDF has been amended/repealed by [administrative document] since [date].) + "Xem văn bản sửa đổi" (View the amending administrative document) |
| Effectivity not yet clear | "Hiệu lực chưa xác minh. Hệ thống chưa kết luận khoản này còn hay hết hiệu lực." (Effectivity not yet verified. The system has not concluded whether this clause is still in effect or no longer in effect.) |
| Source outside the category | "Nguồn ngoài danh mục đã chọn" (Source outside the selected category) |
| Copy | "Sao chép kèm phạm vi" (Copy with scope) → the announcement "Đã sao chép, kèm phạm vi và cảnh báo." (Copied, including scope and the warning.) |
| Notice at the end of a result | "Kết quả hỗ trợ tra cứu và tham mưu, không thay thế quyết định của người có thẩm quyền." (The result supports lookup and is advisory (tham mưu); it does not replace the decision of the person with authority.) |
| Feedback | "Căn cứ sai" (Wrong evidence) · "Thiếu căn cứ" (Missing evidence) · "Văn bản hết hiệu lực" (Administrative document no longer in effect) · "Trích dẫn sai đoạn" (Wrong passage cited) |
| Domain blocked | "Tên miền này chưa nằm trong danh sách cho phép. Nhờ quản trị viên thêm tên miền sau khi xác minh." (This domain is not yet on the allowlist. Ask an administrator to add the domain after verification.) |
| Revision conflict | "Mục này vừa được người khác sửa. Tải lại để xem thay đổi." (Someone else just edited this item. Reload to see the change.) |
| Effectivity confirmation | "Thay đổi này ảnh hưởng cách hệ thống trả lời với các ngày từ [ngày]. Hành động được ghi nhật ký." (This change affects how the system answers for dates from [date]. The action is written to the log.) → "Duyệt" (Approve) / "Quay lại" (Go back) |
| Delete memory | "Xóa toàn bộ bộ nhớ của bạn? Hành động này không hoàn tác." (Delete all of your memory? This action cannot be undone.) → "Xóa bộ nhớ" (Delete memory) / "Giữ lại" (Keep it) |
| Not-stored mode | "Hội thoại này sẽ không được ghi nhớ." (This conversation will not be remembered.) |
| Memory (explanation) | "Bộ nhớ giúp trợ lý hiểu câu hỏi nối tiếp. Câu trả lời luôn lấy căn cứ lại từ kho tài liệu." (Memory helps the assistant understand a follow-up question. The answer always fetches evidence again from the document corpus.) |
| Empty category | "Danh mục chưa có tài liệu đã duyệt. Nhờ người phụ trách nạp tài liệu." (The category does not yet have an approved document. Ask the assignee to ingest documents.) |
| Connection lost | "Mất kết nối tới máy chủ. Nội dung bạn nhập vẫn được giữ." (Connection to the server was lost. What you entered is still kept.) + "Thử lại" (Try again) |
| Local Mode badge | "Local Mode · offline" (tooltip: "Mọi xử lý chạy trên máy chủ nội bộ, không gửi dữ liệu ra ngoài." (All processing runs on the internal server, and no data is sent outside.)) |
| API Mode badge | "API Mode" (tooltip: "Chỉ dữ liệu được chính sách cho phép mới được gửi tới nhà cung cấp AI." (Only data the policy allows is sent to the AI provider.)) |

Forbidden in the interface: "Đã khóa X căn cứ xác thực" (Locked X authentic pieces of evidence), "Đã xác minh X căn cứ" (Verified X pieces of evidence) (when effectivity and coverage have not been established), an accuracy percentage, "chắc chắn" (certain), "AI đảm bảo" (AI guarantees).

### D.9 Accessibility and interface performance

**Accessibility (WCAG 2.2 AA minimum)**

- Every function can be operated by keyboard; focus order follows reading order; focus is always visible (3px, offset 2px).
- Chat Agent: the launcher is a `button`; the panel is `role="dialog"` and **not modal** (`aria-modal="false"`) when docked, with `aria-labelledby` pointing at the title; opening the panel moves focus into the input; `Esc` closes it and returns focus to the launcher; focus is not trapped except when full screen on a phone; the stream sits in an `aria-live="polite"` region, announcing only important milestones (evidence is available, a result is available), and does not read each token.
- Touch targets ≥ 44×44px on a phone; support zoom up to 200% without losing function; no horizontal scrolling at 320px.
- Color is not the only signal; charts have an alternative data table.
- `prefers-reduced-motion` turns off slide/fade motion.
- Vietnamese content with diacritics displays correctly; the attribute `lang="vi"`; copying text includes the source.

**Interface performance**

- The launcher costs almost nothing on the page: the panel bundle, the PDF viewer, and charts are **lazy-loaded** (code-splitting); prefetch on hovering the launcher or when typing into the question box.
- The PDF viewer is built page by page (virtualized), rendering only the page being viewed and its neighbors; prefetch the cited page when hovering `[n]`.
- Long lists (documents, the queue, Gold [Not implemented — see ADR-010] cases) use pagination or virtual scrolling.
- Local Mode: do not load resources from outside (CDN, fonts, analytics, telemetry).
- Measure the page-load budget before and after adding the widget (WP 4.7); do not state a number before it is measured.

### D.10 Interface testing (mandatory)

- **Image snapshots** for: effectivity states (`active/modified/repealed/suspended/not_yet_effective/unknown`), result labels (4 + not found), FactChip (3 kinds + dirty), Sticky Amendment Banner (open/collapsed), EvidenceCard, the Chat Agent panel (closed/open/minimized/phone), the two-phase skeleton, the viewer fallback.
- **An automatic contrast test** for every color/state pair (tokens); if it fails, adjust the token.
- **Lint** forbids hardcoded HEX in components.
- **An automatic accessibility check** (axe or equivalent) on every screen + a manual keyboard/screen-reader check for S1, S3, and S6.
- **E2E**: flows L-1 through L-7 (C.11); Local Mode produces no request to the outside; moving between pages keeps the conversation; opening an old citation rechecks rights.
- **Copy**: a test that the forbidden strings in D.8 do not appear in the bundle.
- **USER desktop:** a real check of login → Orb → chat → PDF/workspace → collapse/open → tray → logout/exit; a round Orb with no square background/leftover shadow, opaque login/panel backgrounds, a drag region that does not cover text, resize works, no console. Check DPI 100/125/150/200%, a monitor/work-area change, 200% zoom, the widths 320/768/1024/1280px, and collapse/open without losing content.

---

## E. Supplementary API contract

SRS §11 keeps the original APIs (`/query/analyze`, `/query/requery`, `/query/evidence`, `/citations/*`, `/feedback`, `/admin/*`). The endpoint `/query/evidence` is responsible for returning evidence (căn cứ), evidence groups, findings, and reference suggestions; the earlier mock `/query/answer` and `/analysis/situation` have been removed; the complete two-phase streaming flow runs through `/agent/sessions/{id}/turns`. Below is the **supplementary API required at the behavior level**; the agent locks the OpenAPI schema at the start of Sprint 1 and reconciles it with SRS v1.3. Every endpoint checks ACL on the server; **no endpoint allows the Agent to write business data**.

| Group | Proposed endpoint | Purpose |
|---|---|---|
| Chat Agent session | `POST /api/v1/agent/sessions` (with an `incognito` flag) · `GET /api/v1/agent/sessions/{id}` · `DELETE /api/v1/agent/sessions/{id}` | Create, read state (facts, scope, revision), delete a session |
| Conversation turn | `POST /api/v1/agent/sessions/{id}/turns` (SSE) | Send a turn; uses the shared two-phase SSE contract |
| Turn control | `POST /api/v1/agent/sessions/{id}/turns/{turn_id}/cancel` · `…/retry` · `GET …/{turn_id}/events?run_id=…` | Stop, try again deliberately, reconnect the event stream by run |
| Memory | `GET /api/v1/memory` · `DELETE /api/v1/memory/{item_id}` · `DELETE /api/v1/memory` · `GET/PUT /api/v1/memory/preferences` | View, delete one item/all, read and save default-category search preferences (opt-in) |
| Analysis and suggestions | Integrated in `POST /api/v1/query/evidence` and SSE `/turns` · `POST /api/v1/query/followups` (A2) | Structured situation analysis (A1); suggested next questions (already dry-run, and deduplicated against claims). The mock endpoint `/analysis/situation` has been removed. |
| Sources and comparison | `GET /api/v1/nodes/{id}/notes` (A4) · `GET /api/v1/nodes/{id}/diff?as_of=…` (A5) · `GET /api/v1/nodes/{id}/related` (A6) | Points to note, version comparison, related administrative documents (văn bản) |
| AI suggestions for the curator | `GET /api/v1/admin/ai-suggestions` · `POST /api/v1/admin/ai-suggestions/{id}/accept` · `…/reject` · `…/edit` | The suggestion queue; accepting is the curator's action, with an audit |
| Source domains | `GET/POST /api/v1/admin/source-domains` · `PATCH /api/v1/admin/source-domains/{id}` | Allowlist management |
| Test set | `GET /api/v1/admin/evaluation/cases` · `POST /api/v1/admin/evaluation/cases/{id}/review` · `GET /api/v1/admin/evaluation/splits` | Approve Gold [Not implemented — see ADR-010]/the trap set; view the calibration/held-out split |
| Follow (P1) | `POST /api/v1/watches` · `GET /api/v1/notifications` | A9 |

**Supplementary SSE events:** `retrieval_started`, `evidence_verified`, `evidence_complete`, `analysis_ready`, `answer_complete`, `explanation_unavailable`, `understood_as`, `clarify_needed`, `analysis_item`, `followup_suggestions`, `memory_state_changed`, `turn_cancelled`, and `turn_error` (with error codes: `SESSION_EXPIRED`, `MEMORY_CAPACITY_EXCEEDED`, `QUERY_FAILED`). Added to the original event list in SRS §11.4; the frontend does not guess progress on its own.

**Shared contract that must go into OpenAPI at the start of Sprint 1**

- Scope: `scope_mode=SELECTED|ALL_AUTHORIZED`; SELECTED needs category IDs that have been granted; ALL_AUTHORIZED is resolved again by the server against current rights on every run. The query right is a separate right, and is not inferred from the SYS_ADMIN role.
- A session belongs to one principal; creating a session defaults to `incognito=true`. `incognito=false` is allowed only when an approved retention policy and an opt-in exist; if that is not yet sufficient, return `RETENTION_NOT_APPROVED`, and do not write silently. The response states `persistence_state=ephemeral|retained`, `expires_at`, and the revisions; it contains no secret. Incognito uses RAM as in C.4; sensitive HTTP caches are set to no-store, and the question/token is not stored in local storage.
- POST turn/retry accepts an idempotency key; the server assigns `turn_id`/`query_id`/`run_id`. Retry keeps one user message, creates a new run and a new budget with a rate limit; the response/event states clearly which run is in effect. Cancel stops only a turn owned by that user, and does not call a business tool.
- Every event has `query_id`, `run_id`, `facts_revision`, `snapshot_revision`, `event_sequence`. The snapshot may be null before it is pinned; from the moment evidence exists, the same snapshot must be used within the run. The SSE ID is the combination of query/run/sequence; Last-Event-ID reconnects the correct run, and does not create a new generation on its own. The client accepts only the current run, drops duplicate/old events, and does not splice claims from two runs. Reconnect must authenticate again and check ACL/policy before replaying; incognito replays only what remains in RAM, and when the TTL expires or the process restarts it returns `SESSION_EXPIRED`.
- DELETE memory/session deletes operational data and invalidates derivatives/cache/jobs under C.4; the audit/deletion-request ledger holds only the metadata that is needed. Do not return another person's content or session name. Deletion does not remove an approved source PDF, or business audit that has its own retention policy.
- The checklist uses the enum `passed/failed/unknown` and the standard names in D.7; the finding schema distinguishes conditional/needs_review/blocked. Do not stream a raw claim that has not been validated; do not treat a pass on a number/negation check as proof of meaning.
- **CORS security:** the development identity headers `X-Principal-Id` and `X-Roles` are removed completely from the CORS configuration in standard or production runs; they are opened only when the POC flag `DEV_ALLOW_IN_MEMORY_STORE=true` is on, to prevent a client from forging rights.
- **Model Registry & Runtime:** `is_safe_endpoint` allows loopback/localhost (`127.0.0.1`, `localhost`, `::1`) when `EVIDENCE_ALLOW_LOCAL_AI=true`, for Ollama/vLLM; filter the denylist of sensitive environment variables (`_SECRET_DENIED`) against `secret_ref`; automatically strip reasoning tags (`<think>...</think>`) and markdown fences for reasoning models; cap the AI-selection timeout at 70% of the query timeout, and degrade gracefully to the fixed pipeline when the model responds slowly.

| Operation | Required right/principal | Allowed consequence |
|---|---|---|
| Query, session, history, memory, cancel/retry | USER/the right rag.query + owner of the session + ACL scope | Write technical state when a policy exists; do not write business data |
| Upload/import, edit a node, accept/edit/reject an AI suggestion | CURATOR + document scope | Create/edit a draft only; accept does not publish |
| Approve a document/version/amendment/effectivity (hiệu lực) | REVIEWER + scope + If-Match | Write the approved revision, then build/publish an atomic snapshot |
| Configure account/role/provider/route/domain | SYS_ADMIN + the corresponding configuration right | Audit; do not grant a right to read content by default |
| Approve Gold [Not implemented — see ADR-010]/trap | REVIEWER/a designated specialist | Only confirm a case whose source was read; do not grant a right to tune held-out |
| Read audit | AUDITOR + audit scope | Read metadata/evidence within rights, and do not modify it |

A role is not inferred from the `/admin` prefix. For CURATOR-only, a call to approve must be rejected and the snapshot must not change; an account with several roles has only the rights that were granted explicitly. Services that write session/audit do not become tools for the LLM to call on its own.

---

## F. Detailed implementation plan

### F.1 How to read the plan

- Each sprint has **work packages (WP)**: the work · the output · acceptance; it ends with a **gate**. Recognize a gate only after its preconditions have been met; independent work may be done early, but a gate that is still missing must be reported, and a mock or a degraded state must not be turned into full acceptance.
- The plan **does not estimate time**: the SRS makes no commitment, and speed depends on the POC result. The owner sets the schedule after Sprint 0.
- Feature codes (Q, V, G, M, A, C, K, R, Z) refer to section C; screen codes (S1–S14) refer to section D.
- Technical defaults are in B.6; invariants are in B.3.

### F.2 Sprint and gate summary

| Sprint | Goal | Gate |
|---|---|---|
| 0 | A POC on real Windows: pgvector, PDF anchor, model, offline Local Mode, ADR-000/001/002 | ADRs locked; SRS v1.3; a footprint actually measured; pgvector, backup/restore, and Windows services run on the target machine |
| 1 | Document corpus, node effectivity (hiệu lực), ERD (including memory), foundation frontend, Gold [Not implemented — see ADR-010] v0 | Import → parse → review → approve → snapshot runs on a real PDF; the resolver passes every case; Gold v0 (150–200 questions) is approved by a person who knows the business; tokens + contrast test green |
| 2 | Retrieval, evidence-first, defense against wrong retrieval, A4–A6, a performance baseline | BFS 2-hop vs full-chain; pre-gate with 3 states; a stale snapshot; B0–B7 with real measurements; `wrong_doc_rate`/`wrong_node_rate`; a performance baseline; C1 at the rules tier |
| 3 | Model Router, Local/API Mode, claims, two-phase UI, Chat Agent, memory, P0 analysis and suggestions | Both API/Local modes run (Local is checked on a machine with the Internet actually disconnected); polarity/numeric/temporal regression green; the widget, memory, and trap set meet the threshold the owner locked; A1–A3 |
| 4 | Hardening, performance, Windows packaging, P1 chosen by the owner | Red-team (memory, prompt injection, ACL leakage); performance regression; a successful restore on a clean machine; footprint within the demo ceiling |

### F.3 Default decisions

Use the table in B.6. The agent does not stop and wait on those points; record an ADR when choosing otherwise.

### F.4 Workstreams and dependencies

Seven streams: **A** DB/ACL/effectivity · **B** Ingestion/Parsing · **C** Retrieval/Eval · **D** Validator/Workflow · **E** Model Router · **F** Frontend · **G** Platform/CI.

- Sprint 0 checks feasibility on Windows and on representative configurations; the POC selects a compatible library/runtime, and does not fix a provider/model. Profile B only proves the offline core; AI/local-model gates that are still missing must be reported separately.
- A (schema) blocks B, C, and D. B (nodes + span) blocks C and viewer display. The effectivity resolver (A) blocks the effectivity validator (D).
- Gold [Not implemented — see ADR-010] v0 (C) runs in parallel from the start of Sprint 1, but it needs real PDFs from Sprint 0 and a person to approve.
- F starts design tokens, the viewer, and split-view when OpenAPI/the schema is stable (end of Sprint 1); before that, use a mock server.
- E (router) is independent of retrieval; it only needs the schema `providers/model_profiles/stage_routes`.
- The widget and the USER desktop (WP 3.9) need an SSE contract with run_id (WP 3.4), EvidenceCards (WP 2.9), auth/ACL, and the shell POC in WP 0.5. Frontend/native does not create a separate workflow/backend.
- One lead is accountable for each WP: backend/data leads 4.8 (red-team, coordinating with retrieval and frontend); retrieval/eval leads 4.9 (P1 chosen by the owner, coordinating with backend/frontend). The UI part of a backend WP is contributed by frontend; the interface is not treated as a second owner in place of the lead.

### F.5 Sprint 0 — POC on real Windows

| WP | Work | Output | Acceptance |
|---|---|---|---|
| 0.0 | Place dossier 1.1, SRS v1.3, and the existing ADR-000 into the prescribed repository paths; keep v1.2.1 as history; review the B.7 matrix | The current document set links correctly | Do not rewrite the specification or re-choose decisions already locked; do not treat the existence of documents as completion of the technical WPs |
| 0.1 | Repository skeleton per SRS §17; CI (prefer a Windows runner): lint, typing, unit, migration check, secret scan, SBOM; `dependency-manifest` (license, version, SHA-256, footprint); declare the deployment profile installation.programs_root / EVIDENCE_PROGRAMS_ROOT and the dependency-manifest per B.8 | Repository + CI | CI green on an empty repository; source/scripts do not hardcode PATH/LLM; the install root is read from configuration, and the inventory records relative/real path |
| 0.2 | PostgreSQL + pgvector **on Windows**: install an approved build, configure it, and run it as a Windows service; measure exact-query performance; backup and restore; the API and the worker run as Windows services; install PostgreSQL/pgvector and the service wrapper under the tool-install root per B.8 | ADR-001 (how to install and operate on Windows) + an install script | `CREATE EXTENSION vector` and an exact `<=>` query run on the target Windows machine; a clean install can be reproduced; backup then restore onto a clean machine succeeds; the service starts again on its own after a failure. If pgvector fails: an ADR proposes a fix on Windows (which build, how to compile), and the architecture is not changed yet; binaries/helpers resolve through the manifest under the root; do not use a global PostgreSQL outside the manifest, and do not hardcode an executable path |
| 0.3 | Native PDF POC on 10–20 real PDFs: many provision levels, old files/TCVN3, scans, landscape rotation, CropBox. Compare pypdfium2/pdfplumber | `pdf-anchor-coordinate-contract.md` + a report | Highlight is correct across multiple lines, rotation, and CropBox; an uncertain mapping ⇒ page fallback + quote; record the correct rate on each file |
| 0.4 | A configurable NLP/model POC: Underthesea; embedding/reranker ONNX without PyTorch if compatible; LLM via API or a local runtime through the Registry, with no hardcoded model/provider/endpoint; check license, prefix, hash, and the trust_remote_code policy; install runtime/tools and the model/package cache under the configured root per B.8 | ADR-002 + footprint-report + a trial configuration with secrets masked | Check each capability/format/runtime; GGUF or a local LLM format that has been verified is allowed. If a model/key is missing, record MODEL_NOT_CONFIGURED or a capability not yet checked; do not fake AI and do not require one fixed model; the POC does not use a tool/model store outside the manifest or the global PATH; model/provider can still be changed by configuration |
| 0.5 | A thin E2E: auth, SQL ACL, upload one PDF + SHA-256, a viewer of the original bytes, FakeAdapter; a USER desktop shell POC of login → Orb → panel → collapse/open, tray, DPI, and hit-test region; verify-egress; the shell/helper/runtime uses only components already installed under the B.8 root | A shared backend skeleton + a shell report | A user without rights does not see the document; no square background/leftover shadow/drag region covering text; no console. FakeAdapter tests the contract only, and does not count as real AI; startup from a shortcut/service does not depend on the global PATH or a tool in the source directory |
| 0.6 | A POC parser for legal references (`Điều X khoản Y điểm Z`, symbol numbers) + the chain A→B→C on real PDFs | A report + sample tests | Parses the sample set correctly; an ambiguous case returns "không chắc" (not sure), and does not guess |
| 0.7 | A Local Mode POC with the Internet actually disconnected: sign-in, PDF, lexical/extractive; add embedding/rerank/LLM per each local capability that is configured; an egress guard + a sample firewall rule; check the inventory of local runtime/tool/model store under the B.8 root | verify-egress + a matrix of capabilities checked/not checked, and configuration with no secrets | No DNS/HTTP to the Internet; an internal LAN endpoint only per the allowlist. Profile B is accepted as a feasible offline core with the limits stated in public; missing dense/rerank/generation must not be recorded as those stages having been checked, and does not replace the S3 AI gate; a missing root/dependency reports an error, and does not fall back to another location or download/install online on its own |

**Gate S0:** ADR-000/001/002, SRS v1.3, footprint, and pgvector/backup/restore/Windows services have evidence on the target machine; the USER shell POC has a report; PDFs and hashes are in `evaluation/corpus_public_real`. The core-feasibility part may be met under profile B when the model is not yet ready, but capabilities of AI not yet checked are reported separately and are not accepted as met. A platform failure ⇒ record an ADR with an option that fits Windows; do not change the requirement or lower the S3 AI gate.

### F.6 Sprint 1 — Document corpus, node effectivity, Gold [Not implemented — see ADR-010] v0

**Streams A/B (data foundation)**

| WP | Work | Acceptance |
|---|---|---|
| 1.1 | The AI designs the entire ERD itself (tables, relationships, foreign keys, constraints, version history) and creates migrations + database tests per SRS §10; it checks consistency, integrity, and authorization itself. Includes principal/ACL, categories, documents/versions, `source_provenance`, pages/spans, nodes, references, amendments, reviews, snapshots, jobs, audit. **Add** FKs, RLS or a security view, exclusion/check for intervals, `unresolved_targets`, append-only audit. Fix the illustrative DDL: `evidence_groups.query_id` and `citation_id` must have real FKs | Migration up/down has tests; an ACL test does not leak; do not copy the illustrative DDL into production; a separate test for effectivity, amend (sửa đổi), supplement (bổ sung), and repeal (bãi bỏ) relationships down to each Article (Điều)/Clause (Khoản)/Point (Điểm), and for version history; the ERD comes with a self-check report, and only the important business principles are presented to the owner |
| 1.2 | Auth RBAC+ABAC; Category CRUD: create/edit/hide/soft-delete/restore, a tree at a configured depth, prevent cycles, N–N, import/export JSON/CSV with validation | SYS_ADMIN does not read content by default; a soft delete does not delete the original file; a document whose right was lost is not revealed |
| 1.3 | Source ingestion (block arbitrary URLs by default; the `domain_allowlist` table is added/edited/disabled by the admin in the interface after verification, and every change has an audit; PDF upload from the machine supports a single file or selecting many files in a sequential batch with independent metadata and a two-tier duplicate check of SHA-256 bytes + an NFC content fingerprint; only an `approved` document enters the corpus; a valid domain does not mean it is still in effect): `import-url` (DNS pin/recheck, block private/local, limit redirect/size), `upload` (magic bytes, quota, SHA-256), an immutable copy, provenance | Tests for SSRF, a redirect onto the internal network, and a fake-MIME file; a hash change at the same URL ⇒ a new version waiting for approval; a URL outside the allowlist is blocked; if a domain is disabled, import stops; a duplicate byte hash is blocked with 409, and duplicate content warns on the draft; a file with bad structure/hash/metadata can never become approved |
| 1.4 | Job queue: `SKIP LOCKED`, lease, heartbeat, retry cap, cancel, idempotency key, backpressure | Two workers do not parse the same version; cancel stops the right job; errors are redacted |
| 1.5 | Native parse of each page; diagnostics (the character `�`, valid-syllable ratio, text coverage, reading order); recognize TCVN3/VNI + transcode with a round-trip check; the state `needs_ocr` + an OCR-plugin interface (do not install the runtime); `extraction_method` per page | A bad page **never** becomes a verified quote; a scanned page goes to `needs_ocr` |
| 1.6 | Tree parser: Chapter/Section/Article/Clause/Point/Appendix; an unstructured administrative document (văn bản) is handled by heading/page (do not invent an Article/Clause); `text_indexed` has a breadcrumb; applicability header; `node_references` resolved at ingest, and unresolved ones are flagged; `parse_confidence`; a review queue prioritized by risk | Tests on real PDFs: a skipped clause, a reference "khoản 1 Điều này" (clause 1 of this Article), an official dispatch (công văn) that has no Article |
| 1.7 | **Effectivity:** `node_amendments` (the CURATOR prepares the draft, the REVIEWER approves), an amendment-chain resolver that runs to a fixed point (detects a cycle/break/overlap/conflict, a resource guard fails closed, and does not leak an administrative document outside the ACL), snapshot staged → atomic publish by `snapshot_revision`, `source_review_revision`, stale fails closed, a cache-invalidation hook, audit | Test: A→B→C→D beyond 2 hops is still correct; a cycle/missing edge/conflict ⇒ `temporal_unknown`; a worker failure ⇒ `SNAPSHOT_STALE`; rollback when cutover fails |
| 1.10 | Memory ERD: session, state, summary, user memory, retrieval hints, administrative-document map; constraints for a real delete and for retention | Tests for ACL, delete, and expiry; there is no path that turns memory into a citation |

**Stream F (foundation frontend)**

| WP | Work | Acceptance |
|---|---|---|
| 1.8 | A design-token module per D.2 (including the additional tokens); an automatic WCAG 2.2 AA contrast test; lint that forbids hardcoded HEX; `PdfViewer` (original bytes, anchor, an honest fallback); `AmendmentBanner` in two positions (toolbar + next to the highlight); `CuratorSplitView` (autosave draft ≠ Approve, `If-Match`, shortcuts do not approve while typing, confirmation when editing effectivity/in bulk); `CategoryAdmin`; `CuratorQueue`; the Allowed-domains screen (S8); a mock server from OpenAPI | Image snapshots for `active/modified/repealed/suspended/not_yet_effective/unknown`; keyboard + screen reader; the banner has a text label + an icon, not color alone |

**Stream C (evaluation)**

| WP | Work | Acceptance |
|---|---|---|
| 1.9 | **Gold [Not implemented — see ADR-010] v0, 150–200 questions** (replacing the 50–100 target) from PDFs of real official administrative documents. The agent reads the PDFs itself, and drafts questions, reference answers, and evidence (căn cứ); each question has the administrative-document symbol number, article/clause/point, the quoted passage, the version, the application time when relevant, and the source URL/hash. Coverage: a direct question, a situation with many conditions, an exception, an amending administrative document (including the chain A→B→C→D), transition, a repealed administrative document, insufficient evidence, outside the ACL, ordinary wording, no diacritics, an abbreviated symbol number, a PDF with a broken font. The agent checks structure, citations (the quote matches `text_original`), and duplicate detection itself. Separate calibration and held-out by scenario_group_id; rephrased questions/the same situation are not split across the two sets; the suggested ratio of about 30/70 is by case count but does not break groups. Operational regression is separate from held-out; the manifest/corpus/split revision is locked before tuning. The approval screen S11 | Each case has a status draft → reviewed by a person who knows the business; **only an approved case may be used as the standard**; the AI does not accept an answer on its own; the duplicate report and the citation check pass on every case; a script checks case ID, scenario_group_id, and paraphrase/near-duplicate situations between calibration and held-out; freeze split_revision before tuning; the corpus is separate from the business corpus; UI fixtures live in `synthetic_ui_fixtures` |

**Gate S1:** import → parse → review → approve → snapshot runs through on a real PDF; the resolver passes every case in WP 1.7; Gold [Not implemented — see ADR-010] v0 (150–200 questions) has been approved by a person who knows the business; tokens + contrast test green.

### F.7 Sprint 2 — Retrieval and evidence-first

| WP | Work | Acceptance |
|---|---|---|
| 2.1 | `vietnamese_nlp`: NFC + a tone-mark mapping table (`hòa/hoà`, `thúy/thuý`) checked in both directions and versioned, `đ→d` separately, an offset map back to the original, canonicalization of symbol numbers (keep the original value + a standard key), an alias dictionary managed by the curator | A two-direction test; `text_original` is never modified |
| 2.2 | Lexical: `L1_WORD` (Underthesea, fixed words), `L2_SYLLABLE` (uni/bigram), `text_folded` at a low weight; FTS `tsvector` + `setweight` A/B/C, GIN; ACL in SQL; store the tokenizer/index revision. **Do not call `ts_rank` BM25** | `EXPLAIN ANALYZE` shows the index is used; an ACL test does not leak through the tokenizer |
| 2.3 | Deterministic Legal Reference Router (B0): bypass Analyze only when the match is **unique + approved + ACL + as_of_date** | Tests for correct/incorrect/duplicate/ambiguous symbol numbers and Article/Clause/Point; ambiguous ⇒ return to Analyze |
| 2.4 | Dense: `EmbeddingAdapter`, `embedding_indices` + `node_embeddings` with their own revision, exact `<=>` on `authorized_nodes`; changing the model ⇒ a new index in parallel, then cutover; contextual prefix behind a flag, OFF | Do not mix vectors from different models; a model-switch test; HNSW is only a POC of ACL-filtered recall, off by default |
| 2.5 | Fusion: RRF; Grouped RRF by aspect (a missing `required` ⇒ `uncovered`); a 3-branch pre-gate calibrated by model/category/query type on the calibration set (do not touch held-out); conditional rerank of the top 12 with a window that keeps negation/exception/transition | Tests for false refusal, no-answer, and a low cosine that is still the correct source and is not dropped early; do not use RRF as a threshold |
| 2.6 | Context expansion: auto-merge when ≥2 clauses of the same Article; bounded BFS `max_hops=2` (visited, `max_expanded_nodes/tokens`, deadline, ACL + a time filter **at each step**, `partial_graph`); expansion outside the category only when policy allows and it is displayed clearly | Tests for cycle, depth, token cap, cross-scope; when the budget is exhausted ⇒ `coverage.partial_graph=true` |
| 2.7 | Evidence: `citation_records`, quote hydrator, citation validator (ACL at retrieval/generate/opening a citation; the span matches version/node/page/hash), numeric/date/period validator, Polarity & Modality validator (tested equivalents are allowed, `không quá ≈ tối đa` (not more than ≈ at most)), claim schema §6.2, an allowlist of `evidence_ids` | Tests for `15→30 ngày` (15→30 days), `không quá↔ít nhất` (not more than ↔ at least), `có thể↔phải` (may ↔ must), dropping `trừ trường hợp` (except where); measure false positives; do not claim the validator guarantees absolute correctness |
| 2.8 | Benchmarks B0–B7 + ablation on calibration/regression; pin corpus, split, model/tokenizer/prompt/config revision, protocol, and candidate before the lock-in evaluation | Report the confidence interval, missed-exception, false abstention, over-expansion, and ACL leakage; held-out runs only in the lock-in round under the protocol, and is not tuned after seeing the result and then reported as independent on the same set |
| 2.9 | API `/query/evidence`, `/citations/*`; `EvidenceCards`, `NodeToc`, a click opens the correct PDF/version/anchor, 4 feedback types into the curator queue | The click lands on the correct page; the banner matches the node/`as_of_date`; a link to the approved amending administrative document |
| 2.10 | Session service + rewrite of a follow-up question + display "Đang hiểu là" (Understood as) + ask again with one question | A follow-up question points at the right object; a missing condition ⇒ ask again, and do not guess |
| 2.11 | Administrative-document routing, metadata filters, version deduplication, `retrieval_diagnostics` (L0–L2) | Measure `wrong_doc_rate`/`wrong_node_rate` on Gold [Not implemented — see ADR-010]; there is an ablation |
| 2.12 | Retrieval hints approved by the curator + alias expansion with an audit | A suggestion not yet approved does not affect ranking |
| 2.13 | Performance baseline, precomputation at index time, connection pool | A P50/P95 report by stage on the target machine |
| 2.14 | Rules for points to note (A4), a deterministic diff (A5), a relatedness graph (A6) | Tests on real PDFs; the diff matches approved text; A6 does not reveal a node outside the ACL |
| 2.15 | A suggestion detector for the curator at the rules tier: amendment relationships, unresolved references, abnormal nodes (C1 a, b, d) | Precision/recall on a labeled set taken from real PDFs, with the curator approving the labeled set |

**Gate S2 (a release gate, not P1):** BFS 2-hop vs the full-chain resolver; pre-gate with 3 states; a stale snapshot + a worker failure; Gold [Not implemented — see ADR-010] v0 runs B0–B7 (approved cases only; the final evaluation is on held-out) with real measurements; a performance baseline; `wrong_doc_rate`/`wrong_node_rate`; A4–A6 and C1 at the rules tier.

### F.8 Sprint 3 — Model Router, claims, Chat Agent, memory, analysis

| WP | Work | Acceptance |
|---|---|---|
| 3.1 | Model Registry by capability, Hybrid Multi-LLM architecture (each stage selects a model through the Registry), two operating modes API Mode / Local Mode: `OpenAICompatibleAdapter`, `AnthropicNativeAdapter`, `LocalInferenceAdapter` written in-house (timeout, idempotent backoff, circuit breaker, redirect/endpoint limits); secrets encrypted, masked, and not readable back; an endpoint test uses aggregate data only | Do not use LiteLLM; test each compatibility feature, and do not assume rerank/JSON-schema |
| 3.2 | API Mode (Internet available; embedding/reranker local or via API; send only data the policy allows; fallback stays within the permitted API scope) and Local Mode (Internet fully disconnected; LLM, embedding, and reranker 100% local; fallback is internal models only). Egress policy by the formula in §8.4 with the condition `mode == API`; fallback only within the same privacy zone; audit every route decision | Remote denied ⇒ `REMOTE_AI_DENIED`; Local Mode has no DNS/HTTP to the Internet, only approved internal endpoints (egress guard + a Windows Firewall rule), and runs search/embedding/rerank/analysis/PDF viewing in full when the machine has no Internet; sign-in and startup do not call an external service; models and updates are imported by offline media with a hash check; a local failure does not turn remote on by itself |
| 3.3 | A fixed Analyze/Generate workflow, a total llm_attempt_budget=2 per run, counting errors/timeout/retry/fallback; rules-first, extractive when the model/budget is missing; evidence in EVIDENCE_DATA | A counter test in the adapter: no more than two LLM requests; the P0 summary is in code, and A2 does not add a call; on error or when the budget is exhausted, valid evidence is still returned, with no loop |
| 3.4 | OpenAPI/SSE per E: query_id + run_id + facts_revision + snapshot_revision + event_sequence; idempotency, cancel, an explicit retry, and reconnect; the snapshot is null before pin, and consistent after evidence | An old event/replay does not overwrite a new run; reconnect does not call the model again; recheck ACL/policy when emitting an event; incognito replays RAM only; do not stream a raw claim that has not been validated |
| 3.5 | Frontend S1: `FactChips` dirty-state, `DirtyFactBar`, `EvidenceGroupTabs`, `TwoPhaseSkeleton` (a neutral sentence), `CoverageChecklist` separating `source_verified / effective_checked / applicability_checked / claim_supported`, status labels, the `stale` label | Editing 3 chips produces only 1 requery; copy/print keeps scope + `as_of_date` + the warning; the UI does not use "Đã xác minh X căn cứ" (Verified X pieces of evidence) |
| 3.6 | Admin AI Configuration complete per S9: API/Local configuration, provider/adapter/endpoint/model/runtime/artifact/secret/stage routes, an aggregate test, and key masking; dashboard S12 | Changing a model within a supported adapter through configuration does not require a code change; no secret reaches the frontend/log; when there is no model/key yet there is a real status, and the owner enters it later; the USER has no AI-configuration form |
| 3.7 | Memory service M1–M5; a P0 rolling summary in code; retention + opt-in, incognito RAM TTL, Memory Center, invalidation, deletion of messages/summary/facts/cache, and cancellation of derivative jobs | A test that incognito content is not persisted, that the session is lost when the TTL expires, cross-user ACL, and that a delete is not written back by an old job; a claim does not point at memory; deleted data does not return after a restore that applies the deletion ledger |
| 3.8 | Long-context manager: token budget, evidence packing, handling by aspect, `partial` | A question across many administrative documents still quotes correctly; exceeding the budget reports `partial` |
| 3.9 | User Portal separated from Admin Portal; AgentLauncher/Panel + viewer/workspace in the same session; the USER desktop shell on Tauri 2 per W1–W8/S14: sign-in inside the app, Orb toggle, drag/resize, tray, logout/exit, shared backend state | Native/web E2E and server-side rights; no square background/leftover shadow/transparent login/console/drag region covering text; collapse/open/PDF/workspace does not lose the session; the USER has no administration menu; Local does not load external resources |
| 3.10 | L3–L5: contradiction/exception, tier-1 claim check, a tier-2 POC | `unsupported_claim_rate` falls relative to the baseline while false rejection does not rise |
| 3.11 | A trap set approved by a person who knows the business, with paraphrase/situation groups split into the correct split; a metrics dashboard; freeze the candidate/config before the lock-in evaluation round | Regression is used during development; the trap hold-out is only the lock-in evaluation, and does not reveal answers to the person who tunes; a set already used to fix is marked, and an unseen set replaces it for a later claim of independence |
| 3.12 | Situation analysis (A1) and information still missing (A3) on FactChips | Every row has an `evidence_id`; a missing condition does not produce a conclusion; the trap set is not broken |
| 3.13 | Suggested next questions (A2) with a retrieval dry-run | Every suggestion displayed has evidence inside the ACL (checked by test); measure the click rate |
| 3.14 | Interface: Analysis/Related tabs in the Chat Agent, the AI-suggestions tab for the curator (S6) | E2E; accept/reject is written to the audit; the AI has no API that writes business data |

**Gate S3:** API Mode / Local Mode are checked with the provider/model actually configured; Local is checked with the Internet disconnected, and an approved internal LAN endpoint is allowed; polarity/numeric/temporal regression, the two-phase UI, memory, the trap set, and A1–A3 pass. The USER desktop passes the flow login → Orb → chat → viewer/workspace → collapse/open → logout. If there is no real key/model yet, record that the AI gate has not been met; independent work may be completed with a mock, but it must not be recorded as real AI having run.

### F.9 Sprint 4 — Hardening and Windows packaging

| WP | Work | Acceptance |
|---|---|---|
| 4.1 | A security/regression test set: ACL through cache and `as_of_date`, cross-scope, prompt injection, XSS from PDF, CSP, KV cache isolation (if there is a local LLM), PDF mojibake, a curator missing approval, zero-answer | Every bug from feedback has a gold [Not implemented — see ADR-010] test that reproduces it |
| 4.2 | Load and backpressure: a concurrency gate for LLM CPU, job position, cancel; a test of 30–60 sessions; measure `evidence_ready_ms` P50/P95 separately from `final_answer_ms`; compare parallel vs serial vs CTE under load | Measurements are recorded with the environment; evidence-first still appears when inference is stuck |
| 4.3 | Packaging for Windows (installer, Windows services): Core Pack, Model Pack manifest (id, sha256, license, revision, dimension, RAM/disk), Data Pack; a clean demo install **< 10 GB** checked in CI; report the size of Core/Model/PostgreSQL/data separately; the installer places every tool/runtime that must be installed under `E:\Programs` through the deployment configuration, including cache/store managed by the project | `measure-footprint` runs in CI; no PyTorch/full ML extras by default; preflight of root/rights/disk space; the inventory's real path is the correct root; no hardcoded PATH/LLM, no global/AppData/Program Files install, and no silent drive change |
| 4.4 | Encrypted backup + restore onto a clean machine; retention of audit/memory/backup, the latest deletion-request ledger, SBOM/license/offline runbook/API and the desktop client; the runbook records the install root, the dependency-manifest, and how to load configuration; data/backup follow their own configuration | A restore that includes sample data already deleted: apply the deletion ledger before opening the service, and do not restore content into history/cache; if reconciliation is missing, do not open access yet. Endpoint/path configuration comes through the deployment environment; secrets are entered/restored by the operator under policy, and are not copied from the old machine; restore/reinstall keeps the correct tool-install root; do not copy an old machine path into source, and do not move data on your own |
| 4.5 | Gold [Not implemented — see ADR-010] extended beyond v0 (150–200 questions) **when a reviewer is available**; P1 (PyVi, BM25 re-score, ParadeDB, HNSW, ONNX INT8, KV prefix) opens only if a benchmark/ADR proves it | Do not turn it on by default before it passes non-regression |
| 4.6 | Optimize and separate the embedding/analysis/retrieval caches per C.7; analysis/retrieval stay OFF until the fingerprint and invalidation are sufficient; measure regression | A test of the same question with a different user/session/facts/memory/scope/as_of_date/ACL/policy/index/model; incognito has no durable cache; accuracy does not regress, and measurements include the environment |
| 4.7 | Check the widget and the desktop W1–W8/S14: auth, Orb toggle, opaque login/panel backgrounds, drag region, resize, tray, workspace/viewer, stop/retry, logout; responsive 320/768/1024/1280px, DPI 100/125/150/200%, multiple monitors, keyboard/contrast/reduced-motion; check native after install at the B.8 root, with tools outside the manifest not present on the test process's PATH | There are images/logs on the target Windows machine; the two interactive regions do not overlap, there is no square background/leftover shadow/console, and content is not lost on collapse/open; measure page load before/after; unit/build does not replace real native acceptance; Orb/chat/viewer still run on declared dependencies; a missing root/tool shows a clear error, and does not fall back to another path |
| 4.8 | Backend/data leads the red-team: prompt injection, memory poisoning, cross-user leak, context cache, incognito persistence, delete/restore, and old jobs; retrieval/frontend coordinate | No leakage; deleted content is not revived; feedback not yet approved does not change ranking. The report names the lead, the test cases, the data, and what was not checked |
| 4.9 | Retrieval/eval leads the P1 list the owner chooses: A7–A10, D1, C1(c,e); backend/frontend coordinate, and state clearly which items were not chosen | Each chosen feature has a test/metric and an owner lock; do not increase unsupported_claim_rate; do not turn P1 on by itself, and do not use held-out that has already been seen to tune |

**Gate S4:** red-team/cache/memory, a restore that does not revive deleted content, performance regression, and real desktop acceptance all pass; footprint is within the demo ceiling; P1 chosen by the owner passes acceptance. Do not use old tests/builds of a project that was lost as current evidence.

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

The "CHƯA XONG" (NOT DONE) section must not be left empty by omitting it; do not change acceptance criteria to make tests green.

### F.11 Work that needs a person (the agent cannot substitute)

- **Business rules:** approve the important business principles in the ERD (effectivity, amend, supplement, and repeal relationships down to Article/Clause/Point; node states) and the sequence `ingest → review → retrieve → evidence → claims → citation-click`, at the start of Sprint 1. There is no need to approve every technical detail.
- **Correctness of evidence:** a person who knows the business approves the sample answers of Gold [Not implemented — see ADR-010] v0 (150–200 questions) and the trap set before they are used as the standard; the CURATOR handles drafts/hints; the REVIEWER approves documents, effectivity metadata, and amendment relationships that affect evidence.
- **Access rights:** approve the remote-AI policy per category (API Mode); who may see the Chat Agent by role; the rights mapping to the personnel-management app if it is integrated.
- **Security and privacy:** the admin verifies and approves each domain placed on the allowlist; confirm the Local Mode configuration and the Internet disconnect at the network infrastructure; lock the default retention period of conversation memory and the kinds of data allowed to be stored.
- **Acceptance thresholds:** the owner locks the thresholds for the anti-hallucination metrics and the latency target after the baseline exists; chooses which P1 features to do first (C.5); the curator decides to accept or reject each AI suggestion.
- **Confirm the assumptions in B.6**, in particular: whether the user may choose the mode, the Gold [Not implemented — see ADR-010] split ratio, and the trap-set size.
- **Provide (this is not an approval):** a target Windows machine to measure footprint, latency, and backup/restore.

### F.12 Principal risks

| Risk | How the plan handles it |
|---|---|
| pgvector has a problem on Windows | WP 0.2; an ADR proposes a fix on Windows (which build, how to compile) before an architecture change is discussed |
| Blocking connections in the application cannot stand in for a real network disconnect | WP 0.7, 3.2; the agent provides an egress guard and a sample firewall rule; disconnecting the Internet at the infrastructure is guaranteed by the operator |
| A Vietnamese embedding/reranker model does not run on ONNX, or is blocked by a license | WP 0.4; profile B does not need an LLM/dense |
| An old PDF has a broken font, or a bbox shifts on rotation/CropBox | WP 0.3, 1.5; page fallback + quote, and do not highlight incorrectly |
| An amendment chain is missing an administrative document in the corpus | The resolver reports `temporal_unknown`, and does not assert "không sót sửa đổi" (no amendment was missed) |
| Gold [Not implemented — see ADR-010] of 150–200 questions needs a lot of approval time from a person who knows the business | The agent drafts complete citations and self-checks first; approval is in batches; a case not yet approved does not count toward the standard; report clearly how many cases have been approved |
| Mixing Gold [Not implemented — see ADR-010] with threshold tuning biases the evaluation | Separate calibration and held-out, with a script that checks they do not overlap |
| A local LLM on CPU congests at 30–60 sessions | Evidence is separated from generate; queue + backpressure; an extractive template |
| Dependency and size bloat | A manifest + CI measures footprint, with a demo ceiling < 10 GB |
| Old memory after the snapshot changes | Attach a revision + the label "cần kiểm lại" (needs rechecking) |
| Poisoned memory/hints | Only a curator-approved item takes effect; user feedback does not change ranking on its own |
| A new check layer causes over-refusal or slows things down | Watch false rejection and `evidence_ready_ms` after each layer; each layer sits behind a flag |
| Analysis is read as legal advice | Three labels, Evidence/Analysis/Suggestion; do not conclude when a condition is missing; a notice at the end of the result |
| The curator is overloaded by AI suggestions | Rank by risk, limit the number of suggestions per turn, measure `suggestion_acceptance_rate` |

### F.13 Mandatory release-gate cases (summary; the full P0 list is in SRS §16)

- ACL leakage: through lexical, vector, rerank, cache, tokenizer, citation, viewer, memory, suggestions, and the relatedness graph.
- SSRF/redirect/fake MIME; a URL outside the allowlist; prompt injection and XSS from PDF.
- Effectivity: the chain A→B→C→D; a cycle; a missing edge; a conflict; a stale snapshot; cutover rollback; `as_of_date` before the amendment date.
- Retrieval: a 3-branch pre-gate; no-answer; a low cosine that is still the correct source; confusing neighbors (Article 15/150); a false premise.
- Claims: numeric/date, polarity/modality, a quote hydrated by the backend, a claim that points at memory is rejected.
- Local Mode: no Internet connection; an internal endpoint only per the allowlist; a full run when the Internet is disconnected; no automatic switch to the API when the local LLM fails.
- Viewer: highlight is correct (multiple lines, rotation, CropBox); an honest fallback; the PDF bytes do not change.
- Operations: backup/restore onto a clean machine with the deletion ledger reconciled; Windows services start again on their own; footprint < 10 GB.
- The LLM is configured as API/Local, with no fixed provider/model/endpoint/key/path; try changing two representative configurations within a supported adapter; count retry/fallback inside the budget.
- PATH/installation: every project tool/runtime that is installed, and the corresponding cache/store, is at `E:\Programs` through configuration, with the real path checked inside the root; do not hardcode PATH/LLM or depend on a global tool; a missing root/dependency does not fall back to another path.
- Desktop: User/Admin separated, a round Orb toggle, login/panel not transparent, no console/leftover shadow, drag/resize does not cover content, collapse/open/PDF/workspace keeps the session, tray/logout/exit behave correctly.
- Gold [Not implemented — see ADR-010]: check the split by situation group, and held-out content must not be used to tune; record the candidate/config/corpus/split revision.

---

## G. Kickoff prompt and appendices

### G.1 Prompt to give the implementing AI

> You are the coding agent implementing the Vietnamese Evidence RAG Agent on Windows. Read `docs/SRS_v1.3.md`, `docs/HOSO_BAN_GIAO.md`, and `docs/architecture-decisions/ADR-000.md`; if you are inside the handover bundle, use the mapping in the README. SRS v1.3 and ADR-000 already exist: WP 0.0 integrates and reconciles them, and does not rewrite the specification or re-choose the owner's decisions.
>
> Implement the WPs in section F in order, including memory, anti-hallucination, analysis/suggestions, and the USER desktop. The USER opens the shortcut, signs in inside the Windows app, uses the round Orb at the right corner of the desktop, clicks to open/collapse chat, and opens a PDF/workspace in the same session; drag/resize/tray/stop/retry/logout/exit follow S14. The Admin Portal is separate from the User Portal and shares auth/backend/PostgreSQL/the document corpus/RAG; do not create a chatbot or a database on each USER machine. Keep the theme/tokens and text that is easy to read; the Orb has no square background/leftover shadow, login/panel backgrounds are opaque, the drag region does not cover text, and no console appears.
>
> The LLM is configured as API or Local through the Registry/Router per stage: adapter/provider, an approved endpoint/runtime, model ID/artifact, params, revision, secret reference, and fallback. Do not hardcode rights/provider/model/endpoint/key/host/port/path; use configuration, the manifest, and the platform API. API Mode has the Internet and permitted egress; Local Mode disconnects the Internet, uses only an approved internal runtime/endpoint, and does not switch to the API on its own. A POC model is not a mandatory model. The owner enters the key later; when there is no model/key yet, finish the feature and the contract tests, return real evidence/extractive output, and do not fake AI or accept a provider gate as met.
>
> Do not hardcode PATH or the LLM. Every project tool/runtime installed to build/install/operate the app must be under the root `E:\Programs` locked by the owner; the root is only the value of the deployment profile `installation.programs_root` / `EVIDENCE_PROGRAMS_ROOT`, and is not embedded in code/scripts. Resolve the executable/model/artifact and the tool cache from the manifest under the root, and do not use a PATH/global/AppData/Program Files fallback. If the root/dependency is missing, report an error, and do not change the drive on your own. Each machine installs only the components for its role; business data/backups have their own configured paths, and are not moved on their own. Follow B.8 and SRS §25.9.
>
> Follow B.3/B.7/B.8 and SRS §25: the CURATOR drafts, the REVIEWER approves; the analysis/retrieval cache stays OFF until the fingerprint and tests are sufficient; incognito is RAM only, and storage happens only with retention + opt-in; delete derivatives/cache/jobs, and on restore apply the deletion ledger; Gold [Not implemented — see ADR-010] is 150–200 cases approved by a person who knows the business, split by situation group, with regression separate from held-out; llm_attempt_budget=2 counts timeout/retry/fallback, and the P0 summary is in code. Scope is SELECTED or ALL_AUTHORIZED, and the server always checks ACL; SSE uses query_id/run_id/revisions/sequence, and an explicit retry does not mix turns.
>
> The AI builds the ERD/migration/database tests itself and does as much as possible of the technical work that can be verified; a person is needed only for business principles, access rights, security, and correctness of evidence (căn cứ). Do not accept Gold [Not implemented — see ADR-010] on your own, do not fabricate legal administrative documents (văn bản), do not add a forbidden dependency, and do not use an old result as current evidence. If a key/model/reviewer/device is missing, report exactly which gate is still missing and continue the independent work. At the end of each WP, report in the F.10 template, with measurements/environment and a CHƯA XONG (NOT DONE) section.

### G.2 Handover file list

| File | Role |
|---|---|
| `01_HOSO_BAN_GIAO_Vietnamese_Evidence_RAG_Agent.md` | This dossier: features, UX/UI, API, plan, prompt |
| `02_Vietnamese_Evidence_RAG_Agent_SRS_v1_3.md` | The current technical SRS, including §25 |
| `03_ADR_000_QUYET_DINH_BAN_GIAO.md` | Records the decisions, the defaults, and the acceptance boundary |
| `02_Vietnamese_Evidence_RAG_Agent_SRS_v1_2_1.md` | The historical copy, kept unchanged, and not used as the current requirement |

### G.3 Short glossary

**as_of_date:** the application date of a query. **Evidence:** a source passage that has been checked, together with its position. **Node:** one unit of an administrative document (Chapter/Section/Article (Điều)/Clause (Khoản)/Point (Điểm)). **Effectivity (hiệu lực) snapshot:** the computed result of an amendment (sửa đổi) chain, published atomically by revision. **Fail-closed:** when unsure, block/refuse instead of letting it through. **Held-out:** an evaluation set that is not used to tune thresholds. **Dry-run retrieval:** a trial retrieval run to check whether a suggestion has evidence inside the user's rights.
