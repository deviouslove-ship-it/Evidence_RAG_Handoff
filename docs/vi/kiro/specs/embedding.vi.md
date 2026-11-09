# Spec: Quản lý embedding, bản dịch

**Ngôn ngữ / Language:** Tiếng Việt · bản chuẩn: [`.kiro/specs/embedding/`](../../../../.kiro/specs/embedding/)

> Spec dựng lại từ mã nguồn đã triển khai ngày 09/11/2026 (`Spec reconstructed from the implemented code on 2026-11-09`). Không phải spec lịch sử do Kiro tạo. Quyết định: ADR-009 mục 1.

## Giới thiệu
Tìm theo nghĩa cần một chỉ mục vector cho mỗi model và số chiều. Quản trị viên đổi model qua tác vụ nền có kiểm soát, và chỉ mục đang phục vụ vẫn dùng được cho đến khi chỉ mục mới được kiểm tra.

## Yêu cầu (EARS)

**Y1. Một chỉ mục cho mỗi model và số chiều.**
1. THE SYSTEM SHALL lưu vector trong `node_embeddings` không cố định chiều và ghi model, phiên bản, số chiều trong `embedding_indices`, mỗi chỉ mục có HNSW riêng (migration `0012_comprehensive_search.sql`).
2. THE SYSTEM SHALL tạo embedding từ số hiệu, nhãn trích dẫn và chữ khoản, tối đa 800 ký tự.
3. THE SYSTEM SHALL yêu cầu model embedding của câu hỏi khớp chỉ mục đang phục vụ.

**Y2. Preflight trước khi đổi.**
1. WHEN quản trị viên kiểm tra model THE SYSTEM SHALL thử kết nối, vector, số chiều, quyền, số nút và báo ước tính (`POST /api/v1/admin/embeddings/preflight`, `embedding_jobs.py::preflight`).
2. IF chế độ, chính sách endpoint hoặc vùng dữ liệu không cho phép THEN THE SYSTEM SHALL từ chối kèm mã lỗi (`remote_embedding_allowed`).

**Y3. Tác vụ nền.**
1. WHEN quản trị viên xác nhận THE SYSTEM SHALL tạo tác vụ và xử lý theo lô (mặc định 16, tối đa 256) trong tiến trình API, mỗi lần một tác vụ (`EmbeddingWorker`).
2. THE SYSTEM SHALL hỗ trợ tạm dừng, tiếp tục, thử lại, hủy theo trạng thái: tạm dừng từ queued/running, tiếp tục từ paused, thử lại từ failed, hủy từ queued/paused/failed.
3. WHEN một lô lỗi THE SYSTEM SHALL thử lại với backoff và đánh dấu failed sau 5 lần lỗi liên tiếp hoặc lỗi vĩnh viễn.
4. THE SYSTEM SHALL hiển thị tiến độ, tốc độ, ước tính và lỗi.

**Y4. Chuyển chỉ mục đã kiểm tra.**
1. WHEN mọi nút đã có vector THE SYSTEM SHALL kiểm chỉ mục và kiểm mẫu trước khi kích hoạt.
2. IF kiểm tra không đạt THEN THE SYSTEM SHALL giữ chỉ mục cũ phục vụ và đánh dấu tác vụ failed.
3. THE SYSTEM SHALL KHÔNG BAO GIỜ tự xóa chỉ mục cũ.
4. WHEN có nút mới được duyệt THE SYSTEM SHALL cho phép "kiểm tra và bổ sung vector còn thiếu".

**Y5. Giai đoạn chỉ chạy local.**
1. THE SYSTEM SHALL chỉ gửi giai đoạn `embedding` và `rerank` tới hồ sơ local, không bao giờ tới hồ sơ `public`, ở cả hai chế độ (`model_registry/stages.py::LOCAL_ONLY_STAGES`).
2. IF không có vector THEN THE SYSTEM SHALL vẫn phục vụ tìm từ khóa.

## Thiết kế (tóm tắt)

| Mối quan tâm | Tệp |
|---|---|
| Lưu và tìm vector | `storage/embeddings.py`, migration `0012` |
| Tác vụ, preflight, worker | `storage/embedding_jobs.py`, migration `0014_embedding_jobs` |
| API | `api/v1/admin.py` (`/embeddings`, `/embeddings/preflight`, `/embeddings/jobs`, `/embeddings/jobs/{id}/{action}`) |
| CLI | `scripts/build_embeddings.py` (`--rebuild`) |
| Giao diện | `frontend/src/components/EmbeddingManager.tsx` |
| Model tham chiếu | `qwen3-embedding:0.6b`, 1024 chiều, qua Ollama (ADR-009) |

Vòng đời tác vụ: queued → running → (paused ↔ queued) / failed → (retry → queued) / cancelled / completed (đã kiểm và kích hoạt).

Quyết định: chỉ mục cũ tiếp tục phục vụ trong lúc xây chỉ mục mới; chỉ kích hoạt khi báo cáo chỉ mục và kiểm mẫu đạt. Chỉ mục là lịch sử, ứng dụng không xóa. Embedding từ xa cần chế độ API cùng cả hai cờ xử lý từ xa và embedding từ xa trong chính sách endpoint.

Giới hạn: báo cáo của tính năng này ghi lần chạy với Ollama thật, chưa chạy lại khi viết spec (`docs/evidence/2026-11-07-embedding-admin/REPORT.md`).

## Tasks
- [x] 1. Bảng vector không cố định chiều và HNSW theo model (migration `0012`)
- [x] 2. Script xây embedding
- [x] 3. Bảng tác vụ và cột vòng đời chỉ mục (migration `0014`, có tệp down)
- [x] 4. Preflight
- [x] 5. Điều khiển tác vụ và worker có backoff
- [x] 6. API quản trị
- [x] 7. Giao diện quản trị và test
- [x] 8. Báo cáo đã ghi
- [ ] 9. Chạy lại việc chuyển embedding với model thứ hai thật và ghi kết quả (chưa chạy lại khi viết spec)
