# Spec: Tìm kiếm và hỏi đáp có căn cứ, bản dịch

**Ngôn ngữ / Language:** Tiếng Việt · bản chuẩn: [`.kiro/specs/search/`](../../../../.kiro/specs/search/)

> Spec dựng lại từ mã nguồn đã triển khai ngày 09/11/2026 (`Spec reconstructed from the implemented code on 2026-11-09`). Không phải spec lịch sử do Kiro tạo. Hành vi tìm kiếm được mô tả trong ADR-005, ADR-006, ADR-009.

## Giới thiệu
Người dùng tìm điều khoản theo nghĩa, theo đủ các từ hoặc theo cụm từ chính xác, và đặt câu hỏi chỉ được trả lời từ nguồn đã duyệt và được phép.

## Yêu cầu (EARS)

**Y1. Ba chế độ tìm.**
1. WHEN người dùng tìm THE SYSTEM SHALL cung cấp chế độ toàn diện (theo nghĩa), đủ các từ và cụm từ chính xác (`SearchPage.tsx`, `GET /api/v1/search`, `POST /api/v1/search/comprehensive`).
2. WHEN gõ không dấu hoặc khác chữ hoa/thường THE SYSTEM SHALL vẫn khớp (`storage/normalization.py`, `storage/search.py`).
3. WHEN gõ số hiệu ở dạng khác (ví dụ `15/2020/nđ-cp`) THE SYSTEM SHALL chuẩn hóa trước khi khớp.

**Y2. Phân quyền trước khi truy xuất.**
1. THE SYSTEM SHALL lọc ACL trong SQL trước khi lấy ứng viên (`storage/authorized_search.py`).
2. WHEN yêu cầu một trang của bộ kết quả THE SYSTEM SHALL kiểm lại quyền và nguồn.
3. IF văn bản bị tạm ngừng, xóa mềm hoặc chưa duyệt THEN THE SYSTEM SHALL loại khỏi kết quả.

**Y3. Các kênh tìm toàn diện.**
1. WHEN chạy tìm toàn diện THE SYSTEM SHALL hợp bốn kênh bằng RRF (k = 60): chính xác (SQL), theo nghĩa (vector), mở rộng khái niệm, quan hệ văn bản (`storage/comprehensive.py`).
2. IF chưa có chỉ mục embedding THEN THE SYSTEM SHALL tiếp tục với các kênh từ khóa.
3. WHEN hai kết quả bằng điểm THE SYSTEM SHALL xếp theo khóa ổn định: số hiệu, SHA-256 của tệp nguồn, rồi vị trí khoản; so sánh byte `COLLATE "C"`; UUID là lựa chọn cuối (ADR-009 mục 1.3).
4. THE SYSTEM SHALL để rerank là tùy chọn và tắt theo mặc định (`EVIDENCE_RERANK_DEFAULT=false`).

**Y4. Phạm vi trung thực và giới hạn.**
1. THE SYSTEM SHALL đếm kết quả tới trần cấu hình (`EVIDENCE_SEARCH_COUNT_CAP`, 8.000 trong cấu hình đã kiểm) và hiển thị "hơn N" khi vượt.
2. THE SYSTEM SHALL báo danh mục đã tìm, số văn bản trong phạm vi, ngày dữ liệu, số khoản chưa có vector và đóng góp từng kênh.
3. WHEN không tìm thấy THE SYSTEM SHALL nói chưa thấy trong kho và phạm vi hiện tại, và KHÔNG khẳng định đã tìm hết.

**Y5. Bộ kết quả và phân trang.**
1. THE SYSTEM SHALL cố định kết quả theo lượt trong bộ kết quả ở RAM, chỉ chủ đọc được, hết hạn sau `EVIDENCE_RESULT_SET_TTL_SECONDS`, tối đa 20 bộ mỗi người (`GET /api/v1/search/comprehensive/{result_set_id}`).
2. WHEN nhóm theo văn bản THE SYSTEM SHALL phân trang và đặt kết quả khớp một phần ở nhóm riêng.

**Y6. Hỏi đáp có căn cứ.**
1. WHEN người dùng hỏi THE SYSTEM SHALL truyền (SSE) câu trả lời có cấu trúc dựng từ căn cứ đã duyệt và được phép, mỗi văn bản một thẻ (`POST /api/v1/query/evidence`, `workflow/fixed_pipeline.py`, `chat_answer.py`).
2. IF không có điều khoản phù hợp, ví dụ mức phạt hoặc thời hạn THEN THE SYSTEM SHALL trả "chưa tìm thấy" thay vì đoán (`storage/relevance.py`).
3. WHEN căn cứ duy nhất đã hết hiệu lực THE SYSTEM SHALL bỏ kết luận; WHEN một khoản hết hiệu lực THE SYSTEM SHALL loại khoản đó và nêu trong lưu ý khi áp dụng thực tế.
4. THE SYSTEM SHALL giữ bộ nhớ phiên trong RAM và KHÔNG dùng làm căn cứ.

## Thiết kế (tóm tắt)

| Mối quan tâm | Tệp |
|---|---|
| Tìm từ khóa (Search v1) | `storage/search.py`, `search_paging.py`, `normalization.py`, migration `0006`, `0007` |
| Truy xuất ưu tiên ACL | `storage/authorized_search.py` |
| Tìm toàn diện, RRF | `storage/comprehensive.py`, `api/v1/comprehensive.py`, migration `0012` |
| Vector | `storage/embeddings.py`, `scripts/build_embeddings.py` |
| Truy xuất và trả lời chat | `storage/chat_retrieval.py`, `relevance.py`, `workflow/fixed_pipeline.py`, `chat_answer.py`, `api/v1/user.py` |
| Rerank tùy chọn | `storage/cross_encoder.py`, `scripts/local_reranker_server.py` |
| Giao diện | `SearchPage.tsx`, `EvidenceChat.tsx`, `components/DocumentCard.tsx` |
| Đánh giá | `evaluation/coverage/*`, `scripts/benchmark_search.py` |

Luồng: câu hỏi → chuẩn hóa (dấu, chữ hoa, số hiệu) → bốn kênh (SQL, pgvector, khái niệm, quan hệ) → RRF k=60 với khóa phá hòa ổn định → nhóm theo văn bản, phân trang → kiểm lại ACL và nguồn từng trang.

Quyết định: rerank đo trên 100 văn bản không hơn RRF thuần có ý nghĩa thống kê và tốn 32–48 giây mỗi câu trên CPU nên RRF là mặc định (`docs/evidence/2026-11-07-g5-rerank/REPORT.md`). Trần 8.000, ngưỡng ngữ nghĩa (tương đối 0,8 trong cấu hình báo cáo gần nhất) và timeout giới hạn mỗi truy vấn, đồng thời giới hạn độ đầy đủ.

Giới hạn đã biết: hai căn cứ bắt buộc trong 42 không tìm thấy ở lần đo bao phủ G5; báo cáo quy cho truy xuất ứng viên (ngưỡng ngữ nghĩa), không phải xếp hạng. Căn cứ bắt buộc và câu hỏi mẫu do tác nhân soạn, chưa được chuyên gia xác nhận.

## Tasks
- [x] 1. Kênh SQL Search v1 và chuẩn hóa
- [x] 2. Truy xuất ưu tiên ACL
- [x] 3. Tìm toàn diện bốn kênh, RRF (migration `0012`)
- [x] 4. Khóa phá hòa ổn định (`evaluation/coverage/check_tiebreak_stability.py`, `REPORT-tiebreak.md`)
- [x] 5. Bộ kết quả và phân trang
- [x] 6. Giao diện tìm kiếm ba chế độ và bộ lọc
- [x] 7. Chat có căn cứ với SSE, dừng và thử lại
- [x] 8. Bộ đo bao phủ và benchmark
- [x] 9. So sánh reranker đã ghi; giữ RRF làm mặc định
- [ ] 10. Chuyên gia xác nhận căn cứ bắt buộc và câu hỏi (chưa có)
- [ ] 11. Khắc phục truy xuất cho hai căn cứ bị bỏ sót ở lần đo G5 (chưa có)
