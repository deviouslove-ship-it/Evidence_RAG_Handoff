# Spec: Model Registry (AI Local / AI API), bản dịch

**Ngôn ngữ / Language:** Tiếng Việt · bản chuẩn: [`.kiro/specs/model-registry/`](../../../../.kiro/specs/model-registry/)

> Spec dựng lại từ mã nguồn đã triển khai ngày 09/11/2026 (`Spec reconstructed from the implemented code on 2026-11-09`). Không phải spec lịch sử do Kiro tạo. Quyết định: ADR-002, ADR-004, ADR-007.

## Giới thiệu
Mỗi lần dùng model là một giai đoạn có tên. Quản trị viên đăng ký hồ sơ Local hoặc API, kiểm tra và phân công theo giai đoạn và chế độ vận hành, dưới chính sách egress và chi phí.

## Yêu cầu (EARS)

**Y1. Hồ sơ.**
1. WHEN SYS_ADMIN thêm hồ sơ THE SYSTEM SHALL lưu adapter, endpoint, model ID, khả năng, phiên bản, vùng dữ liệu, trạng thái phê duyệt và sức khỏe (`model_registry/profiles.py`, `POST /api/v1/admin/model-registry`).
2. THE SYSTEM SHALL cung cấp form "Thêm AI Local" (Ollama, vLLM, llama.cpp) và "Thêm AI API" (OpenAI, Gemini, tùy chỉnh tương thích OpenAI) (`components/ai/ProfileEditor.tsx`).
3. WHEN lưu khóa API THE SYSTEM SHALL mã hóa bằng Windows DPAPI gắn tài khoản chạy server và KHÔNG trả khóa qua bất kỳ API nào (`secret_store.py`).

**Y2. Kiểm tra trước khi dùng.**
1. WHEN quản trị viên kiểm tra hồ sơ nháp hoặc đã lưu THE SYSTEM SHALL kiểm chính sách, khóa, kết nối, sự có mặt của model và phản hồi, báo từng bước (`diagnostics.py`, `POST /model-registry/test`, `/{id}/test`, `/{id}/probe`).
2. IF kiểm tra thất bại THEN THE SYSTEM SHALL chỉ cho lưu khi quản trị viên chọn rõ "Vẫn lưu (chưa dùng được)" và KHÔNG đánh dấu hồ sơ sẵn sàng.

**Y3. Phân công theo giai đoạn.**
1. THE SYSTEM SHALL hỗ trợ các giai đoạn `answer`, `summarize`, `expand`, `relation`, `label`, `embedding`, `rerank` (`stages.py`).
2. WHEN quản trị viên phân công hồ sơ THE SYSTEM SHALL kiểm tra và áp dụng theo giai đoạn và chế độ (`POST /model-registry/routes`), kèm hồ sơ dự phòng và nâng cấp tùy chọn.
3. WHEN model không kết nối được THE SYSTEM SHALL bỏ qua trong một khoảng thời gian và giảm xuống trả căn cứ gốc thay vì để lượt chat treo.
4. THE SYSTEM SHALL tách việc đổi model "Diễn giải AI" khỏi đổi model embedding: chỉ việc sau cần dựng lại chỉ mục.

**Y4. Chính sách egress.**
1. IF chế độ là `LOCAL` THEN THE SYSTEM SHALL từ chối hồ sơ `public` và KHÔNG gọi API ngoài (`REMOTE_AI_DENIED`).
2. WHEN chế độ là `API` THE SYSTEM SHALL chỉ gửi nội dung ra ngoài nếu miền endpoint nằm trong danh sách cho phép, truyền HTTPS, người dùng có `remote_ai_allowed`, mọi danh mục nguồn cho phép xử lý ngoài và văn bản không `restricted` (nếu không: `AI_EGRESS_DENIED`).
3. THE SYSTEM SHALL giới hạn `embedding` và `rerank` ở hồ sơ local ở cả hai chế độ.

**Y5. Chính sách Hybrid Auto và trần chi phí.**
1. THE SYSTEM SHALL đọc giới hạn theo (chế độ, giai đoạn) từ `stage_policies`: số lần gửi 1–10, token ra tối đa 16.384, thời gian chờ tối đa 30 s, đồng thời 1–64 (`stages.py::StagePolicy`).
2. WHEN kết quả local của `answer` hoặc `summarize` không qua kiểm tra bằng mã, hoặc người dùng chọn phân tích sâu, THE SYSTEM SHALL nâng cấp một lần lên hồ sơ API đã cấu hình, chỉ ở chế độ API.
3. IF không có căn cứ THEN THE SYSTEM SHALL KHÔNG gọi model.
4. WHEN đạt trần chi phí ngày hoặc tháng THE SYSTEM SHALL ngừng gửi tới hồ sơ đó và giảm xuống đường không model, báo `ai_limited`.
5. THE SYSTEM SHALL ghi mỗi lần gọi vào `ai_usage_events` không kèm câu hỏi, câu trả lời hay nội dung văn bản, và SHALL báo `external_ai_used`.

**Y6. Kiểm toán.**
1. WHEN hồ sơ, tuyến hoặc chính sách thay đổi THE SYSTEM SHALL ghi sự kiện kiểm toán.

## Thiết kế (tóm tắt)

| Mối quan tâm | Tệp |
|---|---|
| Hồ sơ và tuyến | `model_registry/profiles.py`, `runtime.py` |
| Giai đoạn và chính sách | `stages.py`, migration `0010_ai_policy`, `backend/app/ai_limits.py` |
| Adapter nhà cung cấp | `adapters/base.py`, `openai_compatible.py` |
| Chẩn đoán | `diagnostics.py` |
| Kho khóa | `secret_store.py` |
| Chọn giai đoạn trong pipeline | `workflow/ai_selection.py` |
| API | `api/v1/admin.py` (`/model-registry*`) |
| Giao diện | `frontend/src/components/ai/` |
| Cấu hình mẫu | `configs/model-registry.example.yaml`, `ai-runtime.env.example`, `security-policy.example.yaml` |

Định tuyến: mỗi lời gọi giai đoạn → chế độ. LOCAL chỉ dùng hồ sơ local. API dùng hồ sơ local chính, nâng cấp một lần lên hồ sơ API khi kiểm tra không đạt hoặc phân tích sâu; tất cả qua bộ chặn egress và chi phí → adapter OpenAI-compatible → `ai_usage_events`.

Quyết định: quy tắc cứng (egress, nâng cấp, giai đoạn chỉ local) nằm trong mã, không trong prompt hay công tắc từng hồ sơ. Endpoint `localhost` hiểu theo máy chủ backend, không theo máy trạm. Lưu hồ sơ không qua kiểm tra chỉ khi có đồng ý rõ và không bao giờ làm hồ sơ dùng được.

Giới hạn: báo cáo giao diện Model Registry ghi chưa kiểm thật OpenAI/Gemini và chưa kiểm trong Tauri (`docs/evidence/2026-11-08-model-registry-ui/REPORT.md`). Lần chạy Hybrid Auto API trong báo cáo G4 dùng lời gọi API thật như đã ghi ở đó; cả hai chưa chạy lại khi viết spec.

## Tasks
- [x] 1. Hồ sơ không phụ thuộc nhà cung cấp và adapter tương thích OpenAI
- [x] 2. Định nghĩa giai đoạn và bảng chính sách theo giai đoạn (migration `0010`)
- [x] 3. Nâng cấp Hybrid Auto, trần chi phí, nhật ký sử dụng (ADR-007)
- [x] 4. Chẩn đoán cho hồ sơ nháp và đã lưu
- [x] 5. Kho khóa DPAPI
- [x] 6. API quản trị
- [x] 7. Giao diện hai form và bảng phân công (có test)
- [x] 8. Test chính sách (`test_ai_policy.py`, `test_ai_registry_postgres.py`)
- [ ] 9. Kết nối thật OpenAI và Gemini (báo cáo 08/11/2026 ghi chưa làm)
- [ ] 10. Kiểm giao diện Model Registry trong vỏ Tauri (báo cáo ghi chưa làm)
