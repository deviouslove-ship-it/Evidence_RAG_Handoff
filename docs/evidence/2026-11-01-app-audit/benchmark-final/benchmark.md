# Search v1 synthetic benchmark (HƯ CẤU)

- Dataset: 1000 documents x 100 nodes = 100000 nodes
- Verified node count: 100000
- Seed time: 14.01 s
- Phrase p50/p95: 75.49 / 77.52 ms
- Keywords p50/p95: 56.51 / 58.27 ms
- Empty p50/p95: 26.71 / 26.71 ms
- API default call (approximate count capped at 500): {'latency_ms': 80.4, 'documents': 1000, 'approximate_hidden': 0}
- Target p95 (tạm, chưa chốt): 300 ms — chỉ có hiệu lực trên máy Windows đích.
- Synthetic target verdict: phrase p95 = 77.52 ms (meets the provisional 300 ms target).
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

- Execution: 0.588 ms; planning: 3.07 ms
- `document_nodes_search_word_gin` in plan: False

| Depth | Node | Relation | Index | Actual time (ms) | Actual rows | Loops |
|---|---|---|---|---|---|---|
| 0 | Sort | None | None | 0.416 | 1.0 | 1 |
| 1 | Nested Loop | None | None | 0.402 | 0.0 | 1 |
| 2 | Nested Loop | None | None | 0.401 | 0.0 | 1 |
| 3 | Nested Loop | None | None | 0.401 | 0.0 | 1 |
| 4 | Nested Loop | None | None | 0.401 | 0.0 | 1 |
| 5 | Nested Loop | None | None | 0.401 | 0.0 | 1 |
| 6 | Hash Join | None | None | 0.4 | 0.0 | 1 |
| 7 | Unique | None | None | 0.38 | 1.0 | 1 |
| 8 | Sort | None | None | 0.38 | 1.0 | 1 |
| 9 | Seq Scan | document_versions | None | 0.255 | 1000.0 | 1 |
| 7 | Hash | None | None | 0.017 | 0.0 | 1 |
| 8 | Bitmap Heap Scan | document_nodes | None | 0.017 | 0.0 | 1 |
| 9 | Bitmap Index Scan | None | document_nodes_search_folded_gin | 0.012 | 0.0 | 1 |
| 6 | Index Scan | documents | documents_pkey | 0.0 | 0 | 0 |
| 5 | Index Scan | source_spans | source_spans_pkey | 0.0 | 0 | 0 |
| 4 | Index Scan | source_pages | source_pages_pkey | 0.0 | 0 | 0 |
| 3 | Index Scan | source_provenance | source_provenance_document_version_id_key | 0.0 | 0 | 0 |
| 2 | Limit | None | None | 0.0 | 0 | 0 |
| 3 | Sort | None | None | 0.0 | 0 | 0 |
| 4 | Nested Loop | None | None | 0.0 | 0 | 0 |
| 5 | Index Scan | node_effective_intervals | node_effective_intervals_lookup | 0.0 | 0 | 0 |
| 5 | Index Scan | effectivity_snapshot_revisions | effectivity_snapshot_revisions_pkey | 0.0 | 0 | 0 |
| 1 | Nested Loop | None | None | 0.41 | 1.0 | 1 |
| 2 | Aggregate | None | None | 0.404 | 1.0 | 1 |
| 3 | Sort | None | None | 0.402 | 0.0 | 1 |
| 4 | CTE Scan | None | None | 0.401 | 0.0 | 1 |
| 2 | Subquery Scan | None | None | 0.005 | 0.0 | 1 |
| 3 | WindowAgg | None | None | 0.004 | 0.0 | 1 |
| 4 | WindowAgg | None | None | 0.004 | 0.0 | 1 |
| 5 | Sort | None | None | 0.004 | 0.0 | 1 |
| 6 | Nested Loop | None | None | 0.001 | 0.0 | 1 |
| 7 | CTE Scan | None | None | 0.0 | 0.0 | 1 |
| 7 | Subquery Scan | None | None | 0.0 | 0 | 0 |
| 8 | WindowAgg | None | None | 0.0 | 0 | 0 |
| 9 | Sort | None | None | 0.0 | 0 | 0 |
| 10 | Subquery Scan | None | None | 0.0 | 0 | 0 |
| 11 | Unique | None | None | 0.0 | 0 | 0 |
| 12 | Sort | None | None | 0.0 | 0 | 0 |

Dữ liệu sinh tổng hợp, không phải văn bản pháp luật; không dùng số này để tuyên bố chất lượng search.
