# Sản phẩm: Vietnamese Evidence RAG Agent (bản dịch)

**Ngôn ngữ / Language:** Tiếng Việt · bản chuẩn: [`.kiro/steering/product.md`](../../../../.kiro/steering/product.md)

> Bản dịch tham khảo. Steering dựng lại từ mã nguồn và tài liệu dự án ngày 09/11/2026; không phải steering lịch sử của Kiro.

## Mục đích

Tra cứu văn bản pháp lý tiếng Việt có căn cứ. Người dùng hỏi hoặc tìm trong kho đã duyệt và có kiểm soát truy cập, xem đúng đoạn và vị trí, rồi mở tệp gốc. Hệ thống hỗ trợ cán bộ; không tạo thẩm quyền pháp lý, và kết quả AI luôn cần chuyên gia đối chiếu.

## Giao diện

- **User Portal** (web và vỏ Tauri Windows): hỏi đáp có căn cứ, tìm kiếm văn bản, "Diễn giải AI" tùy chọn.
- **Admin Portal**: nhập và duyệt tài liệu, quản lý văn bản, danh mục, tài khoản (RBAC/ABAC), Model Registry, tác vụ embedding, rà soát hiệu lực, nhật ký kiểm toán.

## Vai trò

| Vai trò | Được làm | Không được làm |
|---|---|---|
| `USER` (ví dụ `chuyenvien`) | Hỏi, tìm, mở nguồn được phép | Đọc ngoài ACL |
| `CURATOR` | Nhập tệp, tạo và sửa bản nháp, trích xuất lại, gửi duyệt | Tự duyệt bản nháp của mình |
| `REVIEWER` | Xử lý tác vụ, xác nhận trang OCR, chọn danh mục, duyệt hoặc từ chối, rà soát hiệu lực | Tự duyệt đề xuất của mình; duyệt khi thiếu `can_review` trên một danh mục đã gán |
| `SYS_ADMIN` (`admin`) | Danh mục, tài khoản, vai trò, Model Registry, embedding, tạm ngừng hoặc xóa mềm văn bản | Mặc định đọc mọi nội dung hoặc duyệt |
| `AUDITOR` | Xem chức năng kiểm toán theo quyền | Đổi cấu hình AI; đọc mọi tài liệu |

## Quy tắc sản phẩm (không được làm yếu đi)

1. Agent chỉ tham mưu, read-only; không có công cụ ghi hay phê duyệt dữ liệu nghiệp vụ.
2. Người duyệt bản nháp khác người chuẩn bị nó (`SELF_APPROVAL_DENIED`).
3. ACL lọc trong SQL trước khi lấy ứng viên; trích dẫn và tệp được kiểm lại quyền khi mở.
4. Trích dẫn lấy từ `text_original` đã lưu. Model không bao giờ viết trích dẫn, ID nút hay số trang.
5. Tệp nguồn bất biến, định danh theo SHA-256; mã băm được kiểm lại khi mở tệp.
6. Hiệu lực do máy đề xuất không bao giờ được hiển thị là đã xác minh. "Còn hiệu lực + Đã xác minh" chỉ đến từ xác nhận của người.
7. Bộ nhớ phiên nằm trong RAM, không bao giờ là căn cứ, và không phải sao lưu.
8. Gửi dữ liệu ra ngoài bị chặn mặc định; chế độ `LOCAL` từ chối hồ sơ `public`.
9. Không dùng bộ câu hỏi Gold để chấm AI (ADR-010): AI chỉ hỗ trợ, cán bộ chuyên môn quyết định.

## Phạm vi trung thực

Chưa có nghiệm thu nghiệp vụ, và không có kế hoạch xây bộ câu hỏi Gold (ADR-010). Số liệu kiểm thử trong `docs/evidence/` là báo cáo lịch sử, không phải bảo đảm. Không thêm khẳng định về độ chính xác, độ bao phủ hay mức sẵn sàng triển khai mà báo cáo trong repository không hỗ trợ.
