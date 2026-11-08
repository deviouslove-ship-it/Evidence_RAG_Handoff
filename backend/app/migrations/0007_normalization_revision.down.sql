DROP INDEX IF EXISTS document_nodes_stale_normalization;
ALTER TABLE document_nodes DROP COLUMN IF EXISTS normalization_revision;
