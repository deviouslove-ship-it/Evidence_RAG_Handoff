"""PostgreSQL + FastAPI integration tests for Phase 1 comparison (C2 + audit fixes)."""

from __future__ import annotations

import json
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
from app.documents.draft import PreparedDraft, persist_draft
from app.documents.native_pdf import ExtractedPage
from app.documents.review import approve_document_version, submit_draft_for_review
from app.documents.tree_parser import parse_legal_tree
from app.main import create_app
from app.migrations.runner import apply_migrations
from app.model_registry.profiles import OperatingMode
from app.model_registry.runtime import GenerationOutcome

_PASSWORD = "ComparePgPassword!2026"
_DISCLAIMER = "Gợi ý tự động — cần chuyên viên thẩm định trước khi áp dụng"


def _blank_pdf(pages: int = 1) -> bytes:
    output = BytesIO()
    document = pdfium.PdfDocument.new()
    for _ in range(pages):
        document.new_page(595, 842).close()
    document.save(output)
    document.close()
    return output.getvalue() + f"\n% {uuid4().hex}\n".encode("ascii")


@pytest.fixture
async def comparison_pg_pool() -> AsyncIterator[asyncpg.Pool]:
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
    *,
    remote_ai_allowed: bool = False,
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
        remote_ai_allowed=remote_ai_allowed,
    )
    return UUID(row["id"])


async def _auth_headers(pool: asyncpg.Pool, username: str) -> dict[str, str]:
    result = await auth_service.login(
        pool, username=username, password=_PASSWORD, ttl_seconds=3600
    )
    return {"Authorization": f"Bearer {result.token}"}


def _make_app(pool: asyncpg.Pool, *, runtime: Any = None) -> Any:
    app = create_app()
    app.state.settings = replace(app.state.settings, dev_allow_in_memory_store=False)
    app.state.db_pool = pool
    if runtime is not None:
        app.state.ai_runtime = runtime
    return app


async def _seed_version(
    pool: asyncpg.Pool,
    store_root: Path,
    *,
    curator_id: UUID,
    reviewer_id: UUID,
    category_id: UUID,
    title: str,
    doc_number: str | None,
    doc_type: str,
    page_texts: list[str],
    approve: bool = True,
    publication_date: date | None = None,
    effective_from: date | None = None,
    document_id: UUID | None = None,
    version_number: int = 1,
    based_on_version_id: UUID | None = None,
    retire_based_on: bool = False,
) -> tuple[UUID, UUID, list[dict[str, Any]]]:
    """Persist real parsed nodes via write_nodes and optionally submit+approve."""
    pdf_bytes = _blank_pdf(len(page_texts))
    pages = [
        ExtractedPage(index + 1, 595, 842, 0, text, (), "native_pdf", "usable")
        for index, text in enumerate(page_texts)
    ]
    nodes = parse_legal_tree(pages)
    prepared = PreparedDraft(pdf_bytes, sha256(pdf_bytes).hexdigest(), pages, nodes)
    if document_id is None:
        draft = await persist_draft(
            prepared,
            pool=pool,
            store_root=store_root,
            title=title,
            doc_type=doc_type,
            document_number=doc_number,
            publication_date=publication_date,
            original_filename=f"{uuid4().hex}.pdf",
            submitted_by=curator_id,
        )
        doc_uuid = draft.document_id
        ver_uuid = draft.document_version_id
    else:
        # Persist as a new document first then re-parent? Better: insert version directly
        # via persist_draft is tied to new_original_base requiring admin_metadata; instead,
        # use persist_draft on a fresh document or create version row and call write_nodes.
        from app.documents.node_writer import write_nodes
        from app.documents.provenance import save_immutable_pdf

        source = save_immutable_pdf(prepared.content, store_root / "originals")
        ver_uuid = uuid4()
        doc_uuid = document_id
        async with pool.acquire() as conn, conn.transaction():
            await conn.execute(
                """INSERT INTO document_versions
                   (id, document_id, publication_date, effective_from,
                    original_file_path, original_file_sha256, original_filename,
                    review_status, submitted_by, source_format, version_number,
                    based_on_version_id)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, 'draft', $8, 'pdf', $9, $10)""",
                ver_uuid, doc_uuid, publication_date, effective_from,
                f"originals/{source.sha256}.pdf", source.sha256, f"{uuid4().hex}.pdf",
                curator_id, version_number, based_on_version_id,
            )
            await conn.execute(
                """INSERT INTO source_provenance (document_version_id, fetched_checksum)
                   VALUES ($1, $2)""",
                ver_uuid, source.sha256,
            )
            page_ids: dict[int, UUID] = {}
            for page in pages:
                page_id = uuid4()
                page_ids[page.page_number] = page_id
                await conn.execute(
                    """INSERT INTO source_pages
                       (id, document_version_id, page_number, width, height, rotation,
                        extraction_method, text_quality, text_original)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
                    page_id, ver_uuid, page.page_number, page.width, page.height,
                    page.rotation, page.extraction_method, page.text_quality, page.text,
                )
            await write_nodes(
                conn,
                document_id=doc_uuid,
                version_id=ver_uuid,
                title=title,
                document_number=doc_number,
                page_ids=page_ids,
                page_texts={p.page_number: p.text for p in pages},
                nodes=nodes,
            )
    if approve:
        await submit_draft_for_review(pool, version_id=ver_uuid, curator_id=curator_id)
        await approve_document_version(
            pool,
            version_id=ver_uuid,
            reviewer_id=reviewer_id,
            category_ids=[category_id],
            store_root=store_root,
            max_bytes=10 * 1024 * 1024,
            review_note="Duyệt kiểm thử HƯ CẤU",
            publication_date=publication_date,
            effective_from=effective_from,
            resolve_all_tasks=True,
        )
        if retire_based_on and based_on_version_id is not None:
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE document_versions SET retired_at = now() WHERE id = $1",
                    based_on_version_id,
                )
    async with pool.acquire() as conn:
        node_rows = await conn.fetch(
            """SELECT id, node_type, path, citation_label, text_original,
                      node_source_text_valid(id) AS source_valid
               FROM document_nodes
               WHERE document_version_id = $1
               ORDER BY path""",
            ver_uuid,
        )
    return doc_uuid, ver_uuid, [dict(r) for r in node_rows]


class _FakeRuntime:
    def __init__(self, mode: OperatingMode, reply: str | None) -> None:
        self.mode = mode
        self._reply = reply
        self.calls: list[dict[str, Any]] = []

    async def generate(
        self,
        stage: str,
        messages: list[dict[str, str]],
        *,
        principal_id: UUID,
        document_ids: list[UUID],
        parse: Any = None,
    ) -> GenerationOutcome:
        self.calls.append({
            "stage": stage,
            "messages": messages,
            "principal_id": principal_id,
            "document_ids": document_ids,
        })
        if self._reply is None:
            return GenerationOutcome(content=None)
        parsed = parse(self._reply) if parse is not None else self._reply
        return GenerationOutcome(
            content=parsed,
            external_api_used=(self.mode == OperatingMode.API),
            limited=False,
        )


async def test_acl_isolation_across_all_comparison_routes(
    comparison_pg_pool: asyncpg.Pool, tmp_path: Path
) -> None:
    cat_a = await create_category(comparison_pg_pool, actor_id=uuid4(), code="CA", name="Cat A")
    cat_b = await create_category(comparison_pg_pool, actor_id=uuid4(), code="CB", name="Cat B")
    cat_a_id, cat_b_id = UUID(cat_a["id"]), UUID(cat_b["id"])

    curator = await _create_user(
        comparison_pg_pool, "acl-curator", ["CURATOR"], [cat_a_id, cat_b_id]
    )
    reviewer = await _create_user(
        comparison_pg_pool, "acl-reviewer", ["REVIEWER"], [cat_a_id, cat_b_id]
    )
    await _create_user(comparison_pg_pool, "user-a", ["USER"], [cat_a_id])
    await _create_user(comparison_pg_pool, "user-b", ["USER"], [cat_b_id])

    doc_a, _, nodes_a = await _seed_version(
        comparison_pg_pool, tmp_path,
        curator_id=curator, reviewer_id=reviewer, category_id=cat_a_id,
        title="Nghị định A HƯ CẤU", doc_number="10/2025/NĐ-CP", doc_type="decree",
        page_texts=["Điều 1. Phạm vi\n1. Quy định chung tại mục A."],
    )
    doc_b, _, _ = await _seed_version(
        comparison_pg_pool, tmp_path,
        curator_id=curator, reviewer_id=reviewer, category_id=cat_b_id,
        title="Nghị định B HƯ CẤU", doc_number="20/2025/NĐ-CP", doc_type="decree",
        page_texts=["Điều 1. Phạm vi\n1. Quy định chung tại mục B."],
    )

    app = _make_app(comparison_pg_pool)
    headers_a = await _auth_headers(comparison_pg_pool, "user-a")
    headers_b = await _auth_headers(comparison_pg_pool, "user-b")
    node_a_id = nodes_a[0]["id"]

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get(f"/api/v1/documents/{doc_a}/versions")).status_code == 401

        ok_ver = await client.get(f"/api/v1/documents/{doc_a}/versions", headers=headers_a)
        assert ok_ver.status_code == 200
        assert ok_ver.headers.get("cache-control") == "no-store"

        r_ver = await client.get(f"/api/v1/documents/{doc_a}/versions", headers=headers_b)
        assert r_ver.status_code == 404
        assert r_ver.json()["code"] == "DOCUMENT_NOT_FOUND"

        r_cmp = await client.post(
            "/api/v1/compare/documents",
            headers=headers_b,
            json={
                "mode": "cross_document",
                "left_document_id": str(doc_b),
                "right_document_id": str(doc_a),
            },
        )
        assert r_cmp.status_code == 404
        assert r_cmp.json()["code"] == "DOCUMENT_NOT_FOUND"

        r_node = await client.get(f"/api/v1/nodes/{node_a_id}/diff", headers=headers_b)
        assert r_node.status_code == 404
        assert r_node.json()["code"] == "DOCUMENT_NOT_FOUND"

        r_sum = await client.post(
            "/api/v1/compare/summarize",
            headers=headers_b,
            json={
                "mode": "cross_document",
                "left_document_id": str(doc_a),
                "right_document_id": str(doc_b),
            },
        )
        assert r_sum.status_code == 404
        assert r_sum.json()["code"] == "DOCUMENT_NOT_FOUND"


async def test_versions_retired_draft_suspended_and_validation_errors(
    comparison_pg_pool: asyncpg.Pool, tmp_path: Path
) -> None:
    cat = await create_category(comparison_pg_pool, actor_id=uuid4(), code="VER", name="Versions")
    cat_id = UUID(cat["id"])
    curator = await _create_user(comparison_pg_pool, "ver-curator", ["CURATOR"], [cat_id])
    reviewer = await _create_user(comparison_pg_pool, "ver-reviewer", ["REVIEWER"], [cat_id])
    await _create_user(comparison_pg_pool, "ver-reader", ["USER"], [cat_id])

    doc_id, v1_id, _ = await _seed_version(
        comparison_pg_pool, tmp_path,
        curator_id=curator, reviewer_id=reviewer, category_id=cat_id,
        title="Thông tư phiên bản HƯ CẤU", doc_number="30/2024/TT-BTC", doc_type="circular",
        page_texts=[
            "Điều 1. Phạm vi\n1. Áp dụng cho tổ chức.\n"
            "Điều 2. Thời hạn\n1. Tổ chức được phép nộp hồ sơ trong thời hạn 10 ngày."
        ],
        publication_date=date(2024, 1, 10),
        effective_from=date(2024, 3, 1),
    )
    _, v2_id, v2_nodes = await _seed_version(
        comparison_pg_pool, tmp_path,
        curator_id=curator, reviewer_id=reviewer, category_id=cat_id,
        title="Thông tư phiên bản HƯ CẤU", doc_number="30/2024/TT-BTC", doc_type="circular",
        page_texts=[
            "Điều 1. Phạm vi\n1. Áp dụng cho tổ chức.\n"
            "Điều 2. Thời hạn\n1. Tổ chức phải nộp hồ sơ trong thời hạn 15 ngày."
        ],
        publication_date=date(2025, 1, 10),
        effective_from=date(2025, 3, 1),
        document_id=doc_id,
        version_number=2,
        based_on_version_id=v1_id,
        retire_based_on=True,
    )
    _, v3_draft_id, _ = await _seed_version(
        comparison_pg_pool, tmp_path,
        curator_id=curator, reviewer_id=reviewer, category_id=cat_id,
        title="Thông tư phiên bản HƯ CẤU", doc_number="30/2024/TT-BTC", doc_type="circular",
        page_texts=["Điều 1. Phạm vi\n1. Bản nháp 99 ngày."],
        approve=False,
        document_id=doc_id,
        version_number=3,
        based_on_version_id=v2_id,
    )
    other_doc_id, _, _ = await _seed_version(
        comparison_pg_pool, tmp_path,
        curator_id=curator, reviewer_id=reviewer, category_id=cat_id,
        title="Thông tư khác HƯ CẤU", doc_number="31/2024/TT-BTC", doc_type="circular",
        page_texts=["Điều 1. Khác."],
    )

    app = _make_app(comparison_pg_pool)
    headers = await _auth_headers(comparison_pg_pool, "ver-reader")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        ver_resp = await client.get(f"/api/v1/documents/{doc_id}/versions", headers=headers)
        assert ver_resp.status_code == 200
        ver_body = ver_resp.json()
        assert [v["version_number"] for v in ver_body["versions"]] == [2, 1]
        assert ver_body["versions"][0]["is_current"] is True
        assert ver_body["versions"][1]["is_current"] is False
        assert ver_body["versions"][0]["reviewed_at"] is not None

        # Historical retired v1 vs current v2 -> 200 OK
        cmp_resp = await client.post(
            "/api/v1/compare/documents",
            headers=headers,
            json={
                "mode": "versions",
                "left_document_id": str(doc_id),
                "right_document_id": str(doc_id),
                "left_version_id": str(v1_id),
                "right_version_id": str(v2_id),
                "as_of_date": "2025-06-01",
            },
        )
        assert cmp_resp.status_code == 200, cmp_resp.text
        assert cmp_resp.headers.get("cache-control") == "no-store"
        cmp_data = cmp_resp.json()
        assert cmp_data["left_doc"]["version_number"] == 1
        assert cmp_data["right_doc"]["version_number"] == 2
        assert cmp_data["summary"]["modified"] >= 1
        assert cmp_data["summary"]["high_impact_changes"] >= 1
        assert cmp_data["disclaimer"] == _DISCLAIMER
        modified_clause = next(
            item for item in cmp_data["items"]
            if item["change_kind"] == "modified"
            and item["left"]["structural_key"] == "dieu:2/khoan:1"
        )
        assert modified_clause["impact_level"] == "high"
        deadline_nums = {
            s["value_num"] for s in modified_clause["signals"]["deadlines_changed"]
        }
        assert deadline_nums == {10.0, 15.0}
        assert modified_clause["signals"]["modality_shifted"] is True

        # Draft v3 -> 404 COMPARE_VERSION_NOT_FOUND
        draft_resp = await client.post(
            "/api/v1/compare/documents",
            headers=headers,
            json={
                "mode": "versions",
                "left_document_id": str(doc_id),
                "right_document_id": str(doc_id),
                "left_version_id": str(v2_id),
                "right_version_id": str(v3_draft_id),
            },
        )
        assert draft_resp.status_code == 404
        assert draft_resp.json()["code"] == "COMPARE_VERSION_NOT_FOUND"

        # Mode mismatch -> 422 COMPARE_MODE_MISMATCH
        mismatch_resp = await client.post(
            "/api/v1/compare/documents",
            headers=headers,
            json={
                "mode": "versions",
                "left_document_id": str(doc_id),
                "right_document_id": str(other_doc_id),
            },
        )
        assert mismatch_resp.status_code == 422
        assert mismatch_resp.json()["code"] == "COMPARE_MODE_MISMATCH"

        # Same target -> 422 COMPARE_SAME_TARGET
        same_resp = await client.post(
            "/api/v1/compare/documents",
            headers=headers,
            json={
                "mode": "versions",
                "left_document_id": str(doc_id),
                "right_document_id": str(doc_id),
            },
        )
        assert same_resp.status_code == 422
        assert same_resp.json()["code"] == "COMPARE_SAME_TARGET"

        # A5 node diff on v2 clause -> previous v1 found
        v2_clause = next(n for n in v2_nodes if n["path"].endswith("dieu:2/khoan:1"))
        node_diff_resp = await client.get(
            f"/api/v1/nodes/{v2_clause['id']}/diff?as_of_date=2025-06-01", headers=headers
        )
        assert node_diff_resp.status_code == 200
        nd = node_diff_resp.json()
        assert nd["has_previous"] is True
        assert nd["previous_version"]["version_number"] == 1
        assert nd["change_kind"] == "modified"
        assert nd["impact_level"] == "high"
        assert nd["message"] is None

        # Suspended document -> 404 DOCUMENT_NOT_FOUND everywhere
        async with comparison_pg_pool.acquire() as conn:
            await conn.execute(
                "UPDATE documents SET suspended_at = now() WHERE id = $1", doc_id
            )
            audit_count = await conn.fetchval(
                "SELECT count(*) FROM audit_events "
                "WHERE action = 'document.compare' AND target_id = $1",
                str(doc_id),
            )
        assert int(audit_count) == 1

        assert (await client.get(f"/api/v1/documents/{doc_id}/versions", headers=headers)).json()[
            "code"
        ] == "DOCUMENT_NOT_FOUND"
        assert (
            await client.post(
                "/api/v1/compare/documents",
                headers=headers,
                json={
                    "mode": "versions",
                    "left_document_id": str(doc_id),
                    "right_document_id": str(doc_id),
                    "left_version_id": str(v1_id),
                    "right_version_id": str(v2_id),
                },
            )
        ).json()["code"] == "DOCUMENT_NOT_FOUND"
        assert (
            await client.get(f"/api/v1/nodes/{v2_clause['id']}/diff", headers=headers)
        ).json()["code"] == "DOCUMENT_NOT_FOUND"


async def test_amendment_pair_bidirectional_tiep_and_a5_amendments(
    comparison_pg_pool: asyncpg.Pool, tmp_path: Path
) -> None:
    cat = await create_category(comparison_pg_pool, actor_id=uuid4(), code="AMD", name="Amendments")
    cat_id = UUID(cat["id"])
    curator = await _create_user(comparison_pg_pool, "amd-curator", ["CURATOR"], [cat_id])
    reviewer = await _create_user(comparison_pg_pool, "amd-reviewer", ["REVIEWER"], [cat_id])
    await _create_user(comparison_pg_pool, "amd-reader", ["USER"], [cat_id])

    long_clause = "1. " + ("Nội dung quy định gốc về xử lý hồ sơ. " * 105)
    orig_page = (
        "Điều 2. Hồ sơ\n"
        f"{long_clause}\n"
        "Phần tiếp theo của khoản 1 Điều 2 quy định nộp 10 ngày.\n"
        "Điều 3. Lệ phí\n"
        "1. Mức thu là 100.000 đồng."
    )
    doc_a, _, nodes_a = await _seed_version(
        comparison_pg_pool, tmp_path,
        curator_id=curator, reviewer_id=reviewer, category_id=cat_id,
        title="Nghị định gốc HƯ CẤU", doc_number="10/2020/NĐ-CP", doc_type="decree",
        page_texts=[orig_page],
        effective_from=date(2020, 5, 1),
    )
    # Verify real write_nodes produced 000001: prefixes, tiep:2, and valid spans
    assert all(n["source_valid"] for n in nodes_a)
    a_d2k1 = next(n for n in nodes_a if n["path"].endswith("dieu:2/khoan:1"))
    a_d2k1_tiep = next(n for n in nodes_a if n["path"].endswith("dieu:2/khoan:1/tiep:2"))
    a_d3k1 = next(n for n in nodes_a if n["path"].endswith("dieu:3/khoan:1"))

    doc_b, _, nodes_b = await _seed_version(
        comparison_pg_pool, tmp_path,
        curator_id=curator, reviewer_id=reviewer, category_id=cat_id,
        title="Nghị định sửa đổi HƯ CẤU", doc_number="50/2025/NĐ-CP", doc_type="decree",
        page_texts=[
            "Điều 1. Sửa đổi bổ sung\n"
            "1. Sửa đổi khoản 1 Điều 2 thành nộp 20 ngày.\n"
            "2. Thay thế khoản 1 Điều 3 thành 200.000 đồng."
        ],
        effective_from=date(2025, 6, 1),
    )
    b_k1 = next(n for n in nodes_b if n["path"].endswith("dieu:1/khoan:1"))
    b_k2 = next(n for n in nodes_b if n["path"].endswith("dieu:1/khoan:2"))

    async with comparison_pg_pool.acquire() as conn:
        # Link 1: targets tiep:2 member id directly (approved)
        await conn.execute(
            """INSERT INTO node_amendments
               (source_node_id, source_document_id, target_document_id, target_node_id,
                scope, action, valid_from, evidence_source, review_status, source_quote)
               VALUES ($1, $2, $3, $4, 'node', 'modify', $5, 'manual', 'approved', $6)""",
            b_k1["id"], doc_b, doc_a, a_d2k1_tiep["id"],
            date(2025, 6, 1), "Sửa đổi khoản 1 Điều 2 như sau:",
        )
        # Link 2: path-only target (target_node_id IS NULL, scope='node', target_path set)
        await conn.execute(
            """INSERT INTO node_amendments
               (source_node_id, source_document_id, target_document_id, target_node_id,
                target_path, scope, action, valid_from, evidence_source, review_status,
                source_quote)
               VALUES ($1, $2, $3, NULL, $4, 'node', 'replace', $5, 'manual', 'approved', $6)""",
            b_k2["id"], doc_b, doc_a, "000005:dieu:03/khoan:01",
            date(2025, 7, 1), "Thay thế khoản 1 Điều 3 như sau:",
        )
        # Link 3: draft link (must be ignored everywhere)
        await conn.execute(
            """INSERT INTO node_amendments
               (source_node_id, source_document_id, target_document_id, target_node_id,
                scope, action, valid_from, evidence_source, review_status)
               VALUES ($1, $2, $3, $4, 'node', 'add', $5, 'manual', 'draft')""",
            b_k1["id"], doc_b, doc_a, a_d3k1["id"], date(2025, 8, 1),
        )

    app = _make_app(comparison_pg_pool)
    headers = await _auth_headers(comparison_pg_pool, "amd-reader")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        ver_a = (await client.get(f"/api/v1/documents/{doc_a}/versions", headers=headers)).json()
        assert len(ver_a["related_amendment_documents"]) == 1
        rel_b = ver_a["related_amendment_documents"][0]
        assert rel_b["id"] == str(doc_b)
        assert rel_b["directions"] == ["amends_this_document"]
        assert rel_b["actions"] == ["modify", "replace"]

        ver_b = (await client.get(f"/api/v1/documents/{doc_b}/versions", headers=headers)).json()
        assert ver_b["related_amendment_documents"][0]["directions"] == [
            "amended_by_this_document"
        ]

        # UI default: left = original (docA), right = amending (docB)
        cmp_default = await client.post(
            "/api/v1/compare/documents",
            headers=headers,
            json={
                "mode": "amendment_pair",
                "left_document_id": str(doc_a),
                "right_document_id": str(doc_b),
            },
        )
        assert cmp_default.status_code == 200, cmp_default.text
        default_data = cmp_default.json()
        assert default_data["summary"]["explicit_amendment_links"] == 2
        explicit_default = [
            i for i in default_data["items"] if i["alignment_method"] == "explicit_amendment"
        ]
        assert len(explicit_default) == 2
        d2_item = next(
            i for i in explicit_default if i["left"]["structural_key"] == "dieu:2/khoan:1"
        )
        assert d2_item["left"]["member_node_ids"] == [str(a_d2k1["id"]), str(a_d2k1_tiep["id"])]
        assert d2_item["right"]["node_id"] == str(b_k1["id"])
        assert d2_item["amendment_link"]["action"] == "modify"
        assert d2_item["amendment_link"]["valid_from"] == "2025-06-01"

        # Reverse direction: left = amending (docB), right = original (docA)
        cmp_reverse = await client.post(
            "/api/v1/compare/documents",
            headers=headers,
            json={
                "mode": "amendment_pair",
                "left_document_id": str(doc_b),
                "right_document_id": str(doc_a),
            },
        )
        assert cmp_reverse.status_code == 200
        assert cmp_reverse.json()["summary"]["explicit_amendment_links"] == 2

        # A5 node diff on primary node of stitched tiep:2 -> finds Link 1 + no prev msg
        nd_d2 = await client.get(f"/api/v1/nodes/{a_d2k1['id']}/diff", headers=headers)
        assert nd_d2.status_code == 200
        nd_d2_data = nd_d2.json()
        assert nd_d2_data["has_previous"] is False
        assert nd_d2_data["message"] == "Không có phiên bản trước của văn bản này trong kho."
        assert nd_d2_data["current"]["member_node_ids"] == [
            str(a_d2k1["id"]),
            str(a_d2k1_tiep["id"]),
        ]
        assert [a["action"] for a in nd_d2_data["amendments"]] == ["modify"]
        assert nd_d2_data["amendments"][0]["source_document"]["id"] == str(doc_b)

        # A5 node diff on d3k1 -> finds Link 2 via path-only match, ignores draft Link 3
        nd_d3 = await client.get(f"/api/v1/nodes/{a_d3k1['id']}/diff", headers=headers)
        assert nd_d3.status_code == 200
        nd_d3_data = nd_d3.json()
        assert nd_d3_data["has_previous"] is False
        assert [a["action"] for a in nd_d3_data["amendments"]] == ["replace"]


async def test_renumbered_articles_and_non_article_admin_doc_via_write_nodes(
    comparison_pg_pool: asyncpg.Pool, tmp_path: Path
) -> None:
    cat = await create_category(comparison_pg_pool, actor_id=uuid4(), code="ADM", name="Admin")
    cat_id = UUID(cat["id"])
    curator = await _create_user(comparison_pg_pool, "adm-curator", ["CURATOR"], [cat_id])
    reviewer = await _create_user(comparison_pg_pool, "adm-reviewer", ["REVIEWER"], [cat_id])
    await _create_user(comparison_pg_pool, "adm-reader", ["USER"], [cat_id])

    # Renumbered article: insert a new Điều 2 so old Điều 2 becomes Điều 3.
    v1_text = (
        "Điều 1. Quy định chung\n"
        "1. Phạm vi áp dụng toàn quốc.\n"
        "Điều 2. Huấn luyện an toàn\n"
        "1. Huấn luyện an toàn lao động cho người lao động trong doanh nghiệp.\n"
    )
    v2_text = (
        "Điều 1. Quy định chung\n"
        "1. Phạm vi áp dụng toàn quốc.\n"
        "Điều 2. Quản lý ngân sách\n"
        "1. Quản lý thu chi ngân sách và kiểm soát kinh phí công đoàn.\n"
        "Điều 3. Huấn luyện an toàn\n"
        "1. Huấn luyện an toàn lao động cho người lao động trong doanh nghiệp.\n"
    )
    doc_renum, v1_id, _ = await _seed_version(
        comparison_pg_pool, tmp_path,
        curator_id=curator, reviewer_id=reviewer, category_id=cat_id,
        title="Quy chế đánh số lại HƯ CẤU", doc_number="40/2024/QĐ", doc_type="decision",
        page_texts=[v1_text],
    )
    _, v2_id, _ = await _seed_version(
        comparison_pg_pool, tmp_path,
        curator_id=curator, reviewer_id=reviewer, category_id=cat_id,
        title="Quy chế đánh số lại HƯ CẤU", doc_number="40/2024/QĐ", doc_type="decision",
        page_texts=[v2_text],
        document_id=doc_renum, version_number=2, based_on_version_id=v1_id, retire_based_on=True,
    )

    # Non-article admin document (headings + paragraphs only, no Điều).
    admin_v1 = (
        "Chương I. Mục đích và phạm vi\n"
        "Kế hoạch nhằm nâng cao chất lượng dịch vụ công trực tuyến.\n"
        "Chương II. Tổ chức thực hiện\n"
        "Các đơn vị triển khai đào tạo cán bộ và kiểm tra định kỳ."
    )
    admin_v2 = (
        "Chương I. Mục đích và phạm vi\n"
        "Kế hoạch nhằm nâng cao chất lượng dịch vụ công trực tuyến mức độ bốn.\n"
        "Chương II. Tổ chức thực hiện\n"
        "Các đơn vị triển khai đào tạo cán bộ và kiểm tra định kỳ."
    )
    admin_doc, av1_id, admin_nodes = await _seed_version(
        comparison_pg_pool, tmp_path,
        curator_id=curator, reviewer_id=reviewer, category_id=cat_id,
        title="Kế hoạch hành chính HƯ CẤU", doc_number="05/KH-UBND", doc_type="plan",
        page_texts=[admin_v1],
    )
    assert not any(n["node_type"] == "article" for n in admin_nodes)
    assert any(n["path"].startswith("000001:") for n in admin_nodes)
    _, av2_id, _ = await _seed_version(
        comparison_pg_pool, tmp_path,
        curator_id=curator, reviewer_id=reviewer, category_id=cat_id,
        title="Kế hoạch hành chính HƯ CẤU", doc_number="05/KH-UBND", doc_type="plan",
        page_texts=[admin_v2],
        document_id=admin_doc, version_number=2, based_on_version_id=av1_id, retire_based_on=True,
    )

    app = _make_app(comparison_pg_pool)
    headers = await _auth_headers(comparison_pg_pool, "adm-reader")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        renum_resp = await client.post(
            "/api/v1/compare/documents",
            headers=headers,
            json={
                "mode": "versions",
                "left_document_id": str(doc_renum),
                "right_document_id": str(doc_renum),
                "left_version_id": str(v1_id),
                "right_version_id": str(v2_id),
            },
        )
        assert renum_resp.status_code == 200
        renum_data = renum_resp.json()
        assert renum_data["summary"]["moved_or_renumbered"] >= 1
        moved = [
            i for i in renum_data["items"] if i["change_kind"] == "moved_or_renumbered"
        ]
        assert any(
            i["left"]["structural_key"].startswith("dieu:2")
            and i["right"]["structural_key"].startswith("dieu:3")
            for i in moved
        )

        admin_resp = await client.post(
            "/api/v1/compare/documents",
            headers=headers,
            json={
                "mode": "versions",
                "left_document_id": str(admin_doc),
                "right_document_id": str(admin_doc),
                "left_version_id": str(av1_id),
                "right_version_id": str(av2_id),
            },
        )
        assert admin_resp.status_code == 200
        admin_data = admin_resp.json()
        assert admin_data["summary"]["modified"] == 1
        assert admin_data["summary"]["unchanged"] >= 1


async def test_summarize_checks_dated_link_and_remote_egress_policy(
    comparison_pg_pool: asyncpg.Pool, tmp_path: Path
) -> None:
    cat_public = await create_category(
        comparison_pg_pool, actor_id=uuid4(), code="PUB", name="Public",
        remote_processing_allowed=True,
    )
    cat_local = await create_category(
        comparison_pg_pool, actor_id=uuid4(), code="LOC", name="Internal",
        remote_processing_allowed=False,
    )
    pub_id, loc_id = UUID(cat_public["id"]), UUID(cat_local["id"])

    curator = await _create_user(
        comparison_pg_pool, "sum-curator", ["CURATOR"], [pub_id, loc_id]
    )
    reviewer = await _create_user(
        comparison_pg_pool, "sum-reviewer", ["REVIEWER"], [pub_id, loc_id]
    )
    await _create_user(
        comparison_pg_pool, "sum-reader", ["USER"], [pub_id, loc_id], remote_ai_allowed=True
    )

    doc_orig, _, nodes_orig = await _seed_version(
        comparison_pg_pool, tmp_path,
        curator_id=curator, reviewer_id=reviewer, category_id=pub_id,
        title="Nghị định gốc tóm tắt HƯ CẤU", doc_number="11/2021/NĐ-CP", doc_type="decree",
        page_texts=["Điều 5. Thời hạn\n1. Nộp hồ sơ trong thời hạn 10 ngày."],
    )
    doc_pub_amd, _, nodes_pub_amd = await _seed_version(
        comparison_pg_pool, tmp_path,
        curator_id=curator, reviewer_id=reviewer, category_id=pub_id,
        title="Nghị định sửa đổi công khai HƯ CẤU", doc_number="22/2025/NĐ-CP", doc_type="decree",
        page_texts=["Điều 1. Sửa đổi\n1. Nộp hồ sơ trong thời hạn 15 ngày."],
    )
    doc_restricted, _, _ = await _seed_version(
        comparison_pg_pool, tmp_path,
        curator_id=curator, reviewer_id=reviewer, category_id=loc_id,
        title="Tài liệu nội bộ HƯ CẤU", doc_number="33/2025/NB", doc_type="circular",
        page_texts=["Điều 1. Nội bộ\n1. Quy định nội bộ 30 ngày."],
    )
    orig_k1 = next(n for n in nodes_orig if n["path"].endswith("dieu:5/khoan:1"))
    amd_k1 = next(n for n in nodes_pub_amd if n["path"].endswith("dieu:1/khoan:1"))

    async with comparison_pg_pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO node_amendments
               (source_node_id, source_document_id, target_document_id, target_node_id,
                scope, action, valid_from, evidence_source, review_status, source_quote)
               VALUES ($1, $2, $3, $4, 'node', 'modify', $5, 'manual', 'approved', $6)""",
            amd_k1["id"], doc_pub_amd, doc_orig, orig_k1["id"],
            date(2025, 6, 1), "Sửa đổi khoản 1 Điều 5 như sau:",
        )

    headers = await _auth_headers(comparison_pg_pool, "sum-reader")

    # 1. LOCAL runtime with grounded point + hallucinated number + business conclusion
    ai_json = json.dumps({
        "executive_summary": "Thời hạn tăng từ 10 ngày lên 15 ngày.",
        "key_changes": [
            {
                "point": "Thời hạn nộp hồ sơ đổi từ 10 ngày thành 15 ngày.",
                "item_keys": ["item_0001"],
                "evidence_ids": ["e1", "e2"],
            },
            {
                "point": "Phạt 999 triệu đồng nếu chậm nộp.",
                "item_keys": ["item_0001"],
                "evidence_ids": ["e2"],
            },
            {
                "point": "Cơ quan phải xử lý và đủ điều kiện chấp thuận ngay.",
                "item_keys": ["item_0001"],
                "evidence_ids": ["e1"],
            },
        ],
    }, ensure_ascii=False)
    local_runtime = _FakeRuntime(OperatingMode.LOCAL, ai_json)
    app_local = _make_app(comparison_pg_pool, runtime=local_runtime)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_local), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/v1/compare/summarize",
            headers=headers,
            json={
                "mode": "amendment_pair",
                "left_document_id": str(doc_orig),
                "right_document_id": str(doc_pub_amd),
            },
        )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["mode_used"] == "ai"
    assert data["summary_status"] == "verified"
    assert data["external_api_used"] is False
    assert len(local_runtime.calls) == 1
    assert '"valid_from": "2025-06-01"' in local_runtime.calls[0]["messages"][1]["content"]
    # Grounded verified + hallucinated needs_review; business conclusion dropped
    assert len(data["key_changes"]) == 2
    assert data["key_changes"][0]["status"] == "verified"
    assert data["key_changes"][1]["status"] == "needs_review"
    assert "NUMBER_NOT_IN_EVIDENCE" in data["key_changes"][1]["check_notes"]
    assert all("phải xử lý" not in kc["point"] for kc in data["key_changes"])

    # 2. API mode with one document in remote_processing_allowed=FALSE category -> 0 model calls
    api_runtime = _FakeRuntime(OperatingMode.API, ai_json)
    app_api = _make_app(comparison_pg_pool, runtime=api_runtime)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_api), base_url="http://test"
    ) as client:
        blocked = await client.post(
            "/api/v1/compare/summarize",
            headers=headers,
            json={
                "mode": "cross_document",
                "left_document_id": str(doc_orig),
                "right_document_id": str(doc_restricted),
            },
        )
    assert blocked.status_code == 200
    bdata = blocked.json()
    assert bdata["mode_used"] == "deterministic_fallback"
    assert bdata["reason"] == "remote_blocked_by_document_policy"
    assert bdata["external_api_used"] is False
    assert bdata["deterministic_highlights"]
    assert len(api_runtime.calls) == 0

    async with comparison_pg_pool.acquire() as conn:
        sum_audits = await conn.fetchval(
            "SELECT count(*) FROM audit_events WHERE action = 'document.compare.summarize'"
        )
    assert int(sum_audits) == 2
