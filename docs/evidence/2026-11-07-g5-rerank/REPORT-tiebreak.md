# Khóa phá hòa ổn định cho RRF và các kênh của "Tìm toàn diện"

Ngày: 08/11/2026. Công thức RRF (k = 60), các kênh, ngưỡng, embedding và dữ liệu hiện có không đổi. Không tái tạo embedding, không xóa gì.

## 1. Vấn đề

Khi hai khoản bằng điểm, thứ tự được quyết định bằng `node_id`, là UUID sinh ngẫu nhiên mỗi lần nhập. Hai lần nhập cùng 100 tệp
cho hai thứ tự khác nhau. Việc này xảy ra ở ba chỗ, không chỉ ở `_rrf`:

| Nơi | Cách phá hòa trước đây |
|---|---|
| `_rrf` (hợp 4 kênh) | điểm RRF, hạng tốt nhất, rồi `node_id` |
| Kênh chính xác (`candidates_sql`, chỉ dùng cho kênh này) | bậc, điểm `ts_rank_cd`, rồi `node_id`; hạng trong kênh là đầu vào của RRF nên UUID ảnh hưởng cả điểm RRF |
| Kênh quan hệ (`_relation_hits`) | hạng, rồi `node_id` |

Đo trước khi sửa trên hai CSDL nhập độc lập từ cùng 100 tệp (`tiebreak-before-*.md`; 17/50 câu cho kết quả rỗng ở kênh chính xác, tính ở cả hai bên):

| Kênh | Cùng tập kết quả | Cùng thứ tự đầy đủ | Tỷ lệ vị trí giống nhau |
|---|---|---|---|
| chính xác | 50/50 | 45/50 | 0,672 |
| chính xác + quan hệ (có hợp RRF) | 50/50 | 41/50 | 0,613 |

## 2. Khóa mới

Thay `node_id` bằng khóa theo vị trí của khoản, giống nhau ở mọi lần nhập cùng tệp:

1. số hiệu văn bản (`documents.document_number`);
2. SHA-256 của tệp (`document_versions.original_file_sha256`, duy nhất; phân biệt hai văn bản trùng số hiệu như 96/2026);
3. số thứ tự trong văn bản, là tiền tố của `document_nodes.path` (ví dụ `000034:chuong:II/dieu:6/khoan:4`), tức thứ tự đọc Điều, Khoản, Điểm;
4. chính `path`;
5. `node_id` chỉ còn là lựa chọn cuối cùng cho khoản không có khóa.

So sánh theo byte (`COLLATE "C"` trong SQL, thứ tự điểm mã trong Python) nên không phụ thuộc locale máy chủ. Mã: `stable_clause_key` và `stable_order_sql`
(`storage/search_paging.py`), dùng ở `_rrf`, `candidates_sql` và `_relation_hits` (`storage/comprehensive.py`). Search v1 (`document_page_sql`) không đổi.
Bản gốc các tệp đã sao ở `.agents/backup-2026-11-08-rrf-tiebreak/`.

## 3. Kiểm tra

| Kiểm tra | Kết quả |
|---|---|
| Thứ tự SQL bằng thứ tự Python trên mọi khoản (7.230) | bằng nhau |
| `_rrf` sau khi gán lại UUID ngẫu nhiên cho mọi khoản, 20 lần | giống hệt 20/20 với khóa; 0/20 nếu không có khóa (hành vi cũ) |
| Hai CSDL nhập độc lập, kênh chính xác | cùng thứ tự đầy đủ **50/50** (trước: 45/50) |
| Hai CSDL nhập độc lập, chính xác + quan hệ + hợp RRF | **50/50** (trước: 41/50) |
| Cùng CSDL, hai lượt, kênh chính xác + theo nghĩa + quan hệ | 50/50, vị trí giống nhau 100% |
| `scripts/verify.ps1` | 12/12; backend 225 passed, frontend 77 passed (xem mục 5) |

Công cụ: `evaluation/coverage/check_tiebreak_stability.py`. Chưa kiểm được qua hai lần nhập: kênh theo nghĩa (hai CSDL nhập sau chưa có vector, theo yêu cầu không tạo embedding),
và kênh khái niệm (phụ thuộc bước `expand` của LLM, xem mục 4).

## 4. Ảnh hưởng đến kết quả (cùng CSDL `evidence_rerank_eval`, 50 câu, RRF thuần)

| Chỉ số | Khóa cũ (UUID) | Khóa mới |
|---|---|---|
| Recall@10 / @20 | 0,865 / 0,892 | 0,865 / 0,892 |
| Recall@50 | 0,932 | 0,946 |
| Recall@toàn bộ | 0,960 | 0,960 |
| MRR@10 | 0,790 | 0,779 |
| NDCG@10 | 0,594 | 0,589 |
| P@10 | 0,344 | 0,342 |

Recall giữ nguyên ở 10, 20 và toàn bộ; thay đổi còn lại nằm trong mức dao động đã biết (±0,02). Thứ tự đổi mạnh ở các vị trí hòa điểm: 10 kết quả đầu giống kết quả cũ chỉ ở 10/50 câu,
vì hòa điểm rất phổ biến. Đó là điều mong đợi khi khóa đổi: khóa chỉ đổi thứ tự giữa các khoản bằng điểm, không đổi khoản nào được tìm thấy (tập kết quả của kênh chính xác giống nhau giữa hai CSDL 50/50, cả trước lẫn sau khi sửa).

Hai lượt liên tiếp trên cùng CSDL với đủ bốn kênh vẫn cho nhóm ứng viên khác nhau ở 12/50 câu (hạng căn cứ khác ở 3/50; `bench-rrf-50-stable-1/2.json`). Khi bỏ kênh khái niệm thì 50/50 giống hệt,
nên nguồn không ổn định còn lại là bước `expand` (LLM) của kênh khái niệm, không phải khóa phá hòa. Kênh theo nghĩa dùng chỉ mục HNSW xấp xỉ; một chỉ mục dựng lại có thể cho láng giềng hơi khác.

## 5. Ghi chú về cây mã và dữ liệu

- Từ 20:53 đến 21:19 ngày 07/11 có thay đổi khác trong cây mã không phải của lần làm này: migration `0014_embedding_jobs`, quản lý embedding trong Admin Portal
  (`EmbeddingManager`), `storage/embedding_jobs.py`, `deploy/portable`, `docs/openapi.json`. Hồi quy chạy trên cây mã hiện tại nên số test là 225 và 77 (trước 218 và 74); tôi không thêm test nào.
- Khởi động API tự áp migration còn thiếu, nên `0014` đã được áp lên `evidence_rerank_eval` (thêm bảng `embedding_jobs` và vài cột của `embedding_indices`; 7.230 vector và chỉ mục `ready` không đổi) và lên CSDL nhập thử mới.
  Bản dump đầu tiên (schema 0013) và bản khôi phục `evidence_rerank_eval_restorecheck` vẫn nguyên. Để bản sao lưu khớp CSDL hiện tại, đã tạo thêm
  `backups\rerank-eval\evidence_rerank_eval-schema0014-20261108-084058.dump` (37 MB, SHA-256 `02c13cc1…b2ce`), khôi phục thử vào `evidence_rerank_eval_restorecheck_0014`
  và `verify_db_restore.py` đạt (52 bảng, 38.107 dòng, 101 chỉ mục, vector và HNSW khớp).
- CSDL mới `evidence_rerank_eval_reimport` (nhập lại 100 tệp, không embedding, kho tài liệu `data\rerank-eval\reimport-check`) được giữ lại; nó dùng cho `check_tiebreak_stability.py`. Không xóa dữ liệu nào.
