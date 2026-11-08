-- G1: document-level effectivity (design docs/thiet-ke-tra-cuu-hieu-luc.md §3, §4, §9).
-- Two axes: effective status (axis A) and verification state (axis B).

-- D10: a REVIEWER confirms effectivity only inside categories granted with can_review.
ALTER TABLE category_acl ADD COLUMN can_review BOOLEAN NOT NULL DEFAULT FALSE;

-- Dates read from the document text by rules; the reviewer confirms them at source
-- review.  ``valid_from``/``valid_to`` keep their meaning (version selection) and are
-- not used for effectivity, so a document is never hidden by its effective date (D9).
ALTER TABLE document_versions
  ADD COLUMN effective_from DATE,
  ADD COLUMN dates_detected JSONB NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN dates_confirmed_by UUID REFERENCES users(id),
  ADD COLUMN dates_confirmed_at TIMESTAMPTZ;

-- Effectivity relations at document or node level in one table.  Proposals (rule,
-- AI, person) stay review_status='draft' and never change axis A (hard rule 3).
ALTER TABLE node_amendments DROP CONSTRAINT IF EXISTS node_amendments_action_check;
ALTER TABLE node_amendments ADD CONSTRAINT node_amendments_action_check
  CHECK (action IN ('modify', 'replace', 'add', 'repeal', 'repeal_partial', 'suspend', 'commence'));
ALTER TABLE node_amendments ALTER COLUMN valid_from DROP NOT NULL;
ALTER TABLE node_amendments
  ADD COLUMN scope TEXT NOT NULL DEFAULT 'node' CHECK (scope IN ('document', 'node')),
  ADD COLUMN source_document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
  ADD COLUMN target_document_id UUID REFERENCES documents(id),
  ADD COLUMN target_number TEXT,
  ADD COLUMN target_doc_type TEXT,
  ADD COLUMN target_issue_date DATE,
  ADD COLUMN target_path TEXT,
  ADD COLUMN target_expression TEXT,
  ADD COLUMN resolution_state TEXT NOT NULL DEFAULT 'resolved'
    CHECK (resolution_state IN ('resolved', 'unresolved', 'ambiguous')),
  ADD COLUMN condition_text TEXT,
  ADD COLUMN proposed_by TEXT NOT NULL DEFAULT 'person'
    CHECK (proposed_by IN ('rule', 'ai', 'person')),
  ADD COLUMN proposer_id UUID REFERENCES users(id),
  ADD COLUMN confidence NUMERIC CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
  ADD COLUMN model_version TEXT,
  ADD COLUMN source_quote TEXT,
  ADD COLUMN source_page INTEGER,
  ADD COLUMN extraction_key TEXT,
  ADD COLUMN review_batch_id UUID,
  ADD COLUMN reviewed_at TIMESTAMPTZ,
  ADD COLUMN review_note TEXT,
  ADD COLUMN superseded_by UUID REFERENCES node_amendments(id);
CREATE UNIQUE INDEX node_amendments_extraction
  ON node_amendments (source_node_id, extraction_key) WHERE extraction_key IS NOT NULL;
CREATE INDEX node_amendments_target_document ON node_amendments (target_document_id);
CREATE INDEX node_amendments_source_document ON node_amendments (source_document_id);
CREATE INDEX node_amendments_unresolved ON node_amendments (target_number)
  WHERE target_document_id IS NULL;

-- Relations that only relate documents (never change effectivity).
ALTER TABLE node_references
  ADD COLUMN reference_kind TEXT NOT NULL DEFAULT 'citation'
    CHECK (reference_kind IN ('basis', 'guidance', 'consolidation', 'citation')),
  ADD COLUMN source_document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
  ADD COLUMN target_document_id UUID REFERENCES documents(id),
  ADD COLUMN target_number TEXT,
  ADD COLUMN source_quote TEXT,
  ADD COLUMN extraction_key TEXT;
CREATE UNIQUE INDEX node_references_extraction
  ON node_references (source_node_id, extraction_key) WHERE extraction_key IS NOT NULL;
CREATE INDEX node_references_target_document ON node_references (target_document_id);
CREATE INDEX node_references_source_document ON node_references (source_document_id);

-- Axis B on both interval tables; the store's data date on the snapshot.
ALTER TABLE effectivity_snapshot_revisions ADD COLUMN data_date DATE;
ALTER TABLE node_effective_intervals
  ADD COLUMN verification_state TEXT NOT NULL DEFAULT 'not_found'
    CHECK (verification_state IN ('verified', 'unverified', 'not_found')),
  ADD COLUMN notes JSONB NOT NULL DEFAULT '[]'::jsonb;

-- Document level; a node only stores exceptions and otherwise inherits this.
-- valid_from = '-infinity' when the start is not known.
CREATE TABLE document_effective_intervals (
  snapshot_revision_id UUID NOT NULL
    REFERENCES effectivity_snapshot_revisions(id) ON DELETE CASCADE,
  document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  valid_from DATE NOT NULL,
  valid_to DATE,
  effective_status TEXT NOT NULL CHECK (effective_status IN (
    'active', 'not_yet_effective', 'modified', 'suspended', 'repealed', 'replaced', 'unknown')),
  verification_state TEXT NOT NULL DEFAULT 'not_found'
    CHECK (verification_state IN ('verified', 'unverified', 'not_found')),
  verification_source TEXT,
  verified_by UUID REFERENCES users(id),
  verified_at TIMESTAMPTZ,
  amendment_chain JSONB NOT NULL DEFAULT '[]'::jsonb,
  notes JSONB NOT NULL DEFAULT '[]'::jsonb,
  PRIMARY KEY (snapshot_revision_id, document_id, valid_from),
  CHECK (valid_to IS NULL OR valid_to > valid_from)
);

-- A person's statement about effectivity: target, result, the period it covers,
-- source, person and time.  Never deleted; superseded or revoked instead.
CREATE TABLE effectivity_attestations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  target_document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  target_node_id UUID REFERENCES document_nodes(id) ON DELETE CASCADE,
  result TEXT NOT NULL CHECK (result IN (
    'active', 'not_yet_effective', 'modified', 'suspended', 'repealed', 'replaced')),
  valid_for_from DATE NOT NULL,
  valid_for_to DATE NOT NULL,
  source_note TEXT NOT NULL CHECK (length(btrim(source_note)) > 0),
  source_document_id UUID REFERENCES documents(id),
  attested_by UUID NOT NULL REFERENCES users(id),
  attested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  status TEXT NOT NULL DEFAULT 'valid' CHECK (status IN ('valid', 'needs_reverify', 'revoked')),
  status_reason TEXT,
  status_changed_at TIMESTAMPTZ,
  superseded_by UUID REFERENCES effectivity_attestations(id),
  CHECK (valid_for_to >= valid_for_from)
);
CREATE INDEX effectivity_attestations_target
  ON effectivity_attestations (target_document_id) WHERE status <> 'revoked';

-- Hard rule 5: an attestation needs re-verification when the store records a new
-- relation touching its target after the attestation was made.
CREATE FUNCTION effectivity_mark_reverify() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.target_document_id IS NULL OR NEW.review_status = 'rejected' THEN
    RETURN NEW;
  END IF;
  IF TG_OP = 'UPDATE'
     AND OLD.target_document_id IS NOT DISTINCT FROM NEW.target_document_id
     AND NOT (OLD.review_status <> 'approved' AND NEW.review_status = 'approved') THEN
    RETURN NEW;
  END IF;
  UPDATE effectivity_attestations
     SET status = 'needs_reverify', status_reason = 'new_relation', status_changed_at = now()
   WHERE status = 'valid'
     AND target_document_id = NEW.target_document_id
     AND attested_at < now();
  RETURN NEW;
END;
$$;
CREATE TRIGGER node_amendments_reverify
  AFTER INSERT OR UPDATE OF target_document_id, review_status ON node_amendments
  FOR EACH ROW EXECUTE FUNCTION effectivity_mark_reverify();
