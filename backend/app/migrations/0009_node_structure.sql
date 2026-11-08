-- G0: a node may be anchored to several source spans (one per page, in reading
-- order) and records a citation label ("Điểm a khoản 2 Điều 5").  parent_id,
-- page_end and path already exist; the application now fills them.
CREATE TABLE node_source_spans (
  node_id UUID NOT NULL REFERENCES document_nodes(id) ON DELETE CASCADE,
  ordinal INTEGER NOT NULL CHECK (ordinal > 0),
  source_span_id UUID NOT NULL REFERENCES source_spans(id),
  PRIMARY KEY (node_id, ordinal)
);
CREATE INDEX node_source_spans_span ON node_source_spans (source_span_id);

-- Existing nodes keep their single span as span 1.
INSERT INTO node_source_spans (node_id, ordinal, source_span_id)
SELECT id, 1, source_span_id FROM document_nodes WHERE source_span_id IS NOT NULL;

ALTER TABLE document_nodes ADD COLUMN citation_label TEXT;

-- The whole quote of a node, page by page: every span lies inside a usable page
-- of the node's own version, span 1 is document_nodes.source_span_id, and the
-- spans joined by a newline are exactly the node text.
-- A node without node_source_spans rows is checked as one span
-- (document_nodes.source_span_id), exactly as before this migration.
CREATE FUNCTION node_source_text_valid(p_node UUID) RETURNS boolean
LANGUAGE sql STABLE AS $$
  WITH spans AS (
    SELECT nss.ordinal, nss.source_span_id FROM node_source_spans nss
    WHERE nss.node_id = p_node
    UNION ALL
    SELECT 1, n0.source_span_id FROM document_nodes n0
    WHERE n0.id = p_node AND n0.source_span_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM node_source_spans x WHERE x.node_id = p_node)
  )
  SELECT COALESCE((
    SELECT count(*) = max(s.ordinal)
       AND bool_and(sp.document_version_id = n.document_version_id
                    AND sp.text_quality = 'usable'
                    AND sp.text_original IS NOT NULL
                    AND ss.original_length = char_length(ss.text_original)
                    AND substring(sp.text_original FROM ss.original_offset + 1
                                  FOR ss.original_length) = ss.text_original)
       AND (array_agg(s.source_span_id ORDER BY s.ordinal))[1]
           IS NOT DISTINCT FROM n.source_span_id
       AND string_agg(ss.text_original, E'\n' ORDER BY s.ordinal) = n.text_original
    FROM document_nodes n
    JOIN spans s ON TRUE
    JOIN source_spans ss ON ss.id = s.source_span_id
    JOIN source_pages sp ON sp.id = ss.page_id
    WHERE n.id = p_node
    GROUP BY n.id, n.document_version_id, n.source_span_id, n.text_original
  ), FALSE)
$$;
