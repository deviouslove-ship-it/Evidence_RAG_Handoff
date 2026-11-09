"""Admin document lifecycle with a disposable database and synthetic OCR text."""

from datetime import date
from hashlib import sha256
from uuid import UUID

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient
from test_ocr_review import _blank_pdf, _user
from test_ocr_review import ocr_pool as management_pool  # noqa: F401

from app.admin_services import create_category
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
from app.migrations.runner import MIGRATIONS_DIR, apply_migrations

BASE = "/api/v1/admin/documents"


def headers(actor, role):
    return {"X-Principal-Id": str(actor), "X-Roles": role}


async def test_management_acl_and_soft_delete(
    management_pool, tmp_path, monkeypatch,  # noqa: F811
):
    monkeypatch.setenv("DEV_ALLOW_IN_MEMORY_STORE", "true")
    monkeypatch.setenv("EVIDENCE_DOCUMENT_STORE_ROOT", str(tmp_path))
    app = create_app()
    app.state.db_pool = management_pool
    curator = await _user(management_pool, "manager-curator", ["CURATOR"])
    admin = await _user(management_pool, "manager-admin", ["SYS_ADMIN"])
    other = await _user(management_pool, "manager-user", ["USER"])
    source = _blank_pdf(1)

    pages = [ExtractedPage(1, 595, 842, 0, "Điều 1. Nội dung hư cấu", (),
                           "local_ocr", "needs_review")]
    draft = await persist_draft(
        PreparedDraft(source, sha256(source).hexdigest(), pages, parse_legal_tree(pages)),
        pool=management_pool, store_root=tmp_path, title="Văn bản kiểm thử hư cấu",
        doc_type="decree", original_filename="scan.pdf", submitted_by=curator,
    )
    document = f"{BASE}/{draft.document_id}"
    version = f"{document}/versions/{draft.document_version_id}"
    hc = headers(curator, "CURATOR")
    ha = headers(admin, "SYS_ADMIN")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get(BASE, headers=headers(other, "USER"))).status_code == 403
        listing = await client.get(BASE, params={"q": "kiem thu", "page_size": 1}, headers=ha)
        assert listing.status_code == 200, listing.text
        assert listing.json()["total"] == 1
        assert not listing.json()["items"][0]["can_read"]
        assert (await client.get(f"{version}/original", headers=ha)).status_code == 404

        detail = await client.get(document, headers=hc)
        assert detail.status_code == 200, detail.text
        assert detail.json()["page"]["text"] == pages[0].text
        assert (await client.get(f"{version}/original", headers=hc)).content == source
        edit = await client.patch(version, headers=hc, json={
            "revision": detail.json()["revision"], "title": "Trích yếu đã sửa",
            "ocr_page": {"page_number": 1, "text": "Điều 1. Nội dung đã sửa"},
        })
        assert edit.status_code == 200, edit.text
        assert (await client.patch(version, headers=hc, json={
            "revision": detail.json()["revision"], "title": "Phiên sửa cũ",
        })).status_code == 409
        detail = (await client.get(document, headers=hc)).json()
        assert detail["document"]["title"] == "Trích yếu đã sửa"
        assert detail["page"]["text_quality"] == "needs_review"
        assert not detail["page"]["reviewed"]

        action = {"document_ids": [str(draft.document_id)], "action": "delete",
                  "reason": "Kiểm thử", "confirmed": False}
        assert (await client.post(f"{BASE}/actions", headers=ha, json=action)).status_code == 422
        action["confirmed"] = True
        assert (await client.post(f"{BASE}/actions", headers=hc, json=action)).status_code == 403
        deletion = await client.post(f"{BASE}/actions", headers=ha, json=action)
        assert deletion.json()["updated"] == 1
        assert (await client.get(BASE, headers=ha)).json()["total"] == 0
        deleted = (await client.get(BASE, params={"availability": "deleted"}, headers=ha)).json()
        assert deleted["items"][0]["availability"] == "deleted"
        assert (await client.get(f"{version}/original", headers=hc)).status_code == 404
        action["action"] = "restore"
        assert (await client.post(f"{BASE}/actions", headers=ha, json=action)).status_code == 200
        assert (await client.get(f"{version}/original", headers=hc)).content == source

    async with management_pool.acquire() as conn:
        assert await conn.fetchval(
            "SELECT count(*) FROM document_ocr_edits WHERE document_version_id=$1",
            UUID(str(draft.document_version_id)),
        ) == 1


async def test_review_correction_keeps_original_and_requires_independent_scoped_review(
    management_pool, tmp_path, monkeypatch,  # noqa: F811
):
    monkeypatch.setenv("DEV_ALLOW_IN_MEMORY_STORE", "true")
    monkeypatch.setenv("EVIDENCE_DOCUMENT_STORE_ROOT", str(tmp_path))
    app = create_app()
    app.state.db_pool = management_pool
    curator = await _user(management_pool, "version-curator", ["CURATOR", "REVIEWER"])
    reviewer = await _user(management_pool, "version-reviewer", ["REVIEWER"])
    outside = await _user(management_pool, "version-outsider", ["CURATOR", "REVIEWER"])
    category = UUID((await create_category(
        management_pool, actor_id=curator, code="REVISION", name="Nguồn hư cấu",
    ))["id"])
    async with management_pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO category_acl (category_id,user_id,can_query,can_review)
               VALUES ($1,$2,true,true), ($1,$3,true,true)""", category, curator, reviewer,
        )
    source = _blank_pdf(1)
    initial = "Điều 1. Quy định ban đầu\n1. Đoạn thử HƯ CẤU."
    pages = [ExtractedPage(1, 595, 842, 0, initial, (), "local_ocr", "needs_review")]
    draft = await persist_draft(
        PreparedDraft(source, sha256(source).hexdigest(), pages, parse_legal_tree(pages)),
        pool=management_pool, store_root=tmp_path, title="Bản đã công bố", doc_type="decree",
        original_filename="scan.pdf", publication_date=date(2026, 1, 3), submitted_by=curator,
    )
    original_id = draft.document_version_id
    await submit_draft_for_review(management_pool, version_id=original_id, curator_id=curator)
    tasks = await list_review_tasks(management_pool, version_id=original_id, status_filter="open")
    await resolve_review_task(
        management_pool, task_id=UUID(next(t["id"] for t in tasks if t["page"])),
        reviewer_id=reviewer, resolution_note="Đã đối chiếu",
    )
    await approve_document_version(
        management_pool, store_root=tmp_path, max_bytes=len(source)+1, version_id=original_id,
        reviewer_id=reviewer, category_ids=[category], review_note="Duyệt bản đầu",
        resolve_all_tasks=True,
    )
    document = f"{BASE}/{draft.document_id}"
    hc = headers(curator, "CURATOR,REVIEWER")
    hr = headers(reviewer, "REVIEWER")
    hx = headers(outside, "CURATOR,REVIEWER")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        before = (await client.get(document, headers=hc)).json()
        edited = await client.patch(f"{document}/versions/{original_id}", headers=hc, json={
            "revision": before["revision"], "title": "Trích yếu đã hiệu chỉnh",
            "ocr_page": {"page_number": 1, "text": "Điều 1. Quy định mới\n1. HƯ CẤU."},
        })
        assert edited.status_code == 200, edited.text
        replacement = edited.json()
        new_id = UUID(replacement["version_id"])
        assert new_id != original_id
        legacy = f"{BASE}/drafts/{new_id}"
        assert (await client.get(f"{legacy}/pdf", headers=hx)).status_code == 404
        assert (await client.get(BASE + "/drafts", headers=hx)).json() == []
        assert (await client.get(BASE + "/review-tasks", headers=hx)).json() == []
        assert (await client.post(f"{legacy}/submit", headers=hx)).status_code == 403
        assert (await client.post(f"{legacy}/submit", headers=hc)).status_code == 200
        async with management_pool.acquire() as conn:
            assert await conn.fetchval("SELECT title FROM documents WHERE id=$1",
                                       draft.document_id) == "Bản đã công bố"
            assert await conn.fetchval("SELECT retired_at FROM document_versions WHERE id=$1",
                                       original_id) is None

        approval = {"revision": replacement["revision"], "category_ids": [str(category)],
                    "review_note": "Duyệt bản hiệu chỉnh", "resolve_all_tasks": True}
        forbidden = await client.post(f"{legacy}/approve", headers=hx, json=approval)
        assert forbidden.status_code == 403
        assert (await client.post(f"{legacy}/approve", headers=hc, json=approval)).json()[
            "code"
        ] == "SELF_APPROVAL_DENIED"
        assert (await client.post(f"{legacy}/approve", headers=hr, json=approval)).json()[
            "code"
        ] == "OPEN_REVIEW_TASKS_REMAIN"
        tasks = (await client.get(BASE + "/review-tasks", headers=hr, params={
            "version_id": str(new_id), "status": "open",
        })).json()
        task_id = next(t["id"] for t in tasks if t["page"])
        resolved = await client.post(
            f"{BASE}/review-tasks/{task_id}/resolve", headers=hr,
            json={"resolution_note": "Đã so từng dòng với scan"},
        )
        assert resolved.status_code == 200, resolved.text
        stale = await client.post(f"{legacy}/approve", headers=hr,
                                  json={**approval, "revision": before["revision"]})
        assert stale.status_code == 409
        approved = await client.post(f"{legacy}/approve", headers=hr, json=approval)
        assert approved.status_code == 200, approved.text
        old = (await client.get(document, headers=hc,
                                params={"version_id": str(original_id)})).json()
        assert old["page"]["text"] == initial
        assert old["document"]["title"] == "Bản đã công bố"
        assert next(v for v in old["versions"] if v["id"] == str(original_id))["retired"]
        latest = (await client.get(document, headers=hc)).json()
        assert latest["document"]["title"] == "Trích yếu đã hiệu chỉnh"
        assert latest["page"]["reviewed"]
        assert (await client.get(f"{document}/versions/{new_id}/original",
                                 headers=hc)).content == source

        text = "Điều 1. Bản đính chính\n1. Dữ liệu mới HƯ CẤU."
        upload = await client.post(BASE + "/drafts", headers=hc, data={
            "document_id": str(draft.document_id), "revision": str(latest["revision"]),
            "title": latest["document"]["title"], "doc_type": "decree",
        }, files={"file": ("thu-nghiem.txt", text.encode(), "text/plain")})
        assert upload.status_code == 201, upload.text
        uploaded = upload.json()["document_version_id"]
        latest = (await client.get(document, headers=hc)).json()
        assert latest["document"]["version_number"] == 3
        assert (await client.get(f"{document}/versions/{uploaded}/original",
                                 headers=hc)).content == text.encode()
        reprocessed = await client.post(
            f"{document}/versions/{uploaded}/reprocess",
            headers=hc, json={"revision": latest["revision"]},
        )
        assert reprocessed.status_code == 200, reprocessed.text
        assert reprocessed.json()["version_id"] == uploaded


async def test_upgrade_keeps_approved_source_and_vectors(management_pool):  # noqa: F811
    name = "0016_document_management"
    down = (MIGRATIONS_DIR / f"{name}.down.sql").read_text(encoding="utf-8")
    async with management_pool.acquire() as conn:
        await conn.execute(down)
        await conn.execute("DELETE FROM schema_migrations WHERE name=$1", f"{name}.sql")
        document = await conn.fetchval(
            "INSERT INTO documents (doc_type,title) VALUES ('decree','HƯ CẤU') RETURNING id"
        )
        digest = "a" * 64
        version = await conn.fetchval(
            """INSERT INTO document_versions
                 (document_id,version_number,original_file_path,original_file_sha256,
                  original_filename,review_status)
               VALUES ($1,1,'originals/test.pdf',$2,'test.pdf','approved') RETURNING id""",
            document, digest,
        )
        node = await conn.fetchval(
            """INSERT INTO document_nodes
                 (document_id,document_version_id,node_type,path,text_original,text_indexed,
                  text_normalized,text_folded,parse_confidence,review_status)
               VALUES ($1,$2,'article','000001:article.1','A','A','a','a',1,'approved')
               RETURNING id""", document, version,
        )
        index = await conn.fetchval(
            """INSERT INTO embedding_indices
                 (model_id,model_revision,tokenizer_revision,dimensions,index_revision)
               VALUES ('fake','test','test',3,1) RETURNING id"""
        )
        await conn.execute(
            "INSERT INTO node_embeddings (embedding_index_id,document_node_id,embedding) "
            "VALUES ($1,$2,'[1,2,3]')", index, node,
        )
        assert await apply_migrations(conn) == [f"{name}.sql"]
        assert await apply_migrations(conn) == []
        preserved = await conn.fetchrow(
            """SELECT v.original_file_sha256, v.review_status, v.retired_at,
                      d.suspended_at, e.embedding::text
               FROM document_versions v JOIN documents d ON d.id=v.document_id
               JOIN document_nodes n ON n.document_version_id=v.id
               JOIN node_embeddings e ON e.document_node_id=n.id
               WHERE v.id=$1 AND n.id=$2 AND e.embedding_index_id=$3""", version, node, index,
        )
        assert tuple(preserved) == (digest, "approved", None, None, "[1,2,3]")
        await conn.execute("UPDATE documents SET suspended_at=now() WHERE id=$1", document)
        with pytest.raises(asyncpg.RaiseError, match="Document management is in use"):
            async with conn.transaction():
                await conn.execute(down)
        assert await conn.fetchval("SELECT suspended_at IS NOT NULL FROM documents WHERE id=$1",
                                   document)
