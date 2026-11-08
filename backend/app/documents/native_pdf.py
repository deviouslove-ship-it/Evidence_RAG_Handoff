"""Native PDF text extraction with PDF-native page/character geometry."""

from __future__ import annotations

import os
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from threading import RLock
from typing import Any

from .ocr import OcrEngine, OcrError, suspect_tokens

_PDFIUM_LOCK = RLock()
_MAX_PAGE_CHARACTERS = 50_000
# Whole-document text cap; EVIDENCE_MAX_DOCUMENT_CHARACTERS raises it for long books
# (469-page technical regulations reach about 600,000 characters).
_DEFAULT_MAX_DOCUMENT_CHARACTERS = 2_000_000
_MAX_RENDER_PIXELS = 25_000_000


@dataclass(frozen=True)
class CharacterBox:
    index: int
    left: float
    bottom: float
    right: float
    top: float


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int
    width: float
    height: float
    rotation: int
    text: str
    character_boxes: tuple[CharacterBox, ...]
    extraction_method: str = "native_text"
    text_quality: str = "unknown"
    extraction_error: str | None = None
    # OCR pages only: confidences, suspect tokens, rotation (documents/ocr.py).
    ocr_diagnostics: dict[str, Any] | None = None


def extract_native_pdf(
    path: Path,
    ocr_engine: OcrEngine | None = None,
    *,
    max_pages: int | None = None,
) -> tuple[list[ExtractedPage], str]:
    # PDFium forbids simultaneous calls, even for different documents. API
    # intake additionally isolates this code in a bounded child process.
    with _PDFIUM_LOCK:
        return _extract_locked(path, ocr_engine, max_pages=max_pages)


def _extract_locked(
    path: Path,
    ocr_engine: OcrEngine | None = None,
    *,
    max_pages: int | None = None,
) -> tuple[list[ExtractedPage], str]:
    """Extract text and character boxes using pypdfium2.

    pypdfium2 is a small Core dependency; OCR is an explicitly configured
    optional worker. A missing PDF runtime never enables an unverifiable parser.
    """

    try:
        import pypdfium2 as pdfium
    except ImportError as exc:  # pragma: no cover - depends on deployment manifest
        raise RuntimeError("PDF_RUNTIME_NOT_CONFIGURED") from exc

    document = pdfium.PdfDocument(str(path))
    pages: list[ExtractedPage] = []
    total_characters = 0
    document_limit = max_document_characters()
    try:
        if max_pages is not None and len(document) > max_pages:
            raise ValueError("PDF_PAGE_LIMIT_EXCEEDED")
        for page_index in range(len(document)):
            page = document[page_index]
            try:
                text_page = page.get_textpage()
                try:
                    char_count = text_page.count_chars()
                    total_characters += char_count
                    if (char_count > _MAX_PAGE_CHARACTERS
                            or total_characters > document_limit):
                        raise ValueError("PDF_RESOURCE_LIMIT_EXCEEDED")
                    text = text_page.get_text_range(0, char_count, errors="replace")
                    boxes: list[CharacterBox] = []
                    for index in range(char_count):
                        box = text_page.get_charbox(index, loose=False)
                        if box:
                            left, bottom, right, top = box
                            boxes.append(CharacterBox(index, left, bottom, right, top))
                finally:
                    text_page.close()
                quality = diagnose_text_quality(text)
                method = "native_text"
                error = None
                diagnostics: dict[str, Any] | None = None
                if text and len(text) != char_count:
                    quality = "needs_review"
                    error = "TEXT_BOX_INDEX_MISMATCH"
                if quality == "needs_ocr" and ocr_engine is not None:
                    try:
                        width, height = page.get_size()
                        if width * height * (200 / 72) ** 2 > _MAX_RENDER_PIXELS:
                            raise ValueError("PDF_RESOURCE_LIMIT_EXCEEDED")
                        bitmap = page.render(scale=200 / 72, grayscale=True)
                        try:
                            output = BytesIO()
                            bitmap.to_pil().save(output, format="PNG")
                        finally:
                            bitmap.close()
                        reader = getattr(ocr_engine, "recognize", None)
                        if callable(reader):
                            result = reader(output.getvalue())
                            recognized, diagnostics = result.text, dict(result.diagnostics)
                        else:
                            recognized = ocr_engine.recognize_png(output.getvalue())
                            diagnostics = {"suspect_tokens": suspect_tokens(recognized)}
                        if recognized:
                            text = recognized
                            method = "local_ocr"
                            quality = "needs_review"
                        else:
                            error = "OCR_EMPTY"
                    except (ImportError, OcrError) as exc:
                        error = (
                            str(exc) if isinstance(exc, OcrError) else "OCR_IMAGE_RUNTIME_MISSING"
                        )
                width, height = page.get_size()
                pages.append(
                    ExtractedPage(
                        page_number=page_index + 1,
                        width=float(width),
                        height=float(height),
                        rotation=int(page.get_rotation()),
                        text=text,
                        character_boxes=tuple(boxes) if method == "native_text" else (),
                        extraction_method=method,
                        text_quality=quality,
                        extraction_error=error,
                        ocr_diagnostics=diagnostics,
                    )
                )
            finally:
                page.close()
    finally:
        document.close()
    return pages, sha256_file(path)


def max_document_characters() -> int:
    try:
        value = int(os.environ.get("EVIDENCE_MAX_DOCUMENT_CHARACTERS", ""))
    except ValueError:
        return _DEFAULT_MAX_DOCUMENT_CHARACTERS
    return value if 10_000 <= value <= 20_000_000 else _DEFAULT_MAX_DOCUMENT_CHARACTERS


def diagnose_text_quality(text: str) -> str:
    if not text.strip():
        return "needs_ocr"
    replacement_ratio = text.count("�") / max(len(text), 1)
    if replacement_ratio > 0.01:
        return "needs_review"
    return "usable"


def sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
