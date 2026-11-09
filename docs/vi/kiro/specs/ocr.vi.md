# Spec: Nhập PDF, chuyển đổi và OCR có rà soát từng trang, bản dịch

**Ngôn ngữ / Language:** Tiếng Việt · bản chuẩn: [`.kiro/specs/ocr/`](../../../../.kiro/specs/ocr/)

> Spec dựng lại từ mã nguồn đã triển khai ngày 09/11/2026 (`Spec reconstructed from the implemented code on 2026-11-09`). Không phải spec lịch sử do Kiro tạo.

## Giới thiệu
Tài liệu vào hệ thống dưới dạng PDF, Word (`.docx`, `.doc`) hoặc TXT. Trang scan được đọc bằng OCR, và chữ OCR không trở thành căn cứ cho đến khi reviewer đối chiếu từng trang với bản scan.

## Yêu cầu (EARS)

**Y1. Kiểm định khi nhập.**
1. WHEN tải tệp lên THE SYSTEM SHALL nhận dạng định dạng từ byte (đuôi tệp chỉ dùng phân xử với văn bản thuần), kiểm kích thước và magic PDF, tính SHA-256 (`convert.py::detect_format`, `provenance.py`).
2. IF byte trùng tệp đã có THEN THE SYSTEM SHALL chặn; IF chỉ trùng nội dung chữ THEN THE SYSTEM SHALL cảnh báo (`deduplication.py`).
3. IF `.doc` thực chất là HTML hoặc RTF, văn bản rỗng, hoặc mã hóa TXT không hỗ trợ THEN THE SYSTEM SHALL từ chối kèm mã lỗi.

**Y2. Chuyển đổi Word và TXT.**
1. WHEN nhận Word hoặc TXT THE SYSTEM SHALL vẽ thành PDF A4 có lớp chữ, kết quả như nhau mỗi lần, để dùng chung một đường trích dẫn (`convert.py::convert_to_pdf`, `render_pdf`).
2. THE SYSTEM SHALL giữ tệp gốc cùng mã băm riêng (`document_versions.source_format`, `source_file_sha256`; migration `0008_source_format.sql`).
3. IF Word chỉ chứa ảnh THEN THE SYSTEM SHALL KHÔNG OCR như PDF scan.

**Y3. Chữ gốc và OCR.**
1. THE SYSTEM SHALL trích chữ và hộp ký tự bằng pypdfium2 trong tiến trình con cô lập (`native_pdf.py`, `pdf_worker.py`, `isolated.py`).
2. WHEN trang không có chữ dùng được hoặc lớp chữ nghi lỗi (`diagnose_text_quality`) VÀ OCR đã cấu hình THE SYSTEM SHALL chạy Tesseract (`vie+eng`) cho trang đó (`ocr.py::TesseractOcr`).
3. WHEN chạy OCR THE SYSTEM SHALL lưu chẩn đoán: độ tin cậy, tỉ lệ mực, góc xoay, token đáng ngờ, dấu điểm bị đọc sai (`ocr.py::diagnose`, migration `0015_ocr_page_review.sql`).
4. IF OCR chưa cấu hình hoặc lỗi THEN THE SYSTEM SHALL giữ trang ngoài căn cứ đã xác minh và báo mã lỗi (`OcrError`).
5. THE SYSTEM SHALL chỉ mô tả tọa độ OCR tới mức trang.

**Y4. Người rà soát từng trang.**
1. WHEN reviewer mở bản nháp có trang OCR THE SYSTEM SHALL hiển thị chữ OCR và cảnh báo của từng trang bên cạnh bản scan.
2. THE SYSTEM SHALL yêu cầu reviewer xác nhận từng trang OCR (`source_pages.reviewed_by`, `reviewed_at`) trước khi phê duyệt.
3. WHEN CURATOR sửa chữ OCR của bản đã duyệt THE SYSTEM SHALL tạo bản nháp mới và yêu cầu xác nhận lại từng trang đã sửa.
4. THE SYSTEM SHALL giữ chữ OCR trước và sau khi sửa.

**Y5. Trích xuất lại.**
1. WHEN CURATOR có quyền yêu cầu trích xuất lại THE SYSTEM SHALL chạy lại trích xuất và OCR từ nguồn đã lưu và đưa kết quả về bản nháp (`POST /api/v1/admin/documents/drafts/{version_id}/reextract`, `reextract.py`).

**Y6. Cây pháp lý.**
1. WHEN đã trích chữ THE SYSTEM SHALL dựng cây Chương/Mục/Điều/Khoản/Điểm khi nhận diện được và đánh dấu trường hợp mơ hồ để rà soát (`tree_parser.py`).

## Thiết kế (tóm tắt)

Luồng: tải lên → `detect_format`, kích thước, SHA-256 → (Word/TXT) `convert_to_pdf` → `native_pdf` (pypdfium2, tiến trình con) → trang thiếu chữ thì Tesseract `vie+eng` → chẩn đoán từng trang → `tree_parser` → reviewer xác nhận từng trang OCR → người khác phê duyệt.

| Mối quan tâm | Tệp |
|---|---|
| Nhận dạng và chuyển đổi | `documents/convert.py` (fpdf2, olefile, defusedxml; phông `fonts/Tinos-*.ttf`) |
| Lưu bất biến | `documents/provenance.py` |
| Chống trùng | `documents/deduplication.py` |
| Trích chữ gốc | `native_pdf.py`, `pdf_worker.py`, `isolated.py` |
| OCR | `documents/ocr.py` |
| Nháp và duyệt | `draft.py`, `draft_read.py`, `review.py`, `preview.py`, `reextract.py` |
| Lược đồ | migration `0008_source_format`, `0015_ocr_page_review` |
| Giao diện | `frontend/src/components/DraftReviewPanel.tsx` |
| Nạp hàng loạt | `scripts/import_official_corpus.py`, `test-data/README.md` |

Quyết định: PDF được phân tích trong tiến trình con để tệp lỗi không làm sập API; PDF chuyển đổi có kết quả như nhau mỗi lần nên mã băm và trích dẫn ổn định; OCR là dữ liệu dẫn xuất, bản scan không đổi. Runtime OCR (Tesseract, dữ liệu ngôn ngữ) cấu hình ngoài mã; gói LAN Portable đóng kèm, còn gói `deploy/portable` không có Tesseract.

Giới hạn: OCR có thể sai số hiệu và điều kiện. Báo cáo ghi các lần thử OCR PDF scan trên máy phát triển (`docs/evidence/2026-11-08-ai-ocr/REPORT.md`); chưa chạy lại khi viết spec.

## Tasks
- [x] 1. Nhận dạng định dạng, chuyển Word/TXT sang PDF (migration `0008`)
- [x] 2. Lưu bất biến và kiểm digest
- [x] 3. Chống trùng theo byte và nội dung (migration `0005`)
- [x] 4. Trích chữ gốc cô lập
- [x] 5. OCR Tesseract kèm chẩn đoán
- [x] 6. Cột rà soát OCR từng trang (migration `0015`) và giao diện
- [x] 7. Trích xuất lại
- [x] 8. Parser cây pháp lý
- [x] 9. Script nạp hàng loạt
- [ ] 10. Kiểm OCR trong vỏ Tauri và với nguồn TXT (báo cáo ghi chưa kiểm)
- [ ] 11. Tesseract trong gói `deploy/portable` (chưa đóng kèm)
