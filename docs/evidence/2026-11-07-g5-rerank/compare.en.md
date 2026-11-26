**Language / Ngôn ngữ:** [Tiếng Việt](compare.md) · English

English counterpart of `docs/evidence/2026-11-07-g5-rerank/compare.md`. The Vietnamese file is the original.

# Comparison of three ranking options (G5)

Questions: 24, pairs (question, required evidence (căn cứ)): 42.

| Metric | Pure RRF | RRF + current LLM rerank (qwen3:1.7b) | RRF + Qwen3-Reranker-0.6B |
|---|---|---|---|
| recall@10 | 0.762 | 0.691 | 0.809 |
| recall@20 | 0.809 | 0.833 | 0.881 |
| recall@50 | 0.905 | 0.881 | 0.905 |
| recall@all | 0.929 | 0.929 | 0.929 |
| mrr@10 | 0.674 | 0.729 | 0.713 |
| ndcg@10 | 0.554 | 0.549 | 0.536 |
| seconds_median | 2.476 | 47.657 | 32.292 |
| seconds_mean | 2.913 | 46.093 | 31.140 |
| seconds_p95 | 4.060 | 56.579 | 36.380 |
| rerank_ms_median | 0.000 | 45463.600 | 29986.200 |
| queries_reranked | 0 | 24 | 24 |

Memory (MB, measured during the run of the 24 questions):

- Pure RRF: api peak 91.9 / median 89.5, ollama peak 3269.6 / median 3168.7
- RRF + current LLM rerank (qwen3:1.7b): api peak 95.6 / median 90.4, ollama peak 11229.8 / median 11055.4
- RRF + Qwen3-Reranker-0.6B: api peak 93.3 / median 90.2, reranker peak 4846.6 / median 3847.9, ollama peak 3270.7 / median 3169.9

Candidate pools the same across the three options: 21/24 questions.

Compared with pure RRF (MRR@10 per question): RRF + current LLM rerank (qwen3:1.7b): better 9, worse 4, equal 11; RRF + Qwen3-Reranker-0.6B: better 8, worse 5, equal 11

## Two evidence (căn cứ) items on detention rules

| Question | Evidence (căn cứ) | RRF | LLM | Qwen3 | Diagnosis |
|---|---|---|---|---|---|
| rules of inmate detention facilities and rules of temporary detention camps (nội quy cơ sở giam giữ phạm nhân và nội quy trại tạm giam) | 58/2026/TT-BCA Article (Điều) 11 | - | - | - | candidate-retrieval error (not in the candidate pool of any channel) |
| rules of inmate detention facilities and rules of temporary detention camps (nội quy cơ sở giam giữ phạm nhân và nội quy trại tạm giam) | 96/2026/TT-BCA Article (Điều) 3 | 7 | 6 | 6 | found in the top 10 by RRF |
| items prohibited from being brought into temporary holding and temporary detention cells (đồ vật cấm đưa vào buồng tạm giữ tạm giam) | 58/2026/TT-BCA Article (Điều) 11 | 1 | 1 | 1 | found in the top 10 by RRF |
| items prohibited from being brought into temporary holding and temporary detention cells (đồ vật cấm đưa vào buồng tạm giữ tạm giam) | 96/2026/TT-BCA Article (Điều) 3 | - | - | - | candidate-retrieval error (not in the candidate pool of any channel) |
| Circular (Thông tư) on detention-facility rules with effectivity (hiệu lực) on 2026-07-01 (thông tư nội quy cơ sở giam giữ hiệu lực 01/7/2026) | 58/2026/TT-BCA Article (Điều) 11 | 6 | 7 | 7 | found in the top 10 by RRF |
| Circular (Thông tư) on detention-facility rules with effectivity (hiệu lực) on 2026-07-01 (thông tư nội quy cơ sở giam giữ hiệu lực 01/7/2026) | 96/2026/TT-BCA Article (Điều) 3 | 2 | 3 | 2 | found in the top 10 by RRF |

How well the rerank score separates relevant evidence (căn cứ) from the rest of the head of the list (mean AUC per question, 0,5 = chance; tied scores fall back to RRF order):

- RRF + current LLM rerank (qwen3:1.7b): AUC 0.677 over 23 questions; share of results with a tied score 0.992; number of distinct score levels (median) 4.0
- RRF + Qwen3-Reranker-0.6B: AUC 0.801 over 23 questions; share of results with a tied score 0.007; number of distinct score levels (median) 40.0

## Only the 21 questions whose candidate pool is identical across all three options

| Metric | Pure RRF | RRF + current LLM rerank (qwen3:1.7b) | RRF + Qwen3-Reranker-0.6B |
|---|---|---|---|
| recall@10 | 0.784 | 0.703 | 0.811 |
| recall@20 | 0.838 | 0.865 | 0.892 |
| recall@50 | 0.919 | 0.919 | 0.919 |
| mrr@10 | 0.689 | 0.714 | 0.708 |
| ndcg@10 | 0.540 | 0.524 | 0.512 |
| p@10 | 0.409 | 0.362 | 0.391 |

Mean difference versus pure RRF (95% bootstrap confidence interval, 10.000 resamples):

- all_queries / RRF + current LLM rerank (qwen3:1.7b): mrr@10 +0.055 [-0.089; +0.188]; ndcg@10 -0.005 [-0.108; +0.091]
- all_queries / RRF + Qwen3-Reranker-0.6B: mrr@10 +0.039 [-0.129; +0.209]; ndcg@10 -0.018 [-0.089; +0.053]
- matched_pool / RRF + current LLM rerank (qwen3:1.7b): mrr@10 +0.025 [-0.134; +0.168]; ndcg@10 -0.016 [-0.134; +0.090]
- matched_pool / RRF + Qwen3-Reranker-0.6B: mrr@10 +0.019 [-0.164; +0.207]; ndcg@10 -0.028 [-0.104; +0.049]

## Additional experiment: A. Similarity threshold 0,6, pure RRF, all 24 questions

Questions: 24; times reranked: 0; median rerank time (ms): 0.000

| Metric | Experiment | Pure RRF (main run) | LLM (main run) | Qwen3 (main run) |
|---|---|---|---|---|
| recall@10 | 0.762 | 0.762 | 0.691 | 0.809 |
| recall@20 | 0.857 | 0.809 | 0.833 | 0.881 |
| recall@50 | 0.905 | 0.905 | 0.881 | 0.905 |
| recall@all | 1.000 | 0.929 | 0.929 | 0.929 |
| mrr@10 | 0.680 | 0.674 | 0.729 | 0.713 |
| ndcg@10 | 0.458 | 0.554 | 0.549 | 0.536 |
| p@10 | 0.404 | 0.408 | 0.362 | 0.392 |

Candidate-pool size by question - experiment: 153, 270, 1087, 261, 205, 165, 272, 231, 302, 144, 324, 189, 295, 277, 347, 337, 324, 302, 172, 368, 229, 641, 835, 1106; main RRF: 8, 86, 956, 100, 35, 32, 86, 83, 142, 70, 233, 36, 197, 130, 280, 237, 207, 157, 148, 352, 183, 579, 737, 985
Evidence (căn cứ) absent from the candidate pool: none

## Additional experiment: B. Threshold 0,6, Qwen3 reranks the top 40, detention-rules topic

Questions: 3; times reranked: 3; median rerank time (ms): 32482.800

| Metric | Experiment | Pure RRF (main run) | LLM (main run) | Qwen3 (main run) |
|---|---|---|---|---|
| recall@10 | 0.667 | 0.667 | 0.667 | 0.667 |
| recall@20 | 0.667 | 0.667 | 0.667 | 0.667 |
| recall@50 | 0.667 | 0.667 | 0.667 | 0.667 |
| recall@all | 1.000 | 0.667 | 0.667 | 0.667 |
| mrr@10 | 0.556 | 0.548 | 0.500 | 0.556 |
| ndcg@10 | 0.290 | 0.510 | 0.494 | 0.530 |
| p@10 | 0.167 | 0.167 | 0.167 | 0.200 |

Candidate-pool size by question - experiment: 172, 368, 229; main RRF: 148, 352, 183
Evidence (căn cứ) absent from the candidate pool: none

## Additional experiment: C. Threshold 0,6, current LLM reranks the top 40, detention-rules topic

Questions: 3; times reranked: 3; median rerank time (ms): 38078.200

| Metric | Experiment | Pure RRF (main run) | LLM (main run) | Qwen3 (main run) |
|---|---|---|---|---|
| recall@10 | 0.667 | 0.667 | 0.667 | 0.667 |
| recall@20 | 0.667 | 0.667 | 0.667 | 0.667 |
| recall@50 | 0.667 | 0.667 | 0.667 | 0.667 |
| recall@all | 1.000 | 0.667 | 0.667 | 0.667 |
| mrr@10 | 0.733 | 0.548 | 0.500 | 0.556 |
| ndcg@10 | 0.317 | 0.510 | 0.494 | 0.530 |
| p@10 | 0.133 | 0.167 | 0.167 | 0.200 |

Candidate-pool size by question - experiment: 172, 203, 229; main RRF: 148, 352, 183
Evidence (căn cứ) absent from the candidate pool: none

## Additional experiment: D. Qwen3 reranks the first 20 results, all 24 questions

Questions: 24; times reranked: 24; median rerank time (ms): 19750.050

| Metric | Experiment | Pure RRF (main run) | LLM (main run) | Qwen3 (main run) |
|---|---|---|---|---|
| recall@10 | 0.762 | 0.762 | 0.691 | 0.809 |
| recall@20 | 0.809 | 0.809 | 0.833 | 0.881 |
| recall@50 | 0.905 | 0.905 | 0.881 | 0.905 |
| recall@all | 0.929 | 0.929 | 0.929 | 0.929 |
| mrr@10 | 0.696 | 0.674 | 0.729 | 0.713 |
| ndcg@10 | 0.530 | 0.554 | 0.549 | 0.536 |
| p@10 | 0.383 | 0.408 | 0.362 | 0.392 |

Candidate-pool size by question - experiment: 8, 86, 956, 100, 35, 32, 86, 83, 142, 70, 233, 36, 197, 130, 280, 237, 207, 157, 148, 352, 183, 579, 737, 985; main RRF: 8, 86, 956, 100, 35, 32, 86, 83, 142, 70, 233, 36, 197, 130, 280, 237, 207, 157, 148, 352, 183, 579, 737, 985
Evidence (căn cứ) absent from the candidate pool: 110/2021/TT-BCA Article (Điều) 2 :: Does Circular (Thông tư) 29/2016/TT-BCA still have effectivity (hiệu lực) (Thông tư 29/2016/TT-BCA còn hiệu lực không); 58/2026/TT-BCA Article (Điều) 11 :: rules of inmate detention facilities and rules of temporary detention camps (nội quy cơ sở giam giữ phạm nhân và nội quy trại tạm giam); 96/2026/TT-BCA Article (Điều) 3 :: items prohibited from being brought into temporary holding and temporary detention cells (đồ vật cấm đưa vào buồng tạm giữ tạm giam)

## Additional experiment: E. Threshold 0,6, Qwen3 reranks the entire candidate pool (at most 200), detention-rules topic

Questions: 3; times reranked: 3; median rerank time (ms): 147604.700

| Metric | Experiment | Pure RRF (main run) | LLM (main run) | Qwen3 (main run) |
|---|---|---|---|---|
| recall@10 | 0.667 | 0.667 | 0.667 | 0.667 |
| recall@20 | 0.667 | 0.667 | 0.667 | 0.667 |
| recall@50 | 0.833 | 0.667 | 0.667 | 0.667 |
| recall@all | 1.000 | 0.667 | 0.667 | 0.667 |
| mrr@10 | 0.548 | 0.548 | 0.500 | 0.556 |
| ndcg@10 | 0.259 | 0.510 | 0.494 | 0.530 |
| p@10 | 0.133 | 0.167 | 0.167 | 0.200 |

Candidate-pool size by question - experiment: 172, 368, 229; main RRF: 148, 352, 183
Evidence (căn cứ) absent from the candidate pool: none

## Additional experiment: F. Threshold 0,6, current LLM reranks the entire candidate pool (at most 200), detention-rules topic

Questions: 3; times reranked: 3; median rerank time (ms): 188938.500

| Metric | Experiment | Pure RRF (main run) | LLM (main run) | Qwen3 (main run) |
|---|---|---|---|---|
| recall@10 | 0.667 | 0.667 | 0.667 | 0.667 |
| recall@20 | 0.833 | 0.667 | 0.667 | 0.667 |
| recall@50 | 1.000 | 0.667 | 0.667 | 0.667 |
| recall@all | 1.000 | 0.667 | 0.667 | 0.667 |
| mrr@10 | 0.733 | 0.548 | 0.500 | 0.556 |
| ndcg@10 | 0.317 | 0.510 | 0.494 | 0.530 |
| p@10 | 0.133 | 0.167 | 0.167 | 0.200 |

Candidate-pool size by question - experiment: 172, 203, 229; main RRF: 148, 352, 183
Evidence (căn cứ) absent from the candidate pool: none

## Additional experiment: G. Qwen3 first server build (vocabulary projection at every position not yet dropped), all 24 questions

Questions: 24; times reranked: 24; median rerank time (ms): 35067.750

| Metric | Experiment | Pure RRF (main run) | LLM (main run) | Qwen3 (main run) |
|---|---|---|---|---|
| recall@10 | 0.809 | 0.762 | 0.691 | 0.809 |
| recall@20 | 0.881 | 0.809 | 0.833 | 0.881 |
| recall@50 | 0.905 | 0.905 | 0.881 | 0.905 |
| recall@all | 0.929 | 0.929 | 0.929 | 0.929 |
| mrr@10 | 0.713 | 0.674 | 0.729 | 0.713 |
| ndcg@10 | 0.536 | 0.554 | 0.549 | 0.536 |
| p@10 | 0.392 | 0.408 | 0.362 | 0.392 |

Candidate-pool size by question - experiment: 8, 86, 956, 100, 35, 32, 86, 83, 142, 70, 233, 36, 197, 130, 280, 237, 207, 157, 148, 352, 183, 579, 737, 985; main RRF: 8, 86, 956, 100, 35, 32, 86, 83, 142, 70, 233, 36, 197, 130, 280, 237, 207, 157, 148, 352, 183, 579, 737, 985
Evidence (căn cứ) absent from the candidate pool: 110/2021/TT-BCA Article (Điều) 2 :: Does Circular (Thông tư) 29/2016/TT-BCA still have effectivity (hiệu lực) (Thông tư 29/2016/TT-BCA còn hiệu lực không); 58/2026/TT-BCA Article (Điều) 11 :: rules of inmate detention facilities and rules of temporary detention camps (nội quy cơ sở giam giữ phạm nhân và nội quy trại tạm giam); 96/2026/TT-BCA Article (Điều) 3 :: items prohibited from being brought into temporary holding and temporary detention cells (đồ vật cấm đưa vào buồng tạm giữ tạm giam)
