**Language / Ngôn ngữ:** [Tiếng Việt](README.md) · English

English counterpart of `evaluation/coverage/README.md`. The Vietnamese file is the original.

# Coverage tests (D15, G5)

This is not the Gold QA set. Each topic has several ways of asking and a list of evidence (căn cứ) that **must be found** (document number + Article (Điều)), taken from `test-data/cau-hoi-kiem-thu-vong-1.md` and the `test-data/van-ban` set. The evidence was drafted by AI from the text of the files. A subject-matter specialist must confirm it before it is used as the standard.

| File | Contents |
|---|---|
| `topics.json` | 17 topics, 50 ways of asking, 74 pairs (question, required evidence). The first 8 topics (24 questions; an absent `set` = `v1`) are the original G5 set. 9 topics with `"set": "v2"` (26 questions) were drafted as a supplement (bổ sung) on 2026-11-07 from the text of 100 trial administrative documents (văn bản), before any search was run on them. The evidence was drafted by an agent and has not been confirmed by a specialist |
| `run_coverage.py` | Calls the real “Tìm toàn diện” (Comprehensive search) API; measures the rate at which required items are found, with all channels together and with each channel alone; reads the entire result through pagination; exports a JSON report |
| `g3_relations_reference.json` | 31 Article / Clause (Khoản) / Point (Điểm)-level relations checked against the verbatim text (prepared by: an agent; not yet confirmed by a specialist) |
| `measure_g3_relations.py` | Precision and coverage of the Article / Clause-level relation reader |

```powershell
$env:EVIDENCE_EVAL_USERNAME = '<tài khoản USER>'; $env:EVIDENCE_EVAL_PASSWORD = '<mật khẩu>'
python evaluation/coverage/run_coverage.py --base-url http://127.0.0.1:8000 --out coverage.json
$env:DATABASE_URL = '<chuỗi kết nối>'; python evaluation/coverage/measure_g3_relations.py --out g3.json
```

After changing the embedding model, measure again: `python scripts/build_embeddings.py --rebuild` (the new index replaces (thay thế) the old index once there are enough vectors), then run `run_coverage.py` again and compare the two reports.

**The default of “Tìm toàn diện” (Comprehensive search) is pure RRF, with no rerank** (`EVIDENCE_RERANK_DEFAULT=false`). Both rerank options are kept and are used when needed: a local LLM in batches (the `rerank` stage in the Model Registry, `EVIDENCE_RERANK_BACKEND=llm`) or Qwen3-Reranker-0.6B on CPU (`EVIDENCE_RERANK_BACKEND=cross_encoder`). A request may send `"rerank": true` to turn rerank on for that request only. Set `EVIDENCE_RERANK_DEFAULT=true` to turn it on for every request that does not say. The default similarity threshold of the semantic channel is 0.8 (`EVIDENCE_SEMANTIC_RELATIVE_THRESHOLD`). 0.6 is used only when experimenting.

## Reranker comparison (experiment)

| File | Contents |
|---|---|
| `select_subset.py` | Selects a fixed subset of N files (default 100): every file whose document number is in `topics.json`, and the rest by the SHA-256 of the file name; writes `subset-manifest.json` |
| `run_rerank_benchmark.py` | One ranking option: Recall@10/20/50, MRR@10, NDCG@10, P@10, time, and RAM (API, Ollama, rerank service) |
| `compare_rerank.py` | Merges the pure-RRF, current-LLM, and Qwen3 reports; a table for the same candidate group, a bootstrap confidence interval, rerank-score AUC, and a supplementary (bổ sung) experiment |
| `summarize_rrf.py` | Summarizes one pure-RRF run: the original set, the supplementary set, each topic, and evidence (căn cứ) outside the top 10 results |
| `compare_reproduction.py` | Compares two runs of the same question set by (document number, Clause (Khoản) label): candidate group, position, and evidence rank; used to check reproducibility after rebuilding or restoring the database |
| `../../scripts/verify_db_restore.py` | Compares the original database with the restore from `pg_dump`: row counts, checksums of administrative documents (văn bản) and vectors, indexes, and an HNSW query |
| `diagnose_missing.py` | One missing evidence item: a candidate-retrieval error or a ranking error (the true vector position, the semantic-channel threshold, and the position in each channel) |

Qwen3-Reranker service (a separate venv with the CPU build of `torch`, `transformers`, and `psutil`; the application's venv does not need them):

```powershell
python scripts/local_reranker_server.py --model-dir <thư mục model Qwen3-Reranker-0.6B> --threads 8
$env:EVIDENCE_RERANK_BACKEND = 'cross_encoder'                 # mặc định: llm
$env:EVIDENCE_CROSS_ENCODER_URL = 'http://127.0.0.1:8791'      # chỉ nhận địa chỉ loopback
# tùy chọn: EVIDENCE_CROSS_ENCODER_TIMEOUT_SECONDS (120), EVIDENCE_CROSS_ENCODER_INSTRUCTION
```

Each option is run separately against an API started with the matching configuration (pure RRF: `--rerank off`):

```powershell
python evaluation/coverage/run_rerank_benchmark.py --variant rrf --rerank off --base-url <api> `
  --pid-file api=<tệp pid> --out bench-rrf.json
python evaluation/coverage/compare_rerank.py --rrf bench-rrf.json --llm bench-llm.json --ce bench-ce.json `
  --out-json compare.json --out-md compare.md
```

Results of the run on 2026-11-07 (100 files): `docs/evidence/2026-11-07-g5-rerank/REPORT.md`.
