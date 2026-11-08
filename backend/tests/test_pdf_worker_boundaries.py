import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.documents.isolated import extract_isolated

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF\n"


def test_hung_pdf_worker_times_out_and_cleans_temporary_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    def timed_out(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired("pdf-worker", 0.01)

    monkeypatch.setattr("app.documents.isolated.subprocess.run", timed_out)
    with pytest.raises(ValueError, match="PDF_PARSE_TIMEOUT"):
        extract_isolated(PDF, max_pages=10, temporary_root=tmp_path, timeout_seconds=0.01)
    assert list(tmp_path.iterdir()) == []


def test_crashed_pdf_worker_cannot_crash_the_parent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "app.documents.isolated.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=139),
    )
    with pytest.raises(ValueError, match="PDF_PARSE_FAILED"):
        extract_isolated(PDF, max_pages=10, temporary_root=tmp_path)
    assert list(tmp_path.iterdir()) == []
