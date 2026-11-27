"""PostgreSQL + FastAPI integration tests for Task D5: Conflicts, Triage & Authority Rules API."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import date
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import httpx
import pypdfium2 as pdfium
import pytest

from app.admin_services import create_category, create_or_update_user
from app.auth_acl import service as auth_service
from app.conflicts.worker import ConflictScanWorker
from app.documents.draft import PreparedDraft, persist_draft
from app.documents.native_pdf import ExtractedPage
from app.documents.review import approve_document_version, submit_draft_for_review
from app.documents.tree_parser import parse_legal_tree
from app.main import create_app
from app.migrations.runner import apply_migrations

_PASSWORD = "ConflictApiPgPassword!2026"
_DISCLAIMER = "Gợi ý tự động — cần chuyên viên thẩm định trước khi áp dụng."


def _blank_pdf(pages: int = 1) -> bytes:
    output = BytesIO()
    document = pdfium.PdfDocument.new()
    for _ in range(pages):
        document.new_page(595, 842).close()
    document.save(output)
    document.close()
    return output.getvalue() + f"\n% {uuid4().hex}\n".encode("ascii")


@pytest.fixture
async def conflict_api_pg_pool() -> AsyncIterator[asyncpg.Pool]:
    dsn = os.getenv("EVIDENCE_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Disposable PostgreSQL not configured")
    schema = "test_cmp_" + uuid4().hex
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
    username: str,
    roles: list[str],
    category_ids: list[UUID] | None = None,
) -> UUID:
    row = await create_or_update_user(
        pool,
        actor_id=uuid4(),
        username=username,
        display_name=username,
        password=_PASSWORD,
        roles=roles,
        category_ids=category_ids or [],
        must_change_password=False,
    )
    return UUID(row["id"])


async def _auth_headers(pool: asyncpg.Pool, username: str) -> dict[str, str]:
    result = await auth_service.login(
        pool, username=username, password=_PASSWORD, ttl_seconds=3600
    )
    return {"Authorization": f"Bearer {result.token}"}


def _make_app(pool: asyncpg.Pool, *, settings_overrides: dict[str, Any] | None = None) -> Any:
    app = create_app()
    overrides = {"dev_allow_in_memory_store": False, **(settings_overrides or {})}
    app.state.settings = replace(app.state.settings, **overrides)
    app.state.db_pool = pool
    return app


async def _seed_approved_doc(
    pool: asyncpg.Pool,
    store_root: Path,
    *,
    curator_id: UUID,
    reviewer_id: UUID,
    category_id: UUID,
    title: str,
    doc_number: str,
    doc_type: str,
    issuing_body: str,
    article_text: str,
    publication_date: date,
    effective_from: date,
) -> tuple[UUID, UUID, list[dict[str, Any]]]:
    pdf_bytes = _blank_pdf(1)
    pages = [ExtractedPage(1, 595, 842, 0, article_text, (), "native_pdf", "usable")]
    nodes = parse_legal_tree(pages)
    prepared = PreparedDraft(pdf_bytes, sha256(pdf_bytes).hexdigest(), pages, nodes)
    draft = await persist_draft(
        prepared,
        pool=pool,
        store_root=store_root,
        title=title,
        doc_type=doc_type,
        document_number=doc_number,
        issuing_body=issuing_body,
        publication_date=publication_date,
        original_filename=f"{uuid4().hex}.pdf",
        submitted_by=curator_id,
    )
    await submit_draft_for_review(pool, version_id=draft.document_version_id, curator_id=curator_id)
    await approve_document_version(
        pool,
        version_id=draft.document_version_id,
        reviewer_id=reviewer_id,
        category_ids=[category_id],
        store_root=store_root,
        max_bytes=10 * 1024 * 1024,
        review_note="Duyệt kiểm thử API xung đột",
        publication_date=publication_date,
        effective_from=effective_from,
        resolve_all_tasks=True,
    )
    async with pool.acquire() as conn:
        node_rows = await conn.fetch(
            """SELECT id, node_type, path, citation_label, text_original
               FROM document_nodes
               WHERE document_version_id = $1
               ORDER BY path""",
            draft.document_version_id,
        )
    return draft.document_id, draft.document_version_id, [dict(r) for r in node_rows]


async def test_scan_end_to_end_contradiction_and_authority_precedence(
    conflict_api_pg_pool: asyncpg.Pool, tmp_path: Path
) -> None:
    cat = await create_category(
        conflict_api_pg_pool, actor_id=uuid4(), name="Thuế", code="tax_d5"
    )
    cat_id = UUID(cat["id"])
    curator_id = await _create_user(conflict_api_pg_pool, "cur-s1", ["CURATOR"], [cat_id])
    reviewer_id = await _create_user(conflict_api_pg_pool, "rev-s1", ["REVIEWER"], [cat_id])
    await _create_user(conflict_api_pg_pool, "usr-s1", ["USER"], [cat_id])

    doc_decree, _, _ = await _seed_approved_doc(
        conflict_api_pg_pool,
        tmp_path,
        curator_id=curator_id,
        reviewer_id=reviewer_id,
        category_id=cat_id,
        title="Nghị định quy định thời hạn cấp phép",
        doc_number="10/2024/NĐ-CP",
        doc_type="decree",
        issuing_body="Chính phủ",
        article_text=(
            "Điều 1. Thời hạn giải quyết hồ sơ cấp phép là 10 ngày làm việc "
            "kể từ ngày nhận đủ hồ sơ."
        ),
        publication_date=date(2024, 1, 15),
        effective_from=date(2024, 3, 1),
    )
    doc_circular, _, _ = await _seed_approved_doc(
        conflict_api_pg_pool,
        tmp_path,
        curator_id=curator_id,
        reviewer_id=reviewer_id,
        category_id=cat_id,
        title="Thông tư hướng dẫn thời hạn cấp phép",
        doc_number="20/2024/TT-BTC",
        doc_type="circular",
        issuing_body="Bộ Tài chính",
        article_text=(
            "Điều 1. Thời hạn giải quyết hồ sơ cấp phép là 20 ngày làm việc "
            "kể từ ngày nhận đủ hồ sơ."
        ),
        publication_date=date(2024, 4, 1),
        effective_from=date(2024, 5, 15),
    )

    class _WakeSpy:
        def __init__(self) -> None:
            self.woken = False

        def wake(self) -> None:
            self.woken = True

    app = _make_app(conflict_api_pg_pool)
    wake_spy = _WakeSpy()
    app.state.conflict_scan_worker = wake_spy
    headers = await _auth_headers(conflict_api_pg_pool, "usr-s1")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        create_resp = await client.post(
            "/api/v1/conflicts/scans",
            headers=headers,
            json={
                "request_id": "scan-req-0001",
                "document_ids": [str(doc_decree), str(doc_circular)],
                "as_of_date": "2025-01-15",
            },
        )
        assert create_resp.status_code == 202
        assert create_resp.headers["cache-control"] == "no-store"
        assert wake_spy.woken is True
        created = create_resp.json()
        assert created["status"] == "queued"
        assert created["scope_document_count"] == 2
        assert created["deduplicated"] is False
        run_id = created["run_id"]

        list_resp = await client.get("/api/v1/conflicts/scans", headers=headers)
        assert list_resp.status_code == 200
        assert list_resp.headers["cache-control"] == "no-store"
        listed = list_resp.json()
        assert listed["total"] == 1
        assert listed["items"][0]["id"] == run_id

        worker = ConflictScanWorker(conflict_api_pg_pool, runtime=None)
        assert await worker.run_once() is True

        detail_resp = await client.get(f"/api/v1/conflicts/scans/{run_id}", headers=headers)
        assert detail_resp.status_code == 200
        assert detail_resp.headers["cache-control"] == "no-store"
        detail = detail_resp.json()
        assert detail["status"] == "completed"
        assert detail["disclaimer"] == _DISCLAIMER
        assert detail["hidden_due_to_acl"] == 0
        assert detail["total_findings"] >= 1
        finding = detail["findings"][0]
        assert finding["finding_type"] == "contradiction"
        expected_precedence = (
            "higher_authority_a"
            if finding["document_a_id"] == str(doc_decree)
            else "higher_authority_b"
        )
        assert finding["precedence_result"] == expected_precedence

    async with conflict_api_pg_pool.acquire() as conn:
        actions = [
            row["action"]
            for row in await conn.fetch(
                "SELECT action FROM audit_events WHERE target_id = $1 ORDER BY occurred_at ASC",
                run_id,
            )
        ]
    assert "conflict_scan.create" in actions
    assert "conflict_scan.complete" in actions


async def test_scan_idempotency_limits_and_cancel(
    conflict_api_pg_pool: asyncpg.Pool, tmp_path: Path
) -> None:
    cat = await create_category(
        conflict_api_pg_pool, actor_id=uuid4(), name="Hải quan", code="hq_d5"
    )
    cat_id = UUID(cat["id"])
    curator_id = await _create_user(conflict_api_pg_pool, "cur-s2", ["CURATOR"], [cat_id])
    reviewer_id = await _create_user(conflict_api_pg_pool, "rev-s2", ["REVIEWER"], [cat_id])
    await _create_user(conflict_api_pg_pool, "usr-s2a", ["USER"], [cat_id])
    await _create_user(conflict_api_pg_pool, "usr-s2b", ["USER"], [cat_id])

    doc_1, _, _ = await _seed_approved_doc(
        conflict_api_pg_pool,
        tmp_path,
        curator_id=curator_id,
        reviewer_id=reviewer_id,
        category_id=cat_id,
        title="Văn bản 1",
        doc_number="01/2024/NĐ-CP",
        doc_type="decree",
        issuing_body="Chính phủ",
        article_text="Điều 1. Thời hạn nộp hồ sơ là 05 ngày.",
        publication_date=date(2024, 1, 1),
        effective_from=date(2024, 2, 1),
    )
    doc_2, _, _ = await _seed_approved_doc(
        conflict_api_pg_pool,
        tmp_path,
        curator_id=curator_id,
        reviewer_id=reviewer_id,
        category_id=cat_id,
        title="Văn bản 2",
        doc_number="02/2024/TT-BTC",
        doc_type="circular",
        issuing_body="Bộ Tài chính",
        article_text="Điều 1. Thời hạn nộp hồ sơ là 15 ngày.",
        publication_date=date(2024, 1, 1),
        effective_from=date(2024, 2, 1),
    )
    doc_3, _, _ = await _seed_approved_doc(
        conflict_api_pg_pool,
        tmp_path,
        curator_id=curator_id,
        reviewer_id=reviewer_id,
        category_id=cat_id,
        title="Văn bản 3",
        doc_number="03/2024/TT-BTC",
        doc_type="circular",
        issuing_body="Bộ Tài chính",
        article_text="Điều 1. Thời hạn nộp hồ sơ là 20 ngày.",
        publication_date=date(2024, 1, 1),
        effective_from=date(2024, 2, 1),
    )

    app = _make_app(
        conflict_api_pg_pool,
        settings_overrides={"conflict_scan_max_documents": 2, "conflict_scan_max_queued": 1},
    )
    h_a = await _auth_headers(conflict_api_pg_pool, "usr-s2a")
    h_b = await _auth_headers(conflict_api_pg_pool, "usr-s2b")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        too_many = await client.post(
            "/api/v1/conflicts/scans",
            headers=h_a,
            json={
                "request_id": "req-too-many-docs",
                "document_ids": [str(doc_1), str(doc_2), str(doc_3)],
            },
        )
        assert too_many.status_code == 422
        assert too_many.json()["code"] == "CONFLICT_SCAN_TOO_MANY_DOCUMENTS"

        first = await client.post(
            "/api/v1/conflicts/scans",
            headers=h_a,
            json={
                "request_id": "req-idem-0001",
                "document_ids": [str(doc_1), str(doc_2)],
                "as_of_date": "2025-01-01",
            },
        )
        assert first.status_code == 202
        run_id = first.json()["run_id"]

        replay = await client.post(
            "/api/v1/conflicts/scans",
            headers=h_a,
            json={
                "request_id": "req-idem-0001",
                "document_ids": [str(doc_1), str(doc_2)],
                "as_of_date": "2025-01-01",
            },
        )
        assert replay.status_code == 202
        assert replay.json()["run_id"] == run_id
        assert replay.json()["deduplicated"] is True

        conflict = await client.post(
            "/api/v1/conflicts/scans",
            headers=h_a,
            json={
                "request_id": "req-idem-0001",
                "document_ids": [str(doc_1), str(doc_2)],
                "as_of_date": "2025-02-01",
            },
        )
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "CONFLICT_SCAN_IDEMPOTENCY_CONFLICT"

        q_full = await client.post(
            "/api/v1/conflicts/scans",
            headers=h_a,
            json={
                "request_id": "req-queue-full-2",
                "document_ids": [str(doc_1), str(doc_2)],
            },
        )
        assert q_full.status_code == 429
        assert q_full.json()["code"] == "CONFLICT_SCAN_QUEUE_FULL"

        other_cancel = await client.post(
            f"/api/v1/conflicts/scans/{run_id}/cancel", headers=h_b
        )
        assert other_cancel.status_code == 404
        assert other_cancel.json()["code"] == "CONFLICT_RUN_NOT_FOUND"

        cancelled = await client.post(
            f"/api/v1/conflicts/scans/{run_id}/cancel", headers=h_a
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        assert cancelled.json()["error_code"] == "CONFLICT_SCAN_CANCELLED"

        worker = ConflictScanWorker(conflict_api_pg_pool, runtime=None)
        assert await worker.run_once() is False


async def test_live_acl_revocation_and_suspension_hide_findings_without_leakage(
    conflict_api_pg_pool: asyncpg.Pool, tmp_path: Path
) -> None:
    cat_a = await create_category(
        conflict_api_pg_pool, actor_id=uuid4(), name="Danh mục A", code="ca_d5"
    )
    cat_b = await create_category(
        conflict_api_pg_pool, actor_id=uuid4(), name="Danh mục B", code="cb_d5"
    )
    cat_a_id, cat_b_id = UUID(cat_a["id"]), UUID(cat_b["id"])

    curator_id = await _create_user(
        conflict_api_pg_pool, "cur-s3", ["CURATOR"], [cat_a_id, cat_b_id]
    )
    reviewer_id = await _create_user(
        conflict_api_pg_pool, "rev-s3", ["REVIEWER"], [cat_a_id, cat_b_id]
    )
    user_id = await _create_user(
        conflict_api_pg_pool, "usr-s3", ["USER"], [cat_a_id, cat_b_id]
    )

    secret_phrase = "BÍ MẬT NỘI BỘ BỊ THU HỒI QUYỀN"
    doc_a, _, _ = await _seed_approved_doc(
        conflict_api_pg_pool,
        tmp_path,
        curator_id=curator_id,
        reviewer_id=reviewer_id,
        category_id=cat_a_id,
        title="Văn bản A công khai",
        doc_number="11/2024/NĐ-CP",
        doc_type="decree",
        issuing_body="Chính phủ",
        article_text="Điều 1. Thời hạn giải quyết hồ sơ hoàn thuế là 07 ngày làm việc.",
        publication_date=date(2024, 1, 10),
        effective_from=date(2024, 2, 1),
    )
    doc_b, _, _ = await _seed_approved_doc(
        conflict_api_pg_pool,
        tmp_path,
        curator_id=curator_id,
        reviewer_id=reviewer_id,
        category_id=cat_b_id,
        title="Văn bản B hạn chế",
        doc_number="22/2024/TT-BTC",
        doc_type="circular",
        issuing_body="Bộ Tài chính",
        article_text=(
            "Điều 1. Thời hạn giải quyết hồ sơ hoàn thuế là 30 ngày làm việc "
            f"({secret_phrase})."
        ),
        publication_date=date(2024, 3, 10),
        effective_from=date(2024, 4, 1),
    )

    app = _make_app(conflict_api_pg_pool)
    headers = await _auth_headers(conflict_api_pg_pool, "usr-s3")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        create_resp = await client.post(
            "/api/v1/conflicts/scans",
            headers=headers,
            json={
                "request_id": "req-acl-revoke-1",
                "document_ids": [str(doc_a), str(doc_b)],
            },
        )
        assert create_resp.status_code == 202
        run_id = create_resp.json()["run_id"]

        worker = ConflictScanWorker(conflict_api_pg_pool, runtime=None)
        assert await worker.run_once() is True

        before = await client.get(f"/api/v1/conflicts/scans/{run_id}", headers=headers)
        assert before.status_code == 200
        assert before.json()["total_findings"] >= 1
        assert before.json()["hidden_due_to_acl"] == 0

        # Revoke ACL on category B after scan completed
        async with conflict_api_pg_pool.acquire() as conn:
            await conn.execute(
                "UPDATE category_acl SET can_query = FALSE WHERE user_id = $1 AND category_id = $2",
                user_id,
                cat_b_id,
            )

        after_revoke = await client.get(f"/api/v1/conflicts/scans/{run_id}", headers=headers)
        assert after_revoke.status_code == 200
        body = after_revoke.json()
        assert body["findings"] == []
        assert body["total_findings"] == 0
        assert body["hidden_due_to_acl"] >= 1
        assert secret_phrase not in after_revoke.text
        assert "Văn bản B hạn chế" not in after_revoke.text

        # Restore ACL, then suspend doc_b -> still hidden
        async with conflict_api_pg_pool.acquire() as conn:
            await conn.execute(
                "UPDATE category_acl SET can_query = TRUE WHERE user_id = $1 AND category_id = $2",
                user_id,
                cat_b_id,
            )
            await conn.execute(
                "UPDATE documents SET suspended_at = now() WHERE id = $1",
                doc_b,
            )

        after_suspend = await client.get(f"/api/v1/conflicts/scans/{run_id}", headers=headers)
        assert after_suspend.status_code == 200
        assert after_suspend.json()["findings"] == []
        assert after_suspend.json()["hidden_due_to_acl"] >= 1
        assert secret_phrase not in after_suspend.text


async def test_worker_recover_interrupted_runs_marks_failed(
    conflict_api_pg_pool: asyncpg.Pool, tmp_path: Path
) -> None:
    cat = await create_category(
        conflict_api_pg_pool, actor_id=uuid4(), name="Phục hồi", code="rec_d5"
    )
    cat_id = UUID(cat["id"])
    curator_id = await _create_user(conflict_api_pg_pool, "cur-s4", ["CURATOR"], [cat_id])
    reviewer_id = await _create_user(conflict_api_pg_pool, "rev-s4", ["REVIEWER"], [cat_id])
    await _create_user(conflict_api_pg_pool, "usr-s4", ["USER"], [cat_id])

    doc_1, _, _ = await _seed_approved_doc(
        conflict_api_pg_pool,
        tmp_path,
        curator_id=curator_id,
        reviewer_id=reviewer_id,
        category_id=cat_id,
        title="Doc R1",
        doc_number="41/2024/NĐ-CP",
        doc_type="decree",
        issuing_body="Chính phủ",
        article_text="Điều 1. Nội dung quy định mẫu một.",
        publication_date=date(2024, 1, 1),
        effective_from=date(2024, 2, 1),
    )
    doc_2, _, _ = await _seed_approved_doc(
        conflict_api_pg_pool,
        tmp_path,
        curator_id=curator_id,
        reviewer_id=reviewer_id,
        category_id=cat_id,
        title="Doc R2",
        doc_number="42/2024/TT-BTC",
        doc_type="circular",
        issuing_body="Bộ Tài chính",
        article_text="Điều 1. Nội dung quy định mẫu hai.",
        publication_date=date(2024, 1, 1),
        effective_from=date(2024, 2, 1),
    )

    app = _make_app(conflict_api_pg_pool)
    headers = await _auth_headers(conflict_api_pg_pool, "usr-s4")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        resp = await client.post(
            "/api/v1/conflicts/scans",
            headers=headers,
            json={"request_id": "req-recover-0001", "document_ids": [str(doc_1), str(doc_2)]},
        )
        assert resp.status_code == 202
        run_id = resp.json()["run_id"]

        async with conflict_api_pg_pool.acquire() as conn:
            await conn.execute(
                """UPDATE conflict_review_runs
                   SET status = 'running',
                       lease_token = $2,
                       lease_expires_at = now() - interval '15 minutes',
                       started_at = now() - interval '20 minutes'
                   WHERE id = $1""",
                UUID(run_id),
                uuid4(),
            )

        worker = ConflictScanWorker(conflict_api_pg_pool, runtime=None)
        recovered = await worker.recover_interrupted_runs()
        assert recovered >= 1

        detail = await client.get(f"/api/v1/conflicts/scans/{run_id}", headers=headers)
        assert detail.status_code == 200
        assert detail.json()["status"] == "failed"
        assert detail.json()["error_code"] == "CONFLICT_SCAN_INTERRUPTED"


async def test_reviewer_triage_draft_amendment_and_can_review_guard(
    conflict_api_pg_pool: asyncpg.Pool, tmp_path: Path
) -> None:
    cat1 = await create_category(
        conflict_api_pg_pool, actor_id=uuid4(), name="Lĩnh vực 1", code="c1_d5"
    )
    cat2 = await create_category(
        conflict_api_pg_pool, actor_id=uuid4(), name="Lĩnh vực 2", code="c2_d5"
    )
    cat1_id, cat2_id = UUID(cat1["id"]), UUID(cat2["id"])

    curator_id = await _create_user(conflict_api_pg_pool, "cur-s5", ["CURATOR"], [cat1_id])
    rev_ok_id = await _create_user(conflict_api_pg_pool, "rev-ok", ["REVIEWER", "USER"], [cat1_id])
    await _create_user(conflict_api_pg_pool, "rev-no", ["REVIEWER", "USER"], [cat2_id])
    await _create_user(conflict_api_pg_pool, "usr-s5", ["USER"], [cat1_id])

    async with conflict_api_pg_pool.acquire() as conn:
        await conn.execute(
            "UPDATE category_acl SET can_review = TRUE WHERE user_id = $1 AND category_id = $2",
            rev_ok_id,
            cat1_id,
        )

    doc_a, _, _ = await _seed_approved_doc(
        conflict_api_pg_pool,
        tmp_path,
        curator_id=curator_id,
        reviewer_id=rev_ok_id,
        category_id=cat1_id,
        title="Nghị định Triage A",
        doc_number="51/2024/NĐ-CP",
        doc_type="decree",
        issuing_body="Chính phủ",
        article_text="Điều 1. Thời hạn nộp báo cáo tài chính là 30 ngày.",
        publication_date=date(2024, 1, 10),
        effective_from=date(2024, 2, 1),
    )
    doc_b, _, _ = await _seed_approved_doc(
        conflict_api_pg_pool,
        tmp_path,
        curator_id=curator_id,
        reviewer_id=rev_ok_id,
        category_id=cat1_id,
        title="Thông tư Triage B",
        doc_number="52/2024/TT-BTC",
        doc_type="circular",
        issuing_body="Bộ Tài chính",
        article_text="Điều 1. Thời hạn nộp báo cáo tài chính là 60 ngày.",
        publication_date=date(2024, 3, 10),
        effective_from=date(2024, 4, 1),
    )

    app = _make_app(conflict_api_pg_pool)
    h_user = await _auth_headers(conflict_api_pg_pool, "usr-s5")
    h_rev_ok = await _auth_headers(conflict_api_pg_pool, "rev-ok")
    h_rev_no = await _auth_headers(conflict_api_pg_pool, "rev-no")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        scan_resp = await client.post(
            "/api/v1/conflicts/scans",
            headers=h_user,
            json={"request_id": "req-triage-0001", "document_ids": [str(doc_a), str(doc_b)]},
        )
        assert scan_resp.status_code == 202
        worker = ConflictScanWorker(conflict_api_pg_pool, runtime=None)
        assert await worker.run_once() is True

        # Plain USER cannot access admin findings queue
        user_forbidden = await client.get("/api/v1/admin/conflicts/findings", headers=h_user)
        assert user_forbidden.status_code == 403
        assert user_forbidden.json()["code"] == "CURATOR_OR_REVIEWER_REQUIRED"

        # Reviewer without can_review on cat1 sees empty queue and gets 403 on review
        rev_no_list = await client.get("/api/v1/admin/conflicts/findings", headers=h_rev_no)
        assert rev_no_list.status_code == 200
        assert rev_no_list.json()["total"] == 0

        rev_ok_list = await client.get(
            "/api/v1/admin/conflicts/findings?review_status=pending", headers=h_rev_ok
        )
        assert rev_ok_list.status_code == 200
        assert rev_ok_list.headers["cache-control"] == "no-store"
        items = rev_ok_list.json()["items"]
        assert len(items) >= 1
        finding_id = items[0]["id"]

        rev_no_post = await client.post(
            f"/api/v1/admin/conflicts/findings/{finding_id}/review",
            headers=h_rev_no,
            json={"decision": "confirm"},
        )
        assert rev_no_post.status_code == 403
        assert rev_no_post.json()["code"] == "REVIEW_SCOPE_REQUIRED"

        missing_action = await client.post(
            f"/api/v1/admin/conflicts/findings/{finding_id}/review",
            headers=h_rev_ok,
            json={"decision": "confirm", "create_amendment_draft": True},
        )
        assert missing_action.status_code == 422
        assert missing_action.json()["code"] == "CONFLICT_AMENDMENT_ACTION_REQUIRED"

        reviewed = await client.post(
            f"/api/v1/admin/conflicts/findings/{finding_id}/review",
            headers=h_rev_ok,
            json={
                "decision": "confirm",
                "review_note": "Xác nhận và tạo đề xuất sửa đổi",
                "create_amendment_draft": True,
                "amendment_action": "modify",
                "source_side": "a",
            },
        )
        assert reviewed.status_code == 200
        assert reviewed.headers["cache-control"] == "no-store"
        rev_body = reviewed.json()
        assert rev_body["review_status"] == "linked_amendment"
        assert rev_body["amendment_review_status"] == "draft"
        amend_id = UUID(rev_body["linked_amendment_id"])

    async with conflict_api_pg_pool.acquire() as conn:
        amend = await conn.fetchrow("SELECT * FROM node_amendments WHERE id = $1", amend_id)
        assert amend is not None
        assert amend["review_status"] == "draft"
        assert amend["proposed_by"] == "conflict_review"
        assert amend["proposer_id"] == rev_ok_id
        assert amend["evidence_source"] == f"conflict_review:{finding_id}"

        audit_actions = [
            row["action"]
            for row in await conn.fetch(
                "SELECT action FROM audit_events WHERE target_id = $1 ORDER BY occurred_at ASC",
                finding_id,
            )
        ]
    assert "conflict_finding.review" in audit_actions
    assert "conflict_finding.create_amendment_draft" in audit_actions


async def test_admin_authority_rules_crud_and_next_scan_precedence(
    conflict_api_pg_pool: asyncpg.Pool, tmp_path: Path
) -> None:
    cat = await create_category(
        conflict_api_pg_pool, actor_id=uuid4(), name="Thứ bậc", code="auth_d5"
    )
    cat_id = UUID(cat["id"])
    curator_id = await _create_user(conflict_api_pg_pool, "cur-s6", ["CURATOR"], [cat_id])
    reviewer_id = await _create_user(conflict_api_pg_pool, "rev-s6", ["REVIEWER"], [cat_id])
    await _create_user(conflict_api_pg_pool, "usr-s6", ["USER"], [cat_id])
    await _create_user(conflict_api_pg_pool, "adm-s6", ["SYS_ADMIN", "USER"], [cat_id])

    doc_decree, _, _ = await _seed_approved_doc(
        conflict_api_pg_pool,
        tmp_path,
        curator_id=curator_id,
        reviewer_id=reviewer_id,
        category_id=cat_id,
        title="Nghị định Thứ bậc A",
        doc_number="61/2024/NĐ-CP",
        doc_type="decree",
        issuing_body="Chính phủ",
        article_text="Điều 1. Thời hạn thẩm định hồ sơ là 10 ngày làm việc.",
        publication_date=date(2024, 1, 10),
        effective_from=date(2024, 2, 1),
    )
    doc_circular, _, _ = await _seed_approved_doc(
        conflict_api_pg_pool,
        tmp_path,
        curator_id=curator_id,
        reviewer_id=reviewer_id,
        category_id=cat_id,
        title="Thông tư Thứ bậc B",
        doc_number="62/2024/TT-BTC",
        doc_type="circular",
        issuing_body="Bộ Tài chính",
        article_text="Điều 1. Thời hạn thẩm định hồ sơ là 25 ngày làm việc.",
        publication_date=date(2024, 3, 10),
        effective_from=date(2024, 4, 1),
    )

    app = _make_app(conflict_api_pg_pool)
    h_user = await _auth_headers(conflict_api_pg_pool, "usr-s6")
    h_admin = await _auth_headers(conflict_api_pg_pool, "adm-s6")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        denied = await client.get("/api/v1/admin/authority-rules", headers=h_user)
        assert denied.status_code == 403
        assert denied.json()["code"] == "ADMIN_REQUIRED"

        rules_resp = await client.get("/api/v1/admin/authority-rules", headers=h_admin)
        assert rules_resp.status_code == 200
        assert rules_resp.headers["cache-control"] == "no-store"
        rules = rules_resp.json()["items"]
        circular_rule = next(r for r in rules if r["rule_code"] == "circular_ministry")

        bad_regex = await client.post(
            "/api/v1/admin/authority-rules",
            headers=h_admin,
            json={
                "rule_code": "bad_regex_rule",
                "doc_type": "circular",
                "issuing_body_pattern": "[unclosed",
                "authority_rank": 15,
                "authority_tier_label": "Lỗi regex",
            },
        )
        assert bad_regex.status_code == 422
        assert bad_regex.json()["code"] == "INVALID_REGEX_PATTERN"

        dup_code = await client.post(
            "/api/v1/admin/authority-rules",
            headers=h_admin,
            json={
                "rule_code": "circular_ministry",
                "doc_type": "circular",
                "authority_rank": 15,
                "authority_tier_label": "Trùng mã",
            },
        )
        assert dup_code.status_code == 409
        assert dup_code.json()["code"] == "AUTHORITY_RULE_EXISTS"

        created_rule = await client.post(
            "/api/v1/admin/authority-rules",
            headers=h_admin,
            json={
                "rule_code": "circular_special_custom",
                "doc_type": "circular",
                "issuing_body_pattern": "bo tu phap",
                "authority_rank": 25,
                "authority_tier_label": "Thông tư đặc thù",
                "match_priority": 15,
                "note": "Quy tắc thử nghiệm",
            },
        )
        assert created_rule.status_code == 201
        created_rule_body = created_rule.json()
        assert created_rule_body["rule_code"] == "circular_special_custom"

        cleared_rule = await client.put(
            f"/api/v1/admin/authority-rules/{created_rule_body['id']}",
            headers=h_admin,
            json={"issuing_body_pattern": None, "is_active": False},
        )
        assert cleared_rule.status_code == 200
        assert cleared_rule.json()["issuing_body_pattern"] is None
        assert cleared_rule.json()["is_active"] is False

        # Scan 1: default ranks -> decree (30) outranks circular (40)
        scan1 = await client.post(
            "/api/v1/conflicts/scans",
            headers=h_user,
            json={
                "request_id": "req-prec-scan-1",
                "document_ids": [str(doc_decree), str(doc_circular)],
            },
        )
        assert scan1.status_code == 202
        run1_id = scan1.json()["run_id"]
        worker = ConflictScanWorker(conflict_api_pg_pool, runtime=None)
        assert await worker.run_once() is True

        d1 = (await client.get(f"/api/v1/conflicts/scans/{run1_id}", headers=h_user)).json()
        f1 = d1["findings"][0]
        expected_1 = (
            "higher_authority_a"
            if f1["document_a_id"] == str(doc_decree)
            else "higher_authority_b"
        )
        assert f1["precedence_result"] == expected_1

        # SYS_ADMIN updates circular_ministry rank to 20 (higher authority than decree's 30)
        upd = await client.put(
            f"/api/v1/admin/authority-rules/{circular_rule['id']}",
            headers=h_admin,
            json={"authority_rank": 20, "note": "Ưu tiên Thông tư thử nghiệm"},
        )
        assert upd.status_code == 200
        assert upd.json()["authority_rank"] == 20

        # Scan 2: circular (20) now outranks decree (30)
        scan2 = await client.post(
            "/api/v1/conflicts/scans",
            headers=h_user,
            json={
                "request_id": "req-prec-scan-2",
                "document_ids": [str(doc_decree), str(doc_circular)],
            },
        )
        assert scan2.status_code == 202
        run2_id = scan2.json()["run_id"]
        assert await worker.run_once() is True

        d2 = (await client.get(f"/api/v1/conflicts/scans/{run2_id}", headers=h_user)).json()
        f2 = d2["findings"][0]
        expected_2 = (
            "higher_authority_a"
            if f2["document_a_id"] == str(doc_circular)
            else "higher_authority_b"
        )
        assert f2["precedence_result"] == expected_2

    async with conflict_api_pg_pool.acquire() as conn:
        created_audit = await conn.fetchval(
            "SELECT count(*) FROM audit_events WHERE action = 'authority_rule.created'"
        )
        updated_audit = await conn.fetchval(
            "SELECT count(*) FROM audit_events WHERE action = 'authority_rule.updated'"
        )
    assert int(created_audit or 0) >= 1
    assert int(updated_audit or 0) >= 1


async def test_scan_doc_types_and_taxonomy_codes_scope_filtering(
    conflict_api_pg_pool: asyncpg.Pool, tmp_path: Path
) -> None:
    cat = await create_category(
        conflict_api_pg_pool, actor_id=uuid4(), name="Phạm vi", code="scope_d5"
    )
    cat_id = UUID(cat["id"])
    curator_id = await _create_user(conflict_api_pg_pool, "cur-s7", ["CURATOR"], [cat_id])
    reviewer_id = await _create_user(conflict_api_pg_pool, "rev-s7", ["REVIEWER"], [cat_id])
    await _create_user(conflict_api_pg_pool, "usr-s7", ["USER"], [cat_id])

    doc_decree, _, nodes_decree = await _seed_approved_doc(
        conflict_api_pg_pool,
        tmp_path,
        curator_id=curator_id,
        reviewer_id=reviewer_id,
        category_id=cat_id,
        title="Nghị định Thuế",
        doc_number="71/2024/NĐ-CP",
        doc_type="decree",
        issuing_body="Chính phủ",
        article_text=(
            "Điều 1. Thời hạn nộp hồ sơ thuế là 10 ngày làm việc.\n"
            "Điều 2. Quy định về kiểm tra chuyên ngành là 05 ngày làm việc."
        ),
        publication_date=date(2024, 1, 10),
        effective_from=date(2024, 2, 1),
    )
    doc_circular, _, nodes_circular = await _seed_approved_doc(
        conflict_api_pg_pool,
        tmp_path,
        curator_id=curator_id,
        reviewer_id=reviewer_id,
        category_id=cat_id,
        title="Thông tư Thuế",
        doc_number="72/2024/TT-BTC",
        doc_type="circular",
        issuing_body="Bộ Tài chính",
        article_text=(
            "Điều 1. Thời hạn nộp hồ sơ thuế là 20 ngày làm việc.\n"
            "Điều 2. Quy định về kiểm tra chuyên ngành là 30 ngày làm việc."
        ),
        publication_date=date(2024, 3, 10),
        effective_from=date(2024, 4, 1),
    )
    await _seed_approved_doc(
        conflict_api_pg_pool,
        tmp_path,
        curator_id=curator_id,
        reviewer_id=reviewer_id,
        category_id=cat_id,
        title="Quyết định khác",
        doc_number="73/2024/QĐ-TTg",
        doc_type="decision",
        issuing_body="Thủ tướng Chính phủ",
        article_text="Điều 1. Thời hạn nộp hồ sơ thuế là 40 ngày làm việc.",
        publication_date=date(2024, 3, 10),
        effective_from=date(2024, 4, 1),
    )

    tax_id = uuid4()
    d1_art1 = next(
        n["id"] for n in nodes_decree if n["text_original"].startswith("Điều 1.")
    )
    c1_art1 = next(
        n["id"] for n in nodes_circular if n["text_original"].startswith("Điều 1.")
    )
    async with conflict_api_pg_pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO content_taxonomy (id, code, name, sort_order)
               VALUES ($1, 'thue_gtgt', 'Thuế GTGT', 1)""",
            tax_id,
        )
        await conn.execute(
            """INSERT INTO node_labels (node_id, taxonomy_id, source, status)
               VALUES ($1, $2, 'person', 'approved'), ($3, $2, 'person', 'approved')""",
            d1_art1,
            tax_id,
            c1_art1,
        )

    app = _make_app(conflict_api_pg_pool)
    headers = await _auth_headers(conflict_api_pg_pool, "usr-s7")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        resp = await client.post(
            "/api/v1/conflicts/scans",
            headers=headers,
            json={
                "request_id": "req-scope-filter-1",
                "category_id": str(cat_id),
                "doc_types": ["decree", "circular"],
                "taxonomy_codes": ["thue_gtgt"],
            },
        )
        assert resp.status_code == 202
        body = resp.json()
        # Decision doc excluded by doc_types
        assert body["scope_document_count"] == 2
        run_id = body["run_id"]

        worker = ConflictScanWorker(conflict_api_pg_pool, runtime=None)
        assert await worker.run_once() is True

        detail = (await client.get(f"/api/v1/conflicts/scans/{run_id}", headers=headers)).json()
        assert detail["status"] == "completed"
        assert detail["summary_json"]["total_normative_nodes"] == 2
        assert detail["total_findings"] == 1
        f = detail["findings"][0]
        assert {f["document_a_id"], f["document_b_id"]} == {str(doc_decree), str(doc_circular)}
        assert {f["node_a_id"], f["node_b_id"]} == {str(d1_art1), str(c1_art1)}


async def test_sys_admin_only_can_cancel_other_user_scan(
    conflict_api_pg_pool: asyncpg.Pool, tmp_path: Path
) -> None:
    cat = await create_category(
        conflict_api_pg_pool, actor_id=uuid4(), name="Quản trị hủy", code="adm_cancel_d5"
    )
    cat_id = UUID(cat["id"])
    curator_id = await _create_user(conflict_api_pg_pool, "cur-adm-c", ["CURATOR"], [cat_id])
    reviewer_id = await _create_user(conflict_api_pg_pool, "rev-adm-c", ["REVIEWER"], [cat_id])
    await _create_user(conflict_api_pg_pool, "usr-adm-c1", ["USER"], [cat_id])
    await _create_user(conflict_api_pg_pool, "usr-adm-c2", ["USER"], [cat_id])
    await _create_user(conflict_api_pg_pool, "sysadmin-only", ["SYS_ADMIN"], [])

    doc_1, _, _ = await _seed_approved_doc(
        conflict_api_pg_pool,
        tmp_path,
        curator_id=curator_id,
        reviewer_id=reviewer_id,
        category_id=cat_id,
        title="Doc Cancel 1",
        doc_number="81/2024/NĐ-CP",
        doc_type="decree",
        issuing_body="Chính phủ",
        article_text="Điều 1. Thời hạn nộp hồ sơ là 10 ngày.",
        publication_date=date(2024, 1, 1),
        effective_from=date(2024, 2, 1),
    )
    doc_2, _, _ = await _seed_approved_doc(
        conflict_api_pg_pool,
        tmp_path,
        curator_id=curator_id,
        reviewer_id=reviewer_id,
        category_id=cat_id,
        title="Doc Cancel 2",
        doc_number="82/2024/TT-BTC",
        doc_type="circular",
        issuing_body="Bộ Tài chính",
        article_text="Điều 1. Thời hạn nộp hồ sơ là 20 ngày.",
        publication_date=date(2024, 1, 1),
        effective_from=date(2024, 2, 1),
    )

    app = _make_app(conflict_api_pg_pool)
    h_owner = await _auth_headers(conflict_api_pg_pool, "usr-adm-c1")
    h_other_user = await _auth_headers(conflict_api_pg_pool, "usr-adm-c2")
    h_curator = await _auth_headers(conflict_api_pg_pool, "cur-adm-c")
    h_admin_only = await _auth_headers(conflict_api_pg_pool, "sysadmin-only")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        created = await client.post(
            "/api/v1/conflicts/scans",
            headers=h_owner,
            json={
                "request_id": "req-admin-cancel-1",
                "document_ids": [str(doc_1), str(doc_2)],
            },
        )
        assert created.status_code == 202
        run_id = created.json()["run_id"]

        other_resp = await client.post(
            f"/api/v1/conflicts/scans/{run_id}/cancel", headers=h_other_user
        )
        assert other_resp.status_code == 404
        assert other_resp.json()["code"] == "CONFLICT_RUN_NOT_FOUND"

        curator_resp = await client.post(
            f"/api/v1/conflicts/scans/{run_id}/cancel", headers=h_curator
        )
        assert curator_resp.status_code == 403
        assert curator_resp.json()["code"] == "QUERY_REQUIRED"

        admin_resp = await client.post(
            f"/api/v1/conflicts/scans/{run_id}/cancel", headers=h_admin_only
        )
        assert admin_resp.status_code == 200
        assert admin_resp.json()["status"] == "cancelled"
        assert admin_resp.json()["error_code"] == "CONFLICT_SCAN_CANCELLED"


async def test_admin_findings_hides_degraded_source_and_unverified_provenance(
    conflict_api_pg_pool: asyncpg.Pool, tmp_path: Path
) -> None:
    cat = await create_category(
        conflict_api_pg_pool, actor_id=uuid4(), name="Toàn vẹn nguồn", code="integrity_d5"
    )
    cat_id = UUID(cat["id"])
    curator_id = await _create_user(conflict_api_pg_pool, "cur-int", ["CURATOR"], [cat_id])
    reviewer_id = await _create_user(
        conflict_api_pg_pool, "rev-int", ["REVIEWER", "USER"], [cat_id]
    )
    async with conflict_api_pg_pool.acquire() as conn:
        await conn.execute(
            "UPDATE category_acl SET can_review = TRUE WHERE user_id = $1 AND category_id = $2",
            reviewer_id,
            cat_id,
        )

    doc_a, _, _ = await _seed_approved_doc(
        conflict_api_pg_pool,
        tmp_path,
        curator_id=curator_id,
        reviewer_id=reviewer_id,
        category_id=cat_id,
        title="Doc Integrity A",
        doc_number="91/2024/NĐ-CP",
        doc_type="decree",
        issuing_body="Chính phủ",
        article_text="Điều 1. Thời hạn xác minh hồ sơ là 05 ngày làm việc.",
        publication_date=date(2024, 1, 1),
        effective_from=date(2024, 2, 1),
    )
    doc_b, ver_b, nodes_b = await _seed_approved_doc(
        conflict_api_pg_pool,
        tmp_path,
        curator_id=curator_id,
        reviewer_id=reviewer_id,
        category_id=cat_id,
        title="Doc Integrity B",
        doc_number="92/2024/TT-BTC",
        doc_type="circular",
        issuing_body="Bộ Tài chính",
        article_text="Điều 1. Thời hạn xác minh hồ sơ là 15 ngày làm việc.",
        publication_date=date(2024, 3, 1),
        effective_from=date(2024, 4, 1),
    )

    app = _make_app(conflict_api_pg_pool)
    h_rev = await _auth_headers(conflict_api_pg_pool, "rev-int")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        scan = await client.post(
            "/api/v1/conflicts/scans",
            headers=h_rev,
            json={"request_id": "req-integrity-1", "document_ids": [str(doc_a), str(doc_b)]},
        )
        assert scan.status_code == 202
        worker = ConflictScanWorker(conflict_api_pg_pool, runtime=None)
        assert await worker.run_once() is True

        visible = await client.get("/api/v1/admin/conflicts/findings", headers=h_rev)
        assert visible.status_code == 200
        assert visible.json()["total"] == 1

        # Degrade node_source_text_valid on node_b by changing source_page_id to NULL or
        # mismatching source_pages.text_original
        node_b_id = nodes_b[0]["id"]
        async with conflict_api_pg_pool.acquire() as conn:
            orig_page_text = await conn.fetchval(
                "SELECT text_original FROM source_pages WHERE document_version_id = $1",
                ver_b,
            )
            await conn.execute(
                """UPDATE source_pages
                   SET text_original = 'Nội dung trang đã bị thay đổi khác gốc'
                   WHERE document_version_id = $1""",
                ver_b,
            )
            assert (
                await conn.fetchval("SELECT node_source_text_valid($1)", node_b_id)
            ) is False

        degraded_src = await client.get("/api/v1/admin/conflicts/findings", headers=h_rev)
        assert degraded_src.status_code == 200
        assert degraded_src.json()["total"] == 0
        assert degraded_src.json()["items"] == []

        # Restore page text, then degrade source_provenance.verified_at
        async with conflict_api_pg_pool.acquire() as conn:
            await conn.execute(
                "UPDATE source_pages SET text_original = $2 WHERE document_version_id = $1",
                ver_b,
                orig_page_text,
            )
            assert (
                await conn.fetchval("SELECT node_source_text_valid($1)", node_b_id)
            ) is True
            await conn.execute(
                "UPDATE source_provenance SET verified_at = NULL WHERE document_version_id = $1",
                ver_b,
            )

        unverified_prov = await client.get("/api/v1/admin/conflicts/findings", headers=h_rev)
        assert unverified_prov.status_code == 200
        assert unverified_prov.json()["total"] == 0
        assert unverified_prov.json()["items"] == []
