> **Không triển khai – xem [ADR-010](../architecture-decisions/ADR-010-khong-trien-khai-bo-cau-hoi-gold.md).** Giao thức này được giữ để tra cứu lịch sử; không áp dụng.

> **Kh么ng tri峄僴 khai 鈥?xem [ADR-010](../architecture-decisions/ADR-010-khong-trien-khai-bo-cau-hoi-gold.md).** Giao th峄ヽ n脿y 膽瓢峄 gi峄?膽峄?tra c峄﹗ l峄媍h s峄? kh么ng 谩p d峄g.

# Gold evaluation protocol

## Corpus

- Chỉ dùng PDF công khai thật từ nguồn chính thức.
- Mỗi corpus lưu URL, publisher, license, hash và captured timestamp.
- Fixture UI được giữ riêng và gắn nhãn **HƯ CẤU**.

## Review và split

- Mỗi case có câu hỏi, answer tham chiếu, evidence, source hash, `scenario_group_id` và trạng thái review.
- Chỉ case `approved` bởi người nắm nghiệp vụ được dùng làm chuẩn.
- Các paraphrase hoặc cùng tình huống phải cùng một `scenario_group_id` và không được chia giữa calibration và held-out.
- `split_revision` bị khoá trước khi tune candidate.

## Báo cáo

Báo candidate, config/model/tokenizer revision, corpus/split hash, số case, môi trường, recall/precision, `wrong_doc_rate`, `wrong_node_rate`, abstention, missed exception và khoảng tin cậy. Không tune trên held-out rồi báo lại là đánh giá độc lập.

Gold v0 chưa được tạo và chưa có reviewer; gate S1/S2/S3 vẫn mở.

## Search v1 — định nghĩa exact_phrase_precision (owner chốt 31/10/2026)

- Tử số = số clause được backend gắn `match_type="exact_phrase"` mà `quote_exact` **tự xác
  minh** (NFC + lowercase + dấu câu thành phân tách, các từ liền nhau) thực sự chứa cụm từ.
  Không tin nhãn backend, không dùng `expected_documents`/`expected_nodes` để tính tử số.
- Mẫu số = tổng số clause được gắn `exact_phrase` trong `results[:k]`.
- Ca âm (`expected_no_result`) bắt buộc **0.0**, kể cả khi mẫu số > 0 hoặc quote tình cờ
  chứa cụm từ.
- Case dương có mẫu số 0 → **null** (loại khỏi trung bình), không phải 1.0.
- Cụm từ đối chiếu ưu tiên `response.query.phrase`, fallback câu hỏi của case.
- Không tuyên bố “đúng/đủ” khi chưa có Gold được người nắm nghiệp vụ duyệt.