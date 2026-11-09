# ADR-010 — Không triển khai bộ câu hỏi Gold

- Ngày: 09/11/2026
- Trạng thái: Accepted
- Người quyết định: chủ dự án
- Thay thế một phần: các nội dung về Gold, trap set, held-out và điều kiện "chưa có Gold thì chưa báo đúng/đủ" trong
  [ADR-000](ADR-000.md) (ADR-000.07), [ADR-003](ADR-003-rag-anything-selective-adoption.md),
  [ADR-005](ADR-005-search-v1.md), SRS v1.3, hồ sơ bàn giao và kế hoạch Search v1.
- Tài liệu liên quan: [Giao thức Gold cũ](../history/eval-gold-protocol.md) (lưu lịch sử, không áp dụng)

## 1. Bối cảnh

Các tài liệu trước đây đặt mục tiêu xây một bộ 150–200 câu hỏi Gold (kèm trap set, tách calibration và held-out) do
người nắm nghiệp vụ duyệt, và dùng bộ này làm điều kiện nghiệm thu chất lượng câu trả lời. Việc đó chưa bao giờ được thực
hiện: chưa có case nào, chưa có reviewer, các cổng S1/S2/S3 vẫn mở.

## 2. Quyết định

Không triển khai bộ câu hỏi Gold và không dùng bộ câu hỏi để chấm điểm câu trả lời của AI.

Lý do:

1. **AI không phải người ra quyết định.** AI chỉ hỗ trợ tra cứu và diễn giải; đáp án không do AI quyết định nên không có
   "đáp án chuẩn" để chấm.
2. **Cán bộ chuyên môn chịu trách nhiệm.** Cán bộ tra cứu, đối chiếu với căn cứ gốc và chịu trách nhiệm về báo cáo của mình.
   Kết quả AI luôn cần được kiểm tra trước khi dùng.
3. **Chất lượng được bảo đảm bằng cơ chế kiểm soát, không bằng điểm số:**
   - trích dẫn có ghim nguồn: trích đoạn lấy từ `text_original`, tệp gốc định danh bằng SHA-256 và được kiểm lại khi mở;
   - quy trình duyệt hai người: người duyệt khác người chuẩn bị (`SELF_APPROVAL_DENIED`);
   - nhật ký kiểm toán cho thao tác quản trị và duyệt.

## 3. Phạm vi giữ lại

Các kiểm tra kỹ thuật của tìm kiếm vẫn giữ, vì chúng đo hành vi của bộ máy tìm kiếm chứ không chấm điểm câu trả lời của AI:
độ phủ trích dẫn, độ chính xác cụm từ chính xác (`exact_phrase_precision`) và các kiểm tra tương tự. Ví dụ trong kiểm tra G5:
độ phủ 0,960 và 0,865. Các số này là số đo kỹ thuật trên dữ liệu và môi trường đã ghi trong báo cáo, không phải bằng chứng về
độ đúng của câu trả lời.

## 4. Hệ quả

- Bỏ nguyên tắc "Gold/trap chỉ được công nhận sau khi người nắm nghiệp vụ duyệt". Nguyên tắc mới: **không dùng bộ câu hỏi Gold
  để chấm AI; AI chỉ hỗ trợ, cán bộ chuyên môn quyết định.**
- Không còn điều kiện nghiệm thu dựa trên Gold. Hệ thống vẫn không được tuyên bố độ chính xác, độ phủ hay mức sẵn sàng triển
  khai nếu không có báo cáo trong kho hỗ trợ.
- Các tài liệu cũ nhắc Gold như việc sẽ làm được gắn nhãn "[Không triển khai – xem ADR-010]". Báo cáo lịch sử trong
  `docs/evidence/` và mã, dữ liệu trong `evaluation/` giữ nguyên.
- Giao thức cũ được chuyển sang [`docs/history/eval-gold-protocol.md`](../history/eval-gold-protocol.md).
