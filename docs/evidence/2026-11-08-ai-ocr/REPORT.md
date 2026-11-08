# Diễn giải AI và PDF scan OCR (08/11/2026)

Môi trường: DB thử `evidence_rerank_eval` (100 văn bản đã duyệt + 5 nghị định scan thử nghiệm
trong danh mục riêng), `ung-dung-test.ps1`, chế độ LOCAL, model theo Model Registry (giai đoạn
`summarize` đang trỏ `qwen3:1.7b` trên CPU Ryzen 9 6900HX, không GPU). RRF thuần, rerank tắt, ngưỡng
theo nghĩa 0,8: không đổi. Không nhập lại 100 văn bản, không tạo lại 7.230 vector, không xóa DB,
chỉ mục, model hay bản sao lưu. Sao lưu trước khi sửa: mã ở `.agents/backup-2026-11-08-ai-ocr/`,
DB ở `.agents/backup-2026-11-08-ai-ocr/evidence_rerank_eval.dump` (pg_dump, 38,9 MB).

## A. Diễn giải AI

### Ca lỗi và nguyên nhân

“Xử phạt về nồng độ cồn” → bấm “Diễn giải AI” (`ai_before.txt`, `ai_before_ev.txt`): 10 ý, trong
đó có phòng cháy chữa cháy, đặt cược, hồ sơ doanh nghiệp, đều “verified”. Kho không có điều khoản
nào quy định xử phạt về nồng độ cồn (`ai_truth.txt`: 7 khoản nhắc “nồng độ cồn”, 0 khoản có
“phạt tiền/xử phạt”).

| Tầng | Nguyên nhân |
|---|---|
| Chọn căn cứ | Mọi khoản mức `direct/related` được gửi cho model. Khoản danh mục ngành nghề (5625/QĐ) có “nồng độ cồn” nên là `direct`; không có khái niệm “vấn đề được hỏi” (xử phạt) |
| Gom nhóm | Gom theo nhãn nội dung, nhãn do AI đề xuất chưa duyệt (khoản thiết bị đo cồn bị gắn “Thời hạn”); mỗi lượt còn gọi AI gán nhãn |
| Prompt | Model **không được biết câu hỏi**: chỉ “tóm tắt căn cứ theo nhóm X” |
| Kiểm chứng | Chỉ kiểm mã căn cứ, số, ngày, Điều/Khoản; ý sai chủ đề có mã hợp lệ thì qua. Số sai chỉ bị gắn “chưa kiểm chứng”, vẫn hiển thị |
| Hiển thị | Mã căn cứ không có trong danh sách hiển thị thành chữ “căn cứ đã trích”; “Diễn giải tiếp” lặp lại toàn bộ ý cũ; gợi ý vô nghĩa |

### Thay đổi

- `synthesis/focus.py` (mới): tách câu hỏi thành **vấn đề hỏi** (bảng 12 loại: mức phạt, xử phạt,
  hành vi bị cấm, thẩm quyền, thời hạn, điều kiện, hiệu lực, thủ tục, hồ sơ, đối tượng, khái niệm,
  quyền/nghĩa vụ; mỗi loại có cụm từ hỏi và cụm từ cho thấy khoản quy định nó) và **nội dung** (các
  cụm từ còn lại của câu, theo `relevance.py`). Bảng là loại nội dung pháp lý, không chứa câu hỏi, số
  hiệu hay văn bản nào. Loại “chặt” (mức phạt, xử phạt, thời hạn, thẩm quyền, điều kiện, hiệu lực,
  hành vi bị cấm): không có khoản quy định thì không suy ra.
- `synthesis/focused.py` (mới), `service.py` (`only_relevant`): từ bộ kết quả G2, mỗi khoản được xếp
  `primary` (đủ nội dung, có tính đến phạm vi ghi ở trích yếu, và đúng vấn đề hỏi), `partial` (chỉ
  một phần nội dung, chỉ dùng khi không có `primary`, có ghi chú), `other_aspect` (cùng nội dung,
  khác vấn đề; chỉ liệt kê), `off_topic`, `mentioned` (danh mục). Khoản `primary` được dựng thành
  thẻ văn bản bằng `chat_answer.compose` (một khoản đại diện mỗi Điều, khoản trùng chữ giữa văn bản
  hợp nhất và văn bản sửa đổi chỉ gửi một lần). Model nhận câu hỏi, vấn đề hỏi, nội dung, từng căn
  cứ (loại + số hiệu, trích yếu, Điều/Khoản + tên Điều, hiệu lực chỉ khi đã xác minh) và các ý đã
  nêu. Mỗi lượt 4 khoản; “Diễn giải tiếp” chỉ lấy các văn bản chưa xử lý. Không có `primary` cho vấn
  đề “chặt” → trả lời “Chưa tìm thấy…”, **không gọi model**. Không gán nhãn AI trong chế độ này.
- `synthesis/checks.py` `verify_claim`: các lớp kiểm (1) mã căn cứ, (2) số, ngày, số hiệu,
  Điều/Khoản/Điểm phải có trong căn cứ — **sai là loại**, không còn “chưa kiểm chứng”, (3) kết luận
  nghiệp vụ (trừ khi chỉ nhắc lại chữ của căn cứ như “quyết định xử phạt”), (4) đoạn trong ngoặc
  kép phải là nguyên văn, (5) mức hỗ trợ từ ngữ của căn cứ được dẫn (< 0,35 loại, < 0,55 “cần đối
  chiếu”), (6) đúng chủ đề câu hỏi, (7) ý nêu một vấn đề “chặt” (phạt, thời hạn…) cần khoản quy định
  vấn đề đó, (8) phủ định ngược nghĩa (loại), phủ định/ngoại lệ/điều kiện bị bỏ, “phải” ↔ “có thể”
  (cần đối chiếu), (9) hiệu lực chỉ nêu khi đã xác minh hoặc căn cứ tự ghi, (10) trùng ý (có so
  số liệu), (11) chép nguyên văn dài. Ý giữ lại chỉ ghi “đã đối chiếu với căn cứ”, không “đúng”.
  Khi mọi ý bị loại, hỏi lại model một lần kèm lý do loại. `clean_text`: NFC, bỏ markdown và mã
  `e1`, “Căn cứ: ,,”, viết hoa đầu câu; không đụng trích dẫn nguyên văn (lấy từ DB).
- Hỏi đáp (`chat_answer._answer`): vấn đề “chặt” không có khoản nào quy định → tóm tắt “Chưa tìm
  thấy điều khoản quy định … về …; các văn bản này không dùng để suy ra …”.
- Giao diện `AiAnswerView.tsx` (dùng chung cho Hỏi đáp và trang Tìm kiếm): câu trả lời chính → các ý
  có số trích dẫn [n] dẫn tới khoản → phần thiếu căn cứ → lưu ý một lần → “Diễn giải tiếp” → “Căn
  cứ hỗ trợ” (chỉ khoản được ý nào dẫn): loại, số hiệu, ngày, trích yếu, Điều/Khoản + tên Điều,
  trích dẫn ngắn ≤ 320 ký tự, hiệu lực “(đã xác minh)” hoặc “Chưa xác minh trong kho”, nút “Mở văn
  bản gốc”; văn bản cùng nội dung khác vấn đề ở mục thu gọn; “Thông tin kiểm tra” (số khoản bị
  loại, ý bị loại và lý do).
- Độc lập model: gọi `runtime.generate("summarize", …)` qua Model Registry (Local/API, egress, timeout
  ≤ 30 s mỗi lượt, token, trần chi phí, Hybrid Auto giữ nguyên). Không có tên model trong mã. Model lỗi
  → “Chưa diễn giải được bằng AI lúc này”, căn cứ vẫn hiển thị.

### Kết quả HTTP thật (`ai_after4.txt`, `ai_after5.txt`, `ocr_ai.txt`)

| Câu hỏi | Diễn giải AI |
|---|---|
| Xử phạt về nồng độ cồn | “Chưa tìm thấy trong kho điều khoản quy định xử phạt về ‘nồng độ cồn’”; 5 văn bản nêu nồng độ cồn ở nội dung khác (kiểm tra tại hiện trường, máy đo…) được liệt kê riêng; 0 lần gọi model, 0,1 s. Hỏi đáp cũng nói “Chưa tìm thấy…” |
| Mức phạt khi không đội mũ bảo hiểm | “Chưa tìm thấy…”, 2 văn bản nêu mũ bảo hiểm ở nội dung khác |
| Thủ tục bổ nhiệm, miễn nhiệm trong CAND | 01/VBHN-BCA và 77/2019/TT-BCA; 5 ý đã đối chiếu (hồ sơ 02 bộ, Công an cấp tỉnh chủ trì với Sở Tư pháp…); 3 ý bị loại vì nêu Điều/số không có trong căn cứ; 42 s |
| Chế độ báo cáo định kỳ | 10/2014/TT-BCA (ngày 20 hằng tháng, 25/5, 25/11), 04/CT-BCA, 05/2015/TT-BCA; ý gán nội dung 04/CT-BCA cho 10/2014 hoặc 117/2021 bị loại; “Diễn giải tiếp” thêm 05/2015 không lặp ý |
| Hiệu lực thi hành của Thông tư quy tắc ứng xử CAND | “27/2017/TT-BCA có hiệu lực thi hành kể từ 06/10/2017, thay thế QĐ 893/2008/QĐ-BCA ngày 04/7/2008” [Điều 15]. Một lượt khác model chép sai năm (04/7/2017): bị loại, không hiển thị |
| Đồ vật cấm đưa vào buồng tạm giữ, tạm giam | 58/2026/TT-BCA, 3 ý |
| Xử phạt vi phạm thuế TNCN (ngoài kho) | “Không tìm thấy căn cứ…”, không gọi model |
| OCR: Thời hạn thi hành biện pháp khắc phục hậu quả trong lĩnh vực thống kê | 362/2026/NĐ-CP (scan): 30 ngày làm việc kể từ ngày nhận quyết định… |
| OCR: Phụ cấp công vụ đối với cán bộ, công chức ở xã | 381/2026/NĐ-CP (scan): 55% mức lương hiện hưởng cộng phụ cấp chức vụ… Trước khi siết lựa chọn, 350/2026 (phụ cấp y tế) bị đưa vào; sau khi yêu cầu đủ nội dung thì không còn |

Chrome headless 1024/1366/1920 (`ai-report-*.json`, `ai-*.png`): không tràn ngang, không lỗi console,
mọi [n] trỏ tới khoản có thật; một câu miễn trừ trách nhiệm. Mở tệp gốc từ “Căn cứ hỗ trợ”: Word
01/VBHN-BCA, 77/2019/TT-BCA tải đúng `source_file_sha256`; PDF scan 362/2026 mở tab `#page=6`,
SHA-256 = bản scan.

## B. PDF scan OCR

- Runtime: Tesseract 5.5.0 (`vie`, `eng`, `osd`; Apache-2.0) đã có trên máy ở Program Files; bản sao
  đặt dưới gốc chương trình `E:\Programs\EvidenceRAG\tools\tesseract\5.5.0` (190 MB) theo quy tắc
  HOSO (không dùng PATH/Program Files). Chạy offline. `ung-dung-test.ps1` tự nhận bản dưới
  `tools\tesseract\`; gói portable dùng `runtime\tesseract\` nếu quản trị đặt vào, hoặc
  `EVIDENCE_OCR_EXECUTABLE` trong `evidence.env` (mặc định tắt, đúng “OCR là plugin ngoại lệ”).
- `documents/ocr.py`: đọc qua TSV để có độ tin cậy từng từ; trang đọc kém thì hỏi hướng trang
  (`--psm 0`) và đọc lại sau khi xoay; chẩn đoán trang: số từ, độ tin cậy trung bình, tỷ lệ từ
  < 60, từ yếu nhất, từ không thể là tiếng Việt (`B6`, `1Š`, `bd`, `ø`, `§`, `⁄QH15`, `UBTVQHI5`),
  ký hiệu điểm đọc nhầm (“l)” → “1)”), mực/chữ (sót nội dung), xoay. Không sửa chữ.
- Lưu: migration `0015` (`source_pages.ocr_diagnostics`, `reviewed_by`, `reviewed_at`). Trang OCR
  luôn `needs_review`; tác vụ rủi ro cao khi có cờ. Số hiệu khai báo không thấy trong chữ OCR 2 trang
  đầu → tác vụ `document_number_not_in_ocr_text`.
- Duyệt: reviewer xác nhận **từng trang** (giao diện hiện chữ OCR, cờ, từ nghi sai, nút xem đúng trang
  scan); chỉ khi đó trang thành `usable` và khoản của trang mới vào được tìm kiếm/trích dẫn. “Phê
  duyệt và đóng mọi tác vụ” không đóng tác vụ trang. Trang không có chữ (trang ký) chỉ qua khi được
  xác nhận riêng. Mỗi xác nhận ghi kiểm toán `document.confirm_page_text`.
- Parser: dòng xuống hàng “Điều 3 của Nghị định này, …” không còn bị tách thành Điều mới (trên chữ
  OCR thật của 362/2026: 6 → 4 Điều, đúng bản gốc, `ocr_reparse.txt`).
- Trích dẫn: khoản từ trang OCR mang cờ `ocr`; giao diện ghi “Trích từ bản scan qua OCR đã duyệt; vị
  trí chỉ xác định đến trang”. Không tô sáng trong PDF (OCR không có tọa độ ký tự).

### Kiểm thử với scan thật (HTTP, `ocr_state.json`, `ocr_original.json`)

5 nghị định scan công khai (362, 381, 350, 390, 356/2026/NĐ-CP; 28 trang, không có lớp chữ) nạp qua
API curator: 3,8–11,1 s mỗi tệp; độ tin cậy trung bình 94,1–96,2 %. Danh mục riêng “Thử nghiệm OCR”,
chỉ tài khoản thử `ocr_tester` đọc được; `chuyenvien` (tài khoản benchmark) không thấy.

| Kiểm tra | Kết quả |
|---|---|
| SHA-256 tệp lưu ở `originals/` = SHA-256 trong manifest nguồn | 5/5 |
| `/original` trả `application/pdf`, đúng SHA-256 bản scan, đủ số trang | 8/8 khoản kiểm |
| Trang được trích (OCR lại độc lập từ byte nhận được) chứa các từ của trích dẫn | 8/8, 100 % từ |
| Người không có danh mục: `/original` | 404 (8/8); tìm kiếm không trả văn bản OCR |
| Embedding | chỉ 160 + 57 khoản mới (catch-up); 7.230 vector cũ giữ nguyên; tổng 7.447 |
| Quan hệ hiệu lực sinh ra | 30 đề xuất `draft`, 0 trỏ tới văn bản trong kho |
| Xoay 90°/180° (`ocr_rotate.json`) | tự xoay lại, chữ giống bản thẳng; trang trắng → `NO_TEXT` |

## Kiểm thử, hồi quy

- `verify.ps1` 12/12: backend 257 passed (thêm 18: `test_ai_interpretation.py`, `test_ocr_review.py`
  có PostgreSQL), frontend 60 passed (thêm 3). OpenAPI cập nhật.
- 50 câu G5 (`ul_bench_ai_ocr.json`, so với lần cuối của đợt trước): R@10 0,851 (=), R@20 0,905
  (0,892), R@50 0,960 (=), R@toàn bộ 0,960 (=), MRR@10 0,781 (0,792), NDCG@10 0,613 (0,629), trung
  vị 3,1 s. Mã truy xuất không đổi; 10 cặp đổi hạng ±1–16 đều theo kênh khái niệm (`expand` của model
  cho kết quả khác nhau giữa các lần, `ul_bench_ai_ocr_diff.txt`).

## Giới hạn còn lại

- Kiểm chứng là quy tắc từ ngữ: bắt được ý sai chủ đề, số/ngày/Điều bịa, đảo phủ định, suy ra vấn
  đề khác; **không chứng minh được** một câu diễn giải đúng nghĩa pháp lý. Ví dụ ý “Thông tư 33/2014
  quy định thẩm quyền… cấp thẻ giám định viên” được giữ vì đúng chữ căn cứ dù hơi lệch trọng tâm.
  Ý “cần đối chiếu” vẫn hiển thị kèm lý do.
- Model nhỏ trên CPU: 7–50 s mỗi lần bấm; có lượt mọi ý bị loại (khi đó chỉ hiện căn cứ). Kết quả
  model thay đổi giữa các lần. Chưa thử API ngoài, chưa thử model lớn hơn.
- Bảng vấn đề hỏi do tác tử soạn, chưa có cán bộ nghiệp vụ duyệt; cách hỏi không có trong bảng thì
  diễn giải theo nội dung, không theo vấn đề.
- Câu hỏi có số hiệu/Điều (tra cứu tham chiếu) không có nút Diễn giải AI (không có bộ kết quả G2).
- OCR: số bị đọc sai không phát hiện được nếu vẫn là số hợp lệ (362/2026 trang 1 ghi “25/2016” thay
  vì “95/2016” trong dòng trích yếu); bảng biểu, chữ viết tay, dấu đỏ chưa có mẫu thử; trang
  đa cột chỉ có phần đầu văn bản 2 cột (đọc theo dòng). Thời hạn trích xuất mặc định 120 s cho cả tệp
  (~1,3–2,7 s/trang): tệp > ~60 trang cần tăng `EVIDENCE_PDF_TIMEOUT_SECONDS` (tối đa 600).
- Ba văn bản nạp đầu (362, 381, 350) dùng parser cũ: 362 còn 2 “Điều 3 …” giả và các khoản trong
  phần trích sửa đổi bị đánh nhãn theo Điều 1 (giới hạn chung của văn bản sửa đổi, có cả ở PDF chữ).
  Chỉ sửa được bằng xóa và nạp lại; chưa làm vì là thao tác xóa dữ liệu.
- Xác nhận trang OCR trong thử nghiệm do tác tử thực hiện bằng tài khoản reviewer thử, đối chiếu bố
  cục và tiêu đề, **không soát từng chữ**; các văn bản này chỉ ở danh mục thử nghiệm, chưa xác minh
  nghiệp vụ, không thuộc Gold. Chữ OCR còn lỗi (“bồ sung”, “ké từ”) được giữ nguyên như máy đọc.
- Chưa có chức năng reviewer sửa chữ OCR (chỉ xác nhận hoặc từ chối/nạp lại).
- Ứng dụng desktop Tauri/WebView2 chưa build lại, chưa thử; kết quả trên là Chrome headless.
- TXT: DB thử không có tệp TXT; không thử thêm.
