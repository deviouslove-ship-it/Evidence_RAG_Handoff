"""Regression coverage for visibility gates and existing result sets."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest
from test_ai_registry_postgres import DSN, _insert_document, _insert_user
from test_ai_registry_postgres import database as registry_database

from app.documents.provenance import save_immutable_pdf
from app.effectivity.store import publish_snapshot
from app.main import create_app
from app.memory.service import EphemeralMemoryService
from app.storage.chat_retrieval import ChatRetrieval
from app.storage.comprehensive import ComprehensiveSearch
from app.storage.search import SearchService
from app.synthesis.service import SynthesisService
from app.workflow.fixed_pipeline import FixedPipeline, PipelineDependencies

lookup_database = registry_database


@pytest.mark.skipif(not DSN, reason="No disposable PostgreSQL test database configured")
@pytest.mark.parametrize("direct_acl", [False, True], ids=["category", "document"])
async def test_suspended_document_cannot_replay_cached_search_or_synthesis(
    lookup_database: tuple[Any, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    direct_acl: bool,
) -> None:
    pool, connection = lookup_database
    principal = uuid4()
    category = uuid4()
    await _insert_user(connection, principal, "reader")
    await connection.execute(
        "INSERT INTO categories (id, name, code) VALUES ($1, 'Fixture', 'fixture')", category,
    )
    document, node = await _insert_document(connection, category_id=category)
    related, _ = await _insert_document(
        connection, category_id=category, document_number="111/2026/NĐ-CP",
        quote="Hư cấu: Chế độ báo cáo thường kỳ.",
    )
    if direct_acl:
        await connection.executemany(
            "INSERT INTO document_acl (document_id, user_id) VALUES ($1, $2)",
            [(document, principal), (related, principal)],
        )
    else:
        await connection.execute(
            "INSERT INTO category_acl (category_id, user_id) VALUES ($1, $2)", category, principal,
        )
    version = await connection.fetchval(
        "SELECT document_version_id FROM document_nodes WHERE id = $1", node,
    )
    await connection.execute(
        """INSERT INTO node_amendments
             (source_node_id, source_document_id, target_document_id, scope, action,
              valid_from, evidence_source, review_status, reviewed_by, reviewed_at)
           VALUES ($1, $2, $3, 'document', 'repeal', '2024-01-01', 'fixture',
                   'approved', $4, now())""",
        node, document, related, principal,
    )
    async with connection.transaction():
        await publish_snapshot(connection, actor_id=principal)
    original = save_immutable_pdf(b"%PDF-1.4\nfixture\n%%EOF\n", tmp_path / "originals")
    await connection.execute(
        """UPDATE document_versions SET original_file_path = $2, original_file_sha256 = $3
           WHERE id = $1""",
        version, f"originals/{original.sha256}.pdf", original.sha256,
    )
    monkeypatch.setenv("EVIDENCE_DOCUMENT_STORE_ROOT", str(tmp_path))
    app = create_app()
    app.state.db_pool = pool
    app.state.memory = EphemeralMemoryService()
    search = SearchService(pool, audit_enabled=False)
    app.state.search_service = search
    app.state.comprehensive_search = ComprehensiveSearch(
        search, None, semantic_top_n=10, semantic_relative_threshold=0.8,
        rerank_top_n=10, rerank_batch_size=5, result_set_ttl_seconds=300, concept_min_terms=1,
    )
    retrieval = ChatRetrieval(app.state.comprehensive_search)
    app.state.pipeline = FixedPipeline(PipelineDependencies(
        search_authorized_nodes=search.search_clauses, chat_retrieval=retrieval,
    ))
    app.state.synthesis = SynthesisService(pool, None, retrieval=retrieval)
    payload = {"q": "phụ cấp", "channels": ["exact"], "as_of_date": date.today().isoformat()}
    question = {
        "question": "Điều 3 Nghị định 381/2026/NĐ-CP quy định thế nào?",
        "scope": {"scope_mode": "ALL_AUTHORIZED", "as_of_date": payload["as_of_date"]},
    }
    base = "/api/v1"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
        headers={"X-Principal-Id": str(principal), "X-Roles": "USER"},
    ) as client:
        initial = await client.post(base + "/search/comprehensive", json=payload)
        assert initial.status_code == 200, initial.text
        assert initial.json()["totals"]["documents"] == 1
        assert initial.headers["cache-control"] == "no-store"
        result = initial.json()["result_set_id"]
        assert (await client.get(f"{base}/citations/ev_{node}")).status_code == 200
        assert (await client.get(f"{base}/effectivity/documents/{document}")).status_code == 200
        for only_relevant in (False, True):
            synthesis = await client.post(
                base + "/synthesis", json={"result_set_id": result, "only_relevant": only_relevant},
            )
            assert synthesis.is_success, synthesis.text
        old_effectivity = await client.get(f"{base}/effectivity/documents/{related}")
        assert "381/2026" in old_effectivity.text
        session = (await client.post(base + "/agent/sessions", json={})).json()["session_id"]
        turns_url = f"{base}/agent/sessions/{session}/turns"
        turn = await client.post(
            turns_url, json=question, headers={"Idempotency-Key": "before-suspension"},
        )
        assert turn.status_code == 200 and str(node) in turn.text, turn.text
        replay_url = f'{turns_url}/{turn.headers["x-turn-id"]}/events'

        await connection.execute("UPDATE documents SET suspended_at = now() WHERE id=$1", document)
        for suffix in ("", f"/documents/{document}"):
            stale = await client.get(f"{base}/search/comprehensive/{result}{suffix}")
            assert stale.status_code == 410
            assert stale.json()["code"] == "RESULT_SET_EXPIRED"
        for only_relevant in (False, True):
            stale = await client.post(
                base + "/synthesis", json={"result_set_id": result, "only_relevant": only_relevant}
            )
            assert stale.status_code == 410
        assert (await client.get(f"{base}/citations/ev_{node}")).status_code == 404
        assert (await client.get(f"{base}/citations/ev_{node}/original")).status_code == 404
        assert (await client.get(f"{base}/effectivity/documents/{document}")).status_code == 404
        updated_effectivity = await client.get(f"{base}/effectivity/documents/{related}")
        assert "381/2026" not in updated_effectivity.text
        assert (updated_effectivity.json()["effectivity"]["status"]
                == old_effectivity.json()["effectivity"]["status"] == "repealed")
        assert (await client.get(replay_url)).status_code == 403
        duplicate_turn = await client.post(
            turns_url, json=question, headers={"Idempotency-Key": "before-suspension"},
        )
        assert duplicate_turn.status_code == 403
        answer = await client.post(base + "/query/evidence", json=question)
        assert answer.status_code == 200, answer.text
        assert str(document) not in answer.text
        fresh = await client.get(base + "/search", params={"q": "phụ cấp"})
        assert fresh.status_code == 200, fresh.text
        assert fresh.json()["totals"]["documents"] == 0
        fresh = await client.post(base + "/search/comprehensive", json=payload)
        assert fresh.json()["totals"]["documents"] == 0

        await connection.execute("UPDATE documents SET suspended_at = NULL WHERE id=$1", document)
        fresh = await client.post(base + "/search/comprehensive", json=payload)
        assert fresh.json()["totals"]["documents"] == 1
        assert (await client.get(replay_url)).status_code == 403
        await connection.execute(
            "UPDATE document_versions SET review_status='pending_review' WHERE id=$1", version,
        )
        answer = await client.post(base + "/query/evidence", json=question)
        assert answer.status_code == 200, answer.text
        assert str(document) not in answer.text
        await connection.execute(
            "UPDATE document_versions SET review_status='approved', retired_at=now() WHERE id=$1",
            version,
        )
        assert (await client.get(f"{base}/citations/ev_{node}")).status_code == 404
        fresh = await client.post(base + "/search/comprehensive", json=payload)
        assert fresh.json()["totals"]["documents"] == 0


@pytest.mark.parametrize("path", ["/api/v1/search", "/api/v1/search/approximate"])
def test_search_does_not_allow_browser_caching(path: str, monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient
    from test_search_api import HEADERS, FakeSearchService

    monkeypatch.setenv("DEV_ALLOW_IN_MEMORY_STORE", "true")
    app = create_app()
    with TestClient(app) as client:
        app.state.search_service = FakeSearchService()
        response = client.get(path, params={"q": "báo cáo"}, headers=HEADERS)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
