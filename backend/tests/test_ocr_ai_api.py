"""API contract tests for B1: idempotency, explicit retry, and ACL document scoping."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import pypdfium2 as pdfium
import pytest
from httpx import ASGITransport, AsyncClient

from app.admin_services import create_category, create_or_update_user
from app.documents.draft import PreparedDraft, persist_draft
from app.documents.native_pdf import ExtractedPage
from app.documents.tree_parser import parse_legal_tree
from app.main import create_app
from app.migrations.runner import apply_migrations


def _blank_pdf(pages: int) -> bytes:
    output = BytesIO()
    document = pdfium.PdfDocument.new()
    for _ in range(pages):
        document.new_page(595, 842).close()
    document.save(output)
    document.close()
    return output.getvalue()


def _headers(actor: UUID, roles: str) -> dict[str, str]:
    return {"X-Principal-Id": str(actor), "X-Roles": roles}


@pytest.fixture
async def ocr_ai_api_pool() -> AsyncIterator[asyncpg.Pool]:
    dsn = os.getenv("EVIDENCE_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Disposable PostgreSQL not configured")
    schema = "test_ocr_ai_api_" + uuid4().hex
    connection = await asyncpg.connect(dsn)
    pool: asyncpg.Pool | None = None
    try:
        await connection.execute(f'CREATE SCHEMA "{schema}"')
        pool = await asyncpg.create_pool(
            dsn,
            min_size=1,
            max_size=4,
            server_settings={"search_path": f"{schema},public"},
        )
        async with pool.acquire() as conn:
            await apply_migrations(conn)
        yield pool
    finally:
        if pool is not None:
            await pool.close()
        await connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await connection.close()


async def _user(
    pool: asyncpg.Pool,
    name: str,
    roles: list[str],
    category_ids: list[UUID] | None = None,
) -> UUID:
    row = await create_or_update_user(
        pool,
        actor_id=uuid4(),
        username=name,
        display_name=name,
        password="ApiPassword!2026",
        roles=roles,
        category_ids=category_ids or [],
        must_change_password=False,
    )
    return UUID(row["id"])


class _DummyWorker:
    def __init__(self) -> None:
        self.wake_calls = 0

    def wake(self) -> None:
        self.wake_calls += 1


async def _setup_scoped_doc(
    pool: asyncpg.Pool,
    store_root: Path,
) -> tuple[UUID, UUID, int, UUID, UUID, UUID, UUID]:
    bootstrap = uuid4()
    cat = await create_category(pool, actor_id=bootstrap, code="OCR_SCOPE", name="OCR Scope")
    cat_id = UUID(cat["id"])
    curator = await _user(pool, "scoped-curator", ["CURATOR"], [cat_id])
    outsider = await _user(pool, "outside-curator", ["CURATOR"], [])
    reviewer = await _user(pool, "scoped-reviewer", ["REVIEWER"], [cat_id])
    end_user = await _user(pool, "end-user", ["USER"], [cat_id])

    content = _blank_pdf(1)
    pages = [
        ExtractedPage(
            1,
            595,
            842,
            0,
            "Điều 1. Nội dung scan chưa đối chiếu.",
            (),
            "local_ocr",
            "needs_review",
        )
    ]
    prepared = PreparedDraft(
        content,
        sha256(content).hexdigest(),
        pages,
        parse_legal_tree(pages),
    )
    draft = await persist_draft(
        prepared,
        pool=pool,
        store_root=store_root,
        title="Văn bản phân quyền OCR AI",
        doc_type="decree",
        original_filename="scoped.pdf",
        submitted_by=curator,
    )
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO document_categories (document_id, category_id) VALUES ($1, $2)",
            draft.document_id,
            cat_id,
        )
        revision = await conn.fetchval(
            "SELECT source_review_revision FROM document_versions WHERE id = $1",
            draft.document_version_id,
        )
    return (
        draft.document_id,
        draft.document_version_id,
        int(revision),
        curator,
        outsider,
        reviewer,
        end_user,
    )


async def test_ocr_ai_request_is_idempotent_and_retry_is_explicit(
    ocr_ai_api_pool: asyncpg.Pool,
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("EVIDENCE_DOCUMENT_STORE_ROOT", str(tmp_path))
    monkeypatch.setenv("EVIDENCE_OCR_AI_ENABLED", "true")
    doc_id, ver_id, revision, curator, _, _, _ = await _setup_scoped_doc(ocr_ai_api_pool, tmp_path)
    app = create_app()
    app.state.db_pool = ocr_ai_api_pool
    worker = _DummyWorker()
    app.state.ocr_ai_worker = worker

    url = f"/api/v1/admin/documents/{doc_id}/versions/{ver_id}/ocr-ai"
    req_id = str(uuid4())
    payload = {"page_number": 1, "expected_revision": revision, "request_id": req_id}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        app.state.ocr_ai_worker = None
        disabled = await client.post(url, headers=_headers(curator, "CURATOR"), json=payload)
        assert disabled.status_code == 503
        assert disabled.json()["code"] == "OCR_AI_DISABLED"
        app.state.ocr_ai_worker = worker
        first = await client.post(url, headers=_headers(curator, "CURATOR"), json=payload)
        assert first.status_code == 202, first.text
        first_data = first.json()
        assert first_data["status"] == "queued"
        assert first_data["deduplicated"] is False
        assert worker.wake_calls == 1

        # Exact same request_id returns the same proposal cleanly.
        replay = await client.post(url, headers=_headers(curator, "CURATOR"), json=payload)
        assert replay.status_code == 202
        assert replay.json()["proposal_id"] == first_data["proposal_id"]
        assert replay.json()["deduplicated"] is True
        assert worker.wake_calls == 1

        # Explicit new request_id while active deduplicates cleanly without creating a second job.
        second_active = await client.post(
            url,
            headers=_headers(curator, "CURATOR"),
            json={"page_number": 1, "expected_revision": revision, "request_id": str(uuid4())},
        )
        assert second_active.status_code == 202
        assert second_active.json()["proposal_id"] == first_data["proposal_id"]
        assert second_active.json()["deduplicated"] is True

        # Cancel then explicitly retry with a new request_id creates a brand-new proposal.
        cancelled = await client.post(
            f"/api/v1/admin/ocr-ai/{first_data['proposal_id']}/cancel",
            headers=_headers(curator, "CURATOR"),
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"

        retry = await client.post(
            url,
            headers=_headers(curator, "CURATOR"),
            json={"page_number": 1, "expected_revision": revision, "request_id": str(uuid4())},
        )
        assert retry.status_code == 202
        assert retry.json()["proposal_id"] != first_data["proposal_id"]
        assert retry.json()["status"] == "queued"
        assert worker.wake_calls == 2


async def test_ocr_ai_requires_document_scope(
    ocr_ai_api_pool: asyncpg.Pool,
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("EVIDENCE_DOCUMENT_STORE_ROOT", str(tmp_path))
    monkeypatch.setenv("EVIDENCE_OCR_AI_ENABLED", "true")
    doc_id, ver_id, revision, curator, outsider, reviewer, end_user = await _setup_scoped_doc(
        ocr_ai_api_pool,
        tmp_path,
    )
    app = create_app()
    app.state.db_pool = ocr_ai_api_pool
    app.state.ocr_ai_worker = _DummyWorker()
    url = f"/api/v1/admin/documents/{doc_id}/versions/{ver_id}/ocr-ai"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # USER and REVIEWER cannot trigger OCR AI admin proposals.
        res_user = await client.post(
            url,
            headers=_headers(end_user, "USER"),
            json={"page_number": 1, "expected_revision": revision, "request_id": str(uuid4())},
        )
        assert res_user.status_code == 403

        res_reviewer = await client.post(
            url,
            headers=_headers(reviewer, "REVIEWER"),
            json={"page_number": 1, "expected_revision": revision, "request_id": str(uuid4())},
        )
        assert res_reviewer.status_code == 403

        # Out-of-scope curator gets 404/403 and cannot inspect in-scope proposals.
        res_outside = await client.post(
            url,
            headers=_headers(outsider, "CURATOR"),
            json={"page_number": 1, "expected_revision": revision, "request_id": str(uuid4())},
        )
        assert res_outside.status_code in (403, 404)

        created = await client.post(
            url,
            headers=_headers(curator, "CURATOR"),
            json={"page_number": 1, "expected_revision": revision, "request_id": str(uuid4())},
        )
        assert created.status_code == 202
        proposal_id = created.json()["proposal_id"]

        res_get_outside = await client.get(
            f"/api/v1/admin/ocr-ai/{proposal_id}",
            headers=_headers(outsider, "CURATOR"),
        )
        assert res_get_outside.status_code in (403, 404)

        res_cancel_outside = await client.post(
            f"/api/v1/admin/ocr-ai/{proposal_id}/cancel",
            headers=_headers(outsider, "CURATOR"),
        )
        assert res_cancel_outside.status_code in (403, 404)

        # Out-of-range page and stale revision checks.
        res_oor = await client.post(
            url,
            headers=_headers(curator, "CURATOR"),
            json={"page_number": 99, "expected_revision": revision, "request_id": str(uuid4())},
        )
        assert res_oor.status_code == 422

        res_stale = await client.post(
            url,
            headers=_headers(curator, "CURATOR"),
            json={
                "page_number": 1,
                "expected_revision": revision + 1,
                "request_id": str(uuid4()),
            },
        )
        assert res_stale.status_code == 409
