**Language / Ngôn ngữ:** [Tiếng Việt](2026-10-22-public-pdf-report.md) · English

English counterpart of `docs/evidence/2026-10-22-public-pdf-report.md`. The Vietnamese file is the original.

# Public-PDF testing and app progress — 2026-10-22

Source: [Government administrative-document system (hệ thống văn bản Chính phủ)](https://vanban.chinhphu.vn/he-thong-van-ban?classid=1&mode=1&typegroupid=4). The [manifest](../../evaluation/corpus_public_real/manifest.json) records 12 detail URLs, PDF URLs, download dates, hashes, and sizes. The PDFs are separate test data: they are not in the app package, and they are not part of Gold or of an approved source.

| Measurement | Result |
|---|---:|
| PDFs / total bytes / pages | 12 / 26,319,803 / 135 |
| Native text | 3 PDFs, 70 pages, 149,514 characters |
| Scans with no text layer | 9 PDFs, 65 pages |
| Experimental local OCR | 65/65 pages yielded text, 113,860 characters; 65/65 pages `needs_review` |
| Parser after the fix | 1,094 technical-trial nodes across 12 PDFs |
| Candidate retrieval | 15/15 cases: 12 document numbers (số hiệu), 3 Articles (Điều); 12/15 before the fix |
| CURATOR API `/documents/preview` | 12/12 PDFs returned the correct hash and 135 pages; with OCR off, 65 pages `needs_ocr` |
| API with OCR enabled separately | PDF 381: 3/3 pages `local_ocr`, 3/3 `needs_review`, correct hash |
| Draft import into dev PostgreSQL, native text | 12/12 `draft` copies, 135 pages, 648 nodes, 77 review tasks; 0 nodes exposed through ACL |
| Verbatim-matching character spans | 174/648 native nodes; no quads/bbox yet |

Core only added pypdfium2 (6,143,401 bytes installed in the test environment). Pillow serves optional OCR (14,912,867 bytes); Tesseract, already present on the test machine, is a runtime outside the Core package (190,325,373 bytes) and has not been packaged or approved for deployment. The separate dev PostgreSQL/pgvector occupies 163,383,005 bytes of programs, 86,468,241 bytes of data cluster, and 384,620,317 bytes of ZIP cache; these amounts are not counted in Core. RAG-Anything was not installed. These are the sizes of **installed components**, not a clean-install measurement of the whole app.

[RAG-Anything](https://github.com/HKUDS/RAG-Anything) aims at multimodal retrieval, and its [declared core dependencies](https://github.com/HKUDS/RAG-Anything/blob/main/pyproject.toml) include LightRAG, MinerU, and Hugging Face Hub. The current test set is PDFs of regulatory administrative documents (văn bản pháp quy), and limiting size is a priority, so there is no evidence that the whole framework needs to be pulled into Core. The framework's real install size has not been measured, so no hypothetical savings figure is assigned.

Code changes: PDF extraction with resource management and a page limit; OCR runs only on pages that have no text, and only when execution is explicitly configured; OCR results require review, and there is no fake native bbox; the parser keeps the continuation of a point (Điểm) and lowers confidence for OCR; retrieval considers the document number (số hiệu), the title, and the Article (Điều) before cutting the candidate set. The preview API limits bytes and pages and requires CURATOR. The PDF import API stores the original by hash at `EVIDENCE_DOCUMENT_STORE_ROOT` (an absolute path configured by the deployment), and stores source metadata, pages, spans, and nodes in PostgreSQL under `draft` status; it creates a review task and blocks a duplicate hash. CURATOR/REVIEWER can list drafts and read the PDF bytes back after the hash check. The 12-PDF test used a separate schema and store and then deleted them; it did not import into the app's approved sources.

Evidence: [PDF audit](2026-10-22-public-pdf-ocr-audit.json), [retrieval](2026-10-22-public-pdf-retrieval.json), [API smoke](2026-10-22-public-pdf-api-smoke.json), [API OCR](2026-10-22-public-pdf-api-ocr-smoke.json), [12-PDF draft import](2026-10-22-public-pdf-draft-ingest.json), [dev PostgreSQL](2026-10-22-postgres-dev.json), [footprint](2026-10-22-public-pdf-footprint.json), [12 checks](2026-10-22-public-pdf-verification/summary.json). Backend 82 passed, 0 skipped; frontend 8 passed and the build succeeded. Still missing: a production identity provider, a source-review and source-approval interface, the USER citation viewer, quads/bbox, malware scanning, OCR-accuracy QA, backup/restore, and acceptance of legal answers. The SQL test used a real dev database but does not prove the app is ready for release.
