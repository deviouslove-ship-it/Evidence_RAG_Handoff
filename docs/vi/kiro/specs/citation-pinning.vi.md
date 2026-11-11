# Spec: Ghim trích dẫn, bản dịch

**Ngôn ngữ / Language:** Tiếng Việt · bản chuẩn: [`.kiro/specs/citation-pinning/`](../../../../.kiro/specs/citation-pinning/)

> Spec dựng lại từ mã nguồn đã triển khai ngày 09/11/2026 (`Spec reconstructed from the implemented code on 2026-11-09`). Không phải spec lịch sử do Kiro tạo. Hợp đồng: `docs/citation-contract.md`, `docs/pdf-anchor-coordinate-contract.md`.

## Giới thiệu
Mọi căn cứ hiển thị cho người dùng được ghim vào một phiên bản văn bản bất biến, một nút Điều/Khoản/Điểm, một span nguồn trên trang và SHA-256 của tệp gốc. Lời trích đến từ văn bản đã lưu, không bao giờ từ model.

## Yêu cầu (EARS)

**Y1. Định danh căn cứ ổn định, truy ngược được.**
1. THE SYSTEM SHALL định danh căn cứ dạng `ev_<node id>` truy ngược được tới `document_version_id`, `document_nodes.id`, `source_spans` (trang, offset, độ dài, quads) và SHA-256 tệp nguồn (`storage/citations.py`).
2. THE SYSTEM SHALL ghim `as_of_date` và trạng thái hiệu lực đã rà soát cùng căn cứ.

**Y2. Lời trích không do model sinh.**
1. THE SYSTEM SHALL lấy mọi lời trích từ `document_nodes.text_original`.
2. THE SYSTEM SHALL KHÔNG nhận lời trích, ID nút hay số trang từ model (`evidence/validators.py`, `mapper.py`, `synthesis/checks.py`).

**Y3. Khoản nhiều trang.**
1. WHEN khoản trải nhiều trang THE SYSTEM SHALL lưu một span nguồn cho từng trang (`documents/spans.py`, `node_writer.py`).
2. WHEN nút dài hơn 4.000 ký tự THE SYSTEM SHALL tiếp tục ở các phần "(phần N)" (`tree_parser.py::MAX_NODE_CHARACTERS`).
3. THE SYSTEM SHALL lưu `parent_id`, `path`, `citation_label` cho cây Chương/Mục/Điều/Khoản/Điểm (migration `0009_node_structure.sql`).

**Y4. Mở bản gốc với phân quyền thời gian thực.**
1. WHEN người dùng mở căn cứ (`GET /api/v1/citations/{id}`, `/pdf`, `/original`) THE SYSTEM SHALL kiểm lại ACL, trạng thái tra cứu, phiên bản, trạng thái nguồn và SHA-256 trước khi trả byte.
2. IF quyền đã bị thu hồi THEN THE SYSTEM SHALL trả 403 và KHÔNG phát lại nội dung cache.
3. WHEN nguồn là PDF THE SYSTEM SHALL mở đúng trang; WHEN là Word hoặc TXT THE SYSTEM SHALL tải đúng tệp đã nạp.
4. IF không chắc bbox, CropBox hoặc xoay trang THEN THE SYSTEM SHALL chỉ mở trang và hiển thị lời trích, không tô vị trí.

**Y5. Nguồn bất biến.**
1. THE SYSTEM SHALL lưu tệp gốc dưới `originals/<sha256>.pdf` và kiểm digest khi đọc (`documents/provenance.py::verify_immutable_pdf`).
2. IF digest hoặc đường dẫn không khớp THEN THE SYSTEM SHALL từ chối với `PDF_STORAGE_CONFLICT`.

## Thiết kế (tóm tắt)

| Mối quan tâm | Tệp |
|---|---|
| Tra cứu căn cứ được phép | `storage/citations.py`; route trong `backend/app/main.py` |
| Tệp nguồn bất biến | `documents/provenance.py` |
| Cây và span | `tree_parser.py`, `spans.py`, `node_writer.py`, `scripts/rebuild_node_tree.py`, migration `0009` |
| Kiểm căn cứ | `evidence/validators.py`, `mapper.py`, `workflow/evidence_mapper.py` |
| Giao diện | `OpenOriginalButton.tsx`, `DocumentCard.tsx` |

Luồng: người dùng mở `ev_<node>` → API kiểm ACL, trạng thái tra cứu, phiên bản, nguồn trong PostgreSQL → đọc `originals/<sha256>` và kiểm digest → trả trang PDF hoặc tệp Word/TXT gốc.

Quyết định: ID căn cứ chứa ID nút nên tham chiếu tự do từ model không thể tạo căn cứ. Tọa độ chữ OCR chỉ tới mức trang. Hợp đồng neo ghi rõ việc tô sáng tọa độ hộp ký tự (PDF bbox highlight) trên trình xem PDF và fixture PDF chứng minh độ chính xác tô vị trí (cổng WP 0.3 và 1.5) không triển khai (`docs/pdf-anchor-coordinate-contract.md`); trình xem mở đúng trang PDF và hiển thị trích đoạn nguyên văn.

Giới hạn: ở bộ thử G0, 0/21.724 khoản không neo (số liệu do phiên báo cáo, xem `KIRO_WORK_SUMMARY.vi.md` A8); chưa chạy lại khi viết spec.

## Tasks
- [x] 1. Tài liệu hợp đồng trích dẫn và neo
- [x] 2. Tra cứu căn cứ được phép và route
- [x] 3. Lưu tệp gốc bất biến, kiểm digest
- [x] 4. Cây Điều/Khoản/Điểm có parent, path, nhãn
- [x] 5. Span nguồn theo trang
- [x] 6. Validator từ chối lời trích do model đưa
- [x] 7. Nút "Mở văn bản gốc" cho PDF, Word, TXT
- [ ] 8. [Không triển khai] Tô sáng tọa độ hộp ký tự (PDF bbox highlight) trên trình xem PDF và fixture chứng minh độ chính xác tô vị trí (cổng WP 0.3/1.5 bỏ không triển khai)
- [ ] 9. Kiểm "Mở văn bản gốc" trong vỏ Tauri và với nguồn TXT (báo cáo ghi chưa kiểm)
