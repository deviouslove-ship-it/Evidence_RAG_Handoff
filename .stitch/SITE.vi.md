**Ngôn ngữ / Language:** [English](SITE.md) · Tiếng Việt

# Evidence RAG — Sơ đồ màn hình và phân cấp

## Màn hình
1. **Không gian căn cứ của người dùng (`surface = "user"`)**
   - Khung trái: lịch sử hội thoại, chip gợi ý nhanh, bộ chọn phạm vi và ngày hiệu lực, ô soạn được ghim.
   - Khung giữa: thẻ căn cứ đã được cấp quyền, kèm trích dẫn nguyên văn, huy hiệu trạng thái hiệu lực, và mở trang PDF bằng một lần bấm.
   - Khung phải: trình xem PDF trong iframe đã kiểm mã băm (`#page=N`) và thẻ đối chiếu trích dẫn nguyên văn.
2. **Cổng quản trị (`surface = "admin"`)**
   - Tab 1 (`documents`): CURATOR nạp bản nháp PDF và hàng đợi REVIEWER phê duyệt/từ chối.
   - Tab 2 (`categories`): quản lý danh mục văn bản và chính sách gửi dữ liệu ra AI từ xa.
   - Tab 3 (`users`): tài khoản, vai trò RBAC và quyền danh mục ABAC.
   - Tab 4 (`ai_audit`): Model Registry, định tuyến giai đoạn, và kiểm tra nhật ký kiểm toán chuỗi băm.
3. **Đăng nhập và hộp thoại bắt buộc đổi mật khẩu (`LoginPanel`)**
   - Lớp phủ hộp thoại căn giữa (`position: fixed; inset: 0`).
4. **Tiện ích trợ lý chat nổi (`ChatAgentDock`) và Orb desktop gốc (`DesktopOrb`)**
   - Nút mở Trợ lý chat luôn ở góc dưới bên phải, kèm ngăn hỏi nhanh có thể mở rộng.
   - Cửa sổ nổi tròn Tauri `#/orb` kích thước 72x72.
