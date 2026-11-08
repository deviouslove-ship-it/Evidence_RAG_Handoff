# Search v1 synthetic benchmark (HƯ CẤU)

- Dataset: 1000 documents x 100 nodes = 100000 nodes
- Verified node count: 100000
- Seed time: 18.76 s
- Phrase p50/p95: 243.62 / 324.31 ms
- Keywords p50/p95: 255.57 / 268.95 ms
- Empty p50/p95: 62.61 / 62.61 ms
- API default call (approximate count capped at 500): latency 338.66 ms, documents 1000, approximate_hidden 0
- Target p95 (tạm, chưa chốt): 300 ms — chỉ có hiệu lực trên máy Windows đích.
- Synthetic target verdict: phrase p95 = 324.31 ms (exceeds the provisional 300 ms target).
- `enable_seqscan` is left at its default; no seqscan was forced off.

## Planner settings

| Setting | Value |
|---|---|
| default_statistics_target | 100  |
| effective_cache_size | 524288 8kB |
| enable_bitmapscan | on  |
| enable_indexscan | on  |
| enable_seqscan | on  |
| jit | on  |
| maintenance_work_mem | 65536 kB |
| max_parallel_workers_per_gather | 2  |
| random_page_cost | 4  |
| seq_page_cost | 1  |
| work_mem | 4096 kB |

## Phrase query plan (EXPLAIN ANALYZE)

- Execution: 66.81 ms; planning: 5.425 ms
- `document_nodes_search_word_gin` in plan: True

| Depth | Node | Relation | Index | Actual time (ms) | Actual rows | Loops |
|---|---|---|---|---|---|---|
| 0 | Limit | None | None | 66.57 | 50.0 | 1 |
| 1 | Sort | None | None | 66.564 | 50.0 | 1 |
| 2 | Nested Loop | None | None | 65.81 | 1000.0 | 1 |
| 3 | Nested Loop | None | None | 32.608 | 1000.0 | 1 |
| 4 | Nested Loop | None | None | 30.777 | 1000.0 | 1 |
| 5 | Nested Loop | None | None | 26.66 | 1000.0 | 1 |
| 6 | Nested Loop | None | None | 23.171 | 1000.0 | 1 |
| 7 | Hash Join | None | None | 20.869 | 1000.0 | 1 |
| 8 | Unique | None | None | 0.774 | 1000.0 | 1 |
| 9 | Sort | None | None | 0.539 | 1000.0 | 1 |
| 10 | Seq Scan | document_versions | None | 0.307 | 1000.0 | 1 |
| 8 | Hash | None | None | 19.492 | 1000.0 | 1 |
| 9 | Bitmap Heap Scan | document_nodes | None | 18.915 | 1000.0 | 1 |
| 10 | Bitmap Index Scan | None | document_nodes_search_word_gin | 0.269 | 1000.0 | 1 |
| 7 | Index Scan | documents | documents_pkey | 0.002 | 1.0 | 1000 |
| 6 | Index Scan | source_spans | source_spans_pkey | 0.003 | 1.0 | 1000 |
| 5 | Index Scan | source_pages | source_pages_pkey | 0.004 | 1.0 | 1000 |
| 4 | Index Scan | source_provenance | source_provenance_document_version_id_key | 0.001 | 1.0 | 1000 |
| 3 | Limit | None | None | 0.002 | 0.0 | 1000 |
| 4 | Sort | None | None | 0.002 | 0.0 | 1000 |
| 5 | Nested Loop | None | None | 0.001 | 0.0 | 1000 |
| 6 | Index Scan | node_effective_intervals | node_effective_intervals_lookup | 0.001 | 0.0 | 1000 |
| 6 | Index Scan | effectivity_snapshot_revisions | effectivity_snapshot_revisions_pkey | 0.0 | 0 | 0 |

Dữ liệu sinh tổng hợp, không phải văn bản pháp luật; không dùng số này để tuyên bố chất lượng search.
