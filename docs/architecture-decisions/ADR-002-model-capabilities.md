# ADR-002 — Model Registry theo capability & Runtime Bounded

**Trạng thái:** Đã cập nhật và củng cố kỹ thuật (26/10/2026).

## Quyết định

- Registry lưu adapter, endpoint, model ID/revision, capability, privacy zone, params (temperature, top_p, max_tokens, json_mode), secret reference, fallback và health trong PostgreSQL (`model_profiles`, `stage_routes`, `providers`).
- Runtime thực thi là `RegistryRuntime`:
  - Nạp tuyến đường (`stage_routes`) và hồ sơ (`model_profiles`) động từ cơ sở dữ liệu cho mỗi thao tác.
  - Sử dụng adapter chuẩn `openai_compatible` hỗ trợ cả Local AI (`ollama_local`, `vllm_local`, `llama_cpp_local`) và Remote OpenAI-compatible API.
  - Loại bỏ router tĩnh `router.py` và các protocol trừu tượng chưa sử dụng trong code để tránh dead code.
- Cơ chế bảo vệ và xử lý thực tế:
  1. **Hỗ trợ Local AI:** Chấp nhận hostname `localhost` và địa chỉ loopback cục bộ cho các endpoint Local AI.
  2. **Làm sạch định dạng suy luận (Unwrap Reasoning):** Tự động bóc tách các khối suy luận `<think>...</think>` và markdown code fences ```` ```json ```` trước khi parse canonical JSON `{"evidence_ids": [...]}`, tương thích với các mô hình suy luận hiện đại (Qwen 2.5, DeepSeek R1).
  3. **Bảo mật Secret Reference:** `secret_ref` chỉ cho phép cú pháp `env:VAR_NAME` và cấm triệt để các biến môi trường nhạy cảm của hệ thống (`DATABASE_URL`, `PG*`, `POSTGRES*`, `*PASSWORD*`, `EVIDENCE_*` ngoại trừ `EVIDENCE_AI_*`).
  4. **Timeout & Suy thoái mềm (Graceful Degradation):** Bước chọn căn cứ qua AI được giới hạn bằng 70% query timeout. Nếu model phản hồi chậm hoặc lỗi, hệ thống ghi log mã lỗi bảo mật (redacted log) và bỏ qua AI selection, trả về trọn vẹn tập căn cứ đã xác minh nguồn gốc mà không làm đứt gãy luồng truy vấn (chống lỗi 504 Gateway Timeout).
  5. **Chống mồ côi tài nguyên:** Khi Admin cập nhật hồ sơ, hệ thống cập nhật trực tiếp bản ghi `providers` tương ứng thay vì tạo dòng mới vô tội vạ.
- Router chọn profile theo `(mode, stage)`; mode gồm `API` hoặc `LOCAL`.
- `remote_allowed` là điều kiện AND đầy đủ: API mode + scope category + candidate document + user permission + provider approved + payload policy.
- Local Mode từ chối profile remote bằng `REMOTE_AI_DENIED` và không fallback sang API.
- Tổng ngân sách LLM mỗi run là tối đa hai request đã gửi, tính timeout/error/fallback. Fact extraction và rules phân tích dùng code Python xác định.
- Endpoint test (`/probe`) dùng GET `/models` đối soát model ID; secret chỉ lưu reference, không bao giờ gửi raw key về frontend.
- Giao diện Admin Portal hỗ trợ chỉnh sửa `temperature`, `max_tokens`, ép kiểu JSON `json_mode`, kiểm tra kết nối (`probe`) và phân tầng 3 tab con trực quan.

## Hệ quả

- Thay model của adapter đã hỗ trợ chỉ qua cấu hình, không sửa source.
- Chưa có model/key thật thì API trả evidence/extractive thật với `answer_generated=false`; adapter chỉ chọn căn cứ, không sinh quote mới.
- Không bị treo hoặc crash app khi model local/cloud bị trễ mạng hoặc crash.

## Việc còn chưa chứng minh

Chưa có đánh giá hiệu năng trên phần cứng yếu chuyên biệt (Raspberry Pi/CPU thuần) hoặc Local offline không GPU.
