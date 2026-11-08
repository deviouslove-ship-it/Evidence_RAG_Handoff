# Đối chiếu kết quả sau khi dựng lại dữ liệu

50 câu hỏi của bộ gốc, so theo (số hiệu, nhãn khoản) theo thứ tự.

- Kích thước nhóm ứng viên bằng nhau: 43/50
- 10 kết quả đầu giống hệt: 10/50
- 50 kết quả đầu giống hệt: 0/50
- Hạng của mọi căn cứ bắt buộc bằng nhau: 38/50

| Chỉ số | Lần chạy trước (DB đã xóa) | Sau khi dựng lại |
|---|---|---|
| recall@10 | 0.8649 | 0.8649 |
| recall@20 | 0.8919 | 0.8919 |
| recall@50 | 0.9324 | 0.9459 |
| recall@all | 0.9595 | 0.9595 |
| mrr@10 | 0.7902 | 0.7795 |
| ndcg@10 | 0.5937 | 0.589 |
| p@10 | 0.344 | 0.342 |

Câu hỏi có khác biệt:

| Câu hỏi | Nhóm trước / sau | Hạng căn cứ trước | Hạng căn cứ sau |
|---|---|---|---|
| chà số máy số khung đăng ký xe trực tuyến | 139 / 142 | [2] | [2] |
| khiếu nại quyết định kỷ luật công nhân công an | 71 / 70 | [1, 23] | [3, 45] |
| thẩm quyền giải quyết khiếu nại lần đầu lần hai trong Công an nhân dân | 134 / 233 | [5, 60] | [3, 26] |
| thời hạn thụ lý khiếu nại 10 ngày làm việc | 37 / 36 | [6, 1] | [7, 1] |
| đăng ký cư trú qua VNeID giấy tờ không ký số | 130 / 130 | [12, 4, 2] | [12, 3, 2] |
| tiếp nhận hồ sơ đăng ký cư trú và thông báo kết quả | 280 / 280 | [1, 4, 37] | [1, 4, 36] |
| kiểm tra giấy tờ người điều khiển xe qua tài khoản định danh điện tử | 128 / 573 | [1, 3] | [1, 3] |
| cảnh sát giao thông kiểm tra giấy phép lái xe trên VNeID | 732 / 732 | [16, 34] | [15, 33] |
| tuần tra kiểm soát kiểm tra giấy tờ đã tích hợp căn cước điện tử | 949 / 949 | [327, 1] | [151, 1] |
| tố cáo trực tiếp thì người tiếp nhận hướng dẫn viết đơn hoặc ghi lại n | 254 / 234 | [1] | [1] |
| Cảnh sát giao thông phải giải quyết tai nạn giao thông đường bộ trong  | 83 / 83 | [1] | [2] |
| hiệu lệnh dừng phương tiện giao thông của Cảnh sát giao thông bằng gậy | 46 / 46 | [3, 1, 2] | [1, 3, 5] |
| cảnh sát giao thông kiểm soát tại một điểm đứng nghiêm hướng về phía p | 335 / 335 | [3, 1, 2] | [2, 1, 3] |
| tín hiệu ưu tiên của xe tuần tra kiểm soát có được dùng làm hiệu lệnh  | 120 / 120 | [1, 4, 2] | [1, 3, 5] |
| công an nhân dân không được chia sẻ bình luận thông tin trái thuần pho | 532 / 507 | [2] | [1] |
