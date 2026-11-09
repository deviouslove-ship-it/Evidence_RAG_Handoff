# ADR-007 — Chính sách gọi model theo giai đoạn, Hybrid Auto và trần chi phí (G1.0)

- Ngày: 07/11/2026
- Trạng thái: Đã triển khai
- Thay thế: bất biến "tối đa 2 lần gọi LLM mỗi lượt" trong hồ sơ bàn giao (B.3/C.9, WP 3.3),
  SRS §25 (`llm_attempt_budget=2`), ADR-004 mục 4 (số lần thử).
- Căn cứ: thiết kế chốt `docs/thiet-ke-tra-cuu-hieu-luc.md`, quyết định D5, D8; điểm nhất quán 2, 3, 4.

## 1. Bối cảnh

Số lượt gọi model cố định là 2 và chế độ `API` bắt mọi tuyến dùng hồ sơ vùng `public`. Chủ sở hữu
chốt: Local trước; tự nâng cấp lên API (Hybrid Auto) khi kết quả local không đạt hoặc người dùng
chọn phân tích sâu; không nâng cấp vì thiếu căn cứ; tuân thủ quyền, trần chi phí; chế độ Local Only
tuyệt đối không gọi API.

## 2. Quyết định

1. **Chính sách theo giai đoạn** (`stage_policies`, migration `0010`): số lần gửi tối đa mỗi yêu cầu
   (1–10), token ra, thời gian chờ (≤ 30 s, không vượt `EVIDENCE_AI_TIMEOUT_SECONDS`), số yêu cầu đồng
   thời, cho từng cặp (chế độ, giai đoạn). Thiếu dòng thì dùng `LLM_ATTEMPT_BUDGET` (nay 1–10, mặc
   định 2). Mỗi lần gửi HTTP, kể cả lỗi, hết giờ, dự phòng, vẫn trừ một lượt. Không có vòng lặp tự chủ.
2. **Giai đoạn trong Registry:** `answer`, `summarize`, `expand`, `relation`, `label`, `embedding`,
   `rerank`. Khi viết ADR (07/11/2026) ứng dụng chỉ gọi `answer` (cập nhật 09/11/2026: G1–G4 đã nối đủ, xem `ACTIVE_STAGES` trong `model_registry/stages.py`); các giai đoạn khác cấu hình được nhưng chưa dùng.
3. **Hai chế độ giữ nguyên tên:**
   - `LOCAL` = Local Only. Hồ sơ `public` bị từ chối khi lưu tuyến và khi chạy; tuyến LOCAL không
     được có hồ sơ nâng cấp; runtime ở chế độ này không đọc hồ sơ nâng cấp.
   - `API` = Hybrid Auto. Tuyến chính được là hồ sơ local (kiểm theo luật endpoint local); thêm
     `stage_routes.escalation_profile_id` trỏ tới một hồ sơ `public`, chỉ cho giai đoạn có kiểm tra
     bằng mã (`answer`, `summarize`).
4. **Khi nào nâng cấp:** (a) đã có model local thực sự chạy và không kết quả nào qua kiểm tra của ứng
   dụng (với `answer`: JSON đúng dạng và mọi id thuộc tập căn cứ đã đưa), gọi hồ sơ nâng cấp **một lần**;
   (b) người dùng bật "Phân tích sâu" (`deep_analysis`), gọi hồ sơ nâng cấp trước, local làm dự phòng.
   Không có căn cứ thì không gọi model nào, nên không bao giờ nâng cấp vì thiếu căn cứ, không tìm thấy
   hay chưa xác minh hiệu lực. Tuyến local không dùng được (lỗi cấu hình, đang tạm bỏ qua) không phải
   lý do nâng cấp.
5. **Điều kiện đi ra ngoài** giữ nguyên ADR-004: tên miền nằm trong danh sách, HTTPS, người dùng có
   `remote_ai_allowed`, mọi danh mục nguồn cho phép xử lý ngoài, văn bản không `restricted`.
6. **Chi phí:** hồ sơ có giá mỗi triệu token vào/ra và trần ngày/tháng. Đạt trần thì không gửi tới hồ
   sơ đó; kết quả hạ về đường không model (nguyên văn) và báo `ai_limited`. Thiếu số token máy chủ
   báo thì ước tính cao (ký tự/3 cho đầu vào, toàn bộ token ra) để trần dừng sớm hơn là muộn.
7. **Nhật ký:** mỗi lần gửi ghi một dòng `ai_usage_events` (chế độ, giai đoạn, hồ sơ, người, kết quả
   `ok/rejected/unusable/error/unreachable/cancelled`, có nâng cấp, token, thời gian, chi phí ước tính).
   Không lưu câu hỏi, câu trả lời hay nội dung văn bản.
8. **Minh bạch:** phản hồi có `external_ai_used` (đã gửi nội dung căn cứ ra API ngoài) và `ai_limited`;
   giao diện hiện "Đã dùng API ngoài cho lượt này." Admin Portal hiện tuyến nâng cấp, giới hạn đang áp
   dụng và mức dùng ngày/tháng.

## 3. Hệ quả

- Cấu hình đã triển khai vẫn chạy: không có dòng chính sách thì vẫn 2 lượt; tuyến API cũ trỏ thẳng hồ
  sơ `public` vẫn hợp lệ.
- Chính sách, tuyến và mức chi đã dùng được đọc từ DB ở mỗi yêu cầu, nên đổi cấu hình không cần
  khởi động lại. Trạng thái tạm bỏ qua và giới hạn đồng thời vẫn tính trong một process (như ADR-006).
- Trần chi phí kiểm trước khi gửi nên nhiều yêu cầu đồng thời có thể vượt trần một chút (tối đa số lần
  gửi đang chạy).

## 4. Kiểm chứng

`backend/tests/test_ai_policy.py` (Local Only không gọi API kể cả khi bật phân tích sâu; nâng cấp một
lần khi local trả id ngoài tập; giữ kết quả local tốt; phân tích sâu gọi API trước; từ chối khi người
dùng/danh mục không cho phép; không nâng cấp khi local không chạy được; trần chi phí; nhật ký token/chi
phí không chứa nội dung; chính sách thay 2 lượt; không căn cứ thì 0 lần gọi) và
`test_ai_registry_postgres.py::test_hybrid_auto_route_stage_policy_and_cost_cap` trên PostgreSQL thật.
