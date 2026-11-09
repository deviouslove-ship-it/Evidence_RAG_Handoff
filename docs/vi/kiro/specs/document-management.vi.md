# Spec: Quản lý văn bản (Admin Portal), bản dịch

**Ngôn ngữ / Language:** Tiếng Việt · bản chuẩn: [`.kiro/specs/document-management/`](../../../../.kiro/specs/document-management/) (`requirements.md`, `design.md`, `tasks.md`)

> Spec dựng lại từ mã nguồn đã triển khai ngày 09/11/2026 (`Spec reconstructed from the implemented code on 2026-11-09`). Không phải spec lịch sử do Kiro tạo; không có phiên spec nào của Kiro cho dự án này. Bằng chứng được dẫn theo đường dẫn trong repository.

## Giới thiệu
Admin Portal cho phép nhân sự được cấp quyền liệt kê, xem, sửa, tạo phiên bản mới, tạm ngừng và xóa mềm văn bản mà không làm hỏng tra cứu của người dùng hay mất tệp nguồn.

## Yêu cầu (EARS)

**Y1. Liệt kê, tìm và lọc.**
1. WHEN người dùng được phép mở "Quản lý văn bản" THE SYSTEM SHALL trả danh sách phân trang (`GET /api/v1/admin/documents`, `documents/management_read.py::list_documents`).
2. WHEN tìm theo số hiệu hoặc trích yếu THE SYSTEM SHALL khớp không phân biệt dấu.
3. WHEN áp dụng bộ lọc (loại, cơ quan, khoảng ngày, trạng thái xử lý, hiệu lực, trạng thái tra cứu, đã xóa) THE SYSTEM SHALL chỉ trả văn bản khớp.
4. IF người dùng không phải SYS_ADMIN THEN THE SYSTEM SHALL giới hạn theo ACL danh mục hoặc ACL văn bản (`management_access.py`).

**Y2. Chi tiết văn bản.**
1. WHEN mở một văn bản THE SYSTEM SHALL hiển thị metadata, danh mục, lịch sử phiên bản và lịch sử xử lý (`management_read.py::detail`).
2. WHEN người dùng có quyền đọc THE SYSTEM SHALL cung cấp tệp gốc bất biến và trang OCR sau khi kiểm lại quyền, phiên bản và SHA-256 (`management_read.py::original`).
3. WHEN người dùng thiếu quyền nội dung THE SYSTEM SHALL chỉ hiển thị metadata nếu vai trò cho phép và KHÔNG để lộ nội dung hay tệp gốc.

**Y3. Sửa bản đã duyệt.**
1. WHEN CURATOR sửa metadata hoặc chữ OCR của bản đã duyệt THE SYSTEM SHALL tạo bản nháp mới dùng lại tệp gốc bất biến (`management_write.py::change_version`).
2. WHILE bản mới chờ duyệt THE SYSTEM SHALL tiếp tục phục vụ bản đã duyệt trước đó nếu văn bản đang hoạt động và người dùng được phép.
3. WHEN bản mới được duyệt THE SYSTEM SHALL rút phiên bản trước của cùng tệp khỏi tra cứu và giữ trong lịch sử.
4. WHEN sửa chữ OCR một trang THE SYSTEM SHALL yêu cầu xác nhận lại từng trang đã sửa và lưu chữ OCR trước/sau khi sửa.
5. IF số phiên bản rà soát gửi lên đã cũ THEN THE SYSTEM SHALL từ chối để người dùng tải lại.

**Y4. Thêm phiên bản từ tệp mới.**
1. WHEN CURATOR thêm PDF, Word hoặc TXT vào văn bản đã có THE SYSTEM SHALL chạy luồng nhập chuẩn và tạo phiên bản nháp của cùng văn bản.
2. WHEN phiên bản được duyệt THE SYSTEM SHALL cho tra cứu từ ngày ban hành đã xác nhận, hoặc ngày duyệt nếu thiếu ngày ban hành.

**Y5. Tách biệt nhiệm vụ khi duyệt.**
1. WHEN bản nháp được gửi duyệt THE SYSTEM SHALL chỉ cho REVIEWER khác duyệt hoặc từ chối.
2. IF reviewer thiếu `can_review` trên bất kỳ danh mục đã gán THEN THE SYSTEM SHALL từ chối phê duyệt.
3. IF danh mục thay đổi trong lúc duyệt bản sửa THEN THE SYSTEM SHALL từ chối để reviewer tải lại.

**Y6. Tạm ngừng, xóa mềm, khôi phục.**
1. WHEN SYS_ADMIN gửi `POST /api/v1/admin/documents/actions` kèm lý do THE SYSTEM SHALL tạm ngừng tra cứu, khôi phục tra cứu, xóa mềm hoặc khôi phục các văn bản đã chọn (`management_write.py::change_availability`).
2. THE SYSTEM SHALL giữ tệp nguồn, vector, danh mục và lịch sử của văn bản bị tạm ngừng hoặc xóa mềm.
3. WHEN khôi phục văn bản đã xóa THE SYSTEM SHALL giữ hiệu lực của cờ tạm ngừng trước đó.
4. THE SYSTEM SHALL coi trạng thái tra cứu độc lập với hiệu lực pháp lý.

**Y7. Hiển thị giữa các tiến trình.**
1. WHEN trạng thái tra cứu thay đổi THE SYSTEM SHALL tăng bộ đếm phiên bản tra cứu (migration `0016_document_management.sql`, `storage/lookup_visibility.py`).
2. WHEN một tiến trình backend thấy bộ đếm đổi THE SYSTEM SHALL làm hết hạn bộ kết quả cũ; hỏi đáp, tìm kiếm, Diễn giải AI và API trích dẫn SHALL kiểm lại khả năng truy cập.

**Y8. Kiểm toán.**
1. WHEN metadata, chữ OCR, trạng thái tra cứu hoặc phê duyệt thay đổi THE SYSTEM SHALL ghi sự kiện kiểm toán chuỗi băm trong cùng giao dịch (`audit.py::append_audit`).

## Thiết kế (tóm tắt)

| Tầng | Tệp |
|---|---|
| API | `backend/app/api/v1/admin.py` (`/documents`, `/documents/{id}`, `/documents/actions`, `.../original`) |
| Đọc | `documents/management_read.py` |
| Ghi | `documents/management_write.py` |
| Truy cập | `documents/management_access.py` |
| Hiển thị tra cứu | `storage/lookup_visibility.py`, migration `0016` |
| Giao diện | `frontend/src/pages/AdminPortal.tsx`, `components/AdminDocumentManager.tsx`, `AdminDocumentDetail.tsx` |

Quyết định: bản sửa không bao giờ thay đổi bản đã duyệt (`_new_revision` sao metadata sang bản nháp mới trỏ cùng tệp gốc `originals/<sha256>.pdf`). Thao tác vòng đời, người sửa và reviewer lấy khóa dòng văn bản trước (`lock_review_version`). Số phiên bản rà soát phát hiện màn hình cũ. Trạng thái tra cứu (`suspended`, `deleted`) không xóa vector hay tệp. Lỗi (bản cũ, đổi danh mục khi duyệt, thiếu quyền) trả mã 4xx để giao diện yêu cầu tải lại.

Test hiện có: `backend/tests/test_document_management.py`, `test_lookup_visibility.py`, `frontend/src/pages/AdminDocuments.test.tsx`.

## Tasks
- [x] 1. Migration `0016_document_management` (trường quản lý, bộ đếm hiển thị tra cứu) có tệp down
- [x] 2. Quy tắc truy cập theo ACL danh mục/văn bản
- [x] 3. Đường đọc: danh sách, bộ lọc, chi tiết, tệp gốc
- [x] 4. Đường ghi: bản mới từ chỉnh sửa, sửa trang OCR, thao tác trạng thái tra cứu
- [x] 5. Route API quản trị
- [x] 6. Làm mới cache giữa tiến trình
- [x] 7. Giao diện Admin Portal
- [x] 8. Test backend và frontend đã có
- [ ] 9. Bộ chọn nút đích cho quan hệ cấp khoản chưa ghép được (hướng dẫn nêu là chưa có)
- [ ] 10. Chạy `scripts/verify.ps1` độc lập cho commit quản lý văn bản ngày 09/11 (`ba596ce`) và ghi vào `docs/evidence/` (chưa có trong repository)
