**Language / Ngôn ngữ:** [Tiếng Việt](REPORT.md) · English

English counterpart of `docs/evidence/2026-10-22-desktop-native/REPORT.md`. The Vietnamese file is the original.

# Implementation and Real-World Verification Report (Full Stack + Desktop Native)

Date performed: `2026-10-22`

## 1. What was done

1. **Local authentication, RBAC/ABAC, separation of duties (CURATOR / REVIEWER), and the audit hash chain:**
   - Implemented migration `backend/app/migrations/0002_auth_admin.sql` (together with the `.down.sql` rollback) and the automatic migration runner `backend/app/migrations/runner.py`.
   - Password hashing with `hashlib.scrypt` (`backend/app/auth_acl/passwords.py`), PostgreSQL session management, account lockout after 5 consecutive failures, and a forced password change (`PASSWORD_CHANGE_REQUIRED`) in `backend/app/auth_acl/service.py` and `backend/app/api/v1/auth.py`.
   - A source-approval flow with separation of duties in `backend/app/documents/review.py`: `CURATOR` creates a draft and submits it for review (`submit_draft_for_review`); `REVIEWER` resolves the review task and approves or rejects (`approve_document_version`, blocks self-approval with `SELF_APPROVAL_DENIED`, blocks approval while open tasks remain with `OPEN_REVIEW_TASKS_REMAIN`, rechecks the SHA-256 of the original PDF on disk, stamps `source_provenance.verified_at`, attaches the ACL categories, and approves the nodes/spans).
   - An immutable hash-chained audit log (`audit_events`) with the transaction lock `pg_advisory_xact_lock` and the chain-integrity check (`verify_audit_chain`) in `backend/app/audit.py`.
2. **Admin Portal and User Workspace (Web + Desktop UI):**
   - Login and forced password-change screens (`frontend/src/components/LoginPanel.tsx`), plus a **Change password** (**Đổi mật khẩu**) button directly on the Topbar (`frontend/src/App.tsx`) for every active account.
   - An evidence-first lookup workspace (`frontend/src/pages/EvidenceChat.tsx`, `frontend/src/components/PdfViewer.tsx`):
     - A methodical two-column layout: the **left column** shows groups of approved legal evidence (căn cứ) and a viewer of the original PDF on the correct page through a `Blob` URL; the **right column** is the **Evidence-grounded lookup** (**Tra cứu có căn cứ**) chat pane.
     - Natural Vietnamese queries are normalized (`backend/app/storage/authorized_search.py`), and interrogative function words are dropped for FTS.
     - **Session Ephemeral Memory**: multi-turn fact extraction (`FactChips`), RAM managed with the thread lock `threading.RLock`, and a clear-session button that resets the memory.
   - The Admin Portal (`frontend/src/pages/AdminPortal.tsx`) has 4 complete sections:
     - **Documents and source review** (`CURATOR` / `REVIEWER`): upload a draft, submit it for review, and approve or reject with separation of duties.
     - **Categories** (`SYS_ADMIN`): add (with 3 quick templates), edit, and soft-delete a category (`DELETE /api/v1/admin/categories/{category_id}`), together with ACL revocation and an audit-log entry.
     - **Accounts and ACL** (`SYS_ADMIN`): add an account, assign RBAC/ABAC, change or reset a password, lock or unlock an account, delete an account (`DELETE /api/v1/admin/users/{user_id}`, self-deletion blocked by `CANNOT_DELETE_SELF`), and change one's own password.
     - **AI models and audit** (`SYS_ADMIN` / `AUDITOR`): a 6-stage multi-model architecture (`analyze`, `embedding`, `rerank`, `answer`, `verify`, `ocr`) with 10 model profiles (6 local AI + 4 cloud APIs), a visual interface of 3 subtabs, the redundant `Revision` field hidden, and a check of audit hash-chain integrity.
3. **Windows native desktop USER app (`src-tauri/`):**
   - Two windows are configured in `src-tauri/tauri.conf.json`:
     - `main`: an opaque window (`transparent: false`, `decorations: true`, `1180x780`, `minWidth: 360`, `minHeight: 520`) for login, the chat pane, and PDF viewing.
     - `orb`: a circular floating window (`url: index.html#/orb`, `72x72`, `transparent: true`, `decorations: false`, `shadow: false`, `alwaysOnTop: true`, `skipTaskbar: true`) shown after login.
   - Smooth dragging by pointer offset (`drag_orb_window`), synchronization of the question and the evidence (căn cứ) from the Orb into the main workspace (`open_evidence_in_workspace`), and the Orb fully hidden on the web so it is not redundant.
   - Coordinate clamping (`work area` clamping) across multiple monitors and DPI scales of 100%–200% in `src-tauri/src/geometry.rs`, state stored in `src-tauri/src/shell_config.rs`, a system tray (*Open/Collapse assistant* (*Mở/Thu trợ lý*), *Log out* (*Đăng xuất*), *Exit* (*Thoát*)), and IPC commands in `src-tauri/src/lib.rs`.
   - The release executable `.exe` is packaged with `#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]` (no console window).
4. **Real-data initialization and background services:**
   - The scripts `scripts/seed_local_runtime.py` and `scripts/start-local-stack.ps1` initialize automatically on PostgreSQL 18.6 (`127.0.0.1:55432`):
     - 4 standard accounts (`admin`, `curator`, `reviewer`, `chuyenvien`).
     - 1 category (`PHAP_QUY_CHINH_PHU` — Government normative administrative documents (Văn bản quy phạm Chính phủ)).
     - 10 AI Model Registry profiles (6 local AI + 4 cloud APIs) and 12 routes across the 6 RAG stages.
     - 3 Decrees (Nghị định) with an original text layer (`351/2026/NĐ-CP`, `355/2026/NĐ-CP`, `385/2026/NĐ-CP`) that have gone through the full flow of `CURATOR` submitting for review and `REVIEWER` approving, so they can be looked up and the cited PDF opened immediately.
     - 9 scanned Decrees (Nghị định) in the `draft` queue, with open review tasks, for testing the approval workflow on the Admin Portal.

## 2. Tests and real measurements

- **Automated suite `scripts/verify.ps1` (`docs/evidence/2026-10-22-full-verification/summary.json`):**
  - `12/12` steps reached exit code `0` (`dependency-check`, `backend-lint`, `backend-typing`, `backend-tests`, `source-policy`, `migration-pairs`, `openapi`, `polarity-fixtures`, `temporal-fixtures`, `frontend-lint`, `frontend-tests`, `frontend-build`).
  - Backend: **88 passed, 0 skipped** on real PostgreSQL 18.6.
  - Frontend: **13 passed** (5 Vitest test files), and `vite build` succeeded.
  - Rust (`src-tauri`): **17 passed** (`cargo test`); the compile `cargo build --release --features custom-protocol` exited `0`.
- **End-to-end smoke test on the running system (`docs/evidence/2026-10-22-desktop-native/live-stack-smoke.json`):**
  - `GET http://127.0.0.1:1420/health` → `{"status": "ok", "service": "evidence-rag"}`.
  - Logged in as `chuyenvien` and called `POST /api/v1/query/evidence` for a question about Decree (Nghị định) `351/2026/NĐ-CP` → `status: "evidence_found"`, returning `12` approved evidence items (căn cứ).
  - Opened the evidence (căn cứ) `GET /api/v1/citations/ev_7e20ba2d-6dd2-49b9-b7f8-494a3237c8c4` and downloaded the original PDF `GET /api/v1/citations/ev_7e20ba2d-6dd2-49b9-b7f8-494a3237c8c4/pdf` → `HTTP 200`, `363,260` bytes matching the SHA-256.
  - Logged in as `reviewer` and `admin` and checked a queue of `9` drafts, `4` accounts, and `46` audit events (`audit_chain_valid: true`).
  - The native process `vietnamese-evidence-desktop.exe` started stably and did not open a console window.

## 3. NOT DONE (external dependency gates that cannot be self-validated)

1. **A Gold set of 150–200 cases and domain acceptance:** There is no legal-affairs domain owner to accept 150–200 real Gold/Trap questions.
2. **A real AI model (an API key, or local LLM/embedding/reranker weights):** The system is running in safe verbatim-extraction mode (`answer_generated: false`, `explanation_unavailable: true`, returning only verbatim quotations from approved articles and clauses (điều khoản)). Generating a natural synthesized answer requires a real runtime model configured in the Model Registry.
3. **Acceptance on physical multi-monitor / DPI hardware, and a signed MSI/NSIS package:** Verified with 17 geometry unit tests (`geometry.rs`) and by launching the real `.exe` process on this machine; physical drag-and-drop on mixed-DPI monitors, and code-signing with a release certificate, have not been done.
