-- A text match is a review signal, not a uniqueness constraint or source approval.
ALTER TABLE document_versions ADD COLUMN native_text_fingerprint_v1 TEXT
  CHECK (native_text_fingerprint_v1 IS NULL OR native_text_fingerprint_v1 ~ '^[0-9a-f]{64}$');
CREATE INDEX document_versions_native_text_fingerprint_v1
  ON document_versions (native_text_fingerprint_v1)
  WHERE native_text_fingerprint_v1 IS NOT NULL;
