ALTER TABLE providers
  DROP COLUMN IF EXISTS approved_at,
  DROP COLUMN IF EXISTS approved_by,
  DROP COLUMN IF EXISTS display_name;
ALTER TABLE curator_review_tasks
  DROP COLUMN IF EXISTS resolution_note,
  DROP COLUMN IF EXISTS resolved_at,
  DROP COLUMN IF EXISTS resolved_by;
ALTER TABLE document_versions
  DROP COLUMN IF EXISTS review_note,
  DROP COLUMN IF EXISTS reviewed_at,
  DROP COLUMN IF EXISTS reviewed_by,
  DROP COLUMN IF EXISTS submitted_by;
DROP TABLE IF EXISTS auth_sessions;
ALTER TABLE users
  DROP COLUMN IF EXISTS password_changed_at,
  DROP COLUMN IF EXISTS last_login_at,
  DROP COLUMN IF EXISTS locked_until,
  DROP COLUMN IF EXISTS failed_login_count,
  DROP COLUMN IF EXISTS must_change_password,
  DROP COLUMN IF EXISTS password_hash;
