# Threat model (P0 baseline)

## Xác thực, Header & CORS

- Xác thực Bearer Token bắt buộc với mọi phiên người dùng và quản trị viên.
- Header định danh nhà phát triển (`X-Principal-Id` và `X-Roles`) chỉ được phép nạp trong cấu hình CORS khi bật cờ POC `DEV_ALLOW_IN_MEMORY_STORE=true`. Trong môi trường chuẩn hoặc production, hai header này bị loại hoàn toàn khỏi CORS allowlist để ngăn ngừa tuyệt đối nguy cơ giả mạo quyền hạn (identity spoofing) từ client.

## Tài liệu và quyền

- ACL phải được áp dụng trong SQL trước lexical/vector/rerank/cache/citation.
- `ALL_AUTHORIZED` được server giải lại theo quyền hiện tại; client không gửi wildcard quyền.
- SYS_ADMIN không mặc nhiên có `rag.query` hoặc quyền đọc nội dung/hội thoại.

## Nguồn ngoài

- URL import chỉ qua domain allowlist đã xác minh; DNS/redirect phải được kiểm lại và private/local network bị chặn.
- Upload kiểm magic bytes, MIME thực, cấu trúc PDF, quota và SHA-256 trước khi tạo version bất biến.

## LLM, Runtime và Egress

- Remote route fail-closed. Local Mode không fallback remote.
- Secret không bao giờ đi vào source code, prompt, log hoặc response.
- Khóa API nhập trên Admin Portal được ghi một lần vào kho khóa mã hóa (`secret:<tên>`, Windows DPAPI, thư mục `EVIDENCE_SECRET_STORE_DIR`), gắn với tài khoản Windows chạy máy chủ; khóa không được trả lại qua API, không vào DB, nhật ký kiểm toán hay log. Khóa nhập đi qua HTTP tới máy chủ; trên mạng LAN không TLS cần cân nhắc rủi ro này hoặc dùng `env:`.
- `secret_ref` chỉ cho phép cú pháp `env:KEY_NAME` hoặc `secret:<tên>` (kho khóa ở trên) và áp dụng blacklist chặn các biến môi trường hệ thống (`DATABASE_URL`, mật khẩu kết nối DB, token nội bộ).
- Log lỗi kết nối mô hình được làm sạch (redacted), chỉ ghi lại mã lỗi hoặc tên lớp ngoại lệ, không lộ thông tin endpoint hay header xác thực.
- Quá trình chọn căn cứ qua AI được bảo vệ bởi timeout riêng (70% query timeout); khi xảy ra nghẽn, trễ hoặc lỗi mạng, hệ thống tự động suy thoái mềm (graceful degradation) mà không làm sập hoặc nghẽn luồng truy vấn.
- Nội dung PDF được đưa vào vùng dữ liệu, không phải chỉ dẫn.

## Bộ nhớ và xóa

- Incognito chỉ RAM, TTL cấu hình; không ghi nội dung vào DB/log/cache bền.
- Khi người dùng đăng xuất hoặc chuyển trang, frontend gửi tín hiệu hủy session và xóa RAM ngay lập tức.
- Xóa từng mục bộ nhớ làm mất hiệu lực các lượt cũ để bảo đảm tính toàn vẹn ngữ cảnh.
- Hết TTL hoặc phiên bị xóa, luồng SSE gửi sự kiện lỗi tường minh (`turn_error: SESSION_EXPIRED`) thay vì ngắt im lặng.
- Restore phải phát lại sổ xóa trước khi mở dịch vụ.

## Tạm chưa đóng

- Chưa có kiểm thử tấn công tích hợp trên Windows đích, firewall rule hiệu dụng, secret scanner, CSP production hoặc bằng chứng restore sạch.
