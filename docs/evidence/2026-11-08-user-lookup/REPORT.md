# Rà soát và sửa chức năng tra cứu của USER (08/11/2026)

Dữ liệu: DB `evidence_rerank_eval` (100 văn bản đã duyệt, 7.230 vector `qwen3-embedding:0.6b`), chạy
bằng `ung-dung-test.ps1` (LOCAL, RRF thuần, không rerank). Không nhập lại văn bản, không tạo lại vector,
không xóa model, DB, chỉ mục hay bản sao lưu. Mã trước khi sửa: `.agents/backup-2026-11-08-user-lookup/`.

## Ca lỗi “Thủ tục bổ nhiệm, miễn nhiệm trong Công an nhân dân”

Trước khi sửa (HTTP thật): 12 căn cứ, đứng đầu là các khối 4.000 ký tự của danh mục 540/QĐ-BCA và
721/QĐ-BCA; nhận định là nguyên văn cả khối; cùng một khoản lặp ở “nhận định” và “gợi ý”; nhãn
`paragraph`; điều “Các đồng chí … chịu trách nhiệm thi hành” được chọn vì chỉ trùng tên văn bản.

Nguyên nhân tìm được:

| Tầng | Nguyên nhân |
|---|---|
| Phân tích câu hỏi | Từ khóa là âm tiết rời; không có khái niệm cụm từ; “còn”, “này” làm câu hỏi mới nhận dữ kiện cũ; giao diện tự đặt số hiệu, Điều của căn cứ đầu tiên thành dữ kiện cho lượt sau |
| Truy xuất chat | Kênh riêng của chat (không phải G2); kênh “tên văn bản” lấy mọi khoản của văn bản có tên khớp; “đủ các từ” tính trên `text_indexed` (gồm cả tên văn bản) |
| Xếp hạng | `ts_rank_cd` ưu tiên khối dài nhiều lần lặp từ chung (danh mục văn bản) |
| Mở rộng khái niệm | Gợi ý AI chưa duyệt (ví dụ “thủ tục điều động”) được tính như khớp; khi không có nguyên cụm thì rơi về “mọi từ ở bất kỳ đâu” |
| Hiển thị | Nhận định = nguyên văn khoản; PDF nhúng 3 cột; nút mở PDF dựng từ Word |

## Thay đổi

- `storage/relevance.py` (mới): tách câu hỏi thành cụm (dấu câu, hư từ), đơn vị là cặp âm tiết liền
  nhau; mỗi âm tiết thuộc cặp phổ biến nhất chứa nó (loại cặp vắt hai từ như “tục bổ”); trọng số IDF
  đếm trong PostgreSQL trên các khoản người dùng được đọc; chấm trên chữ của khoản và tiêu đề Điều,
  tên văn bản tính một nửa; từ cách xa nhau (ngoài cửa sổ 30 âm tiết) chỉ được 0,3. Ba mức:
  `direct` (đủ các cụm chính, viết liền), `related` (có cụm hiếm và thêm từ của câu hỏi ở gần),
  `weak` (chỉ từ chung, âm tiết rời, hoặc chỉ gần theo nghĩa). Đoạn liệt kê từ 4 số hiệu trở lên là
  “chỉ nhắc đến”, không bao giờ là căn cứ trực tiếp. Trích đoạn ≤ 520 ký tự là lát cắt nguyên văn của
  `text_original`, tô các cụm chính.
- `storage/comprehensive.py`: G2 gắn mức liên quan cho 2.000 kết quả đầu; sắp xếp ổn định theo (nhóm
  hiệu lực D9, mức liên quan), giữ thứ tự RRF trong từng nhóm; không loại kết quả nào. Thêm `mode`
  (chính xác cụm từ / đủ các từ), xem theo văn bản (`view=documents`), lọc mức (`tier`), tất cả khoản
  của một văn bản (`GET …/{id}/documents/{document_id}`). RRF k = 60, ngưỡng theo nghĩa 0,8, rerank tắt:
  không đổi.
- Hỏi đáp (`storage/chat_retrieval.py`, `workflow/chat_answer.py`, `fixed_pipeline.py`): câu hỏi không
  nêu số hiệu/Điều chạy đúng bộ kết quả G2; câu có số hiệu/Điều giữ tra cứu tham chiếu cũ. Chỉ khoản
  `direct`/`related` thành căn cứ; tối đa 8 văn bản, mỗi văn bản tối đa 4 khoản, mỗi Điều một khoản đại
  diện (khoản khác ghi “Cùng điều còn khớp”); điều phạm vi/định nghĩa/hiệu lực và biểu mẫu xếp sau;
  khoản trùng chữ giữa văn bản hợp nhất và văn bản sửa đổi ghi “Nội dung giống …”. Câu trả lời viết từ
  siêu dữ liệu và tiêu đề Điều, không gọi model, không tạo số hiệu, ngày, hiệu lực. Loại văn bản hợp
  nhất / sửa đổi, bổ sung đọc từ số hiệu và trích yếu; quan hệ chỉ ghi “đã xác minh” khi đã duyệt
  (DB thử: 0 quan hệ đã duyệt). Diễn giải AI là nút riêng, chỉ trên khoản liên quan (`only_relevant`).
- Tệp gốc: `GET /api/v1/citations/{id}/original` kiểm ACL, phiên bản, SHA-256; PDF (kể cả scan) trả đúng
  tệp đã nạp, Word/TXT trả tệp gốc ở `sources/` theo `source_file_sha256`, không trả PDF dựng.

> Ghi nhận ngày 08/11, trước khi có giao diện hai khung (11/11/2026).

- Giao diện: một cột đọc; câu trả lời ngắn, thẻ từng văn bản (loại, số hiệu, ngày, cơ quan, trích yếu,
  tệp gốc, hiệu lực, Điều/Khoản, trích dẫn mở rộng được, “Mở văn bản gốc”); PDF mở tab riêng tại trang,
  Word/TXT tải đúng định dạng; dữ kiện, bộ nhớ phiên, kiểm tra độ phủ chuyển vào vùng “Thông tin kỹ
  thuật”. Một trang “Tìm kiếm văn bản” (bỏ “Tìm toàn diện”) trên G2: theo nghĩa / đủ các từ / chính xác
  cụm từ, bộ lọc danh mục, loại, ngày hiệu lực, phạm vi thời gian, trạng thái hiệu lực, xác minh; kết quả
  khớp một phần ở nhóm riêng thu gọn; liên kết cũ `?q=…&mode=phrase` vẫn mở trang tìm kiếm. Xóa
  `PdfViewer`, `EvidenceCards`, `ComprehensiveSearchPage`.

## Kết quả đo

HTTP thật, 7 câu hỏi (`chat-after.txt`, `chat-after.json`): 1,3–3,1 giây mỗi lượt.

| Câu hỏi | Kết quả |
|---|---|
| Thủ tục bổ nhiệm, miễn nhiệm trong CAND | 3 văn bản trực tiếp: 01/VBHN-BCA (Khoản 4 Điều 5, Khoản 5 Điều 8, Điều 6…), 77/2019/TT-BCA (Khoản 4, 3 Điều 1), 05/VBHN-BCA (Khoản 2 Điều 21); 2 liên quan (777/QĐ, 14/2024); 540, 721 xếp vào “chỉ nhắc đến” |
| chế độ báo cáo định kỳ | 8 văn bản có điều khoản nêu trực tiếp (10/2014 Điều 18 đứng đầu), 4 văn bản khác ở trang tìm kiếm, 2 danh mục |
| đồ vật cấm đưa vào buồng tạm giữ, tạm giam | 58/2026/TT-BCA trực tiếp; 7 liên quan |
| Điều 5 Thông tư 55/2021/TT-BCA quy định gì? | Chỉ 55/2021/TT-BCA (tra cứu tham chiếu) |
| quy tắc ứng xử của CAND | 27/2017/TT-BCA (PDF) đứng đầu |
| xử phạt vi phạm thuế thu nhập cá nhân | “Chưa tìm thấy trong kho…” (kho không có văn bản thuế) |

Mở văn bản gốc qua trình duyệt (Chrome headless, `report-*.json`): 8 tệp Word khác nhau và 1 PDF; SHA-256 của
byte nhận được trùng `source_file_sha256` (Word) hoặc `original_file_sha256` (PDF) trong DB; PDF mở tab
`blob:…#page=N`. Bố cục 1024/1366/1920 px: không tràn ngang, trích dẫn dài nhất 513 ký tự, không lỗi
console. Ảnh: `chat-*.png`, `search-*.png`.

50 câu G5 (`bench-rrf-50-before.json`, `bench-rrf-50-after.json`, `bench-diff.txt`):

| | R@10 | R@20 | R@50 | R@toàn bộ | MRR@10 | NDCG@10 | Trung vị |
|---|---|---|---|---|---|---|---|
| Trước | 0,865 | 0,892 | 0,946 | 0,960 | 0,780 | 0,589 | 2,1 s |
| Sau | 0,851 | 0,892 | 0,960 | 0,960 | 0,792 | 0,629 | 2,9 s |

Không mất căn cứ bắt buộc nào (R@toàn bộ giữ 0,960). Một lượt đo trung gian cho R@10 0,865: bước mở
rộng khái niệm (`expand`, qwen3:1.7b) cho kết quả khác nhau giữa các lần nên R@10 dao động ±1 cặp.
Thử bỏ đường rơi “mọi từ” của kênh khái niệm làm mất 1 căn cứ bắt buộc (23/2022 Điều 5) nên đã giữ lại.

`verify.ps1` 12/12: backend 239 passed (PostgreSQL thật), frontend 57 passed, ruff/mypy/eslint sạch,
OpenAPI cập nhật.

## Giới hạn còn lại

- Ngưỡng mức liên quan đặt theo nguyên tắc, kiểm trên 7 câu và 50 câu do tác tử soạn; chưa có cán bộ
  nghiệp vụ xác nhận. Đoạn văn của Kế hoạch/Chỉ thị nhắc “báo cáo định kỳ” vẫn được tính “trực tiếp”.
- Không có PDF scan đã OCR trong DB thử và máy chưa cài Tesseract: chỉ kiểm bằng test rằng nhánh PDF
  trả đúng tệp `originals/` đã nạp (OCR không tạo tệp mới). Không có tệp TXT trong DB thử; nhánh TXT
  kiểm bằng mã chung với Word.
- Ứng dụng desktop (Tauri) chưa build lại và chưa thử mở tab/tải tệp trong WebView2; khi trình duyệt chặn
  tab mới, tệp được tải xuống.
- Phân nhóm chủ đề dùng 27 quy tắc cụm từ của 11 nhóm nội dung G4; chưa có nhóm theo lĩnh vực.
- Số liệu ngày ban hành, cơ quan ban hành thiếu ở nhiều văn bản hợp nhất trong DB thử; hiển thị
  “Chưa xác định”. Tên lấy từ tên tệp (không dấu) giữ nguyên như dữ liệu.
- Bộ test frontend giảm từ 77 xuống 57 vì bỏ 36 test của trang Search v1 và PdfViewer đã gỡ; thay bằng
  10 test cho trang mới, thẻ văn bản và nút mở tệp gốc.
