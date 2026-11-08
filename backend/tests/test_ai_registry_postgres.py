"""PostgreSQL-backed verification for the model registry and answer runtime."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import AsyncIterator
from contextlib import suppress
from datetime import date
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest
import pytest_asyncio

from app.admin_services import (
    AdminServiceError,
    list_model_registry,
    upsert_model_profile,
    upsert_stage_policy,
    upsert_stage_route,
)
from app.migrations.runner import apply_migrations
from app.model_registry.profiles import OperatingMode
from app.model_registry.runtime import EndpointPolicy, RegistryRuntime
from app.schemas import AnalyzeRequest, Scope, ScopeMode
from app.storage.authorized_search import PostgresAuthorizedNodeSearch
from app.workflow.ai_selection import ConfiguredSelection
from app.workflow.fixed_pipeline import FixedPipeline, PipelineDependencies

DSN = os.environ.get("EVIDENCE_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DSN, reason="No disposable PostgreSQL/pgvector test database configured"
)


@pytest_asyncio.fixture
async def database(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[Any, Any]]:
    """Create a disposable schema while keeping the connection string private."""

    monkeypatch.setenv("EVIDENCE_AI_ALLOWED_REMOTE_DOMAINS", "api.example.test")
    monkeypatch.setenv("EVIDENCE_AI_ALLOWED_LAN_ENDPOINTS", "")
    monkeypatch.setenv("EVIDENCE_REMOTE_PROCESSING_ALLOWED", "true")
    monkeypatch.setenv("EVIDENCE_AI_TIMEOUT_SECONDS", "5")
    monkeypatch.setenv("TEST_AI_API_KEY", "integration-test-key")

    assert DSN
    schema = "test_ai_registry_" + uuid4().hex
    connection = await asyncpg.connect(DSN)
    pool: asyncpg.Pool[Any] | None = None
    try:
        await connection.execute(f'CREATE SCHEMA "{schema}"')
        await connection.execute(f'SET search_path TO "{schema}", public')
        await apply_migrations(connection)
        pool = await asyncpg.create_pool(
            DSN,
            min_size=1,
            max_size=2,
            server_settings={"search_path": f"{schema},public"},
        )
        yield pool, connection
    finally:
        if pool is not None:
            await pool.close()
        with suppress(Exception):
            await connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await connection.close()


async def _insert_user(
    connection: Any,
    user_id: UUID,
    username: str,
    *,
    remote_ai_allowed: bool = False,
    disabled: bool = False,
) -> None:
    await connection.execute(
        """INSERT INTO users
           (id, username, display_name, remote_ai_allowed, disabled_at)
           VALUES ($1, $2, $3, $4, CASE WHEN $5 THEN now() ELSE NULL END)""",
        user_id,
        username,
        username.title(),
        remote_ai_allowed,
        disabled,
    )


async def _insert_document(
    connection: Any,
    *,
    category_id: UUID,
    document_number: str = "381/2026/NĐ-CP",
    classification_level: str = "internal",
    label: str = "Điều 3",
    quote: str = "Mức phụ cấp được xác định theo quy định tại Điều 3.",
) -> tuple[UUID, UUID]:
    document_id = uuid4()
    version_id = uuid4()
    node_id = uuid4()
    page_id = uuid4()
    span_id = uuid4()
    source_hash = hashlib.sha256(str(document_id).encode()).hexdigest()
    await connection.execute(
        """INSERT INTO documents
           (id, doc_type, title, document_number, classification_level)
           VALUES ($1, 'decree', 'Nghị định thử nghiệm', $2, $3)""",
        document_id,
        document_number,
        classification_level,
    )
    await connection.execute(
        "INSERT INTO document_categories (document_id, category_id) VALUES ($1, $2)",
        document_id,
        category_id,
    )
    await connection.execute(
        """INSERT INTO document_versions
           (id, document_id, version_number, original_file_path,
            original_file_sha256, original_filename, review_status)
           VALUES ($1, $2, 1, 'fixture.pdf', $3, 'fixture.pdf', 'approved')""",
        version_id,
        document_id,
        source_hash,
    )
    await connection.execute(
        """INSERT INTO source_provenance (document_version_id, verified_at)
           VALUES ($1, now())""",
        version_id,
    )
    await connection.execute(
        """INSERT INTO source_pages
           (id, document_version_id, page_number, width, height,
            extraction_method, text_quality, text_original)
           VALUES ($1, $2, 1, 595, 842, 'native_text', 'usable', $3)""",
        page_id,
        version_id,
        quote,
    )
    await connection.execute(
        """INSERT INTO source_spans
           (id, page_id, original_offset, original_length, text_original)
           VALUES ($1, $2, 0, $3, $4)""",
        span_id,
        page_id,
        len(quote),
        quote,
    )
    await connection.execute(
        """INSERT INTO document_nodes
           (id, document_id, document_version_id, node_type, label_original,
            path, text_original, text_indexed, text_normalized, text_folded,
            page_start, parse_confidence, review_status, source_span_id)
           VALUES ($1, $2, $3, 'article', $4, $4, $5, $5, $5, $5,
                   1, 0.95, 'approved', $6)""",
        node_id,
        document_id,
        version_id,
        label,
        quote,
        span_id,
    )
    return document_id, node_id


async def _insert_profile_without_admin(
    connection: Any,
    *,
    profile_id: str,
    capabilities: list[str],
) -> None:
    provider_id = await connection.fetchval(
        """INSERT INTO providers (adapter, endpoint, approved)
           VALUES ('openai_compatible', 'http://127.0.0.1:11434/v1', FALSE)
           RETURNING id"""
    )
    await connection.execute(
        """INSERT INTO model_profiles
           (profile_key, provider_id, model_id, revision, capabilities,
            privacy_zone, fallback)
           VALUES ($1, $2, 'unsupported-model', 'r1', $3::jsonb,
                   'internal', '[]'::jsonb)""",
        profile_id,
        provider_id,
        json.dumps(capabilities),
    )


async def _create_runtime_profile(
    pool: Any,
    *,
    actor_id: UUID,
    profile_id: str,
) -> None:
    await upsert_model_profile(
        pool,
        actor_id=actor_id,
        profile_id=profile_id,
        adapter="openai_compatible",
        endpoint="https://api.example.test/v1",
        model_id="integration-model",
        capabilities=["answer"],
        privacy_zone="public",
        revision="integration-r1",
        secret_ref="env:TEST_AI_API_KEY",
        fallback=[],
        provider_approved=True,
    )
    await upsert_stage_route(
        pool,
        actor_id=actor_id,
        mode="API",
        stage="answer",
        profile_id=profile_id,
        fallback=[],
    )


@pytest.mark.asyncio
async def test_admin_registry_persistence_and_route_guards(database: tuple[Any, Any]) -> None:
    pool, connection = database
    actor_id = uuid4()
    await _insert_user(connection, actor_id, "registry-admin")

    saved = await upsert_model_profile(
        pool,
        actor_id=actor_id,
        profile_id="local-answer",
        adapter="ollama_local",
        endpoint="http://127.0.0.1:11434/v1",
        model_id="local-model",
        capabilities=["answer"],
        privacy_zone="internal",
        revision="local-r1",
        secret_ref="env:TEST_AI_API_KEY",
        fallback=[],
        provider_approved=False,
    )
    assert saved["status"] == "saved_unverified"
    row = await connection.fetchrow(
        """SELECT p.approved, mp.secret_ref, mp.health
           FROM model_profiles mp JOIN providers p ON p.id = mp.provider_id
           WHERE mp.profile_key = 'local-answer'"""
    )
    assert row is not None
    assert row["approved"] is False
    assert row["health"] == "unknown"
    assert row["secret_ref"] == "env:TEST_AI_API_KEY"

    with pytest.raises(AdminServiceError) as raw_secret:
        await upsert_model_profile(
            pool,
            actor_id=actor_id,
            profile_id="raw-secret",
            adapter="ollama_local",
            endpoint="http://127.0.0.1:11434/v1",
            model_id="local-model",
            capabilities=["answer"],
            privacy_zone="internal",
            revision="r1",
            secret_ref="sk-raw-key",
            fallback=[],
        )
    assert raw_secret.value.code == "MODEL_SECRET_REF_INVALID"

    with pytest.raises(AdminServiceError) as unsupported_stage:
        await upsert_stage_route(
            pool,
            actor_id=actor_id,
            mode="LOCAL",
            stage="verify",
            profile_id="local-answer",
            fallback=[],
        )
    assert unsupported_stage.value.code == "MODEL_STAGE_UNSUPPORTED"

    await _insert_profile_without_admin(
        connection,
        profile_id="embedding-only",
        capabilities=["embedding"],
    )
    with pytest.raises(AdminServiceError) as bad_capability:
        await upsert_stage_route(
            pool,
            actor_id=actor_id,
            mode="LOCAL",
            stage="answer",
            profile_id="embedding-only",
            fallback=[],
        )
    assert bad_capability.value.code == "MODEL_CAPABILITY_UNAVAILABLE"

    await upsert_model_profile(
        pool,
        actor_id=actor_id,
        profile_id="local-fallback",
        adapter="llama_cpp_local",
        endpoint="http://127.0.0.1:11434/v1",
        model_id="fallback-model",
        capabilities=["answer"],
        privacy_zone="internal",
        revision="r1",
        secret_ref=None,
        fallback=[],
    )
    await upsert_model_profile(
        pool,
        actor_id=actor_id,
        profile_id="public-fallback",
        adapter="openai_compatible",
        endpoint="https://api.example.test/v1",
        model_id="public-model",
        capabilities=["answer"],
        privacy_zone="public",
        revision="r1",
        secret_ref="env:TEST_AI_API_KEY",
        fallback=[],
    )
    await upsert_model_profile(
        pool,
        actor_id=actor_id,
        profile_id="local-fallback",
        adapter="llama_cpp_local",
        endpoint="http://127.0.0.1:11434/v1",
        model_id="fallback-model",
        capabilities=["answer"],
        privacy_zone="internal",
        revision="r1",
        secret_ref=None,
        fallback=[],
    )
    with pytest.raises(AdminServiceError) as zone_mismatch:
        await upsert_stage_route(
            pool,
            actor_id=actor_id,
            mode="LOCAL",
            stage="answer",
            profile_id="local-answer",
            fallback=["public-fallback"],
        )
    assert zone_mismatch.value.code == "MODEL_FALLBACK_ZONE_MISMATCH"

    await upsert_model_profile(
        pool,
        actor_id=actor_id,
        profile_id="local-answer",
        adapter="ollama_local",
        endpoint="http://127.0.0.1:11434/v1",
        model_id="local-model",
        capabilities=["answer"],
        privacy_zone="internal",
        revision="local-r1",
        secret_ref="env:TEST_AI_API_KEY",
        fallback=["local-fallback"],
    )
    with pytest.raises(AdminServiceError) as fallback_cycle:
        await upsert_model_profile(
            pool,
            actor_id=actor_id,
            profile_id="local-fallback",
            adapter="llama_cpp_local",
            endpoint="http://127.0.0.1:11434/v1",
            model_id="fallback-model",
            capabilities=["answer"],
            privacy_zone="internal",
            revision="r1",
            secret_ref=None,
            fallback=["local-answer"],
        )
    assert fallback_cycle.value.code == "MODEL_FALLBACK_CYCLE"


@pytest.mark.asyncio
async def test_runtime_acl_probe_selection_and_pipeline(database: tuple[Any, Any]) -> None:
    pool, connection = database
    principal_id = uuid4()
    await _insert_user(connection, principal_id, "runtime-user", remote_ai_allowed=False)

    good_category = uuid4()
    bad_category = uuid4()
    restricted_category = uuid4()
    await connection.execute(
        """INSERT INTO categories (id, name, code, remote_processing_allowed)
           VALUES ($1, 'Remote-safe', 'REMOTE_SAFE', TRUE),
                  ($2, 'Remote-blocked', 'REMOTE_BLOCKED', FALSE),
                  ($3, 'Restricted-fixture', 'RESTRICTED_FIXTURE', TRUE)""",
        good_category,
        bad_category,
        restricted_category,
    )
    await connection.execute(
        """INSERT INTO category_acl (category_id, user_id, can_query)
           VALUES ($1, $3, TRUE), ($2, $3, TRUE)""",
        good_category,
        bad_category,
        principal_id,
    )
    good_document, _ = await _insert_document(connection, category_id=good_category)
    restricted_document, _ = await _insert_document(
        connection,
        category_id=restricted_category,
        document_number="382/2026/NĐ-CP",
        classification_level="restricted",
    )
    blocked_document, _ = await _insert_document(
        connection,
        category_id=bad_category,
        document_number="383/2026/NĐ-CP",
        label="Điều 4",
        quote="Nội dung không được phép xử lý từ xa.",
    )

    await _create_runtime_profile(pool, actor_id=principal_id, profile_id="api-answer")
    runtime = RegistryRuntime(
        pool,
        OperatingMode.API,
        attempt_limit=2,
        policy=EndpointPolicy.from_env(),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"data": [{"id": "integration-model"}]},
                request=request,
            )
        ),
    )

    assert await runtime._remote_authorized(principal_id, [good_document]) is False
    await connection.execute(
        "UPDATE users SET remote_ai_allowed = TRUE WHERE id = $1", principal_id
    )
    assert await runtime._remote_authorized(principal_id, [good_document]) is True

    await connection.execute(
        "UPDATE categories SET remote_processing_allowed = FALSE WHERE id = $1",
        good_category,
    )
    assert await runtime._remote_authorized(principal_id, [good_document]) is False
    await connection.execute(
        "UPDATE categories SET remote_processing_allowed = TRUE WHERE id = $1",
        good_category,
    )

    await connection.execute(
        "UPDATE documents SET classification_level = 'restricted' WHERE id = $1",
        good_document,
    )
    assert await runtime._remote_authorized(principal_id, [good_document]) is False
    await connection.execute(
        "UPDATE documents SET classification_level = 'internal' WHERE id = $1",
        good_document,
    )

    await connection.execute(
        "DELETE FROM category_acl WHERE category_id = $1 AND user_id = $2",
        good_category,
        principal_id,
    )
    assert await runtime._remote_authorized(principal_id, [good_document]) is False
    await connection.execute(
        "INSERT INTO category_acl (category_id, user_id, can_query) VALUES ($1, $2, TRUE)",
        good_category,
        principal_id,
    )

    await connection.execute(
        "UPDATE users SET disabled_at = now() WHERE id = $1", principal_id
    )
    assert await runtime._remote_authorized(principal_id, [good_document]) is False
    await connection.execute(
        "UPDATE users SET disabled_at = NULL WHERE id = $1", principal_id
    )
    assert await runtime._remote_authorized(principal_id, [blocked_document]) is False
    assert await runtime._remote_authorized(principal_id, [restricted_document]) is False
    assert await runtime._remote_authorized(principal_id, [good_document]) is True

    calls: list[httpx.Request] = []

    def dispatch(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path.endswith("/models"):
            return httpx.Response(
                200,
                json={"data": [{"id": "integration-model"}]},
                request=request,
            )
        body = json.loads(request.content)
        candidates = json.loads(body["messages"][1]["content"])["candidates"]
        selection = {"evidence_ids": [candidates[0]["id"]]}
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(selection)}}]},
            request=request,
        )

    runtime = RegistryRuntime(
        pool,
        OperatingMode.API,
        attempt_limit=2,
        policy=EndpointPolicy.from_env(),
        transport=httpx.MockTransport(dispatch),
    )
    probe = await runtime.probe("api-answer")
    assert probe["status"] == "ready"
    assert probe["health"] == "ready"

    scope = Scope(
        scope_mode=ScopeMode.SELECTED,
        category_ids=[good_category],
        as_of_date=date(2026, 10, 26),
    )
    search = PostgresAuthorizedNodeSearch(pool)
    evidence = await search.search(
        principal_id=principal_id,
        scope=scope,
        query="Điều 3 381/2026/NĐ-CP",
    )
    assert len(evidence) == 1
    expected_id = evidence[0].evidence_id
    selected = await ConfiguredSelection(runtime)(
        "Điều 3 381/2026/NĐ-CP", evidence, principal_id=principal_id
    )
    assert selected.evidence_ids == [expected_id]
    assert selected.external_api_used is True
    assert [request.method for request in calls] == ["GET", "POST"]
    assert calls[0].url.path == "/v1/models"
    assert calls[1].url.path == "/v1/chat/completions"
    assert json.loads(calls[1].content)["model"] == "integration-model"
    actual_header = calls[1].headers.get("authorization", "")
    expected_digest = hashlib.sha256(
        f"Bearer {os.environ['TEST_AI_API_KEY']}".encode()
    ).hexdigest()
    assert hashlib.sha256(actual_header.encode()).hexdigest() == expected_digest

    pipeline = FixedPipeline(
        PipelineDependencies(
            search_authorized_nodes=search,
            select_evidence=ConfiguredSelection(runtime),
        ),
        operating_mode="API",
        llm_attempt_budget=2,
    )
    response = await pipeline.execute(
        AnalyzeRequest(question="Điều 3 381/2026/NĐ-CP quy định gì?", scope=scope),
        principal_id=principal_id,
    )
    assert response.ai_selection_applied is True
    assert response.external_ai_used is True and response.ai_limited is False
    assert response.evidence[0].evidence_id == expected_id
    assert response.evidence[0].quote_exact == "Mức phụ cấp được xác định theo quy định tại Điều 3."
    assert response.claims[0].text == response.evidence[0].quote_exact



@pytest.mark.asyncio
async def test_hybrid_auto_route_stage_policy_and_cost_cap(database: tuple[Any, Any]) -> None:
    pool, connection = database
    actor_id = uuid4()
    await _insert_user(connection, actor_id, "policy-admin")
    await upsert_model_profile(
        pool, actor_id=actor_id, profile_id="loc", adapter="ollama_local",
        endpoint="http://127.0.0.1:11434/v1", model_id="local-model", capabilities=["answer"],
        privacy_zone="internal", revision="r1", secret_ref=None, fallback=[],
        provider_approved=True,
    )
    await upsert_model_profile(
        pool, actor_id=actor_id, profile_id="cloud", adapter="openai_compatible",
        endpoint="https://api.example.test/v1", model_id="cloud-model", capabilities=["answer"],
        privacy_zone="public", revision="r1", secret_ref="env:TEST_AI_API_KEY", fallback=[],
        provider_approved=True,
        costs={"input_price_per_mtok": 1.0, "output_price_per_mtok": 4.0,
               "daily_cost_limit": 0.5, "monthly_cost_limit": None},
    )

    # Local Only has no way out to an API, and an escalation must be public.
    with pytest.raises(AdminServiceError) as local_escalation:
        await upsert_stage_route(
            pool, actor_id=actor_id, mode="LOCAL", stage="answer", profile_id="loc",
            fallback=[], escalation_profile_id="cloud",
        )
    assert local_escalation.value.code == "MODEL_ESCALATION_NOT_ALLOWED"
    with pytest.raises(AdminServiceError) as local_target:
        await upsert_stage_route(
            pool, actor_id=actor_id, mode="API", stage="answer", profile_id="loc",
            fallback=[], escalation_profile_id="loc",
        )
    assert local_target.value.code == "MODEL_ESCALATION_NOT_PUBLIC"
    with pytest.raises(AdminServiceError) as no_check_stage:
        await upsert_stage_route(
            pool, actor_id=actor_id, mode="API", stage="embedding", profile_id="loc",
            fallback=[], escalation_profile_id="cloud",
        )
    assert no_check_stage.value.code == "MODEL_ESCALATION_NOT_ALLOWED"

    # API mode (Hybrid Auto): the main route is the local model.
    saved = await upsert_stage_route(
        pool, actor_id=actor_id, mode="API", stage="answer", profile_id="loc",
        fallback=[], escalation_profile_id="cloud",
    )
    assert saved["escalation_profile_id"] == "cloud"
    with pytest.raises(AdminServiceError) as demoted:
        await upsert_model_profile(
            pool, actor_id=actor_id, profile_id="cloud", adapter="openai_compatible",
            endpoint="http://127.0.0.1:11434/v1", model_id="cloud-model",
            capabilities=["answer"], privacy_zone="internal", revision="r2",
            secret_ref=None, fallback=[],
        )
    assert demoted.value.code == "MODEL_ESCALATION_NOT_PUBLIC"

    with pytest.raises(AdminServiceError) as too_many:
        await upsert_stage_policy(
            pool, actor_id=actor_id, mode="API", stage="answer", max_attempts=11,
            max_output_tokens=None, timeout_seconds=None, max_concurrency=None,
        )
    assert too_many.value.code == "INVALID_REQUEST"
    await upsert_stage_policy(
        pool, actor_id=actor_id, mode="API", stage="answer", max_attempts=4,
        max_output_tokens=256, timeout_seconds=8, max_concurrency=3,
    )

    registry = await list_model_registry(pool)
    route = next(item for item in registry["routes"] if item["mode"] == "API")
    assert route["profile_id"] == "loc" and route["escalation_profile_id"] == "cloud"
    assert registry["stage_policies"][0]["max_attempts"] == 4
    cloud = next(item for item in registry["profiles"] if item["profile_id"] == "cloud")
    assert cloud["daily_cost_limit"] == 0.5
    assert {item["stage"] for item in registry["stages"]} >= {"answer", "summarize"}

    runtime = RegistryRuntime(
        pool, OperatingMode.API, attempt_limit=2, policy=EndpointPolicy.from_env(),
    )
    plan = await runtime._load_plan("answer")
    assert plan is not None and plan.escalation is not None
    assert [item.profile_id for item in plan.candidates] == ["loc"]
    assert plan.policy.max_attempts == 4 and plan.policy.max_output_tokens == 256
    assert not await runtime._over_cost_limit(plan.escalation)
    await connection.execute(
        """INSERT INTO ai_usage_events (mode, stage, profile_key, outcome, estimated_cost)
           VALUES ('API', 'answer', 'cloud', 'ok', 0.5)"""
    )
    assert await runtime._over_cost_limit(plan.escalation)
    local_plan = await RegistryRuntime(
        pool, OperatingMode.LOCAL, attempt_limit=2, policy=EndpointPolicy.from_env(),
    )._load_plan("answer")
    assert local_plan is None