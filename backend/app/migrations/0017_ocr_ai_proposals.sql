-- Stage-specific OCR timeout (up to 300s for stage='ocr') and unified OCR AI proposal queue.
ALTER TABLE stage_policies DROP CONSTRAINT IF EXISTS stage_policies_timeout_seconds_check;
ALTER TABLE stage_policies ADD CONSTRAINT stage_policies_timeout_seconds_check
  CHECK (timeout_seconds IS NULL OR (timeout_seconds > 0 AND (
    (stage = 'ocr' AND timeout_seconds <= 300)
    OR (stage <> 'ocr' AND timeout_seconds <= 30)
  )));

CREATE TABLE document_ocr_ai_proposals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  purpose TEXT NOT NULL CHECK (purpose IN ('user_page_text', 'admin_correction')),
  document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  version_id UUID NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
  page_number INTEGER NOT NULL CHECK (page_number > 0),
  source_review_revision INTEGER NOT NULL,
  pdf_sha256 TEXT NOT NULL,
  page_text_sha256 TEXT NOT NULL,
  image_sha256 TEXT,
  profile_id TEXT,
  profile_revision TEXT,
  model_digest TEXT,
  prompt_version TEXT NOT NULL,
  render_params JSONB NOT NULL DEFAULT '{}'::jsonb,
  request_id UUID NOT NULL,
  requested_by UUID NOT NULL REFERENCES users(id),
  requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ,
  status TEXT NOT NULL CHECK (status IN (
    'queued', 'running', 'ready', 'applied', 'rejected', 'failed', 'cancelled', 'stale'
  )),
  attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0 AND attempts <= 1),
  lease_token TEXT,
  lease_expires_at TIMESTAMPTZ,
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  candidate_json JSONB,
  candidate_text TEXT,
  error_code TEXT,
  applied_version_id UUID REFERENCES document_versions(id) ON DELETE SET NULL,
  decided_by UUID REFERENCES users(id),
  decided_at TIMESTAMPTZ,
  note TEXT,
  UNIQUE (requested_by, request_id)
);

CREATE UNIQUE INDEX document_ocr_ai_proposals_active_dedup
  ON document_ocr_ai_proposals (
    purpose, requested_by, document_id, version_id, page_number,
    source_review_revision, pdf_sha256, page_text_sha256
  )
  WHERE status IN ('queued', 'running', 'ready');

CREATE INDEX document_ocr_ai_proposals_queue_idx
  ON document_ocr_ai_proposals (status, requested_at ASC)
  WHERE status IN ('queued', 'running');

CREATE INDEX document_ocr_ai_proposals_version_page_idx
  ON document_ocr_ai_proposals (version_id, page_number, requested_at DESC);
