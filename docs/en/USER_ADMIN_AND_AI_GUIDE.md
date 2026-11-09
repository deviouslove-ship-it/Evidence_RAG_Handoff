# Evidence RAG User, Administration and AI Configuration Guide

**Language / Ngôn ngữ:** [Tiếng Việt](../HUONG_DAN_SU_DUNG_VA_CAU_HINH_AI.md) · English

English counterpart of `docs/HUONG_DAN_SU_DUNG_VA_CAU_HINH_AI.md` (the Vietnamese original). Checked against the interface and source on 2026-11-09. Button names below follow the Vietnamese interface in the current source, given in English with the Vietnamese label in quotes where it helps; a running package may be a different build. See the [system description](SYSTEM_DESCRIPTION.md) for architecture and limits. Perform administration, model changes, restore or configuration changes only with the right permission and after understanding their effect on the system.

## Contents

1. [Log in and look up](#1-log-in-and-look-up)
2. [Ingest, OCR and review sources](#2-ingest-ocr-and-review-sources) · [Document management](#document-management)
3. [Categories, accounts and audit](#3-categories-accounts-and-audit)
4. [Configure AI Local](#4-configure-ai-local)
5. [Configure AI API](#5-configure-ai-api)
6. [AI assignment and embedding](#6-ai-assignment-and-embedding)
7. [Local models for offline Portable](#7-local-models-for-offline-portable)
8. [Start, stop, back up and restore](#8-start-stop-back-up-and-restore)
9. [Troubleshooting](#9-troubleshooting)

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

## 3. Categories, accounts and audit

- **Danh mục** (Categories): SYS_ADMIN creates/edits categories, codes, names and the option that allows remote processing. Ticking the option does not bypass egress policy or account permission. Soft-deleting a category affects the corresponding access.
- **Tài khoản & Phân quyền** (Accounts & Permissions): create or edit accounts, roles, status and permitted categories (see "Category permissions" just below); check the real need before granting. An administrator role does not grant the right to read all documents. New/reset accounts may have to change their password.
- **Category permissions**: the admin grants them per account in **Tài khoản & Phân quyền**, in two boxes: **Danh mục được phép tra cứu (ABAC)** (categories the account may look up and open documents from) and **Danh mục được xác nhận hiệu lực (người duyệt)** (categories in which a reviewer confirms effectivity; shown only when the account has the REVIEWER role), then press **Lưu tài khoản**. An account with no category sees no document. On initialisation `chuyenvien` already holds look-up rights on the test categories; `curator` and `reviewer` see an empty list until the admin grants categories. Roles (RBAC) decide what a user may do, categories (ABAC) decide which documents are visible; nobody can approve a submission they sent for review themselves.
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

This applies to packages with the BAT files in `deploy/lan-portable/`; the `deploy/portable/` build uses `start.cmd`/`stop.cmd` and has its own initialisation. Do not confuse launcher source with a package that already contains the full runtime.

1. Extract the LAN package fully into a folder on 64-bit Windows, check the manifest and the documents shipped with the package. Click **Start-Server.bat** and wait for the readiness checks; the window prints the address `http://<server IP>:<port>/`. The first run may take longer because of initialisation. Do not force-close or overwrite data while the database is running.
2. From a client on the same network, open the printed address and log in. If you cannot connect, check IP/port, the network and Windows Firewall. `tools/Allow-LAN-Firewall.bat` is an administrative action needing Administrator rights; review the network policy before running it. The database and Ollama are designed to listen on loopback only; web HTTP is unencrypted.
3. To stop, run **Stop-Server.bat** and wait for completion. `tools/Status.bat` shows status; `tools/Verify-Package.bat` compares the release checksums.
4. Run **Backup-Data.bat** to create a consistent copy of the database and file store, or specify a target folder per the package README. Check the result, protect it and keep the copy in another location. A backup contains data and permissions and needs access control.
5. To restore, use **Restore-Data.bat** with the backup folder per the package README. Read the contents and integrity check; the action requires typing `KHOI PHUC`, makes a pre-restore copy and keeps the old data as the launcher describes. Confirm only after choosing the right backup and understanding that it replaces the data in use. After restoring, re-check accounts, permissions, documents and search.

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
