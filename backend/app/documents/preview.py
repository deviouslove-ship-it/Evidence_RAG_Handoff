"""Bounded PDF inspection for a curator before creating a persistent draft."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pypdfium2 as pdfium

from ..schemas import PdfPagePreview, PdfPreviewResponse
from .isolated import extract_isolated
from .native_pdf import extract_native_pdf
from .ocr import OcrEngine
from .provenance import save_immutable_pdf
from .tree_parser import parse_legal_tree


def inspect_pdf_preview(
    content: bytes,
    *,
    max_pages: int,
    ocr_engine: OcrEngine | None = None,
    temporary_root: Path | None = None,
    isolate: bool = False,
    timeout_seconds: float = 120,
) -> PdfPreviewResponse:
    """Inspect a temporary original; never mark content approved or retain it."""
    if temporary_root is not None:
        temporary_root.mkdir(parents=True, exist_ok=True)
    if isolate:
        pages, digest = extract_isolated(
            content, max_pages=max_pages, temporary_root=temporary_root,
            enable_ocr=ocr_engine is not None, timeout_seconds=timeout_seconds,
        )
    else:
        with TemporaryDirectory(prefix="evidence-pdf-preview-", dir=temporary_root) as temporary:
            source = save_immutable_pdf(content, Path(temporary))
            try:
                pages, digest = extract_native_pdf(
                    source.path,
                    ocr_engine=ocr_engine,
                    max_pages=max_pages,
                )
            except pdfium.PdfiumError as exc:
                raise ValueError("PDF_PARSE_FAILED") from exc
    nodes = parse_legal_tree(pages)
    return PdfPreviewResponse(
        sha256=digest,
        size_bytes=len(content),
        page_count=len(pages),
        node_count=len(nodes),
        review_required_pages=sum(page.text_quality != "usable" for page in pages),
        pages=[
            PdfPagePreview(
                page_number=page.page_number,
                extraction_method=page.extraction_method,
                text_quality=page.text_quality,
                text_characters=len(page.text),
                extraction_error=page.extraction_error,
            )
            for page in pages
        ],
    )
