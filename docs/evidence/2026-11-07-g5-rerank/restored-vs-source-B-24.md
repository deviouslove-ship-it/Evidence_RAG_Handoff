# Đối chiếu kết quả sau khi dựng lại dữ liệu

24 câu hỏi của bộ gốc, so theo (số hiệu, nhãn khoản) theo thứ tự.

- Kích thước nhóm ứng viên bằng nhau: 24/24
- 10 kết quả đầu giống hệt: 23/24
- 50 kết quả đầu giống hệt: 18/24
- Hạng của mọi căn cứ bắt buộc bằng nhau: 23/24

| Chỉ số | Lần chạy trước (DB đã xóa) | Sau khi dựng lại |
|---|---|---|
| recall@10 | 0.7619 | 0.7619 |
| recall@20 | 0.8095 | 0.8095 |
| recall@50 | 0.881 | 0.881 |
| recall@all | 0.9286 | 0.9286 |
| mrr@10 | 0.681 | 0.681 |
| ndcg@10 | 0.5414 | 0.5414 |
| p@10 | 0.4042 | 0.4042 |

Câu hỏi có khác biệt:

| Câu hỏi | Nhóm trước / sau | Hạng căn cứ trước | Hạng căn cứ sau |
|---|---|---|---|
| tiếp nhận hồ sơ đăng ký cư trú và thông báo kết quả | 280 / 280 | [1, 4, 37] | [1, 4, 35] |
