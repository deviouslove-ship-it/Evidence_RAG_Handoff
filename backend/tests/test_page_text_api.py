"""API contract tests for B4a: user page-text reading, cancellation, and source PDF."""

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
from app.documents.review import (
    approve_document_version,
    list_review_tasks,
    resolve_review_task,
    submit_draft_for_review,
)
from app.documents.tree_parser import parse_legal_tree
from app.main import create_app
from app.migrations.runner import apply_migrations


def _blank_pdf(pages: int) -> bytes:
    output = BytesIO()
    doc = pdfium.PdfDocument.new()
    for _ in range(pages):
        doc.new_page(595, 842).close()
    doc.save(output)
    doc.close()
    return output.getvalue()


def _headers(uid: UUID, roles: str) -> dict[str, str]:
    return {"X-Principal-Id": str(uid), "X-Roles": roles}


@pytest.fixture
async def pt_api_pool() -> AsyncIterator[asyncpg.Pool]:
    dsn = os.getenv("EVIDENCE_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Disposable PostgreSQL not configured")
    schema = "test_pt_api_" + uuid4().hex
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
        password="PtApiPassword!2026",
        roles=roles,
        category_ids=category_ids or [],
        must_change_password=False,
    )
    return UUID(row["id"])


class _CountingWakeWorker:
    def __init__(self) -> None:
        self.wakes = 0

    def wake(self) -> None:
        self.wakes += 1


async def test_page_text_api_direct_queue_cancel_and_pdf(
    pt_api_pool: asyncpg.Pool,
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("EVIDENCE_DOCUMENT_STORE_ROOT", str(tmp_path))
    monkeypatch.setenv("EVIDENCE_OCR_AI_ENABLED", "true")
    bootstrap = uuid4()
    cat = await create_category(pt_api_pool, actor_id=bootstrap, code="PT_API", name="PT API")
    cat_id = UUID(cat["id"])
    curator = await _user(pt_api_pool, "pt-api-cur", ["CURATOR"], [cat_id])
    reviewer = await _user(pt_api_pool, "pt-api-rev", ["REVIEWER"], [cat_id])
    reader = await _user(pt_api_pool, "pt-api-user", ["USER"], [cat_id])
    outsider = await _user(pt_api_pool, "pt-api-out", ["USER"], [])

    async with pt_api_pool.acquire() as conn:
        await conn.execute(
            "UPDATE category_acl SET can_review = TRUE WHERE category_id = $1 AND user_id = $2",
            cat_id,
            reviewer,
        )

    pdf_bytes = _blank_pdf(2)
    pages = [
        ExtractedPage(
            1, 595, 842, 0, "Điều 1. Nội dung chuẩn trang 1.", (), "native_text", "usable"
        ),
        ExtractedPage(2, 595, 842, 0, "", (), "local_ocr", "needs_ocr"),
    ]
    prepared = PreparedDraft(
        pdf_bytes, sha256(pdf_bytes).hexdigest(), pages, parse_legal_tree(pages)
    )
    draft = await persist_draft(
        prepared,
        pool=pt_api_pool,
        store_root=tmp_path,
        title="Thông tư kiểm thử API trang",
        doc_type="circular",
        original_filename="thong-tu.pdf",
        submitted_by=curator,
    )
    await submit_draft_for_review(
        pt_api_pool,
        version_id=draft.document_version_id,
        curator_id=curator,
    )
    tasks = await list_review_tasks(
        pt_api_pool,
        version_id=draft.document_version_id,
        status_filter="open",
    )
    for task in tasks:
        await resolve_review_task(
            pt_api_pool,
            task_id=UUID(task["id"]),
            reviewer_id=reviewer,
            resolution_note="Đã đối chiếu",
        )
    await approve_document_version(
        pt_api_pool,
        store_root=tmp_path,
        max_bytes=len(pdf_bytes) + 1,
        version_id=draft.document_version_id,
        reviewer_id=reviewer,
        category_ids=[cat_id],
        review_note="Duyệt API test",
        resolve_all_tasks=True,
    )

    app = create_app()
    app.state.db_pool = pt_api_pool
    worker = _CountingWakeWorker()
    app.state.ocr_ai_worker = worker

    url = f"/api/v1/documents/{draft.document_id}/versions/{draft.document_version_id}/page-text"
    pdf_url = f"/api/v1/documents/{draft.document_id}/versions/{draft.document_version_id}/pdf"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Page 1 resolves directly with HTTP 200 and zero worker wakes.
        r1 = await client.post(url, headers=_headers(reader, "USER"), json={"page_number": 1})
        assert r1.status_code == 200, r1.text
        assert r1.json()["source_kind"] == "native"
        assert r1.json()["verified"] is True
        assert worker.wakes == 0

        # Disabled worker must not silently queue a task that will never run.
        app.state.ocr_ai_worker = None
        disabled = await client.post(url, headers=_headers(reader, "USER"), json={"page_number": 2})
        assert disabled.status_code == 503
        assert disabled.json()["code"] == "OCR_AI_DISABLED"
        app.state.ocr_ai_worker = worker

        # Out-of-range page returns 422 without calling worker.
        r_oor = await client.post(url, headers=_headers(reader, "USER"), json={"page_number": 7})
        assert r_oor.status_code == 422
        assert worker.wakes == 0

        # Page 2 scan returns 202 and wakes worker once.
        r2 = await client.post(url, headers=_headers(reader, "USER"), json={"page_number": 2})
        assert r2.status_code == 202, r2.text
        task_id = r2.json()["task_id"]
        assert worker.wakes == 1

        polled = await client.get(
            f"/api/v1/page-text-tasks/{task_id}",
            headers=_headers(reader, "USER"),
        )
        assert polled.status_code == 200
        assert polled.json()["status"] == "queued"

        cancelled = await client.post(
            f"/api/v1/page-text-tasks/{task_id}/cancel",
            headers=_headers(reader, "USER"),
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"

        # Original PDF endpoint checks ACL.
        pdf_ok = await client.get(pdf_url, headers=_headers(reader, "USER"))
        assert pdf_ok.status_code == 200
        assert pdf_ok.content == pdf_bytes
        assert (await client.get(pdf_url, headers=_headers(outsider, "USER"))).status_code == 404
