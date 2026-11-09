-- Refuse a downgrade that would lose review history or republish suspended sources.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM documents WHERE suspended_at IS NOT NULL)
     OR EXISTS (SELECT 1 FROM document_versions
                WHERE based_on_version_id IS NOT NULL OR retired_at IS NOT NULL
                   OR admin_metadata IS NOT NULL)
     OR EXISTS (SELECT 1 FROM document_ocr_edits) THEN
    RAISE EXCEPTION 'Document management is in use; downgrade requires a reviewed data migration';
  END IF;
END;
$$;

CREATE OR REPLACE VIEW authorized_nodes AS
SELECT DISTINCT n.id, n.document_id, n.document_version_id, n.parent_id,
       n.node_type, n.label_original, n.path, n.text_original, n.text_indexed,
       n.text_normalized, n.text_folded, n.page_start, n.page_end, n.source_span_id,
       n.parse_confidence, n.review_status, n.node_effective_from, n.node_effective_to,
       n.applicability_id, n.created_at
FROM document_nodes n
JOIN document_versions dv ON dv.id = n.document_version_id AND dv.review_status = 'approved'
JOIN documents d ON d.id = n.document_id AND d.deleted_at IS NULL
JOIN document_categories dc ON dc.document_id = d.id
JOIN authorized_categories ac ON ac.category_id = dc.category_id
WHERE current_setting('app.user_id', true) <> ''
  AND ac.user_id = current_setting('app.user_id', true)::uuid
  AND n.review_status = 'approved'
UNION
SELECT DISTINCT n.id, n.document_id, n.document_version_id, n.parent_id,
       n.node_type, n.label_original, n.path, n.text_original, n.text_indexed,
       n.text_normalized, n.text_folded, n.page_start, n.page_end, n.source_span_id,
       n.parse_confidence, n.review_status, n.node_effective_from, n.node_effective_to,
       n.applicability_id, n.created_at
FROM document_nodes n
JOIN document_versions dv ON dv.id = n.document_version_id AND dv.review_status = 'approved'
JOIN documents d ON d.id = n.document_id AND d.deleted_at IS NULL
JOIN document_acl da ON da.document_id = d.id
JOIN users u ON u.id = da.user_id AND u.disabled_at IS NULL
WHERE da.can_query
  AND da.user_id = current_setting('app.user_id', true)::uuid
  AND n.review_status = 'approved';

DROP TRIGGER document_lookup_version_delete ON document_versions;
DROP TRIGGER document_lookup_version_insert ON document_versions;
DROP TRIGGER document_lookup_version_update ON document_versions;
DROP TRIGGER document_lookup_document_change ON documents;
DROP FUNCTION bump_document_lookup_revision();
DROP TABLE document_lookup_revision;
DROP INDEX audit_events_target;
DROP TABLE document_ocr_edits;
DROP INDEX document_versions_unique_intake_sha;
ALTER TABLE document_versions
  DROP COLUMN admin_metadata,
  DROP COLUMN retired_at,
  DROP COLUMN based_on_version_id,
  ADD UNIQUE (original_file_sha256);
ALTER TABLE documents DROP COLUMN suspended_at;
