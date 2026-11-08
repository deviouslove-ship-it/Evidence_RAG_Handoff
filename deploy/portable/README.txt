EVIDENCE RAG - BẢN CHẠY DI ĐỘNG (không cần cài đặt)
====================================================

Yêu cầu máy chạy
  - Windows 10 / Windows Server 2016 trở lên, 64-bit. Không cần cài Python, PostgreSQL, Node.
  - Không cần quyền Administrator (chỉ cần khi mở tường lửa, xem mục 4).
  - Khoảng 2 GB trống cho gói + dữ liệu. Nên đặt trong thư mục có đường dẫn không dấu,
    không quá dài, ví dụ D:\EvidenceRAG (đường dẫn có khoảng trắng vẫn chạy được).

1. Chạy
  - Chép cả thư mục này sang máy cần chạy (giữ nguyên cấu trúc), vào thư mục rồi bấm đúp
    start.cmd.
  - Lần đầu: tự tạo cơ sở dữ liệu trống (mất vài chục giây), rồi in ra mật khẩu của 4 tài
    khoản khởi tạo và lưu tại secrets\first-login.txt. Mỗi tài khoản bị buộc đổi mật khẩu ở
    lần đăng nhập đầu. Sau khi đổi xong hãy xóa tệp first-login.txt.
  - Cuối lệnh start, chương trình in các địa chỉ dạng http://<IP-máy-này>:8000/ . Gửi địa
    chỉ đó cho người dùng cùng mạng để mở bằng trình duyệt. Địa chỉ được dò lúc chạy, không
    ghi cứng.

2. Tài khoản khởi tạo (cùng một mật khẩu ban đầu)
  admin       quản trị hệ thống, danh mục, tài khoản, cấu hình AI, nhật ký kiểm toán
  curator     nạp PDF, tạo và gửi bản nháp
  reviewer    thẩm định và duyệt văn bản (người khác curator)
  chuyenvien  hỏi đáp và tìm kiếm
  Hệ thống chưa có văn bản nào được duyệt: hỏi đáp/tìm kiếm chỉ có kết quả sau khi curator
  nạp PDF và reviewer duyệt (gắn danh mục cho người dùng).

3. Dừng / xem trạng thái
  stop.cmd     dừng máy chủ web và cơ sở dữ liệu (dữ liệu giữ nguyên trong thư mục data)
  status.cmd   xem đang chạy hay không và các địa chỉ truy cập

4. Cho máy khác trong mạng truy cập
  - Nếu máy khác không mở được địa chỉ: bấm chuột phải open-firewall.cmd > Run as
    administrator (chạy một lần). Quy tắc chỉ cho phép từ cùng mạng con và các mạng
    Private/Domain. Gỡ bằng close-firewall.cmd (cũng cần Administrator).
  - Chỉ dùng trong mạng tin cậy: kết nối là HTTP, chưa mã hóa.
  - Chỉ cho máy này truy cập: đặt EVIDENCE_LISTEN_HOST=127.0.0.1 trong config\evidence.env.

5. Cấu hình
  config\evidence.env: địa chỉ nghe, cổng, chế độ AI (LOCAL/API), giới hạn. Sửa xong thì
  stop.cmd rồi start.cmd. Hồ sơ model AI cấu hình trong Admin Portal; khóa API đặt theo
  hướng dẫn trong evidence.env (không lưu khóa trong cơ sở dữ liệu).

5a. Đổi hoặc nâng cấp model embedding (tìm theo nghĩa) - không cần lệnh hay sửa mã
  - Admin Portal > Mô hình AI > 1. Hồ sơ Mô hình: chọn vai trò "Tạo vector (embedding)",
    nhập địa chỉ dịch vụ (API tương thích OpenAI, ví dụ máy chủ model chạy trên máy này),
    tên model, phê duyệt, lưu.
  - Mục "Embedding (tìm theo nghĩa)": chọn hồ sơ > Kiểm tra model (kết nối, model, số chiều,
    chính sách dữ liệu, số nút cần tạo) > xác nhận. Việc tạo vector chạy nền trong máy chủ,
    có tiến độ, tạm dừng / tiếp tục / thử lại, tự chạy tiếp sau khi khởi động lại (khoảng 1
    phút sau khi máy chủ lên).
  - Trong lúc tạo, tìm kiếm vẫn dùng model và chỉ mục cũ. Khi xong, hệ thống kiểm tra toàn
    vẹn rồi mới chuyển; nếu lỗi thì giữ chỉ mục cũ. Chỉ mục và vector cũ được giữ lại.
  - Không cần nhập lại PDF/Word/TXT: vector được tạo từ các Điều/Khoản/Điểm đã duyệt.

6. Sao lưu và chuyển sang máy khác
  - Dữ liệu nằm trong data\ (cơ sở dữ liệu + kho PDF) và secrets\ (mật khẩu DB).
  - Dừng bằng stop.cmd, rồi chép cả thư mục. Muốn chuyển sang máy mới nhưng GIỮ dữ liệu:
    chép nguyên thư mục. Muốn bắt đầu SẠCH: chép thư mục nhưng xóa data\, secrets\, logs\,
    run\, cache\ trước khi chạy.
  - secrets\ chứa mật khẩu cơ sở dữ liệu: không chia sẻ thư mục này.

7. Gặp sự cố
  - Xem logs\backend.err.log, logs\postgres.log, logs\seed.err.log.
  - Báo "port in use": đổi EVIDENCE_HTTP_PORT hoặc EVIDENCE_PG_PORT trong config\evidence.env.
  - Diệt phần mềm/antivirus chặn: cho phép thư mục runtime\ chạy.
  - Gói tải từ internet/email về bị Windows chặn (SmartScreen, "blocked"): mở PowerShell trong
    thư mục gói rồi chạy: Get-ChildItem -Recurse | Unblock-File . Chép qua ổ USB/mạng nội bộ thì
    không bị chặn.
  - Máy rất cũ báo thiếu DLL "api-ms-win-crt": cài bản cập nhật Universal C Runtime của
    Windows (Windows 10/Server 2016 trở lên đã có sẵn).

AI MODELS AND API KEYS (Admin Portal > Mô hình AI & Kiểm toán)
- 1. Mô hình AI: separate forms for AI Local and AI API; "Kiểm tra kết nối" tests the
  connection and the model before saving. 2. Phân công AI: assign a model to each function.
- An API key typed in the AI API form is stored encrypted (Windows DPAPI, bound to the
  Windows account running the server) in secrets\ai-keys; it is never shown again. If the
  server account changes, enter the keys again. Back up secrets\ai-keys with the data only
  if the same account will restore it.
- The typed key travels to the server over HTTP; on a LAN without TLS prefer env:NAME
  (Nâng cao) or use the form on the server machine itself.

OCR FOR SCANNED PDF (optional, not included)
- Copy Tesseract 5 (tesseract.exe, its DLLs and tessdata with vie, eng, osd) to
  runtime\tesseract\ and restart; or set EVIDENCE_OCR_EXECUTABLE in config\evidence.env.
- It runs offline. OCR text becomes evidence only after a reviewer confirms each page
  against the scan in Admin Portal > Duyệt nguồn. The scan itself stays the original.
