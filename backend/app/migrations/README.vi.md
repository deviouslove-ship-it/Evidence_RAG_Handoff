**Ngôn ngữ / Language:** [English](README.md) · Tiếng Việt

# Migration cơ sở dữ liệu

Migration nhắm PostgreSQL với `pgcrypto` và `pgvector`. Backend áp chúng
khi khởi động qua `runner.py`: các tệp `NNNN_*.sql` chạy theo thứ tự tên, mỗi tệp trong
giao dịch riêng, được ghi vào `schema_migrations` cùng SHA-256 của nội dung SQL. Tệp
bị sửa sau khi đã áp thì chặn khởi động (`MIGRATION_CHANGED_AFTER_APPLY`) thay vì
áp lại. Migration không tạo database, không chuyển dữ liệu nghiệp vụ và không cài
PostgreSQL.

| Up | Down | Mục đích |
|---|---|---|
| `0001_core.sql` | `0001_core.down.sql` | Lược đồ lõi, view ACL |
| `0002_auth_admin.sql` | `0002_auth_admin.down.sql` | Tài khoản, vai trò, phiên |
| `0003_source_integrity.sql` | `0003_source_integrity.down.sql` | Chữ trang, thứ tự kiểm toán, kiểm tra lại span |
| `0004_ai_runtime.sql` | `0004_ai_runtime.down.sql` | Tham số hồ sơ model |
| `0005_pdf_content_fingerprint.sql` | `0005_pdf_content_fingerprint.down.sql` | Tín hiệu trùng nội dung |
| `0006_search_index.sql` | `0006_search_index.down.sql` | Chỉ mục biểu thức GIN của tìm kiếm v1 |
| `0007_normalization_revision.sql` | `0007_normalization_revision.down.sql` | Dấu revision chuẩn hóa |
| `0008_source_format.sql` | `0008_source_format.down.sql` | Định dạng nạp và mã băm nguồn Word/TXT |
| `0009_node_structure.sql` | `0009_node_structure.down.sql` | Span nguồn theo trang, nhãn trích dẫn, `node_source_text_valid` |
| `0010_ai_policy.sql` | `0010_ai_policy.down.sql` | Chính sách giai đoạn AI và cài đặt runtime |
| `0011_effectivity.sql` | `0011_effectivity.down.sql` | Quan hệ hiệu lực, thẩm định và snapshot |
| `0012_comprehensive_search.sql` | `0012_comprehensive_search.down.sql` | Tìm toàn diện và số chiều vector linh hoạt |
| `0013_content_groups.sql` | `0013_content_groups.down.sql` | Nhóm nội dung và quy tắc gán nhãn |
| `0014_embedding_jobs.sql` | `0014_embedding_jobs.down.sql` | Job dựng lại embedding chạy nền, trạng thái chỉ mục `paused`/`failed` |
| `0015_ocr_page_review.sql` | `0015_ocr_page_review.down.sql` | Chẩn đoán trang OCR và người duyệt đã đối chiếu trang với bản scan |
| `0016_document_management.sql` | `0016_document_management.down.sql` | Siêu dữ liệu có phiên bản, sửa OCR, khả năng tra cứu và revision bộ nhớ đệm |
| `0017_ocr_ai_proposals.sql` | `0017_ocr_ai_proposals.down.sql` | Job OCR AI theo trang theo yêu cầu và đề xuất sửa của curator (`ocr_ai_jobs`, `ocr_ai_proposals`) |
| `0018_legal_hierarchy_and_conflict_reviews.sql` | `0018_legal_hierarchy_and_conflict_reviews.down.sql` | Quy tắc thứ bậc hiệu lực pháp lý (23 quy tắc VBQPPL được nạp sẵn), lượt rà soát mâu thuẫn chạy nền và phát hiện (`legal_authority_rules`, `conflict_review_runs`, `conflict_findings`) |

Hiện có **18** cặp migration tiến/lùi (`0001`–`0018`). Migration `0016`, `0017` và `0018` chỉ thêm mới và giữ nguyên mọi văn bản, phiên bản, mã băm, nút và embedding pgvector hiện có (`0018` nạp quy tắc thẩm quyền mặc định với `ON CONFLICT DO NOTHING`).
Migration lùi chạy trên schema chưa dùng và từ chối xóa các trường mới khi chúng
đã chứa dữ liệu quản trị. Giữ một bản sao lưu mã hóa trước khi nâng cấp để quay lui nhị phân.

Mỗi tệp up cần một `.down.sql` tương ứng (`scripts/validate_migrations.py`). Không thêm
chỉ mục b-tree trên `document_nodes(document_version_id)` nếu chưa chạy lại benchmark
tìm kiếm: planner ưu tiên nó hơn các chỉ mục GIN (ADR-006 §2.3).

Nghiệm thu vận hành còn yêu cầu:

1. Extension pgvector và truy vấn vector chính xác đã được kiểm trên máy Windows đích.
2. Migration tiến/lùi đã thử trên một database thử sạch.
3. Kiểm thử rò ACL cho quyền danh mục và quyền văn bản.
4. Sao lưu đã mã hóa và phục hồi sang máy sạch, rồi phát lại sổ xóa.
