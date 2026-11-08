ALTER TABLE document_versions
  DROP COLUMN IF EXISTS source_file_sha256,
  DROP COLUMN IF EXISTS source_format;
