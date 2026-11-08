# Citation contract

Mỗi evidence phải có identity ổn định và truy ngược được tới:

1. `document_version_id` bất biến;
2. `document_nodes.id`;
3. `source_spans.id`, page, original offset/length, quads;
4. SHA-256 của file PDF gốc;
5. `as_of_date` và trạng thái hiệu lực đã review;
6. quyền của principal tại thời điểm mở citation.

Quote luôn được hydrate từ `document_nodes.text_original`; LLM không cung cấp quote, node ID hoặc số trang. Khi không chắc bbox/CropBox/rotation, viewer chỉ mở trang và hiển thị quote, tuyệt đối không tô sai vị trí.

Khi mở citation cũ, server kiểm lại ACL và policy. Nếu quyền thu hồi, trả `403`; không phát lại nội dung đã cache.
