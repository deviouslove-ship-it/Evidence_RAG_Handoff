DROP TRIGGER IF EXISTS node_amendments_reverify ON node_amendments;
DROP FUNCTION IF EXISTS effectivity_mark_reverify();
DROP TABLE IF EXISTS effectivity_attestations;
DROP TABLE IF EXISTS document_effective_intervals;
ALTER TABLE node_effective_intervals DROP COLUMN IF EXISTS notes,
  DROP COLUMN IF EXISTS verification_state;
ALTER TABLE effectivity_snapshot_revisions DROP COLUMN IF EXISTS data_date;
DROP INDEX IF EXISTS node_references_extraction;
DROP INDEX IF EXISTS node_references_target_document;
DROP INDEX IF EXISTS node_references_source_document;
ALTER TABLE node_references DROP COLUMN IF EXISTS extraction_key,
  DROP COLUMN IF EXISTS source_quote, DROP COLUMN IF EXISTS target_number,
  DROP COLUMN IF EXISTS target_document_id, DROP COLUMN IF EXISTS source_document_id,
  DROP COLUMN IF EXISTS reference_kind;
DROP INDEX IF EXISTS node_amendments_extraction;
DROP INDEX IF EXISTS node_amendments_target_document;
DROP INDEX IF EXISTS node_amendments_source_document;
DROP INDEX IF EXISTS node_amendments_unresolved;
-- Relations that only exist in the G1 model (no date or a new action) cannot be
-- represented by the earlier schema.
UPDATE node_amendments SET superseded_by = NULL;
DELETE FROM node_amendments
 WHERE valid_from IS NULL OR action IN ('repeal_partial', 'commence');
ALTER TABLE node_amendments DROP COLUMN IF EXISTS superseded_by,
  DROP COLUMN IF EXISTS review_note, DROP COLUMN IF EXISTS reviewed_at,
  DROP COLUMN IF EXISTS review_batch_id, DROP COLUMN IF EXISTS extraction_key,
  DROP COLUMN IF EXISTS source_page, DROP COLUMN IF EXISTS source_quote,
  DROP COLUMN IF EXISTS model_version, DROP COLUMN IF EXISTS confidence,
  DROP COLUMN IF EXISTS proposer_id, DROP COLUMN IF EXISTS proposed_by,
  DROP COLUMN IF EXISTS condition_text, DROP COLUMN IF EXISTS resolution_state,
  DROP COLUMN IF EXISTS target_expression, DROP COLUMN IF EXISTS target_path,
  DROP COLUMN IF EXISTS target_issue_date, DROP COLUMN IF EXISTS target_doc_type,
  DROP COLUMN IF EXISTS target_number, DROP COLUMN IF EXISTS target_document_id,
  DROP COLUMN IF EXISTS source_document_id, DROP COLUMN IF EXISTS scope;
ALTER TABLE node_amendments ALTER COLUMN valid_from SET NOT NULL;
ALTER TABLE node_amendments DROP CONSTRAINT IF EXISTS node_amendments_action_check;
ALTER TABLE node_amendments ADD CONSTRAINT node_amendments_action_check
  CHECK (action IN ('modify', 'replace', 'add', 'repeal', 'suspend'));
ALTER TABLE document_versions DROP COLUMN IF EXISTS dates_confirmed_at,
  DROP COLUMN IF EXISTS dates_confirmed_by, DROP COLUMN IF EXISTS dates_detected,
  DROP COLUMN IF EXISTS effective_from;
ALTER TABLE category_acl DROP COLUMN IF EXISTS can_review;
