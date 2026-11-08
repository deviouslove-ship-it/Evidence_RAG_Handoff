"""Citation open/PDF routes recheck ACL and serve hash-checked source bytes."""

import os
from contextlib import asynccontextmanager
from datetime import date
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

import asyncpg
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.migrations.runner import apply_migrations
from app.storage.citations import get_authorized_citation

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF\n"
QUOTE = "Điều 3. Mức phụ cấp công vụ"


class _Connection:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self._row = row

    @asynccontextmanager
    async def transaction(self) -> Any:
        yield

    async def execute(self, *_args: object) -> None:
        return None

    async def fetchrow(self, *_args: object) -> dict[str, Any] | None:
        return self._row


class _Pool:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self._row = row

    @asynccontextmanager
    async def acquire(self) -> Any:
        yield _Connection(self._row)


def _row(digest: str, path: str) -> dict[str, Any]:
    return {
        "node_id": uuid4(),
        "document_id": uuid4(),
        "document_version_id": uuid4(),
        "document_number": "381/2026/NĐ-CP",
        "title": "Quy định phụ cấp công vụ",
        "label": "Điều 3",
        "quote_exact": QUOTE,
        "original_page": 2,
        "source_hash": digest,
        "original_file_path": path,
    }


def _headers(roles: str = "USER") -> dict[str, str]:
    return {"X-Principal-Id": str(uuid4()), "X-Roles": roles}


def test_citation_routes_fail_closed_without_database_or_auth() -> None:
    with TestClient(create_app()) as client:
        unauth = client.get("/api/v1/citations/ev_" + str(uuid4()))
        denied = client.get("/api/v1/citations/ev_" + str(uuid4()), headers=_headers("SYS_ADMIN"))
        missing = client.get("/api/v1/citations/ev_" + str(uuid4()), headers=_headers())
        pdf_url = "/api/v1/citations/ev_" + str(uuid4()) + "/pdf"
        missing_pdf = client.get(pdf_url, headers=_headers())
    assert unauth.status_code == 401
    assert denied.status_code == 403
    assert missing.status_code == 404 and missing.json()["code"] == "CITATION_INVALID"
    assert missing_pdf.status_code == 404


def test_citation_route_returns_exact_quote_and_viewer_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    digest = sha256(PDF).hexdigest()
    (tmp_path / "originals").mkdir()
    (tmp_path / "originals" / f"{digest}.pdf").write_bytes(PDF)
    monkeypatch.setenv("EVIDENCE_DOCUMENT_STORE_ROOT", str(tmp_path))
    row = _row(digest, f"originals/{digest}.pdf")
    app = create_app()
    with TestClient(app) as client:
        app.state.db_pool = _Pool(row)
        try:
            citation_id = f"ev_{row['node_id']}"
            opened = client.get(
                f"/api/v1/citations/{citation_id}",
                params={"as_of_date": "2026-10-22"},
                headers=_headers(),
            )
            pdf = client.get(
                f"/api/v1/citations/{citation_id}/pdf",
                params={"as_of_date": "2026-10-22"},
                headers=_headers(),
            )
        finally:
            del app.state.db_pool
    assert opened.status_code == 200
    body = opened.json()
    assert body["quote_exact"] == QUOTE
    assert body["amendment_state"] == "unknown"
    assert body["evidence"]["viewer_url"] == (
        f"/api/v1/citations/{citation_id}/pdf?as_of_date=2026-10-22"
    )
    assert pdf.status_code == 200
    assert pdf.content == PDF
    assert pdf.headers["cache-control"] == "no-store"


def test_pdf_route_refuses_bytes_whose_hash_changed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    digest = sha256(PDF).hexdigest()
    (tmp_path / "originals").mkdir()
    (tmp_path / "originals" / f"{digest}.pdf").write_bytes(PDF + b"tampered")
    monkeypatch.setenv("EVIDENCE_DOCUMENT_STORE_ROOT", str(tmp_path))
    row = _row(digest, f"originals/{digest}.pdf")
    app = create_app()
    with TestClient(app) as client:
        app.state.db_pool = _Pool(row)
        try:
            response = client.get(
                f"/api/v1/citations/ev_{row['node_id']}/pdf", headers=_headers()
            )
        finally:
            del app.state.db_pool
    assert response.status_code == 503
    assert response.json()["code"] == "CITATION_SOURCE_UNAVAILABLE"


async def test_malformed_citation_id_never_reaches_database() -> None:
    pool = _Pool(_row("a" * 64, "originals/x.pdf"))
    for value in ("e1", "ev_not-a-uuid", ""):
        assert (
            await get_authorized_citation(
                pool, principal_id=uuid4(), citation_id=value, as_of_date=date(2026, 10, 22)
            )
            is None
        )


async def test_postgres_citation_requires_acl_and_verified_provenance() -> None:
    dsn = os.environ.get("EVIDENCE_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("No disposable PostgreSQL/pgvector test database configured")
    schema = "test_citation_" + uuid4().hex
    connection = await asyncpg.connect(dsn)
    pool = None
    try:
        await connection.execute(f'CREATE SCHEMA "{schema}"')
        await connection.execute(f'SET search_path TO "{schema}", public')
        await apply_migrations(connection)
        pool = await asyncpg.create_pool(
            dsn, min_size=1, max_size=1, server_settings={"search_path": schema + ",public"}
        )
        allowed, other = uuid4(), uuid4()
        category, document, version = uuid4(), uuid4(), uuid4()
        digest = sha256(PDF).hexdigest()
        await connection.execute(
            "INSERT INTO users (id, username, display_name) VALUES ($1, 'a', 'A')", allowed
        )
        await connection.execute(
            "INSERT INTO categories (id, name, code) VALUES ($1, 'Fixture', 'fixture')", category
        )
        await connection.execute(
            "INSERT INTO category_acl (category_id, user_id) VALUES ($1, $2)", category, allowed
        )
        await connection.execute(
            "INSERT INTO documents (id, doc_type, title, document_number)"
            " VALUES ($1, 'decree', 'Quy định phụ cấp công vụ', '381/2026/NĐ-CP')",
            document,
        )
        await connection.execute(
            "INSERT INTO document_categories (document_id, category_id) VALUES ($1, $2)",
            document,
            category,
        )
        await connection.execute(
            """INSERT INTO document_versions (id, document_id, version_number,
                 original_file_path, original_file_sha256, original_filename, review_status)
               VALUES ($1, $2, 1, $3, $4, 'f.pdf', 'approved')""",
            version,
            document,
            f"originals/{digest}.pdf",
            digest,
        )
        page = await connection.fetchval(
            """INSERT INTO source_pages (document_version_id, page_number, width, height,
                 extraction_method, text_quality, text_original)
               VALUES ($1, 2, 595, 842, 'native_text', 'usable', $2) RETURNING id""",
            version, QUOTE,
        )
        span = await connection.fetchval(
            """INSERT INTO source_spans (page_id, original_offset, original_length, text_original)
               VALUES ($1, 0, $2, $3) RETURNING id""",
            page,
            len(QUOTE),
            QUOTE,
        )
        node = await connection.fetchval(
            """INSERT INTO document_nodes (document_id, document_version_id, node_type,
                 label_original, path, text_original, text_indexed, text_normalized,
                 text_folded, page_start, parse_confidence, review_status, source_span_id)
               VALUES ($1, $2, 'article', 'Điều 3', 'Điều 3', $3, $3, $3, $3, 2, 0.95,
                       'approved', $4) RETURNING id""",
            document,
            version,
            QUOTE,
            span,
        )
        citation_id = f"ev_{node}"
        today = date(2026, 10, 22)

        async def open_as(principal: Any) -> Any:
            return await get_authorized_citation(
                pool, principal_id=principal, citation_id=citation_id, as_of_date=today
            )

        assert await open_as(allowed) is None  # provenance not verified yet
        await connection.execute(
            "INSERT INTO source_provenance (document_version_id, verified_at)"
            " VALUES ($1, now())",
            version,
        )
        found = await open_as(allowed)
        assert found is not None
        assert found.response.quote_exact == QUOTE
        assert found.response.evidence.page == 2
        assert found.source_hash == digest
        assert await open_as(other) is None  # ACL is rechecked on open
    finally:
        if pool is not None:
            await pool.close()
        await connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await connection.close()



DOC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"word 97-2003 fixture" * 4


def test_original_route_serves_the_uploaded_pdf_inline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    digest = sha256(PDF).hexdigest()
    (tmp_path / "originals").mkdir()
    (tmp_path / "originals" / f"{digest}.pdf").write_bytes(PDF)
    monkeypatch.setenv("EVIDENCE_DOCUMENT_STORE_ROOT", str(tmp_path))
    row = {**_row(digest, f"originals/{digest}.pdf"), "source_format": "pdf",
           "original_filename": "Thông tư 55.pdf"}
    app = create_app()
    with TestClient(app) as client:
        app.state.db_pool = _Pool(row)
        try:
            response = client.get(
                f"/api/v1/citations/ev_{row['node_id']}/original", headers=_headers()
            )
        finally:
            del app.state.db_pool
    assert response.status_code == 200
    assert response.content == PDF  # the stored original itself (scans included)
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["x-source-format"] == "pdf"
    assert response.headers["x-source-sha256"] == digest
    assert response.headers["content-disposition"].startswith("inline;")
    assert "filename*=UTF-8''Th%C3%B4ng%20t%C6%B0%2055.pdf" in (
        response.headers["content-disposition"])


def test_original_route_serves_the_word_file_not_the_rendered_pdf(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pdf_digest = sha256(PDF).hexdigest()
    doc_digest = sha256(DOC).hexdigest()
    (tmp_path / "originals").mkdir()
    (tmp_path / "sources").mkdir()
    (tmp_path / "originals" / f"{pdf_digest}.pdf").write_bytes(PDF)
    (tmp_path / "sources" / f"{doc_digest}.doc").write_bytes(DOC)
    monkeypatch.setenv("EVIDENCE_DOCUMENT_STORE_ROOT", str(tmp_path))
    row = {**_row(pdf_digest, f"originals/{pdf_digest}.pdf"), "source_format": "doc",
           "source_file_sha256": doc_digest, "original_filename": "[01_VBHN-BCA]_VBHN.doc"}
    app = create_app()
    with TestClient(app) as client:
        app.state.db_pool = _Pool(row)
        try:
            response = client.get(
                f"/api/v1/citations/ev_{row['node_id']}/original", headers=_headers()
            )
            (tmp_path / "sources" / f"{doc_digest}.doc").write_bytes(DOC + b"x")
            tampered = client.get(
                f"/api/v1/citations/ev_{row['node_id']}/original", headers=_headers()
            )
        finally:
            del app.state.db_pool
    assert response.status_code == 200
    assert response.content == DOC
    assert response.headers["content-type"] == "application/msword"
    assert response.headers["x-source-format"] == "doc"
    assert response.headers["x-source-sha256"] == doc_digest
    assert response.headers["content-disposition"].startswith("attachment;")
    assert tampered.status_code == 503
    assert tampered.json()["code"] == "CITATION_SOURCE_UNAVAILABLE"


def test_original_route_requires_an_authorized_citation() -> None:
    with TestClient(create_app()) as client:
        unauth = client.get(f"/api/v1/citations/ev_{uuid4()}/original")
        missing = client.get(f"/api/v1/citations/ev_{uuid4()}/original", headers=_headers())
    assert unauth.status_code == 401
    assert missing.status_code == 404
