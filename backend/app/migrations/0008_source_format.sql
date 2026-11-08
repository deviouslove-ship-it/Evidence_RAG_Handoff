-- Word/TXT sources are rendered to a PDF that the app cites.  Record what the author
-- actually uploaded: its format and its own SHA-256 (the PDF hash stays in
-- original_file_sha256).  Existing rows are PDFs uploaded as-is.
ALTER TABLE document_versions
  ADD COLUMN source_format TEXT NOT NULL DEFAULT 'pdf'
    CHECK (source_format IN ('pdf', 'docx', 'doc', 'txt')),
  ADD COLUMN source_file_sha256 TEXT
    CHECK (source_file_sha256 IS NULL OR source_file_sha256 ~ '^[0-9a-f]{64}$');
