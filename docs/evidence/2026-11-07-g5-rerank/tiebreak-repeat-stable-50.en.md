**Language / Ngôn ngữ:** [Tiếng Việt](tiebreak-repeat-stable-50.md) · English

English counterpart of `docs/evidence/2026-11-07-g5-rerank/tiebreak-repeat-stable-50.md`. The Vietnamese file is the original.

# Comparison of results after the data was rebuilt

50 questions from the original set, compared in order by (document number, Clause (Khoản) label).

- Candidate-pool sizes equal: 38/50
- Top 10 results identical: 39/50
- Top 50 results identical: 31/50
- Ranks of every required evidence (căn cứ) item equal: 47/50

| Metric | Previous run (DB deleted) | After rebuild |
|---|---|---|
| recall@10 | 0.8649 | 0.8649 |
| recall@20 | 0.8919 | 0.8919 |
| recall@50 | 0.9459 | 0.9324 |
| recall@all | 0.9595 | 0.9595 |
| mrr@10 | 0.7795 | 0.7852 |
| ndcg@10 | 0.589 | 0.6088 |
| p@10 | 0.342 | 0.346 |

Questions that differ:

| Question | Pool before / after | Evidence (căn cứ) rank before | Evidence (căn cứ) rank after |
|---|---|---|---|
| rubbing the engine number and chassis number for online vehicle registration (chà số máy số khung đăng ký xe trực tuyến) | 142 / 139 | [2] | [2] |
| complaint against a disciplinary decision concerning a public-security worker (khiếu nại quyết định kỷ luật công nhân công an) | 70 / 71 | [3, 45] | [1, 23] |
| authority to settle a first-instance and second-instance complaint in the People's Public Security (thẩm quyền giải quyết khiếu nại lần đầu lần hai trong Công an nhân dân) | 233 / 134 | [3, 26] | [5, 63] |
| checking a driver's documents through an electronic identification account (kiểm tra giấy tờ người điều khiển xe qua tài khoản định danh điện tử) | 573 / 128 | [1, 3] | [1, 3] |
| Traffic police must settle a road traffic accident within  (Cảnh sát giao thông phải giải quyết tai nạn giao thông đường bộ trong ) | 83 / 81 | [2] | [2] |
| using a whistle and loudspeaker when directing and controlling road traffic (sử dụng còi loa trong chỉ huy điều khiển giao thông đường bộ) | 65 / 101 | [1] | [1] |
| traffic-police stop signal for a vehicle given with a baton (hiệu lệnh dừng phương tiện giao thông của Cảnh sát giao thông bằng gậy) | 46 / 47 | [1, 3, 5] | [1, 3, 5] |
| traffic police controlling at one point, standing at attention facing p (cảnh sát giao thông kiểm soát tại một điểm đứng nghiêm hướng về phía p) | 335 / 430 | [2, 1, 3] | [2, 1, 3] |
| rules for using electronic devices by officers and soldiers of Công an nhân d (quy tắc sử dụng phương tiện điện tử của cán bộ chiến sĩ Công an nhân d) | 236 / 238 | [1] | [1] |
| public notice of enrollment at a key-cadre conference or by  (thông báo công khai tuyển sinh tại hội nghị cán bộ chủ chốt hoặc bằng ) | 113 / 116 | [2] | [4] |
| sealing a wastewater sample with a stamp bearing the signature of the sampling officer and đại  (niêm phong mẫu nước thải bằng tem có chữ ký của cán bộ thu mẫu và đại ) | 32 / 37 | [1] | [1] |
| a soldier who detects a railway traffic violation must stop the act  (chiến sĩ phát hiện vi phạm giao thông đường sắt phải đình chỉ hành vi ) | 529 / 336 | [2] | [2] |
