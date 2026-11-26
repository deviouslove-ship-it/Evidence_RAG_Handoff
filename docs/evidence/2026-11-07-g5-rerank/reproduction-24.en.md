**Language / Ngôn ngữ:** [Tiếng Việt](reproduction-24.md) · English

English counterpart of `docs/evidence/2026-11-07-g5-rerank/reproduction-24.md`. The Vietnamese file is the original.

# Comparison of results after the data was rebuilt

24 questions from the original set, compared in order by (document number, Clause (Khoản) label).

- Candidate-pool sizes equal: 20/24
- Top 10 results identical: 5/24
- Top 50 results identical: 0/24
- Ranks of every required evidence (căn cứ) item equal: 17/24

| Metric | Previous run (DB deleted) | After rebuild |
|---|---|---|
| recall@10 | 0.7619 | 0.7619 |
| recall@20 | 0.8095 | 0.8095 |
| recall@50 | 0.9048 | 0.9048 |
| recall@all | 0.9286 | 0.9286 |
| mrr@10 | 0.674 | 0.6518 |
| ndcg@10 | 0.5536 | 0.5338 |
| p@10 | 0.4083 | 0.4042 |

Questions that differ:

| Question | Pool before / after | Evidence (căn cứ) rank before | Evidence (căn cứ) rank after |
|---|---|---|---|
| fingerprint image ISO/IEC 19794-4 at a density of 500 points (ảnh vân tay ISO/IEC 19794-4 mật độ 500 điểm) | 956 / 960 | [1] | [1] |
| complaint against a disciplinary decision concerning a public-security worker (khiếu nại quyết định kỷ luật công nhân công an) | 70 / 70 | [3, 45] | [3, 44] |
| authority to settle a first-instance and second-instance complaint in the People's Public Security (thẩm quyền giải quyết khiếu nại lần đầu lần hai trong Công an nhân dân) | 233 / 233 | [5, 25] | [6, 26] |
| residence registration via VNeID with documents that are not digitally signed (đăng ký cư trú qua VNeID giấy tờ không ký số) | 130 / 130 | [12, 2, 3] | [12, 4, 2] |
| receiving a residence-registration dossier and notifying the result (tiếp nhận hồ sơ đăng ký cư trú và thông báo kết quả) | 280 / 280 | [1, 2, 35] | [1, 4, 35] |
| items prohibited from being brought into temporary holding and temporary detention cells (đồ vật cấm đưa vào buồng tạm giữ tạm giam) | 352 / 352 | [1, None] | [2, None] |
| checking a driver's documents through an electronic identification account (kiểm tra giấy tờ người điều khiển xe qua tài khoản định danh điện tử) | 579 / 573 | [1, 3] | [1, 3] |
| traffic police checking a driving licence on VNeID (cảnh sát giao thông kiểm tra giấy phép lái xe trên VNeID) | 737 / 732 | [13, 31] | [16, 34] |
| patrol and control checking documents already integrated with the electronic citizen identity (tuần tra kiểm soát kiểm tra giấy tờ đã tích hợp căn cước điện tử) | 985 / 949 | [315, 1] | [327, 1] |
