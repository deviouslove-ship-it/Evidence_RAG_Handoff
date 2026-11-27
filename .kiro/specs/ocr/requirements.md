# Requirements: PDF Intake, Conversion and OCR with Page Review

**Language / Ngôn ngữ:** [Tiếng Việt](../../../docs/vi/kiro/specs/ocr.vi.md) · English

> Initially reconstructed from implemented code on 2026-11-09 and updated against the source on 2026-11-17. This is not a historical Kiro-generated spec. Evidence is cited by repository path.

## Introduction

Documents enter as PDF, Word (`.docx`, `.doc`) or TXT. Scanned pages are read by OCR, and no OCR text becomes evidence until a reviewer has compared each page with the scan.

## Requirements

### Requirement 1: Intake validation

#### Acceptance Criteria

1. WHEN a file is uploaded THE SYSTEM SHALL detect its format from the bytes (extension only breaks ties for plain text), validate size and PDF magic, and compute SHA-256 (`documents/convert.py::detect_format`, `documents/provenance.py`).
2. IF the bytes are identical to an existing file THEN THE SYSTEM SHALL block the upload; IF only the text content duplicates THEN THE SYSTEM SHALL warn (`documents/deduplication.py`).
3. IF a `.doc` file is really HTML or RTF, or the text is empty, or TXT encoding is unsupported THEN THE SYSTEM SHALL reject it with a coded error.

### Requirement 2: Word and TXT conversion

#### Acceptance Criteria

1. WHEN a Word or TXT file is accepted THE SYSTEM SHALL render a deterministic A4 PDF with a text layer, so that one citation path serves all formats (`convert.py::convert_to_pdf`, `render_pdf`).
2. THE SYSTEM SHALL keep the original file with its own hash (`document_versions.source_format`, `source_file_sha256`; migration `0008_source_format.sql`).
3. IF a Word file contains only images THEN THE SYSTEM SHALL NOT OCR it as a scanned PDF.

### Requirement 3: Native text and OCR

#### Acceptance Criteria

1. THE SYSTEM SHALL extract text and character boxes with pypdfium2 in an isolated child process (`native_pdf.py`, `pdf_worker.py`, `isolated.py`).
2. WHEN a page has no usable text or its text layer looks defective (`diagnose_text_quality`) AND OCR is configured THE SYSTEM SHALL run Tesseract (`vie+eng`) on that page (`documents/ocr.py::TesseractOcr`).
3. WHEN OCR runs THE SYSTEM SHALL store diagnostics: confidence, ink share, rotation, suspect tokens, misread point markers (`ocr.py::diagnose`, migration `0015_ocr_page_review.sql`).
4. IF OCR is not configured or fails THEN THE SYSTEM SHALL keep the page out of verified evidence and show a coded error (`OcrError`).
5. THE SYSTEM SHALL describe OCR coordinates to page level only.

### Requirement 4: Page-by-page human review

#### Acceptance Criteria

1. WHEN a reviewer opens a draft with OCR pages THE SYSTEM SHALL show each page's OCR text and warnings beside the scan.
2. THE SYSTEM SHALL require the reviewer to confirm each OCR page (`source_pages.reviewed_by`, `reviewed_at`) before approval.
3. WHEN a curator edits OCR text of an approved version THE SYSTEM SHALL create a new draft and require re-confirmation of each edited page.
4. THE SYSTEM SHALL keep OCR text before and after an edit.

### Requirement 5: Re-extraction

#### Acceptance Criteria

1. WHEN a permitted curator requests re-extraction THE SYSTEM SHALL re-run extraction and OCR from the stored source and return the result to draft (`POST /api/v1/admin/documents/drafts/{version_id}/reextract`, `documents/reextract.py`).

### Requirement 6: Document structure tree

#### Acceptance Criteria

1. WHEN text is extracted THE SYSTEM SHALL build a Chapter/Section/Article/Clause/Point tree where recognisable and flag ambiguous cases for review (`documents/tree_parser.py`).

### Requirement 7: USER requests text for a specific PDF page

1. WHEN an authorized USER asks for a specific page of a selected document THE SYSTEM SHALL resolve the document from the selected chat context or an explicit title/number and validate the requested PDF page against the current source version (`documents/page_text.py`, `api/v1/page_text.py`).
2. IF approved/extracted page text is usable and the user has not explicitly requested an image reread THEN THE SYSTEM SHALL return that page text without calling a model.
3. IF page text is missing/unusable or an image reread is explicit THEN THE SYSTEM SHALL render and send only the requested PDF page to the local `ocr` stage; it SHALL NOT send the whole PDF, other page images, or use an external API image fallback (`documents/ocr_ai.py`, `ocr_ai_jobs.py`, `model_registry/runtime.py`).
4. THE SYSTEM SHALL re-check ACL, document/version revision, PDF hash and page-text hash while processing and before returning a ready result. A changed source SHALL invalidate the candidate.
5. THE SYSTEM SHALL label vision output as unverified, preserve warnings/unreadable regions, expose cancellation and an original-page link, expire temporary results after one hour, and SHALL NOT create a verified citation, modify source text or create vectors.

### Requirement 8: Admin OCR AI proposal and review

1. WHEN a permitted CURATOR requests OCR AI for a draft page THE SYSTEM SHALL create an idempotent proposal bound to the document version/page and a configuration fingerprint; only an approved, tested Ollama vision profile assigned to `ocr` may process the image.
2. IF `EVIDENCE_OCR_AI_ENABLED` is false or absent THEN THE SYSTEM SHALL reject new image-reading tasks with a coded disabled response; stored page text remains available.
3. WHEN the CURATOR compares/edits and applies a current proposal THE SYSTEM SHALL create a new draft version and audit record while preserving the previously approved version. A different REVIEWER remains responsible for page confirmation and approval.
4. IF the source revision, model/profile revision or prompt fingerprint changes before apply THEN THE SYSTEM SHALL mark the proposal stale and reject the apply operation.
