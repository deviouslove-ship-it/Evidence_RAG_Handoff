"""Opt-in PostgreSQL tests for Admin Portal embedding management (G5).

Run with a disposable database:

    EVIDENCE_TEST_DATABASE_URL=postgresql://user:pass@127.0.0.1:55432/postgres \
        python -m pytest backend/tests/test_embedding_jobs_postgres.py -q

Each test creates (and drops) an isolated schema with a few synthetic approved
clauses (text marked HƯ CẤU).  The embedding "service" is an in-process
OpenAI-compatible fake reached through the runtime's HTTP transport, so model names
and vector sizes here are test data, not configuration.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest

from app.admin_services import create_or_update_user
from app.main import create_app
from app.migrations.runner import apply_migrations
from app.model_registry.runtime import EndpointPolicy, RegistryRuntime
from app.storage.comprehensive import ComprehensiveSearch
from app.storage.embedding_jobs import (
    EmbeddingJobError,
    EmbeddingWorker,
    control_job,
    create_job,
    embedding_overview,
    preflight,
)
from app.storage.embeddings import (
    active_index,
    build_embeddings,
    hnsw_index_name,
    semantic_candidates,
)
from app.storage.search import SearchService
from app.vietnamese_nlp.unicode_norm import fold_text, normalize_text

DSN = os.environ.get("EVIDENCE_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DSN, reason="No disposable PostgreSQL test database configured"
)
ENDPOINT = "http://127.0.0.1:65500/v1"
POLICY = EndpointPolicy()


class FakeEmbeddingService:
    """OpenAI-compatible /models and /embeddings with per-model size and faults."""

    def __init__(self, sizes: dict[str, int]) -> None:
        self.sizes = sizes
        self.fail_models: set[str] = set()
        self.fail_after: dict[str, int] = {}
        self.random_models: set[str] = set()
        self.calls: dict[str, int] = {}

    def vector(self, model: str, text: str) -> list[float]:
        size = self.sizes[model]
        if model in self.random_models:
            return [random.uniform(-1, 1) for _ in range(size)]
        digest = hashlib.sha256(f"{model}|{text}".encode()).digest()
        values = [(digest[i % len(digest)] - 127.5) / 127.5 + 0.01 * i for i in range(size)]
        norm = math.sqrt(sum(v * v for v in values))
        return [v / norm for v in values]

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": m} for m in self.sizes]})
        body = json.loads(request.content)
        model = body["model"]
        self.calls[model] = self.calls.get(model, 0) + 1
        limit = self.fail_after.get(model)
        if model in self.fail_models or (limit is not None and self.calls[model] > limit):
            return httpx.Response(500, json={"error": "fake outage"})
        return httpx.Response(200, json={"data": [
            {"index": i, "embedding": self.vector(model, text)}
            for i, text in enumerate(body["input"])
        ]})


async def _seed_node(connection: asyncpg.Connection, category: UUID, number: str,
                     text: str) -> UUID:
    document_id, version_id = uuid4(), uuid4()
    await connection.execute(
        "INSERT INTO documents (id, doc_type, title, document_number) "
        "VALUES ($1, 'decree', 'Nghị định HƯ CẤU', $2)", document_id, number,
    )
    await connection.execute(
        "INSERT INTO document_categories (document_id, category_id) VALUES ($1, $2)",
        document_id, category,
    )
    await connection.execute(
        """INSERT INTO document_versions (id, document_id, version_number, valid_from,
             original_file_path, original_file_sha256, original_filename, review_status)
           VALUES ($1, $2, 1, '2025-01-01', 'f.pdf', $3, 'f.pdf', 'approved')""",
        version_id, document_id, uuid4().hex + uuid4().hex,
    )
    await connection.execute(
        "INSERT INTO source_provenance (document_version_id, verified_at) VALUES ($1, now())",
        version_id,
    )
    page_id = await connection.fetchval(
        """INSERT INTO source_pages (document_version_id, page_number, width, height,
             extraction_method, text_quality, text_original)
           VALUES ($1, 1, 595, 842, 'native_text', 'usable', $2) RETURNING id""",
        version_id, text,
    )
    span_id = await connection.fetchval(
        """INSERT INTO source_spans (page_id, original_offset, original_length, text_original)
           VALUES ($1, 0, $2, $3) RETURNING id""", page_id, len(text), text,
    )
    return UUID(str(await connection.fetchval(
        """INSERT INTO document_nodes (document_id, document_version_id, node_type,
             label_original, path, text_original, text_indexed, text_normalized, text_folded,
             page_start, parse_confidence, review_status, source_span_id)
           VALUES ($1, $2, 'clause', 'Điều 1', $3, $4, $4, $5, $6, 1, 0.9, 'approved', $7)
           RETURNING id""",
        document_id, version_id, f"node/{number}", text, normalize_text(text),
        fold_text(text), span_id,
    )))


async def _profile(connection: asyncpg.Connection, key: str, model: str,
                   params: dict[str, Any] | None = None) -> None:
    provider = await connection.fetchval(
        "INSERT INTO providers (adapter, endpoint, approved, approved_at) "
        "VALUES ('vllm_local', $1, TRUE, now()) RETURNING id", ENDPOINT,
    )
    await connection.execute(
        """INSERT INTO model_profiles (profile_key, provider_id, model_id, revision,
             capabilities, privacy_zone, fallback, params)
           VALUES ($1, $2, $3, 'v1', '["embedding"]'::jsonb, 'internal', '[]'::jsonb, $4::jsonb)""",
        key, provider, model, json.dumps(params or {}),
    )


async def _setup(schema: str) -> tuple[asyncpg.Pool, UUID, UUID]:
    assert DSN
    admin = await asyncpg.connect(DSN)
    await admin.execute(f'CREATE SCHEMA "{schema}"')
    await admin.close()
    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=6,
                                     server_settings={"search_path": f"{schema},public"})
    async with pool.acquire() as connection:
        await apply_migrations(connection)
        actor = uuid4()
        await connection.execute(
            "INSERT INTO users (id, username, display_name) VALUES ($1, 'emb-admin', 'Admin')",
            actor,
        )
        category = uuid4()
        await connection.execute(
            "INSERT INTO categories (id, name, code) VALUES ($1, 'HƯ CẤU', 'hucau')", category
        )
        for number, text in [
            ("HC/1", "Cán bộ được nghỉ phép năm theo quy định HƯ CẤU."),
            ("HC/2", "Cơ quan lập báo cáo định kỳ hằng quý HƯ CẤU."),
            ("HC/3", "Ủy ban nhân dân cấp tỉnh tổ chức kiểm tra HƯ CẤU."),
        ]:
            await _seed_node(connection, category, number, text)
    return pool, actor, category


async def _drop(pool: asyncpg.Pool | None, schema: str) -> None:
    if pool is not None:
        await pool.close()
    assert DSN
    admin = await asyncpg.connect(DSN)
    try:
        await admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
    finally:
        await admin.close()


def _worker(pool: asyncpg.Pool, runtime: RegistryRuntime) -> EmbeddingWorker:
    return EmbeddingWorker(pool, runtime, backoff_seconds=(0.01,), heartbeat_seconds=0.2,
                           stale_seconds=60)


async def _job(pool: asyncpg.Pool, job_id: str) -> asyncpg.Record:
    async with pool.acquire() as connection:
        return await connection.fetchrow("SELECT * FROM embedding_jobs WHERE id = $1",
                                         UUID(job_id))


async def _index(pool: asyncpg.Pool, model: str, status: str | None = None) -> asyncpg.Record:
    async with pool.acquire() as connection:
        return await connection.fetchrow(
            """SELECT i.*, (SELECT count(*) FROM node_embeddings e
                            WHERE e.embedding_index_id = i.id) AS vectors
               FROM embedding_indices i WHERE model_id = $1
                 AND ($2::text IS NULL OR status = $2)
               ORDER BY index_revision DESC LIMIT 1""",
            model, status,
        )


async def test_embedding_model_change_lifecycle_on_postgresql() -> None:
    schema = "test_embjobs_" + uuid4().hex
    pool = None
    try:
        pool, actor, category = await _setup(schema)
        service = FakeEmbeddingService({"fake-a": 8, "fake-b": 12, "fake-c": 8,
                                        "fake-wide": 2100, "fake-huge": 4100})
        runtime = RegistryRuntime(pool, mode="LOCAL", attempt_limit=2, policy=POLICY,
                                  transport=httpx.MockTransport(service.handler))
        async with pool.acquire() as connection:
            for key, model in [("emb-a", "fake-a"), ("emb-b", "fake-b"), ("emb-c", "fake-c"),
                               ("emb-wide", "fake-wide"), ("emb-huge", "fake-huge")]:
                await _profile(connection, key, model)
            await _profile(connection, "emb-short", "fake-a", {"dimensions": 4})
        worker = _worker(pool, runtime)
        search = ComprehensiveSearch(
            SearchService(pool, audit_enabled=False), runtime, semantic_top_n=10,
            semantic_relative_threshold=0.0, rerank_top_n=0, rerank_batch_size=1,
            result_set_ttl_seconds=60, concept_min_terms=1,
        )

        # No index yet: the overview reports the change to make; queries skip semantics.
        overview = await embedding_overview(pool, mode="LOCAL", policy=POLICY, worker=worker)
        assert overview["active_index"] is None and overview["eligible_nodes"] == 3
        assert await search._query_vector("nghỉ phép", actor) == (None, None)

        # 1. Preflight checks connection, model, size and counts the work.
        check = await preflight(pool, runtime, profile_key="emb-a", rebuild=False,
                                mode="LOCAL", policy=POLICY)
        assert check["ok"], check["problems"]
        assert (check["dimensions"], check["storage"], check["to_embed"]) == (8, "vector", 3)
        assert {item["key"] for item in check["checks"]} >= {
            "capability", "approved", "configuration", "connection", "test_vector",
            "vector_values", "storage"}
        with pytest.raises(EmbeddingJobError) as missing:
            await preflight(pool, runtime, profile_key="nope", rebuild=False, mode="LOCAL",
                            policy=POLICY)
        assert missing.value.code == "PROFILE_NOT_FOUND"
        huge = await preflight(pool, runtime, profile_key="emb-huge", rebuild=False,
                               mode="LOCAL", policy=POLICY)
        assert not huge["ok"] and "EMBEDDING_DIMENSIONS_UNSUPPORTED" in huge["problems"]
        short = await preflight(pool, runtime, profile_key="emb-short", rebuild=False,
                                mode="LOCAL", policy=POLICY)
        # The fake ignores "dimensions": a size other than the one configured is refused.
        assert "EMBEDDING_DIMENSION_MISMATCH" in short["problems"]

        job = await create_job(pool, runtime, actor_id=actor, profile_key="emb-a",
                               batch_size=2, rebuild=False, mode="LOCAL", policy=POLICY)
        assert job["status"] == "queued" and job["total_nodes"] == 3
        with pytest.raises(EmbeddingJobError) as duplicate:
            await create_job(pool, runtime, actor_id=actor, profile_key="emb-a",
                             batch_size=2, rebuild=False, mode="LOCAL", policy=POLICY)
        assert duplicate.value.code == "EMBEDDING_JOB_EXISTS"
        assert await worker.run_once()
        done = await _job(pool, job["id"])
        assert (done["status"], done["phase"], done["done_nodes"]) == ("completed", "done", 3)
        index_a = await _index(pool, "fake-a")
        assert index_a["is_active"] and index_a["status"] == "ready"
        assert index_a["vectors"] == 3 and index_a["verified_at"] is not None
        vector, note = await search._query_vector("nghỉ phép", actor)
        assert note is None and vector is not None and len(vector) == 8
        async with pool.acquire() as connection:
            route = await connection.fetchval(
                "SELECT mp.profile_key FROM stage_routes sr JOIN model_profiles mp "
                "ON mp.id = sr.profile_id WHERE sr.mode = 'LOCAL' AND sr.stage = 'embedding'"
            )
        assert route == "emb-a"
        overview = await embedding_overview(pool, mode="LOCAL", policy=POLICY, worker=worker)
        assert overview["active_index"]["model_id"] == "fake-a"
        assert overview["missing_in_active"] == 0 and not overview["change"]["detected"]

        # 2. Change to a model of another size; the service fails after one batch.
        b_check = await preflight(pool, runtime, profile_key="emb-b", rebuild=False,
                                  mode="LOCAL", policy=POLICY)
        assert (b_check["kind"], b_check["to_embed"], b_check["dimensions"]) == (
            "rebuild", 3, 12)
        service.fail_after["fake-b"] = service.calls["fake-b"] + 2  # create_job probe + 1 batch
        job_b = await create_job(pool, runtime, actor_id=actor, profile_key="emb-b",
                                 batch_size=1, rebuild=False, mode="LOCAL", policy=POLICY)
        overview = await embedding_overview(pool, mode="LOCAL", policy=POLICY, worker=worker)
        assert overview["change"]["detected"] and overview["change"]["profile_id"] == "emb-b"
        assert overview["change"]["open_job_id"] == job_b["id"]
        assert await worker.run_once()
        failed = await _job(pool, job_b["id"])
        assert failed["status"] == "failed" and failed["last_error"] == "MODEL_REQUEST_FAILED"
        assert failed["failed_batches"] == 5 and failed["done_nodes"] == 1
        index_b = await _index(pool, "fake-b")
        assert (index_b["status"], index_b["is_active"], index_b["vectors"]) == (
            "failed", False, 1)
        # The old index and model keep serving search, untouched.
        index_a = await _index(pool, "fake-a")
        assert index_a["is_active"] and index_a["vectors"] == 3
        vector, _ = await search._query_vector("nghỉ phép", actor)
        assert vector is not None and len(vector) == 8

        # 3. Retry after the service is back: resumes from the stored vector, switches.
        service.fail_after.pop("fake-b")
        retried = await control_job(pool, actor_id=actor, job_id=UUID(job_b["id"]),
                                    action="retry")
        assert retried["status"] == "queued"
        assert await worker.run_once()
        done_b = await _job(pool, job_b["id"])
        assert done_b["status"] == "completed" and done_b["embedded_nodes"] == 3
        index_b = await _index(pool, "fake-b")
        assert index_b["is_active"] and index_b["vectors"] == 3
        index_a = await _index(pool, "fake-a")
        assert (index_a["status"], index_a["is_active"], index_a["vectors"]) == (
            "retired", False, 3)
        vector, _ = await search._query_vector("nghỉ phép", actor)
        assert vector is not None and len(vector) == 12
        async with pool.acquire() as connection:
            for row in (index_a, index_b):
                valid = await connection.fetchval(
                    "SELECT indisvalid FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
                    "WHERE c.relname = $1", hnsw_index_name(row["id"]),
                )
                assert valid is True  # the old HNSW index is kept as well

        # 4. A newly approved node: detected, catch-up job, pause and resume.
        async with pool.acquire() as connection:
            await _seed_node(connection, category, "HC/4", "Quy định mới về tiền lương HƯ CẤU.")
        overview = await embedding_overview(pool, mode="LOCAL", policy=POLICY, worker=worker)
        assert overview["missing_in_active"] == 1
        catch_up = await preflight(pool, runtime, profile_key="emb-b", rebuild=False,
                                   mode="LOCAL", policy=POLICY)
        assert (catch_up["kind"], catch_up["to_embed"]) == ("catch_up", 1)
        job_c = await create_job(pool, runtime, actor_id=actor, profile_key="emb-b",
                                 batch_size=4, rebuild=False, mode="LOCAL", policy=POLICY)
        await control_job(pool, actor_id=actor, job_id=UUID(job_c["id"]), action="pause")
        assert not await worker.run_once()  # paused jobs are not picked up
        with pytest.raises(EmbeddingJobError) as state:
            await control_job(pool, actor_id=actor, job_id=UUID(job_c["id"]), action="retry")
        assert state.value.code == "EMBEDDING_JOB_STATE"
        await control_job(pool, actor_id=actor, job_id=UUID(job_c["id"]), action="resume")
        assert await worker.run_once()
        assert (await _job(pool, job_c["id"]))["status"] == "completed"
        assert (await _index(pool, "fake-b"))["vectors"] == 4
        with pytest.raises(EmbeddingJobError) as up_to_date:
            await create_job(pool, runtime, actor_id=actor, profile_key="emb-b",
                             batch_size=4, rebuild=False, mode="LOCAL", policy=POLICY)
        assert up_to_date.value.code == "EMBEDDING_UP_TO_DATE"

        # 5. Back to model A: the retired index is reused (only the new node is sent),
        # and a job left "running" by a dead process is recovered after restart.
        back = await preflight(pool, runtime, profile_key="emb-a", rebuild=False,
                               mode="LOCAL", policy=POLICY)
        assert (back["kind"], back["to_embed"], back["already_embedded"]) == ("rebuild", 1, 3)
        job_d = await create_job(pool, runtime, actor_id=actor, profile_key="emb-a",
                                 batch_size=4, rebuild=False, mode="LOCAL", policy=POLICY)
        async with pool.acquire() as connection:
            await connection.execute(
                "UPDATE embedding_jobs SET status = 'running', worker_id = 'dead-process', "
                "heartbeat_at = now() - interval '10 minutes' WHERE id = $1",
                UUID(job_d["id"]),
            )
        restarted = _worker(pool, runtime)
        assert await restarted.run_once()
        assert (await _job(pool, job_d["id"]))["status"] == "completed"
        index_a = await _index(pool, "fake-a")
        assert index_a["is_active"] and index_a["vectors"] == 4
        assert (await _index(pool, "fake-b"))["status"] == "retired"

        # 6. Integrity: a model that does not reproduce its vectors is never switched in.
        service.random_models.add("fake-c")
        job_e = await create_job(pool, runtime, actor_id=actor, profile_key="emb-c",
                                 batch_size=4, rebuild=False, mode="LOCAL", policy=POLICY)
        assert await worker.run_once()
        failed_e = await _job(pool, job_e["id"])
        assert (failed_e["status"], failed_e["last_error"]) == (
            "failed", "EMBEDDING_SAMPLE_MISMATCH")
        assert (await _index(pool, "fake-c"))["status"] == "failed"
        assert (await _index(pool, "fake-a"))["is_active"]
        await control_job(pool, actor_id=actor, job_id=UUID(job_e["id"]), action="cancel")
        assert (await _job(pool, job_e["id"]))["status"] == "cancelled"
        assert (await _index(pool, "fake-c"))["vectors"] == 4  # cancelling keeps vectors

        # 7. Above 2000 dimensions the index uses halfvec and semantic search still works.
        job_f = await create_job(pool, runtime, actor_id=actor, profile_key="emb-wide",
                                 batch_size=4, rebuild=False, mode="LOCAL", policy=POLICY)
        assert await worker.run_once()
        assert (await _job(pool, job_f["id"]))["status"] == "completed"
        async with pool.acquire() as connection:
            wide = await active_index(connection)
            assert wide["model_id"] == "fake-wide" and wide["dimensions"] == 2100
            versions = [row[0] for row in await connection.fetch(
                "SELECT id FROM document_versions")]
            query = service.vector("fake-wide", "Điều 1\nCán bộ được nghỉ phép năm")
            async with connection.transaction():
                hits = await semantic_candidates(
                    connection, index=wide, query_vector=query, version_ids=versions,
                    category_ids=None, doc_types=None, top_n=5)
        assert len(hits) == 4

        # 8. The maintenance script shares the same steps and stays compatible.
        async def embed(texts: list[str]) -> Any:
            return await runtime.embed(texts, profile_key="emb-b", purpose="index")

        result = await build_embeddings(pool, embed, batch_size=4)
        assert result["status"] == "ready" and result["vectors"] == 4
        assert (await _index(pool, "fake-b", "ready"))["is_active"]

        # Nothing was deleted along the way.
        async with pool.acquire() as connection:
            counts = await connection.fetch(
                "SELECT i.model_id, count(e.*) FROM embedding_indices i LEFT JOIN "
                "node_embeddings e ON e.embedding_index_id = i.id GROUP BY i.model_id")
        assert {row[0]: row[1] for row in counts} == {
            "fake-a": 4, "fake-b": 4, "fake-c": 4, "fake-wide": 4}
    finally:
        await _drop(pool, schema)


async def test_embedding_admin_api_on_postgresql(tmp_path: Path) -> None:
    schema = "test_embapi_" + uuid4().hex
    pool = None
    try:
        pool, _actor, _category = await _setup(schema)
        service = FakeEmbeddingService({"fake-a": 8})
        runtime = RegistryRuntime(pool, mode="LOCAL", attempt_limit=2, policy=POLICY,
                                  transport=httpx.MockTransport(service.handler))
        async with pool.acquire() as connection:
            await _profile(connection, "emb-a", "fake-a")
        await create_or_update_user(
            pool, actor_id=uuid4(), username="sysadmin", display_name="Quản trị",
            password="AdminPassword!2026", roles=["SYS_ADMIN"], category_ids=[],
            must_change_password=False,
        )
        await create_or_update_user(
            pool, actor_id=uuid4(), username="reader", display_name="Tra cứu",
            password="ReaderPassword!2026", roles=["USER"], category_ids=[],
            must_change_password=False,
        )
        app = create_app()
        app.state.settings = app.state.settings.__class__(
            database_url=DSN, programs_root=app.state.settings.programs_root,
            operating_mode="LOCAL", llm_attempt_budget=2, session_ttl_seconds=1800,
            retention_approved=False, dev_allow_in_memory_store=False,
            allowed_origins=app.state.settings.allowed_origins,
            max_upload_bytes=app.state.settings.max_upload_bytes,
            max_preview_pages=app.state.settings.max_preview_pages,
            document_store_root=str(tmp_path),
        )
        app.state.db_pool = pool
        app.state.ai_runtime = runtime
        worker = _worker(pool, runtime)
        app.state.embedding_worker = worker
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            async def token(username: str, password: str) -> dict[str, str]:
                response = await client.post("/api/v1/auth/login", json={
                    "username": username, "password": password, "client": "web"})
                assert response.status_code == 200
                return {"Authorization": f"Bearer {response.json()['access_token']}"}

            admin = await token("sysadmin", "AdminPassword!2026")
            reader = await token("reader", "ReaderPassword!2026")
            assert (await client.get("/api/v1/admin/embeddings", headers=reader)).status_code \
                == 403
            status = await client.get("/api/v1/admin/embeddings", headers=admin)
            assert status.status_code == 200
            assert status.json()["active_index"] is None
            assert status.json()["change"]["reason"] == "no_active_index"
            assert status.json()["change"]["pending_nodes"] == 3
            assert [p["profile_id"] for p in status.json()["profiles"]] == ["emb-a"]

            checked = await client.post("/api/v1/admin/embeddings/preflight", headers=admin,
                                        json={"profile_id": "emb-a"})
            assert checked.status_code == 200 and checked.json()["to_embed"] == 3
            unconfirmed = await client.post("/api/v1/admin/embeddings/jobs", headers=admin,
                                            json={"profile_id": "emb-a"})
            assert unconfirmed.status_code == 422
            assert unconfirmed.json()["code"] == "EMBEDDING_CONFIRMATION_REQUIRED"
            created = await client.post("/api/v1/admin/embeddings/jobs", headers=admin,
                                        json={"profile_id": "emb-a", "confirmed": True,
                                              "batch_size": 2})
            assert created.status_code == 201
            job_id = created.json()["id"]
            bad = await client.post(f"/api/v1/admin/embeddings/jobs/{job_id}/explode",
                                    headers=admin)
            assert bad.status_code == 422
            assert await worker.run_once()
            final = (await client.get("/api/v1/admin/embeddings", headers=admin)).json()
            assert final["active_index"]["model_id"] == "fake-a"
            assert final["jobs"][0]["status"] == "completed"
            assert final["jobs"][0]["percent"] == 100.0
            assert final["indices"][0]["state"] == "active"
            late = await client.post(f"/api/v1/admin/embeddings/jobs/{job_id}/pause",
                                     headers=admin)
            assert late.status_code == 409 and late.json()["code"] == "EMBEDDING_JOB_STATE"
            async with pool.acquire() as connection:
                actions = {row[0] for row in await connection.fetch(
                    "SELECT action FROM audit_events")}
            assert {"admin.embedding_preflight", "admin.embedding_job_create",
                    "embedding.index_activated"} <= actions
    finally:
        await _drop(pool, schema)
