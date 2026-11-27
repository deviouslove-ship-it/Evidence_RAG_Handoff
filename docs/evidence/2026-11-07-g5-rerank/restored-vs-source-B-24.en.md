**Language / Ngôn ngữ:** [Tiếng Việt](restored-vs-source-B-24.md) · English

English counterpart of `docs/evidence/2026-11-07-g5-rerank/restored-vs-source-B-24.md`. The Vietnamese file is the original.

# Comparison of results after the data was rebuilt

24 questions from the original set, compared in order by (document number, Clause (Khoản) label).

- Candidate-pool sizes equal: 24/24
- Top 10 results identical: 23/24
- Top 50 results identical: 18/24
- Ranks of every required evidence (căn cứ) item equal: 23/24

| Metric | Previous run (DB deleted) | After rebuild |
|---|---|---|
| recall@10 | 0.7619 | 0.7619 |
| recall@20 | 0.8095 | 0.8095 |
| recall@50 | 0.881 | 0.881 |
| recall@all | 0.9286 | 0.9286 |
| mrr@10 | 0.681 | 0.681 |
| ndcg@10 | 0.5414 | 0.5414 |
| p@10 | 0.4042 | 0.4042 |

Questions that differ:

| Question | Pool before / after | Evidence (căn cứ) rank before | Evidence (căn cứ) rank after |
|---|---|---|---|
| receiving a residence-registration dossier and notifying the result (tiếp nhận hồ sơ đăng ký cư trú và thông báo kết quả) | 280 / 280 | [1, 4, 37] | [1, 4, 35] |
