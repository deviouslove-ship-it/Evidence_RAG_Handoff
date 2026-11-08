# Tiếp tục hoàn thiện: PDF và chống trùng nội dung

## Quy tắc chống trùng

1. File PDF có byte giống hệt được nhận diện bằng SHA-256 trước khi chạy bộ trích xuất;
   ràng buộc duy nhất trong PostgreSQL vẫn bảo vệ trường hợp nhập đồng thời.
2. Với tài liệu mà mọi trang có lớp chữ gốc đọc được, hệ thống tạo dấu vân tay SHA-256 từ
   văn bản chuẩn hóa Unicode NFC và khoảng trắng. Dấu tiếng Việt, chữ hoa/thường và dấu câu
   vẫn được giữ; văn bản các trang được nối bằng khoảng trắng. Bản khác byte có cùng dấu vân tay
   được báo là **có thể trùng**, lưu riêng ở trạng thái nháp và tạo tác vụ kiểm tra.
3. Danh sách ứng viên trong màn hình rà soát chỉ trả bản nháp/chờ duyệt hoặc tài liệu mà
   người xem có quyền truy cập. Hai lượt nhập đồng thời cùng nội dung được tuần tự hóa khi
   kiểm tra. Không tự gộp, xóa hay phê duyệt vì chữ ký, hình ảnh, nguồn và phiên bản pháp lý
   có thể khác nhau dù lớp chữ giống nhau.
4. Trang scan, OCR hoặc lớp chữ không đạt chất lượng không được cấp dấu vân tay nội dung;
   vẫn kiểm tra SHA-256 file. Thuật toán này chưa tìm các bản chỉ giống một phần, thay đổi
   vài từ, thêm trang trắng, đổi số trang/header trong lớp chữ hay có sai lệch OCR. Kết quả
   không phát hiện trùng không chứng minh hai văn bản khác nhau.

Migration mới chỉ thêm cột và chỉ mục, không tự suy đoán dấu vân tay cho dữ liệu cũ. Cả 12
phiên bản hiện có chưa được lập dấu vân tay nội dung; khi biên tập viên chọn **Trích xuất lại
PDF gốc**, hệ thống tính dấu vân tay nếu mọi trang đáp ứng điều kiện. Tài liệu scan vẫn cần
OCR và kiểm tra riêng. Rollback migration giữ bản ghi tài liệu nhưng xóa dấu vân tay dẫn xuất.

## Trích xuất và rà soát nguồn

- Khớp đoạn theo khoảng trắng nhưng lưu đúng lát cắt nguyên văn của một trang PDF. Từ chối
  khớp mơ hồ hoặc đoạn không nằm trọn trên một trang, tạo tác vụ rà soát thay vì bịa span.
- Phân biệt tiêu đề có số như `Chương II`, `Mục 1` với các từ thông thường như “Chương trình”
  và “Mục tiêu”.
- Biên tập viên có thể trích xuất lại một bản nháp/chờ duyệt từ PDF gốc đã kiểm mã băm.
  Chỉ khôi phục trang còn thiếu, bảo toàn ID node, không ghi đè văn bản trang khác kết quả
  trích xuất, không xử lý bản đã duyệt và không tự phê duyệt. Thao tác được ghi kiểm toán và
  tạo tác vụ thẩm định lại.

## Kết quả kiểm thử

- [Bộ kiểm tra](verification/summary.json): 12/12 mục đạt; backend 161 kiểm thử, frontend
  37 kiểm thử và [Rust](desktop-tests.txt) 17 kiểm thử. Một cảnh báo deprecation từ
  dependency kiểm thử vẫn xuất hiện.
- [12 PDF nguồn công khai](public-pdf-draft-ingest.json) được nhập vào schema/kho tạm: 135
  trang, 797 node nháp, 791 node có span nguyên văn duy nhất, 6 node chưa gắn được trang;
  không có node nháp lọt vào retrieval. Đoạn có span chưa đồng nghĩa đã được thẩm định.
- [Mô phỏng](reextract-simulation.json) từ một PDF nguồn trong schema tạm: khôi phục 18 trang,
  gắn 190 node, cảnh báo bản khác byte cùng lớp chữ, chặn tự duyệt, thử duyệt bằng tài khoản
  khác, tra cứu, kiểm mã băm PDF và thu hồi quyền. Việc duyệt chỉ là dữ liệu thử, không phải
  phê duyệt hay kết luận pháp lý thật.
- [Kiểm tra chỉ đọc](legacy-readonly-preview.json) trên ba bản cũ: 351 có 190/190 node có
  thể gắn; 355 có 102/106 và 385 có 348/352. Chưa tự thay đổi ba bản này. Node cũ không được
  tự xây dựng lại để tránh làm mất ID và liên kết; tám node cũ chưa gắn vẫn cần xử lý.
- Migration đã áp dụng sau [bản sao lưu](backup.json); đã thử [khôi phục vào cơ sở tạm](backup-restore-test.json)
  và đếm đủ 12 phiên bản. Đây chưa phải kiểm thử đầy đủ mọi dữ liệu khôi phục.
  [Thử down/up](migration-down-up.json) được thực hiện trên schema riêng.
- Backend và web phản hồi, các route mới xuất hiện trong OpenAPI
  ([thử khói](live-smoke.json)). Desktop release đã build và có cửa sổ phản hồi trong 5 giây
  ([build](desktop-build.json), [thử khởi chạy](desktop-launch-smoke.json)); chưa kiểm thử
  tương tác đầy đủ trên desktop hoặc cấu hình AI thật.

## Việc còn lại

Chưa có giao diện sửa/tách đầy đủ node kéo dài qua nhiều trang. Một số bản cũ vì vậy vẫn
không thể phê duyệt, dù đã trích xuất lại; không bỏ qua rào chắn kiểm tra span. Cần tiếp tục
xây dựng công cụ biên tập có đối chiếu PDF và kiểm thử trường hợp xuyên trang, OCR và thay đổi
phiên bản, sau đó mới đánh giá nghiệp vụ trên bộ Gold và model thật.
