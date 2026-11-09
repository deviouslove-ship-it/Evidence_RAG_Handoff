"""End-to-end PostgreSQL tests for local auth, review workflow, Admin Portal and audit chain."""

from __future__ import annotations

import os
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest

from app.admin_services import create_or_update_user
from app.documents.draft import PreparedDraft, persist_draft
from app.documents.native_pdf import ExtractedPage
from app.documents.tree_parser import ParsedNode
from app.main import create_app
from app.migrations.runner import apply_migrations
from app.storage.authorized_search import PostgresAuthorizedNodeSearch
from app.workflow.fixed_pipeline import FixedPipeline, PipelineDependencies

DSN = os.environ.get("EVIDENCE_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DSN, reason="No disposable PostgreSQL/pgvector test database configured"
)


def _sample_pdf() -> bytes:
    pdfium = pytest.importorskip("pypdfium2")
    output = BytesIO()
    document = pdfium.PdfDocument.new()
    page = document.new_page(595, 842)
    page.close()
    document.save(output)
    document.close()
    return output.getvalue()


async def test_auth_admin_review_and_audit_flow_on_postgresql(tmp_path: Path) -> None:
    assert DSN
    schema = "test_portal_" + uuid4().hex
    connection = await asyncpg.connect(DSN)
    pool = None
    try:
        await connection.execute(f'CREATE SCHEMA "{schema}"')
        pool = await asyncpg.create_pool(
            DSN,
            min_size=1,
            max_size=4,
            server_settings={"search_path": f"{schema},public"},
        )
        async with pool.acquire() as conn:
            applied = await apply_migrations(conn)
            assert applied == [
                "0001_core.sql", "0002_auth_admin.sql", "0003_source_integrity.sql",
                "0004_ai_runtime.sql", "0005_pdf_content_fingerprint.sql",
                "0006_search_index.sql",
                "0007_normalization_revision.sql",
                "0008_source_format.sql",
                "0009_node_structure.sql",
                "0010_ai_policy.sql",
                "0011_effectivity.sql",
                "0012_comprehensive_search.sql",
                "0013_content_groups.sql",
                "0014_embedding_jobs.sql",
                "0015_ocr_page_review.sql",
                "0016_document_management.sql",
            ]
            assert await apply_migrations(conn) == []

        bootstrap_actor = uuid4()
        admin_record = await create_or_update_user(
            pool,
            actor_id=bootstrap_actor,
            username="sysadmin",
            display_name="Quản trị hệ thống",
            password="AdminPassword!2026",
            roles=["SYS_ADMIN", "AUDITOR"],
            category_ids=[],
            must_change_password=False,
        )
        assert admin_record["username"] == "sysadmin"

        app = create_app()
        app.state.settings = app.state.settings.__class__(
            database_url=DSN,
            programs_root=app.state.settings.programs_root,
            operating_mode="LOCAL",
            llm_attempt_budget=2,
            session_ttl_seconds=1800,
            retention_approved=False,
            dev_allow_in_memory_store=False,
            allowed_origins=app.state.settings.allowed_origins,
            max_upload_bytes=app.state.settings.max_upload_bytes,
            max_preview_pages=app.state.settings.max_preview_pages,
            document_store_root=str(tmp_path),
        )
        app.state.db_pool = pool
        app.state.search_authorized_nodes = PostgresAuthorizedNodeSearch(pool)
        app.state.pipeline = FixedPipeline(
            dependencies=PipelineDependencies(
                search_authorized_nodes=app.state.search_authorized_nodes
            ),
            operating_mode="LOCAL",
            llm_attempt_budget=2,
        )

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            login_resp = await client.post(
                "/api/v1/auth/login",
                json={"username": "sysadmin", "password": "AdminPassword!2026", "client": "web"},
            )
            assert login_resp.status_code == 200
            admin_token = login_resp.json()["access_token"]
            admin_headers = {"Authorization": f"Bearer {admin_token}"}

            cat_resp = await client.post(
                "/api/v1/admin/categories",
                headers=admin_headers,
                json={
                    "code": "CONG_VU",
                    "name": "Chế độ công vụ",
                    "remote_processing_allowed": False,
                },
            )
            assert cat_resp.status_code == 201
            cat_id = cat_resp.json()["id"]

            for uname, dname, rlist, must_change in [
                ("curator1", "Biên tập viên", ["CURATOR", "REVIEWER"], False),
                ("reviewer1", "Người duyệt", ["REVIEWER"], False),
                ("user1", "Chuyên viên tra cứu", ["USER"], True),
            ]:
                resp = await client.post(
                    "/api/v1/admin/users",
                    headers=admin_headers,
                    json={
                        "username": uname,
                        "display_name": dname,
                        "password": f"InitialPass!{uname}",
                        "roles": rlist,
                        "category_ids": [cat_id] if uname == "user1" else [],
                        "must_change_password": must_change,
                        "disabled": False,
                    },
                )
                assert resp.status_code == 201

            user_login = await client.post(
                "/api/v1/auth/login",
                json={"username": "user1", "password": "InitialPass!user1", "client": "desktop"},
            )
            assert user_login.status_code == 200
            user_token = user_login.json()["access_token"]
            user_headers = {"Authorization": f"Bearer {user_token}"}

            blocked = await client.get("/api/v1/categories", headers=user_headers)
            assert blocked.status_code == 403
            assert blocked.json()["code"] == "PASSWORD_CHANGE_REQUIRED"

            pw_change = await client.post(
                "/api/v1/auth/password",
                headers=user_headers,
                json={
                    "current_password": "InitialPass!user1",
                    "new_password": "UpdatedUserPass!2026",
                },
            )
            assert pw_change.status_code == 204

            cats = await client.get("/api/v1/categories", headers=user_headers)
            assert cats.status_code == 200
            assert [c["code"] for c in cats.json()] == ["CONG_VU"]

            curator_token = (
                await client.post(
                    "/api/v1/auth/login",
                    json={"username": "curator1", "password": "InitialPass!curator1"},
                )
            ).json()["access_token"]
            reviewer_token = (
                await client.post(
                    "/api/v1/auth/login",
                    json={"username": "reviewer1", "password": "InitialPass!reviewer1"},
                )
            ).json()["access_token"]
            curator_headers = {"Authorization": f"Bearer {curator_token}"}
            reviewer_headers = {"Authorization": f"Bearer {reviewer_token}"}
            curator_id = UUID(
                (await client.get("/api/v1/auth/me", headers=curator_headers)).json()["id"]
            )

            pdf_bytes = _sample_pdf()
            quote_text = "Điều 3. Mức phụ cấp công vụ bằng 25% mức lương hiện hưởng."
            prepared = PreparedDraft(
                content=pdf_bytes,
                sha256=sha256(pdf_bytes).hexdigest(),
                pages=[
                    ExtractedPage(
                        page_number=1,
                        width=595.0,
                        height=842.0,
                        rotation=0,
                        text=quote_text,
                        character_boxes=0,
                        extraction_method="native_text",
                        text_quality="usable",
                    )
                ],
                nodes=[
                    ParsedNode(
                        node_type="article",
                        label_original="Điều 3. Mức phụ cấp công vụ",
                        text_original=quote_text,
                        page_start=1,
                        parse_confidence=0.98,
                    )
                ],
            )
            draft = await persist_draft(
                prepared,
                pool=pool,
                store_root=tmp_path,
                title="Nghị định quy định phụ cấp công vụ",
                doc_type="decree",
                original_filename="381.pdf",
                document_number="381/2026/NĐ-CP",
                official_url="https://vanban.chinhphu.vn/381",
                submitted_by=curator_id,
            )
            version_id = str(draft.document_version_id)

            submit_resp = await client.post(
                f"/api/v1/admin/documents/drafts/{version_id}/submit",
                headers=curator_headers,
            )
            assert submit_resp.status_code == 200

            self_approve = await client.post(
                f"/api/v1/admin/documents/drafts/{version_id}/approve",
                headers=curator_headers,
                json={
                    "category_ids": [cat_id],
                    "review_note": "Tự duyệt",
                    "resolve_all_tasks": True,
                },
            )
            assert self_approve.status_code == 403
            assert self_approve.json()["code"] == "SELF_APPROVAL_DENIED"

            unresolved = await client.post(
                f"/api/v1/admin/documents/drafts/{version_id}/approve",
                headers=reviewer_headers,
                json={
                    "category_ids": [cat_id],
                    "review_note": "Duyệt nhưng chưa đóng task",
                    "resolve_all_tasks": False,
                },
            )
            assert unresolved.status_code == 409
            assert unresolved.json()["code"] == "OPEN_REVIEW_TASKS_REMAIN"

            approved = await client.post(
                f"/api/v1/admin/documents/drafts/{version_id}/approve",
                headers=reviewer_headers,
                json={
                    "category_ids": [cat_id],
                    "review_note": "Đã đối chiếu bản gốc và chữ ký số.",
                    "resolve_all_tasks": True,
                },
            )
            assert approved.status_code == 200
            assert approved.json()["status"] == "approved"
            assert approved.json()["approved_nodes"] == 1

            query_resp = await client.post(
                "/api/v1/query/evidence",
                headers=user_headers,
                json={
                    "question": "Điều 3 Nghị định 381/2026/NĐ-CP quy định phụ cấp công vụ thế nào?",
                    "scope": {
                        "scope_mode": "ALL_AUTHORIZED",
                        "category_ids": [],
                        "document_types": [],
                        "as_of_date": "2026-10-22",
                    },
                    "facts": [],
                },
            )
            assert query_resp.status_code == 200
            qbody = query_resp.json()
            assert qbody["status"] == "conditional"
            assert qbody["coverage_checks"]["effective_checked"] == "unknown"
            assert len(qbody["evidence"]) == 1
            ev = qbody["evidence"][0]
            assert ev["quote_exact"] == quote_text

            pdf_resp = await client.get(ev["viewer_url"], headers=user_headers)
            assert pdf_resp.status_code == 200
            assert pdf_resp.content == pdf_bytes

            prof_resp = await client.post(
                "/api/v1/admin/model-registry",
                headers=admin_headers,
                json={
                    "profile_id": "public-cloud-1",
                    "adapter": "openai_compatible",
                    "endpoint": "https://api.example.com/v1",
                    "model_id": "model-x",
                    "capabilities": ["answer"],
                    "privacy_zone": "public",
                    "revision": "2026-10",
                    "secret_ref": "env:CLOUD_KEY",
                    "fallback": [],
                },
            )
            assert prof_resp.status_code == 201

            denied_route = await client.post(
                "/api/v1/admin/model-registry/routes",
                headers=admin_headers,
                json={
                    "mode": "LOCAL",
                    "stage": "answer",
                    "profile_id": "public-cloud-1",
                    "fallback": [],
                },
            )
            assert denied_route.status_code == 409
            assert denied_route.json()["code"] == "REMOTE_AI_DENIED"

            audit_resp = await client.get("/api/v1/admin/audit-events", headers=admin_headers)
            assert audit_resp.status_code == 200
            audit_body = audit_resp.json()
            assert audit_body["chain"]["valid"] is True
            assert audit_body["chain"]["checked"] >= 8
    finally:
        if pool is not None:
            await pool.close()
        await connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await connection.close()
