# Bộ PDF công khai để thử kỹ thuật

`manifest.json` ghi nguồn chính thức, URL tệp, thời điểm tải, kích thước và SHA-256 của 12 nghị định từ Cổng Thông tin điện tử Chính phủ. Các PDF trong `files/` chỉ dùng để thử trích xuất, phân đoạn và truy xuất; `*.pdf` bị Git bỏ qua và không thuộc gói cài app.

Trạng thái `test_only_unreviewed` nghĩa là chưa có người xác minh tính xác thực, hiệu lực hay tính phù hợp nghiệp vụ. Không đưa các văn bản này vào nguồn đã duyệt hoặc bộ Gold. Tài liệu nghiệp vụ sẽ được nhập riêng khi người dùng cung cấp.

Chạy `evaluation/scripts/audit_public_pdf_corpus.py` bằng Python của backend để kiểm tra lại hash, trang, lớp chữ và kết quả phân đoạn.

Để thử 9 PDF scan, cấu hình biến môi trường `EVIDENCE_OCR_EXECUTABLE` bằng đường dẫn tuyệt đối đến Tesseract đã cài riêng, rồi chạy script audit với `--ocr`. OCR là thành phần tùy chọn; trang OCR luôn cần duyệt. Chạy `evaluation/scripts/evaluate_public_pdf_retrieval.py` với cùng biến môi trường để đo truy xuất ứng viên trên 12 tệp. Kết quả đó chỉ là kiểm thử kỹ thuật, không xác nhận hiệu lực pháp lý hoặc quyền công bố.
