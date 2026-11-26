**Language / Ngôn ngữ:** [Tiếng Việt](repeat-same-db-50.md) · English

English counterpart of `docs/evidence/2026-11-07-g5-rerank/repeat-same-db-50.md`. The Vietnamese file is the original.

# Comparison of results after the data was rebuilt

50 questions from the original set, compared in order by (document number, Clause (Khoản) label).

- Candidate-pool sizes equal: 39/50
- Top 10 results identical: 41/50
- Top 50 results identical: 33/50
- Ranks of every required evidence (căn cứ) item equal: 49/50

| Metric | Previous run (DB deleted) | After rebuild |
|---|---|---|
| recall@10 | 0.8649 | 0.8649 |
| recall@20 | 0.8919 | 0.8919 |
| recall@50 | 0.9324 | 0.9324 |
| recall@all | 0.9595 | 0.9595 |
| mrr@10 | 0.7902 | 0.7842 |
| ndcg@10 | 0.5937 | 0.6084 |
| p@10 | 0.344 | 0.348 |

Questions that differ:

| Question | Pool before / after | Evidence (căn cứ) rank before | Evidence (căn cứ) rank after |
|---|---|---|---|
| fully online first-time vehicle registration (đăng ký xe lần đầu trực tuyến toàn trình) | 86 / 121 | [2] | [2] |
| traffic police checking a driving licence on VNeID (cảnh sát giao thông kiểm tra giấy phép lái xe trên VNeID) | 732 / 611 | [16, 34] | [16, 34] |
| for an in-person denunciation, the receiving person guides writing the petition or records n (tố cáo trực tiếp thì người tiếp nhận hướng dẫn viết đơn hoặc ghi lại n) | 254 / 234 | [1] | [1] |
| Traffic police must settle a road traffic accident within  (Cảnh sát giao thông phải giải quyết tai nạn giao thông đường bộ trong ) | 83 / 81 | [1] | [1] |
| using a whistle and loudspeaker when directing and controlling road traffic (sử dụng còi loa trong chỉ huy điều khiển giao thông đường bộ) | 65 / 101 | [1] | [1] |
| traffic-police stop signal for a vehicle given with a baton (hiệu lệnh dừng phương tiện giao thông của Cảnh sát giao thông bằng gậy) | 46 / 47 | [3, 1, 2] | [3, 1, 2] |
| traffic police controlling at one point, standing at attention facing p (cảnh sát giao thông kiểm soát tại một điểm đứng nghiêm hướng về phía p) | 335 / 430 | [3, 1, 2] | [3, 1, 2] |
| rules for using electronic devices by officers and soldiers of Công an nhân d (quy tắc sử dụng phương tiện điện tử của cán bộ chiến sĩ Công an nhân d) | 236 / 238 | [1] | [1] |
| public notice of enrollment at a key-cadre conference or by  (thông báo công khai tuyển sinh tại hội nghị cán bộ chủ chốt hoặc bằng ) | 113 / 116 | [2] | [5] |
| sealing a wastewater sample with a stamp bearing the signature of the sampling officer and đại  (niêm phong mẫu nước thải bằng tem có chữ ký của cán bộ thu mẫu và đại ) | 32 / 37 | [1] | [1] |
| a soldier who detects a railway traffic violation must stop the act  (chiến sĩ phát hiện vi phạm giao thông đường sắt phải đình chỉ hành vi ) | 529 / 336 | [2] | [2] |
