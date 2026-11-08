# Đối chiếu kết quả sau khi dựng lại dữ liệu

24 câu hỏi của bộ gốc, so theo (số hiệu, nhãn khoản) theo thứ tự.

- Kích thước nhóm ứng viên bằng nhau: 20/24
- 10 kết quả đầu giống hệt: 5/24
- 50 kết quả đầu giống hệt: 0/24
- Hạng của mọi căn cứ bắt buộc bằng nhau: 17/24

| Chỉ số | Lần chạy trước (DB đã xóa) | Sau khi dựng lại |
|---|---|---|
| recall@10 | 0.7619 | 0.7619 |
| recall@20 | 0.8095 | 0.8095 |
| recall@50 | 0.9048 | 0.9048 |
| recall@all | 0.9286 | 0.9286 |
| mrr@10 | 0.674 | 0.6518 |
| ndcg@10 | 0.5536 | 0.5338 |
| p@10 | 0.4083 | 0.4042 |

Câu hỏi có khác biệt:

| Câu hỏi | Nhóm trước / sau | Hạng căn cứ trước | Hạng căn cứ sau |
|---|---|---|---|
| ảnh vân tay ISO/IEC 19794-4 mật độ 500 điểm | 956 / 960 | [1] | [1] |
| khiếu nại quyết định kỷ luật công nhân công an | 70 / 70 | [3, 45] | [3, 44] |
| thẩm quyền giải quyết khiếu nại lần đầu lần hai trong Công an nhân dân | 233 / 233 | [5, 25] | [6, 26] |
| đăng ký cư trú qua VNeID giấy tờ không ký số | 130 / 130 | [12, 2, 3] | [12, 4, 2] |
| tiếp nhận hồ sơ đăng ký cư trú và thông báo kết quả | 280 / 280 | [1, 2, 35] | [1, 4, 35] |
| đồ vật cấm đưa vào buồng tạm giữ tạm giam | 352 / 352 | [1, None] | [2, None] |
| kiểm tra giấy tờ người điều khiển xe qua tài khoản định danh điện tử | 579 / 573 | [1, 3] | [1, 3] |
| cảnh sát giao thông kiểm tra giấy phép lái xe trên VNeID | 737 / 732 | [13, 31] | [16, 34] |
| tuần tra kiểm soát kiểm tra giấy tờ đã tích hợp căn cước điện tử | 985 / 949 | [315, 1] | [327, 1] |
