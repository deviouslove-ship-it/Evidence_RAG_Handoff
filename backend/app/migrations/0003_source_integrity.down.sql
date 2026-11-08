-- Re-opened legacy approvals stay pending; rollback never auto-approves content.
DROP INDEX IF EXISTS auth_sessions_expiry;
DROP INDEX IF EXISTS users_username_casefold;
ALTER TABLE audit_events DROP COLUMN event_order;
DROP SEQUENCE IF EXISTS audit_event_order_seq;
ALTER TABLE source_pages DROP COLUMN extraction_error;
ALTER TABLE source_pages DROP COLUMN text_original;
-- The disabled-user ACL fix is intentionally retained on rollback.
