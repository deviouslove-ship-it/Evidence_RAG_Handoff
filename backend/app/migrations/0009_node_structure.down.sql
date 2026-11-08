DROP FUNCTION IF EXISTS node_source_text_valid(UUID);
ALTER TABLE document_nodes DROP COLUMN IF EXISTS citation_label;
DROP TABLE IF EXISTS node_source_spans;
