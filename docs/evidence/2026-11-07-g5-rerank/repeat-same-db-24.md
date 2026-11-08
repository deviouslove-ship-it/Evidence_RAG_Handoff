# Đối chiếu kết quả sau khi dựng lại dữ liệu

24 câu hỏi của bộ gốc, so theo (số hiệu, nhãn khoản) theo thứ tự.

- Kích thước nhóm ứng viên bằng nhau: 19/24
- 10 kết quả đầu giống hệt: 18/24
- 50 kết quả đầu giống hệt: 15/24
- Hạng của mọi căn cứ bắt buộc bằng nhau: 20/24

| Chỉ số | Lần chạy trước (DB đã xóa) | Sau khi dựng lại |
|---|---|---|
| recall@10 | 0.7619 | 0.7619 |
| recall@20 | 0.8095 | 0.8095 |
| recall@50 | 0.9048 | 0.881 |
| recall@all | 0.9286 | 0.9286 |
| mrr@10 | 0.6518 | 0.681 |
| ndcg@10 | 0.5338 | 0.5414 |
| p@10 | 0.4042 | 0.4042 |

Câu hỏi có khác biệt:

| Câu hỏi | Nhóm trước / sau | Hạng căn cứ trước | Hạng căn cứ sau |
|---|---|---|---|
| chà số máy số khung đăng ký xe trực tuyến | 142 / 139 | [2] | [2] |
| khiếu nại quyết định kỷ luật công nhân công an | 70 / 71 | [3, 44] | [1, 23] |
| thẩm quyền giải quyết khiếu nại lần đầu lần hai trong Công an nhân dân | 233 / 134 | [6, 26] | [5, 60] |
| thời hạn thụ lý khiếu nại 10 ngày làm việc | 36 / 37 | [7, 1] | [6, 1] |
| tiếp nhận hồ sơ đăng ký cư trú và thông báo kết quả | 280 / 280 | [1, 4, 35] | [1, 4, 37] |
| kiểm tra giấy tờ người điều khiển xe qua tài khoản định danh điện tử | 573 / 128 | [1, 3] | [1, 3] |
