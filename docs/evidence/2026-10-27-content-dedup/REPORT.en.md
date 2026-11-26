**Language / Ngôn ngữ:** [Tiếng Việt](REPORT.md) · English

English counterpart of `docs/evidence/2026-10-27-content-dedup/REPORT.md`. The Vietnamese file is the original.

# Continuing the work: PDFs and content deduplication

## Deduplication rules

1. A PDF file with identical bytes is recognized by SHA-256 before the extractor runs; the unique constraint in PostgreSQL still protects a concurrent import.
2. For a document whose every page has a readable original text layer, the system builds a SHA-256 fingerprint from Unicode NFC-normalized text and whitespace. Vietnamese diacritics, upper and lower case, and punctuation are kept; the text of the pages is joined with spaces. A different-byte copy with the same fingerprint is reported as a **possible duplicate** (**có thể trùng**), stored separately in draft status, and given a check task.
3. The candidate list on the review screen returns only a draft or a copy pending review, or a document the viewer is allowed to access. Two concurrent imports of the same content are serialized during the check. They are not merged, deleted, or approved automatically, because the signature, the images, the source, and the legal version may differ even when the text layer is the same.
4. A scanned page, OCR, or a text layer that does not meet the quality bar is not given a content fingerprint; the file SHA-256 is still checked. This algorithm does not yet find a copy that is only partly similar, that changes a few words, that adds a blank page, that changes the page number or header in the text layer, or that differs because of OCR. A result that finds no duplicate does not prove that two administrative documents (văn bản) are different.

The new migration only adds columns and indexes; it does not infer a fingerprint for old data. None of the 12 current versions has a content fingerprint yet; when an editor chooses **Re-extract the original PDF** (**Trích xuất lại PDF gốc**), the system computes the fingerprint if every page meets the conditions. A scanned document still needs OCR and a separate check. Rolling the migration back keeps the document records but deletes the derived fingerprint.

## Extraction and source review

- A passage is matched by whitespace, but the exact verbatim slice of a single PDF page is what is stored. An ambiguous match, or a passage that does not lie entirely on one page, is rejected, and a review task is created instead of inventing a span.
- Numbered headings such as `Chương II` and `Mục 1` are distinguished from ordinary words such as "program" ("Chương trình") and "objective" ("Mục tiêu").
- An editor can re-extract a draft or a copy pending review from the original PDF after its hash has been checked. Only a page that is still missing is restored, node IDs are preserved, page text that differs from the extraction result is not overwritten, an approved copy is not processed, and nothing is approved automatically. The action is written to the audit log, and a re-verification task is created.

## Test results

- [Test suite](verification/summary.json): 12/12 items passed; 161 backend tests, 37 frontend tests, and 17 [Rust](desktop-tests.txt) tests. One deprecation warning from a test dependency still appears.
- [12 public-source PDFs](public-pdf-draft-ingest.json) were imported into a temporary schema and store: 135 pages, 797 draft nodes, 791 nodes with a unique verbatim span, and 6 nodes that could not be attached to a page; no draft node leaked into retrieval. A passage that has a span has not thereby been verified.
- A [simulation](reextract-simulation.json) from one source PDF in a temporary schema: restored 18 pages, attached 190 nodes, warned of a different-byte copy with the same text layer, blocked self-approval, tried approval with another account, ran a lookup, checked the PDF hash, and revoked permission. The approval is test data only, not a real approval or a real legal conclusion.
- A [read-only check](legacy-readonly-preview.json) of three old copies: 351 has 190/190 nodes that can be attached; 355 has 102/106 and 385 has 348/352. These three copies were not changed automatically. Old nodes are not rebuilt automatically, so that IDs and links are not lost; eight old nodes that are still unattached still need to be handled.
- The migration was applied after the [backup](backup.json); a [restore into a temporary database](backup-restore-test.json) was tried and all 12 versions were counted. This is not yet a full test of every restored piece of data. The [down/up trial](migration-down-up.json) was performed on a separate schema.
- The backend and the web respond, and the new routes appear in OpenAPI ([smoke trial](live-smoke.json)). The desktop release was built and had a window that responded within 5 seconds ([build](desktop-build.json), [launch trial](desktop-launch-smoke.json)); full interactive testing on the desktop, or with a real AI configuration, has not been done.

## Remaining work

There is not yet a complete interface to edit or split a node that extends across several pages. Some old copies therefore still cannot be approved, even after re-extraction; the span-check barrier is not bypassed. An editing tool with PDF cross-check still has to be built, and cross-page cases, OCR, and version changes still have to be tested, before a domain evaluation on the Gold set and a real model.
