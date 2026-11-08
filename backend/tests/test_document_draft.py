"""The draft boundary keeps imported PDFs unreviewed and out of retrieval."""

import os
from contextlib import asynccontextmanager
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest
from fastapi.testclient import TestClient

from app.documents.draft import persist_draft, prepare_draft, validate_source_url
from app.documents.draft_read import list_document_drafts, load_draft_pdf
from app.main import create_app
from app.migrations.runner import apply_migrations


def _blank_pdf() -> bytes:
    pdfium = pytest.importorskip("pypdfium2")
    output = BytesIO()
    document = pdfium.PdfDocument.new()
    page = document.new_page(595, 842)
    page.close()
    document.save(output)
    document.close()
    return output.getvalue()


def test_draft_api_requires_role_and_persistent_store() -> None:
    content = _blank_pdf()
    with TestClient(create_app()) as client:
        denied = client.post(
            "/api/v1/admin/documents/drafts",
            headers={"X-Principal-Id": str(uuid4()), "X-Roles": "USER"},
            data={"title": "Văn bản thử", "doc_type": "decree"},
            files={"file": ("blank.pdf", content, "application/pdf")},
        )
        unavailable = client.post(
            "/api/v1/admin/documents/drafts",
            headers={"X-Principal-Id": str(uuid4()), "X-Roles": "CURATOR"},
            data={"title": "Văn bản thử", "doc_type": "decree"},
            files={"file": ("blank.pdf", content, "application/pdf")},
        )
    assert denied.status_code == 403
    assert unavailable.status_code == 503
    assert unavailable.json()["code"] == "DRAFT_STORE_NOT_CONFIGURED"
    with TestClient(create_app()) as client:
        list_denied = client.get(
            "/api/v1/admin/documents/drafts",
            headers={"X-Principal-Id": str(uuid4()), "X-Roles": "SYS_ADMIN"},
        )
    assert list_denied.status_code == 403


def test_source_url_is_recorded_only_for_public_https_host() -> None:
    assert validate_source_url("https://vanban.chinhphu.vn/a") == (
        "https://vanban.chinhphu.vn/a", "vanban.chinhphu.vn"
    )
    for value in ("http://vanban.chinhphu.vn/a", "https://127.0.0.1/a",
                  "https://host.local/a", "https://user:pass@example.com/a"):
        with pytest.raises(ValueError, match="INVALID_SOURCE_URL"):
            validate_source_url(value)


def test_reextract_route_requires_curator_and_persistent_store() -> None:
    version_id = uuid4()
    with TestClient(create_app()) as client:
        denied = client.post(
            f"/api/v1/admin/documents/drafts/{version_id}/reextract",
            headers={"X-Principal-Id": str(uuid4()), "X-Roles": "USER"},
        )
        unavailable = client.post(
            f"/api/v1/admin/documents/drafts/{version_id}/reextract",
            headers={"X-Principal-Id": str(uuid4()), "X-Roles": "CURATOR"},
        )
    assert denied.status_code == 403
    assert unavailable.status_code == 503
    assert unavailable.json()["code"] == "DRAFT_STORE_NOT_CONFIGURED"


def test_identical_pdf_is_rejected_before_expensive_extraction(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    from app.api.v1 import admin

    class Connection:
        async def fetchval(self, _sql: str, *_args: object) -> bool:
            return True

    class Pool:
        @asynccontextmanager
        async def acquire(self):
            yield Connection()

    async def forbidden_extraction(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Duplicate should be stopped before PDF extraction")

    monkeypatch.setenv("EVIDENCE_DOCUMENT_STORE_ROOT", str(tmp_path))
    monkeypatch.setattr(admin, "_run_pdf_work", forbidden_extraction)
    app = create_app()
    with TestClient(app) as client:
        app.state.db_pool = Pool()
        try:
            response = client.post(
                "/api/v1/admin/documents/drafts",
                headers={"X-Principal-Id": str(uuid4()), "X-Roles": "CURATOR"},
                data={"title": "Văn bản thử", "doc_type": "decree"},
                files={"file": ("same.pdf", _blank_pdf(), "application/pdf")},
            )
        finally:
            del app.state.db_pool
    assert response.status_code == 409
    assert response.json()["code"] == "DUPLICATE_PDF_HASH"


def test_reviewer_can_read_hash_checked_pdf_route(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.api.v1 import admin

    content = _blank_pdf()

    async def load_stub(*_args: object, **_kwargs: object) -> bytes:
        return content

    monkeypatch.setenv("EVIDENCE_DOCUMENT_STORE_ROOT", str(tmp_path))
    monkeypatch.setattr(admin, "load_draft_pdf", load_stub)
    app = create_app()
    version_id = uuid4()
    with TestClient(app) as client:
        app.state.db_pool = object()
        try:
            denied = client.get(
                f"/api/v1/admin/documents/drafts/{version_id}/pdf",
                headers={"X-Principal-Id": str(uuid4()), "X-Roles": "SYS_ADMIN"},
            )
            allowed = client.get(
                f"/api/v1/admin/documents/drafts/{version_id}/pdf",
                headers={"X-Principal-Id": str(uuid4()), "X-Roles": "REVIEWER"},
            )
        finally:
            del app.state.db_pool
    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert allowed.headers["content-type"] == "application/pdf"
    assert allowed.headers["cache-control"] == "no-store"
    assert allowed.content == content


async def test_postgres_draft_is_immutable_and_not_approved(tmp_path: Path) -> None:
    dsn = os.environ.get("EVIDENCE_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("No disposable PostgreSQL/pgvector test database configured")
    schema = "test_draft_" + uuid4().hex
    connection = await asyncpg.connect(dsn)
    pool = None
    try:
        await connection.execute(f'CREATE SCHEMA "{schema}"')
        await connection.execute(f'SET search_path TO "{schema}", public')
        await apply_migrations(connection)
        pool = await asyncpg.create_pool(
            dsn, min_size=1, max_size=1,
            server_settings={"search_path": schema + ",public"},
        )
        content = _blank_pdf()
        prepared = prepare_draft(content, max_pages=2)
        response = await persist_draft(
            prepared, pool=pool, store_root=tmp_path,
            title="Văn bản thử", doc_type="decree", original_filename="blank.pdf",
            official_url="https://vanban.chinhphu.vn/detail",
        )
        assert response.status == "draft"
        assert response.sha256 == sha256(content).hexdigest()
        assert response.page_count == response.review_required_pages == 1
        assert (tmp_path / "originals" / f"{response.sha256}.pdf").read_bytes() == content
        row = await connection.fetchrow(
            """SELECT dv.review_status::text, dv.original_file_path,
                      sp.verified_at, sp.publisher_domain
               FROM document_versions dv
               JOIN source_provenance sp ON sp.document_version_id = dv.id
               WHERE dv.id = $1""", response.document_version_id,
        )
        assert row is not None
        assert row["review_status"] == "draft"
        assert row["original_file_path"] == f"originals/{response.sha256}.pdf"
        assert row["verified_at"] is None
        assert row["publisher_domain"] == "vanban.chinhphu.vn"
        listing = await list_document_drafts(pool, limit=10, offset=0)
        assert len(listing) == 1
        assert listing[0].document_version_id == response.document_version_id
        assert await load_draft_pdf(
            pool, store_root=tmp_path,
            version_id=response.document_version_id, max_bytes=len(content) + 1,
        ) == content
        assert await connection.fetchval(
            "SELECT count(*) FROM curator_review_tasks WHERE document_version_id = $1",
            response.document_version_id,
        ) == 2
        assert await connection.fetchval("SELECT count(*) FROM authorized_nodes") == 0
        with pytest.raises(asyncpg.UniqueViolationError):
            await persist_draft(
                prepared, pool=pool, store_root=tmp_path,
                title="Bản trùng", doc_type="decree", original_filename="blank.pdf",
            )
        assert await connection.fetchval("SELECT count(*) FROM documents") == 1
        (tmp_path / "originals" / f"{response.sha256}.pdf").write_bytes(b"tampered")
        with pytest.raises(ValueError, match="DRAFT_STORAGE_CONFLICT"):
            await load_draft_pdf(
                pool, store_root=tmp_path,
                version_id=response.document_version_id, max_bytes=len(content) + 1,
            )
    finally:
        if pool is not None:
            await pool.close()
        await connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await connection.close()
