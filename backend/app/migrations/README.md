# Database migrations

Migrations target PostgreSQL with `pgcrypto` and `pgvector`. The backend applies them
on startup through `runner.py`: files `NNNN_*.sql` run in name order, each in its own
transaction, recorded in `schema_migrations` with the SHA-256 of the SQL text. A file
changed after it was applied stops startup (`MIGRATION_CHANGED_AFTER_APPLY`) instead of
being re-applied. Migrations do not create databases, move business data, or install
PostgreSQL.

| Up | Down | Purpose |
|---|---|---|
| `0001_core.sql` | `0001_core.down.sql` | Core schema, ACL views |
| `0002_auth_admin.sql` | `0002_auth_admin.down.sql` | Accounts, roles, sessions |
| `0003_source_integrity.sql` | `0003_source_integrity.down.sql` | Page text, audit order, span re-validation |
| `0004_ai_runtime.sql` | `0004_ai_runtime.down.sql` | Model profile parameters |
| `0005_pdf_content_fingerprint.sql` | `0005_pdf_content_fingerprint.down.sql` | Content duplicate signal |
| `0006_search_index.sql` | `0006_search_index.down.sql` | Search v1 GIN expression indexes |
| `0007_normalization_revision.sql` | `0007_normalization_revision.down.sql` | Normalization revision stamp |
| `0008_source_format.sql` | `0008_source_format.down.sql` | Upload format and hash of Word/TXT sources |
| `0009_node_structure.sql` | `0009_node_structure.down.sql` | Page-by-page source spans, citation label, `node_source_text_valid` |
| `0010_ai_policy.sql` | `0010_ai_policy.down.sql` | AI stage policies and runtime settings |
| `0011_effectivity.sql` | `0011_effectivity.down.sql` | Effectivity relations, reviews and snapshots |
| `0012_comprehensive_search.sql` | `0012_comprehensive_search.down.sql` | Comprehensive search and flexible vector dimensions |
| `0013_content_groups.sql` | `0013_content_groups.down.sql` | Content groups and labeling rules |
| `0014_embedding_jobs.sql` | `0014_embedding_jobs.down.sql` | Background embedding rebuild jobs, index states `paused`/`failed` |
| `0015_ocr_page_review.sql` | `0015_ocr_page_review.down.sql` | OCR page diagnostics and the reviewer who confirmed a page against the scan |
| `0016_document_management.sql` | `0016_document_management.down.sql` | Versioned metadata, OCR edits, lookup availability and cache revision |

Migration `0016` preserves all existing versions, hashes and vectors. The intake hash
remains unique for each original. Corrections can refer to that same immutable original.
The down migration works on an unused schema and refuses to drop the new fields once they
contain management data. Preserve an encrypted pre-upgrade backup for a binary rollback.

Every up file needs a matching `.down.sql` (`scripts/validate_migrations.py`). Do not add
a b-tree index on `document_nodes(document_version_id)` without re-running the search
benchmark: the planner prefers it over the GIN indexes (ADR-006 §2.3).

Production acceptance additionally requires:

1. pgvector extension and exact vector query verified on the target Windows host.
2. Migration up/down tested against a clean test database.
3. ACL leakage tests for category and document grants.
4. Backup encrypted and restored to a clean host, followed by the deletion ledger replay.
