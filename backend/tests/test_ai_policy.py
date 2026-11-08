"""G1.0: stage policy, Hybrid Auto escalation, Local Only, cost caps, usage log."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import date
from typing import Any
from uuid import uuid4

import httpx
import pytest

from app.model_registry.profiles import OperatingMode, PrivacyZone
from app.model_registry.runtime import EndpointPolicy, RegistryRuntime
from app.schemas import EvidenceRef
from app.workflow.ai_selection import ConfiguredSelection

_PUBLIC_HOST = "api.example.test"


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
        policy: dict[str, Any] | None = None,
        remote_ai_allowed: bool = True,
        evidence_allowed: bool = True,
        spent: float = 0.0,
    ) -> None:
        self.profiles = profiles
        self.route = route
        self.policy = policy
        self.remote_ai_allowed = remote_ai_allowed
        self.evidence_allowed = evidence_allowed
        self.spent = spent
        self.usage: list[tuple[Any, ...]] = []

    def transaction(self) -> _Transaction:
        return _Transaction()

    async def execute(self, query: str, *args: Any) -> str:
        if "INSERT INTO ai_usage_events" in query:
            self.usage.append(args)
        return "OK"

    async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None:
        lowered = query.lower()
        if "remote_ai_allowed" in lowered:
            return {"remote_ai_allowed": self.remote_ai_allowed, "disabled_at": None}
        if "ai usage cost" in lowered:
            return {"day_cost": self.spent, "month_cost": self.spent}
        if "from stage_policies" in lowered:
            return self.policy
        if "from stage_routes" in lowered:
            return self.route
        if "from model_profiles" in lowered:
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
    key: str, *, public: bool = False, health: str = "ready", **extra: Any
) -> dict[str, Any]:
    return {
        "profile_key": key,
        "adapter": "openai_compatible",
        "endpoint": f"https://{_PUBLIC_HOST}/v1" if public else "http://127.0.0.1:11434/v1",
        "model_id": f"{key}-model",
        "capabilities": ["answer"],
        "privacy_zone": (PrivacyZone.PUBLIC if public else PrivacyZone.INTERNAL).value,
        "revision": "r1",
        "secret_ref": None,
        "fallback": [],
        "params": {},
        "provider_approved": True,
        "health": health,
        **extra,
    }


def _registry(**connection_args: Any) -> _Connection:
    return _Connection(
        {"local": _profile("local"), "cloud": _profile("cloud", public=True)},
        {"profile_key": "local", "fallback": [], "escalation_key": "cloud"},
        **connection_args,
    )


def _reply(content: str, *, usage: bool = False) -> dict[str, Any]:
    body: dict[str, Any] = {"choices": [{"message": {"content": content}}]}
    if usage:
        body["usage"] = {"prompt_tokens": 1000, "completion_tokens": 100}
    return body


def _transport(
    answer: Callable[[httpx.Request], dict[str, Any]],
) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    sent: list[httpx.Request] = []

    def dispatch(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json=answer(request), request=request)

    return httpx.MockTransport(dispatch), sent


def _runtime(
    connection: _Connection, mode: OperatingMode, transport: httpx.MockTransport
) -> RegistryRuntime:
    return RegistryRuntime(
        _Pool(connection),
        mode,
        attempt_limit=2,
        policy=EndpointPolicy(
            allowed_remote_domains=frozenset({_PUBLIC_HOST}),
            remote_processing_allowed=True,
            timeout_seconds=5,
        ),
        transport=transport,
    )


def _local_bad_cloud_good(request: httpx.Request) -> dict[str, Any]:
    if request.url.host == _PUBLIC_HOST:
        return _reply('{"evidence_ids":["ev_1"]}')
    return _reply('{"evidence_ids":["not-offered"]}')


def _accept_ev1(raw: str) -> bool:
    return json.loads(raw)["evidence_ids"] == ["ev_1"]


async def _select(runtime: RegistryRuntime, **kwargs: Any) -> Any:
    return await runtime.generate_selection(
        [{"role": "user", "content": "chọn căn cứ"}],
        principal_id=uuid4(),
        document_ids=[uuid4()],
        accept=_accept_ev1,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_local_only_never_sends_to_the_api_even_with_an_escalation_route() -> None:
    connection = _registry()
    transport, sent = _transport(_local_bad_cloud_good)

    outcome = await _select(_runtime(connection, OperatingMode.LOCAL, transport))
    deep = await _select(
        _runtime(connection, OperatingMode.LOCAL, transport), deep_analysis=True
    )

    assert outcome.content is None and deep.content is None
    assert not outcome.external_api_used and not deep.external_api_used
    assert sent and all(request.url.host == "127.0.0.1" for request in sent)


@pytest.mark.asyncio
async def test_hybrid_auto_escalates_once_when_the_local_result_fails_the_check() -> None:
    connection = _registry()
    transport, sent = _transport(_local_bad_cloud_good)

    outcome = await _select(_runtime(connection, OperatingMode.API, transport))

    assert json.loads(outcome.content or "{}") == {"evidence_ids": ["ev_1"]}
    assert outcome.external_api_used and outcome.escalated
    assert [request.url.host for request in sent] == ["127.0.0.1", _PUBLIC_HOST]
    assert [(row[4], row[5]) for row in connection.usage] == [
        ("rejected", False), ("ok", True),
    ]


@pytest.mark.asyncio
async def test_hybrid_auto_keeps_a_good_local_result_without_calling_the_api() -> None:
    connection = _registry()
    transport, sent = _transport(lambda _request: _reply('{"evidence_ids":["ev_1"]}'))

    outcome = await _select(_runtime(connection, OperatingMode.API, transport))

    assert outcome.content is not None and not outcome.external_api_used
    assert [request.url.host for request in sent] == ["127.0.0.1"]


@pytest.mark.asyncio
async def test_deep_analysis_goes_to_the_escalation_profile_first() -> None:
    connection = _registry()
    transport, sent = _transport(_local_bad_cloud_good)

    outcome = await _select(
        _runtime(connection, OperatingMode.API, transport), deep_analysis=True
    )

    assert outcome.external_api_used and outcome.escalated
    assert [request.url.host for request in sent] == [_PUBLIC_HOST]


@pytest.mark.parametrize(
    "gate", [{"remote_ai_allowed": False}, {"evidence_allowed": False}]
)
@pytest.mark.asyncio
async def test_escalation_respects_user_and_category_permissions(gate: dict[str, bool]) -> None:
    connection = _registry(**gate)
    transport, sent = _transport(_local_bad_cloud_good)

    outcome = await _select(
        _runtime(connection, OperatingMode.API, transport), deep_analysis=True
    )

    # The API is refused, the local model still runs; nothing leaves the network.
    assert outcome.content is None and not outcome.external_api_used
    assert [request.url.host for request in sent] == ["127.0.0.1"]


@pytest.mark.asyncio
async def test_no_escalation_when_no_local_model_could_run() -> None:
    connection = _registry()
    connection.profiles["local"] = _profile("local", health="unhealthy")
    transport, sent = _transport(_local_bad_cloud_good)

    outcome = await _select(_runtime(connection, OperatingMode.API, transport))

    assert outcome.content is None and sent == []


@pytest.mark.asyncio
async def test_cost_cap_skips_the_profile_and_reports_the_limit() -> None:
    connection = _registry(spent=5.0)
    connection.profiles["cloud"] = _profile(
        "cloud", public=True, input_price_per_mtok=1, output_price_per_mtok=4,
        daily_cost_limit=5,
    )
    transport, sent = _transport(_local_bad_cloud_good)

    outcome = await _select(
        _runtime(connection, OperatingMode.API, transport), deep_analysis=True
    )

    assert outcome.limited and not outcome.external_api_used
    assert all(request.url.host == "127.0.0.1" for request in sent)


@pytest.mark.asyncio
async def test_usage_event_records_tokens_and_estimated_cost_without_content() -> None:
    connection = _registry()
    connection.profiles["local"] = _profile(
        "local", input_price_per_mtok=2, output_price_per_mtok=10
    )
    transport, _ = _transport(
        lambda _request: _reply('{"evidence_ids":["ev_1"]}', usage=True)
    )

    await _select(_runtime(connection, OperatingMode.LOCAL, transport))

    (row,) = connection.usage
    mode, stage, profile_key, _principal, outcome, escalated, tokens_in, tokens_out = row[:8]
    assert (mode, stage, profile_key, outcome, escalated) == (
        "LOCAL", "answer", "local", "ok", False,
    )
    assert (tokens_in, tokens_out) == (1000, 100)
    assert row[9] == pytest.approx((1000 * 2 + 100 * 10) / 1_000_000)
    assert "chọn căn cứ" not in repr(row)


@pytest.mark.asyncio
async def test_stage_policy_replaces_the_fixed_two_attempts() -> None:
    connection = _Connection(
        {
            "a": {**_profile("a"), "fallback": ["b"]},
            "b": {**_profile("b"), "fallback": ["c"]},
            "c": _profile("c"),
        },
        {"profile_key": "a", "fallback": []},
        policy={"max_attempts": 3, "max_output_tokens": 64, "timeout_seconds": 4,
                "max_concurrency": 2},
    )
    transport, sent = _transport(lambda _request: _reply("not json"))

    await _select(_runtime(connection, OperatingMode.LOCAL, transport))
    assert len(sent) == 3
    assert json.loads(sent[0].content)["max_tokens"] == 64

    connection.policy = {"max_attempts": 1}
    sent.clear()
    await _select(_runtime(connection, OperatingMode.LOCAL, transport))
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_no_evidence_means_no_model_call() -> None:
    connection = _registry()
    transport, sent = _transport(_local_bad_cloud_good)
    selection = ConfiguredSelection(_runtime(connection, OperatingMode.API, transport))

    result = await selection("câu hỏi", [], principal_id=uuid4(), deep_analysis=True)

    assert result.evidence_ids is None and not result.external_api_used
    assert sent == [] and connection.usage == []


@pytest.mark.asyncio
async def test_selection_reports_external_api_use_to_the_pipeline() -> None:
    connection = _registry()
    evidence = EvidenceRef(
        evidence_id="ev_1", document_id=uuid4(), document_version_id=uuid4(), node_id=uuid4(),
        title="Thông tư", label="Điều 1", quote_exact="Nội dung.", source_hash="0" * 64,
        as_of_date=date(2026, 11, 7), viewer_url="/viewer",
    )
    transport, _ = _transport(_local_bad_cloud_good)
    selection = ConfiguredSelection(_runtime(connection, OperatingMode.API, transport))

    result = await selection("câu hỏi", [evidence], principal_id=uuid4())

    assert result.evidence_ids == ["ev_1"] and result.external_api_used
