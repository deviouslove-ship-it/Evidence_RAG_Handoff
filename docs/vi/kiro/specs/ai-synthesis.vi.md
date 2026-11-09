# Spec: Diễn giải AI và tổng hợp có kiểm chứng, bản dịch

**Ngôn ngữ / Language:** Tiếng Việt · bản chuẩn: [`.kiro/specs/ai-synthesis/`](../../../../.kiro/specs/ai-synthesis/)

> Spec dựng lại từ mã nguồn đã triển khai ngày 09/11/2026 (`Spec reconstructed from the implemented code on 2026-11-09`). Không phải spec lịch sử do Kiro tạo. Quyết định: ADR-007, ADR-009 mục 2.

## Giới thiệu
"Diễn giải AI" là thao tác riêng, tùy chọn. Model chỉ đọc căn cứ mà người dùng được xem, và mỗi ý model trả về được kiểm bằng mã trước khi hiển thị. Căn cứ gốc luôn còn hiển thị.

## Yêu cầu (EARS)

**Y1. Đầu vào chỉ gồm căn cứ.**
1. WHEN người dùng chọn "Diễn giải AI" THE SYSTEM SHALL gửi câu hỏi và chỉ những căn cứ đã duyệt, được phép và được chọn cho câu hỏi tới model giai đoạn `summarize` (`POST /api/v1/synthesis`, `synthesis/service.py`).
2. THE SYSTEM SHALL phân biệt điều khoản trả lời câu hỏi với điều khoản chỉ cùng chủ đề (`synthesis/focus.py`, `focused.py`).
3. IF không có căn cứ THEN THE SYSTEM SHALL KHÔNG gọi model.

**Y2. Kiểm bằng mã từng ý.**
1. WHEN model trả các ý THE SYSTEM SHALL kiểm mã căn cứ thuộc tập đã cấp (`synthesis/checks.py`).
2. THE SYSTEM SHALL kiểm số, ngày, số hiệu và nhãn Điều/Khoản/Điểm có trong căn cứ đính kèm thực sự đã gửi.
3. IF ý nêu kết luận nghiệp vụ ngoài ngoặc kép THEN THE SYSTEM SHALL bỏ ý đó; IF thiếu dữ kiện THEN THE SYSTEM SHALL gắn "chưa kiểm chứng".
4. THE SYSTEM SHALL hiển thị câu trả lời, số dẫn, phần chưa đủ căn cứ, căn cứ hỗ trợ và thông tin kiểm tra.
5. IF câu hỏi nằm ngoài căn cứ, ví dụ mức phạt nồng độ cồn khi không có điều khoản tương ứng THEN THE SYSTEM SHALL trả "chưa tìm thấy" thay vì ý lạc đề.

**Y3. Lô và ngân sách.**
1. THE SYSTEM SHALL xử lý căn cứ theo lô không quá `max_evidence_per_batch`, trong `token_budget` và `max_batches_per_run` do quản trị viên cấu hình (`GET/PUT /api/v1/admin/synthesis-settings`).
2. THE SYSTEM SHALL báo "đã tổng hợp N trong M căn cứ, K nhóm còn lại" và cung cấp "Tổng hợp tiếp" và "Mở rộng phạm vi" (gấp đôi trần).

**Y4. Giảm chức năng.**
1. IF model lỗi, quá thời gian hoặc không trả gì dùng được THEN THE SYSTEM SHALL vẫn trả căn cứ gốc.
2. WHERE Hybrid Auto cho phép THE SYSTEM SHALL nâng cấp lên hồ sơ API khi không ý local nào qua kiểm tra, hoặc khi chọn "phân tích sâu" (xem spec `model-registry`).

**Y5. Nhóm nội dung và nhãn.**
1. THE SYSTEM SHALL nhóm căn cứ theo nhóm nội dung nếu có nhãn, nếu không thì theo văn bản (`content_taxonomy`, `labeling_rules`, `node_labels`, `node_label_runs`; migration `0013_content_groups.sql`).
2. THE SYSTEM SHALL gán nhãn theo quy tắc cụm từ tự động, và SHALL coi nhãn do AI gợi ý là `proposed` cho đến khi REVIEWER có `can_review` duyệt theo lô (`/api/v1/admin/labels/*`).
3. THE SYSTEM SHALL giới hạn gán nhãn bằng AI theo `ai_label_budget`.

**Y6. Minh bạch.**
1. THE SYSTEM SHALL báo cho người dùng khi đã dùng AI bên ngoài (`external_ai_used`) và khi mức dùng bị giới hạn (`ai_limited`).
2. THE SYSTEM SHALL nêu rõ kiểm tra tự động không thay thế thẩm định pháp lý.

## Thiết kế (tóm tắt)

| Mối quan tâm | Tệp |
|---|---|
| Điều phối, lô | `synthesis/service.py` |
| Tập trung vào câu hỏi | `synthesis/focus.py`, `focused.py` |
| Kiểm bằng mã | `synthesis/checks.py` |
| Nhãn và nhóm | `synthesis/labels.py`, migration `0013` |
| API | `api/v1/synthesis.py` |
| Chọn giai đoạn | `workflow/ai_selection.py`, `model_registry/runtime.py` |
| Giao diện | `AiInterpretation.tsx`, `SynthesisPanel.tsx`, `LabelReviewPanel.tsx`, `AiAnswerView.tsx` |

Luồng: giao diện gửi câu hỏi + bộ kết quả → service chọn căn cứ tập trung trong ngân sách → model `summarize` trả các ý kèm ID căn cứ → `checks.py` kiểm ID, số, ngày, nhãn, kết luận → giữ / bỏ / gắn chưa kiểm chứng → trả câu trả lời, phần thiếu căn cứ, căn cứ, kết quả kiểm.

Quyết định: model không cung cấp lời trích, ID nút hay số trang; thẻ căn cứ lấy từ văn bản đã lưu. Kiểm tra dựa trên quy tắc, không chứng minh được ý đúng về pháp lý. Phiên G4 báo cáo Local 10/10 và API 11/11 (gồm ba lời gọi API thật, 12/12 ý qua kiểm tra); chưa chạy lại khi viết spec.

## Tasks
- [x] 1. Phân loại nội dung, quy tắc, nhãn (migration `0013`)
- [x] 2. Dịch vụ tổng hợp theo lô và cài đặt
- [x] 3. Kiểm bằng mã cho ID, số, ngày, nhãn, kết luận
- [x] 4. Tập trung vào câu hỏi để tránh ý lạc đề
- [x] 5. Giao diện duyệt nhãn và tổng hợp
- [x] 6. Nâng cấp Hybrid Auto cho `summarize` (ADR-007)
- [x] 7. Báo cáo bằng chứng (`docs/evidence/2026-11-08-ai-ocr/REPORT.md`)
- [ ] 8. Chuyên gia pháp lý rà soát các ý tổng hợp (chưa có)
- [ ] 9. Kiểm Diễn giải AI trong vỏ Tauri (báo cáo ghi chưa kiểm)
