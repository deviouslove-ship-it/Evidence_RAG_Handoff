**Language / Ngôn ngữ:** [Tiếng Việt](restored-vs-source-A-24.md) · English

English counterpart of `docs/evidence/2026-11-07-g5-rerank/restored-vs-source-A-24.md`. The Vietnamese file is the original.

# Comparison of results after the data was rebuilt

24 questions from the original set, compared in order by (document number, Clause (Khoản) label).

- Candidate-pool sizes equal: 19/24
- Top 10 results identical: 18/24
- Top 50 results identical: 16/24
- Ranks of every required evidence (căn cứ) item equal: 21/24

| Metric | Previous run (DB deleted) | After rebuild |
|---|---|---|
| recall@10 | 0.7619 | 0.7619 |
| recall@20 | 0.8095 | 0.8095 |
| recall@50 | 0.9048 | 0.881 |
| recall@all | 0.9286 | 0.9286 |
| mrr@10 | 0.6518 | 0.681 |
| ndcg@10 | 0.5338 | 0.5414 |
| p@10 | 0.4042 | 0.4042 |

Questions that differ:

| Question | Pool before / after | Evidence (căn cứ) rank before | Evidence (căn cứ) rank after |
|---|---|---|---|
| rubbing the engine number and chassis number for online vehicle registration (chà số máy số khung đăng ký xe trực tuyến) | 142 / 139 | [2] | [2] |
| complaint against a disciplinary decision concerning a public-security worker (khiếu nại quyết định kỷ luật công nhân công an) | 70 / 71 | [3, 44] | [1, 23] |
| authority to settle a first-instance and second-instance complaint in the People's Public Security (thẩm quyền giải quyết khiếu nại lần đầu lần hai trong Công an nhân dân) | 233 / 134 | [6, 26] | [5, 60] |
| time limit of 10 working days for accepting a complaint (thời hạn thụ lý khiếu nại 10 ngày làm việc) | 36 / 37 | [7, 1] | [6, 1] |
| checking a driver's documents through an electronic identification account (kiểm tra giấy tờ người điều khiển xe qua tài khoản định danh điện tử) | 573 / 128 | [1, 3] | [1, 3] |
