-- Normalization revision for Search v1 index consistency.
-- Existing rows were produced by vietnamese-tone-v2 (no kì→kỳ mapping); new
-- rows are produced by the current normalizer revision.  Rows whose revision
-- differs must be backfilled with scripts/backfill_search_normalization.py.
ALTER TABLE document_nodes ADD COLUMN normalization_revision TEXT;
UPDATE document_nodes SET normalization_revision = 'vietnamese-tone-v2';
ALTER TABLE document_nodes ALTER COLUMN normalization_revision SET NOT NULL;
ALTER TABLE document_nodes ALTER COLUMN normalization_revision SET DEFAULT 'vietnamese-tone-v3';

CREATE INDEX document_nodes_stale_normalization
  ON document_nodes (normalization_revision)
  WHERE review_status = 'approved';
