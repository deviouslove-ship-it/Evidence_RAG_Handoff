"""Bound native PDF work in a disposable process so a bad file cannot crash the API."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from .native_pdf import CharacterBox, ExtractedPage
from .provenance import save_immutable_pdf

_MAX_RESULT_BYTES = 64 * 1024 * 1024


def extract_isolated(
    content: bytes, *, max_pages: int, temporary_root: Path | None = None,
    enable_ocr: bool = False, timeout_seconds: float = 120,
) -> tuple[list[ExtractedPage], str]:
    if temporary_root is not None:
        temporary_root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="evidence-worker-", dir=temporary_root) as folder:
        root = Path(folder)
        source = save_immutable_pdf(content, root)
        output = root / "result.json"
        command = [sys.executable, "-m", "app.documents.pdf_worker", str(source.path),
                   str(output), str(max_pages), "ocr" if enable_ocr else "native"]
        try:
            completed = subprocess.run(
                command, cwd=Path(__file__).resolve().parents[2],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=timeout_seconds, check=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except subprocess.TimeoutExpired as exc:
            raise ValueError("PDF_PARSE_TIMEOUT") from exc
        if completed.returncode != 0 or not output.is_file():
            raise ValueError("PDF_PARSE_FAILED")
        with output.open("rb") as stream:
            raw = stream.read(_MAX_RESULT_BYTES + 1)
        if len(raw) > _MAX_RESULT_BYTES:
            raise ValueError("PDF_RESOURCE_LIMIT_EXCEEDED")
        result = json.loads(raw)
        if "error" in result:
            raise ValueError(result["error"])
        if result["sha256"] != source.sha256:
            raise ValueError("PDF_HASH_CHANGED")
        pages = [
            ExtractedPage(**{**page, "character_boxes": tuple(
                CharacterBox(**box) for box in page["character_boxes"]
            )}) for page in result["pages"]
        ]
        return pages, source.sha256
