# Spec: Nhập PDF, chuyển đổi và OCR có rà soát từng trang, bản dịch

**Ngôn ngữ / Language:** Tiếng Việt · bản chuẩn: [`.kiro/specs/ocr/`](../../../../.kiro/specs/ocr/)

> Ban đầu dựng lại từ mã nguồn ngày 09/11/2026; cập nhật theo source ngày 17/11/2026. Không phải spec lịch sử do Kiro tạo.

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

**Y6. Cây cấu trúc văn bản.**
1. WHEN đã trích chữ THE SYSTEM SHALL dựng cây Chương/Mục/Điều/Khoản/Điểm khi nhận diện được và đánh dấu trường hợp mơ hồ để rà soát (`tree_parser.py`).

**Y7. USER yêu cầu nội dung trang PDF.**
1. WHEN USER được phép yêu cầu trang cụ thể của tài liệu đã chọn THE SYSTEM SHALL nhận diện tài liệu từ lượt chat đang chọn hoặc tên/số hiệu rõ ràng và kiểm trang PDF theo phiên bản nguồn hiện tại (`documents/page_text.py`, `api/v1/page_text.py`).
2. IF chữ đã trích xuất/duyệt của trang dùng được và USER không yêu cầu đọc lại ảnh THEN THE SYSTEM SHALL trả chữ lưu sẵn, không gọi model.
3. IF thiếu chữ dùng được hoặc USER yêu cầu đọc ảnh THEN THE SYSTEM SHALL chỉ render/gửi đúng trang đó qua stage `ocr` local; không gửi toàn PDF/trang khác, không fallback ảnh sang API ngoài.
4. THE SYSTEM SHALL kiểm lại ACL, revision, hash PDF và hash chữ trang trong khi xử lý và trước khi trả kết quả; nguồn đổi thì hủy candidate cũ.
5. THE SYSTEM SHALL ghi rõ kết quả vision chưa xác minh, giữ cảnh báo/vùng không đọc rõ, có hủy và mở trang gốc, hết hạn kết quả tạm sau một giờ; không tạo citation đã xác minh, không sửa nguồn và không tạo vector.

**Y8. Đề xuất OCR AI trong Admin.**
1. WHEN CURATOR được phép yêu cầu OCR AI cho trang nháp THE SYSTEM SHALL tạo proposal idempotent gắn với phiên bản/trang và fingerprint cấu hình; chỉ hồ sơ Ollama vision đã kiểm tra, được duyệt và phân công stage `ocr` mới xử lý ảnh.
2. IF `EVIDENCE_OCR_AI_ENABLED` false hoặc không có THEN THE SYSTEM SHALL từ chối task đọc ảnh mới bằng lỗi có mã; chữ trang đã lưu vẫn tra cứu được.
3. WHEN CURATOR đối chiếu/chỉnh sửa và áp dụng proposal còn hợp lệ THE SYSTEM SHALL tạo bản nháp mới cùng audit, giữ nguyên bản đã duyệt. REVIEWER khác vẫn xác nhận trang và phê duyệt.
4. IF revision nguồn, hồ sơ/model hoặc fingerprint prompt đổi trước khi áp dụng THEN THE SYSTEM SHALL đánh dấu proposal cũ và từ chối áp dụng.

## Thiết kế (tóm tắt)

Luồng nhập: tải lên → `detect_format`, kích thước, SHA-256 → (Word/TXT) `convert_to_pdf` → `native_pdf` (pypdfium2, tiến trình con) → trang thiếu chữ thì Tesseract `vie+eng` → chẩn đoán từng trang → `tree_parser` → reviewer xác nhận từng trang OCR → người khác phê duyệt. Luồng đọc theo yêu cầu: USER chọn văn bản/trang → ACL/revision → chữ trang đã lưu hoặc render riêng trang → hồ sơ Ollama vision local stage `ocr` → kết quả tạm chưa xác minh. Luồng hiệu chỉnh: CURATOR đối chiếu/sửa proposal → bản nháp mới → REVIEWER khác.

| Mối quan tâm | Tệp |
|---|---|
| Nhận dạng và chuyển đổi | `documents/convert.py` (fpdf2, olefile, defusedxml; phông `fonts/Tinos-*.ttf`) |
| Lưu bất biến | `documents/provenance.py` |
| Chống trùng | `documents/deduplication.py` |
| Trích chữ gốc | `native_pdf.py`, `pdf_worker.py`, `isolated.py` |
| OCR | `documents/ocr.py` |
| OCR theo yêu cầu và worker | `documents/page_text.py`, `ocr_ai.py`, `ocr_ai_jobs.py`, `api/v1/page_text.py`, `api/v1/ocr_ai.py` |
| Nháp và duyệt | `draft.py`, `draft_read.py`, `review.py`, `preview.py`, `reextract.py` |
| Lược đồ | migration `0008_source_format`, `0015_ocr_page_review`, `0017_ocr_ai_proposals` |
| Giao diện | `DraftReviewPanel.tsx`, `PageTextPanel.tsx`, `OcrAiPanel.tsx`, `EvidenceChat.tsx`, `AdminDocumentDetail.tsx` |
| Nạp hàng loạt | `scripts/import_official_corpus.py`, `test-data/README.md` |

Quyết định: PDF được phân tích trong tiến trình con để tệp lỗi không làm sập API; PDF chuyển đổi có kết quả như nhau mỗi lần nên mã băm và trích dẫn ổn định; OCR là dữ liệu dẫn xuất, bản scan không đổi. Tesseract là OCR nền trong luồng nhập. OCR AI dùng hồ sơ Ollama vision local từ Registry, không hard-code model và worker tắt mặc định (`EVIDENCE_OCR_AI_ENABLED=false`). Đổi model sinh chữ/OCR không tạo lại vector; đổi embedding dùng luồng chỉ mục riêng. Gói LAN Portable source có probe ảnh nhưng chưa có ZIP mới; r4 giữ nguyên, không được coi là đã có nâng cấp.

Giới hạn: OCR có thể sai số, ngày, bảng và điều kiện. Báo cáo 17/11 thử model trên một PDF ảnh 20 trang hư cấu; không phải nghiệm thu độ chính xác tổng quát. Xem `docs/evidence/qwen35-upgrade/REVIEW_FIXES_2026-11-17.md`. Chưa kiểm thử ZIP Portable mới, di chuyển/offline ở máy Windows khác hoặc tải vận hành.

## Tasks
- [x] 1. Nhận dạng định dạng, chuyển Word/TXT sang PDF (migration `0008`)
- [x] 2. Lưu bất biến và kiểm digest
- [x] 3. Chống trùng theo byte và nội dung (migration `0005`)
- [x] 4. Trích chữ gốc cô lập
- [x] 5. OCR Tesseract kèm chẩn đoán
- [x] 6. Cột rà soát OCR từng trang (migration `0015`) và giao diện
- [x] 7. Trích xuất lại
- [x] 8. Parser cây cấu trúc văn bản
- [x] 9. Script nạp hàng loạt
- [ ] 10. Kiểm OCR trong vỏ Tauri và với nguồn TXT (báo cáo ghi chưa kiểm)
- [ ] 11. Tesseract trong gói `deploy/portable` (chưa đóng kèm)
- [x] 12. API USER đọc trang, ưu tiên chữ lưu, OCR local một trang, ACL/revision, hủy và hết hạn một giờ
- [x] 13. Giao diện chat chọn trang, hiển thị kết quả chưa xác minh, sao chép/mở/hủy
- [x] 14. Proposal OCR AI ADMIN, đối chiếu/chỉnh, áp dụng thành bản nháp mới, kiểm fingerprint và tách người duyệt
- [x] 15. Stage Ollama vision local và probe ảnh; worker mặc định tắt, không fallback ảnh ra API
- [ ] 16. Build ZIP Portable mới và xác nhận chạy offline sau di chuyển/ở máy Windows khác (r4 không thay đổi)

Kiểm chứng task 12–15: `docs/evidence/qwen35-upgrade/REVIEW_FIXES_2026-11-17.md`. Đây là test DB tạm và PDF tổng hợp; chưa đáp ứng task 16 hoặc nghiệm thu OCR nghiệp vụ.
