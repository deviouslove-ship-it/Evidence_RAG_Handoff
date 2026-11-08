from pathlib import Path

import pytest

from app.documents.native_pdf import extract_native_pdf
from app.documents.ocr import OcrError, TesseractOcr


def _blank_pdf(path: Path) -> None:
    pdfium = pytest.importorskip("pypdfium2")
    document = pdfium.PdfDocument.new()
    page = document.new_page(595, 842)
    page.close()
    document.save(path)
    document.close()


def test_blank_page_requires_ocr_without_optional_engine(tmp_path: Path) -> None:
    path = tmp_path / "blank.pdf"
    _blank_pdf(path)
    pages, _ = extract_native_pdf(path)
    assert len(pages) == 1
    assert pages[0].text_quality == "needs_ocr"
    assert pages[0].text == ""


def test_ocr_result_requires_review_and_has_no_native_character_boxes(tmp_path: Path) -> None:
    pytest.importorskip("PIL")
    path = tmp_path / "blank.pdf"
    _blank_pdf(path)

    class FakeOcr:
        def recognize_png(self, image: bytes) -> str:
            assert image.startswith(b"\x89PNG\r\n\x1a\n")
            return "Điều 1. Nội dung OCR chưa được duyệt"

    pages, _ = extract_native_pdf(path, ocr_engine=FakeOcr())
    assert pages[0].extraction_method == "local_ocr"
    assert pages[0].text_quality == "needs_review"
    assert pages[0].character_boxes == ()


def test_ocr_runtime_must_be_explicit_absolute_file(tmp_path: Path) -> None:
    with pytest.raises(OcrError, match="OCR_RUNTIME_NOT_CONFIGURED"):
        TesseractOcr(Path("tesseract.exe")).recognize_png(b"not an image")
