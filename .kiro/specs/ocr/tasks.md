# Tasks: PDF Intake, Conversion and OCR

> Initially reconstructed from implemented code on 2026-11-09 and updated against the source on 2026-11-17. Checkboxes reflect source implementation, not release-package acceptance.

- [x] 1. Format detection, Word/TXT to PDF conversion (`documents/convert.py`, migration `0008`)
- [x] 2. Immutable storage and digest check (`documents/provenance.py`)
- [x] 3. Deduplication by bytes and content (`documents/deduplication.py`, migration `0005`)
- [x] 4. Isolated native extraction (`native_pdf.py`, `pdf_worker.py`, `isolated.py`)
- [x] 5. Tesseract OCR with diagnostics (`documents/ocr.py`)
- [x] 6. Per-page OCR review columns (migration `0015`) and review UI (`DraftReviewPanel.tsx`)
- [x] 7. Re-extraction (`documents/reextract.py`)
- [x] 8. Document structure tree parser (`documents/tree_parser.py`)
- [x] 9. Bulk import script (`scripts/import_official_corpus.py`)
- [ ] 10. OCR check in the Tauri desktop shell and TXT sources (reported not verified)
- [ ] 11. Tesseract in `deploy/portable` package (not included)
- [x] 12. USER page-text API, approved-text fast path, one-page local OCR request, ACL/revision checks, cancellation and one-hour expiry (`documents/page_text.py`, `ocr_ai_jobs.py`, migration `0017`)
- [x] 13. Chat intent, page selection, unverified result panel, copy/open/cancel and responsive UI (`pageTextIntent.ts`, `PageTextPanel.tsx`, `EvidenceChat.tsx`)
- [x] 14. Admin OCR proposal, compare/edit/apply into a new draft, model/source fingerprint validation and reviewer separation (`OcrAiPanel.tsx`, `ocr_ai_store.py`)
- [x] 15. Local Ollama vision stage and image probe; worker disabled by default; API image fallback prohibited (`model_registry/runtime.py`, `diagnostics.py`, `portable.ps1`)
- [ ] 16. Build a new Portable ZIP, verify relocated offline execution on a separate path/drive and test on another Windows machine. The existing r4 package is unchanged.

Review evidence for tasks 12–15: `docs/evidence/qwen35-upgrade/REVIEW_FIXES_2026-11-17.md`. Those checks used isolated test databases and a synthetic PDF; they do not satisfy task 16 or broad OCR acceptance.
