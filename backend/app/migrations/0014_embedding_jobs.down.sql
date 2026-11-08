DROP TABLE IF EXISTS embedding_jobs;
-- The earlier schema knows only building/ready/retired; paused and failed indexes go
-- back to 'building' (their vectors stay, and the build script can resume them).
ALTER TABLE embedding_indices DROP CONSTRAINT IF EXISTS embedding_indices_status_check;
UPDATE embedding_indices SET status = 'building' WHERE status IN ('paused', 'failed');
ALTER TABLE embedding_indices ADD CONSTRAINT embedding_indices_status_check
  CHECK (status IN ('building', 'ready', 'retired'));
ALTER TABLE embedding_indices DROP COLUMN IF EXISTS last_error,
  DROP COLUMN IF EXISTS verified_at, DROP COLUMN IF EXISTS activated_at,
  DROP COLUMN IF EXISTS retired_at;
