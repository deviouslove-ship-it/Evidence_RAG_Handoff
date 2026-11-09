# Requirements: PDF Intake, Conversion and OCR with Page Review

> Spec reconstructed from the implemented code on 2026-11-09. This is not a historical Kiro-generated spec. Evidence is cited by repository path.

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

### Requirement 6: Legal tree

#### Acceptance Criteria

1. WHEN text is extracted THE SYSTEM SHALL build a Chapter/Section/Article/Clause/Point tree where recognisable and flag ambiguous cases for review (`documents/tree_parser.py`).
