"""PostgreSQL integration tests for B4a: verified page read and ephemeral OCR AI."""

from __future__ import annotations

import json
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

from app.admin_services import create_category, create_or_update_user
from app.auth_acl.policy import Principal
from app.documents.draft import PreparedDraft, persist_draft
from app.documents.native_pdf import ExtractedPage
from app.documents.ocr_ai_jobs import OcrAiWorker
from app.documents.page_text import cancel_page_text_task, get_page_text_task, request_page_text
from app.documents.review import (
    ReviewError,
    approve_document_version,
    list_review_tasks,
    resolve_review_task,
    submit_draft_for_review,
)
from app.documents.tree_parser import parse_legal_tree
from app.migrations.runner import apply_migrations
from app.model_registry.runtime import VisionGenerationOutcome


def _blank_pdf(pages: int) -> bytes:
    output = BytesIO()
    doc = pdfium.PdfDocument.new()
    for _ in range(pages):
        doc.new_page(595, 842).close()
    doc.save(output)
    doc.close()
    return output.getvalue()


@pytest.fixture
async def page_text_pool() -> AsyncIterator[asyncpg.Pool]:
    dsn = os.getenv("EVIDENCE_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Disposable PostgreSQL not configured")
    schema = "test_page_txt_" + uuid4().hex
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
) -> tuple[UUID, Principal]:
    row = await create_or_update_user(
        pool,
        actor_id=uuid4(),
        username=name,
        display_name=name,
        password="PagePassword!2026",
        roles=roles,
        category_ids=category_ids or [],
        must_change_password=False,
    )
    uid = UUID(row["id"])
    return uid, Principal(id=str(uid), roles=frozenset(roles))


async def _seed_approved_three_page_doc(
    pool: asyncpg.Pool,
    store_root: Path,
) -> tuple[UUID, UUID, Principal, Principal]:
    bootstrap = uuid4()
    cat = await create_category(pool, actor_id=bootstrap, code="PAGE_CAT", name="Page Cat")
    cat_id = UUID(cat["id"])
    curator_id, _ = await _user(pool, "pt-curator", ["CURATOR"], [cat_id])
    reviewer_id, _ = await _user(pool, "pt-reviewer", ["REVIEWER"], [cat_id])
    reader_id, reader = await _user(pool, "pt-reader", ["USER"], [cat_id])
    outsider_id, outsider = await _user(pool, "pt-outsider", ["USER"], [])

    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE category_acl SET can_review = TRUE WHERE category_id = $1 AND user_id = $2",
            cat_id,
            reviewer_id,
        )

    content = _blank_pdf(3)
    pages = [
        ExtractedPage(
            1,
            595,
            842,
            0,
            "Điều 1. Văn bản PDF có lớp text gốc HƯ CẤU.",
            (),
            "native_text",
            "usable",
        ),
        ExtractedPage(
            2,
            595,
            842,
            0,
            "Điều 2. Văn bản scan đã được rà soát HƯ CẤU.",
            (),
            "local_ocr",
            "needs_review",
        ),
        ExtractedPage(
            3,
            595,
            842,
            0,
            "",
            (),
            "local_ocr",
            "needs_ocr",
        ),
    ]
    prepared = PreparedDraft(content, sha256(content).hexdigest(), pages, parse_legal_tree(pages))
    draft = await persist_draft(
        prepared,
        pool=pool,
        store_root=store_root,
        title="Quyết định đọc trang PDF",
        doc_type="decision",
        original_filename="pages.pdf",
        submitted_by=curator_id,
    )
    await submit_draft_for_review(
        pool,
        version_id=draft.document_version_id,
        curator_id=curator_id,
    )
    tasks = await list_review_tasks(
        pool,
        version_id=draft.document_version_id,
        status_filter="open",
    )
    for task in tasks:
        await resolve_review_task(
            pool,
            task_id=UUID(task["id"]),
            reviewer_id=reviewer_id,
            resolution_note="Đã đối chiếu trang mẫu",
        )
    await approve_document_version(
        pool,
        store_root=store_root,
        max_bytes=len(content) + 1,
        version_id=draft.document_version_id,
        reviewer_id=reviewer_id,
        category_ids=[cat_id],
        review_note="Duyệt để kiểm thử page-text",
        resolve_all_tasks=True,
    )
    return draft.document_id, draft.document_version_id, reader, outsider


async def test_page_text_uses_reviewed_text_without_model_call(
    page_text_pool: asyncpg.Pool,
    tmp_path: Path,
) -> None:
    doc_id, ver_id, reader, outsider = await _seed_approved_three_page_doc(page_text_pool, tmp_path)

    # Page 1 (native_text) returns immediately without queuing any model job.
    status1, p1 = await request_page_text(
        page_text_pool, reader, document_id=doc_id, version_id=ver_id, page_number=1
    )
    assert status1 == 200
    assert p1["source_kind"] == "native"
    assert p1["verified"] is True
    assert p1["total_pages"] == 3
    assert "lớp text gốc" in p1["page_text"]

    # Page 2 (local_ocr reviewed) returns ocr_reviewed with 0 model calls.
    status2, p2 = await request_page_text(
        page_text_pool, reader, document_id=doc_id, version_id=ver_id, page_number=2
    )
    assert status2 == 200
    assert p2["source_kind"] == "ocr_reviewed"
    assert p2["verified"] is True
    assert "scan đã được rà soát" in p2["page_text"]

    async with page_text_pool.acquire() as conn:
        queued = await conn.fetchval("SELECT count(*) FROM document_ocr_ai_proposals")
    assert queued == 0

    # Outsider gets 404.
    with pytest.raises(ReviewError) as exc_out:
        await request_page_text(
            page_text_pool, outsider, document_id=doc_id, version_id=ver_id, page_number=1
        )
    assert exc_out.value.status_code == 404


async def test_expired_page_text_is_gone_and_clears_private_output(
    page_text_pool: asyncpg.Pool,
    tmp_path: Path,
) -> None:
    doc_id, ver_id, reader, _ = await _seed_approved_three_page_doc(page_text_pool, tmp_path)
    _, task = await request_page_text(
        page_text_pool,
        reader,
        document_id=doc_id,
        version_id=ver_id,
        page_number=3,
    )
    task_id = UUID(task["task_id"])
    async with page_text_pool.acquire() as conn:
        await conn.execute(
            """UPDATE document_ocr_ai_proposals SET status='ready', candidate_text='private',
               candidate_json='{}', expires_at=now()-interval '1 second' WHERE id=$1""",
            task_id,
        )
    with pytest.raises(ReviewError) as expired:
        await get_page_text_task(page_text_pool, reader, task_id)
    assert expired.value.status_code == 410
    async with page_text_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT candidate_text, candidate_json FROM document_ocr_ai_proposals WHERE id=$1",
            task_id,
        )
    assert row["candidate_text"] is None and row["candidate_json"] is None


async def test_user_page_text_discards_revision_changed_during_inference(
    page_text_pool: asyncpg.Pool,
    tmp_path: Path,
) -> None:
    doc_id, ver_id, reader, _ = await _seed_approved_three_page_doc(page_text_pool, tmp_path)
    _, task = await request_page_text(
        page_text_pool,
        reader,
        document_id=doc_id,
        version_id=ver_id,
        page_number=3,
    )

    class ChangedRuntime:
        async def generate_vision(self, **_: Any) -> VisionGenerationOutcome:
            async with page_text_pool.acquire() as conn:
                await conn.execute(
                    "UPDATE document_versions SET source_review_revision=source_review_revision+1"
                    " WHERE id=$1",
                    ver_id,
                )
            return VisionGenerationOutcome(
                content=json.dumps(
                    {
                        "blocks": [{"kind": "text", "text": "old output"}],
                        "warnings": [],
                        "unreadable": [],
                    }
                ),
            )

    await OcrAiWorker(page_text_pool, ChangedRuntime(), store_root=tmp_path).run_once()
    polled = await get_page_text_task(page_text_pool, reader, UUID(task["task_id"]))
    assert polled["status"] == "stale" and polled["page_text"] is None


async def test_ready_page_text_is_invalidated_when_source_later_changes(
    page_text_pool: asyncpg.Pool,
    tmp_path: Path,
) -> None:
    doc, version, reader, _ = await _seed_approved_three_page_doc(page_text_pool, tmp_path)
    _, task = await request_page_text(
        page_text_pool, reader, document_id=doc, version_id=version, page_number=3, prefer_ai=True
    )
    async with page_text_pool.acquire() as conn:
        await conn.execute(
            """UPDATE document_ocr_ai_proposals SET status='ready',
                           candidate_text='Old output', candidate_json='{}' WHERE id=$1""",
            UUID(task["task_id"]),
        )
        await conn.execute(
            "UPDATE document_versions SET source_review_revision=source_review_revision+1 "
            "WHERE id=$1",
            version,
        )
    result = await get_page_text_task(page_text_pool, reader, UUID(task["task_id"]))
    assert result["status"] == "stale"
    assert result["page_text"] is None


async def test_user_page_text_never_mutates_corpus(
    page_text_pool: asyncpg.Pool,
    tmp_path: Path,
) -> None:
    doc_id, ver_id, reader, outsider = await _seed_approved_three_page_doc(page_text_pool, tmp_path)

    # Out-of-range page rejects 422 before creating any task or calling model.
    with pytest.raises(ReviewError) as exc_oor:
        await request_page_text(
            page_text_pool, reader, document_id=doc_id, version_id=ver_id, page_number=99
        )
    assert exc_oor.value.code == "PAGE_OUT_OF_RANGE"
    assert exc_oor.value.status_code == 422

    async with page_text_pool.acquire() as conn:
        rev_before = await conn.fetchval(
            "SELECT source_review_revision FROM document_versions WHERE id = $1",
            ver_id,
        )
        p3_before = await conn.fetchrow(
            "SELECT text_original, reviewed_at FROM source_pages "
            "WHERE document_version_id = $1 AND page_number = 3",
            ver_id,
        )
        node_count_before = await conn.fetchval(
            "SELECT count(*) FROM document_nodes WHERE document_version_id = $1",
            ver_id,
        )
        ver_count_before = await conn.fetchval(
            "SELECT count(*) FROM document_versions WHERE document_id = $1",
            doc_id,
        )

    status3, queued = await request_page_text(
        page_text_pool,
        reader,
        document_id=doc_id,
        version_id=ver_id,
        page_number=3,
        request_id=uuid4(),
    )
    assert status3 == 202
    assert queued["status"] == "queued"
    assert queued["verified"] is False
    assert queued["source_kind"] == "ocr_ai_unverified"
    assert queued["warning"] == "AI đọc từ ảnh trang 3 — chưa đối chiếu thủ công"
    task_id = UUID(queued["task_id"])

    class _FakePageVisionRuntime:
        async def generate_vision(self, **_: Any) -> VisionGenerationOutcome:
            return VisionGenerationOutcome(
                content=json.dumps(
                    {
                        "blocks": [{"kind": "text", "text": "Điều 3. Nội dung AI đọc trang 3."}],
                        "warnings": [],
                        "unreadable": [],
                    }
                ),
                profile_id="local-qwen35-ocr",
                profile_revision="1",
                model_digest="sha256:test",
                attempts_used=1,
            )

    worker = OcrAiWorker(page_text_pool, _FakePageVisionRuntime(), store_root=tmp_path)
    assert await worker.run_once() is True

    polled = await get_page_text_task(page_text_pool, reader, task_id)
    assert polled["status"] == "ready"
    assert polled["verified"] is False
    assert "Nội dung AI đọc trang 3" in polled["page_text"]

    # Another user cannot poll or cancel someone else's task.
    with pytest.raises(ReviewError) as exc_other:
        await get_page_text_task(page_text_pool, outsider, task_id)
    assert exc_other.value.status_code == 404

    with pytest.raises(ReviewError):
        await cancel_page_text_task(page_text_pool, outsider, task_id)

    # Corpus tables are 100% untouched.
    async with page_text_pool.acquire() as conn:
        rev_after = await conn.fetchval(
            "SELECT source_review_revision FROM document_versions WHERE id = $1",
            ver_id,
        )
        p3_after = await conn.fetchrow(
            "SELECT text_original, reviewed_at FROM source_pages "
            "WHERE document_version_id = $1 AND page_number = 3",
            ver_id,
        )
        node_count_after = await conn.fetchval(
            "SELECT count(*) FROM document_nodes WHERE document_version_id = $1",
            ver_id,
        )
        ver_count_after = await conn.fetchval(
            "SELECT count(*) FROM document_versions WHERE document_id = $1",
            doc_id,
        )
    assert rev_after == rev_before
    assert tuple(p3_after) == tuple(p3_before)
    assert node_count_after == node_count_before
    assert ver_count_after == ver_count_before
