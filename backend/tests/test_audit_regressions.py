"""Regression boundaries found by the full code audit; no production data is changed."""

from __future__ import annotations

import asyncio
import os
from dataclasses import replace
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import httpx
import pypdfium2 as pdfium
import pytest
from fastapi.testclient import TestClient

from app.admin_services import create_category, create_or_update_user, delete_user
from app.auth_acl import service as auth_service
from app.auth_acl.passwords import verify_password
from app.documents.draft import PreparedDraft, persist_draft
from app.documents.native_pdf import ExtractedPage
from app.documents.reextract import apply_reextracted_draft
from app.documents.review import (
    ReviewError,
    approve_document_version,
    list_review_tasks,
    resolve_review_task,
    submit_draft_for_review,
)
from app.documents.tree_parser import ParsedNode
from app.main import create_app
from app.migrations.runner import apply_migrations


@pytest.fixture
async def audit_pool():
    dsn = os.getenv("EVIDENCE_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Disposable PostgreSQL not configured")
    schema = "test_audit_" + uuid4().hex
    connection = await asyncpg.connect(dsn)
    pool = None
    try:
        await connection.execute(f'CREATE SCHEMA "{schema}"')
        pool = await asyncpg.create_pool(
            dsn, min_size=1, max_size=4,
            server_settings={"search_path": schema + ",public"},
        )
        async with pool.acquire() as conn:
            await apply_migrations(conn)
        yield pool
    finally:
        if pool is not None:
            await pool.close()
        await connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await connection.close()


async def _user(pool, name: str, roles: list[str]) -> UUID:
    row = await create_or_update_user(
        pool, actor_id=uuid4(), username=name, display_name=name,
        password="AuditPassword!2026", roles=roles, category_ids=[],
        must_change_password=False,
    )
    return UUID(row["id"])


async def test_no_anonymous_account_impersonation(audit_pool) -> None:
    await _user(audit_pool, "reader", ["USER"])
    app = create_app()
    app.state.settings = replace(app.state.settings, dev_allow_in_memory_store=False)
    app.state.db_pool = audit_pool
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/api/v1/auth/agent-session")
    assert response.status_code in {401, 403, 404}
    assert "access_token" not in response.json()


@pytest.mark.parametrize("encoded", ["scrypt$3$8$1$YQ==$YQ==", "scrypt$32768$8$1$!$!"])
def test_malformed_password_hash_fails_closed(encoded: str) -> None:
    assert verify_password("some-password", encoded) is False


async def test_password_reset_revokes_old_sessions(audit_pool) -> None:
    user_id = await _user(audit_pool, "resetme", ["USER"])
    logged_in = await auth_service.login(
        audit_pool, username="resetme", password="AuditPassword!2026", ttl_seconds=3600
    )
    await create_or_update_user(
        audit_pool, actor_id=uuid4(), username="resetme", display_name="Reader",
        password="ReplacementPass!2026", roles=["USER"], category_ids=[],
        must_change_password=False,
    )
    assert await auth_service.resolve_token(audit_pool, logged_in.token) is None
    await delete_user(audit_pool, actor_id=uuid4(), user_id=user_id)
    async with audit_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT disabled_at FROM users WHERE id=$1", user_id)
    assert row is not None and row["disabled_at"] is not None


async def test_category_creation_does_not_grant_content_access(audit_pool) -> None:
    actor_id = await _user(audit_pool, "adminreader", ["SYS_ADMIN", "USER"])
    category = await create_category(
        audit_pool, actor_id=actor_id, code="PRIVATE", name="Private"
    )
    async with audit_pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT count(*) FROM category_acl WHERE category_id=$1 AND user_id=$2",
            UUID(category["id"]), actor_id,
        )
    assert count == 0


async def test_approval_cannot_fabricate_missing_source_span(audit_pool, tmp_path: Path) -> None:
    curator = await _user(audit_pool, "curator", ["CURATOR"])
    reviewer = await _user(audit_pool, "reviewer", ["REVIEWER"])
    category = await create_category(audit_pool, actor_id=curator, code="TEST", name="Test")
    output = BytesIO()
    document = pdfium.PdfDocument.new()
    page = document.new_page(595, 842)
    page.close()
    document.save(output)
    document.close()
    content = output.getvalue()
    prepared = PreparedDraft(
        content, sha256(content).hexdigest(),
        [ExtractedPage(1, 595, 842, 0, "Original source text", (), text_quality="usable")],
        [ParsedNode("paragraph", "", "Text not in source", 1, 0.5)],
    )
    draft = await persist_draft(
        prepared, pool=audit_pool, store_root=tmp_path, title="Test",
        doc_type="other", original_filename="test.pdf", submitted_by=curator,
    )
    await submit_draft_for_review(audit_pool, version_id=draft.document_version_id,
                                  curator_id=curator)
    tasks = await list_review_tasks(audit_pool, version_id=draft.document_version_id)
    assert tasks
    await resolve_review_task(
        audit_pool, task_id=UUID(tasks[0]["id"]), reviewer_id=reviewer,
        resolution_note="Đã ghi nhận vấn đề nguồn; chưa phê duyệt.",
    )
    with pytest.raises(ReviewError, match="REVIEW_TASK_ALREADY_RESOLVED"):
        await resolve_review_task(
            audit_pool, task_id=UUID(tasks[0]["id"]), reviewer_id=reviewer,
            resolution_note="Không được ghi đè một xử lý trước đó.",
        )
    with pytest.raises(ReviewError, match="SOURCE_SPANS_REQUIRE_REVIEW"):
        await approve_document_version(
            audit_pool, store_root=tmp_path, max_bytes=len(content) + 1,
            version_id=draft.document_version_id, reviewer_id=reviewer,
            category_ids=[UUID(category["id"])], review_note="Checked",
            resolve_all_tasks=True,
        )
    async with audit_pool.acquire() as conn:
        assert await conn.fetchval(
            "SELECT review_status::text FROM document_versions WHERE id=$1",
            draft.document_version_id,
        ) == "pending_review"
        assert await conn.fetchval(
            "SELECT count(*) FROM document_nodes WHERE document_version_id=$1 "
            "AND source_span_id IS NOT NULL", draft.document_version_id,
        ) == 0


async def test_draft_anchors_original_whitespace_and_flags_unmatched_nodes(
    audit_pool, tmp_path: Path,
) -> None:
    output = BytesIO()
    document = pdfium.PdfDocument.new()
    page = document.new_page(595, 842)
    page.close()
    document.save(output)
    document.close()
    content = output.getvalue()
    # "Lặp" is repeated and does not follow the article directly ("Khác" sits in
    # between), so neither reading order nor a unique match can place it.
    original = "Đầu trang\r\nĐiều 1. Quy định\r\n   Nội dung\r\nKhác\nLặp\nLặp"
    prepared = PreparedDraft(
        content, sha256(content).hexdigest(),
        [ExtractedPage(1, 595, 842, 0, original, (), text_quality="usable")],
        [ParsedNode("article", "Điều 1", "Điều 1. Quy định\nNội dung", 1, 0.8),
         ParsedNode("paragraph", "", "Lặp", 1, 0.5)],
    )
    draft = await persist_draft(
        prepared, pool=audit_pool, store_root=tmp_path, title="Mẫu mô phỏng",
        doc_type="other", original_filename="synthetic.pdf",
    )
    async with audit_pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT n.text_original, ss.original_offset, ss.text_original AS span_text
               FROM document_nodes n LEFT JOIN source_spans ss ON ss.id = n.source_span_id
               WHERE n.document_version_id = $1 ORDER BY n.path""", draft.document_version_id,
        )
        assert rows[0]["text_original"] == rows[0]["span_text"] == (
            "Điều 1. Quy định\r\n   Nội dung"
        )
        assert original[rows[0]["original_offset"]:].startswith(rows[0]["text_original"])
        assert rows[1]["span_text"] is None
        assert await conn.fetchval(
            "SELECT count(*) FROM curator_review_tasks "
            "WHERE document_version_id=$1 AND reason='unanchored_source_spans'",
            draft.document_version_id,
        ) == 1


async def test_draft_flags_same_extracted_content_without_merging_files(
    audit_pool, tmp_path: Path,
) -> None:
    output = BytesIO()
    document = pdfium.PdfDocument.new()
    page = document.new_page(595, 842)
    page.close()
    document.save(output)
    document.close()
    first_pdf = output.getvalue()
    second_pdf = first_pdf + b"\n% synthetic different PDF bytes"
    async def save(content: bytes, text: str):
        prepared = PreparedDraft(
            content, sha256(content).hexdigest(),
            [ExtractedPage(1, 595, 842, 0, text, (), text_quality="usable")],
            [ParsedNode("paragraph", "", text, 1, 0.6)],
        )
        return await persist_draft(
            prepared, pool=audit_pool, store_root=tmp_path,
            title="Nguồn mô phỏng", doc_type="other", original_filename="test.pdf",
        )
    first = await save(first_pdf, "Điều 1. Quy định\n  Nội dung")
    second = await save(second_pdf, "Điều 1. Quy định Nội dung")
    assert first.model_dump().get("content_check_available") is True
    matches = second.model_dump().get("potential_duplicates") or []
    assert len(matches) == 1
    assert matches[0]["document_version_id"] == first.document_version_id
    assert first.document_version_id != second.document_version_id
    async with audit_pool.acquire() as conn:
        assert await conn.fetchval(
            "SELECT count(*) FROM curator_review_tasks "
            "WHERE document_version_id=$1 AND reason='possible_duplicate_content'",
            second.document_version_id,
        ) == 1


async def test_duplicate_candidates_respect_access_to_approved_documents(
    audit_pool, tmp_path: Path,
) -> None:
    curator = await _user(audit_pool, "content-curator", ["CURATOR"])
    output = BytesIO()
    document = pdfium.PdfDocument.new()
    page = document.new_page(595, 842)
    page.close()
    document.save(output)
    document.close()
    original = output.getvalue()

    async def save(suffix: bytes):
        content = original + suffix
        prepared = PreparedDraft(
            content, sha256(content).hexdigest(),
            [ExtractedPage(1, 595, 842, 0, "Nội dung giống nhau", (), text_quality="usable")],
            [ParsedNode("paragraph", "", "Nội dung giống nhau", 1, 0.6)],
        )
        return await persist_draft(
            prepared, pool=audit_pool, store_root=tmp_path, title="Nguồn riêng",
            doc_type="other", original_filename="test.pdf", submitted_by=curator,
        )

    first = await save(b"\n% source A")
    async with audit_pool.acquire() as conn:
        await conn.execute(
            "UPDATE document_versions SET review_status='approved' WHERE id=$1",
            first.document_version_id,
        )
    hidden = await save(b"\n% source B")
    assert hidden.potential_duplicates == []
    async with audit_pool.acquire() as conn:
        await conn.execute(
            "UPDATE document_versions SET review_status='rejected' WHERE id=$1",
            hidden.document_version_id,
        )
        await conn.execute(
            "INSERT INTO document_acl(document_id, user_id, can_query) VALUES($1,$2,true)",
            first.document_id, curator,
        )
    permitted = await save(b"\n% source C")
    assert [item.document_version_id for item in permitted.potential_duplicates] == [
        first.document_version_id,
    ]
    app = create_app()
    app.state.settings = replace(app.state.settings, dev_allow_in_memory_store=True)
    app.state.db_pool = audit_pool
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        url = f"/api/v1/admin/documents/drafts/{permitted.document_version_id}/duplicates"
        denied = await client.get(url, headers={"X-Principal-Id": str(curator), "X-Roles": "USER"})
        visible = await client.get(
            url, headers={"X-Principal-Id": str(curator), "X-Roles": "CURATOR"},
        )
        assert denied.status_code == 403
        assert visible.status_code == 200
        assert visible.json()["content_check_available"] is True
        assert [item["document_version_id"] for item in visible.json()["potential_duplicates"]] == [
            str(first.document_version_id),
        ]
        async with audit_pool.acquire() as conn:
            await conn.execute("DELETE FROM document_acl WHERE document_id=$1", first.document_id)
        revoked = await client.get(
            url, headers={"X-Principal-Id": str(curator), "X-Roles": "CURATOR"},
        )
        assert revoked.json()["potential_duplicates"] == []


async def test_concurrent_content_matches_are_reported(audit_pool, tmp_path: Path) -> None:
    output = BytesIO()
    document = pdfium.PdfDocument.new()
    page = document.new_page(595, 842)
    page.close()
    document.save(output)
    document.close()
    original = output.getvalue()

    async def save(suffix: bytes):
        content = original + suffix
        prepared = PreparedDraft(
            content, sha256(content).hexdigest(),
            [ExtractedPage(1, 595, 842, 0, "Văn bản thử", (), text_quality="usable")],
            [ParsedNode("paragraph", "", "Văn bản thử", 1, 0.6)],
        )
        return await persist_draft(
            prepared, pool=audit_pool, store_root=tmp_path,
            title="Mẫu", doc_type="other", original_filename="test.pdf",
        )

    results = await asyncio.gather(save(b"\n% one"), save(b"\n% two"))
    assert sorted(len(result.potential_duplicates) for result in results) == [0, 1]


async def test_reextract_recovers_missing_page_without_approving_or_inventing_text(
    audit_pool, tmp_path: Path,
) -> None:
    curator = await _user(audit_pool, "reextract-curator", ["CURATOR"])
    output = BytesIO()
    document = pdfium.PdfDocument.new()
    page = document.new_page(595, 842)
    page.close()
    document.save(output)
    document.close()
    content = output.getvalue()
    original = "Điều 1. Quy định\r\n  Nội dung đúng"
    prepared = PreparedDraft(
        content, sha256(content).hexdigest(),
        [ExtractedPage(1, 595, 842, 0, original, (), text_quality="usable")],
        [ParsedNode("article", "Điều 1", "Điều 1. Quy định\nNội dung đúng", 1, 0.8),
         ParsedNode("paragraph", "", "Không có ở trang gốc", 1, 0.5)],
    )
    draft = await persist_draft(
        prepared, pool=audit_pool, store_root=tmp_path, title="Dữ liệu mô phỏng",
        doc_type="other", original_filename="test.pdf", submitted_by=curator,
    )
    async with audit_pool.acquire() as conn:
        await conn.execute(
            "UPDATE source_pages SET text_original=NULL WHERE document_version_id=$1",
            draft.document_version_id,
        )
        await conn.execute(
            "UPDATE document_nodes SET source_span_id=NULL WHERE document_version_id=$1",
            draft.document_version_id,
        )
    result = await apply_reextracted_draft(
        audit_pool, prepared=prepared, version_id=draft.document_version_id, curator_id=curator,
    )
    assert result["pages_restored"] == 1
    assert result["nodes_anchored"] == 1
    assert result["nodes_unresolved"] == 1
    async with audit_pool.acquire() as conn:
        assert await conn.fetchval(
            "SELECT text_original FROM source_pages WHERE document_version_id=$1",
            draft.document_version_id,
        ) == original
        assert await conn.fetchval(
            "SELECT review_status::text FROM document_versions WHERE id=$1",
            draft.document_version_id,
        ) == "draft"
        assert await conn.fetchval(
            "SELECT count(*) FROM document_nodes WHERE document_version_id=$1 "
            "AND source_span_id IS NOT NULL", draft.document_version_id,
        ) == 1
        assert await conn.fetchval(
            "SELECT verified_at FROM source_provenance WHERE document_version_id=$1",
            draft.document_version_id,
        ) is None
        assert await conn.fetchval(
            "SELECT count(*) FROM curator_review_tasks WHERE document_version_id=$1 "
            "AND reason='source_reextraction_review' AND status='open'",
            draft.document_version_id,
        ) == 1
        await conn.execute(
            "UPDATE source_pages SET text_original='Đã chỉnh sửa' WHERE document_version_id=$1",
            draft.document_version_id,
        )
    with pytest.raises(ReviewError, match="SOURCE_REEXTRACTION_CONFLICT"):
        await apply_reextracted_draft(
            audit_pool, prepared=prepared, version_id=draft.document_version_id, curator_id=curator,
        )
    async with audit_pool.acquire() as conn:
        assert await conn.fetchval(
            "SELECT text_original FROM source_pages WHERE document_version_id=$1",
            draft.document_version_id,
        ) == "Đã chỉnh sửa"
        await conn.execute(
            "UPDATE document_versions SET review_status='approved' WHERE id=$1",
            draft.document_version_id,
        )
    with pytest.raises(ReviewError, match="INVALID_REVIEW_STATE"):
        await apply_reextracted_draft(
            audit_pool, prepared=prepared, version_id=draft.document_version_id, curator_id=curator,
        )


def test_unconfigured_mutations_do_not_claim_success() -> None:
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/admin/model-registry",
            headers={"X-Principal-Id": str(uuid4()), "X-Roles": "SYS_ADMIN"},
            json={"profile_id": "test", "adapter": "none", "endpoint": "https://example.com",
                  "model_id": "test", "capabilities": ["answer"], "privacy_zone": "internal",
                  "revision": "test"},
        )
    assert response.status_code == 503
