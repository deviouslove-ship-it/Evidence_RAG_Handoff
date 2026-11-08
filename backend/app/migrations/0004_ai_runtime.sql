-- Remote AI requires an explicit per-user grant in addition to source policy.
ALTER TABLE users ADD COLUMN remote_ai_allowed BOOLEAN NOT NULL DEFAULT FALSE;

-- Earlier profile creation implicitly approved providers without a runtime check.
-- Require an explicit admin approval and a fresh probe before using those entries.
UPDATE providers SET approved = FALSE, approved_by = NULL, approved_at = NULL;
UPDATE model_profiles SET health = 'unknown';
UPDATE model_profiles SET secret_ref = NULL
WHERE secret_ref IS NOT NULL AND secret_ref !~ '^env:[A-Za-z_][A-Za-z0-9_]{0,127}$';
