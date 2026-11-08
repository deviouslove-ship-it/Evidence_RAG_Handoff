# Quản lý embedding trong Admin Portal — 07/11/2026

## Phạm vi

Quản trị viên đổi, thêm hoặc nâng cấp model embedding hoàn toàn trên giao diện; hệ thống tự
tạo lại vector cho các nút Điều/Khoản/Điểm đã duyệt bằng tác vụ nền, giữ chỉ mục cũ phục vụ
tìm kiếm đến khi chỉ mục mới được kiểm tra và chuyển trong một transaction.

Tái sử dụng: migration 0012 (cột vector không cố định chiều, trạng thái chỉ mục),
`storage/embeddings.py` (tách thành các bước dùng chung), `scripts/build_embeddings.py` (gọi
cùng các bước), Model Registry (hồ sơ, probe, chính sách endpoint, audit). Không thêm phụ thuộc
runtime mới (chỉ stdlib, asyncpg, httpx, pgvector đã có).

## Thành phần

| Thành phần | Nội dung |
|---|---|
| `migrations/0014_embedding_jobs.sql` (+ `.down.sql`) | Bảng `embedding_jobs`; trạng thái chỉ mục thêm `paused`, `failed`; cột `last_error`, `verified_at`, `activated_at`, `retired_at`. Không xóa dữ liệu. |
| `storage/embeddings.py` | Tập nút cần phủ dùng chung; mở/dùng lại chỉ mục; HNSW `CONCURRENTLY` (REINDEX nếu hỏng, không DROP); `halfvec` cho 2001–4000 chiều; kiểm tra toàn vẹn; chuyển chỉ mục trong một transaction. |
| `storage/embedding_jobs.py` | Kiểm tra trước (preflight), tạo tác vụ sau xác nhận, tạm dừng/tiếp tục/thử lại/hủy, `EmbeddingWorker` chạy trong tiến trình API. |
| `storage/comprehensive.py` | Vector câu hỏi luôn lấy từ hồ sơ của chỉ mục đang hoạt động; model khác chỉ mục thì kênh theo nghĩa tạm dừng và báo rõ. |
| `model_registry/runtime.py` | `EmbeddingOutcome.error` (mã lỗi đã ẩn chi tiết); chính sách embedding qua API ngoài; tác vụ nền tự giãn cách thay cho cool-down tương tác. |
| `api/v1/admin.py` | `GET /admin/embeddings`, `POST /admin/embeddings/preflight`, `POST /admin/embeddings/jobs` (cần `confirmed: true`), `POST /admin/embeddings/jobs/{id}/{pause|resume|retry|cancel}`; mọi thao tác ghi audit. |
| Frontend | Vai trò model trong form hồ sơ (embedding riêng, tùy chọn số chiều); mục "Embedding (tìm theo nghĩa)" trong AI & Kiểm toán. |
| Gói portable | `config/evidence.env`: `EVIDENCE_REMOTE_EMBEDDING_ALLOWED=false`, `EVIDENCE_EMBEDDING_WORKER=true`; README mục 5a. Mã mới nằm trong `backend/app` nên `package-portable.ps1` tự đóng gói. |

## Quy trình

1. Hồ sơ vai trò `embedding` (local hoặc `public` nếu chính sách cho phép).
2. Kiểm tra model: vai trò, phê duyệt, chính sách, địa chỉ/khóa, `GET /models`, vector thử
   (số hữu hạn, khác 0), số chiều yêu cầu, lưu trữ (`vector` ≤ 2000, `halfvec` ≤ 4000), văn
   bản được phép gửi ra ngoài (hồ sơ `public`). Trả số nút trong kho, đã có vector của model
   này, cần tạo, ước tính thô thời gian.
3. Xác nhận → tác vụ `queued`, route `embedding` của chế độ hiện hành trỏ tới hồ sơ đã chọn
   (chỉ giai đoạn embedding; các giai đoạn khác không đổi).
4. Worker: khóa advisory để chỉ một tác vụ chạy; theo lô; nhịp tim 15 giây; tác vụ `running`
   quá 60 giây không có nhịp tim được xếp lại hàng đợi; dừng máy chủ đúng cách thì xếp lại ngay.
   Lỗi tạm thời: giãn cách 15/30/60/120/120 giây, giảm lô khi quá thời gian; 5 lần liên tiếp →
   `failed`. Lỗi cấu hình (hồ sơ đổi model giữa chừng, chưa duyệt, khóa thiếu…) → `failed` ngay.
5. Hết nút: dựng HNSW, kiểm tra (đủ nút, đúng chiều, HNSW hợp lệ, có vector, tạo lại một vector
   mẫu có cosine ≥ 0,95), chuyển chỉ mục; chỉ mục cũ thành `retired`, giữ vector và HNSW.

Nút được duyệt mới sau khi chuyển được báo "N nút mới chưa có vector" và bổ sung bằng tác vụ
`catch_up` vào chỉ mục đang dùng. Đổi về model cũ dùng lại chỉ mục `retired` của nó.

## Kết quả kiểm thử (máy dev, 07/11/2026)

- `scripts/verify.ps1 -ProgramsRoot E:\Programs` 12/12 đạt (`verify/summary.json`): backend
  **225 passed** với PostgreSQL thật, không bỏ qua test nào (trước đó 218); frontend **77 passed**
  (trước đó 74); lint, mypy, OpenAPI, migration, chính sách mã nguồn, build đều đạt.
- `test_embedding_jobs_postgres.py` (schema tạm, 3–4 nút HƯ CẤU, dịch vụ embedding giả qua
  HTTP transport): tạo chỉ mục đầu; đổi model khác số chiều, dịch vụ lỗi sau một lô → tác vụ
  `failed` sau 5 lần, chỉ mục cũ vẫn phục vụ (vector câu hỏi 8 chiều); thử lại → chạy tiếp từ
  vector đã lưu, chuyển (12 chiều), chỉ mục cũ `retired` giữ 3 vector và HNSW hợp lệ; nút mới →
  `catch_up`, tạm dừng/tiếp tục; quay về model cũ dùng lại vector (chỉ gửi 1 nút); tác vụ bị bỏ
  dở bởi tiến trình chết được phục hồi; model không ổn định → `EMBEDDING_SAMPLE_MISMATCH`, không
  chuyển; 2100 chiều dùng `halfvec` và tìm được; 4100 chiều bị từ chối ở bước kiểm tra; script
  `build_embeddings` vẫn chạy. Cuối test không có vector nào bị xóa. Test API: quyền (USER 403),
  thiếu xác nhận 422, thao tác sai trạng thái 409, audit đủ.
- Model thật (`smoke_real_model.py`, kết quả `smoke-real-model.json`): Ollama local,
  `qwen3-embedding:0.6b`, 12 nút HƯ CẤU, qua HTTP API và worker nền. Lần 1: 1024 chiều, dừng
  worker giữa chừng (tác vụ về `queued`), worker mới chạy tiếp, hoàn tất 12/12, không lỗi.
  Lần 2: cùng model, hồ sơ yêu cầu 256 chiều → kiểm tra đạt 256/256; trong lúc tạo, chỉ mục
  đang phục vụ vẫn là 1024 chiều; sau khi chuyển, câu hỏi 256 chiều, kênh theo nghĩa trả 5 kết
  quả, 0 nút thiếu vector; chỉ mục 1024 chiều `retired` còn đủ 12 vector.
- Migration 0014 chạy thử trên DB `evidence_rerank_eval` (7.230 vector) trong transaction rồi
  `ROLLBACK`: ràng buộc trạng thái thay đúng, dữ liệu không đổi.

## Giới hạn còn lại

- Ước tính thời gian ở bước kiểm tra là ước tính thô từ một lần gọi; thời gian còn lại của tác
  vụ đang chạy tính theo tốc độ thực (trung bình trượt).
- Phục hồi sau sự cố tiến trình mất tối đa khoảng 60 giây (ngưỡng nhịp tim).
- Một tác vụ chạy tại một thời điểm; các tác vụ khác xếp hàng theo thứ tự tạo. Tác vụ hoàn tất
  sau cùng là chỉ mục được dùng.
- Embedding qua API ngoài chưa thử với nhà cung cấp thật trong đợt này (chỉ kiểm tra chính sách
  bằng test).
- Không có chức năng xóa chỉ mục cũ trên giao diện (theo yêu cầu không tự xóa); dọn dẹp, nếu cần,
  là quyết định vận hành riêng.
