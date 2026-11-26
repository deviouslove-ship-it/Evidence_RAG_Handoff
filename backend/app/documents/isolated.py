"""Bound native PDF work in a disposable process so a bad file cannot crash the API."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from .native_pdf import CharacterBox, ExtractedPage, sha256_file
from .ocr_ai import DEFAULT_RENDER_DPI, DEFAULT_RENDER_MAX_BYTES, DEFAULT_RENDER_MAX_EDGE
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


def render_page_isolated(
    source_pdf: bytes | Path,
    *,
    page_number: int,
    temporary_root: Path | None = None,
    dpi: int = DEFAULT_RENDER_DPI,
    max_edge: int = DEFAULT_RENDER_MAX_EDGE,
    max_bytes: int = DEFAULT_RENDER_MAX_BYTES,
    timeout_seconds: float = 60.0,
) -> tuple[bytes, dict[str, Any]]:
    """Render a single PDF page to bounded PNG bytes inside a disposable subprocess."""
    if temporary_root is not None:
        temporary_root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="ocr-ai-render-", dir=temporary_root) as folder:
        root = Path(folder)
        if isinstance(source_pdf, bytes):
            source = save_immutable_pdf(source_pdf, root)
            source_path = source.path
            expected_sha = source.sha256
        else:
            source_path = source_pdf
            expected_sha = sha256_file(source_path)
        output_png = root / f"page-{page_number}.png"
        output_meta = root / "meta.json"
        command = [
            sys.executable,
            "-m",
            "app.documents.pdf_worker",
            "render_page",
            str(source_path),
            str(output_png),
            str(output_meta),
            str(page_number),
            str(dpi),
            str(max_edge),
            str(max_bytes),
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=Path(__file__).resolve().parents[2],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout_seconds,
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except subprocess.TimeoutExpired as exc:
            raise ValueError("PDF_PARSE_TIMEOUT") from exc
        if completed.returncode != 0 or not output_meta.is_file():
            raise ValueError("PDF_PARSE_FAILED")
        meta = json.loads(output_meta.read_text(encoding="utf-8"))
        if "error" in meta:
            raise ValueError(str(meta["error"]))
        if meta.get("sha256") != expected_sha:
            raise ValueError("PDF_HASH_CHANGED")
        if not output_png.is_file():
            raise ValueError("PDF_PARSE_FAILED")
        with output_png.open("rb") as stream:
            png_bytes = stream.read(max_bytes + 1)
        if len(png_bytes) > max_bytes:
            raise ValueError("PDF_RESOURCE_LIMIT_EXCEEDED")
        return png_bytes, meta
