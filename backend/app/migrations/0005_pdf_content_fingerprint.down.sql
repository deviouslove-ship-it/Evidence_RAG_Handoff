DROP INDEX IF EXISTS document_versions_native_text_fingerprint_v1;
ALTER TABLE document_versions DROP COLUMN IF EXISTS native_text_fingerprint_v1;
