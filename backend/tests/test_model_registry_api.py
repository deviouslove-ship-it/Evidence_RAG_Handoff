"""Model Registry Admin API on PostgreSQL: typed keys, multi-role profiles, checks.

Legacy single-role profiles and ``env:`` references keep working; the model server is a
mock transport.  Keys and legal text are invented.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import asyncpg
import httpx
import pytest

from app.admin_services import (
    AdminServiceError,
    create_or_update_user,
    list_model_registry,
    upsert_model_profile,
)
from app.main import create_app
from app.migrations.runner import apply_migrations
from app.model_registry.runtime import EndpointPolicy, RegistryRuntime
from app.model_registry.secret_store import SecretStore

DSN = os.environ.get("EVIDENCE_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="No disposable PostgreSQL configured")
KEY = "sk-invented-typed-key-98765"
REPLACEMENT = "sk-replacement"
WRONG = "sk-wrong"
POLICY = EndpointPolicy(allowed_remote_domains=frozenset({"api.example.test"}),
                        remote_processing_allowed=True, timeout_seconds=5)
GENERATION = ["answer", "summarize", "expand", "relation", "label", "rerank"]


class ModelServer:
    def __init__(self) -> None:
        self.models = ["model-a"]
        self.seen_keys: list[str | None] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.seen_keys.append(request.headers.get("authorization"))
        if request.url.host == "api.example.test" and (
                request.headers.get("authorization") != f"Bearer {KEY}"):
            return httpx.Response(401, request=request)
        if request.url.path.endswith("/models"):
            return httpx.Response(200, request=request,
                                  json={"data": [{"id": name} for name in self.models]})
        return httpx.Response(200, request=request, json={
            "choices": [{"message": {"content": '{"ok": true}'}}]})


def body(profile_id: str = "api-1", **changes: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "profile_id": profile_id, "adapter": "openai_compatible",
        "endpoint": "https://api.example.test/v1", "model_id": "model-a",
        "capabilities": GENERATION[:5], "privacy_zone": "public", "revision": "v1",
        "provider_approved": True, "params": {"json_mode": True, "max_tokens": 512},
    }
    payload.update(changes)
    return payload


@pytest.fixture
async def client(tmp_path: Path):
    assert DSN
    schema = "test_registry_api_" + uuid4().hex
    admin_connection = await asyncpg.connect(DSN)
    await admin_connection.execute(f'CREATE SCHEMA "{schema}"')
    await admin_connection.close()
    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=4,
                                     server_settings={"search_path": f"{schema},public"})
    try:
        async with pool.acquire() as connection:
            await apply_migrations(connection)
        for name, roles in (("sysadmin", ["SYS_ADMIN"]), ("reader", ["USER"])):
            await create_or_update_user(
                pool, actor_id=uuid4(), username=name, display_name=name,
                password="RegistryPassword!2026", roles=roles, category_ids=[],
                must_change_password=False)
        server = ModelServer()
        store = SecretStore(tmp_path / "keys",
                            (lambda data: data[::-1], lambda data: data[::-1]))
        runtime = RegistryRuntime(pool, mode="API", attempt_limit=2, policy=POLICY,
                                  transport=httpx.MockTransport(server.handler), secrets=store)
        app = create_app()
        app.state.settings = app.state.settings.__class__(
            database_url=DSN, programs_root=app.state.settings.programs_root,
            operating_mode="API", llm_attempt_budget=2, session_ttl_seconds=1800,
            retention_approved=False, dev_allow_in_memory_store=False,
            allowed_origins=app.state.settings.allowed_origins,
            max_upload_bytes=app.state.settings.max_upload_bytes,
            max_preview_pages=app.state.settings.max_preview_pages,
            document_store_root=str(tmp_path))
        app.state.db_pool = pool
        app.state.ai_runtime = runtime
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="http://test") as http:
            async def token(name: str) -> dict[str, str]:
                response = await http.post("/api/v1/auth/login", json={
                    "username": name, "password": "RegistryPassword!2026", "client": "web"})
                assert response.status_code == 200
                return {"Authorization": f"Bearer {response.json()['access_token']}"}

            yield http, await token("sysadmin"), await token("reader"), pool, store, server
    finally:
        await pool.close()
        cleanup = await asyncpg.connect(DSN)
        await cleanup.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await cleanup.close()


async def _dump(pool: Any) -> str:
    """Every text the database holds about models, audit included."""

    async with pool.acquire() as connection:
        parts = [str(await connection.fetchval(
            f"SELECT coalesce(string_agg(row_to_json(t)::text, ' '), '') FROM {table} t"))
            for table in ("model_profiles", "providers", "audit_events", "stage_routes")]
    return " ".join(parts)


async def test_typed_key_is_stored_encrypted_and_referenced_never_returned(client) -> None:
    http, admin, _, pool, store, server = client
    saved = await http.post("/api/v1/admin/model-registry", headers=admin,
                            json=body(api_key=KEY))
    assert saved.status_code == 201 and saved.json()["status"] == "saved_unverified"
    registry = (await http.get("/api/v1/admin/model-registry", headers=admin)).json()
    profile = registry["profiles"][0]
    assert profile["secret_ref"].startswith("secret:") and profile["capabilities"] == GENERATION[:5]
    assert registry["secret_store"] == {"available": True}
    name = profile["secret_ref"].removeprefix("secret:")
    assert store.get(name) == KEY
    everything = await _dump(pool) + json.dumps(registry) + saved.text
    assert KEY not in everything, "the key exists only in the key store"
    audit = await http.get("/api/v1/admin/audit-events", headers=admin)
    assert KEY not in audit.text and "api_key" not in audit.text
    # Re-saving without retyping the key keeps using the stored one.
    again = await http.post("/api/v1/admin/model-registry", headers=admin,
                            json=body(secret_ref=profile["secret_ref"], model_id="model-a"))
    assert again.status_code == 201
    checked = await http.post("/api/v1/admin/model-registry/api-1/test", headers=admin)
    assert checked.json()["health"] == "ready"
    assert f"Bearer {KEY}" in server.seen_keys


async def test_refused_profile_does_not_replace_a_stored_key(client) -> None:
    http, admin, _, _, store, _ = client
    await http.post("/api/v1/admin/model-registry", headers=admin, json=body(api_key=KEY))
    name = (await http.get("/api/v1/admin/model-registry", headers=admin)).json()[
        "profiles"][0]["secret_ref"].removeprefix("secret:")
    refused = await http.post("/api/v1/admin/model-registry", headers=admin, json=body(
        api_key=REPLACEMENT, adapter="not-an-adapter"))
    assert refused.status_code == 422
    assert store.get(name) == KEY
    mixed = await http.post("/api/v1/admin/model-registry", headers=admin, json=body(
        api_key=REPLACEMENT, capabilities=["answer", "embedding"]))
    assert mixed.status_code == 422 and mixed.json()["code"] == "MODEL_STAGE_UNSUPPORTED"
    assert store.get(name) == KEY


async def test_key_cannot_be_typed_when_the_store_is_unavailable(client) -> None:
    http, admin, _, pool, _, _ = client
    http._transport.app.state.ai_runtime.secrets = SecretStore(None)  # type: ignore[attr-defined]
    response = await http.post("/api/v1/admin/model-registry", headers=admin,
                               json=body(api_key=KEY))
    assert response.status_code == 503 and response.json()["code"] == "SECRET_STORE_UNAVAILABLE"
    registry = (await http.get("/api/v1/admin/model-registry", headers=admin)).json()
    assert registry["profiles"] == [] and registry["secret_store"] == {"available": False}
    # The legacy way still works: a reference to a variable of the server process.
    legacy = await http.post("/api/v1/admin/model-registry", headers=admin,
                             json=body(secret_ref="env:INVENTED_AI_KEY"))
    assert legacy.status_code == 201
    assert "INVENTED_AI_KEY" in await _dump(pool)


async def test_only_administrators_manage_and_test_models(client) -> None:
    http, _, reader, _, _, _ = client
    for call in (
        http.post("/api/v1/admin/model-registry/test", headers=reader, json=body()),
        http.post("/api/v1/admin/model-registry/api-1/test", headers=reader),
        http.post("/api/v1/admin/model-registry", headers=reader, json=body(api_key=KEY)),
    ):
        assert (await call).status_code == 403


async def test_draft_check_stores_nothing_and_reports_codes(client) -> None:
    http, admin, _, pool, store, server = client
    ok = await http.post("/api/v1/admin/model-registry/test", headers=admin,
                         json=body(api_key=KEY))
    assert ok.status_code == 200 and ok.json()["usable"] and ok.json()["ok"]
    assert [c["id"] for c in ok.json()["checks"]][:3] == ["config", "secret", "connect"]
    wrong_key = await http.post("/api/v1/admin/model-registry/test", headers=admin,
                                json=body(api_key=WRONG))
    assert not wrong_key.json()["ok"]
    assert wrong_key.json()["checks"][-1] == {"id": "connect", "status": "fail",
                                              "code": "AUTH_FAILED"}
    server.models = ["only-other"]
    missing = await http.post("/api/v1/admin/model-registry/test", headers=admin,
                              json=body(api_key=KEY))
    assert missing.json()["checks"][-1]["code"] == "MODEL_NOT_FOUND"
    assert missing.json()["models"] == ["only-other"]
    blocked = await http.post("/api/v1/admin/model-registry/test", headers=admin, json=body(
        api_key=KEY, endpoint="https://not-allowed.example.test/v1"))
    assert blocked.json()["checks"][0] == {"id": "config", "status": "fail",
                                           "code": "AI_EGRESS_DENIED"}
    bad_roles = await http.post("/api/v1/admin/model-registry/test", headers=admin, json=body(
        capabilities=["embedding", "answer"]))
    assert bad_roles.status_code == 422
    registry = (await http.get("/api/v1/admin/model-registry", headers=admin)).json()
    assert registry["profiles"] == [] and not list((store.root or Path()).glob("*.key"))
    texts = await _dump(pool)
    assert KEY not in texts and WRONG not in texts


async def test_saved_check_records_the_health_the_runtime_requires(client) -> None:
    http, admin, _, _, _, server = client
    await http.post("/api/v1/admin/model-registry", headers=admin, json=body(api_key=KEY))
    first = (await http.post("/api/v1/admin/model-registry/api-1/test", headers=admin)).json()
    assert first["status"] == "ready" and first["health"] == "ready" and first["usable"]
    listed = (await http.get("/api/v1/admin/model-registry", headers=admin)).json()
    assert listed["profiles"][0]["health"] == "ready"
    server.models = []
    gone = (await http.post("/api/v1/admin/model-registry/api-1/test", headers=admin)).json()
    assert gone["health"] == "unhealthy" and gone["status"] == "unhealthy"
    # Editing the profile resets its health: it must be checked again before use.
    await http.post("/api/v1/admin/model-registry", headers=admin, json=body(
        secret_ref=listed["profiles"][0]["secret_ref"], model_id="model-b"))
    after = (await http.get("/api/v1/admin/model-registry", headers=admin)).json()
    assert after["profiles"][0]["health"] == "unknown"
    unapproved = body("api-2", provider_approved=False, api_key=KEY)
    await http.post("/api/v1/admin/model-registry", headers=admin, json=unapproved)
    result = (await http.post("/api/v1/admin/model-registry/api-2/test", headers=admin)).json()
    assert result["status"] == "unapproved" and result["health"] == "unknown"
    assert not result["usable"]
    missing = (await http.post("/api/v1/admin/model-registry/none/test", headers=admin)).json()
    assert missing["status"] == "not_configured"


async def test_multi_role_profile_is_assignable_and_legacy_profiles_are_unchanged(client) -> None:
    http, admin, _, pool, _, _ = client
    async with pool.acquire() as connection:
        actor = await connection.fetchval("SELECT id FROM users WHERE username = 'sysadmin'")
    await upsert_model_profile(  # a profile exactly as before this change
        pool, actor_id=actor, profile_id="legacy-summarize", adapter="ollama_local",
        endpoint="http://127.0.0.1:11434/v1", model_id="legacy-model",
        capabilities=["summarize"], privacy_zone="internal", revision="r1",
        secret_ref=None, fallback=[], provider_approved=True,
        params={"max_tokens": 1024, "response_format": {"type": "json_object"}})
    local = body("local-1", adapter="vllm_local", endpoint="http://127.0.0.1:8000/v1",
                 privacy_zone="internal", capabilities=GENERATION)
    assert (await http.post("/api/v1/admin/model-registry", headers=admin,
                            json=local)).status_code == 201
    for stage in ("answer", "summarize", "label"):
        routed = await http.post("/api/v1/admin/model-registry/routes", headers=admin, json={
            "mode": "LOCAL", "stage": stage, "profile_id": "local-1", "fallback": []})
        assert routed.status_code == 200, routed.text
    wrong = await http.post("/api/v1/admin/model-registry/routes", headers=admin, json={
        "mode": "LOCAL", "stage": "answer", "profile_id": "legacy-summarize", "fallback": []})
    assert wrong.status_code == 422 and wrong.json()["code"] == "MODEL_CAPABILITY_UNAVAILABLE"
    local_escalation = await http.post("/api/v1/admin/model-registry/routes", headers=admin, json={
        "mode": "LOCAL", "stage": "answer", "profile_id": "local-1", "fallback": [],
        "escalation_profile_id": "local-1"})
    assert local_escalation.status_code == 422
    registry = await list_model_registry(pool)
    legacy = next(p for p in registry["profiles"] if p["profile_id"] == "legacy-summarize")
    assert legacy["capabilities"] == ["summarize"]
    assert legacy["params"] == {"max_tokens": 1024, "response_format": {"type": "json_object"}}
    with pytest.raises(AdminServiceError, match="MODEL_STAGE_UNSUPPORTED"):
        await upsert_model_profile(
            pool, actor_id=actor, profile_id="bad", adapter="ollama_local",
            endpoint="http://127.0.0.1:11434/v1", model_id="m", capabilities=["embedding", "label"],
            privacy_zone="internal", revision="r1", secret_ref=None, fallback=[])
    with pytest.raises(AdminServiceError, match="MODEL_STAGE_UNSUPPORTED"):
        await upsert_model_profile(
            pool, actor_id=actor, profile_id="bad", adapter="ollama_local",
            endpoint="http://127.0.0.1:11434/v1", model_id="m", capabilities=["verify"],
            privacy_zone="internal", revision="r1", secret_ref=None, fallback=[])
    for raw in ("sk-raw-key", "secret:../x", "env:DATABASE_URL"):
        with pytest.raises(AdminServiceError):
            await upsert_model_profile(
                pool, actor_id=actor, profile_id="bad", adapter="ollama_local",
                endpoint="http://127.0.0.1:11434/v1", model_id="m", capabilities=["answer"],
                privacy_zone="internal", revision="r1", secret_ref=raw, fallback=[])
