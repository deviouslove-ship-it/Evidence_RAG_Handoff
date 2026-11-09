# ADR-003 — Đánh giá RAG-Anything cho thuật toán tra cứu

Ngày: 22/10/2026 · Trạng thái: chấp nhận áp dụng ý tưởng có chọn lọc ở POC, chưa tích hợp framework.

## Căn cứ và ranh giới

Đã đọc mã nguồn công khai HKUDS/RAG-Anything tại commit [afb67c43](https://github.com/HKUDS/RAG-Anything/tree/afb67c43d391b1b1008a6fee9f020a232067b9e5) (21/10/2026), gồm [README](https://github.com/HKUDS/RAG-Anything/blob/afb67c43d391b1b1008a6fee9f020a232067b9e5/README.md), [context-aware processing](https://github.com/HKUDS/RAG-Anything/blob/afb67c43d391b1b1008a6fee9f020a232067b9e5/docs/context_aware_processing.md), [query code](https://github.com/HKUDS/RAG-Anything/blob/afb67c43d391b1b1008a6fee9f020a232067b9e5/raganything/query.py), [dependencies](https://github.com/HKUDS/RAG-Anything/blob/afb67c43d391b1b1008a6fee9f020a232067b9e5/pyproject.toml) và [MIT license](https://github.com/HKUDS/RAG-Anything/blob/afb67c43d391b1b1008a6fee9f020a232067b9e5/LICENSE). Đây là nghiên cứu nguồn, không nhập mã, package, model hoặc license notice vào sản phẩm.

Framework kết hợp parser MinerU, LightRAG, mô hình ngôn ngữ/embedding và bộ xử lý ảnh, bảng, công thức; hướng đến truy xuất văn bản và đa phương thức có ngữ cảnh. Dependency lõi khai báo lightrag-hku<1.5 và mineru[core]>=3.4.1; README nêu mô hình MinerU có thể tải khi dùng lần đầu. Hồ sơ hiện hành của app đặt PDF nguyên bản, ACL trong SQL, snapshot hiệu lực đã duyệt và Local Mode không Internet làm điều kiện bắt buộc; SRS §14.2a/§15 coi full LightRAG/GraphRAG là hướng nghiên cứu P2, không là dependency MVP.

## Quyết định

1. Áp dụng nguyên tắc giữ định danh và cấu trúc nguồn khi xếp hạng, nhóm chứng cứ. Trong POC, pipeline ưu tiên Điều và số hiệu văn bản khớp chính xác trong **tập ứng viên đã qua ACL**, đồng thời tách nhóm theo phiên bản tài liệu. Regression test phân biệt Điều 5/Điều 50, hai version và câu có nhiều tham chiếu. Đây chỉ là xếp lại ứng viên và tổ chức chứng cứ, không chứng minh hiệu lực hay độ đúng ngữ nghĩa.
2. Giữ lộ trình retrieval của SRS v1.3: L1_WORD, L2_SYLLABLE, DENSE có điều kiện; Grouped RRF; bounded reference traversal chỉ trên cạnh đã duyệt; resolver hiệu lực toàn chuỗi độc lập. Không dùng graph entity tự suy ra để xác nhận hiệu lực pháp lý.
3. Không thêm RAG-Anything, LightRAG hoặc MinerU vào lockfile/runtime hiện tại. Chỉ mở POC parser/đa phương thức riêng khi đã có PDF công khai thật, kiểm nguồn/bbox/rotation, chính sách model và footprint Windows. Mọi model phải qua Registry và policy; Local Mode không tải model hay gửi dữ liệu ra Internet.
4. Trước rollout bất kỳ thay đổi retrieval nào, đo ablation B0–B7 trên corpus thật + Gold [Không triển khai – xem ADR-010] được duyệt, theo dõi Recall/nDCG@10, wrong_doc/node, missed_exception, false abstention, ACL leakage, P50/P95 và RAM/disk. So sánh cùng corpus hash, model/tokenizer/index/snapshot revision. Test tổng hợp hiện tại không thay phép đo đó.

## Hệ quả hiện tại

Thay đổi nhỏ hoạt động với backend hiện có và không có dependency mới. Chưa có PostgreSQL/pgvector, ingestion PDF thật, bộ Gold [Không triển khai – xem ADR-010], model hoặc đánh giá đa phương thức nên **chưa kết luận nâng chất lượng truy xuất ngoài đời thực**. Candidate generation SQL hiện vẫn là baseline lexical; việc xếp lại chỉ có tác dụng với ứng viên đã được trả về. Đặc biệt, nó không thay exact lookup, kiểm ACL lại khi dẫn chứng, hay validator hiệu lực.
