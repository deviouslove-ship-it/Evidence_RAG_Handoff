# Báo cáo Triển khai & Kiểm chứng Thực tế (Full Stack + Desktop Native)

Ngày thực hiện: `2026-10-22`

## 1. Đã làm

1. **Xác thực cục bộ, RBAC/ABAC, Tách biệt nhiệm vụ (CURATOR / REVIEWER) và Chuỗi băm Audit:**
   - Triển khai migration `backend/app/migrations/0002_auth_admin.sql` (cùng bản rollback `.down.sql`) và bộ chạy migration tự động `backend/app/migrations/runner.py`.
   - Băm mật khẩu bằng `hashlib.scrypt` (`backend/app/auth_acl/passwords.py`), quản lý phiên đăng nhập PostgreSQL, khóa tài khoản sau 5 lần sai liên tiếp, buộc đổi mật khẩu (`PASSWORD_CHANGE_REQUIRED`) tại `backend/app/auth_acl/service.py` và `backend/app/api/v1/auth.py`.
   - Luồng duyệt nguồn tách biệt nhiệm vụ tại `backend/app/documents/review.py`: `CURATOR` tạo nháp và gửi duyệt (`submit_draft_for_review`); `REVIEWER` giải quyết tác vụ rà soát và phê duyệt/từ chối (`approve_document_version`, chặn tự duyệt `SELF_APPROVAL_DENIED`, chặn duyệt khi còn tác vụ mở `OPEN_REVIEW_TASKS_REMAIN`, kiểm tra lại SHA-256 tệp PDF gốc trên đĩa, đóng dấu `source_provenance.verified_at`, gắn danh mục ACL và duyệt các node/span).
   - Nhật ký kiểm toán chuỗi băm bất biến (`audit_events`) với khóa giao dịch `pg_advisory_xact_lock` và hàm kiểm tra tính toàn vẹn chuỗi (`verify_audit_chain`) tại `backend/app/audit.py`.
2. **Admin Portal & User Workspace (Web + Desktop UI):**
   - Giao diện đăng nhập và đổi mật khẩu bắt buộc (`frontend/src/components/LoginPanel.tsx`), kèm nút **Đổi mật khẩu** trực tiếp trên thanh công cụ Topbar (`frontend/src/App.tsx`) cho mọi tài khoản đang hoạt động.
   - Không gian tra cứu Evidence-first (`frontend/src/pages/EvidenceChat.tsx`, `frontend/src/components/PdfViewer.tsx`):
     - Bố cục 2 cột khoa học: **Cột trái** hiển thị nhóm căn cứ pháp lý đã duyệt và trình xem PDF gốc đúng trang qua `Blob` URL; **Cột phải** là khung chat **Tra cứu có căn cứ**.
     - Chuẩn hóa truy vấn tiếng Việt tự nhiên (`backend/app/storage/authorized_search.py`), loại bỏ hư từ nghi vấn khi tìm kiếm FTS.
     - **Bộ nhớ phiên tạm thời (Session Ephemeral Memory)**: trích xuất dữ kiện đa lượt (`FactChips`), quản lý RAM có khóa luồng `threading.RLock`, nút xóa phiên làm mới bộ nhớ.
   - Cổng quản trị Admin Portal (`frontend/src/pages/AdminPortal.tsx`) gồm 4 phân khu hoàn chỉnh:
     - **Tài liệu & Duyệt nguồn** (`CURATOR` / `REVIEWER`): Tải nháp, gửi duyệt, phê duyệt/từ chối tách biệt nhiệm vụ.
     - **Danh mục** (`SYS_ADMIN`): Thêm mới (kèm 3 mẫu nhanh), sửa và xóa mềm danh mục (`DELETE /api/v1/admin/categories/{category_id}`) kèm thu hồi ACL và lưu Audit log.
     - **Tài khoản & ACL** (`SYS_ADMIN`): Thêm tài khoản mới, phân quyền RBAC/ABAC, đổi/đặt lại mật khẩu, khóa/mở khóa tài khoản, xóa tài khoản (`DELETE /api/v1/admin/users/{user_id}`, chặn tự xóa `CANNOT_DELETE_SELF`) và đổi mật khẩu cá nhân.
     - **Mô hình AI & Kiểm toán** (`SYS_ADMIN` / `AUDITOR`): Kiến trúc đa mô hình 6 giai đoạn (`analyze`, `embedding`, `rerank`, `answer`, `verify`, `ocr`) với 10 hồ sơ mô hình (6 AI Local + 4 Cloud API), giao diện 3 tab con trực quan, ẩn trường `Revision` dư thừa và kiểm tra tính toàn vẹn chuỗi băm Audit.
3. **Ứng dụng Windows Native Desktop USER (`src-tauri/`):**
   - Cấu hình 2 cửa sổ trong `src-tauri/tauri.conf.json`:
     - `main`: cửa sổ nền đục (`transparent: false`, `decorations: true`, `1180x780`, `minWidth: 360`, `minHeight: 520`) cho đăng nhập, khung chat và xem PDF.
     - `orb`: cửa sổ nổi tròn (`url: index.html#/orb`, `72x72`, `transparent: true`, `decorations: false`, `shadow: false`, `alwaysOnTop: true`, `skipTaskbar: true`) hiển thị sau khi đăng nhập.
   - Hỗ trợ kéo thả mượt mà theo độ lệch con trỏ (`drag_orb_window`), đồng bộ câu hỏi & căn cứ từ Orb sang không gian làm việc chính (`open_evidence_in_workspace`), ẩn hoàn toàn Orb trên Web để tránh thừa.
   - Toán học kẹp tọa độ (`work area` clamping) đa màn hình và tỷ lệ DPI 100%–200% tại `src-tauri/src/geometry.rs`, lưu trạng thái tại `src-tauri/src/shell_config.rs`, khay hệ thống (System Tray: *Mở/Thu trợ lý*, *Đăng xuất*, *Thoát*) và IPC commands tại `src-tauri/src/lib.rs`.
   - Đóng gói thực thi release `.exe` với `#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]` (không hiện cửa sổ console).
4. **Khởi tạo dữ liệu thực & Chạy dịch vụ nền:**
   - Script `scripts/seed_local_runtime.py` và `scripts/start-local-stack.ps1` khởi tạo tự động trên PostgreSQL 18.6 (`127.0.0.1:55432`):
     - 4 tài khoản chuẩn (`admin`, `curator`, `reviewer`, `chuyenvien`).
     - 1 danh mục (`PHAP_QUY_CHINH_PHU` — Văn bản quy phạm Chính phủ).
     - 10 hồ sơ AI Model Registry (6 AI Local + 4 Cloud API) và 12 định tuyến theo 6 giai đoạn RAG.
     - 3 Nghị định có lớp chữ gốc (`351/2026/NĐ-CP`, `355/2026/NĐ-CP`, `385/2026/NĐ-CP`) đã đi qua đủ quy trình `CURATOR` gửi duyệt → `REVIEWER` phê duyệt để tra cứu và mở PDF trích dẫn ngay.
     - 9 Nghị định bản quét (scan) nằm trong hàng đợi `draft` kèm tác vụ rà soát mở để kiểm thử quy trình duyệt trên Admin Portal.

## 2. Test và số đo thực

- **Bộ kiểm tra tự động `scripts/verify.ps1` (`docs/evidence/2026-10-22-full-verification/summary.json`):**
  - `12/12` bước đạt exit code `0` (`dependency-check`, `backend-lint`, `backend-typing`, `backend-tests`, `source-policy`, `migration-pairs`, `openapi`, `polarity-fixtures`, `temporal-fixtures`, `frontend-lint`, `frontend-tests`, `frontend-build`).
  - Backend: **88 passed, 0 skipped** trên PostgreSQL 18.6 thật.
  - Frontend: **13 passed** (5 tệp test Vitest), `vite build` thành công.
  - Rust (`src-tauri`): **17 passed** (`cargo test`), biên dịch `cargo build --release --features custom-protocol` exit `0`.
- **Kiểm thử khói toàn trình trên hệ thống đang chạy (`docs/evidence/2026-10-22-desktop-native/live-stack-smoke.json`):**
  - `GET http://127.0.0.1:1420/health` → `{"status": "ok", "service": "evidence-rag"}`.
  - Đăng nhập `chuyenvien`, gọi `POST /api/v1/query/evidence` cho câu hỏi về Nghị định `351/2026/NĐ-CP` → `status: "evidence_found"`, trả về `12` căn cứ đã duyệt.
  - Mở căn cứ `GET /api/v1/citations/ev_7e20ba2d-6dd2-49b9-b7f8-494a3237c8c4` và tải PDF gốc `GET /api/v1/citations/ev_7e20ba2d-6dd2-49b9-b7f8-494a3237c8c4/pdf` → `HTTP 200`, `363,260` bytes khớp SHA-256.
  - Đăng nhập `reviewer` và `admin` kiểm tra hàng đợi `9` bản nháp, `4` tài khoản và `46` sự kiện kiểm toán (`audit_chain_valid: true`).
  - Tiến trình native `vietnamese-evidence-desktop.exe` khởi chạy ổn định, không mở cửa sổ console.

## 3. CHƯA XONG (Các cổng phụ thuộc bên ngoài không tự hợp thức hóa)

1. **Bộ dữ liệu Gold 150–200 ca & Duyệt nghiệp vụ:** Chưa có người nắm nghiệp vụ pháp chế nghiệm thu 150–200 câu hỏi Gold/Trap thực tế.
2. **Model AI thực (API key hoặc trọng số Local LLM/Embedding/Reranker):** Hệ thống đang chạy ở chế độ trích xuất nguyên văn an toàn (`answer_generated: false`, `explanation_unavailable: true`, chỉ trả trích dẫn nguyên văn từ các điều khoản đã duyệt). Để sinh câu trả lời tổng hợp tự nhiên cần cấu hình runtime model thực vào Model Registry.
3. **Nghiệm thu phần cứng đa màn hình / DPI vật lý & đóng gói MSI/NSIS ký số:** Đã kiểm chứng bằng 17 unit test hình học (`geometry.rs`) và khởi chạy tiến trình `.exe` thật trên máy; chưa thực hiện thao tác kéo thả vật lý trên nhiều màn hình DPI hỗn hợp hoặc ký số chứng thư phát hành.
