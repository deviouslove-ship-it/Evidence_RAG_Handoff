DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM node_amendments WHERE proposed_by = 'conflict_review'
  ) THEN
    RAISE EXCEPTION 'Cannot downgrade 0018_legal_hierarchy_and_conflict_reviews: conflict_review amendment proposals exist';
  END IF;
END
$$;

DROP TABLE IF EXISTS conflict_findings;
DROP TABLE IF EXISTS conflict_review_runs;
DROP TABLE IF EXISTS legal_authority_rules;

ALTER TABLE node_amendments DROP CONSTRAINT IF EXISTS node_amendments_proposed_by_check;
ALTER TABLE node_amendments
  ADD CONSTRAINT node_amendments_proposed_by_check
  CHECK (proposed_by IN ('rule', 'ai', 'person'));
