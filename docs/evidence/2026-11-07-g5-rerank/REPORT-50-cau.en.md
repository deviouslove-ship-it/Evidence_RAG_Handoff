**Language / Ngôn ngữ:** [Tiếng Việt](REPORT-50-cau.md) · English

English counterpart of `docs/evidence/2026-11-07-g5-rerank/REPORT-50-cau.md`. The Vietnamese file is the original.

# G5: expansion to 50 questions, pure RRF as the default, rebuild and backup of the data for 100 administrative documents (văn bản)

Run date: 2026-11-07. Supplement to `REPORT.md` (comparison of three ranking options on 24 questions). Source figures are in the same directory.
No business acceptance: the required evidence (căn cứ) list was drafted by the agent from the wording of the administrative documents (văn bản), and has not been confirmed by a specialist officer.

## 1. Decisions already applied

| Owner's decision | How it was done | Check |
|---|---|---|
| Keep the semantic-channel threshold at 0,8; 0,6 is for trials only and can be changed through configuration | No code change. `EVIDENCE_SEMANTIC_RELATIVE_THRESHOLD` (default 0,8, valid in [0; 1]) | The runs below use 0,8 |
| Turn off automatic LLM rerank; pure RRF is the default of "Comprehensive search"; keep both rerank options available as choices | The API `rerank` accepts `true`, `false`, or absent; absent = the server value `EVIDENCE_RERANK_DEFAULT` (default `false`). The default of the internal record also changed to `false`. OpenAPI updated | A call that does not mention `rerank`: `reranked=false`, 0/50 questions reranked. `rerank:true` with the LLM: 40 results, 38,1 seconds. `rerank:true` with Qwen3-Reranker-0.6B: 40 results, 25,4 seconds |

The rerank backend is still chosen with `EVIDENCE_RERANK_BACKEND` (`llm` or `cross_encoder`). The reranker benchmark was not run again, as requested.

## 2. The 50-question set

`evaluation/coverage/topics.json`: 17 topics, 50 questions, 74 pairs (question, required evidence (căn cứ)). The original 24 questions are kept; 26 new questions
(9 topics, `"set": "v2"`) were drafted from the wording of the 100 administrative documents (văn bản) **before any search was run on them**:

| Topic | Questions | Required evidence (căn cứ) |
|---|---|---|
| to_cao_cand | 3 | 10/2014/TT-BCA Article (Điều) 9 |
| the_cccd_thoi_han_xu_ly | 3 | 60/2021/TT-BCA Article (Điều) 11 |
| tai_nan_giao_thong_thoi_han | 3 | 63/2020/TT-BCA Article (Điều) 18 |
| am_hieu_coi_dieu_khien_giao_thong | 3 | 69/2024/TT-BCA Article (Điều) 15 |
| hieu_lenh_dung_phuong_tien | 3 | Article (Điều) 17 of 32/2023 and of 65/2020, Article (Điều) 13 of 73/2024 (three Circulars (Thông tư) that have an Article (Điều) with the same name) |
| ung_xu_dien_thoai_mang | 3 | 27/2017/TT-BCA Article (Điều) 13 |
| cong_khai_tuyen_sinh | 3 | 44/2021/TT-BCA Article (Điều) 5 |
| niem_phong_mau_nuoc_thai | 3 | 71/2023/TT-BCA Article (Điều) 14 |
| xu_ly_vphc_duong_sat | 2 | 26/2010/TT-BCA Article (Điều) 8 |

Seven draft questions were longer than 20 words, so the API rejected them (`TOO_MANY_TERMS`, an existing limit of the system) before returning any result;
I shortened those seven questions, did not change the evidence (căn cứ), and had not looked at their results. Limitation: the new questions are written close to the wording of the provisions, so they are easier than a natural question;
do not compare scores of the new set directly with the original set.

## 3. Rebuilding the data once

- File set: rebuilt with `select_subset.py`; the list and the SHA-256 are **identical** to the previous `subset-manifest.json` (100 files: 14 files by evidence (căn cứ), 86 files by SHA-256 of the file name).
- Imported 100 files, review (trial mode): 100/100 reviewed, 92,3 seconds. Effectivity (hiệu lực) extraction ran afterwards.
- Embedding `qwen3-embedding:0.6b`: 7.230/7.230 clauses, 0 errors, 42 minutes 24 seconds (about 2,8 clauses/second), index ready, 1024 dimensions.
- Stored in a lasting place (`data\rerank-eval`, DB `evidence_rerank_eval`, `backups\rerank-eval`), no longer in a temporary directory. Details: `DATA-INVENTORY.md`.

## 4. Backup immediately after creation, and the restore check

`pg_dump -Fc` ran 6 seconds after the index was ready, before any measurement: 37,0 MB, SHA-256 `915b89b1…ab66c`. The catalog (`.toc.txt`, 316 entries) contains
`node_embeddings` data, the HNSW index, and the `vector` extension. Restore into DB `evidence_rerank_eval_restorecheck`: 6 seconds, no errors.
`scripts/verify_db_restore.py` (result `db-restore-verification.json`): **passed**.

| Check | Result |
|---|---|
| Row counts of 51 tables (36.565 rows) | equal for each table |
| Checksum of administrative-document (văn bản) clause text; checksum of 7.230 vectors | equal |
| 98 indexes | same names, all valid; HNSW is present and the query plan uses it |
| 5 sample clauses, 5 nearest neighbors | identical in the two databases |
| 24 questions run on the restored copy (API port 8766) against the source database in the same session | candidate pools equal on 24/24, top 10 results identical on 23/24, evidence (căn cứ) ranks equal on 23/24, Recall and MRR equal |

The document store was compressed separately (59,2 MB). The source database, the restored copy, the document store, and the backup are all retained.

## 5. Rerun of the old 24 questions on the rebuilt data

| Metric | Previous run (DB deleted) | Rebuild, run 1 | Rebuild, run 2 (same DB, a few minutes later) |
|---|---|---|---|
| Recall@10 / @20 / @50 | 0,762 / 0,810 / 0,905 | 0,762 / 0,810 / 0,905 | 0,762 / 0,810 / 0,881 |
| Recall@entire pool | 0,929 | 0,929 | 0,929 |
| MRR@10 | 0,674 | 0,652 | 0,681 |
| NDCG@10 | 0,554 | 0,534 | 0,541 |
| P@10 | 0,408 | 0,404 | 0,404 |
| Candidate pool equal to the previous run | | 20/24 | 19/24 (compared with run 1) |
| Top 10 results identical to the previous run | | 5/24 | 18/24 (compared with run 1) |
| Rank of every evidence (căn cứ) item equal to the previous run | | 17/24 | 20/24 (compared with run 1) |

**The comparison passes on Recall; the detailed order is not reproduced at every position.** Recall@10, @20, and Recall@entire pool are identical to the previous run; MRR and NDCG differ by 0,02,
on the same scale as the difference between two consecutive runs on the same database (MRR 0,03; NDCG 0,01). The three missing evidence (căn cứ) items (58/2026 Article (Điều) 11, 96/2026 Article (Điều) 3, 110/2021 Article (Điều) 2) are still missing.
Causes of the difference (the causes have not been separated one by one):

- On a tie, the code sorts by `node_id` (in `_rrf`, the exact channel, and the relation channel; fixed in `REPORT-tiebreak.md`); a new node has a new UUID, so the top 10 results change places (5/24 questions identical), while the restored copy keeps the same ids and therefore matches 23/24.
- A newly built HNSW index gives a slightly different nearest-neighbor approximation.
- The `expand` step (qwen3:1.7b) produces different expansion clusters from call to call on some questions, which changes the candidate pool of the concept channel (same database, two consecutive runs: the pools differ on 5/24 questions between run 1 and run 2; across 50 consecutive questions it is 11/50).

## 6. Pure RRF results, 50 questions (`bench-rrf-50.json`, `rrf-50-summary.md`)

| Set | Questions | Pairs | R@10 | R@20 | R@50 | R@entire pool | MRR@10 | NDCG@10 | P@10 |
|---|---|---|---|---|---|---|---|---|---|
| Original 24 questions | 24 | 42 | 0,762 | 0,809 | 0,881 | 0,929 | 0,681 | 0,541 | 0,404 |
| 26 added questions | 26 | 32 | 1,000 | 1,000 | 1,000 | 1,000 | 0,891 | 0,642 | 0,288 |
| **All 50 questions** | 50 | 74 | **0,865** | **0,892** | **0,932** | **0,960** | **0,790** | **0,594** | 0,344 |

- Response time: median 2,2 seconds, mean 2,4 seconds, maximum 10,5 seconds. RAM: API peak 97 MB; Ollama peak 3,6 GB. 0/50 questions were reranked.
- The repeat run immediately afterwards (`bench-rrf-50-repeat.json`): Recall identical, MRR 0,784, NDCG 0,608, P@10 0,348; evidence (căn cứ) ranks equal on 49/50 questions; candidate pools equal on 39/50 questions. Run-to-run noise is about ±0,01 to 0,02 for MRR and NDCG.
- All 32 pairs of the added set are inside the top 10 results. This is easier than the original set because the questions are written close to the wording of the provisions; at the same time P@10 is lower (0,288). Cause not yet checked: it may be because each new topic has only one required Article (Điều), while other clauses on the same topic (another article in the same Circular (Thông tư), a similar Circular (Thông tư)) are not counted as relevant.
- Evidence (căn cứ) absent from the candidate pool, the same as last time because the threshold stays at 0,8: 58/2026 Article (Điều) 11 (question "rules of inmate detention facilities… (nội quy cơ sở giam giữ phạm nhân…)"), 96/2026 Article (Điều) 3 (question "items prohibited from being brought into temporary holding… (đồ vật cấm đưa vào buồng tạm giữ…)"), 110/2021 Article (Điều) 2 (question "Does Circular (Thông tư) 29/2016/TT-BCA still have effectivity (hiệu lực) (Thông tư 29/2016/TT-BCA còn hiệu lực không)"). Seven other pairs are in the pool but outside the top 10, at ranks 12, 16, 23, 34, 37, 60, and 327 (topics: complaints, residence, identity-document checks). Rank 327 in a pool of 949 is 32/2023 Article (Điều) 12 for the question "patrol and control checking documents already integrated with the electronic citizen identity (tuần tra kiểm soát kiểm tra giấy tờ đã tích hợp căn cước điện tử)", found only by the concept channel.

## 7. Regression

`scripts/verify.ps1 -ProgramsRoot E:\Programs` passed 12/12 (`verify-50/`): backend 218 passed, frontend 74 passed, ruff, mypy, 13 migration pairs, OpenAPI (updated), hard-coded-path check.
No new test was added. Files changed: `config.py`, `api/v1/comprehensive.py`, `storage/comprehensive.py`, OpenAPI; new or changed tools in `evaluation/coverage` and `scripts/verify_db_restore.py`.

## 8. Limitations

- Required evidence (căn cứ) has not been confirmed; the added set is easier than the original set.
- Results are not fixed bit for bit: each call to `expand` can return a different expansion cluster. Compare with Recall and a swing of about ±0,02, not position by position.
- The figures in this report were measured while ties were still ordered by UUID. From 2026-11-08 the tie-break key was changed to a stable key by administrative-document (văn bản) number and clause position (`REPORT-tiebreak.md`); the new measurements for the 50 questions are there.
- Not yet measured on the target Windows machine, and a GPU has not been tried.
