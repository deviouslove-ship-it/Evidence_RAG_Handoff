# So sánh ba phương án xếp hạng (G5)

Số câu hỏi: 24, cặp (câu hỏi, căn cứ bắt buộc): 42.

| Chỉ số | RRF thuần | RRF + rerank LLM hiện tại (qwen3:1.7b) | RRF + Qwen3-Reranker-0.6B |
|---|---|---|---|
| recall@10 | 0.762 | 0.691 | 0.809 |
| recall@20 | 0.809 | 0.833 | 0.881 |
| recall@50 | 0.905 | 0.881 | 0.905 |
| recall@all | 0.929 | 0.929 | 0.929 |
| mrr@10 | 0.674 | 0.729 | 0.713 |
| ndcg@10 | 0.554 | 0.549 | 0.536 |
| seconds_median | 2.476 | 47.657 | 32.292 |
| seconds_mean | 2.913 | 46.093 | 31.140 |
| seconds_p95 | 4.060 | 56.579 | 36.380 |
| rerank_ms_median | 0.000 | 45463.600 | 29986.200 |
| queries_reranked | 0 | 24 | 24 |

Bộ nhớ (MB, đo trong lúc chạy 24 câu hỏi):

- RRF thuần: api đỉnh 91.9 / trung vị 89.5, ollama đỉnh 3269.6 / trung vị 3168.7
- RRF + rerank LLM hiện tại (qwen3:1.7b): api đỉnh 95.6 / trung vị 90.4, ollama đỉnh 11229.8 / trung vị 11055.4
- RRF + Qwen3-Reranker-0.6B: api đỉnh 93.3 / trung vị 90.2, reranker đỉnh 4846.6 / trung vị 3847.9, ollama đỉnh 3270.7 / trung vị 3169.9

Nhóm ứng viên giống nhau giữa ba phương án: 21/24 câu hỏi.

So với RRF thuần (MRR@10 theo từng câu hỏi): RRF + rerank LLM hiện tại (qwen3:1.7b): tốt hơn 9, kém hơn 4, bằng 11; RRF + Qwen3-Reranker-0.6B: tốt hơn 8, kém hơn 5, bằng 11

## Hai căn cứ nội quy giam giữ

| Câu hỏi | Căn cứ | RRF | LLM | Qwen3 | Chẩn đoán |
|---|---|---|---|---|---|
| nội quy cơ sở giam giữ phạm nhân và nội quy trại tạm giam | 58/2026/TT-BCA Điều 11 | - | - | - | lỗi truy xuất ứng viên (không nằm trong nhóm ứng viên của kênh nào) |
| nội quy cơ sở giam giữ phạm nhân và nội quy trại tạm giam | 96/2026/TT-BCA Điều 3 | 7 | 6 | 6 | tìm thấy ở top 10 theo RRF |
| đồ vật cấm đưa vào buồng tạm giữ tạm giam | 58/2026/TT-BCA Điều 11 | 1 | 1 | 1 | tìm thấy ở top 10 theo RRF |
| đồ vật cấm đưa vào buồng tạm giữ tạm giam | 96/2026/TT-BCA Điều 3 | - | - | - | lỗi truy xuất ứng viên (không nằm trong nhóm ứng viên của kênh nào) |
| thông tư nội quy cơ sở giam giữ hiệu lực 01/7/2026 | 58/2026/TT-BCA Điều 11 | 6 | 7 | 7 | tìm thấy ở top 10 theo RRF |
| thông tư nội quy cơ sở giam giữ hiệu lực 01/7/2026 | 96/2026/TT-BCA Điều 3 | 2 | 3 | 2 | tìm thấy ở top 10 theo RRF |

Khả năng tách căn cứ liên quan khỏi phần còn lại của đầu danh sách bằng điểm rerank (AUC trung bình theo câu hỏi, 0,5 = ngẫu nhiên; điểm trùng nhau quay về thứ tự RRF):

- RRF + rerank LLM hiện tại (qwen3:1.7b): AUC 0.677 trên 23 câu hỏi; tỷ lệ kết quả bị trùng điểm 0.992; số mức điểm khác nhau (trung vị) 4.0
- RRF + Qwen3-Reranker-0.6B: AUC 0.801 trên 23 câu hỏi; tỷ lệ kết quả bị trùng điểm 0.007; số mức điểm khác nhau (trung vị) 40.0

## Chỉ xét 21 câu hỏi có nhóm ứng viên giống hệt ở cả ba phương án

| Chỉ số | RRF thuần | RRF + rerank LLM hiện tại (qwen3:1.7b) | RRF + Qwen3-Reranker-0.6B |
|---|---|---|---|
| recall@10 | 0.784 | 0.703 | 0.811 |
| recall@20 | 0.838 | 0.865 | 0.892 |
| recall@50 | 0.919 | 0.919 | 0.919 |
| mrr@10 | 0.689 | 0.714 | 0.708 |
| ndcg@10 | 0.540 | 0.524 | 0.512 |
| p@10 | 0.409 | 0.362 | 0.391 |

Chênh lệch trung bình so với RRF thuần (khoảng tin cậy 95% bootstrap, 10.000 lần lấy mẫu):

- all_queries / RRF + rerank LLM hiện tại (qwen3:1.7b): mrr@10 +0.055 [-0.089; +0.188]; ndcg@10 -0.005 [-0.108; +0.091]
- all_queries / RRF + Qwen3-Reranker-0.6B: mrr@10 +0.039 [-0.129; +0.209]; ndcg@10 -0.018 [-0.089; +0.053]
- matched_pool / RRF + rerank LLM hiện tại (qwen3:1.7b): mrr@10 +0.025 [-0.134; +0.168]; ndcg@10 -0.016 [-0.134; +0.090]
- matched_pool / RRF + Qwen3-Reranker-0.6B: mrr@10 +0.019 [-0.164; +0.207]; ndcg@10 -0.028 [-0.104; +0.049]

## Thí nghiệm bổ sung: A. Ngưỡng tương đồng 0,6, RRF thuần, đủ 24 câu

Số câu hỏi: 24; số lần xếp hạng lại: 0; thời gian rerank trung vị (ms): 0.000

| Chỉ số | Thí nghiệm | RRF thuần (chạy chính) | LLM (chạy chính) | Qwen3 (chạy chính) |
|---|---|---|---|---|
| recall@10 | 0.762 | 0.762 | 0.691 | 0.809 |
| recall@20 | 0.857 | 0.809 | 0.833 | 0.881 |
| recall@50 | 0.905 | 0.905 | 0.881 | 0.905 |
| recall@all | 1.000 | 0.929 | 0.929 | 0.929 |
| mrr@10 | 0.680 | 0.674 | 0.729 | 0.713 |
| ndcg@10 | 0.458 | 0.554 | 0.549 | 0.536 |
| p@10 | 0.404 | 0.408 | 0.362 | 0.392 |

Kích thước nhóm ứng viên theo câu hỏi - thí nghiệm: 153, 270, 1087, 261, 205, 165, 272, 231, 302, 144, 324, 189, 295, 277, 347, 337, 324, 302, 172, 368, 229, 641, 835, 1106; RRF chính: 8, 86, 956, 100, 35, 32, 86, 83, 142, 70, 233, 36, 197, 130, 280, 237, 207, 157, 148, 352, 183, 579, 737, 985
Căn cứ không có trong nhóm ứng viên: không có

## Thí nghiệm bổ sung: B. Ngưỡng 0,6, Qwen3 xếp lại 40 đầu, chủ đề nội quy giam giữ

Số câu hỏi: 3; số lần xếp hạng lại: 3; thời gian rerank trung vị (ms): 32482.800

| Chỉ số | Thí nghiệm | RRF thuần (chạy chính) | LLM (chạy chính) | Qwen3 (chạy chính) |
|---|---|---|---|---|
| recall@10 | 0.667 | 0.667 | 0.667 | 0.667 |
| recall@20 | 0.667 | 0.667 | 0.667 | 0.667 |
| recall@50 | 0.667 | 0.667 | 0.667 | 0.667 |
| recall@all | 1.000 | 0.667 | 0.667 | 0.667 |
| mrr@10 | 0.556 | 0.548 | 0.500 | 0.556 |
| ndcg@10 | 0.290 | 0.510 | 0.494 | 0.530 |
| p@10 | 0.167 | 0.167 | 0.167 | 0.200 |

Kích thước nhóm ứng viên theo câu hỏi - thí nghiệm: 172, 368, 229; RRF chính: 148, 352, 183
Căn cứ không có trong nhóm ứng viên: không có

## Thí nghiệm bổ sung: C. Ngưỡng 0,6, LLM hiện tại xếp lại 40 đầu, chủ đề nội quy giam giữ

Số câu hỏi: 3; số lần xếp hạng lại: 3; thời gian rerank trung vị (ms): 38078.200

| Chỉ số | Thí nghiệm | RRF thuần (chạy chính) | LLM (chạy chính) | Qwen3 (chạy chính) |
|---|---|---|---|---|
| recall@10 | 0.667 | 0.667 | 0.667 | 0.667 |
| recall@20 | 0.667 | 0.667 | 0.667 | 0.667 |
| recall@50 | 0.667 | 0.667 | 0.667 | 0.667 |
| recall@all | 1.000 | 0.667 | 0.667 | 0.667 |
| mrr@10 | 0.733 | 0.548 | 0.500 | 0.556 |
| ndcg@10 | 0.317 | 0.510 | 0.494 | 0.530 |
| p@10 | 0.133 | 0.167 | 0.167 | 0.200 |

Kích thước nhóm ứng viên theo câu hỏi - thí nghiệm: 172, 203, 229; RRF chính: 148, 352, 183
Căn cứ không có trong nhóm ứng viên: không có

## Thí nghiệm bổ sung: D. Qwen3 xếp lại 20 kết quả đầu, đủ 24 câu

Số câu hỏi: 24; số lần xếp hạng lại: 24; thời gian rerank trung vị (ms): 19750.050

| Chỉ số | Thí nghiệm | RRF thuần (chạy chính) | LLM (chạy chính) | Qwen3 (chạy chính) |
|---|---|---|---|---|
| recall@10 | 0.762 | 0.762 | 0.691 | 0.809 |
| recall@20 | 0.809 | 0.809 | 0.833 | 0.881 |
| recall@50 | 0.905 | 0.905 | 0.881 | 0.905 |
| recall@all | 0.929 | 0.929 | 0.929 | 0.929 |
| mrr@10 | 0.696 | 0.674 | 0.729 | 0.713 |
| ndcg@10 | 0.530 | 0.554 | 0.549 | 0.536 |
| p@10 | 0.383 | 0.408 | 0.362 | 0.392 |

Kích thước nhóm ứng viên theo câu hỏi - thí nghiệm: 8, 86, 956, 100, 35, 32, 86, 83, 142, 70, 233, 36, 197, 130, 280, 237, 207, 157, 148, 352, 183, 579, 737, 985; RRF chính: 8, 86, 956, 100, 35, 32, 86, 83, 142, 70, 233, 36, 197, 130, 280, 237, 207, 157, 148, 352, 183, 579, 737, 985
Căn cứ không có trong nhóm ứng viên: 110/2021/TT-BCA Điều 2 :: Thông tư 29/2016/TT-BCA còn hiệu lực không; 58/2026/TT-BCA Điều 11 :: nội quy cơ sở giam giữ phạm nhân và nội quy trại tạm giam; 96/2026/TT-BCA Điều 3 :: đồ vật cấm đưa vào buồng tạm giữ tạm giam

## Thí nghiệm bổ sung: E. Ngưỡng 0,6, Qwen3 xếp lại toàn bộ nhóm ứng viên (tối đa 200), chủ đề nội quy giam giữ

Số câu hỏi: 3; số lần xếp hạng lại: 3; thời gian rerank trung vị (ms): 147604.700

| Chỉ số | Thí nghiệm | RRF thuần (chạy chính) | LLM (chạy chính) | Qwen3 (chạy chính) |
|---|---|---|---|---|
| recall@10 | 0.667 | 0.667 | 0.667 | 0.667 |
| recall@20 | 0.667 | 0.667 | 0.667 | 0.667 |
| recall@50 | 0.833 | 0.667 | 0.667 | 0.667 |
| recall@all | 1.000 | 0.667 | 0.667 | 0.667 |
| mrr@10 | 0.548 | 0.548 | 0.500 | 0.556 |
| ndcg@10 | 0.259 | 0.510 | 0.494 | 0.530 |
| p@10 | 0.133 | 0.167 | 0.167 | 0.200 |

Kích thước nhóm ứng viên theo câu hỏi - thí nghiệm: 172, 368, 229; RRF chính: 148, 352, 183
Căn cứ không có trong nhóm ứng viên: không có

## Thí nghiệm bổ sung: F. Ngưỡng 0,6, LLM hiện tại xếp lại toàn bộ nhóm ứng viên (tối đa 200), chủ đề nội quy giam giữ

Số câu hỏi: 3; số lần xếp hạng lại: 3; thời gian rerank trung vị (ms): 188938.500

| Chỉ số | Thí nghiệm | RRF thuần (chạy chính) | LLM (chạy chính) | Qwen3 (chạy chính) |
|---|---|---|---|---|
| recall@10 | 0.667 | 0.667 | 0.667 | 0.667 |
| recall@20 | 0.833 | 0.667 | 0.667 | 0.667 |
| recall@50 | 1.000 | 0.667 | 0.667 | 0.667 |
| recall@all | 1.000 | 0.667 | 0.667 | 0.667 |
| mrr@10 | 0.733 | 0.548 | 0.500 | 0.556 |
| ndcg@10 | 0.317 | 0.510 | 0.494 | 0.530 |
| p@10 | 0.133 | 0.167 | 0.167 | 0.200 |

Kích thước nhóm ứng viên theo câu hỏi - thí nghiệm: 172, 203, 229; RRF chính: 148, 352, 183
Căn cứ không có trong nhóm ứng viên: không có

## Thí nghiệm bổ sung: G. Qwen3 bản máy chủ đầu tiên (chưa bỏ phép chiếu từ vựng ở mọi vị trí), đủ 24 câu

Số câu hỏi: 24; số lần xếp hạng lại: 24; thời gian rerank trung vị (ms): 35067.750

| Chỉ số | Thí nghiệm | RRF thuần (chạy chính) | LLM (chạy chính) | Qwen3 (chạy chính) |
|---|---|---|---|---|
| recall@10 | 0.809 | 0.762 | 0.691 | 0.809 |
| recall@20 | 0.881 | 0.809 | 0.833 | 0.881 |
| recall@50 | 0.905 | 0.905 | 0.881 | 0.905 |
| recall@all | 0.929 | 0.929 | 0.929 | 0.929 |
| mrr@10 | 0.713 | 0.674 | 0.729 | 0.713 |
| ndcg@10 | 0.536 | 0.554 | 0.549 | 0.536 |
| p@10 | 0.392 | 0.408 | 0.362 | 0.392 |

Kích thước nhóm ứng viên theo câu hỏi - thí nghiệm: 8, 86, 956, 100, 35, 32, 86, 83, 142, 70, 233, 36, 197, 130, 280, 237, 207, 157, 148, 352, 183, 579, 737, 985; RRF chính: 8, 86, 956, 100, 35, 32, 86, 83, 142, 70, 233, 36, 197, 130, 280, 237, 207, 157, 148, 352, 183, 579, 737, 985
Căn cứ không có trong nhóm ứng viên: 110/2021/TT-BCA Điều 2 :: Thông tư 29/2016/TT-BCA còn hiệu lực không; 58/2026/TT-BCA Điều 11 :: nội quy cơ sở giam giữ phạm nhân và nội quy trại tạm giam; 96/2026/TT-BCA Điều 3 :: đồ vật cấm đưa vào buồng tạm giữ tạm giam
