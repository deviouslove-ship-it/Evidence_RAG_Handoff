# ADR-009 — Tìm toàn diện bốn kênh, nhóm nội dung và tổng hợp có kiểm tra (G2, G4, G5)

- Ngày: 07/11/2026
- Trạng thái: Đã triển khai
- Căn cứ: thiết kế chốt `docs/thiet-ke-tra-cuu-hieu-luc.md` mục 6, 7, 8, 12; quyết định D3, D4,
  D6, D8, D9, D11, D13, D15; điểm nhất quán 5, 6, 9, 10, 12, 13.

## 1. Tìm toàn diện (G2)

1. **Embedding local qua Model Registry.** Giai đoạn `embedding` dùng adapter OpenAI-compatible
   (`POST /embeddings`); thử nghiệm với Ollama chạy độc lập và `qwen3-embedding:0.6b` (1024 chiều).
   Endpoint, model, đường dẫn cài đặt chỉ nằm trong Registry và biến môi trường; mã không biết
   tên model. Giai đoạn `embedding` và `rerank` **không bao giờ** gửi tới hồ sơ `public`, ở cả hai
   chế độ (`LOCAL_ONLY_STAGES`).
2. **Chỉ mục vector theo chiều model** (migration `0012`): cột `node_embeddings.embedding` không cố
   định số chiều; mỗi `embedding_indices` ghi model, phiên bản, số chiều và có chỉ mục HNSW riêng
   `((embedding::vector(D)) vector_cosine_ops) WHERE embedding_index_id = …`. Đổi model = mở phiên
   bản chỉ mục mới bằng `scripts/build_embeddings.py --rebuild`; chỉ mục cũ dùng tiếp tới khi chỉ mục
   mới đủ (công cụ G5). Câu đưa vào embedding: số hiệu + nhãn trích dẫn + chữ khoản, tối đa 800 ký tự
   (máy không GPU).
3. **Bốn kênh hợp bằng RRF** (k = 60): chính xác (SQL Search v1, đếm đủ tới trần 8.000), theo nghĩa
   (N = `EVIDENCE_SEMANTIC_TOP_N`, ngưỡng tương đối `EVIDENCE_SEMANTIC_RELATIVE_THRESHOLD` so với khoản
   gần nhất), mở rộng khái niệm (`concept_terms` đã duyệt; khi ít hơn `EVIDENCE_CONCEPT_MIN_TERMS` thì
   giai đoạn `expand` gợi ý, hiện cho người dùng bỏ chọn và lưu thành đề xuất chờ duyệt), quan hệ văn
   bản (khoản của văn bản có quan hệ đã duyệt hoặc hợp nhất/hướng dẫn với 20 văn bản đứng đầu).
   **Khóa phá hòa ổn định (08/11/2026):** công thức RRF (k = 60) và các kênh không đổi; khi hai khoản bằng điểm
   (trong kênh chính xác cùng bậc và điểm, trong kênh quan hệ cùng hạng, và khi hợp RRF cùng điểm cùng hạng tốt nhất) thứ tự
   xác định bằng số hiệu văn bản, mã băm SHA-256 của tệp (phân biệt các văn bản trùng số hiệu), rồi vị trí khoản trong
   văn bản (tiền tố số thứ tự của `document_nodes.path`, tức thứ tự Điều → Khoản → Điểm). Trước đây dùng UUID của khoản,
   ngẫu nhiên theo mỗi lần nhập. So sánh theo byte (`COLLATE "C"`), không phụ thuộc locale máy chủ. UUID chỉ còn là lựa chọn cuối cùng.
4. **Bộ kết quả cố định theo lượt** (`ResultSetStore`): chỉ trong RAM, mỗi người tối đa 20 bộ, hết hạn
   `EVIDENCE_RESULT_SET_TTL_SECONDS`; chỉ chủ bộ đọc được; mỗi trang kiểm lại quyền và nguồn.
5. **Rerank theo lô** (giai đoạn `rerank`, model local) là **tùy chọn, tắt theo mặc định** từ 07/11/2026
   (`EVIDENCE_RERANK_DEFAULT=false`; yêu cầu có thể gửi `rerank: true`): `EVIDENCE_RERANK_TOP_N` ứng viên
   đầu, lô `EVIDENCE_RERANK_BATCH_SIZE`; phần sau giữ thứ tự RRF; không loại ứng viên; trả `ranking`.
   Mặc định thực tế của "Tìm toàn diện" là RRF thuần.
6. **Phạm vi trung thực:** danh mục, số văn bản trong phạm vi, ngày dữ liệu, trần và ngưỡng kênh theo
   nghĩa, số khoản chưa có vector, số khoản chỉ nhờ kênh theo nghĩa/quan hệ; khi trống: "Chưa thấy
   trong kho …", không bao giờ "đã tìm hết".
7. **D9:** mặc định ba nhóm "Còn hiệu lực (đã xác minh)", "Chưa xác minh hiệu lực", "Hết hiệu lực, bị
   thay thế, tạm ngưng" (thu gọn, vẫn đếm); "Tìm toàn bộ", "Đối chiếu lịch sử" hoặc ngày tra cứu khác
   hôm nay → một danh sách. Bộ lọc trạng thái/xác minh chạy trên toàn bộ.
8. **Nhóm văn bản (D3)** tính khi truy vấn: văn bản sửa đổi một phần/hợp nhất thuộc nhóm của văn bản
   gốc; văn bản bị thay thế thuộc nhóm của văn bản thay thế; gốc ngoài quyền chỉ ghi "có văn bản liên
   quan ngoài phạm vi được cấp quyền".

## 2. Nhóm nội dung và tổng hợp (G4)

1. `content_taxonomy`, `labeling_rules`, `node_labels`, `node_label_runs` (migration `0013`); 11 nhóm
   ban đầu do triển khai đề xuất (thiết kế không liệt kê tên), sửa/thêm được trong CSDL. Quy tắc cụm
   từ gán ngay (`auto`); giai đoạn `label` đề xuất cho khoản chưa có nhãn (`proposed`), gán lười khi
   tổng hợp, trần `ai_label_budget`; REVIEWER có `can_review` duyệt theo lô.
2. Tổng hợp (`POST /api/v1/synthesis`) trên bộ kết quả: nhóm theo nhóm nội dung nếu có nhãn, không thì
   theo văn bản; lô ≤ `max_evidence_per_batch`, mỗi lượt ≤ `token_budget` và `max_batches_per_run`
   (quản trị viên cấu hình tại `/api/v1/admin/synthesis-settings`, lưu `security_policies`); báo
   "Đã tổng hợp N trong M căn cứ, K nhóm còn lại"; "Tổng hợp tiếp", "Mở rộng phạm vi" (gấp đôi trần).
3. Kiểm tra bằng mã (`synthesis/checks.py`): mã căn cứ thuộc tập đã cấp; số, ngày, số hiệu,
   Điều/Khoản/Điểm phải có trong căn cứ gắn kèm (phần đã gửi cho model); từ kết luận nghiệp vụ ngoài
   ngoặc kép → bỏ ý; thiếu dữ kiện → "chưa kiểm chứng".
4. Hybrid Auto cho `summarize`: nâng cấp API khi không ý local nào qua kiểm tra, hoặc "Phân tích
   sâu"; không có căn cứ → không gọi model.

## 3. Chất lượng (G5)

- `evaluation/coverage/topics.json` (8 chủ đề, 24 cách hỏi) và `run_coverage.py` đo tỷ lệ tìm thấy
  căn cứ bắt buộc với đủ kênh và từng kênh riêng, đọc toàn bộ bộ kết quả qua phân trang.
- `evaluation/coverage/measure_g3_relations.py` đo độ chính xác/độ phủ quan hệ cấp Điều/Khoản.
- **Rerank chuyên dụng (cross-encoder) mới ở mức thử nghiệm.** Mặc định vẫn là LLM local theo lô
  (`EVIDENCE_RERANK_BACKEND=llm`). Đã tích hợp thử Qwen3-Reranker-0.6B trên CPU qua dịch vụ cục bộ
  (`scripts/local_reranker_server.py`, `EVIDENCE_RERANK_BACKEND=cross_encoder`, chỉ địa chỉ loopback) và
  đo trên 100 văn bản: chưa có phương án nào hơn RRF thuần một cách có ý nghĩa thống kê, cả hai rerank
  mất 32 đến 48 giây mỗi câu hỏi trên CPU. Chưa đổi mặc định; xem
  `docs/evidence/2026-11-07-g5-rerank/REPORT.md`. Hai căn cứ chưa tìm thấy ở G5 là lỗi truy xuất ứng
  viên (ngưỡng kênh theo nghĩa), không phải lỗi xếp hạng.
