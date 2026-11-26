**Language / Ngôn ngữ:** [Tiếng Việt](README.md) · English

English counterpart of `evaluation/corpus_public_real/README.md`. The Vietnamese file is the original.

# Public PDF set for technical trials

`manifest.json` records the official source, the file URL, the download time, the size, and the SHA-256 of 12 decrees (Nghị định) from the Government Electronic Information Portal (Cổng Thông tin điện tử Chính phủ). The PDFs in `files/` are used only to try extraction, segmentation, and retrieval. `*.pdf` is ignored by Git and is not part of the app install package.

The status `test_only_unreviewed` means no person has yet verified authenticity, effectivity (hiệu lực), or fitness for the business domain. Do not put these administrative documents (văn bản) into an approved source or into the Gold set. Business documents will be imported separately when the user provides them.

Run `evaluation/scripts/audit_public_pdf_corpus.py` with the backend's Python to recheck the hash, the pages, the text layer, and the segmentation result.

To try the 9 scanned PDFs, set the environment variable `EVIDENCE_OCR_EXECUTABLE` to the absolute path of a separately installed Tesseract, then run the audit script with `--ocr`. OCR is optional. An OCR page always needs review. Run `evaluation/scripts/evaluate_public_pdf_retrieval.py` with the same environment variable to measure candidate retrieval on the 12 files. That result is only a technical test. It does not confirm legal effectivity or the right to publish.
