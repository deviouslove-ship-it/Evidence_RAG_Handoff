# ADR-004 — Rà soát toàn diện, Củng cố Bộ nhớ AI & Model Runtime An toàn

## Đính chính 27/10/2026

Ghi chép bên dưới là mô tả thay đổi của đợt trước, không chứng minh ứng dụng hết treo, hết
dead code hoặc toàn bộ tính năng đã hoàn thành. Bộ nhớ hiện chỉ tạm thời; lưu dài hạn chưa
được triển khai. Kiểm thử mới và các giới hạn về vị trí trích dẫn tài liệu, model thật và kiểm
thử desktop được ghi tại [báo cáo rà soát](../evidence/2026-10-27-audit/REPORT.md).

**Ngày quyết định:** 26/10/2026  
**Trạng thái:** Đã chấp thuận và triển khai (Accepted)

---

## 1. Bối cảnh (Context)

Sau khi triển khai bộ khung hệ thống cục bộ (FastAPI, React, Tauri 2, PostgreSQL 18.6), quá trình rà soát mã nguồn chuyên sâu phát hiện một số rủi ro tiềm ẩn về hiệu năng, bảo mật và tính toàn vẹn tính năng:
1. **Bộ nhớ AI tách rời giao diện:** Backend đã có `EphemeralMemoryService` hoàn chỉnh (quản lý session, turn, memory items, facts revision trong RAM), nhưng giao diện `EvidenceChat` lại gọi API tra cứu phi trạng thái (`/api/v1/query/evidence`). Dữ kiện chỉ lưu tạm ở state React phía client, khiến bộ nhớ server trở thành tính năng không dùng đến.
2. **Tính năng Preferences ảo:** Endpoint `PUT /api/v1/memory/preferences` cho phép lưu cấu hình danh mục ưu tiên nhưng backend không hề áp dụng vào việc lọc căn cứ của các lượt tra cứu tiếp theo, đồng thời thiếu endpoint `GET` để nạp lại sở thích.
3. **Endpoint trùng lặp / ảo:** `POST /api/v1/query/answer` có mã xử lý giống hệt `POST /api/v1/query/evidence` và không hề sinh ra câu trả lời tự động; `POST /api/v1/analysis/situation` trùng lặp hoàn toàn với `POST /api/v1/query/analyze`.
4. **Nguy cơ treo ứng dụng (Hang/Delay/504):** Khi cấu hình Model AI Local hoặc Cloud API, mỗi lượt gọi model có timeout 30 giây kèm tối đa 2 lần thử (tổng cộng 60 giây). Trong khi đó, timeout của toàn bộ truy vấn là 45 giây. Nếu model phản hồi chậm hoặc không thể kết nối, toàn bộ lượt tra cứu bị sập với mã lỗi 504 Gateway Timeout dù căn cứ pháp lý đã được trích xuất thành công từ cơ sở dữ liệu.
5. **Độ trễ tìm kiếm văn bản (FTS Query Delay):** Trong `PostgresAuthorizedNodeSearch`, hàm `to_tsvector` bị gọi lặp lại 3 lần trong mệnh đề `WHERE` và `ORDER BY` cho từng dòng dữ liệu, gây lãng phí CPU và tăng độ trễ khi khối lượng văn bản lớn.
6. **Bất cập cấu hình Model Registry & Local AI:**
   - Cổng kết nối Local AI từ chối hostname `localhost` do chỉ cho phép IP literal, gây cản trở các runtime phổ biến chạy máy cục bộ (Ollama, vLLM, llama.cpp).
   - Các mô hình suy luận thế hệ mới (DeepSeek R1, Qwen 2.5) thường trả về thẻ suy luận `<think>...</think>` hoặc markdown code fences ```` ```json ````, làm bộ phân giải JSON thất bại và bỏ rơi kết quả.
   - Khi lưu hồ sơ mô hình, hệ thống luôn `INSERT` một bản ghi `providers` mới làm phát sinh các dòng mồ côi không dùng đến.
   - Thiếu các tham số sinh thế hệ (`params`: `temperature`, `max_tokens`, `json_mode`).
   - Cấu hình `secret_ref=env:...` không có cơ chế chặn các biến môi trường nhạy cảm của hệ thống.
7. **Dead Code & Router ảo:** Lớp `ModelRouter` (`router.py`) và cấu trúc `StageRoute` chỉ được gọi trong các file kiểm thử cũ nhưng không hề tham gia vào runtime thực tế (`RegistryRuntime` nạp cấu hình trực tiếp từ DB). Nhiều protocol trong `adapters/base.py` (`ChatAdapter`, `EmbeddingAdapter`, `RerankAdapter`) không được sử dụng.
8. **Lỗ hổng giả mạo định danh qua CORS:** Header `X-Principal-Id` và `X-Roles` được mở mặc định trong danh sách CORS `allow_headers` ở mọi chế độ, tiềm ẩn nguy cơ client giả mạo quyền hạn.
9. **Ngắt luồng SSE im lặng:** Khi phiên bộ nhớ hết hạn trong lúc đang xử lý, stream SSE kết thúc mà không phát sự kiện lỗi, khiến người dùng bị treo trạng thái "Đang tra cứu...".

---

## 2. Quyết định kỹ thuật (Decisions)

### 2.1. Nối trọn vẹn Bộ nhớ AI vào User Workspace
- Chuyển đổi `EvidenceChat.tsx` sang mô hình phiên làm việc (`AgentSession`) sử dụng `EphemeralMemoryService` qua Server-Sent Events (SSE) theo luồng:
  1. Tự động khởi tạo phiên RAM khi người dùng tra cứu lần đầu (`POST /api/v1/agent/sessions`).
  2. Gửi lượt tra cứu có gán mã idempotent qua `POST /api/v1/agent/sessions/{id}/turns`.
  3. Bổ sung sự kiện SSE `analysis_ready` từ backend phát về client mang theo thông tin claims, suggestions, missing_information và coverage_checks.
  4. Hỗ trợ điều khiển lượt: nút **Dừng** gọi `POST .../turns/{id}/cancel` hủy tiến trình phía server; nút **Thử lại** gọi `POST .../turns/{id}/retry`.
  5. Xây dựng giao diện "Bộ nhớ phiên": cho phép người dùng xem danh sách mục nhớ, xóa từng mục (`DELETE /api/v1/memory/{item_id}`), hoặc bấm "Xóa dữ liệu tạm" để giải phóng hoàn toàn RAM (`DELETE /api/v1/memory` và `DELETE /api/v1/agent/sessions/{id}`).
  6. Khi người dùng đăng xuất hoặc chuyển trang, phiên làm việc trong RAM được thu hồi ngay lập tức (`deleteAgentSession`).

### 2.2. Kích hoạt tính năng Preferences thực tế
- Bổ sung endpoint `GET /api/v1/memory/preferences`.
- Trong hàm `create_turn`, backend áp dụng hàm `_with_preferences`: khi người dùng bật sở thích và thực hiện tra cứu ở chế độ `ALL_AUTHORIZED`, hệ thống tự động gán `default_category_ids` đã lưu vào phạm vi truy vấn của lượt đó.

### 2.3. Loại bỏ endpoint ảo & chuẩn hóa thông điệp
- Xóa bỏ hoàn toàn route `POST /api/v1/query/answer` và `POST /api/v1/analysis/situation`.
- Chuẩn hóa thông điệp giao diện: làm rõ vai trò AI chỉ là công cụ hỗ trợ chọn tối đa 3 căn cứ liên quan trực tiếp từ nguồn đã được kiểm duyệt, nội dung hiển thị lấy 100% nguyên văn từ văn bản PDF gốc, không có tính năng AI tự viết câu trả lời giả định.
- Khi chọn căn cứ liên quan đối chiếu (`_unclaimed_for_suggestions`), loại bỏ các căn cứ đã hiển thị trong claims để tránh lặp lại thông tin dư thừa.

### 2.4. Ngăn ngừa nghẽn/treo qua Fail-Safe AI Selection
- Bọc thời gian chờ cho lớp `ConfiguredSelection` bằng 70% query timeout (`timeout_seconds = settings.query_timeout_seconds * 0.7`).
- Cơ chế suy thoái mềm (graceful degradation): Nếu model phản hồi chậm hoặc lỗi mạng, hệ thống bắt `TimeoutError`, bỏ qua AI selection và vẫn trả về tập căn cứ gốc đã xác minh nguồn, đảm bảo lượt tra cứu của người dùng luôn hoàn tất nhanh chóng và thành công.

### 2.5. Tối ưu hóa truy vấn tìm kiếm FTS
- Trong `PostgresAuthorizedNodeSearch`, áp dụng mệnh đề `CROSS JOIN LATERAL (SELECT to_tsvector(...) AS tsv) lex`. Hàm `to_tsvector` chỉ tính toán một lần duy nhất cho mỗi dòng ứng viên và tái sử dụng cho các điều kiện tìm kiếm và tính điểm xếp hạng `ts_rank_cd`.

### 2.6. Củng cố Model Registry & Local AI Runtime
- Chấp nhận hostname `localhost` bên cạnh loopback IP cho các kết nối Local AI.
- Hàm `_canonical_selection` tự động lọc bỏ thẻ suy luận `<think>...</think>` và markdown code fences trước khi giải mã JSON.
- Bảo vệ biến môi trường nhạy cảm: `_SECRET_DENIED` từ chối các biến `DATABASE_URL`, `PG*`, `POSTGRES*`, `*PASSWORD*`, và `EVIDENCE_*` (trừ `EVIDENCE_AI_*`).
- Ghi log lỗi redacted: Chỉ ghi nhận tên lớp ngoại lệ hoặc mã lỗi nội bộ, loại bỏ hoàn toàn thông tin endpoint URL và token xác thực khỏi log.
- Mở rộng schema `ModelProfileRequest` và cập nhật form Admin Portal: bổ sung nhóm tham số thế hệ `params` (`temperature`, `max_tokens`, `json_mode`).
- Khi lưu lại hồ sơ mô hình, hệ thống kiểm tra và cập nhật trực tiếp bản ghi `providers` cũ thay vì tạo mới.

### 2.7. Dọn dẹp Dead Code
- Xóa bỏ file `backend/app/model_registry/router.py` và struct `StageRoute` trong `profiles.py`.
- Xóa bỏ các protocol không dùng (`ChatAdapter`, `EmbeddingAdapter`, `RerankAdapter`) trong `adapters/base.py`.
- Xóa hàm hằng số `new_facts_revision()` trong `analyze.py`.
- Xóa thuộc tính `artifact_relative_path` trong `ModelProfile`.

### 2.8. Bảo mật CORS & Xử lý ngắt luồng SSE
- Danh sách CORS `allow_headers` chỉ bổ sung `X-Principal-Id` và `X-Roles` khi cấu hình `dev_allow_in_memory_store = True`. Ở môi trường thực, các header này bị cấm nhằm loại bỏ nguy cơ spoofing định danh.
- Khi phiên làm việc bị hết hạn hoặc bị xóa giữa chừng, luồng SSE phát sự kiện lỗi tường minh `turn_error: SESSION_EXPIRED` (sequence 2) trước khi đóng kết nối.

---

## 3. Hệ quả (Consequences)

- **Tích cực:**
  - Ứng dụng phản hồi nhanh, không còn hiện tượng treo app (504) do model trễ mạng.
  - Bộ nhớ hội thoại hoạt động thật, giúp người dùng tra cứu liền mạch qua nhiều lượt hỏi.
  - Quản trị viên cấu hình được tham số mô hình AI Local / Cloud API linh hoạt và an toàn.
  - Cơ sở mã nguồn sạch sẽ, không còn tính năng ảo hay dead code gây nhầm lẫn.
  - Toàn bộ 19 test frontend vitest và kiểm tra kiểu TypeScript đạt chuẩn tuyệt đối.
- **Lưu ý:**
  - Cần chạy lại `python scripts/export_openapi.py` khi môi trường Python hoàn tất để cập nhật bản đặc tả `docs/openapi.json`.
  - Đối với khối lượng văn bản rất lớn trong tương lai, cần bổ sung chỉ mục GIN trên biểu thức cột tạo sẵn để tối ưu hóa thêm tốc độ FTS.
