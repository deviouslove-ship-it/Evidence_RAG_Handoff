"""Focused tests for the bounded registry-backed AI runtime."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from app.model_registry.adapters import AdapterError, OpenAICompatibleAdapter
from app.model_registry.profiles import ModelProfile, OperatingMode, PrivacyZone
from app.model_registry.runtime import (
    EndpointPolicy,
    RegistryRuntime,
    _canonical_selection,
    validate_profile,
)
from app.schemas import ModelParams


class _Transaction:
    async def __aenter__(self) -> _Transaction:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


class _Connection:
    def __init__(
        self,
        profiles: dict[str, dict[str, Any]],
        route: dict[str, Any],
        *,
        remote_ai_allowed: bool = True,
        disabled: bool = False,
        evidence_allowed: bool = True,
        config_changed_on_update: bool = False,
    ) -> None:
        self.profiles = profiles
        self.route = route
        self.remote_ai_allowed = remote_ai_allowed
        self.disabled = disabled
        self.evidence_allowed = evidence_allowed
        self.config_changed_on_update = config_changed_on_update
        self.health_updates: list[tuple[str, str]] = []
        self.profile_fetches = 0

    def transaction(self) -> _Transaction:
        return _Transaction()

    async def execute(self, query: str, *args: Any) -> str:
        if "set_config('app.user_id'" in query:
            return "SELECT 1"
        if "UPDATE model_profiles" in query:
            if self.config_changed_on_update:
                self.profiles[str(args[1])] = {
                    **self.profiles[str(args[1])],
                    "model_id": "new-model",
                }
            profile = self.profiles.get(str(args[1]))
            matches = profile is not None and all(
                (
                    profile.get("model_id") == args[2],
                    profile.get("revision") == args[3],
                    profile.get("secret_ref") == args[4],
                    profile.get("endpoint") == args[5],
                    profile.get("adapter") == args[6],
                    bool(profile.get("provider_approved")) == bool(args[7]),
                )
            )
            if matches:
                self.health_updates.append((str(args[1]), str(args[0])))
                return "UPDATE 1"
            return "UPDATE 0"
        return "OK"

    async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None:
        lowered = query.lower()
        if "remote_ai_allowed" in lowered:
            return {
                "remote_ai_allowed": self.remote_ai_allowed,
                "disabled_at": object() if self.disabled else None,
            }
        if "from stage_routes" in lowered:
            return self.route
        if "from model_profiles" in lowered:
            self.profile_fetches += 1
            return self.profiles.get(str(args[0]))
        return None

    async def fetchval(self, query: str, *args: Any) -> Any:
        if "registry evidence gate" in query:
            return self.evidence_allowed
        return None


class _Pool:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[_Connection]:
        yield self.connection


def _profile(
    profile_id: str = "p1",
    *,
    endpoint: str = "http://127.0.0.1:11434/v1",
    zone: PrivacyZone = PrivacyZone.INTERNAL,
    approved: bool = True,
    health: str = "ready",
    secret_ref: str | None = None,
) -> dict[str, Any]:
    return {
        "profile_key": profile_id,
        "adapter": "openai_compatible",
        "endpoint": endpoint,
        "model_id": "configured-model",
        "capabilities": ["answer"],
        "privacy_zone": zone.value,
        "revision": "r1",
        "secret_ref": secret_ref,
        "fallback": [],
        "params": {"max_tokens": 128},
        "provider_approved": approved,
        "health": health,
    }


def _route(*fallback: str) -> dict[str, Any]:
    return {"profile_key": "p1", "fallback": list(fallback)}


def _transport(
    handler: Callable[[httpx.Request, int], httpx.Response],
) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    requests: list[httpx.Request] = []
    count = 0

    def dispatch(request: httpx.Request) -> httpx.Response:
        nonlocal count
        requests.append(request)
        response = handler(request, count)
        count += 1
        return response

    return httpx.MockTransport(dispatch), requests


def test_endpoint_policy_from_env_and_strict_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVIDENCE_AI_ALLOWED_REMOTE_DOMAINS", "api.example.test, API2.example.test")
    monkeypatch.setenv("EVIDENCE_AI_ALLOWED_LAN_ENDPOINTS", "http://10.0.0.5:8000/v1/")
    monkeypatch.setenv("EVIDENCE_REMOTE_PROCESSING_ALLOWED", "true")
    monkeypatch.setenv("EVIDENCE_AI_TIMEOUT_SECONDS", "7.5")

    policy = EndpointPolicy.from_env()

    assert policy.remote_processing_allowed is True
    assert policy.timeout_seconds == 7.5
    assert policy.allows_endpoint("https://api.example.test/v1", OperatingMode.API)
    assert policy.allows_endpoint("http://10.0.0.5:8000/v1", OperatingMode.LOCAL)
    assert not policy.allows_endpoint("http://10.0.0.6:8000/v1", OperatingMode.LOCAL)

    monkeypatch.setenv("EVIDENCE_AI_TIMEOUT_SECONDS", "30.01")
    with pytest.raises(ValueError, match="timeout"):
        EndpointPolicy.from_env()
    for invalid in ("nan", "inf", "-inf"):
        monkeypatch.setenv("EVIDENCE_AI_TIMEOUT_SECONDS", invalid)
        with pytest.raises(ValueError, match="timeout"):
            EndpointPolicy.from_env()


def test_local_policy_rejects_public_and_native_ollama_endpoint() -> None:
    policy = EndpointPolicy(
        allowed_remote_domains=frozenset(),
        allowed_lan_endpoints=frozenset(),
        remote_processing_allowed=False,
        timeout_seconds=5,
    )
    local = ModelProfile(
        "local",
        "ollama_local",
        "http://127.0.0.1:11434/v1",
        "m",
        frozenset({"answer"}),
        PrivacyZone.INTERNAL,
        "r1",
    )
    public = ModelProfile(
        "public",
        "openai_compatible",
        "https://api.example.test/v1",
        "m",
        frozenset({"answer"}),
        PrivacyZone.INTERNAL,
        "r1",
    )
    native_ollama = ModelProfile(
        "ollama",
        "ollama_local",
        "http://127.0.0.1:11434/api",
        "m",
        frozenset({"answer"}),
        PrivacyZone.INTERNAL,
        "r1",
    )
    restricted_remote = ModelProfile(
        "restricted",
        "openai_compatible",
        "https://api.example.test/v1",
        "m",
        frozenset({"answer"}),
        PrivacyZone.RESTRICTED,
        "r1",
    )

    validate_profile(local, OperatingMode.LOCAL, policy)
    with pytest.raises(ValueError):
        validate_profile(public, OperatingMode.LOCAL, policy)
    with pytest.raises(ValueError):
        validate_profile(native_ollama, OperatingMode.LOCAL, policy)
    with pytest.raises(ValueError):
        validate_profile(restricted_remote, OperatingMode.API, policy)


def test_profile_secret_must_be_env_reference() -> None:
    profile = ModelProfile(
        "p",
        "openai_compatible",
        "https://api.example.test/v1",
        "m",
        frozenset({"answer"}),
        PrivacyZone.PUBLIC,
        "r1",
        secret_ref="sk-raw-key",
    )
    with pytest.raises(ValueError, match="SECRET"):
        validate_profile(profile)


@pytest.mark.parametrize("scheme", ["http", "https"])
async def test_localhost_requests_connect_to_loopback_without_dns(scheme: str) -> None:
    observed: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        return httpx.Response(200, json={"data": [{"id": "test-model"}]})

    profile = ModelProfile(
        profile_id="local", adapter="openai_compatible", endpoint=f"{scheme}://localhost:8765/v1",
        model_id="test-model", capabilities=frozenset({"answer"}),
        privacy_zone=PrivacyZone.INTERNAL, revision="test",
    )
    adapter = OpenAICompatibleAdapter(timeout_seconds=1, transport=httpx.MockTransport(handle))
    assert "test-model" in await adapter.list_models(profile)
    assert observed[0].url.host == "127.0.0.1"
    assert observed[0].headers["host"] == "localhost:8765"
    if scheme == "https":
        assert observed[0].extensions["sni_hostname"] == "localhost"


def test_model_token_setting_does_not_exceed_runtime_limit() -> None:
    with pytest.raises(ValidationError):
        ModelParams(max_tokens=EndpointPolicy().max_tokens + 1)


def test_fallback_loading_bounds_missing_and_duplicate_profile_lookups() -> None:
    connection = _Connection(
        {"p1": _profile()},
        _route(*(f"missing-{index}" for index in range(100))),
    )
    runtime = RegistryRuntime(
        _Pool(connection),
        OperatingMode.LOCAL,
        attempt_limit=2,
        policy=EndpointPolicy(timeout_seconds=5),
    )

    # The primary plus at most fifteen fallback entries are examined.
    candidates = asyncio.run(runtime._load_candidates())

    assert [item.profile_id for item in candidates] == ["p1"]
    assert connection.profile_fetches == 16


class _SlowBody(httpx.AsyncByteStream):
    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b'{"choices":[{"message":{"content":"'
        await asyncio.sleep(0.1)
        yield b'{"evidence_ids":[]}"}}]}'

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_http_timeout_covers_trickling_response_body() -> None:
    profile = ModelProfile(
        "local",
        "openai_compatible",
        "http://127.0.0.1:11434/v1",
        "m",
        frozenset({"answer"}),
        PrivacyZone.INTERNAL,
        "r1",
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, stream=_SlowBody(), request=request)
    )
    adapter = OpenAICompatibleAdapter(timeout_seconds=0.02, transport=transport)

    with pytest.raises(AdapterError, match="MODEL_REQUEST_FAILED"):
        await adapter.generate([{"role": "user", "content": "select"}], profile)


def test_selection_contract_is_strict_and_allows_abstention() -> None:
    assert json.loads(_canonical_selection('{"evidence_ids": []}') or "{}") == {
        "evidence_ids": []
    }
    assert _canonical_selection('{"evidence_ids":["ev_1"],"answer":"ignore"}') is None
    assert _canonical_selection('{"evidence_ids":["ev_1","ev_2","ev_3","ev_4"]}') is None
    assert _canonical_selection('{"evidence_ids":["ev_1","ev_1"]}') is None
    assert _canonical_selection('{"evidence_ids":["bad id"]}') is None


@pytest.mark.asyncio
async def test_runtime_generates_canonical_selection_and_bounds_request() -> None:
    principal_id = uuid4()
    connection = _Connection({"p1": _profile()}, _route())
    transport, requests = _transport(
        lambda request, _: httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": '{"evidence_ids":["ev_1","ev_2"]}'}}
                ]
            },
            request=request,
        )
    )
    runtime = RegistryRuntime(
        _Pool(connection),
        OperatingMode.LOCAL,
        attempt_limit=2,
        policy=EndpointPolicy(
            allowed_remote_domains=frozenset(),
            allowed_lan_endpoints=frozenset(),
            remote_processing_allowed=False,
            timeout_seconds=5,
        ),
        transport=transport,
    )

    result = await runtime.generate_selection(
        [{"role": "user", "content": "select evidence"}],
        principal_id=principal_id,
        document_ids=[uuid4()],
    )

    assert json.loads(result.content or "{}") == {"evidence_ids": ["ev_1", "ev_2"]}
    assert len(requests) == 1
    assert requests[0].url.path.endswith("/chat/completions")
    assert json.loads(requests[0].content)["model"] == "configured-model"


@pytest.mark.asyncio
async def test_api_generation_fails_closed_without_user_or_document_permission() -> None:
    connection = _Connection(
        {
            "p1": _profile(
                endpoint="https://api.example.test/v1",
                zone=PrivacyZone.PUBLIC,
                secret_ref="env:AI_KEY",
            )
        },
        _route(),
        remote_ai_allowed=False,
        evidence_allowed=True,
    )
    transport, requests = _transport(
        lambda request, _: httpx.Response(200, json={}, request=request)
    )
    runtime = RegistryRuntime(
        _Pool(connection),
        OperatingMode.API,
        attempt_limit=2,
        policy=EndpointPolicy(
            allowed_remote_domains=frozenset({"api.example.test"}),
            allowed_lan_endpoints=frozenset(),
            remote_processing_allowed=True,
            timeout_seconds=5,
        ),
        transport=transport,
    )

    result = await runtime.generate_selection(
        [{"role": "user", "content": "select"}],
        principal_id=uuid4(),
        document_ids=[uuid4()],
    )

    assert result.content is None
    assert requests == []


@pytest.mark.asyncio
async def test_api_generation_fails_closed_when_document_scope_is_not_remote_safe() -> None:
    connection = _Connection(
        {
            "p1": _profile(
                endpoint="https://api.example.test/v1",
                zone=PrivacyZone.PUBLIC,
                secret_ref="env:AI_KEY",
            )
        },
        _route(),
        remote_ai_allowed=True,
        evidence_allowed=False,
    )
    transport, requests = _transport(
        lambda request, _: httpx.Response(200, json={}, request=request)
    )
    runtime = RegistryRuntime(
        _Pool(connection),
        OperatingMode.API,
        attempt_limit=2,
        policy=EndpointPolicy(
            allowed_remote_domains=frozenset({"api.example.test"}),
            allowed_lan_endpoints=frozenset(),
            remote_processing_allowed=True,
            timeout_seconds=5,
        ),
        transport=transport,
    )

    result = await runtime.generate_selection(
        [{"role": "user", "content": "select"}],
        principal_id=uuid4(),
        document_ids=[uuid4()],
    )

    assert result.content is None
    assert requests == []


@pytest.mark.asyncio
async def test_runtime_requires_provider_approval_and_ready_health() -> None:
    connection = _Connection(
        {"p1": _profile(approved=False, health="unknown")},
        _route(),
    )
    transport, requests = _transport(
        lambda request, _: httpx.Response(200, json={}, request=request)
    )
    runtime = RegistryRuntime(
        _Pool(connection),
        OperatingMode.LOCAL,
        attempt_limit=2,
        policy=EndpointPolicy(timeout_seconds=5),
        transport=transport,
    )

    result = await runtime.generate_selection(
        [{"role": "user", "content": "select"}],
        principal_id=uuid4(),
        document_ids=[uuid4()],
    )

    assert result.content is None
    assert requests == []


@pytest.mark.asyncio
async def test_runtime_uses_one_fallback_and_never_exceeds_two_sends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_KEY", "test-secret")
    connection = _Connection(
        {
            "p1": _profile(endpoint="http://127.0.0.1:11434/v1", secret_ref=None),
            "p2": {
                **_profile("p2", endpoint="http://127.0.0.1:11434/v1", secret_ref=None),
                "fallback": ["p1", "missing"],
            },
        },
        _route("p2", "p1", "missing"),
    )
    transport, requests = _transport(
        lambda request, index: httpx.Response(
            503 if index == 0 else 200,
            json={
                "choices": [
                    {"message": {"content": '{"evidence_ids":["ev_3"]}'}}
                ]
            },
            request=request,
        )
    )
    runtime = RegistryRuntime(
        _Pool(connection),
        OperatingMode.LOCAL,
        attempt_limit=2,
        policy=EndpointPolicy(
            allowed_remote_domains=frozenset(),
            allowed_lan_endpoints=frozenset(),
            remote_processing_allowed=False,
            timeout_seconds=5,
        ),
        transport=transport,
    )

    result = await runtime.generate_selection(
        [{"role": "user", "content": "select"}],
        principal_id=uuid4(),
        document_ids=[uuid4()],
    )

    assert json.loads(result.content or "{}") == {"evidence_ids": ["ev_3"]}
    assert len(requests) == 2


@pytest.mark.asyncio
async def test_probe_ready_requires_exact_model_advertisement_and_updates_health() -> None:
    connection = _Connection({"p1": _profile()}, _route())
    transport, requests = _transport(
        lambda request, _: httpx.Response(
            200,
            json={"data": [{"id": "configured-model"}, {"id": "other"}]},
            request=request,
        )
    )
    runtime = RegistryRuntime(
        _Pool(connection),
        OperatingMode.LOCAL,
        attempt_limit=2,
        policy=EndpointPolicy(
            allowed_remote_domains=frozenset(),
            allowed_lan_endpoints=frozenset(),
            remote_processing_allowed=False,
            timeout_seconds=5,
        ),
        transport=transport,
    )

    result = await runtime.probe("p1")

    assert result["health"] == "ready"
    assert result["model_id"] == "configured-model"
    assert len(requests) == 1
    assert connection.health_updates[-1] == ("p1", "ready")


@pytest.mark.asyncio
async def test_probe_does_not_mark_new_config_ready_after_concurrent_edit() -> None:
    connection = _Connection(
        {"p1": _profile()},
        _route(),
        config_changed_on_update=True,
    )
    transport, _ = _transport(
        lambda request, _: httpx.Response(
            200,
            json={"data": [{"id": "configured-model"}]},
            request=request,
        )
    )
    runtime = RegistryRuntime(
        _Pool(connection),
        OperatingMode.LOCAL,
        attempt_limit=2,
        policy=EndpointPolicy(timeout_seconds=5),
        transport=transport,
    )

    result = await runtime.probe("p1")

    assert result == {
        "profile_id": "p1",
        "model_id": "configured-model",
        "status": "config_changed",
        "health": "unknown",
    }
    assert connection.health_updates == []

