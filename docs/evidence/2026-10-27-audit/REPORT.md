# Kết quả rà soát kỹ thuật ngày 27/10/2026

## Thay đổi

- Bộ nhớ phiên: xóa từng dữ kiện thực sự ở máy chủ và vô hiệu hóa kết quả phụ thuộc; xử lý
  phiên hết hạn, xóa lỗi, đổi tài khoản và thao tác dừng/khởi tạo đồng thời. Lượt thử lại chỉ
  dùng lượt cũ nếu câu hỏi, dữ kiện, phạm vi và ngày không đổi.
- Sở thích mặc định yêu cầu danh mục hợp lệ. Từ chối đặt ngày mặc định và lưu hội thoại dài
  hạn vì hai chức năng này chưa được triển khai; không báo lưu thành công giả.
- Luồng SSE kiểm tra mã lượt, thứ tự sự kiện và dữ liệu hoàn thành, giới hạn bộ đệm và xử lý
  ngắt luồng. Phản hồi muộn của lượt đã dừng không xóa kết quả mới; phiên hết hạn trong lúc
  cập nhật sở thích không giữ khóa giao diện. Ngày mặc định dùng ngày cục bộ, cập nhật khi
  sang ngày mới; danh mục và ngày tự chọn được đặt lại khi đổi tài khoản.
- Cấu hình model chấp nhận tối đa 2.048 token đầu ra theo giới hạn runtime. Kết nối Local tới
  `localhost` được neo vào địa chỉ loopback, bảo toàn Host và SNI tương ứng. Không thêm
  RAG-Anything hoặc tải trọng số model.
- Cập nhật OpenAPI, chỉnh lỗi lint/type và đồng bộ ProgramsRoot khi khởi động dịch vụ.

## Bằng chứng

- [12/12 kiểm tra tự động](final/summary.json) thành công; backend **148 passed, 0 skipped**
  với PostgreSQL thật, frontend **34 passed**. Các kiểm tra bao gồm lint, type, build,
  OpenAPI, migration, fixture và chính sách đường dẫn. Bộ Rust có **17 passed**
  ([log](final/desktop-tests.txt)).
- Backend và giao diện web phản hồi HTTP 200; hai API cần đăng nhập trả 401 khi không có
  xác thực ([kết quả](final/stack-smoke.json)). Đây là kiểm tra khói, chưa phải kiểm thử đầy
  đủ qua tài khoản và giao diện desktop.
- Adapter Local kết nối HTTP thực đến một máy chủ mô phỏng trên loopback, nhận danh sách
  model và gửi đúng tham số ([kết quả](final/local-adapter-smoke.json)). Không phải thử với
  Ollama, một model thật hay nhà cung cấp API bên ngoài.
- Thử qua HTTP thực với schema PostgreSQL tạm và model giả lập: đăng nhập, lưu profile và
  route Local, probe, gọi runtime theo tham số, tạo phiên, đọc SSE, xóa dữ kiện và đăng xuất
  đều đạt ([kết quả](final/registry-http-smoke.json)). Schema và máy chủ thử đã được thu hồi.
- Bản desktop release đã build và có cửa sổ, tiến trình vẫn phản hồi sau 5 giây
  ([build](final/desktop-build.txt), [khởi chạy](final/desktop-launch-smoke.json)). Chưa thử
  đăng nhập, kéo/thả, DPI, nhiều màn hình hoặc chạy dài. File exe 9.906.176 byte, SHA-256
  `D6538E059F8A926E3A1414A40F3A12F907B14CF0175B73A6790B9DB59909EEBC`; kích thước này không
  bao gồm backend, cơ sở dữ liệu hoặc bộ cài.
- Bộ công cụ Rust được đặt dưới ProgramsRoot để build phát triển, thêm khoảng 462.423.977 byte
  trên máy; dung lượng này không nằm trong exe. Chưa đo tổng kích thước bản phân phối.
- Đợt thử 12 PDF công khai trong kho tạm đã nhập 12 bản nháp, 135 trang và 648 node, trong đó
  174 node có vị trí nguyên văn chính xác; còn 77 tác vụ rà soát và không có node được duyệt
  ([số liệu](../2026-10-26-code-audit/public-pdf-draft-ingest.json)). Thời gian 8,157 giây là
  số đo riêng của lần thử đó, không chứng minh chất lượng trả lời hay hiệu năng vận hành.

## Giới hạn và việc còn lại

1. Cơ sở dữ liệu hiện có 9 bản nháp và 3 bản chờ duyệt, không có bản đã duyệt
   ([số liệu](final/database-summary.json)). Ba tài liệu trước đây được tự duyệt đã được đưa
   lại vào diện rà soát vì chưa có dữ liệu trang và vị trí trích dẫn có thể đối chiếu. Bản
   sao lưu trước migration đã được tạo và kiểm tra danh mục bằng `pg_restore --list`; chưa
   thử khôi phục toàn bộ.
2. Quy trình hiện chưa có giao diện sửa/tái gắn các vị trí trích dẫn thiếu hoặc khôi phục
   nội dung trang cũ. Vì vậy một số tài liệu không thể được phê duyệt qua giao diện hiện tại;
   không bỏ qua rào chắn đối chiếu nguồn. PDF scan cũng cần OCR và rà soát của con người.
3. Chưa cấu hình được model thực ở trạng thái `ready`; chỉ kiểm tra policy, adapter và máy
   chủ mô phỏng. Chưa đánh giá API bên ngoài, độ chính xác gợi ý hoặc bộ Gold nghiệp vụ.
   Runtime model hiện chỉ chọn mã căn cứ đã có, không viết kết luận pháp lý.
4. Chưa có nghiệm thu trên Windows thực tế cho các thao tác native, tải kéo dài, bộ cài ký số
   hay cấu hình phần cứng của người dùng. Không thể kết luận đã loại bỏ mọi lag, crash,
   tính năng ảo hoặc dead code.
