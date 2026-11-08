# Thiết kế lại giao diện Model Registry (08/11/2026)

## Kết quả

Mục "Mô hình AI & Kiểm toán" có bốn tab: **1. Mô hình AI**, **2. Phân công AI**, **Embedding** (giữ nguyên), **3. Nhật ký Kiểm toán**.

| Yêu cầu | Cách làm |
|---|---|
| Hai form riêng | **AI Local**: Tên hồ sơ, Runtime (Ollama/vLLM/llama.cpp), Địa chỉ máy chủ (tự điền theo runtime), Model ID. **AI API**: Tên hồ sơ, Nhà cung cấp (OpenAI/Gemini/Tùy chỉnh), Base URL (tự điền, sửa được), Model ID, API Key (ô mật khẩu). |
| Ẩn tham số mặc định | Adapter, nhiệt độ, token, mức suy luận, JSON mode, vùng dữ liệu, phiên bản được suy ra trong `aiConfig.ts`; chỉnh được ở "Nâng cao". Sửa hồ sơ đã lưu gửi lại đúng giá trị đã lưu, không tính lại. |
| Phân công AI riêng | Mỗi chức năng một dòng: model chính, "Nâng cao" (dự phòng, nâng cấp API, giới hạn gọi). Dòng embedding chỉ đọc, dẫn sang tab Embedding. |
| Kiểm tra trước khi lưu/kích hoạt | "Kiểm tra kết nối" (không lưu) và "Kiểm tra & Lưu"; ở Phân công AI là "Kiểm tra & Áp dụng". Kiểm tra thất bại thì chỉ lưu/áp dụng khi chọn "Vẫn lưu/áp dụng (chưa dùng được)". |
| Tương thích ngược | Hồ sơ, route, `/probe` cũ không đổi; thêm cột/bảng: không. |

## Thay đổi phía backend (cần để chức năng chạy thật)

- **Kho khóa API** `model_registry/secret_store.py`: trước đây backend chỉ nhận `env:NAME`, nên ô API Key không có nơi lưu. Khóa nhập được mã hóa Windows DPAPI, ghi một lần vào `EVIDENCE_SECRET_STORE_DIR` (`secret:<tên>`), không trả lại qua API, không vào DB/nhật ký.
- **Hồ sơ nhiều chức năng**: một hồ sơ có thể giữ nhiều chức năng sinh văn bản; `embedding` luôn đứng riêng. Hồ sơ một chức năng cũ không đổi.
- **Chẩn đoán** `model_registry/diagnostics.py`: cấu hình → chế độ → khóa → kết nối → model có trong danh sách → gọi thử (JSON hoặc embedding). Mã lỗi riêng, thông báo tiếng Việt. `models/<id>` của Gemini được chấp nhận; `/models` trả 404/405 chỉ là cảnh báo.
- Endpoint mới `POST /api/v1/admin/model-registry/test` và `POST /api/v1/admin/model-registry/{profile_id}/test`; audit `admin.test_model_draft` / `admin.test_model`. OpenAPI đã xuất lại.
- Các launcher đặt `EVIDENCE_SECRET_STORE_DIR` (`ung-dung-test.ps1`, `deploy/portable/evidence.ps1`).

## Bằng chứng

- `scripts\verify.ps1`: **12/12** đạt. Backend **288 passed** (trước 257, thêm 31). Frontend **86 passed** (trước 60, thêm 26), lint, tsc, build sạch.
- Test mới: `test_model_diagnostics.py` (24, mock transport), `test_model_registry_api.py` (7, PostgreSQL thật, kiểm khóa không lọt vào DB/audit/response), `aiConfig.test.ts`, `ModelProfilesPanel.test.tsx`, `AssignmentsPanel.test.tsx`, `AdminPortal.test.tsx`.
- HTTP thật vào ứng dụng đang chạy (cổng 8000, Ollama local):
  - Registry cũ nguyên vẹn: 6 hồ sơ `local-*` (qwen3:1.7b, qwen3-embedding:0.6b), tất cả `ready`, 12 route không đổi; `secret_store.available = true`.
  - Nháp qwen3:1.7b: đạt (kết nối 78 ms, gọi thử 1,4 s, trả JSON). Nháp embedding: đạt, 1024 chiều.
  - Model không tồn tại: `MODEL_NOT_FOUND`. Cổng sai: `CONNECTION_FAILED`. Nháp OpenAI khi máy chủ ở chế độ LOCAL: `AI_EGRESS_DENIED`.
  - Lưu hồ sơ nhiều chức năng (answer, summarize, label) kèm khóa nhập: lưu được, kiểm tra hồ sơ đã lưu ghi `ready`; file khóa 253 byte, bắt đầu `EVSEC1`, **không chứa khóa dạng rõ**; registry không lộ khóa.
- Chrome headless 1366 px (`ai-1…4-*.png`, `ui-report-1366.json`): không tràn ngang; form Local chỉ hiện 4 trường; form API có ô mật khẩu và thông báo lỗi egress dễ hiểu; Phân công AI đủ chức năng.
- Hỏi đáp và Diễn giải AI chạy lại qua `ai_probe.py` sau khi khởi động lại: trả lời bình thường (chat 3,1 s, diễn giải 14,6 s). Cấu hình RRF, rerank tắt, ngưỡng ngữ nghĩa 0,8 không đụng tới. Không import lại văn bản, không tạo lại 7.230 vector.
- **Dữ liệu thử đã dọn**: hồ sơ `zz-check-local` tạo để kiểm khóa thật đã xóa khỏi `model_profiles` (không có route tham chiếu) cùng file khóa của nó. Nhật ký kiểm toán giữ nguyên (chuỗi băm không bị sửa).

## Đánh đổi và giới hạn

- **Tự phê duyệt nhà cung cấp**: bỏ ô "phê duyệt"; lưu từ form đặt `provider_approved = true`. Form API ghi rõ lưu là cho phép gửi dữ liệu đã được phép; việc gửi thật vẫn bị chặn bởi chính sách egress của máy chủ, danh mục và quyền người dùng.
- Khóa nhập đi qua HTTP tới máy chủ (portable chạy HTTP trên LAN). DPAPI gắn với tài khoản Windows chạy máy chủ; đổi tài khoản thì phải nhập lại khóa.
- Chưa có API xóa hồ sơ. Lưu hồ sơ công khai không kiểm tra egress lúc lưu (như trước); kiểm tra nháp báo `AI_EGRESS_DENIED` trước khi lưu.
- Chưa kiểm thử gọi OpenAI/Gemini thật (không có khóa); đường API được kiểm bằng mock transport và trên đường Ollama thật.
- Chưa kiểm thử trong Tauri; chỉ kiểm bằng Chrome headless và vitest.
- Trong DB dev, chức năng "Hỏi đáp: chọn căn cứ" (`answer`) chưa có route: tình trạng có từ trước, giao diện hiện "Chưa phân công".
- Tab Embedding không đổi.
