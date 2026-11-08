-- Local identity, revocable sessions and the review/approval trail used by the Admin Portal.

ALTER TABLE users
  ADD COLUMN password_hash TEXT,
  ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT TRUE,
  ADD COLUMN failed_login_count INTEGER NOT NULL DEFAULT 0 CHECK (failed_login_count >= 0),
  ADD COLUMN locked_until TIMESTAMPTZ,
  ADD COLUMN last_login_at TIMESTAMPTZ,
  ADD COLUMN password_changed_at TIMESTAMPTZ;

INSERT INTO roles (code, name) VALUES
  ('USER', 'Người dùng tra cứu'),
  ('CURATOR', 'Biên tập nguồn'),
  ('REVIEWER', 'Người duyệt nguồn'),
  ('SYS_ADMIN', 'Quản trị hệ thống'),
  ('AUDITOR', 'Kiểm toán')
ON CONFLICT (code) DO NOTHING;

-- Opaque bearer tokens are stored only as SHA-256 digests so a database read cannot replay them.
CREATE TABLE auth_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE CHECK (token_hash ~ '^[0-9a-f]{64}$'),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  revoked_at TIMESTAMPTZ,
  client_kind TEXT NOT NULL DEFAULT 'web'
);
CREATE INDEX auth_sessions_user ON auth_sessions(user_id) WHERE revoked_at IS NULL;

ALTER TABLE document_versions
  ADD COLUMN submitted_by UUID REFERENCES users(id),
  ADD COLUMN reviewed_by UUID REFERENCES users(id),
  ADD COLUMN reviewed_at TIMESTAMPTZ,
  ADD COLUMN review_note TEXT;

ALTER TABLE curator_review_tasks
  ADD COLUMN resolved_by UUID REFERENCES users(id),
  ADD COLUMN resolved_at TIMESTAMPTZ,
  ADD COLUMN resolution_note TEXT;

ALTER TABLE providers
  ADD COLUMN display_name TEXT,
  ADD COLUMN approved_by UUID REFERENCES users(id),
  ADD COLUMN approved_at TIMESTAMPTZ;
