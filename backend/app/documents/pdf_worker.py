"""Private subprocess entry point; no network or persistent approval writes."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

from .native_pdf import extract_native_pdf
from .ocr import configured_ocr_engine


def main() -> None:
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
