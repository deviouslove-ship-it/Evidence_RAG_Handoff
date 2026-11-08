# Search v1 synthetic benchmark (HƯ CẤU)

- Dataset: 1000 documents x 100 nodes = 100000 nodes
- Verified node count: 100000
- Seed time: 17.52 s
- Phrase p50/p95: 251.4 / 333.97 ms
- Keywords p50/p95: 303.72 / 327.05 ms
- Empty p50/p95: 56.68 / 56.68 ms
- API default call (approximate count capped at 500): {'latency_ms': 329.25, 'documents': 1000, 'approximate_hidden': 0}
- Target p95 (tạm, chưa chốt): 300 ms — chỉ có hiệu lực trên máy Windows đích.
- Synthetic target verdict: phrase p95 = 333.97 ms (exceeds the provisional 300 ms target).
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

- Execution: 503.15 ms; planning: 14.572 ms
- `document_nodes_search_word_gin` in plan: True

| Depth | Node | Relation | Index | Actual time (ms) | Actual rows | Loops |
|---|---|---|---|---|---|---|
| 0 | Limit | None | None | 502.918 | 50.0 | 1 |
| 1 | Sort | None | None | 502.913 | 50.0 | 1 |
| 2 | Nested Loop | None | None | 501.563 | 1000.0 | 1 |
| 3 | Nested Loop | None | None | 456.013 | 1000.0 | 1 |
| 4 | Nested Loop | None | None | 450.022 | 1000.0 | 1 |
| 5 | Nested Loop | None | None | 444.479 | 1000.0 | 1 |
| 6 | Nested Loop | None | None | 324.734 | 1000.0 | 1 |
| 7 | Nested Loop | None | None | 320.688 | 1000.0 | 1 |
| 8 | Bitmap Heap Scan | document_nodes | None | 36.44 | 1000.0 | 1 |
| 9 | Bitmap Index Scan | None | document_nodes_search_word_gin | 6.916 | 1000.0 | 1 |
| 8 | Unique | None | None | 0.199 | 1000.0 | 1000 |
| 9 | Sort | None | None | 0.049 | 1000.0 | 1000 |
| 10 | Seq Scan | document_versions | None | 0.329 | 1000.0 | 1 |
| 7 | Index Scan | documents | documents_pkey | 0.003 | 1.0 | 1000 |
| 6 | Seq Scan | source_provenance | None | 0.077 | 500.5 | 1000 |
| 5 | Index Scan | source_spans | source_spans_pkey | 0.005 | 1.0 | 1000 |
| 4 | Index Scan | source_pages | source_pages_pkey | 0.005 | 1.0 | 1000 |
| 3 | Limit | None | None | 0.004 | 0.0 | 1000 |
| 4 | Sort | None | None | 0.003 | 0.0 | 1000 |
| 5 | Nested Loop | None | None | 0.002 | 0.0 | 1000 |
| 6 | Index Scan | node_effective_intervals | node_effective_intervals_lookup | 0.002 | 0.0 | 1000 |
| 6 | Index Scan | effectivity_snapshot_revisions | effectivity_snapshot_revisions_pkey | 0.0 | 0 | 0 |

Dữ liệu sinh tổng hợp, không phải văn bản pháp luật; không dùng số này để tuyên bố chất lượng search.
