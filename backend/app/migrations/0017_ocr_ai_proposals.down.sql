DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM document_ocr_ai_proposals
    WHERE status = 'applied' OR applied_version_id IS NOT NULL
  ) THEN
    RAISE EXCEPTION 'Cannot downgrade 0017_ocr_ai_proposals: applied OCR AI proposals exist';
  END IF;
END
$$;

DROP TABLE IF EXISTS document_ocr_ai_proposals;
DELETE FROM stage_policies WHERE stage = 'ocr' AND timeout_seconds > 30;
ALTER TABLE stage_policies DROP CONSTRAINT IF EXISTS stage_policies_timeout_seconds_check;
ALTER TABLE stage_policies ADD CONSTRAINT stage_policies_timeout_seconds_check
  CHECK (timeout_seconds IS NULL OR (timeout_seconds > 0 AND timeout_seconds <= 30));
