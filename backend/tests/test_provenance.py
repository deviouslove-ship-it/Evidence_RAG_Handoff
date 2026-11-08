from pathlib import Path

import pytest

from app.documents.provenance import save_immutable_pdf, sha256_bytes, validate_pdf_bytes


def test_rejects_fake_mime() -> None:
    with pytest.raises(ValueError, match="INVALID_PDF_MAGIC"):
        validate_pdf_bytes(b"not a pdf")


def test_same_hash_does_not_overwrite_original(tmp_path: Path) -> None:
    content = b"%PDF-1.7\nfixture\n%%EOF"
    first = save_immutable_pdf(content, tmp_path)
    second = save_immutable_pdf(content, tmp_path)
    assert first.path == second.path
    assert first.sha256 == sha256_bytes(content)
