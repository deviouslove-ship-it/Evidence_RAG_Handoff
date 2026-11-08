# Đối chiếu kết quả sau khi dựng lại dữ liệu

50 câu hỏi của bộ gốc, so theo (số hiệu, nhãn khoản) theo thứ tự.

- Kích thước nhóm ứng viên bằng nhau: 38/50
- 10 kết quả đầu giống hệt: 39/50
- 50 kết quả đầu giống hệt: 31/50
- Hạng của mọi căn cứ bắt buộc bằng nhau: 47/50

| Chỉ số | Lần chạy trước (DB đã xóa) | Sau khi dựng lại |
|---|---|---|
| recall@10 | 0.8649 | 0.8649 |
| recall@20 | 0.8919 | 0.8919 |
| recall@50 | 0.9459 | 0.9324 |
| recall@all | 0.9595 | 0.9595 |
| mrr@10 | 0.7795 | 0.7852 |
| ndcg@10 | 0.589 | 0.6088 |
| p@10 | 0.342 | 0.346 |

Câu hỏi có khác biệt:

| Câu hỏi | Nhóm trước / sau | Hạng căn cứ trước | Hạng căn cứ sau |
|---|---|---|---|
| chà số máy số khung đăng ký xe trực tuyến | 142 / 139 | [2] | [2] |
| khiếu nại quyết định kỷ luật công nhân công an | 70 / 71 | [3, 45] | [1, 23] |
| thẩm quyền giải quyết khiếu nại lần đầu lần hai trong Công an nhân dân | 233 / 134 | [3, 26] | [5, 63] |
| kiểm tra giấy tờ người điều khiển xe qua tài khoản định danh điện tử | 573 / 128 | [1, 3] | [1, 3] |
| Cảnh sát giao thông phải giải quyết tai nạn giao thông đường bộ trong  | 83 / 81 | [2] | [2] |
| sử dụng còi loa trong chỉ huy điều khiển giao thông đường bộ | 65 / 101 | [1] | [1] |
| hiệu lệnh dừng phương tiện giao thông của Cảnh sát giao thông bằng gậy | 46 / 47 | [1, 3, 5] | [1, 3, 5] |
| cảnh sát giao thông kiểm soát tại một điểm đứng nghiêm hướng về phía p | 335 / 430 | [2, 1, 3] | [2, 1, 3] |
| quy tắc sử dụng phương tiện điện tử của cán bộ chiến sĩ Công an nhân d | 236 / 238 | [1] | [1] |
| thông báo công khai tuyển sinh tại hội nghị cán bộ chủ chốt hoặc bằng  | 113 / 116 | [2] | [4] |
| niêm phong mẫu nước thải bằng tem có chữ ký của cán bộ thu mẫu và đại  | 32 / 37 | [1] | [1] |
| chiến sĩ phát hiện vi phạm giao thông đường sắt phải đình chỉ hành vi  | 529 / 336 | [2] | [2] |
