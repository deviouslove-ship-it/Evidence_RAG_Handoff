-- Search v1: expression indexes used by app/storage/search.py.
-- The query must use exactly the same expression, otherwise PostgreSQL will
-- not use these indexes.  `text_indexed` already contains breadcrumb + title +
-- document number + label + content and is immutable after ingest.
CREATE INDEX document_nodes_search_word_gin
  ON document_nodes
  USING GIN (to_tsvector('simple'::regconfig, text_indexed));

-- Accent folds are an additional recall channel with a lower weight; it never
-- promotes a result to the exact-phrase tier.
CREATE INDEX document_nodes_search_folded_gin
  ON document_nodes
  USING GIN (to_tsvector('simple'::regconfig, text_folded));
