"""Verify the separate public-PDF test corpus and measure native extraction."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.documents.native_pdf import extract_native_pdf  # noqa: E402
from app.documents.ocr import OcrEngine, configured_ocr_engine  # noqa: E402
from app.documents.provenance import sha256_bytes, validate_pdf_bytes  # noqa: E402
from app.documents.tree_parser import parse_legal_tree  # noqa: E402


def audit(manifest_path: Path, ocr_engine: OcrEngine | None = None) -> dict[str, object]:
    corpus_root = manifest_path.resolve().parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    documents = manifest["documents"]
    if not 10 <= len(documents) <= 20:
        raise ValueError("TEST_CORPUS_COUNT_OUT_OF_RANGE")

    rows: list[dict[str, object]] = []
    seen_hashes: set[str] = set()
    for entry in documents:
        source_url = urlparse(entry["pdf_url"])
        detail_url = urlparse(entry["detail_url"])
        if source_url.scheme != "https" or source_url.hostname != "datafiles.chinhphu.vn":
            raise ValueError("UNEXPECTED_PDF_SOURCE")
        if detail_url.scheme != "https" or detail_url.hostname != "vanban.chinhphu.vn":
            raise ValueError("UNEXPECTED_DETAIL_SOURCE")
        if entry["review_status"] != "test_only_unreviewed":
            raise ValueError("TEST_CORPUS_REVIEW_STATUS_CHANGED")
        path = (corpus_root / entry["local_file"]).resolve()
        if not path.is_relative_to(corpus_root) or not path.is_file():
            raise ValueError("MISSING_OR_UNSAFE_LOCAL_FILE")
        content = path.read_bytes()
        validate_pdf_bytes(content)
        if len(content) != entry["size_bytes"] or sha256_bytes(content) != entry["sha256"]:
            raise ValueError(f"CORPUS_INTEGRITY_MISMATCH: {entry['document_number']}")
        pages, digest = extract_native_pdf(path, ocr_engine=ocr_engine)
        if digest != entry["sha256"]:
            raise ValueError(f"CORPUS_INTEGRITY_MISMATCH: {entry['document_number']}")
        if digest in seen_hashes:
            raise ValueError("DUPLICATE_PDF_CONTENT")
        seen_hashes.add(digest)
        nodes = parse_legal_tree(pages)
        rows.append(
            {
                "document_number": entry["document_number"],
                "sha256": digest,
                "size_bytes": len(content),
                "page_count": len(pages),
                "text_characters": sum(len(page.text) for page in pages),
                "character_boxes": sum(len(page.character_boxes) for page in pages),
                "extraction_methods": dict(Counter(page.extraction_method for page in pages)),
                "text_quality_pages": dict(Counter(page.text_quality for page in pages)),
                "extraction_errors": dict(
                    Counter(page.extraction_error for page in pages if page.extraction_error)
                ),
                "node_types": dict(Counter(node.node_type for node in nodes)),
            }
        )

    return {
        "purpose": "Public PDF technical test corpus; no review or legal-effectivity assertion",
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "document_count": len(rows),
        "total_bytes": sum(int(row["size_bytes"]) for row in rows),
        "total_pages": sum(int(row["page_count"]) for row in rows),
        "total_text_characters": sum(int(row["text_characters"]) for row in rows),
        "documents": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=PROJECT_ROOT / "evaluation" / "corpus_public_real" / "manifest.json",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--ocr", action="store_true", help="Use configured local OCR on empty pages")
    args = parser.parse_args()
    ocr_engine = configured_ocr_engine() if args.ocr else None
    if args.ocr and ocr_engine is None:
        parser.error("--ocr requires EVIDENCE_OCR_EXECUTABLE")
    result = audit(args.manifest, ocr_engine=ocr_engine)
    output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output)


if __name__ == "__main__":
    main()
