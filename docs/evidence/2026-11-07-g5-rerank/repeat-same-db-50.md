# Đối chiếu kết quả sau khi dựng lại dữ liệu

50 câu hỏi của bộ gốc, so theo (số hiệu, nhãn khoản) theo thứ tự.

- Kích thước nhóm ứng viên bằng nhau: 39/50
- 10 kết quả đầu giống hệt: 41/50
- 50 kết quả đầu giống hệt: 33/50
- Hạng của mọi căn cứ bắt buộc bằng nhau: 49/50

| Chỉ số | Lần chạy trước (DB đã xóa) | Sau khi dựng lại |
|---|---|---|
| recall@10 | 0.8649 | 0.8649 |
| recall@20 | 0.8919 | 0.8919 |
| recall@50 | 0.9324 | 0.9324 |
| recall@all | 0.9595 | 0.9595 |
| mrr@10 | 0.7902 | 0.7842 |
| ndcg@10 | 0.5937 | 0.6084 |
| p@10 | 0.344 | 0.348 |

Câu hỏi có khác biệt:

| Câu hỏi | Nhóm trước / sau | Hạng căn cứ trước | Hạng căn cứ sau |
|---|---|---|---|
| đăng ký xe lần đầu trực tuyến toàn trình | 86 / 121 | [2] | [2] |
| cảnh sát giao thông kiểm tra giấy phép lái xe trên VNeID | 732 / 611 | [16, 34] | [16, 34] |
| tố cáo trực tiếp thì người tiếp nhận hướng dẫn viết đơn hoặc ghi lại n | 254 / 234 | [1] | [1] |
| Cảnh sát giao thông phải giải quyết tai nạn giao thông đường bộ trong  | 83 / 81 | [1] | [1] |
| sử dụng còi loa trong chỉ huy điều khiển giao thông đường bộ | 65 / 101 | [1] | [1] |
| hiệu lệnh dừng phương tiện giao thông của Cảnh sát giao thông bằng gậy | 46 / 47 | [3, 1, 2] | [3, 1, 2] |
| cảnh sát giao thông kiểm soát tại một điểm đứng nghiêm hướng về phía p | 335 / 430 | [3, 1, 2] | [3, 1, 2] |
| quy tắc sử dụng phương tiện điện tử của cán bộ chiến sĩ Công an nhân d | 236 / 238 | [1] | [1] |
| thông báo công khai tuyển sinh tại hội nghị cán bộ chủ chốt hoặc bằng  | 113 / 116 | [2] | [5] |
| niêm phong mẫu nước thải bằng tem có chữ ký của cán bộ thu mẫu và đại  | 32 / 37 | [1] | [1] |
| chiến sĩ phát hiện vi phạm giao thông đường sắt phải đình chỉ hành vi  | 529 / 336 | [2] | [2] |
