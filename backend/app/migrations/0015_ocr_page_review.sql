-- OCR pages: diagnostics shown to the reviewer and who confirmed the page text against
-- the scan.  The scan (original PDF) is unchanged; OCR text stays derived data.
ALTER TABLE source_pages ADD COLUMN IF NOT EXISTS ocr_diagnostics JSONB;
ALTER TABLE source_pages ADD COLUMN IF NOT EXISTS reviewed_by UUID REFERENCES users(id);
ALTER TABLE source_pages ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ;
