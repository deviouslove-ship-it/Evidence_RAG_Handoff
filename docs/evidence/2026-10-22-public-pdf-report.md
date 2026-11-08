# Kiểm thử PDF công khai và tiến độ app — 22/10/2026

Nguồn: [hệ thống văn bản Chính phủ](https://vanban.chinhphu.vn/he-thong-van-ban?classid=1&mode=1&typegroupid=4). [Manifest](../../evaluation/corpus_public_real/manifest.json) ghi 12 URL chi tiết, URL PDF, ngày tải, hash và kích thước. PDF là dữ liệu thử riêng, không nằm trong gói app, không thuộc Gold hoặc nguồn đã duyệt.

| Phép đo | Kết quả |
|---|---:|
| PDF / tổng bytes / trang | 12 / 26.319.803 / 135 |
| Text native | 3 PDF, 70 trang, 149.514 ký tự |
| Scan không có lớp chữ | 9 PDF, 65 trang |
| OCR cục bộ thử nghiệm | 65/65 trang đọc được chữ, 113.860 ký tự; 65/65 trang `needs_review` |
| Parser sau sửa | 1.094 node thử kỹ thuật trên 12 PDF |
| Truy xuất ứng viên | 15/15 ca: 12 số hiệu, 3 Điều; trước sửa 12/15 |
| API CURATOR `/documents/preview` | 12/12 PDF trả hash đúng, 135 trang; khi không bật OCR, 65 trang `needs_ocr` |
| API với OCR bật riêng | PDF 381: 3/3 trang `local_ocr`, 3/3 `needs_review`, hash đúng |
| Nhập nháp PostgreSQL dev, native text | 12/12 bản `draft`, 135 trang, 648 node, 77 tác vụ duyệt; 0 node lộ qua ACL |
| Span ký tự khớp nguyên văn | 174/648 node native; chưa có quads/bbox |

Core chỉ thêm pypdfium2 (6.143.401 bytes cài tại môi trường thử). Pillow phục vụ OCR tùy chọn (14.912.867 bytes); Tesseract sẵn trên máy thử là runtime ngoài gói Core (190.325.373 bytes), chưa được đóng gói/phê duyệt để triển khai. PostgreSQL/pgvector dev riêng chiếm 163.383.005 bytes chương trình, 86.468.241 bytes data cluster và 384.620.317 bytes ZIP cache; không tính các khoản này vào Core. RAG-Anything không được cài. Đây là kích thước **thành phần đã cài**, chưa phải số đo clean-install của cả app.

[RAG-Anything](https://github.com/HKUDS/RAG-Anything) hướng tới truy xuất đa phương thức và [khai báo phụ thuộc lõi](https://github.com/HKUDS/RAG-Anything/blob/main/pyproject.toml) gồm LightRAG, MinerU và Hugging Face Hub. Với bộ thử hiện là PDF văn bản pháp quy và ưu tiên hạn chế dung lượng, chưa có bằng chứng cần kéo toàn bộ framework vào Core; chưa đo kích thước cài đặt thật của framework nên không gán con số tiết kiệm giả định.

Thay đổi mã: trích PDF có quản lý tài nguyên và giới hạn trang; OCR chỉ chạy trên trang không có chữ khi cấu hình thực thi rõ ràng; kết quả OCR buộc duyệt, không có bbox native giả; parser giữ đúng nội dung tiếp của điểm và hạ confidence khi OCR; truy xuất xét số hiệu, tiêu đề và Điều trước khi cắt ứng viên. API xem trước giới hạn bytes/trang và yêu cầu CURATOR. API nhập PDF lưu bản gốc theo hash tại `EVIDENCE_DOCUMENT_STORE_ROOT` (đường dẫn tuyệt đối do triển khai cấu hình), metadata nguồn, trang, span và node vào PostgreSQL dưới trạng thái `draft`; tạo task rà soát, chặn trùng hash. CURATOR/REVIEWER có thể liệt kê nháp và đọc lại byte PDF sau khi kiểm hash. Test 12 PDF dùng schema/kho riêng rồi xóa, không nhập vào nguồn app đã duyệt.

Bằng chứng: [audit PDF](2026-10-22-public-pdf-ocr-audit.json), [retrieval](2026-10-22-public-pdf-retrieval.json), [API smoke](2026-10-22-public-pdf-api-smoke.json), [API OCR](2026-10-22-public-pdf-api-ocr-smoke.json), [nhập nháp 12 PDF](2026-10-22-public-pdf-draft-ingest.json), [PostgreSQL dev](2026-10-22-postgres-dev.json), [footprint](2026-10-22-public-pdf-footprint.json), [12 check](2026-10-22-public-pdf-verification/summary.json). Backend 82 passed, 0 skipped; frontend 8 passed và build thành công. Còn thiếu identity provider production, giao diện duyệt và phê duyệt nguồn, viewer citation của USER, quads/bbox, quét mã độc, QA độ đúng OCR, backup/restore và nghiệm thu câu trả lời pháp lý. Bài kiểm thử SQL dùng DB dev thật nhưng không chứng minh app sẵn sàng phát hành.
