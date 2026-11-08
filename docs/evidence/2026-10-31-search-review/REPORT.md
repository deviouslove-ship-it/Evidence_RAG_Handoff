# Rà soát và sửa Search v1 — 31/10/2026

Phạm vi: trang tìm kiếm mới, API `/search` và `/search/approximate`, phân trang,
kiểm tra đầu vào và tách các tầng kết quả. Search v1 dùng PostgreSQL FTS theo
ADR-005, không gọi mô hình AI. Không thay đổi Registry/Router hay nội dung chứng cứ.

## Lỗi đã tái hiện và sửa

| Lỗi | Nguyên nhân | Sau sửa |
|---|---|---|
| Tải thêm khoản sau khi sửa ô tìm kiếm trộn kết quả của hai câu hỏi | Phân trang đọc form đang sửa | Dùng truy vấn thành công gần nhất; giữ nguyên nội dung đang nhập |
| Tải thêm gặp lỗi rồi bấm lại bỏ qua một trang khoản | Tăng trang trước khi nhận kết quả | Chỉ ghi nhận trang thành công; lần sau yêu cầu lại trang bị lỗi |
| Mở URL có `clause_page>1` mất các khoản đầu | Buffer khoản chỉ tồn tại trong RAM | Khi mở lại trang, bắt đầu từ cửa sổ khoản đầu, giữ câu hỏi và bộ lọc |
| Kết quả gần đúng chứa cả khoản khớp đủ từ/cụm từ | Truy vấn lấy kết quả thiếu điều kiện loại trừ của truy vấn đếm | Hai truy vấn dùng chung điều kiện lọc; kết quả khớp đầy đủ không bị gắn `any_term` |
| Cụm từ trong ngoặc kép dài hơn 200 ký tự lọt giới hạn | Regex không nhận cụm từ quá dài và chuyển sang keywords | Nhận diện cụm từ trước, trả `QUERY_TOO_LONG` đúng quy tắc |
| Có kết quả một phần nhưng giao diện không cho mở khi kết quả chính rỗng | Mục gần đúng nằm trong điều kiện có document chính | Mục gần đúng độc lập với danh sách kết quả chính |
| Không thể yêu cầu gần đúng khi backend bỏ qua bước đếm tùy chọn | Giao diện chỉ hiện nút nếu số đếm lớn hơn 0 | Luôn cho yêu cầu theo nhu cầu; chưa có số đếm thì không ghi “0 khoản” |
| Tổng gần đúng thấp hơn danh sách thực tế khi chạm trần đếm gợi ý | Endpoint chi tiết dùng lại trần đếm gợi ý | Tổng và cờ `capped` mô tả tập ứng viên thực tế; bỏ một truy vấn đếm thừa |
| Không xem được văn bản gần đúng sau trang đầu | Thiếu điều khiển phân trang; tải thêm khoản luôn gửi `page=1` | Thêm Trước/Sau theo quy ước hiện hữu; tải thêm khoản giữ đúng trang văn bản gần đúng |
| Không mở được PDF của kết quả gần đúng khi danh sách chính rỗng | Viewer nằm trong điều kiện có document chính | Tái sử dụng viewer hiện hữu cho trường hợp chỉ có kết quả gần đúng |

Các ca hồi quy được chạy trước khi sửa và thất bại đúng lỗi tương ứng. Test
PostgreSQL bổ sung cả kiểm tra principal không có quyền không nhận được kết quả
hay tổng số gần đúng.

## Kiểm chứng

- Chạy `scripts/verify.ps1` với `EVIDENCE_TEST_DATABASE_URL`: 12/12 bước đạt.
- Backend: 188 test đạt, không skip PostgreSQL; 1 cảnh báo deprecated của thư viện
  Starlette/AnyIO, không phải lỗi kiểm thử.
- Frontend: 72 test đạt; lint và build đạt. Bộ kiểm tra hiện hữu bao gồm contrast,
  accessibility, Local Mode và liên kết từ chat sang tìm kiếm.
- Chrome headless E2E hiện hữu đạt: đăng nhập giả lập, tìm cụm từ, tải thêm khoản,
  mở gần đúng, mở PDF fixture; không có HTTP(S) request ra ngoài origin cục bộ.
- Log: `verification/summary.json`, các log trong `verification/`,
  `browser-e2e.json.log`. Các log `approximate-*-red.txt` ghi nhận lỗi trước sửa.

## Giới hạn bằng chứng

- E2E trình duyệt dùng API/PDF fixture; kiểm thử DB dùng schema riêng và dữ liệu
  HƯ CẤU, tự xóa schema sau khi chạy. Chưa nghiệm thu độ đúng của tìm kiếm trên
  văn bản nghiệp vụ đã duyệt hay chất lượng lựa chọn căn cứ của mô hình AI thật.
- Không đo lại benchmark tải 100.000 node hoặc p95 trong đợt sửa này.
- Giới hạn ứng viên hiện hữu là 5.000. Endpoint gần đúng đánh dấu `capped` khi
  chạm ngưỡng; tổng số khi đó là tổng trong tập ứng viên, không phải toàn kho.
- Khi mở lại URL, cửa sổ khoản bắt đầu lại từ đầu; không phục dựng buffer cũ.
- Đã build frontend; chưa đóng gói/phát hành lại ứng dụng Tauri Windows.
- Lần chạy đầu gặp PostgreSQL cục bộ đang tắt (`ConnectionRefusedError`). Đã khởi
  động PostgreSQL dev và chạy lại kiểm thử thật; đây là điều kiện môi trường,
  không bị ghi nhận thành lỗi mã tìm kiếm.

## File mã thay đổi

- `backend/app/storage/search.py`
- `backend/tests/test_search_parser.py`
- `backend/tests/test_search_postgres.py`
- `frontend/src/pages/SearchPage.tsx`
- `frontend/src/pages/SearchPage.test.tsx`
