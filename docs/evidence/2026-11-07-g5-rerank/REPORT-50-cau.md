# G5: mở rộng lên 50 câu hỏi, RRF thuần mặc định, dựng lại và sao lưu dữ liệu 100 văn bản

Ngày chạy: 07/11/2026. Bổ sung cho `REPORT.md` (so sánh ba phương án xếp hạng trên 24 câu). Số liệu gốc cùng thư mục.
Không nghiệm thu nghiệp vụ: danh sách căn cứ bắt buộc do tác tử soạn từ chữ của văn bản, chưa được cán bộ chuyên môn xác nhận.

## 1. Quyết định đã áp dụng

| Quyết định của chủ sở hữu | Cách thực hiện | Kiểm tra |
|---|---|---|
| Giữ ngưỡng kênh theo nghĩa 0,8; 0,6 chỉ để thử, đổi được qua cấu hình | Không đổi mã. `EVIDENCE_SEMANTIC_RELATIVE_THRESHOLD` (mặc định 0,8, hợp lệ trong [0; 1]) | Các lần chạy dưới đây dùng 0,8 |
| Tắt rerank LLM tự động; RRF thuần là mặc định của "Tìm toàn diện"; giữ hai phương án rerank để tùy chọn | `rerank` của API nhận `true`, `false` hoặc vắng; vắng = giá trị máy chủ `EVIDENCE_RERANK_DEFAULT` (mặc định `false`). Mặc định của bản ghi nội bộ cũng đổi thành `false`. OpenAPI cập nhật | Gọi không nêu `rerank`: `reranked=false`, 0/50 câu bị xếp hạng lại. `rerank:true` với LLM: 40 kết quả, 38,1 giây. `rerank:true` với Qwen3-Reranker-0.6B: 40 kết quả, 25,4 giây |

Backend rerank vẫn chọn bằng `EVIDENCE_RERANK_BACKEND` (`llm` hoặc `cross_encoder`). Không chạy lại benchmark reranker theo yêu cầu.

## 2. Bộ 50 câu hỏi

`evaluation/coverage/topics.json`: 17 chủ đề, 50 câu, 74 cặp (câu hỏi, căn cứ bắt buộc). 24 câu gốc giữ nguyên; 26 câu mới
(9 chủ đề, `"set": "v2"`) soạn từ chữ của 100 văn bản **trước khi chạy bất kỳ lần tìm nào trên chúng**:

| Chủ đề | Câu | Căn cứ bắt buộc |
|---|---|---|
| to_cao_cand | 3 | 10/2014/TT-BCA Điều 9 |
| the_cccd_thoi_han_xu_ly | 3 | 60/2021/TT-BCA Điều 11 |
| tai_nan_giao_thong_thoi_han | 3 | 63/2020/TT-BCA Điều 18 |
| am_hieu_coi_dieu_khien_giao_thong | 3 | 69/2024/TT-BCA Điều 15 |
| hieu_lenh_dung_phuong_tien | 3 | Điều 17 của 32/2023 và 65/2020, Điều 13 của 73/2024 (ba thông tư có điều cùng tên) |
| ung_xu_dien_thoai_mang | 3 | 27/2017/TT-BCA Điều 13 |
| cong_khai_tuyen_sinh | 3 | 44/2021/TT-BCA Điều 5 |
| niem_phong_mau_nuoc_thai | 3 | 71/2023/TT-BCA Điều 14 |
| xu_ly_vphc_duong_sat | 2 | 26/2010/TT-BCA Điều 8 |

Bảy câu bản nháp dài hơn 20 từ nên bị API từ chối (`TOO_MANY_TERMS`, giới hạn có sẵn của hệ thống) trước khi trả về bất kỳ kết quả nào;
tôi rút gọn bảy câu đó, không đổi căn cứ và chưa xem kết quả của chúng. Hạn chế: câu mới viết sát chữ của điều khoản nên dễ hơn cách hỏi
tự nhiên; không so trực tiếp điểm của bộ mới với bộ gốc.

## 3. Dựng lại dữ liệu một lần

- Tập tệp: dựng lại bằng `select_subset.py`, danh sách và SHA-256 **giống hệt** `subset-manifest.json` của lần trước (100 tệp: 14 tệp theo căn cứ, 86 tệp theo SHA-256 tên tệp).
- Nhập 100 tệp, duyệt (chế độ thử): 100/100 đã duyệt, 92,3 giây. Trích xuất hiệu lực chạy sau đó.
- Embedding `qwen3-embedding:0.6b`: 7.230/7.230 khoản, 0 lỗi, 42 phút 24 giây (khoảng 2,8 khoản/giây), chỉ mục sẵn sàng, 1024 chiều.
- Đặt ở nơi lâu dài (`data\rerank-eval`, DB `evidence_rerank_eval`, `backups\rerank-eval`), không còn trong thư mục tạm. Chi tiết: `DATA-INVENTORY.md`.

## 4. Sao lưu ngay sau khi tạo xong và kiểm tra khôi phục

`pg_dump -Fc` chạy 6 giây sau khi chỉ mục sẵn sàng, trước mọi lần đo: 37,0 MB, SHA-256 `915b89b1…ab66c`. Danh mục (`.toc.txt`, 316 mục) có dữ liệu
`node_embeddings`, chỉ mục HNSW và tiện ích `vector`. Khôi phục vào DB `evidence_rerank_eval_restorecheck`: 6 giây, không lỗi.
`scripts/verify_db_restore.py` (kết quả `db-restore-verification.json`): **đạt**.

| Kiểm tra | Kết quả |
|---|---|
| Số dòng 51 bảng (36.565 dòng) | bằng nhau từng bảng |
| Tổng kiểm văn bản khoản; tổng kiểm 7.230 vector | bằng nhau |
| 98 chỉ mục | cùng tên, đều hợp lệ; HNSW có mặt và kế hoạch truy vấn dùng nó |
| 5 khoản mẫu, 5 láng giềng gần nhất | giống hệt ở hai CSDL |
| 24 câu chạy trên bản khôi phục (API cổng 8766) so với CSDL gốc cùng phiên | nhóm ứng viên bằng nhau 24/24, 10 kết quả đầu giống hệt 23/24, hạng căn cứ bằng nhau 23/24, Recall và MRR bằng nhau |

Kho tài liệu nén riêng (59,2 MB). Cả CSDL gốc, bản khôi phục, kho tài liệu và bản sao lưu đều được giữ.

## 5. Chạy lại 24 câu cũ trên dữ liệu dựng lại

| Chỉ số | Lần chạy trước (DB đã xóa) | Dựng lại, lần 1 | Dựng lại, lần 2 (cùng DB, vài phút sau) |
|---|---|---|---|
| Recall@10 / @20 / @50 | 0,762 / 0,810 / 0,905 | 0,762 / 0,810 / 0,905 | 0,762 / 0,810 / 0,881 |
| Recall@toàn bộ nhóm | 0,929 | 0,929 | 0,929 |
| MRR@10 | 0,674 | 0,652 | 0,681 |
| NDCG@10 | 0,554 | 0,534 | 0,541 |
| P@10 | 0,408 | 0,404 | 0,404 |
| Nhóm ứng viên bằng lần trước | | 20/24 | 19/24 (so với lần 1) |
| 10 kết quả đầu giống hệt lần trước | | 5/24 | 18/24 (so với lần 1) |
| Hạng của mọi căn cứ bằng lần trước | | 17/24 | 20/24 (so với lần 1) |

**Đối chiếu đạt về Recall; thứ tự chi tiết không tái lập từng vị trí.** Recall@10, @20 và Recall@toàn bộ giống hệt lần chạy trước; MRR và NDCG lệch 0,02,
cùng cỡ với mức lệch giữa hai lần chạy liên tiếp trên cùng một CSDL (MRR 0,03; NDCG 0,01). Ba căn cứ vắng (58/2026 Điều 11, 96/2026 Điều 3, 110/2021 Điều 2) vẫn vắng.
Nguyên nhân khác biệt (chưa tách riêng từng nguyên nhân):

- Khi hòa điểm, mã xếp theo `node_id` (ở `_rrf`, kênh chính xác và kênh quan hệ; đã sửa ở `REPORT-tiebreak.md`); nút mới có UUID mới, nên 10 kết quả đầu đổi chỗ (5/24 câu giống hệt), trong khi bản khôi phục giữ nguyên id nên giống 23/24.
- Chỉ mục HNSW dựng mới cho xấp xỉ gần nhất hơi khác.
- Bước `expand` (qwen3:1.7b) cho cụm mở rộng khác nhau giữa các lần gọi ở một số câu, làm nhóm ứng viên của kênh khái niệm đổi (cùng CSDL, hai lần liên tiếp: nhóm khác nhau ở 5/24 câu ở lần 1 và lần 2; ở 50 câu liên tiếp là 11/50).

## 6. Kết quả RRF thuần, 50 câu (`bench-rrf-50.json`, `rrf-50-summary.md`)

| Bộ | Câu | Cặp | R@10 | R@20 | R@50 | R@toàn bộ | MRR@10 | NDCG@10 | P@10 |
|---|---|---|---|---|---|---|---|---|---|
| 24 câu gốc | 24 | 42 | 0,762 | 0,809 | 0,881 | 0,929 | 0,681 | 0,541 | 0,404 |
| 26 câu bổ sung | 26 | 32 | 1,000 | 1,000 | 1,000 | 1,000 | 0,891 | 0,642 | 0,288 |
| **Cả 50 câu** | 50 | 74 | **0,865** | **0,892** | **0,932** | **0,960** | **0,790** | **0,594** | 0,344 |

- Thời gian trả lời: trung vị 2,2 giây, trung bình 2,4 giây, lớn nhất 10,5 giây. RAM: API đỉnh 97 MB; Ollama đỉnh 3,6 GB. 0/50 câu bị xếp hạng lại.
- Lần chạy lặp lại ngay sau đó (`bench-rrf-50-repeat.json`): Recall giống hệt, MRR 0,784, NDCG 0,608, P@10 0,348; hạng căn cứ bằng nhau 49/50 câu; nhóm ứng viên bằng nhau 39/50 câu. Mức nhiễu giữa các lần chạy khoảng ±0,01 đến 0,02 cho MRR và NDCG.
- Cả 32 cặp của bộ bổ sung nằm trong 10 kết quả đầu. Điều dễ hơn bộ gốc do câu viết sát chữ điều khoản; đồng thời P@10 thấp hơn (0,288). Nguyên nhân chưa kiểm: có thể do mỗi chủ đề mới chỉ có một Điều bắt buộc, còn các khoản khác cùng chủ đề (điều khác trong cùng thông tư, thông tư tương tự) không được tính là liên quan.
- Căn cứ không có trong nhóm ứng viên, giống lần trước vì ngưỡng giữ 0,8: 58/2026 Điều 11 (câu "nội quy cơ sở giam giữ phạm nhân…"), 96/2026 Điều 3 (câu "đồ vật cấm đưa vào buồng tạm giữ…"), 110/2021 Điều 2 (câu "Thông tư 29/2016/TT-BCA còn hiệu lực không"). Bảy cặp khác nằm trong nhóm nhưng ngoài 10 kết quả đầu, ở hạng 12, 16, 23, 34, 37, 60 và 327 (chủ đề khiếu nại, cư trú, kiểm tra giấy tờ định danh). Hạng 327 trong nhóm 949 là 32/2023 Điều 12 với câu "tuần tra kiểm soát kiểm tra giấy tờ đã tích hợp căn cước điện tử", chỉ do kênh khái niệm tìm được.

## 7. Hồi quy

`scripts/verify.ps1 -ProgramsRoot E:\Programs` đạt 12/12 (`verify-50/`): backend 218 passed, frontend 74 passed, ruff, mypy, 13 cặp migration, OpenAPI (đã cập nhật), kiểm tra đường dẫn cứng.
Không thêm test mới. Các tệp đã đổi: `config.py`, `api/v1/comprehensive.py`, `storage/comprehensive.py`, OpenAPI; công cụ mới/đổi trong `evaluation/coverage` và `scripts/verify_db_restore.py`.

## 8. Giới hạn

- Căn cứ bắt buộc chưa xác nhận; bộ bổ sung dễ hơn bộ gốc.
- Kết quả không xác định từng bit: mỗi lần gọi `expand` có thể cho cụm mở rộng khác. Nên so sánh bằng Recall và khoảng dao động ±0,02, không so từng vị trí.
- Các số ở báo cáo này đo khi hòa điểm còn xếp theo UUID. Từ 08/11/2026 khóa phá hòa đã đổi sang khóa ổn định theo số hiệu văn bản và vị trí khoản (`REPORT-tiebreak.md`); số đo mới của 50 câu nằm ở đó.
- Chưa đo trên máy Windows đích và chưa thử GPU.
