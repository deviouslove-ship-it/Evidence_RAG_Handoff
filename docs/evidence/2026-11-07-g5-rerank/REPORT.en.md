**Language / Ngôn ngữ:** [Tiếng Việt](REPORT.md) · English

English counterpart of `docs/evidence/2026-11-07-g5-rerank/REPORT.md`. The Vietnamese file is the original.

# G5: test of a dedicated reranker (Qwen3-Reranker-0.6B) on 100 trial administrative documents (văn bản)

**Same-day update (`REPORT-50-cau.md`):** by the owner's decision, LLM rerank no longer runs on its own; pure RRF is the default of
"Comprehensive search" (`EVIDENCE_RERANK_DEFAULT=false`), and the two rerank options are kept as optional. The 100-file data has been rebuilt, backed up, and the
test set extended to 50 questions. The sentences below about "the interface calling rerank by itself" describe the state before that change. The "Regression" section and where the data is kept: see
`REPORT-50-cau.md` and `DATA-INVENTORY.md`; the database of the first 24-question run was deleted and rebuilt identically (same files, same model).

Run date: 2026-11-07. Machine: AMD Ryzen 9 6900HX (8 cores, 16 threads), RAM 29,7 GB, no GPU.
Source figures: `bench-*.json`, `compare.json`, `compare.md`, `diagnose-noi-quy.json`, `micro-latency.json`.
Every figure below is taken from those files; no figure was typed into the code by hand.

**Data status:** 100 files, 14 files belonging to document numbers present in the required evidence (căn cứ), the remaining 86 files chosen by
SHA-256 order of the file name (`evaluation/coverage/select_subset.py`, list in `subset-manifest.json`).
The question set and the required evidence (căn cứ) are the existing `evaluation/coverage/topics.json` (8 topics, 24 questions, 42 question–evidence (căn cứ) pairs).
The evidence (căn cứ) list **was drafted by the agent and has not been confirmed by a specialist officer**, so every metric is measured only against that list.

## 1. Current batched rerank

- Code: `ComprehensiveSearch._rerank` (`backend/app/storage/comprehensive.py`). The `rerank` stage of the Model Registry.
- Model in the experiment: `qwen3:1.7b` (2 billion parameters, Q4_K_M) through Ollama, `temperature 0`, `json_mode`, `max_tokens 1024`.
- Algorithm: take the first 40 candidates by RRF (`EVIDENCE_RERANK_TOP_N`), split into batches of 10 (`EVIDENCE_RERANK_BATCH_SIZE`).
  Each batch is a prompt asking the model to score each passage with an integer 0–3 and return JSON. Scores are sorted descending; equal scores keep the RRF order.
  The part outside the top 40 keeps the RRF order. If a batch has no valid result, stop; the unscored part keeps the RRF order.
- Measured consequence: in the head of the list, 99,2% of results share a score with another result, and the median has only 4 score levels
  (AUC for separating relevant evidence (căn cứ) 0,677). The effective ranking is decided by the RRF order; rerank only pushes passages scored 3 to the front.
- The interface currently does not send the `rerank` field, while the API defaults to `true`. If the Registry has a `rerank` route, every "Comprehensive search" run executes this step
  (about 45 seconds per question on the test machine).

## 2. Experimental integration of Qwen3-Reranker-0.6B (CPU, no API)

| Component | Content |
|---|---|
| Model | `Qwen/Qwen3-Reranker-0.6B` (Apache-2.0), downloaded to `E:\Programs\EvidenceRAG\models\qwen3-reranker-0.6b` |
| Environment | `E:\Programs\EvidenceRAG\runtimes\reranker-venv` (torch 2.15.0+cpu, transformers 5.22.2, psutil 7.2.2). The application's venv is unchanged |
| Service | `scripts/local_reranker_server.py`: binds only to the loopback address, fp32, 8 threads, batch 8, at most 1024 tokens, score = probability of "yes" relative to "no" following the model's instructions |
| Application | `backend/app/storage/cross_encoder.py` (accepts only a loopback URL) and the `_rerank_cross_encoder` branch. Enabled with `EVIDENCE_RERANK_BACKEND=cross_encoder` and `EVIDENCE_CROSS_ENCODER_URL` |
| Default | `EVIDENCE_RERANK_BACKEND=llm`: the old behavior, unchanged. No model in the Registry is changed |
| On error | The service does not respond or the time limit is exceeded: keep the RRF order, `ranking.reranked=false` with a note (encountered when the timeout was left at 120 seconds with 200 candidates) |
| Also recorded | `ranking.duration_ms` and `ranking.backend` (added fields; they do not break the old contract) |

Note: the first server build computed the vocabulary projection at every position, causing a RAM peak of 8,3 GB. The current build computes it only at the last position (`logits_to_keep=1`).
The ranking order is identical to the first build on 24/24 questions; the table below uses the current build.

## 3. Comparison of three options (24 questions, 42 pairs)

Same `EVIDENCE_RERANK_TOP_N=40`, same question set; each option restarts the API and Ollama before measuring, with one warmup question not counted.
Recall@k is computed per pair (question, evidence (căn cứ)): an evidence (căn cứ) item counts when at least one Clause (Khoản) of that correct Article (Điều) is among the first k results.
MRR@10 and NDCG@10 are computed per clause (a clause that belongs to required evidence (căn cứ) is relevant, score 0/1).
NDCG is normalized by the number of relevant clauses in that same candidate pool, so it cannot be compared across candidate pools of different sizes.

| Metric | Pure RRF | RRF + current LLM rerank (qwen3:1.7b) | RRF + Qwen3-Reranker-0.6B |
|---|---|---|---|
| Recall@10 | 0,762 | 0,691 | 0,810 |
| Recall@20 | 0,810 | 0,833 | 0,881 |
| Recall@50 | 0,905 | 0,881 | 0,905 |
| Recall@entire pool | 0,929 | 0,929 | 0,929 |
| MRR@10 | 0,674 | 0,729 | 0,713 |
| NDCG@10 | 0,554 | 0,549 | 0,536 |
| Response time, median (seconds) | 2,5 | 47,7 | 32,3 |
| Response time, mean / p95 (seconds) | 2,9 / 4,1 | 46,1 / 56,6 | 31,1 / 36,4 |
| Rerank step alone, median (seconds) | 0 | 45,5 | 30,0 |
| API RAM peak / median | 92 / 90 MB | 96 / 90 MB | 93 / 90 MB |
| Ollama RAM peak / median (embedding + qwen3:1.7b) | 3,27 / 3,17 GB | **11,23 / 11,06 GB** | 3,27 / 3,17 GB |
| Rerank-service RAM peak / median | none | none | **4,85 / 3,85 GB** |
| Rerank score separating relevant evidence (căn cứ) (AUC, 0,5 = chance) | none | 0,677 | 0,801 |

Reading the results:

- Recall@50 and Recall@entire pool are unchanged between the options that rerank and RRF, because rerank only reorders within the first 40 results. The difference of 0,881 versus 0,905 for the LLM option comes from a different candidate pool on 3 questions (cause not yet verified; suspected to be the `expand` step or the time limit of the concept channel when the machine is under heavy load).
- Considering only the 21 questions whose candidate pool is identical across all three options: Recall@10 0,784 / 0,703 / 0,811; Recall@20 0,838 / 0,865 / 0,892; MRR@10 0,689 / 0,714 / 0,708; NDCG@10 0,540 / 0,524 / 0,512; P@10 0,409 / 0,362 / 0,391 (RRF / LLM / Qwen3).
- Per question, MRR@10 compared with RRF: LLM better on 9, worse on 4, equal on 11; Qwen3 better on 8, worse on 5, equal on 11.
- Mean difference versus RRF (95% bootstrap confidence interval, 24 questions): LLM MRR +0,055 [−0,089; +0,188], NDCG −0,005 [−0,108; +0,091]; Qwen3 MRR +0,039 [−0,129; +0,209], NDCG −0,018 [−0,089; +0,053]. Every interval contains 0, so with 24 questions there is not yet evidence that any option is better than pure RRF.
- Qwen3 separates better (AUC 0,801 with continuous scores, 0,7% tied scores) and has the highest Recall@10/20, but NDCG@10 is a little lower than RRF (not statistically significant).
- Both rerank options are slow: 32 and 48 seconds per question against 2,5 seconds. With Qwen3 reranking only the first 20 results (experiment D): median 19,8 seconds, MRR@10 0,696, NDCG@10 0,530, Recall@10/20/50 the same as RRF.

Latency of the Qwen3 scoring step alone (40 passages of 600 characters, `micro-latency.json`): 39,4 seconds (8 threads), 40,9 seconds (16 threads), 38,6 seconds (batch 4), 40,5 seconds (length 512): no configuration was faster. Dropping the vocabulary projection at every position leaves 32,8 seconds, with scores unchanged. bf16 took 298 seconds. Dynamic int8 leaves 21,4 seconds but matches only 3/10 of the top results against fp32 (maximum score deviation 0,48), so it is not usable.

## 4. Two evidence (căn cứ) items not found: a candidate-retrieval error or a ranking error

Across the 100 files, three pairs are not in the candidate pool of any channel (RRF; all three options are the same):
58/2026 Article (Điều) 11 for the question "rules of inmate detention facilities and rules of temporary detention camps (nội quy cơ sở giam giữ phạm nhân và nội quy trại tạm giam)", 96/2026 Article (Điều) 3 for the question "items prohibited from being brought into temporary holding and temporary detention cells (đồ vật cấm đưa vào buồng tạm giữ tạm giam)",
and 110/2021 Article (Điều) 2 for the question "Does Circular (Thông tư) 29/2016/TT-BCA still have effectivity (hiệu lực) (Thông tư 29/2016/TT-BCA còn hiệu lực không)" (the third pair's cause has not been analyzed, but it was found in experiment A).
The first two pairs are the same as the two missing pairs from the earlier G5 measurement on 293 administrative documents (văn bản).

**Conclusion: both are candidate-retrieval errors, not ranking errors.** Data from `diagnose-noi-quy.json`:

| | 58/2026 Article (Điều) 11 (question 1) | 96/2026 Article (Điều) 3 (question 2) |
|---|---|---|
| Clause (Khoản) present in the store and with a vector | yes (3 clauses) | yes (8 clauses, belonging to 2 administrative documents (văn bản) with the same number 96/2026) |
| True position of the nearest vector among 7.230 vectors | 26 (similarity 0,563) | 52 (0,530) |
| Semantic-channel threshold (0,8 × best result) | 0,622: excluded | 0,653: excluded |
| Exact / concept channels | 4 and 80 clauses, not contained | 7 and 146 clauses, not contained |
| Content | "Implementation effectivity (Hiệu lực thi hành)", replacing 32/2017 and 36/2017 | Article (Điều) 3 of the inmate rules (sleeping place, meals), and Article (Điều) 3 "Implementation effectivity (Hiệu lực thi hành)" of the promulgating Circular (Thông tư) |

Tried lowering the threshold to 0,6 (only the configuration `EVIDENCE_SEMANTIC_RELATIVE_THRESHOLD` was changed, experiments A–F):

- All 42/42 pairs entered the candidate pool (Recall@entire pool went from 0,929 to 1,000). The total number of candidate clauses for the 24 questions rose from 6.059 to 8.836 (1,46 times); these two questions alone rose from 148 to 172 and from 352 to 368, and the first question of the fingerprint topic rose from 8 to 153. Recall@20 rose from 0,810 to 0,857, MRR@10 from 0,674 to 0,680, and P@10 was almost unchanged (0,408 compared with 0,404).
- After entering the pool, the two evidence (căn cứ) items stood at RRF ranks 78 and 125, outside the first 40 results that rerank processes.
- Having rerank process the whole pool (at most 200): Qwen3 brought them to rank 91 (score 0,057) and rank 49 (score 0,224); the current LLM to ranks 20 and 42. No option brought them into the top 10.
- A plausible reason: these two articles are implementation-effectivity (hiệu lực thi hành) provisions or rules written for inmates, while the questions ask about temporary-detention-camp rules and prohibited items. They are found correctly through the effectivity (hiệu lực) relation (the `relation` channel), but in this set of 100 files no relation has been reviewed, so that channel contributes nothing. Evidence (căn cứ) 96/2026 Article (Điều) 3 for question 2 may be a wrong label; an officer needs to confirm it.

Changing the reranker therefore cannot fix these two evidence (căn cứ) items. The fix is in retrieval: lower the semantic threshold, or review the effectivity (hiệu lực) relations of the two rules Circulars (Thông tư).

## 5. Recommendation

1. **Do not change the default yet.** No option is better than pure RRF in a statistically significant way on this question set, and both reranks cost 30 to 48 seconds per question.
2. **Current LLM rerank** (`qwen3:1.7b`): scores are almost all tied (99,2%), Recall@10 is lower than RRF (0,691 compared with 0,762), Ollama RAM rises from 3,3 to 11,2 GB, 48 seconds per question. The interface is calling it under the default `rerank=true`; consider turning it off on a machine without a GPU.
3. **Qwen3-Reranker-0.6B** is the better rerank option on score quality (AUC 0,801 compared with 0,677), 1,5 times faster, and it does not need Ollama, but 32 seconds per question (20 seconds with 20 candidates) is still too slow for direct lookup, and it needs another 3,9 GB of RAM (peak 4,9 GB). It can be used as a "deep ranking" mode that runs in the background or on a machine with a GPU; the GPU has not been measured.
4. **What should be done before choosing:** (a) have a specialist officer confirm the evidence (căn cứ) list; (b) enlarge the question set (24 questions is too few; every confidence interval contains 0); (c) decide the semantic-channel threshold (experiment A shows Recall rises when the threshold is lowered); (d) review the effectivity (hiệu lực) relations for the two rules Circulars (Thông tư).

## 6. Limitations

- Only 100 administrative documents (văn bản); the set of 293 administrative documents (văn bản) from the previous G5 measurement gives different figures (a different candidate pool).
- 24 questions, 42 pairs; no test of statistical significance passed.
- The LLM option's candidate pool differs on 3/24 questions (cause not yet verified); the table for the 21 identical questions was reported separately.
- One run per option; time and RAM depend on the machine (8-core CPU, fp32, 8 threads).
- The trial with a 120-second timeout and 200 candidates left no separate result file; the return to RRF order was observed directly.
- A GPU has not been tried, larger rerank models (4B, 8B) have not been tried, and the Qwen3 instruction prompt has not been optimized (one fixed sentence is used).

## 7. Regression

`scripts/verify.ps1 -ProgramsRoot E:\Programs` passed 12/12 (`verify/`): backend 218 passed (unchanged from before), frontend 74 passed,
ruff, mypy, 13 migration pairs, OpenAPI, and the hard-coded-path check are all clean. No new test was added.
