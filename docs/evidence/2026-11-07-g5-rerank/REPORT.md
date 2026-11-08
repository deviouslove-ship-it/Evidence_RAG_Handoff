# G5: kiểm thử reranker chuyên dụng (Qwen3-Reranker-0.6B) trên 100 văn bản thử

**Cập nhật cùng ngày (`REPORT-50-cau.md`):** theo quyết định của chủ sở hữu, rerank LLM không còn tự chạy; RRF thuần là mặc định của
"Tìm toàn diện" (`EVIDENCE_RERANK_DEFAULT=false`), hai phương án rerank giữ làm tùy chọn. Dữ liệu 100 tệp đã dựng lại, sao lưu và mở rộng bộ
kiểm thử lên 50 câu. Các câu về "giao diện tự gọi rerank" dưới đây mô tả trạng thái trước thay đổi đó. Phần "Hồi quy" và nơi đặt dữ liệu: xem
`REPORT-50-cau.md` và `DATA-INVENTORY.md`; CSDL của lần chạy 24 câu đầu đã bị xóa và được dựng lại giống hệt (cùng tệp, cùng model).

Ngày chạy: 07/11/2026. Máy: AMD Ryzen 9 6900HX (8 nhân, 16 luồng), RAM 29,7 GB, không GPU.
Số liệu gốc: `bench-*.json`, `compare.json`, `compare.md`, `diagnose-noi-quy.json`, `micro-latency.json`.
Mọi con số dưới đây lấy từ các tệp đó; không có số nào nhập tay vào mã.

**Trạng thái dữ liệu:** 100 tệp, 14 tệp thuộc các số hiệu có trong căn cứ bắt buộc, 86 tệp còn lại chọn theo
thứ tự SHA-256 của tên tệp (`evaluation/coverage/select_subset.py`, danh sách ở `subset-manifest.json`).
Bộ câu hỏi và căn cứ bắt buộc là `evaluation/coverage/topics.json` hiện có (8 chủ đề, 24 câu, 42 cặp câu hỏi–căn cứ).
Danh sách căn cứ **do tác tử soạn, chưa được cán bộ chuyên môn xác nhận**, nên mọi chỉ số chỉ đo so với danh sách đó.

## 1. Rerank theo lô hiện tại

- Mã: `ComprehensiveSearch._rerank` (`backend/app/storage/comprehensive.py`). Giai đoạn `rerank` của Model Registry.
- Model trong thử nghiệm: `qwen3:1.7b` (2 tỷ tham số, Q4_K_M) qua Ollama, `temperature 0`, `json_mode`, `max_tokens 1024`.
- Thuật toán: lấy 40 ứng viên đầu theo RRF (`EVIDENCE_RERANK_TOP_N`), chia lô 10 (`EVIDENCE_RERANK_BATCH_SIZE`).
  Mỗi lô là một lời nhắc yêu cầu model chấm từng đoạn bằng số nguyên 0–3 và trả JSON. Điểm xếp giảm dần, điểm bằng nhau giữ thứ tự RRF.
  Phần ngoài 40 đầu giữ nguyên thứ tự RRF. Gặp lô không có kết quả hợp lệ thì dừng, phần chưa chấm giữ thứ tự RRF.
- Hệ quả đo được: trong đầu danh sách 99,2% kết quả bị trùng điểm với kết quả khác, trung vị chỉ có 4 mức điểm
  (AUC phân tách căn cứ liên quan 0,677). Xếp hạng thực chất do thứ tự RRF quyết định, rerank chỉ đẩy các đoạn được chấm 3 lên trước.
- Giao diện hiện không gửi trường `rerank`, mà API mặc định `true`. Nếu Registry có tuyến `rerank`, mọi lần "Tìm toàn diện" đều chạy bước này
  (trên máy thử khoảng 45 giây mỗi câu hỏi).

## 2. Tích hợp thử nghiệm Qwen3-Reranker-0.6B (CPU, không API)

| Thành phần | Nội dung |
|---|---|
| Model | `Qwen/Qwen3-Reranker-0.6B` (Apache-2.0), tải về `E:\Programs\EvidenceRAG\models\qwen3-reranker-0.6b` |
| Môi trường | `E:\Programs\EvidenceRAG\runtimes\reranker-venv` (torch 2.15.0+cpu, transformers 5.22.2, psutil 7.2.2). Venv của ứng dụng không đổi |
| Dịch vụ | `scripts/local_reranker_server.py`: chỉ gắn địa chỉ loopback, fp32, 8 luồng, lô 8, tối đa 1024 token, điểm = xác suất "yes" so với "no" theo hướng dẫn của model |
| Ứng dụng | `backend/app/storage/cross_encoder.py` (chỉ nhận URL loopback) và nhánh `_rerank_cross_encoder`. Bật bằng `EVIDENCE_RERANK_BACKEND=cross_encoder` và `EVIDENCE_CROSS_ENCODER_URL` |
| Mặc định | `EVIDENCE_RERANK_BACKEND=llm`: hành vi cũ, không đổi. Không đổi model nào trong Registry |
| Khi lỗi | Dịch vụ không trả lời hoặc quá thời gian: giữ thứ tự RRF, `ranking.reranked=false` kèm ghi chú (đã gặp khi để thời gian chờ 120 giây với 200 ứng viên) |
| Ghi thêm | `ranking.duration_ms` và `ranking.backend` (trường thêm, không phá hợp đồng cũ) |

Ghi chú: bản máy chủ đầu tiên tính phép chiếu từ vựng ở mọi vị trí, gây đỉnh RAM 8,3 GB. Bản hiện tại chỉ tính ở vị trí cuối (`logits_to_keep=1`).
Thứ tự xếp hạng giống hệt bản đầu ở 24/24 câu hỏi; bảng dưới dùng bản hiện tại.

## 3. So sánh ba phương án (24 câu hỏi, 42 cặp)

Cùng `EVIDENCE_RERANK_TOP_N=40`, cùng bộ câu hỏi, mỗi phương án khởi động lại API và Ollama trước khi đo, có một câu khởi động không tính.
Recall@k tính theo cặp (câu hỏi, căn cứ): căn cứ được tính khi có ít nhất một khoản của đúng Điều đó trong k kết quả đầu.
MRR@10 và NDCG@10 tính theo khoản (khoản thuộc căn cứ bắt buộc là liên quan, điểm 0/1).
NDCG chuẩn hóa theo số khoản liên quan trong chính nhóm ứng viên, nên không so được giữa các nhóm ứng viên có kích thước khác nhau.

| Chỉ số | RRF thuần | RRF + rerank LLM hiện tại (qwen3:1.7b) | RRF + Qwen3-Reranker-0.6B |
|---|---|---|---|
| Recall@10 | 0,762 | 0,691 | 0,810 |
| Recall@20 | 0,810 | 0,833 | 0,881 |
| Recall@50 | 0,905 | 0,881 | 0,905 |
| Recall@toàn bộ nhóm | 0,929 | 0,929 | 0,929 |
| MRR@10 | 0,674 | 0,729 | 0,713 |
| NDCG@10 | 0,554 | 0,549 | 0,536 |
| Thời gian trả lời, trung vị (giây) | 2,5 | 47,7 | 32,3 |
| Thời gian trả lời, trung bình / p95 (giây) | 2,9 / 4,1 | 46,1 / 56,6 | 31,1 / 36,4 |
| Riêng bước rerank, trung vị (giây) | 0 | 45,5 | 30,0 |
| RAM đỉnh / trung vị của API | 92 / 90 MB | 96 / 90 MB | 93 / 90 MB |
| RAM đỉnh / trung vị của Ollama (embedding + qwen3:1.7b) | 3,27 / 3,17 GB | **11,23 / 11,06 GB** | 3,27 / 3,17 GB |
| RAM đỉnh / trung vị của dịch vụ rerank | không có | không có | **4,85 / 3,85 GB** |
| Điểm rerank phân tách căn cứ liên quan (AUC, 0,5 = ngẫu nhiên) | không có | 0,677 | 0,801 |

Đọc kết quả:

- Recall@50 và Recall@toàn bộ không đổi giữa phương án có rerank và RRF, vì rerank chỉ đổi thứ tự trong 40 kết quả đầu. Khác biệt 0,881 so với 0,905 của phương án LLM đến từ nhóm ứng viên khác ở 3 câu hỏi (nguyên nhân chưa xác minh; nghi do bước `expand` hoặc hạn thời gian của kênh khái niệm khi máy tải nặng).
- Chỉ xét 21 câu hỏi có nhóm ứng viên giống hệt ở cả ba phương án: Recall@10 0,784 / 0,703 / 0,811; Recall@20 0,838 / 0,865 / 0,892; MRR@10 0,689 / 0,714 / 0,708; NDCG@10 0,540 / 0,524 / 0,512; P@10 0,409 / 0,362 / 0,391 (RRF / LLM / Qwen3).
- Theo từng câu hỏi, MRR@10 so với RRF: LLM tốt hơn 9, kém hơn 4, bằng 11; Qwen3 tốt hơn 8, kém hơn 5, bằng 11.
- Chênh lệch trung bình so với RRF (khoảng tin cậy 95% bootstrap, 24 câu hỏi): LLM MRR +0,055 [−0,089; +0,188], NDCG −0,005 [−0,108; +0,091]; Qwen3 MRR +0,039 [−0,129; +0,209], NDCG −0,018 [−0,089; +0,053]. Mọi khoảng đều chứa 0, nên với 24 câu hỏi chưa có bằng chứng rằng phương án nào hơn RRF thuần.
- Qwen3 phân tách tốt hơn (AUC 0,801 với điểm liên tục, 0,7% trùng điểm) và Recall@10/20 cao nhất, nhưng NDCG@10 thấp hơn RRF một chút (không có ý nghĩa thống kê).
- Hai phương án rerank đều chậm: 32 và 48 giây mỗi câu hỏi so với 2,5 giây. Với Qwen3 chỉ xếp lại 20 kết quả đầu (thí nghiệm D): trung vị 19,8 giây, MRR@10 0,696, NDCG@10 0,530, Recall@10/20/50 như RRF.

Đo độ trễ riêng bước chấm điểm Qwen3 (40 đoạn 600 ký tự, `micro-latency.json`): 39,4 giây (8 luồng), 40,9 giây (16 luồng), 38,6 giây (lô 4), 40,5 giây (độ dài 512): không cấu hình nào nhanh hơn. Bỏ phép chiếu từ vựng ở mọi vị trí còn 32,8 giây, điểm không đổi. bf16 mất 298 giây. int8 động còn 21,4 giây nhưng chỉ trùng 3/10 kết quả đầu với fp32 (lệch điểm tối đa 0,48), không dùng được.

## 4. Hai căn cứ chưa tìm thấy: lỗi truy xuất ứng viên hay lỗi xếp hạng

Trên 100 tệp, ba cặp không nằm trong nhóm ứng viên của bất kỳ kênh nào (RRF, cả ba phương án đều giống nhau):
58/2026 Điều 11 với câu "nội quy cơ sở giam giữ phạm nhân và nội quy trại tạm giam", 96/2026 Điều 3 với câu "đồ vật cấm đưa vào buồng tạm giữ tạm giam",
và 110/2021 Điều 2 với câu "Thông tư 29/2016/TT-BCA còn hiệu lực không" (cặp thứ ba chưa phân tích nguyên nhân, nhưng được tìm thấy ở thí nghiệm A).
Hai cặp đầu trùng với hai cặp thiếu của lần đo G5 trên 293 văn bản.

**Kết luận: cả hai là lỗi truy xuất ứng viên, không phải lỗi xếp hạng.** Dữ liệu từ `diagnose-noi-quy.json`:

| | 58/2026 Điều 11 (câu 1) | 96/2026 Điều 3 (câu 2) |
|---|---|---|
| Khoản có trong kho và có vector | có (3 khoản) | có (8 khoản, thuộc 2 văn bản cùng số 96/2026) |
| Vị trí thật của vector gần nhất trong 7.230 vector | 26 (độ tương đồng 0,563) | 52 (0,530) |
| Ngưỡng của kênh theo nghĩa (0,8 × kết quả tốt nhất) | 0,622: bị loại | 0,653: bị loại |
| Kênh chính xác / khái niệm | 4 và 80 khoản, không chứa | 7 và 146 khoản, không chứa |
| Nội dung | "Hiệu lực thi hành", thay 32/2017 và 36/2017 | Điều 3 của nội quy phạm nhân (chỗ nằm, ăn uống), và Điều 3 "Hiệu lực thi hành" của thông tư ban hành |

Thử hạ ngưỡng xuống 0,6 (chỉ đổi cấu hình `EVIDENCE_SEMANTIC_RELATIVE_THRESHOLD`, thí nghiệm A–F):

- Cả 42/42 cặp vào được nhóm ứng viên (Recall@toàn bộ 0,929 lên 1,000). Tổng số khoản ứng viên của 24 câu tăng từ 6.059 lên 8.836 (1,46 lần); riêng hai câu này tăng 148 lên 172 và 352 lên 368, còn câu đầu của chủ đề vân tay tăng 8 lên 153. Recall@20 tăng 0,810 lên 0,857, MRR@10 0,674 lên 0,680, P@10 gần như không đổi (0,408 so với 0,404).
- Sau khi vào nhóm, hai căn cứ đứng ở hạng RRF 78 và 125, tức ngoài 40 kết quả đầu mà rerank xử lý.
- Cho rerank xử lý toàn bộ nhóm (tối đa 200): Qwen3 đưa chúng về hạng 91 (điểm 0,057) và 49 (điểm 0,224); LLM hiện tại về hạng 20 và 42. Không phương án nào đưa vào top 10.
- Lý do hợp lý: hai điều này là điều khoản hiệu lực thi hành hoặc nội dung quy định cho phạm nhân, còn câu hỏi hỏi về nội quy trại tạm giam và đồ vật cấm. Chúng được tìm đúng qua quan hệ hiệu lực (kênh `relation`), nhưng ở bộ 100 tệp này chưa có quan hệ nào được duyệt, nên kênh đó không đóng góp. Căn cứ 96/2026 Điều 3 cho câu 2 có thể là nhãn chưa đúng; cần cán bộ xác nhận.

Vì vậy đổi reranker không thể sửa hai căn cứ này. Hướng sửa nằm ở truy xuất: hạ ngưỡng theo nghĩa, hoặc duyệt quan hệ hiệu lực để kênh quan hệ hoạt động.

## 5. Khuyến nghị lựa chọn

1. **Chưa đổi mặc định.** Chưa có phương án nào hơn RRF thuần một cách có ý nghĩa thống kê trên bộ câu hỏi này, mà cả hai rerank tốn 30 đến 48 giây mỗi câu hỏi.
2. **Rerank LLM hiện tại** (`qwen3:1.7b`): điểm gần như trùng hết (99,2%), Recall@10 thấp hơn RRF (0,691 so với 0,762), RAM Ollama tăng từ 3,3 lên 11,2 GB, 48 giây mỗi câu hỏi. Giao diện đang gọi nó theo mặc định `rerank=true`; nên cân nhắc tắt trên máy không GPU.
3. **Qwen3-Reranker-0.6B** là phương án rerank tốt hơn về chất lượng điểm (AUC 0,801 so với 0,677), nhanh hơn 1,5 lần và không cần Ollama, nhưng 32 giây mỗi câu hỏi (20 giây với 20 ứng viên) vẫn quá chậm cho tra cứu trực tiếp, và cần thêm 3,9 GB RAM (đỉnh 4,9 GB). Có thể dùng như chế độ "xếp hạng sâu" chạy nền hoặc trên máy có GPU; chưa đo GPU.
4. **Việc nên làm trước khi chọn:** (a) để cán bộ chuyên môn xác nhận danh sách căn cứ; (b) mở rộng bộ câu hỏi (24 câu quá ít, mọi khoảng tin cậy chứa 0); (c) quyết định ngưỡng kênh theo nghĩa (thí nghiệm A cho thấy Recall tăng khi hạ ngưỡng); (d) duyệt quan hệ hiệu lực cho hai thông tư nội quy.

## 6. Giới hạn

- Chỉ 100 văn bản; bộ 293 văn bản của lần đo G5 trước cho số liệu khác (nhóm ứng viên khác).
- 24 câu hỏi, 42 cặp; không có kiểm tra ý nghĩa thống kê nào vượt qua.
- Nhóm ứng viên của phương án LLM khác ở 3/24 câu hỏi (nguyên nhân chưa xác minh); đã báo cáo riêng bảng 21 câu giống hệt.
- Một lần chạy mỗi phương án; thời gian và RAM phụ thuộc máy (CPU 8 nhân, fp32, 8 luồng).
- Chạy thử thời gian chờ 120 giây với 200 ứng viên không để lại tệp kết quả riêng; hành vi quay về thứ tự RRF đã quan sát trực tiếp.
- Chưa thử GPU, chưa thử mô hình rerank lớn hơn (4B, 8B), chưa tối ưu lời nhắc hướng dẫn của Qwen3 (dùng một câu cố định).

## 7. Hồi quy

`scripts/verify.ps1 -ProgramsRoot E:\Programs` đạt 12/12 (`verify/`): backend 218 passed (không đổi so với trước), frontend 74 passed,
ruff, mypy, 13 cặp migration, OpenAPI và kiểm tra đường dẫn cứng đều sạch. Không thêm test mới.
