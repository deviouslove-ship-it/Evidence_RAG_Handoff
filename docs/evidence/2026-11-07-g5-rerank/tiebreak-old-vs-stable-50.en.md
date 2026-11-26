**Language / Ngôn ngữ:** [Tiếng Việt](tiebreak-old-vs-stable-50.md) · English

English counterpart of `docs/evidence/2026-11-07-g5-rerank/tiebreak-old-vs-stable-50.md`. The Vietnamese file is the original.

# Comparison of results after the data was rebuilt

50 questions from the original set, compared in order by (document number, Clause (Khoản) label).

- Candidate-pool sizes equal: 43/50
- Top 10 results identical: 10/50
- Top 50 results identical: 0/50
- Ranks of every required evidence (căn cứ) item equal: 38/50

| Metric | Previous run (DB deleted) | After rebuild |
|---|---|---|
| recall@10 | 0.8649 | 0.8649 |
| recall@20 | 0.8919 | 0.8919 |
| recall@50 | 0.9324 | 0.9459 |
| recall@all | 0.9595 | 0.9595 |
| mrr@10 | 0.7902 | 0.7795 |
| ndcg@10 | 0.5937 | 0.589 |
| p@10 | 0.344 | 0.342 |

Questions that differ:

| Question | Pool before / after | Evidence (căn cứ) rank before | Evidence (căn cứ) rank after |
|---|---|---|---|
| rubbing the engine number and chassis number for online vehicle registration (chà số máy số khung đăng ký xe trực tuyến) | 139 / 142 | [2] | [2] |
| complaint against a disciplinary decision concerning a public-security worker (khiếu nại quyết định kỷ luật công nhân công an) | 71 / 70 | [1, 23] | [3, 45] |
| authority to settle a first-instance and second-instance complaint in the People's Public Security (thẩm quyền giải quyết khiếu nại lần đầu lần hai trong Công an nhân dân) | 134 / 233 | [5, 60] | [3, 26] |
| time limit of 10 working days for accepting a complaint (thời hạn thụ lý khiếu nại 10 ngày làm việc) | 37 / 36 | [6, 1] | [7, 1] |
| residence registration via VNeID with documents that are not digitally signed (đăng ký cư trú qua VNeID giấy tờ không ký số) | 130 / 130 | [12, 4, 2] | [12, 3, 2] |
| receiving a residence-registration dossier and notifying the result (tiếp nhận hồ sơ đăng ký cư trú và thông báo kết quả) | 280 / 280 | [1, 4, 37] | [1, 4, 36] |
| checking a driver's documents through an electronic identification account (kiểm tra giấy tờ người điều khiển xe qua tài khoản định danh điện tử) | 128 / 573 | [1, 3] | [1, 3] |
| traffic police checking a driving licence on VNeID (cảnh sát giao thông kiểm tra giấy phép lái xe trên VNeID) | 732 / 732 | [16, 34] | [15, 33] |
| patrol and control checking documents already integrated with the electronic citizen identity (tuần tra kiểm soát kiểm tra giấy tờ đã tích hợp căn cước điện tử) | 949 / 949 | [327, 1] | [151, 1] |
| for an in-person denunciation, the receiving person guides writing the petition or records n (tố cáo trực tiếp thì người tiếp nhận hướng dẫn viết đơn hoặc ghi lại n) | 254 / 234 | [1] | [1] |
| Traffic police must settle a road traffic accident within  (Cảnh sát giao thông phải giải quyết tai nạn giao thông đường bộ trong ) | 83 / 83 | [1] | [2] |
| traffic-police stop signal for a vehicle given with a baton (hiệu lệnh dừng phương tiện giao thông của Cảnh sát giao thông bằng gậy) | 46 / 46 | [3, 1, 2] | [1, 3, 5] |
| traffic police controlling at one point, standing at attention facing p (cảnh sát giao thông kiểm soát tại một điểm đứng nghiêm hướng về phía p) | 335 / 335 | [3, 1, 2] | [2, 1, 3] |
| may the priority signal of a patrol-and-control vehicle be used as a command signal  (tín hiệu ưu tiên của xe tuần tra kiểm soát có được dùng làm hiệu lệnh ) | 120 / 120 | [1, 4, 2] | [1, 3, 5] |
| People's Public Security personnel must not share or comment on information contrary to thuần pho (công an nhân dân không được chia sẻ bình luận thông tin trái thuần pho) | 532 / 507 | [2] | [1] |
