**Language / Ngôn ngữ:** [Tiếng Việt](REPORT-tiebreak.md) · English

English counterpart of `docs/evidence/2026-11-07-g5-rerank/REPORT-tiebreak.md`. The Vietnamese file is the original.

# Stable tie-break key for RRF and the channels of "Comprehensive search"

Date: 2026-11-08. The RRF formula (k = 60), the channels, the thresholds, the embeddings, and the existing data are unchanged. Embeddings were not rebuilt, and nothing was deleted.

## 1. The problem

When two clauses have the same score, order is decided by `node_id`, a UUID generated at random on each import. Two imports of the same 100 files
give two different orders. This happens in three places, not only in `_rrf`:

| Where | Previous tie-break |
|---|---|
| `_rrf` (fusion of 4 channels) | RRF score, best rank, then `node_id` |
| Exact channel (`candidates_sql`, used only for this channel) | tier, `ts_rank_cd` score, then `node_id`; the within-channel rank is an input to RRF, so the UUID also affects the RRF score |
| Relation channel (`_relation_hits`) | rank, then `node_id` |

Measured before the fix on two databases imported independently from the same 100 files (`tiebreak-before-*.md`; 17/50 questions return an empty result on the exact channel, counted on both sides):

| Channel | Same result set | Same full order | Share of positions that match |
|---|---|---|---|
| exact | 50/50 | 45/50 | 0,672 |
| exact + relation (with RRF fusion) | 50/50 | 41/50 | 0,613 |

## 2. The new key

Replace `node_id` with a key based on the position of the clause, the same on every import of the same files:

1. administrative-document (văn bản) number (`documents.document_number`);
2. SHA-256 of the file (`document_versions.original_file_sha256`, unique; it separates two administrative documents (văn bản) that share a number, such as 96/2026);
3. the ordinal inside the administrative document (văn bản), which is the prefix of `document_nodes.path` (for example `000034:chuong:II/dieu:6/khoan:4`), that is, the reading order of Article (Điều), Clause (Khoản), and Point (Điểm);
4. `path` itself;
5. `node_id` remains only as the last choice for a clause that has no key.

Comparison is by bytes (`COLLATE "C"` in SQL, code-point order in Python), so it does not depend on the server locale. Code: `stable_clause_key` and `stable_order_sql`
(`storage/search_paging.py`), used in `_rrf`, `candidates_sql`, and `_relation_hits` (`storage/comprehensive.py`). Search v1 (`document_page_sql`) is unchanged.
The original copies of the files were saved under `.agents/backup-2026-11-08-rrf-tiebreak/`.

## 3. Checks

| Check | Result |
|---|---|
| SQL order equals Python order on every clause (7.230) | equal |
| `_rrf` after reassigning a random UUID to every clause, 20 times | identical 20/20 with the key; 0/20 without the key (old behavior) |
| Two independently imported databases, exact channel | same full order **50/50** (before: 45/50) |
| Two independently imported databases, exact + relation + RRF fusion | **50/50** (before: 41/50) |
| Same database, two passes, exact + semantic + relation channels | 50/50, positions matching 100% |
| `scripts/verify.ps1` | 12/12; backend 225 passed, frontend 77 passed (see section 5) |

Tool: `evaluation/coverage/check_tiebreak_stability.py`. Not yet checked across two imports: the semantic channel (the two databases imported later have no vectors yet; embeddings were not created, as requested),
and the concept channel (it depends on the LLM `expand` step; see section 4).

## 4. Effect on the results (same database `evidence_rerank_eval`, 50 questions, pure RRF)

| Metric | Old key (UUID) | New key |
|---|---|---|
| Recall@10 / @20 | 0,865 / 0,892 | 0,865 / 0,892 |
| Recall@50 | 0,932 | 0,946 |
| Recall@entire pool | 0,960 | 0,960 |
| MRR@10 | 0,790 | 0,779 |
| NDCG@10 | 0,594 | 0,589 |
| P@10 | 0,344 | 0,342 |

Recall stays the same at 10, 20, and the entire pool; the remaining changes sit inside the known swing (±0,02). Order changes sharply at tied positions: the top 10 results match the old results on only 10/50 questions,
because ties are very common. That is expected when the key changes: the key only changes the order among clauses with equal scores, and does not change which clauses are found (the exact channel's result set is the same between the two databases, 50/50, both before and after the fix).

Two consecutive passes on the same database with all four channels still give different candidate pools on 12/50 questions (evidence (căn cứ) ranks differ on 3/50; `bench-rrf-50-stable-1/2.json`). When the concept channel is removed, 50/50 are identical,
so the remaining unstable source is the `expand` step (LLM) of the concept channel, not the tie-break key. The semantic channel uses an approximate HNSW index; a rebuilt index can give slightly different neighbors.

## 5. Notes on the code tree and the data

- From 20:53 to 21:19 on 2026-11-07 there were other changes in the code tree that are not part of this piece of work: migration `0014_embedding_jobs`, embedding management in the Admin Portal
  (`EmbeddingManager`), `storage/embedding_jobs.py`, `deploy/portable`, `docs/openapi.json`. Regression ran on the current code tree, so the test counts are 225 and 77 (previously 218 and 74); I did not add any test.
- Starting the API applies any missing migration by itself, so `0014` was applied to `evidence_rerank_eval` (adding the table `embedding_jobs` and a few columns of `embedding_indices`; the 7.230 vectors and the `ready` index are unchanged) and to the newly imported trial database.
  The first dump (schema 0013) and the restored copy `evidence_rerank_eval_restorecheck` are still intact. So the backup would match the current database, an additional dump was created,
  `backups\rerank-eval\evidence_rerank_eval-schema0014-20261108-084058.dump` (37 MB, SHA-256 `02c13cc1…b2ce`), with a trial restore into `evidence_rerank_eval_restorecheck_0014`
  and `verify_db_restore.py` passed (52 tables, 38.107 rows, 101 indexes; vectors and HNSW match).
- The new database `evidence_rerank_eval_reimport` (100 files imported again, no embeddings, document store `data\rerank-eval\reimport-check`) is kept; it is used by `check_tiebreak_stability.py`. No data was deleted.
