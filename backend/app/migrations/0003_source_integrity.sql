-- Canonical extracted page text is separate from derived node spans.
ALTER TABLE source_pages ADD COLUMN text_original TEXT;
ALTER TABLE source_pages ADD COLUMN extraction_error TEXT;
CREATE UNIQUE INDEX users_username_casefold ON users (lower(username));
CREATE INDEX auth_sessions_expiry ON auth_sessions (expires_at);
CREATE SEQUENCE audit_event_order_seq;
ALTER TABLE audit_events ADD COLUMN event_order BIGINT;
WITH ordered AS (
  SELECT id, row_number() OVER (ORDER BY occurred_at, id) AS position FROM audit_events
)
UPDATE audit_events a SET event_order = o.position FROM ordered o WHERE a.id = o.id;
SELECT setval('audit_event_order_seq', COALESCE((SELECT max(event_order) FROM audit_events), 0) + 1, false);
ALTER TABLE audit_events ALTER COLUMN event_order SET DEFAULT nextval('audit_event_order_seq');
ALTER TABLE audit_events ALTER COLUMN event_order SET NOT NULL;
CREATE UNIQUE INDEX audit_events_event_order ON audit_events (event_order);

-- Legacy approvals did not validate spans against canonical page text. Re-open
-- them for review rather than inferring provenance from derived node strings.
INSERT INTO curator_review_tasks (document_version_id, reason, risk)
SELECT dv.id, 'source_revalidation_required', 'high'
FROM document_versions dv
WHERE dv.review_status = 'approved' AND EXISTS (
  SELECT 1 FROM source_pages sp
  WHERE sp.document_version_id = dv.id AND sp.text_original IS NULL
);
UPDATE source_provenance SET verified_at = NULL
WHERE document_version_id IN (
  SELECT dv.id FROM document_versions dv
  WHERE dv.review_status = 'approved' AND EXISTS (
    SELECT 1 FROM source_pages sp
    WHERE sp.document_version_id = dv.id AND sp.text_original IS NULL
  )
);
UPDATE document_nodes SET review_status = 'draft'
WHERE document_version_id IN (
  SELECT dv.id FROM document_versions dv
  WHERE dv.review_status = 'approved' AND EXISTS (
    SELECT 1 FROM source_pages sp
    WHERE sp.document_version_id = dv.id AND sp.text_original IS NULL
  )
);
UPDATE document_versions dv SET review_status = 'pending_review',
  source_review_revision = source_review_revision + 1
WHERE dv.review_status = 'approved' AND EXISTS (
  SELECT 1 FROM source_pages sp
  WHERE sp.document_version_id = dv.id AND sp.text_original IS NULL
);

CREATE OR REPLACE VIEW authorized_nodes AS
SELECT DISTINCT n.*
FROM document_nodes n
JOIN document_versions dv ON dv.id = n.document_version_id AND dv.review_status = 'approved'
JOIN documents d ON d.id = n.document_id AND d.deleted_at IS NULL
JOIN document_categories dc ON dc.document_id = d.id
JOIN authorized_categories ac ON ac.category_id = dc.category_id
WHERE current_setting('app.user_id', true) <> ''
  AND ac.user_id = current_setting('app.user_id', true)::uuid
  AND n.review_status = 'approved'
UNION
SELECT DISTINCT n.*
FROM document_nodes n
JOIN document_versions dv ON dv.id = n.document_version_id AND dv.review_status = 'approved'
JOIN documents d ON d.id = n.document_id AND d.deleted_at IS NULL
JOIN document_acl da ON da.document_id = d.id
JOIN users u ON u.id = da.user_id AND u.disabled_at IS NULL
WHERE da.can_query
  AND da.user_id = current_setting('app.user_id', true)::uuid
  AND n.review_status = 'approved';
