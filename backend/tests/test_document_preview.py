from hashlib import sha256
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

PRINCIPAL = "00000000-0000-0000-0000-000000000001"


def _blank_pdf(page_count: int = 1) -> bytes:
    pdfium = pytest.importorskip("pypdfium2")
    output = BytesIO()
    document = pdfium.PdfDocument.new()
    for _ in range(page_count):
        page = document.new_page(595, 842)
        page.close()
    document.save(output)
    document.close()
    return output.getvalue()


def test_curator_preview_keeps_blank_pdf_unapproved(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EVIDENCE_OCR_EXECUTABLE", raising=False)
    content = _blank_pdf()
    app = create_app()
    with TestClient(app) as client:
        denied = client.post(
            "/api/v1/admin/documents/preview",
            headers={"X-Principal-Id": PRINCIPAL, "X-Roles": "USER"},
            files={"file": ("blank.pdf", content, "application/pdf")},
        )
        allowed = client.post(
            "/api/v1/admin/documents/preview",
            headers={"X-Principal-Id": PRINCIPAL, "X-Roles": "CURATOR"},
            files={"file": ("blank.pdf", content, "application/pdf")},
        )
    assert denied.status_code == 403
    assert denied.json()["code"] == "CURATOR_REQUIRED"
    assert allowed.status_code == 200
    body = allowed.json()
    assert body["status"] == "preview_only"
    assert body["sha256"] == sha256(content).hexdigest()
    assert body["page_count"] == body["review_required_pages"] == 1
    assert body["pages"][0]["text_quality"] == "needs_ocr"
    assert "original_file_path" not in body


def test_preview_enforces_byte_and_page_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    content = _blank_pdf(2)
    monkeypatch.setenv("EVIDENCE_MAX_UPLOAD_BYTES", "100")
    with TestClient(create_app()) as client:
        oversized = client.post(
            "/api/v1/admin/documents/preview",
            headers={"X-Principal-Id": PRINCIPAL, "X-Roles": "CURATOR"},
            files={"file": ("two-pages.pdf", content, "application/pdf")},
        )
    assert oversized.status_code == 413
    assert oversized.json()["code"] == "PDF_SIZE_LIMIT_EXCEEDED"

    monkeypatch.setenv("EVIDENCE_MAX_UPLOAD_BYTES", str(len(content) + 1))
    monkeypatch.setenv("EVIDENCE_MAX_PREVIEW_PAGES", "1")
    with TestClient(create_app()) as client:
        too_many_pages = client.post(
            "/api/v1/admin/documents/preview",
            headers={"X-Principal-Id": PRINCIPAL, "X-Roles": "CURATOR"},
            files={"file": ("two-pages.pdf", content, "application/pdf")},
        )
    assert too_many_pages.status_code == 413
    assert too_many_pages.json()["code"] == "PDF_PAGE_LIMIT_EXCEEDED"
