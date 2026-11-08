-- G5: embedding model changes managed from the Admin Portal.
-- A background job (app process, no script) fills a new embedding index while the
-- active one keeps serving search, then verifies it and switches in one transaction.
-- Index states gain 'paused' and 'failed'.  Nothing here deletes vectors or indexes.
DO $$
DECLARE item RECORD;
BEGIN
  FOR item IN SELECT conname FROM pg_constraint
              WHERE conrelid = 'embedding_indices'::regclass AND contype = 'c'
                AND pg_get_constraintdef(oid) LIKE '%status%'
  LOOP
    EXECUTE format('ALTER TABLE embedding_indices DROP CONSTRAINT %I', item.conname);
  END LOOP;
END $$;
ALTER TABLE embedding_indices ADD CONSTRAINT embedding_indices_status_check
  CHECK (status IN ('building', 'paused', 'failed', 'ready', 'retired'));
ALTER TABLE embedding_indices
  ADD COLUMN last_error TEXT,
  ADD COLUMN verified_at TIMESTAMPTZ,
  ADD COLUMN activated_at TIMESTAMPTZ,
  ADD COLUMN retired_at TIMESTAMPTZ;

CREATE TABLE embedding_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  -- No cascade: a job is history of its index, and indexes are never deleted by the app.
  embedding_index_id UUID NOT NULL REFERENCES embedding_indices(id),
  profile_key TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('rebuild', 'catch_up')),
  status TEXT NOT NULL DEFAULT 'queued'
    CHECK (status IN ('queued', 'running', 'paused', 'failed', 'completed', 'cancelled')),
  phase TEXT NOT NULL DEFAULT 'embedding'
    CHECK (phase IN ('embedding', 'indexing', 'verifying', 'switching', 'done')),
  batch_size INTEGER NOT NULL CHECK (batch_size BETWEEN 1 AND 256),
  total_nodes INTEGER NOT NULL DEFAULT 0,
  done_nodes INTEGER NOT NULL DEFAULT 0,
  embedded_nodes INTEGER NOT NULL DEFAULT 0,
  failed_batches INTEGER NOT NULL DEFAULT 0,
  consecutive_failures INTEGER NOT NULL DEFAULT 0,
  rate_per_minute DOUBLE PRECISION,
  active_seconds DOUBLE PRECISION NOT NULL DEFAULT 0,
  last_error TEXT,
  errors JSONB NOT NULL DEFAULT '[]'::jsonb,
  requested_by UUID REFERENCES users(id) ON DELETE SET NULL,
  worker_id TEXT,
  heartbeat_at TIMESTAMPTZ,
  next_attempt_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ
);
-- One open job per index; a paused or failed job is resumed/retried, not duplicated.
CREATE UNIQUE INDEX embedding_jobs_one_open_per_index ON embedding_jobs (embedding_index_id)
  WHERE status IN ('queued', 'running', 'paused', 'failed');
CREATE INDEX embedding_jobs_queue ON embedding_jobs (created_at) WHERE status = 'queued';
