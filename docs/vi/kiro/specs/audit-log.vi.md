# Spec: Nhật ký kiểm toán chuỗi băm, bản dịch

**Ngôn ngữ / Language:** Tiếng Việt · bản chuẩn: [`.kiro/specs/audit-log/`](../../../../.kiro/specs/audit-log/)

> Spec dựng lại từ mã nguồn đã triển khai ngày 09/11/2026 (`Spec reconstructed from the implemented code on 2026-11-09`). Không phải spec lịch sử do Kiro tạo.

## Giới thiệu
Các thay đổi đặc quyền được ghi vào một chuỗi chống sửa mà kiểm toán viên có thể xác minh.

## Yêu cầu (EARS)

**Y1. Ghi cùng thay đổi.**
1. WHEN có thay đổi đặc quyền THE SYSTEM SHALL thêm một dòng `audit_events` trong giao dịch của bên gọi, để thay đổi và nhật ký cùng commit (`audit.py::append_audit`).
2. THE SYSTEM SHALL tuần tự hóa việc ghi bằng khóa advisory của PostgreSQL.

**Y2. Toàn vẹn chuỗi.**
1. THE SYSTEM SHALL tính mã băm mỗi sự kiện bằng SHA-256 trên mã băm trước, tài khoản, hành động, loại và ID đích, metadata và thời điểm (`audit.py::_event_hash`).
2. WHEN xác minh chuỗi THE SYSTEM SHALL báo `valid`, `checked`, `broken_at`, `complete` (`verify_audit_chain`).
3. IF số sự kiện vượt giới hạn xác minh (mặc định 10.000) THEN THE SYSTEM SHALL báo hợp lệ là không xác định (`null`) thay vì hợp lệ.

**Y3. Truy cập.**
1. WHEN người có quyền mở màn hình kiểm toán THE SYSTEM SHALL trả các sự kiện gần đây (1 đến 500) và kết quả chuỗi (`GET /api/v1/admin/audit-events`).
2. THE SYSTEM SHALL KHÔNG suy ra quyền kiểm toán từ vai trò quản trị khác.

**Y4. Nội dung được ghi.**
1. THE SYSTEM SHALL ghi quản trị (tài khoản, danh mục, model registry, tác vụ embedding), vòng đời văn bản (duyệt, trạng thái tra cứu, sửa metadata và OCR), quyết định hiệu lực và lỗi xử lý như `EFFECTIVITY_PROCESSING_FAILED`.
2. THE SYSTEM SHALL KHÔNG ghi mật khẩu hay khóa API vào metadata sự kiện.

## Thiết kế (tóm tắt)

| Mối quan tâm | Tệp |
|---|---|
| Ghi và xác minh | `backend/app/audit.py` |
| API đọc | `api/v1/admin.py` (`GET /audit-events`), `admin_services.py` |
| Lược đồ | migration `0001_core.sql` (`audit_events`) |
| Giao diện | tab "Nhật ký Kiểm toán" của trang Mô hình AI & Kiểm toán (`AdminPortal.tsx`) |

Luồng: thay đổi đặc quyền → cùng giao dịch DB → `pg_advisory_xact_lock` → đọc `event_hash` cuối → SHA-256 của mã băm trước + các trường → `INSERT audit_events`. Thời điểm lấy từ `clock_timestamp()` của cơ sở dữ liệu. JSON chuẩn tắc (`sort_keys`, dấu phân cách gọn, `ensure_ascii=False`) giúp mã băm tái lập được. Xác minh duyệt theo `event_order` và tính lại từng mã băm.

Giới hạn: chuỗi phát hiện việc sửa dòng đã lưu nhưng tự nó không ngăn chủ cơ sở dữ liệu viết lại cả chuỗi. Repository không có cơ chế neo mã băm đầu ra bên ngoài.

## Tasks
- [x] 1. Bảng `audit_events` với `previous_hash`, `event_hash`, `event_order`
- [x] 2. Ghi trong giao dịch với khóa advisory
- [x] 3. Xác minh chuỗi, cờ cắt bớt
- [x] 4. API trả sự kiện và trạng thái chuỗi
- [x] 5. Tab kiểm toán trong Admin Portal
- [ ] 6. Neo mã băm đầu chuỗi ra bên ngoài (chưa có)
- [ ] 7. Tác vụ định kỳ xác minh toàn chuỗi vượt cửa sổ 10.000 sự kiện (chưa có)
