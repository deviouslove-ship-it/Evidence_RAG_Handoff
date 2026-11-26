"""Private subprocess entry point; no network or persistent approval writes."""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import asdict
from io import BytesIO
from pathlib import Path
from typing import Any

from .native_pdf import extract_native_pdf, sha256_file
from .ocr import configured_ocr_engine


def _render_single_page(
    source_path: Path,
    output_png: Path,
    *,
    page_number: int,
    dpi: int,
    max_edge: int,
    max_bytes: int,
) -> dict[str, Any]:
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(str(source_path))
    try:
        total_pages = len(document)
        if page_number < 1 or page_number > total_pages:
            return {"error": "PAGE_OUT_OF_RANGE", "total_pages": total_pages}
        page = document[page_number - 1]
        try:
            width, height = page.get_size()
            base_scale = max(float(dpi) / 72.0, 0.1)
            longest = max(float(width), float(height), 1.0)
            scale = min(base_scale, float(max_edge) / longest)
            bitmap = page.render(scale=scale, grayscale=False)
            try:
                pil_image = bitmap.to_pil()
                buffer = BytesIO()
                pil_image.save(buffer, format="PNG")
                img_width, img_height = pil_image.width, pil_image.height
            finally:
                bitmap.close()
        finally:
            page.close()
    finally:
        document.close()

    png_bytes = buffer.getvalue()
    if len(png_bytes) > max_bytes:
        return {"error": "PDF_RESOURCE_LIMIT_EXCEEDED"}
    output_png.write_bytes(png_bytes)
    return {
        "sha256": sha256_file(source_path),
        "image_sha256": hashlib.sha256(png_bytes).hexdigest(),
        "page_number": page_number,
        "total_pages": total_pages,
        "width": img_width,
        "height": img_height,
        "dpi": dpi,
    }


def main() -> None:
    if len(sys.argv) >= 2 and sys.argv[1] == "render_page":
        _, source, output_png, output_meta, page_str, dpi_str, edge_str, bytes_str = sys.argv[1:]
        try:
            meta = _render_single_page(
                Path(source),
                Path(output_png),
                page_number=int(page_str),
                dpi=int(dpi_str),
                max_edge=int(edge_str),
                max_bytes=int(bytes_str),
            )
        except Exception:
            meta = {"error": "PDF_PARSE_FAILED"}
        Path(output_meta).write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        return

    source, output, max_pages, mode = sys.argv[1:]
    try:
        pages, digest = extract_native_pdf(
            Path(source), max_pages=int(max_pages),
            ocr_engine=configured_ocr_engine() if mode == "ocr" else None,
        )
        # Character boxes are only needed for the quality check done above; they are
        # ~10x the page text in JSON, so they are not sent back to the API process.
        result = {"sha256": digest, "pages": [
            {**asdict(page), "character_boxes": []} for page in pages
        ]}
    except ValueError as exc:
        code = str(exc)
        result = {"error": code if code in {
            "PDF_PAGE_LIMIT_EXCEEDED", "PDF_RESOURCE_LIMIT_EXCEEDED"
        } else "PDF_PARSE_FAILED"}
    Path(output).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
