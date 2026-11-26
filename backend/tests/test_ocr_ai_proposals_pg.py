"""PostgreSQL integration tests for 0017_ocr_ai_proposals and ocr_ai_store."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import pypdfium2 as pdfium
import pytest

from app.admin_services import create_category, create_or_update_user
from app.documents.draft import PreparedDraft, persist_draft
from app.documents.native_pdf import ExtractedPage
from app.documents.ocr_ai_store import (
    MAX_QUEUED_OCR_TASKS,
    apply_candidate,
    cancel_proposal,
    create_proposal,
    get_proposal,
    reject_proposal,
)
from app.documents.review import (
    ReviewError,
    approve_document_version,
    list_review_tasks,
    resolve_review_task,
    submit_draft_for_review,
)
from app.documents.tree_parser import parse_legal_tree
from app.migrations.runner import MIGRATIONS_DIR, apply_migrations


def _blank_pdf(pages: int) -> bytes:
    output = BytesIO()
    document = pdfium.PdfDocument.new()
    for _ in range(pages):
        document.new_page(595, 842).close()
    document.save(output)
    document.close()
    return output.getvalue()


@pytest.fixture
async def ocr_ai_pg_pool() -> AsyncIterator[asyncpg.Pool]:
    dsn = os.getenv("EVIDENCE_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Disposable PostgreSQL not configured")
    schema = "test_ocr_ai_" + uuid4().hex
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


async def _create_user(
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
        password="OcrAiPassword!2026",
        roles=roles,
        category_ids=category_ids or [],
        must_change_password=False,
    )
    return UUID(row["id"])


async def _seed_ocr_draft(
    pool: asyncpg.Pool,
    store_root: Path,
    *,
    submitted_by: UUID,
    category_id: UUID | None = None,
) -> tuple[UUID, UUID, int]:
    content = _blank_pdf(2)
    pages = [
        ExtractedPage(
            1,
            595,
            842,
            0,
            "Điều 1. Nội dung scan chưa rà soát HƯ CẤU.",
            (),
            "local_ocr",
            "needs_review",
        ),
        ExtractedPage(
            2,
            595,
            842,
            0,
            "",
            (),
            "native_pdf",
            "needs_ocr",
        ),
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
        title="Nghị định kiểm thử OCR AI",
        doc_type="decree",
        original_filename="ocr-ai-test.pdf",
        submitted_by=submitted_by,
    )
    async with pool.acquire() as conn:
        if category_id is not None:
            await conn.execute(
                "INSERT INTO document_categories (document_id, category_id) VALUES ($1, $2)",
                draft.document_id,
                category_id,
            )
        revision = await conn.fetchval(
            "SELECT source_review_revision FROM document_versions WHERE id = $1",
            draft.document_version_id,
        )
    return draft.document_id, draft.document_version_id, int(revision)


async def test_0017_migration_up_down_and_applied_guard(
    ocr_ai_pg_pool: asyncpg.Pool,
    tmp_path: Path,
) -> None:
    name = "0017_ocr_ai_proposals"
    down_sql = (MIGRATIONS_DIR / f"{name}.down.sql").read_text(encoding="utf-8")
    curator = await _create_user(ocr_ai_pg_pool, "mig-curator", ["CURATOR"])
    async with ocr_ai_pg_pool.acquire() as conn:
        await conn.execute(down_sql)
        await conn.execute("DELETE FROM schema_migrations WHERE name = $1", f"{name}.sql")
        assert await apply_migrations(conn) == [f"{name}.sql"]
        assert await apply_migrations(conn) == []

    doc_id, ver_id, revision = await _seed_ocr_draft(
        ocr_ai_pg_pool,
        tmp_path,
        submitted_by=curator,
    )
    async with ocr_ai_pg_pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO document_ocr_ai_proposals (
                 purpose, document_id, version_id, page_number, source_review_revision,
                 pdf_sha256, page_text_sha256, prompt_version, request_id, requested_by,
                 status, applied_version_id
               )
               VALUES (
                 'admin_correction', $1, $2, 1, $3,
                 'a', 'b', 'ocr-v1', $4, $5, 'applied', $2
               )""",
            doc_id,
            ver_id,
            revision,
            uuid4(),
            curator,
        )
        with pytest.raises(asyncpg.RaiseError, match="applied OCR AI proposals exist"):
            async with conn.transaction():
                await conn.execute(down_sql)


async def test_create_cancel_reject_and_queue_limit_in_pg(
    ocr_ai_pg_pool: asyncpg.Pool,
    tmp_path: Path,
) -> None:
    from app.auth_acl.policy import Principal

    curator = await _create_user(ocr_ai_pg_pool, "q-curator", ["CURATOR"])
    principal = Principal(id=str(curator), roles=frozenset({"CURATOR"}))
    doc_id, ver_id, rev = await _seed_ocr_draft(
        ocr_ai_pg_pool,
        tmp_path,
        submitted_by=curator,
    )

    req1 = uuid4()
    created = await create_proposal(
        ocr_ai_pg_pool,
        principal,
        document_id=doc_id,
        version_id=ver_id,
        page_number=1,
        expected_revision=rev,
        request_id=req1,
    )
    assert created["status"] == "queued"
    assert created["deduplicated"] is False

    # Same request_id with different page triggers idempotency conflict.
    with pytest.raises(ReviewError) as exc_info:
        await create_proposal(
            ocr_ai_pg_pool,
            principal,
            document_id=doc_id,
            version_id=ver_id,
            page_number=2,
            expected_revision=rev,
            request_id=req1,
        )
    assert exc_info.value.code == "OCR_AI_IDEMPOTENCY_CONFLICT"

    # Cancel and verify ready -> reject flow + diff view.
    cancelled = await cancel_proposal(ocr_ai_pg_pool, principal, UUID(created["proposal_id"]))
    assert cancelled["status"] == "cancelled"

    ready_prop = await create_proposal(
        ocr_ai_pg_pool,
        principal,
        document_id=doc_id,
        version_id=ver_id,
        page_number=1,
        expected_revision=rev,
        request_id=uuid4(),
    )
    assert ready_prop["proposal_id"] != created["proposal_id"]

    async with ocr_ai_pg_pool.acquire() as conn:
        await conn.execute(
            """UPDATE document_ocr_ai_proposals
               SET status = 'ready',
                   candidate_text = 'Điều 1. Nội dung scan đã sửa HƯ CẤU.',
                   candidate_json = '{"blocks":[]}'::jsonb
               WHERE id = $1""",
            UUID(ready_prop["proposal_id"]),
        )
    viewed = await get_proposal(ocr_ai_pg_pool, principal, UUID(ready_prop["proposal_id"]))
    assert viewed["status"] == "ready"
    assert viewed["diff"]
    rejected = await reject_proposal(
        ocr_ai_pg_pool,
        principal,
        UUID(ready_prop["proposal_id"]),
        note="Không chính xác",
    )
    assert rejected["status"] == "rejected"
    assert rejected["note"] == "Không chính xác"

    # Fill remaining queue slots and verify cap MAX_QUEUED_OCR_TASKS = 20.
    async with ocr_ai_pg_pool.acquire() as conn:
        for i in range(MAX_QUEUED_OCR_TASKS):
            await conn.execute(
                """INSERT INTO document_ocr_ai_proposals (
                     purpose, document_id, version_id, page_number, source_review_revision,
                     pdf_sha256, page_text_sha256, prompt_version, request_id, requested_by, status
                   )
                   VALUES (
                     'admin_correction', $1, $2, $3, $4,
                     $5, 'c', 'ocr-v1', $6, $7, 'queued'
                   )""",
                doc_id,
                ver_id,
                1,
                rev,
                f"{i:064x}",
                uuid4(),
                curator,
            )
    with pytest.raises(ReviewError) as cap_exc:
        await create_proposal(
            ocr_ai_pg_pool,
            principal,
            document_id=doc_id,
            version_id=ver_id,
            page_number=2,
            expected_revision=rev,
            request_id=uuid4(),
        )
    assert cap_exc.value.status_code == 429
    assert cap_exc.value.code == "OCR_AI_QUEUE_FULL"


async def test_apply_candidate_is_atomic_and_revision_guarded(
    ocr_ai_pg_pool: asyncpg.Pool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.auth_acl.policy import Principal
    from app.documents import ocr_ai_store

    curator = await _create_user(ocr_ai_pg_pool, "apply-curator", ["CURATOR"])
    principal = Principal(id=str(curator), roles=frozenset({"CURATOR"}))
    doc_id, ver_id, rev = await _seed_ocr_draft(
        ocr_ai_pg_pool,
        tmp_path,
        submitted_by=curator,
    )

    prop = await create_proposal(
        ocr_ai_pg_pool,
        principal,
        document_id=doc_id,
        version_id=ver_id,
        page_number=1,
        expected_revision=rev,
        request_id=uuid4(),
    )
    prop_id = UUID(prop["proposal_id"])
    raw_ai_text = "Điều 1. Nội dung AI đề xuất nguyên gốc HƯ CẤU."
    raw_json = '{"blocks":[{"kind":"text","text":"AI"}],"warnings":[],"unreadable":[]}'
    async with ocr_ai_pg_pool.acquire() as conn:
        await conn.execute(
            """UPDATE document_ocr_ai_proposals
               SET status = 'ready',
                   candidate_text = $2,
                   candidate_json = $3::jsonb
               WHERE id = $1""",
            prop_id,
            raw_ai_text,
            raw_json,
        )

    # Wrong revision fails without modifying candidate or source_pages.
    with pytest.raises(ReviewError) as rev_exc:
        await apply_candidate(ocr_ai_pg_pool, principal, prop_id, expected_revision=rev + 1)
    assert rev_exc.value.code == "DOCUMENT_REVISION_CONFLICT"

    # Empty corrected_text fails 422.
    with pytest.raises(ReviewError) as empty_exc:
        await apply_candidate(
            ocr_ai_pg_pool, principal, prop_id, expected_revision=rev, corrected_text="   "
        )
    assert empty_exc.value.code == "OCR_AI_TEXT_EMPTY"

    # Never apply a candidate produced by an obsolete prompt or Registry profile.
    async with ocr_ai_pg_pool.acquire() as conn:
        await conn.execute(
            "UPDATE document_ocr_ai_proposals SET prompt_version='obsolete' WHERE id=$1", prop_id
        )
    with pytest.raises(ReviewError) as prompt_exc:
        await apply_candidate(ocr_ai_pg_pool, principal, prop_id, expected_revision=rev)
    assert prompt_exc.value.code == "OCR_AI_MODEL_CHANGED"
    async with ocr_ai_pg_pool.acquire() as conn:
        from app.documents.ocr_ai import PROMPT_VERSION

        await conn.execute(
            "UPDATE document_ocr_ai_proposals SET prompt_version=$2, "
            "profile_id='removed-profile', profile_revision='old' WHERE id=$1",
            prop_id,
            PROMPT_VERSION,
        )
    with pytest.raises(ReviewError) as profile_exc:
        await apply_candidate(ocr_ai_pg_pool, principal, prop_id, expected_revision=rev)
    assert profile_exc.value.code == "OCR_AI_MODEL_CHANGED"
    async with ocr_ai_pg_pool.acquire() as conn:
        await conn.execute(
            "UPDATE document_ocr_ai_proposals SET profile_id=NULL, "
            "profile_revision=NULL WHERE id=$1",
            prop_id,
        )

    # Atomicity: failure mid-transaction rolls back BOTH version mutation and proposal status.
    async def _boom(*_: object, **__: object) -> None:
        raise RuntimeError("simulated audit failure")

    monkeypatch.setattr(ocr_ai_store, "append_audit", _boom)
    with pytest.raises(RuntimeError, match="simulated audit failure"):
        await apply_candidate(ocr_ai_pg_pool, principal, prop_id, expected_revision=rev)
    monkeypatch.undo()

    async with ocr_ai_pg_pool.acquire() as conn:
        status_after_fail = await conn.fetchval(
            "SELECT status FROM document_ocr_ai_proposals WHERE id = $1", prop_id
        )
        rev_after_fail = await conn.fetchval(
            "SELECT source_review_revision FROM document_versions WHERE id = $1", ver_id
        )
    assert status_after_fail == "ready"
    assert rev_after_fail == rev

    # Successful apply with human edit keeps original candidate_text intact.
    edited = "Điều 1. Nội dung Curator đã hiệu đính HƯ CẤU."
    applied = await apply_candidate(
        ocr_ai_pg_pool,
        principal,
        prop_id,
        expected_revision=rev,
        corrected_text=edited,
        note="Đã kiểm tra theo bản gốc",
    )
    assert applied["status"] == "draft"
    assert applied["revision"] == rev + 1
    assert applied["proposal"]["status"] == "applied"
    assert applied["proposal"]["candidate_text"] == raw_ai_text

    async with ocr_ai_pg_pool.acquire() as conn:
        page_text = await conn.fetchval(
            "SELECT text_original FROM source_pages "
            "WHERE document_version_id = $1 AND page_number = 1",
            ver_id,
        )
        stored_ai = await conn.fetchval(
            "SELECT candidate_text FROM document_ocr_ai_proposals WHERE id = $1", prop_id
        )
    assert page_text == edited
    assert stored_ai == raw_ai_text

    # Re-applying already applied proposal fails 409.
    with pytest.raises(ReviewError) as again_exc:
        await apply_candidate(ocr_ai_pg_pool, principal, prop_id, expected_revision=rev)
    assert again_exc.value.code == "OCR_AI_PROPOSAL_NOT_READY"


async def test_approved_version_survives_new_ocr_draft(
    ocr_ai_pg_pool: asyncpg.Pool,
    tmp_path: Path,
) -> None:
    from app.auth_acl.policy import Principal

    cat = await create_category(ocr_ai_pg_pool, actor_id=uuid4(), code="SURV", name="Survival")
    cat_id = UUID(cat["id"])
    curator = await _create_user(ocr_ai_pg_pool, "surv-cur", ["CURATOR"], [cat_id])
    reviewer = await _create_user(ocr_ai_pg_pool, "surv-rev", ["REVIEWER"], [cat_id])
    async with ocr_ai_pg_pool.acquire() as conn:
        await conn.execute(
            "UPDATE category_acl SET can_review = TRUE WHERE category_id = $1 AND user_id = $2",
            cat_id,
            reviewer,
        )

    doc_id, v1_id, _ = await _seed_ocr_draft(
        ocr_ai_pg_pool, tmp_path, submitted_by=curator, category_id=cat_id
    )
    await submit_draft_for_review(ocr_ai_pg_pool, version_id=v1_id, curator_id=curator)
    for task in await list_review_tasks(ocr_ai_pg_pool, version_id=v1_id, status_filter="open"):
        await resolve_review_task(
            ocr_ai_pg_pool,
            task_id=UUID(task["id"]),
            reviewer_id=reviewer,
            resolution_note="Duyệt bản gốc",
        )
    await approve_document_version(
        ocr_ai_pg_pool,
        store_root=tmp_path,
        max_bytes=1024 * 1024,
        version_id=v1_id,
        reviewer_id=reviewer,
        category_ids=[cat_id],
        review_note="Phát hành v1",
        resolve_all_tasks=True,
    )

    curator_principal = Principal(id=str(curator), roles=frozenset({"CURATOR"}))
    async with ocr_ai_pg_pool.acquire() as conn:
        v1_rev = int(
            await conn.fetchval(
                "SELECT source_review_revision FROM document_versions WHERE id = $1", v1_id
            )
        )
    prop = await create_proposal(
        ocr_ai_pg_pool,
        curator_principal,
        document_id=doc_id,
        version_id=v1_id,
        page_number=1,
        expected_revision=v1_rev,
        request_id=uuid4(),
    )
    async with ocr_ai_pg_pool.acquire() as conn:
        await conn.execute(
            """UPDATE document_ocr_ai_proposals
               SET status = 'ready',
                   candidate_text = 'Điều 1. Nội dung bản sửa mới v2 HƯ CẤU.'
               WHERE id = $1""",
            UUID(prop["proposal_id"]),
        )
    applied = await apply_candidate(
        ocr_ai_pg_pool,
        curator_principal,
        UUID(prop["proposal_id"]),
        expected_revision=v1_rev,
    )
    v2_id = UUID(applied["version_id"])
    assert v2_id != v1_id

    async with ocr_ai_pg_pool.acquire() as conn:
        v1_row = await conn.fetchrow(
            "SELECT review_status, retired_at FROM document_versions WHERE id = $1", v1_id
        )
        v1_page = await conn.fetchval(
            "SELECT text_original FROM source_pages "
            "WHERE document_version_id = $1 AND page_number = 1",
            v1_id,
        )
        v2_row = await conn.fetchrow(
            "SELECT review_status, version_number FROM document_versions WHERE id = $1", v2_id
        )
        v2_page = await conn.fetchval(
            "SELECT text_original FROM source_pages "
            "WHERE document_version_id = $1 AND page_number = 1",
            v2_id,
        )
    assert v1_row["review_status"] == "approved"
    assert v1_row["retired_at"] is None
    assert "chưa rà soát" in v1_page
    assert v2_row["review_status"] == "draft"
    assert v2_row["version_number"] == 2
    assert "bản sửa mới v2" in v2_page


async def test_submitter_cannot_approve_own_ocr_revision(
    ocr_ai_pg_pool: asyncpg.Pool,
    tmp_path: Path,
) -> None:
    from app.auth_acl.policy import Principal

    cat = await create_category(ocr_ai_pg_pool, actor_id=uuid4(), code="SOD", name="Separation")
    cat_id = UUID(cat["id"])
    dual = await _create_user(ocr_ai_pg_pool, "dual-staff", ["CURATOR", "REVIEWER"], [cat_id])
    independent = await _create_user(ocr_ai_pg_pool, "indep-rev", ["REVIEWER"], [cat_id])
    async with ocr_ai_pg_pool.acquire() as conn:
        await conn.execute(
            "UPDATE category_acl SET can_review = TRUE WHERE category_id = $1", cat_id
        )

    doc_id, ver_id, rev = await _seed_ocr_draft(
        ocr_ai_pg_pool, tmp_path, submitted_by=dual, category_id=cat_id
    )
    dual_principal = Principal(id=str(dual), roles=frozenset({"CURATOR", "REVIEWER"}))
    prop = await create_proposal(
        ocr_ai_pg_pool,
        dual_principal,
        document_id=doc_id,
        version_id=ver_id,
        page_number=1,
        expected_revision=rev,
        request_id=uuid4(),
    )
    async with ocr_ai_pg_pool.acquire() as conn:
        await conn.execute(
            """UPDATE document_ocr_ai_proposals
               SET status = 'ready',
                   candidate_text = 'Điều 1. Nội dung sửa đổi SOD HƯ CẤU.'
               WHERE id = $1""",
            UUID(prop["proposal_id"]),
        )
    applied = await apply_candidate(
        ocr_ai_pg_pool, dual_principal, UUID(prop["proposal_id"]), expected_revision=rev
    )
    await submit_draft_for_review(ocr_ai_pg_pool, version_id=ver_id, curator_id=dual)

    with pytest.raises(ReviewError) as sod_exc:
        await approve_document_version(
            ocr_ai_pg_pool,
            store_root=tmp_path,
            max_bytes=1024 * 1024,
            version_id=ver_id,
            reviewer_id=dual,
            category_ids=[cat_id],
            review_note="Tự duyệt",
            resolve_all_tasks=True,
            revision=applied["revision"],
        )
    assert sod_exc.value.code == "SELF_APPROVAL_DENIED"
    assert sod_exc.value.status_code == 403

    # Independent reviewer must still resolve open page tasks before approval succeeds.
    for task in await list_review_tasks(ocr_ai_pg_pool, version_id=ver_id, status_filter="open"):
        await resolve_review_task(
            ocr_ai_pg_pool,
            task_id=UUID(task["id"]),
            reviewer_id=independent,
            resolution_note="Xác nhận sau đối chiếu",
        )
    approved = await approve_document_version(
        ocr_ai_pg_pool,
        store_root=tmp_path,
        max_bytes=1024 * 1024,
        version_id=ver_id,
        reviewer_id=independent,
        category_ids=[cat_id],
        review_note="Duyệt độc lập",
        resolve_all_tasks=True,
        revision=applied["revision"],
    )
    assert approved["status"] == "approved"
