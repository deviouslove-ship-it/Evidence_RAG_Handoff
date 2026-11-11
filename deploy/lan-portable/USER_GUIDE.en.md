# Evidence RAG - Windows Web LAN Portable: Complete User Guide

**Language / Ngôn ngữ:** English · Tiếng Việt: `HUONG_DAN_SU_DUNG.vi.md` (same folder)

This guide ships with **Evidence RAG - Windows Web LAN Portable** and describes this exact package: start-up, login, USER and ADMIN use, document management, OCR, AI Local and AI API configuration, backup/restore and troubleshooting. Button names follow the Vietnamese interface of the packaged build, given in English with the Vietnamese label in quotes where it helps. Perform administration, model changes, restore or configuration changes only with the right permission and after understanding their effect. The system supports lookup only: AI output always needs expert review and does not replace the official legal source.

## Contents

0. [This Portable package (read first)](#0-this-portable-package-read-first)
1. [Log in and look up](#1-log-in-and-look-up)
2. [Ingest, OCR and review sources](#2-ingest-ocr-and-review-sources) · [Document management](#document-management)
3. [Categories, accounts and audit](#3-categories-accounts-and-audit)
4. [Configure AI Local](#4-configure-ai-local)
5. [Configure AI API](#5-configure-ai-api)
6. [AI assignment and embedding](#6-ai-assignment-and-embedding)
7. [Local models for offline Portable](#7-local-models-for-offline-portable)
8. [Start, stop, back up and restore](#8-start-stop-back-up-and-restore)
9. [Troubleshooting](#9-troubleshooting)
## 0. This Portable package (read first)

**What is inside.** The web interface, the FastAPI server, PostgreSQL + pgvector (database, indexes, vectors), the original document store (file names are the SHA-256 of their content), Tesseract OCR (`vie`, `eng`, `osd`), Ollama and two local AI models (`qwen3:1.7b` for interpretation/expansion/labelling/relations, `qwen3-embedding:0.6b`, 1024 dimensions, for semantic search). It runs fully offline; no need to install Python, PostgreSQL, Ollama, Tesseract or Node.js. Client machines only need a browser.

**Server requirements.** Windows 10 / Windows Server 2016 or later, x64, PowerShell 5.1 (built in). At least 6 GB free for the extracted package and data; RAM at least 8 GB (recommended and tested: Intel Core i3, 32 GB DDR4, 512 GB SSD) (models run on CPU; the first call must load the model into RAM). Administrator rights are not needed to run.

**Quick start.**
1. Extract the WHOLE archive (.rar, with WinRAR or 7-Zip) into any folder on any drive (a folder name with spaces is fine; do not run inside the archive). A short path is recommended.
2. Double-click **Start-Server.bat**. The window checks the components, starts PostgreSQL, Ollama and the web server, then prints an address such as `http://<LAN IP>:8800/`. The first run takes 1-3 more minutes to build the package's own database from the original data copy in `seed\` and compare every table; documents, OCR, vectors and indexes are kept as they were and not re-imported.
3. Send that address to LAN users; they open it in a browser and log in. If another machine cannot connect, see 8.4 (firewall). The package **never opens a firewall port by itself**.
4. Stop with **Stop-Server.bat**; it stops only the processes started from this folder and does not affect other PostgreSQL/Ollama/Python on the machine.

**Folders.** `app\` (web and backend), `runtime\` (Python, PostgreSQL, Ollama, Tesseract), `models\ollama\` (AI models), `data\documents\` (original documents), `data\postgres\` (database, created on the first run), `seed\` (original data for the first build), `config\evidence.env` (settings, 8.6), `secrets\` (randomly generated database password and DPAPI-encrypted API keys; do not share), `logs\`, `backups\`, `tools\`.

**Accounts in the package and per-category permissions (ABAC).** The package has 5 accounts. Each account has its own **demo password**, usable right after extraction (no forced change at the first login). The passwords are **not** in the package, README, logs or source code (only scrypt hashes are stored); they are handed over separately in the file `Acount_Demo.md` placed next to the ZIP (not inside the ZIP). They are demo passwords, not operational ones: **change them right after receiving them** (Change password) or reset them in Admin Portal → Accounts & Permissions before any real use.

| Account | Role | Category permissions |
|---|---|---|
| `chuyenvien` | USER (Q&A, search) | Look-up on all 9 categories |
| `curator` | CURATOR + USER (ingest, edit drafts, OCR, submit for review; Q&A, search) | Look-up on all 9 categories |
| `reviewer` | REVIEWER + USER (approve, confirm effectivity; Q&A, search) | Look-up on all 9 categories and effectivity confirmation (`can_review`) on all 9 categories |
| `admin` | SYS_ADMIN + AUDITOR | System administration and audit; has no USER role and no category grant, so it does not by itself read document content |
| `ocr_tester` | USER (OCR test account) | Look-up on all 9 categories |

The nine categories: Law, Decree, Circular, Joint circular, Decision, Directive, Other document types, Unreviewed test material (PUBLIC_PDF_TEST) and OCR test (THU_NGHIEM_OCR). The last two hold test data that is not verified for business use. A reviewer cannot approve a draft they prepared themselves. The two-role accounts (`curator`, `reviewer`) can open both the user pages (Q&A, search, open original) and the Admin Portal; what a user can see is always decided by the granted categories (ABAC), and an administrative role does not grant read access by itself. Permissions can be changed in Admin Portal → Accounts & Permissions. Old login sessions are not carried into the package.

**Data in the package.** 105 documents, 7,447 passages with vectors (qwen3-embedding:0.6b, 1024 dimensions), 1,566 source pages, 191 original document files. No Gold question set is used to score the AI (ADR-010); the AI only assists and the domain staff decide. Do not use this package to claim accuracy or deployment readiness.

**OCR in the package.** The bundled Tesseract in `runtime\tesseract` is used automatically by the backend (languages `vie+eng`); nothing to install or configure. Per-page and per-PDF timeouts are set with `EVIDENCE_OCR_PAGE_TIMEOUT_SECONDS` and `EVIDENCE_PDF_TIMEOUT_SECONDS` in `config\evidence.env`. The OCR page-review procedure is in section 2.

**AI mode.** Default `LOCAL`: all AI processing runs on the server with the bundled Ollama and no data leaves the machine. API mode applies only when an administrator configures it and policy allows (section 5).
## 1. Log in and look up

1. Open the address from the operator in a browser, choose **Đăng nhập** (Log in), enter the account and password you were given. If asked, use **Đổi mật khẩu** (Change password) first. Do not share accounts.
2. In **Hỏi đáp có căn cứ** (Grounded Q&A), enter a clear question with the document number and Article if known, and send it. You can stop or retry a running turn. Read the answer and each document card, the Article/Clause label, the excerpt and the effectivity. "Not found" means no suitable evidence in the current scope and store; it does not prove the rule does not exist.
3. Choose **Xem tất cả kết quả** (See all results) to move the question to the search page. In **Tìm kiếm văn bản** (Document search), enter the text, choose **Tìm theo nghĩa (toàn diện)** (by meaning, comprehensive), **Tìm đủ các từ** (all words) or **Tìm chính xác cụm từ** (exact phrase), then press **Tìm kiếm** (Search). Open **Bộ lọc** (Filters) to choose category, document type, effectivity date and time range; after results appear you can filter further by status. Browse each group and page.
4. In Q&A or in search results, choose **Diễn giải AI** (AI interpretation) if you want an interpretation from suitable evidence. Read the parts lacking evidence, the warnings and **Căn cứ hỗ trợ** (Supporting evidence); use **Diễn giải tiếp** (Continue interpreting) if offered. Statements checked automatically still need verification before use.
5. Choose **Mở văn bản gốc** (Open original) on an evidence card. A PDF opens separately at the source page; Word/TXT downloads the original file. A refusal does not mean the file was deleted: the session, permission, source state or integrity check may have failed.

## 2. Ingest, OCR and review sources

These sections appear according to the CURATOR/REVIEWER permissions granted.

1. Go to the Admin Portal → **Tài liệu & Duyệt nguồn** (Documents & source review). In **Nhập PDF nguồn (Biên tập viên)** (Import source PDF, editor) choose a PDF, DOC, DOCX or TXT file; enter the title, document type, number and an official HTTPS link if any. For many files, check each item before creating drafts; the system processes them one at a time, lets you stop and retry the unsuccessful ones. If the result is unclear after a lost connection, check the queue before sending again.
2. Choose **Tạo bản nháp** (Create draft), then **Mở PDF & rà soát** (Open PDF & review) to see the content and tasks. Edit/check metadata, the original, pages and warnings. If needed, press **Trích xuất lại PDF gốc** (Re-extract original PDF) when you have permission and OCR is configured; never assume OCR text is correct.
3. For scanned PDFs, the reviewer opens each page in the review screen, compares OCR text and warnings with the page image, then confirms. Do not confirm a page that is unreadable or wrong; configure OCR and re-extract, or reject the draft as appropriate. Even approved OCR text must be compared with the image when used.
4. The editor chooses **Gửi duyệt** (Submit for review). A different reviewer opens the pending draft, resolves open tasks, chooses the applicable categories and enters review notes. Press **Phê duyệt & Phát hành** (Approve & Publish) when conditions are met, or **Từ chối** (Reject). Byte-identical files are blocked; content-duplicate warnings need to be considered.
5. Go to **Hiệu lực** (Effectivity) to review effectivity proposals, relations and labels where permitted. An unverified proposal is not a conclusion about legal effectivity.

### Document management

1. Open **Admin Portal → Quản lý văn bản** (Document management). Search by number or title, or filter by type, issuing body, date, processing status, effectivity and lookup status. Press **Áp dụng bộ lọc** (Apply filters).
2. Choose **Chi tiết** (Details) to see metadata, categories and versions. With read permission, open the original file, move between OCR pages, view Article/Clause/Point and the number of items already embedded in the serving index. Open **Lịch sử xử lý** (Processing history) for recent actions.
3. A CURATOR may use **Sửa thông tin** (Edit information, then **Lưu thông tin**), **Sửa chữ OCR** (Edit OCR text of a scanned page, then **Lưu sửa OCR**) or **Xử lý lại từ tệp gốc** (Reprocess from the source file, then **Xác nhận xử lý lại**). Reprocessing runs the configured extractor/OCR and returns the result to draft. After approval or rejection, the action creates a new draft version. Use **Thêm phiên bản từ tệp mới** (Add version from a new file) to attach a new PDF, Word or TXT to the same document, then choose **Tạo phiên bản nháp** (Create draft version). Verify the file's information before submitting for review.
4. In the document record choose **Gửi duyệt** (Submit), or select several drafts in the list and choose **Gửi duyệt các bản đã chọn** (Submit the selected), confirming with **Xác nhận gửi duyệt**. Check each result. A different REVIEWER opens the pending version, chooses **Mở PDF và thẩm định** (Open PDF and review), views the source file, resolves tasks and re-confirms each edited OCR page. Enter a reason, then choose **Phê duyệt phiên bản** (Approve version) or **Từ chối phiên bản** (Reject version). Assigned categories are kept. The reviewer needs approval permission on all assigned categories. If a "version changed" message appears, reload the detail and continue. The previously approved version stays searchable while the correction awaits approval, if the document is active and the user has permission.
5. SYS_ADMIN selects one or more documents to **Tạm ngừng** (Suspend), **Mở lại tra cứu** (Resume lookup), **Xóa mềm** (Soft delete) or **Khôi phục văn bản** (Restore document). Check the selected list, enter a reason and confirm. Use the **Đã xóa** (Deleted) filter to restore soft-deleted documents. A document that was suspended needs **Mở lại tra cứu** separately. A draft awaiting approval must still pass review before publication.

If a correction changes the grounds of an Article/Clause/Point-level relation, review it again in **Hiệu lực**. When the system cannot match the target by legal path, the relation must have the correct target node set through the review API before approval. The interface currently has no target-node picker. Permission to view content is granted per scope, including for administrator accounts.

**Article/Clause-level effectivity proposals (this build).** The system only *proposes*; a person with effectivity-confirmation rights decides.
- An item with its own "from date D" (for example "Replace clause 2 of Article 4 … from 01/01/2027") uses that date D; only when it has none is the effective date of the whole document used. An item that states several different dates leaves the date empty and the reviewer must enter it.
- "Articles 5 and 6 replace Articles 3 and 4" is split into one proposal per target Article (the source stays the group "Articles 5 and 6").
- "Replaces part of / some articles of document X" without naming an Article creates a *replace* proposal with an empty target: it cannot be approved until a target node is chosen (the system answers `RELATION_TARGET_REQUIRED`).
- "Amend clause 2 of Article 4 of document X" or "Repeal Article 3 of document X" is attached to the exact target node. After approval the repealed Article shows as **no longer in force**, so it disappears from default search results; the amended clause shows as **amended**.

## 3. Categories, accounts and audit

- **Danh mục** (Categories): SYS_ADMIN creates/edits categories, codes, names and the option that allows remote processing. Ticking the option does not bypass egress policy or account permission. Soft-deleting a category affects the corresponding access.
- **Tài khoản & Phân quyền** (Accounts & Permissions): create or edit accounts, roles, status and permitted categories (see "Category permissions" just below); check the real need before granting. An administrator role does not grant the right to read all documents. New/reset accounts may have to change their password.
- **Category permissions**: the admin grants them per account in **Tài khoản & Phân quyền**, in two boxes: **Danh mục được phép tra cứu (ABAC)** (categories the account may look up and open documents from) and **Danh mục được xác nhận hiệu lực (người duyệt)** (categories in which a reviewer confirms effectivity; shown only when the account has the REVIEWER role), then press **Lưu tài khoản**. An account with no category sees no document. On initialisation `chuyenvien` already holds look-up rights on the test categories; `curator` and `reviewer` see an empty list until the admin grants categories. Roles (RBAC) decide what a user may do, categories (ABAC) decide which documents are visible; nobody can approve a submission they sent for review themselves. This Portable package already grants all 9 categories to `chuyenvien`, `curator` and `reviewer` (and `reviewer` also holds effectivity confirmation), see section 0.
- **Mô hình AI & Kiểm toán** (AI Models & Audit) → **3. Nhật ký Kiểm toán** (Audit log): authorised users see administration activity and verify the audit chain. Do not put passwords or API keys in notes or ordinary communication.

## 4. Configure AI Local

Prerequisite: the model service is running and the model is available; the backend must be able to reach that address. For a LAN model server, the endpoint must be on the allow-list in the operating configuration. An endpoint of `localhost`/`127.0.0.1` is interpreted from the **backend server**, not from the client machine.

1. Log in as SYS_ADMIN, open **Mô hình AI & Kiểm toán** (AI Models & Audit) → **1. Mô hình AI** → **Thêm AI Local** (Add AI Local).
2. Enter the **Tên hồ sơ** (Profile name); choose the **Runtime** Ollama, vLLM or llama.cpp; enter the **Địa chỉ máy chủ** (Server address) according to the real endpoint and the exact **Model ID** the service provides. Auto-filled values are suggestions; check the port and API path. The runtime must expose an API compatible with the corresponding adapter.
3. Open **Nâng cao** (Advanced) if you need to choose role/capability, version, limits or dimension; an embedding model has its own role. Do not change parameters arbitrarily without knowing the effect.
4. Press **Kiểm tra kết nối** (Test connection) to try without saving, then **Kiểm tra & Lưu** (Test & Save). Read the result of each step; the option **Vẫn lưu (chưa dùng được)** (Save anyway, not usable) only keeps the configuration when the test fails and does not make the model ready. After fixing the service, use **Kiểm tra** on the profile card.
5. Go to **2. Phân công AI** (AI assignment), choose the model for the function you want and press **Kiểm tra & Áp dụng** (Test & Apply). Under **Nâng cao** you can configure fallback, API escalation or call limits if policy allows. Check the result before real use.

The LAN Portable that ships with Ollama uses its own port, and the launcher may synchronise the local profile endpoint with the package port. If you plan to use a different LAN model machine, check the endpoint policy and the launcher behaviour of that version first; do not assume the address you enter is always kept after start-up.

## 5. Configure AI API

1. Determine the provider, model ID, HTTPS Base URL, data-processing permission and your organisation's policy. The `API` mode, the domain allow-list, user permission and the category's remote-processing flag can all affect the result. LOCAL mode never switches to the Internet by itself.
2. Open **1. Mô hình AI** → **Thêm AI API** (Add AI API). Choose the **Nhà cung cấp** (Provider: OpenAI, Gemini or custom), check the **Base URL**, enter the **Model ID** and **API Key**. A custom provider needs a protocol compatible with the adapter. A suggested Base URL does not prove the model or key works.
3. Choose function/role under **Nâng cao** if needed. Press **Kiểm tra kết nối**, then **Kiểm tra & Lưu**; read policy, key, connection, model or response errors. Use **Sửa** (Edit) to change parameters or enter a new key. A saved key is never shown again; on Windows the key store uses DPAPI of the account running the server.
4. Open **2. Phân công AI**, choose the model on the corresponding function row → **Kiểm tra & Áp dụng**. For embedding use the separate tab below. If the test fails, choosing to save/apply anyway only creates a configuration that is not ready.

A key entered through the interface travels from the browser to the server; LAN Portable is described as an unencrypted HTTP connection. Enter it only over a trusted path and machine, or use suitable transport protection. A real OpenAI/Gemini connection was not confirmed in the 2026-11-08 test report; verify it with an account and policy that permit it.

## 6. AI assignment and embedding

| What to change | Action | Effect on vectors |
|---|---|---|
| Model for **Diễn giải AI** (AI interpretation) | In **2. Phân công AI**, choose the AI interpretation row, test and apply | Does not recreate vectors/index. |
| Model for semantic search | Create a profile with the embedding role; open **Embedding (tìm theo nghĩa)** | Preflight and confirm a job that creates/fills vectors, verify the new index, then switch; the old index is kept during the build and after the switch. |

To change embedding: under **Chọn / đổi model embedding** (Choose / change embedding model), choose a profile, batch size, and choose **Tạo chỉ mục mới từ đầu** (Create new index from scratch) only if really needed; press **Kiểm tra model** (Test model). Review the dimension, the number of nodes to create, the estimate and the checks. If they pass, confirm creating the job. Follow progress and errors and use pause/resume/retry/cancel according to the state. The worker must be on; if it fails, the serving index is kept. Newly approved nodes may need **Kiểm tra và bổ sung vector còn thiếu** (Check and fill missing vectors). Do not delete the old index by hand to "fix" an error.

## 7. Local models for offline Portable

Before moving anything, check the `MANIFEST.json` of the **actual package**: the LAN package per source places Ollama at `runtime/ollama` and the model store at `models/ollama`; the launcher sets `OLLAMA_MODELS` to this store and checks that models in the release manifest exist. Not every Portable package includes Ollama or the same structure.

1. On a machine with Internet and permission, prepare the right model, version and compatible runtime in the Ollama store; check the model name and licence. Transfer by an approved storage device. An Ollama model consists of a manifest and content blobs; copying a single GGUF file or a folder named after the model is not enough for Ollama to recognise it.
2. On the offline machine, back up the package/model store and stop with **Stop-Server.bat**. Move the full manifest and matching blobs into the package's `models/ollama` store, keep the folder structure and do not overwrite blobs/manifests in use without checking. Do not copy the database, secrets or source-machine data along with the model.
3. Start again, confirm the package's service recognises the right Model ID, then add a Local profile and **Kiểm tra kết nối** as in section 4. If the model is an embedding model, continue with the separate preflight and job confirmation in section 6; an interpretation model only needs function assignment.

**Limit:** the launcher source verifies the models listed in the release manifest; a model added by hand does not become a component certified by the release manifest/checksum. The procedure for copying extra models after release has no separate test evidence in the project documents. If you require release-integrity verification or the model is not recognised, use the release process managed by the operator and re-verify the package; do not edit a checksum to hide an error. Adding a model does not require recreating vectors unless you select it for embedding.

## 8. Start, stop, back up and restore

**8.1 Start.** Double-click **Start-Server.bat** and wait until the window prints the access address (every LAN IP of the server is listed, for example `http://192.168.1.15:8800/`). Running it again while the server runs does not create a second process. The package removes the Windows "blocked" mark itself if it was downloaded over the Internet/email. On an error the window names the failing component; details are in `logs\launcher.log`. The package uses only components in its own folder and ignores any Python/PostgreSQL/Ollama/Tesseract/proxy environment variables of the machine.

**8.2 Stop.** Double-click **Stop-Server.bat** and wait for completion (PostgreSQL stops with `pg_ctl stop -m fast`). Stop with Stop-Server.bat before shutting down the machine or copying the folder. Never delete `data\` or copy over `data\postgres` while it runs.

**8.3 Status and package check.** `tools\Status.bat` shows processes, ports and document/vector counts. `tools\Verify-Package.bat` compares the SHA-256 of runtime, model, application and original document files with `checksums.sha256` (takes a few minutes). `MANIFEST.json` lists versions and components.

**8.4 Let other machines connect (firewall).** The package does not change Windows Firewall. If another machine cannot open the address, run `tools\Allow-LAN-Firewall.bat` and accept the Administrator prompt (once). The rule opens only the web port (default 8800) for the local subnet on Private/Domain networks; remove it with `tools\Allow-LAN-Firewall.bat remove`. PostgreSQL (55433) and Ollama (21434) listen on `127.0.0.1` only and are not opened to the LAN. The connection is unencrypted HTTP: use it only in a trusted internal network.

**8.5 Backup and restore.**
- **Backup-Data.bat** [target folder]: consistent backup of the database (including vectors, permissions, audit) and the whole original document store with the SHA-256 of every file; it can run while the server runs. By default it writes to `backups\backup-<date-time>\`. Copy the backup to another drive and protect access, since it contains data and permissions.
- **Restore-Data.bat** [backup folder]: checks integrity, shows the contents, asks you to type `KHOI PHUC`, saves the current data to `backups\pre-restore-*`, builds a new database, compares every table, and only then switches. The old data stays in `data\postgres.before-restore-*` (delete by hand when sure). The document store is only added to; no file is deleted. After restoring, re-check accounts, permissions, documents and search.

**8.6 Configuration (`config\evidence.env`).** Listen address (`EVIDENCE_LISTEN_HOST`), web/PostgreSQL/Ollama ports (`EVIDENCE_HTTP_PORT`, `EVIDENCE_PG_PORT`, `EVIDENCE_OLLAMA_PORT`), AI mode, upload limits and timeouts. After editing, run Stop-Server.bat then Start-Server.bat. Change a port if another program occupies it (the error names the program). The local model address in the Model Registry is synchronised by the launcher with the bundled Ollama port. The database password is generated by the server on the first run and kept in `secrets\`.

**8.7 Move to another machine.** Safe way: on the old machine run Backup-Data.bat and copy the backup folder; on the new machine extract the package, run Start-Server.bat, then Restore-Data.bat. Quick way: Stop-Server.bat then copy the WHOLE folder (changing drive, folder or machine name is fine because paths are relative and the IP is detected on each run); if PostgreSQL reports incompatibility, use the safe way. Running on a physical Windows machine other than the build machine has not been verified for this package.
## 9. Troubleshooting

| Symptom | What to check |
|---|---|
| Cannot log in | Check the account, lock state, password and any forced password change; contact the administrator. |
| No evidence found | Check category permission, approved sources, filters, search mode and effectivity date; do not grant permission just to get a result. |
| Original does not open | Check the session and ACL, version state, source and hash; compare the server log with the operator. |
| Scan has no text / cannot be approved | Check Tesseract and the package's language data, tasks and per-page OCR confirmation. |
| AI connection error / `MODEL_NOT_FOUND` | Check the service, the address as seen from the backend, Model ID, adapter, port and the model list; run **Kiểm tra kết nối** again. |
| `AI_EGRESS_DENIED` | Check LOCAL/API mode, the endpoint allow-list and data policy; do not turn off protection only to get past the error. |
| Semantic search not working | See the **Embedding** tab: model, active index, worker, missing vectors and preflight errors. Keyword search may still work. |
| Slow / timeout / overload | Narrow the query and filters, retry; check server, database and model resources. The first local model call may have to load the model into RAM. |
| Cannot reach the LAN | Check `tools/Status.bat`, the IP/port printed at start, Private/Domain network and firewall. Never open the PostgreSQL/Ollama ports to the LAN. |
| Package reports missing files or busy port | See `logs/launcher.log`, run Verify-Package; check the port settings in `config/evidence.env` and the package documents. Change configuration only when permitted, then stop/start. |

The reports under `docs/evidence/2026-11-08-*` record historical tests on the development machine; they do not show that a specific deployment or a new API model has been accepted.

