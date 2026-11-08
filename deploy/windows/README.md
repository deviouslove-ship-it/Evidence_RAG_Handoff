# Windows deployment

Các đường dẫn dưới đây là placeholder cấu hình, không phải giá trị nhúng trong source.

1. Owner cấp `installation.programs_root` qua deployment profile hoặc `EVIDENCE_PROGRAMS_ROOT`.
2. Cài runtime/tool/model theo dependency manifest dưới root; không sửa PATH toàn hệ thống.
3. Cấu hình `DATABASE_URL`, data/log/backup root riêng. Để bật API nhập PDF nháp, đặt `EVIDENCE_DOCUMENT_STORE_ROOT` là đường dẫn tuyệt đối của kho tài liệu có quyền truy cập giới hạn; PDF gốc được lưu theo SHA-256 dưới `originals/`. Đây là dữ liệu triển khai, tách khỏi Core và không được đặt cứng trong mã.
4. Áp migration trong maintenance window.
5. Chạy `verify-egress`, smoke test, backup và restore.
6. Đăng ký backend/worker dưới dạng Windows service bằng wrapper từ manifest.

## Gói chạy sẵn (portable) — cách đơn giản nhất để chạy trên máy khác

`scripts/package-portable.ps1 -PackageDirectory <thư mục đích> [-Zip] [-Force] [-SkipBuild]`
tạo một thư mục tự chứa (khoảng 216 MB, 77 MB khi nén) gồm: Python chuyển vị trí được và các
gói của backend (không dùng venv vì venv ghi cứng đường dẫn), PostgreSQL kèm pgvector và
`vcruntime140*.dll`, bản web đã build, mã backend, bộ khởi chạy (`evidence.ps1` +
`start/stop/status/open-firewall/close-firewall.cmd`), `config\evidence.env` và `README.txt`.

- Không có đường dẫn hay IP cứng: mọi đường dẫn tính từ vị trí `evidence.ps1`; địa chỉ truy
  cập dò lúc chạy; cổng/địa chỉ nghe cấu hình trong `evidence.env`. Script đóng gói tự quét
  tệp văn bản và dừng nếu còn đường dẫn của máy phát triển.
- Gói **sạch**: không có cơ sở dữ liệu, tài liệu, tài khoản hay mật khẩu. Lần chạy đầu tạo
  cụm PostgreSQL mới (UTF8, locale C, `scram-sha-256`, chỉ nghe `127.0.0.1`), cơ sở dữ liệu
  `evidence_rag`, mật khẩu ngẫu nhiên (`secrets\postgres.password`), chạy migration và tạo
  bốn tài khoản `admin/curator/reviewer/chuyenvien` với một mật khẩu ban đầu ngẫu nhiên
  (hoặc `-BootstrapPassword`). Không tự duyệt văn bản nào.
- Bộ khởi chạy bỏ qua `PYTHON*`/`PG*` của máy chủ, dùng Python và PostgreSQL trong gói,
  không ghi registry hay thư mục ngoài gói, không cần quyền Administrator (chỉ
  `open-firewall.cmd` cần). Windows PowerShell 5.1 có sẵn trên Windows 10/Server 2016+.
- Đã kiểm chứng (06/11/2026) trên ổ khác, đường dẫn có khoảng trắng, PATH tối thiểu và biến
  môi trường cố ý sai: lần chạy đầu 12–16 s; 30 bước nghiệp vụ qua HTTP đạt (đăng nhập,
  buộc đổi mật khẩu, nạp PDF qua tiến trình con, duyệt, tìm kiếm, hỏi đáp, mở PDF gốc,
  chuỗi kiểm toán); dừng sạch 1 s; chạy lại 4 s và giữ dữ liệu; đổi cổng/địa chỉ nghe có
  tác dụng. **Chưa kiểm:** máy Windows thật sự trống (chưa từng cài Visual C++/cập nhật hệ
  thống), Windows Server, antivirus của máy đích, truy cập từ máy khác qua tường lửa.
- Giới hạn: HTTP không mã hóa; một process; chưa là Windows service; không có OCR
  (Tesseract) trong gói; chưa có ứng dụng desktop trong gói (web qua trình duyệt).

## Chạy thử qua LAN từ máy phát triển (giai đoạn test)

`scripts/start-local-stack.ps1 -Lan [-Port 8000] [-OpenFirewall]` cho phép máy khác trong
mạng nội bộ dùng web qua `http://<IP máy chủ>:<Port>/`:

- Backend nghe `0.0.0.0` và phục vụ `frontend/dist` (biến `EVIDENCE_WEB_ROOT`, đường dẫn
  tuyệt đối tới thư mục có `index.html`, script tự đặt) cùng origin với API; không dùng
  `pnpm dev` và không cần Node trên máy chủ khi đã có `dist`.
- PostgreSQL vẫn chỉ nghe `127.0.0.1`.
- `-OpenFirewall` (cần PowerShell quyền quản trị) tạo quy tắc “Evidence RAG test (TCP port)”
  cho profile Private/Domain, chỉ từ mạng con cục bộ. Gỡ: `Remove-NetFirewallRule -DisplayName "Evidence RAG test (TCP 8000)"`.
- HTTP không mã hóa, chưa có TLS hay reverse proxy; không dùng ngoài mạng test tin cậy.
- Giới hạn hiện có: một process, tối đa 64 phiên bộ nhớ (8 mỗi người), 8 lượt hỏi đồng thời,
  4 lượt tìm kiếm DB đồng thời; thừa thì chờ hoặc nhận mã `*_BUSY`.

Chưa có service wrapper hoặc bằng chứng cài sạch trên máy đích; không coi tài liệu này là bằng chứng WP 0.2/4.3.

Để kiểm tra POC trên môi trường dev đã cấp, đặt `EVIDENCE_PROGRAMS_ROOT` hoặc truyền `-ProgramsRoot` rồi chạy `scripts/verify.ps1` từ root repo. Log và giới hạn lần chạy 22/10/2026 ở `docs/evidence/2026-10-22-takeover/REPORT.md`. Script này không triển khai database/service hay đóng gói Tauri.
