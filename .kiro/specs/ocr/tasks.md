# Tasks: PDF Intake, Conversion and OCR

> Spec reconstructed from the implemented code on 2026-11-09. Checkboxes reflect what exists in the repository.

- [x] 1. Format detection, Word/TXT to PDF conversion (`documents/convert.py`, migration `0008`)
- [x] 2. Immutable storage and digest check (`documents/provenance.py`)
- [x] 3. Deduplication by bytes and content (`documents/deduplication.py`, migration `0005`)
- [x] 4. Isolated native extraction (`native_pdf.py`, `pdf_worker.py`, `isolated.py`)
- [x] 5. Tesseract OCR with diagnostics (`documents/ocr.py`)
- [x] 6. Per-page OCR review columns (migration `0015`) and review UI (`DraftReviewPanel.tsx`)
- [x] 7. Re-extraction (`documents/reextract.py`)
- [x] 8. Legal tree parser (`documents/tree_parser.py`)
- [x] 9. Bulk import script (`scripts/import_official_corpus.py`)
- [ ] 10. OCR check in the Tauri desktop shell and TXT sources (reported not verified)
- [ ] 11. Tesseract in `deploy/portable` package (not included)
