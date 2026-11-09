# Prompt khởi động — đồng bộ hồ sơ 1.1 / SRS v1.3

> **[Không triển khai – xem ADR-010]** Mọi nội dung về bộ câu hỏi Gold, trap set, calibration và held-out trong tài liệu này không được triển khai theo [ADR-010](architecture-decisions/ADR-010-khong-trien-khai-bo-cau-hoi-gold.md). Phần còn lại giữ nguyên.

Tài liệu dùng để giao việc triển khai sau; việc cập nhật bộ hồ sơ không có nghĩa các WP đã được thực hiện.

## 1. Prompt chung

Bạn là coding agent triển khai Vietnamese Evidence RAG Agent trên Windows. Đọc `docs/SRS_v1.3.md`, `docs/HOSO_BAN_GIAO.md` và `docs/architecture-decisions/ADR-000.md`; nếu đang ở gói bàn giao, dùng ánh xạ trong README. SRS v1.3 và ADR-000 đã có: WP 0.0 tích hợp/đối soát, không viết lại đặc tả hoặc chọn lại quyết định owner.

Triển khai tuần tự các WP mục F, gồm bộ nhớ, chống ảo giác, phân tích/gợi ý và desktop USER. USER mở shortcut, đăng nhập trong app Windows, dùng Orb tròn góc phải desktop, click mở/thu chat, mở PDF/workspace cùng phiên; có drag/resize/tray/stop/retry/logout/exit theo S14. Admin Portal tách User Portal, dùng chung auth/backend/PostgreSQL/kho tài liệu/RAG; không tạo chatbot hoặc DB mỗi máy USER. Giữ theme/tokens và chữ dễ đọc; Orb không nền vuông/bóng dư, login/panel nền đục, vùng kéo không đè chữ, không hiện console.

LLM cấu hình API hoặc Local qua Registry/Router từng stage: adapter/provider, endpoint/runtime được duyệt, model ID/artifact, params, revision, secret reference và fallback. Không hardcode quyền/provider/model/endpoint/key/host/port/path; dùng cấu hình, manifest và platform API. API Mode có Internet và egress được phép; Local Mode ngắt Internet, chỉ runtime/endpoint nội bộ được duyệt, không tự chuyển API. Model POC không là model bắt buộc. Owner tự nhập key sau; chưa có model/key thì hoàn thiện tính năng và test hợp đồng, trả evidence/extractive thật, không giả lập AI hoặc công nhận gate provider đã đạt.

Không hardcode PATH hoặc LLM. Toàn bộ công cụ/tool/runtime dự án cài để build/cài/vận hành app phải dưới root `E:\Programs` do owner chốt; root chỉ là giá trị deployment profile `installation.programs_root` / `EVIDENCE_PROGRAMS_ROOT`, không nhúng trong code/script. Resolve executable/model/artifact và cache công cụ từ manifest dưới root, không dùng fallback PATH/global/AppData/Program Files. Thiếu root/dependency thì báo lỗi, không tự đổi ổ. Mỗi máy chỉ cài thành phần theo role; dữ liệu nghiệp vụ/backup có đường dẫn cấu hình riêng, không tự di chuyển. Tuân thủ B.8 và SRS §25.9.

Tuân thủ B.3/B.7/B.8 và SRS §25: CURATOR nháp, REVIEWER duyệt; cache analysis/retrieval OFF đến khi đủ fingerprint và test; incognito chỉ RAM, retention + opt-in mới lưu; xóa dẫn xuất/cache/job, restore áp sổ xóa; Gold [Không triển khai – xem ADR-010] 150–200 case người nắm nghiệp vụ duyệt, split theo nhóm tình huống, regression tách held-out; llm_attempt_budget=2 tính cả timeout/retry/fallback, summary P0 bằng code. Scope là SELECTED hoặc ALL_AUTHORIZED, server luôn kiểm ACL; SSE dùng query_id/run_id/revisions/sequence, retry tường minh không trộn lượt.

AI tự dựng ERD/migration/test DB và làm tối đa phần kỹ thuật kiểm chứng được; chỉ cần người quyết các nguyên tắc nghiệp vụ, quyền truy cập, bảo mật và độ đúng căn cứ. Không tự công nhận Gold [Không triển khai – xem ADR-010], không bịa văn bản pháp lý, không thêm dependency bị cấm, không dùng kết quả cũ làm bằng chứng hiện tại. Thiếu key/model/reviewer/thiết bị thì báo đúng gate còn thiếu và làm tiếp việc độc lập. Kết thúc mỗi WP báo cáo F.10, có số đo/môi trường và mục CHƯA XONG.

## 2. Prompt theo luồng (chỉ chia nhiều AI khi owner cho phép)

Mọi luồng đọc phần chung, B.7/B.8, E, F và SRS §25. Backend xuất OpenAPI/permission matrix đầu Sprint 1; frontend dùng mock cùng schema, không tạo chatbot hoặc workflow khác. Mỗi WP có một chủ trì; các luồng còn lại đóng góp theo giao diện/thành phần, không bỏ trống nghiệm thu.

### Luồng backend và dữ liệu (A, B, D, E, G)

Chủ trì WP 0.0–0.2, 0.5, 0.7, 1.1–1.7, 1.10, 2.6–2.7, 3.1–3.4, 3.7, 4.1–4.4, 4.8.

Phụ trách ERD/ACL, curator draft vs reviewer approve, hiệu lực node, OpenAPI, session/memory/incognito/xóa/restore, provider/route/secret và budget LLM. WP 0.5 phối hợp frontend làm POC shell. WP 4.8 do backend chủ trì red-team, yêu cầu retrieval và frontend cung cấp test rò rỉ/cache/SSE/UI; báo cáo có bằng chứng và phần chưa kiểm. Không có tool cho LLM ghi nghiệp vụ; operational session/audit do service kiểm quyền thực hiện.

### Luồng retrieval và đánh giá (C)

Chủ trì WP 0.3, 0.4, 0.6, 1.9, 2.1–2.5, 2.8, 2.10–2.15, 3.8, 3.10–3.13, 4.5–4.6, 4.9.

POC model là kiểm capability/runtime/format, không chốt model cố định. Gold [Không triển khai – xem ADR-010] v0 150–200 case PDF thật do con người duyệt, split theo scenario_group_id; khóa split/corpus/protocol/candidate trước đợt đánh giá chốt. Calibration/regression dùng khi phát triển; không tune bằng held-out/trap hold-out rồi tiếp tục báo độc lập. Chủ trì WP 4.9 cho các mục P1 owner chọn, phối hợp backend/frontend; danh sách không chọn ghi rõ. Góp phần WP 4.8, không tự nhận red-team đã qua khi chưa có test.

### Luồng frontend và desktop USER (F)

Chủ trì WP 1.8, 2.9, 3.5, 3.6, 3.9, 3.14, 4.7.

Đóng góp giao diện cho WP khác theo phân công chủ trì.

Thực hiện User/Admin layout và route riêng, desktop USER Tauri 2 theo C.12/S14 dùng cùng backend/RAG. Orb tròn toggle, login/panel nền đục, không bóng/nền vuông dư/console; drag/resize không đè tiêu đề/nút; tray/logout/exit/stop/retry và viewer/workspace giữ phiên. Phạm vi có “Tất cả danh mục được phép”; USER không có chức năng quản trị hay nhập key. Form admin cho cấu hình API/Local không hardcode model. Chỉ cạnh panel/viewer khi đủ work area; kiểm 320/768/1024/1280px, DPI 100/125/150/200%, nhiều màn hình, zoom, keyboard/contrast/reduced-motion. WP 4.7 phải có kiểm native thực; test/build không thay nghiệm thu Windows.

## 3. Ranh giới hoàn thành

- Profile B chỉ nghiệm thu lõi offline với giới hạn công khai; không thay gate AI cấu hình API/local thật.
- Không dùng API key, tài khoản test, đường dẫn máy hoặc dữ liệu bí mật từ lịch sử project.
- Bộ tài liệu là đầu vào tự chứa; không cần code của project cũ để hiểu hợp đồng.
- Mọi WP có chủ trì và báo cáo F.10; không công nhận toàn bộ chỉ vì một bộ unit test hoặc build xanh.
