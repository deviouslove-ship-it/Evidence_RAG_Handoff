-- A managed correction preserves the original bytes and gets its own source review.
ALTER TABLE documents ADD COLUMN suspended_at TIMESTAMPTZ;
ALTER TABLE document_versions
  ADD COLUMN based_on_version_id UUID REFERENCES document_versions(id),
  ADD COLUMN retired_at TIMESTAMPTZ,
  ADD COLUMN admin_metadata JSONB;
ALTER TABLE document_versions DROP CONSTRAINT document_versions_original_file_sha256_key;
CREATE UNIQUE INDEX document_versions_unique_intake_sha
  ON document_versions (original_file_sha256) WHERE based_on_version_id IS NULL;

CREATE TABLE document_ocr_edits (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_version_id UUID NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
  page_number INTEGER NOT NULL CHECK (page_number > 0),
  previous_text TEXT,
  corrected_text TEXT NOT NULL,
  edited_by UUID NOT NULL REFERENCES users(id),
  edited_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX document_ocr_edits_version ON document_ocr_edits (document_version_id);
CREATE INDEX audit_events_target ON audit_events (target_type, target_id, occurred_at DESC)
  WHERE action LIKE 'document.%';

-- PostgreSQL is the shared invalidation source for caches in all server workers.
CREATE TABLE document_lookup_revision (
  id BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (id),
  revision BIGINT NOT NULL DEFAULT 0
);
INSERT INTO document_lookup_revision DEFAULT VALUES;
CREATE FUNCTION bump_document_lookup_revision() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  UPDATE document_lookup_revision SET revision = revision + 1 WHERE id;
  RETURN NULL;
END;
$$;
CREATE TRIGGER document_lookup_document_change
  AFTER UPDATE OF deleted_at, suspended_at, title, doc_type, document_number, issuing_body
  ON documents FOR EACH ROW
  WHEN (OLD IS DISTINCT FROM NEW)
  EXECUTE FUNCTION bump_document_lookup_revision();
CREATE TRIGGER document_lookup_version_update
  AFTER UPDATE ON document_versions FOR EACH ROW
  WHEN ((OLD.review_status = 'approved' OR NEW.review_status = 'approved')
        AND (OLD.review_status, OLD.retired_at, OLD.source_review_revision,
             OLD.publication_date, OLD.effective_from, OLD.valid_from, OLD.valid_to)
            IS DISTINCT FROM
            (NEW.review_status, NEW.retired_at, NEW.source_review_revision,
             NEW.publication_date, NEW.effective_from, NEW.valid_from, NEW.valid_to))
  EXECUTE FUNCTION bump_document_lookup_revision();
CREATE TRIGGER document_lookup_version_insert
  AFTER INSERT ON document_versions FOR EACH ROW WHEN (NEW.review_status = 'approved')
  EXECUTE FUNCTION bump_document_lookup_revision();
CREATE TRIGGER document_lookup_version_delete
  AFTER DELETE ON document_versions FOR EACH ROW WHEN (OLD.review_status = 'approved')
  EXECUTE FUNCTION bump_document_lookup_revision();

CREATE OR REPLACE VIEW authorized_nodes AS
SELECT DISTINCT n.id, n.document_id, n.document_version_id, n.parent_id,
       n.node_type, n.label_original, n.path, n.text_original, n.text_indexed,
       n.text_normalized, n.text_folded, n.page_start, n.page_end, n.source_span_id,
       n.parse_confidence, n.review_status, n.node_effective_from, n.node_effective_to,
       n.applicability_id, n.created_at
FROM document_nodes n
JOIN document_versions dv ON dv.id = n.document_version_id AND dv.review_status = 'approved'
  AND dv.retired_at IS NULL
JOIN documents d ON d.id = n.document_id AND d.deleted_at IS NULL
  AND d.suspended_at IS NULL
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
  AND dv.retired_at IS NULL
JOIN documents d ON d.id = n.document_id AND d.deleted_at IS NULL
  AND d.suspended_at IS NULL
JOIN document_acl da ON da.document_id = d.id
JOIN users u ON u.id = da.user_id AND u.disabled_at IS NULL
WHERE da.can_query
  AND da.user_id = current_setting('app.user_id', true)::uuid
  AND n.review_status = 'approved';
