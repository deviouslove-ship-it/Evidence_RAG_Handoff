"""Tests for B2: OCR stage policy bounds, local-only vision runtime, and single attempt."""

from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from app.model_registry.adapters.ollama_local import OllamaLocalAdapter, synthetic_ocr_probe_png
from app.model_registry.profiles import ModelProfile, OperatingMode, PrivacyZone
from app.model_registry.runtime import (
    EndpointPolicy,
    PolicyError,
    ProfileValidationError,
    RegistryRuntime,
    validate_profile,
)
from app.model_registry.stages import GENERATION_STAGES, StagePolicy
from app.schemas import StagePolicyRequest


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
        policy: dict[str, Any] | None = None,
    ) -> None:
        self.profiles = profiles
        self.route = route
        self.policy = policy
        self.usage: list[tuple[Any, ...]] = []

    def transaction(self) -> _Transaction:
        return _Transaction()

    async def execute(self, query: str, *args: Any) -> str:
        if "INSERT INTO ai_usage_events" in query:
            self.usage.append(args)
        return "OK"

    async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None:
        lowered = query.lower()
        if "from stage_policies" in lowered:
            return self.policy
        if "from stage_routes" in lowered:
            return self.route
        if "from model_profiles" in lowered:
            return self.profiles.get(str(args[0]))
        return None

    async def fetchval(self, query: str, *args: Any) -> Any:
        return None


class _Pool:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[_Connection]:
        yield self.connection


async def test_ollama_manifest_digest_comes_from_native_tags() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": ["vision"]})
        assert request.url.path == "/api/tags"
        return httpx.Response(
            200,
            json={
                "models": [
                    {"name": "qwen3.5:4b", "digest": "e0" * 32},
                ]
            },
        )

    adapter = OllamaLocalAdapter(
        timeout_seconds=5,
        max_response_bytes=100000,
        max_tokens=100,
        transport=httpx.MockTransport(handle),
    )
    profile = ModelProfile(
        "ocr",
        "ollama_local",
        "http://127.0.0.1:11434/v1",
        "qwen3.5:4b",
        frozenset({"ocr"}),
        PrivacyZone.INTERNAL,
        "r1",
    )
    await adapter.show_model(profile)
    assert adapter.last_model_digest == "sha256:" + "e0" * 32


def test_ocr_timeout_does_not_relax_chat_limit() -> None:
    assert "ocr" not in GENERATION_STAGES
    ocr_ok = StagePolicy(max_attempts=1, timeout_seconds=180, stage="ocr")
    assert ocr_ok.timeout_seconds == 180
    req_ok = StagePolicyRequest(
        mode="LOCAL", stage="ocr", max_attempts=1, timeout_seconds=180, max_output_tokens=8192
    )
    assert req_ok.timeout_seconds == 180

    with pytest.raises(ValueError, match="300"):
        StagePolicy(max_attempts=1, timeout_seconds=301, stage="ocr")
    with pytest.raises(ValidationError):
        StagePolicyRequest(mode="LOCAL", stage="ocr", max_attempts=1, timeout_seconds=301)

    with pytest.raises(ValueError, match="30"):
        StagePolicy(max_attempts=2, timeout_seconds=31, stage="summarize")
    with pytest.raises(ValidationError):
        StagePolicyRequest(mode="LOCAL", stage="summarize", max_attempts=2, timeout_seconds=31)

    with pytest.raises(ValueError, match="only 1 attempt"):
        StagePolicy(max_attempts=2, timeout_seconds=180, stage="ocr")


def test_ocr_profile_requires_local_ollama_loopback() -> None:
    policy = EndpointPolicy(
        allowed_remote_domains=frozenset({"api.example.test"}),
        allowed_lan_endpoints=frozenset({"http://10.0.0.5:11434/v1"}),
        remote_processing_allowed=True,
    )
    valid = ModelProfile(
        "ocr-local",
        "ollama_local",
        "http://127.0.0.1:11434/v1",
        "qwen3.5:4b",
        frozenset({"ocr"}),
        PrivacyZone.INTERNAL,
        "r1",
    )
    validate_profile(valid, OperatingMode.API, policy, "ocr")

    wrong_adapter = ModelProfile(
        "ocr-vllm",
        "vllm_local",
        "http://127.0.0.1:8000/v1",
        "m",
        frozenset({"ocr"}),
        PrivacyZone.INTERNAL,
        "r1",
    )
    with pytest.raises(ProfileValidationError, match="ADAPTER_UNSUPPORTED"):
        validate_profile(wrong_adapter, OperatingMode.LOCAL, policy, "ocr")

    lan_ocr = ModelProfile(
        "ocr-lan",
        "ollama_local",
        "http://10.0.0.5:11434/v1",
        "m",
        frozenset({"ocr"}),
        PrivacyZone.INTERNAL,
        "r1",
    )
    with pytest.raises(PolicyError, match="AI_LOCAL_ENDPOINT_DENIED"):
        validate_profile(lan_ocr, OperatingMode.LOCAL, policy, "ocr")

    public_ocr = ModelProfile(
        "ocr-api",
        "ollama_local",
        "https://api.example.test/v1",
        "m",
        frozenset({"ocr"}),
        PrivacyZone.PUBLIC,
        "r1",
    )
    with pytest.raises(PolicyError, match="AI_LOCAL_ENDPOINT_DENIED"):
        validate_profile(public_ocr, OperatingMode.API, policy, "ocr")


@pytest.mark.asyncio
async def test_vision_payload_is_local_and_bounded() -> None:
    png_bytes = synthetic_ocr_probe_png("Trang 17")
    expected_b64 = base64.b64encode(png_bytes).decode("ascii")
    requests: list[httpx.Request] = []
    chat_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal chat_calls
        requests.append(request)
        if request.url.path == "/api/show":
            return httpx.Response(
                200,
                json={"capabilities": ["completion", "vision"], "digest": "sha256:testdigest"},
                request=request,
            )
        if request.url.path == "/api/chat":
            chat_calls += 1
            if chat_calls == 1:
                return httpx.Response(
                    200,
                    json={
                        "done": True,
                        "done_reason": "stop",
                        "prompt_eval_count": 500,
                        "eval_count": 30,
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "blocks": [{"kind": "text", "text": "Trang 17"}],
                                    "warnings": [],
                                    "unreadable": [],
                                }
                            ),
                        },
                    },
                    request=request,
                )
        return httpx.Response(500, request=request)

    conn = _Connection(
        {
            "local-ocr": {
                "profile_key": "local-ocr",
                "adapter": "ollama_local",
                "endpoint": "http://localhost:11434/v1",
                "model_id": "qwen3.5:4b",
                "capabilities": ["ocr"],
                "privacy_zone": "internal",
                "revision": "r1",
                "secret_ref": None,
                "fallback": ["cloud-ocr"],
                "params": {"ollama_native": True, "think": False, "num_ctx": 8192},
                "provider_approved": True,
                "health": "ready",
            },
            "cloud-ocr": {
                "profile_key": "cloud-ocr",
                "adapter": "openai_compatible",
                "endpoint": "https://api.example.test/v1",
                "model_id": "gpt-vision",
                "capabilities": ["ocr"],
                "privacy_zone": "public",
                "revision": "r1",
                "secret_ref": None,
                "fallback": [],
                "params": {},
                "provider_approved": True,
                "health": "ready",
            },
        },
        {"profile_key": "local-ocr", "fallback": [], "escalation_key": "cloud-ocr"},
        policy={"max_attempts": 1, "timeout_seconds": 180, "max_output_tokens": 8192},
    )
    runtime = RegistryRuntime(
        _Pool(conn),
        OperatingMode.API,  # Even in API mode, OCR never escalates outside loopback!
        attempt_limit=2,
        policy=EndpointPolicy(
            allowed_remote_domains=frozenset({"api.example.test"}),
            remote_processing_allowed=True,
            timeout_seconds=5,
        ),
        transport=httpx.MockTransport(handler),
    )

    outcome = await runtime.generate_vision(
        image_png=png_bytes,
        prompt="Chép lại nội dung.",
        schema={"type": "object"},
        principal_id=uuid4(),
        document_id=uuid4(),
    )
    assert outcome.error_code is None
    assert outcome.attempts_used == 1
    assert outcome.model_digest == "sha256:testdigest"
    assert len(requests) == 3
    assert all(r.url.host == "127.0.0.1" for r in requests)
    chat_body = json.loads(requests[1].content)
    assert chat_body["messages"][0]["images"] == [expected_b64]
    assert chat_body["think"] is False
    assert chat_body["options"]["num_predict"] == 8192

    # A profile edited while Ollama is reading the image invalidates its old output.
    chat_calls = 0

    def changing_profile(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/chat":
            conn.profiles["local-ocr"]["revision"] = "r2"
        return handler(request)

    changed = RegistryRuntime(
        _Pool(conn),
        OperatingMode.LOCAL,
        attempt_limit=1,
        policy=EndpointPolicy(timeout_seconds=5),
        transport=httpx.MockTransport(changing_profile),
    )
    changed_outcome = await changed.generate_vision(
        image_png=png_bytes,
        prompt="Chép lại nội dung.",
        schema={"type": "object"},
        principal_id=uuid4(),
        document_id=uuid4(),
    )
    assert changed_outcome.content is None
    assert changed_outcome.error_code == "OCR_AI_MODEL_CHANGED"
    conn.profiles["local-ocr"]["revision"] = "r1"

    # Second call returning redirect (302) must fail closed without following redirect
    def redirect_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/show":
            return httpx.Response(
                200,
                json={"capabilities": ["vision"], "digest": "sha256:testdigest"},
                request=request,
            )
        return httpx.Response(302, headers={"Location": "https://evil.example/"}, request=request)

    runtime_redir = RegistryRuntime(
        _Pool(conn),
        OperatingMode.LOCAL,
        attempt_limit=1,
        policy=EndpointPolicy(timeout_seconds=5),
        transport=httpx.MockTransport(redirect_handler),
    )
    redir_outcome = await runtime_redir.generate_vision(
        image_png=png_bytes,
        prompt="Chép lại nội dung.",
        schema={"type": "object"},
        principal_id=uuid4(),
        document_id=uuid4(),
    )
    assert redir_outcome.content is None
    assert redir_outcome.error_code == "MODEL_REQUEST_FAILED"
    assert redir_outcome.attempts_used == 1


async def test_portable_missing_projector_keeps_text_search_available() -> None:
    """Missing vision projector on OCR fails OCR cleanly while text & embedding keep working."""

    class _MultiStageConn(_Connection):
        def __init__(self, profiles: dict[str, dict[str, Any]], routes: dict[str, dict[str, Any]]):
            super().__init__(profiles, {})
            self.routes = routes

        async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None:
            lowered = query.lower()
            if "remote_ai_allowed" in lowered:
                return {"remote_ai_allowed": False, "disabled_at": None}
            if "from stage_routes" in lowered and args:
                return self.routes.get(str(args[-1]))
            return await super().fetchrow(query, *args)

        async def fetchval(self, query: str, *args: Any) -> Any:
            if "registry evidence gate" in query:
                return True
            return await super().fetchval(query, *args)

    profiles = {
        "local-qwen35-ocr": {
            "profile_key": "local-qwen35-ocr",
            "adapter": "ollama_local",
            "endpoint": "http://127.0.0.1:11434/v1",
            "model_id": "qwen3.5:4b",
            "capabilities": ["ocr"],
            "privacy_zone": "internal",
            "revision": "1",
            "provider_approved": True,
            "health": "ready",
            "params": {"ollama_native": True, "think": False, "num_ctx": 8192},
        },
        "local-qwen35-text": {
            "profile_key": "local-qwen35-text",
            "adapter": "ollama_local",
            "endpoint": "http://127.0.0.1:11434/v1",
            "model_id": "qwen3.5:4b",
            "capabilities": ["answer"],
            "privacy_zone": "internal",
            "revision": "1",
            "provider_approved": True,
            "health": "ready",
            "params": {"ollama_native": True, "think": False, "num_ctx": 8192},
        },
        "local-embed": {
            "profile_key": "local-embed",
            "adapter": "ollama_local",
            "endpoint": "http://127.0.0.1:11434/v1",
            "model_id": "qwen3-embedding:0.6b",
            "capabilities": ["embedding"],
            "privacy_zone": "internal",
            "revision": "1",
            "provider_approved": True,
            "health": "ready",
            "params": {},
        },
    }
    routes = {
        "ocr": {"profile_key": "local-qwen35-ocr", "fallback": []},
        "answer": {"profile_key": "local-qwen35-text", "fallback": []},
        "embedding": {"profile_key": "local-embed", "fallback": []},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": ["completion"]}, request=request)
        if request.url.path == "/api/chat":
            return httpx.Response(
                200,
                json={
                    "done": True,
                    "done_reason": "stop",
                    "message": {"role": "assistant", "content": "Văn bản tìm kiếm vẫn hoạt động."},
                },
                request=request,
            )
        if request.url.path == "/v1/embeddings":
            return httpx.Response(
                200,
                json={"data": [{"index": 0, "embedding": [0.1, 0.2, 0.3]}]},
                request=request,
            )
        return httpx.Response(404, request=request)

    runtime = RegistryRuntime(
        _Pool(_MultiStageConn(profiles, routes)),
        OperatingMode.LOCAL,
        attempt_limit=1,
        policy=EndpointPolicy(timeout_seconds=10),
        transport=httpx.MockTransport(handler),
    )

    ocr_out = await runtime.generate_vision(
        image_png=synthetic_ocr_probe_png(),
        prompt="Chép lại nội dung.",
        schema={"type": "object"},
        principal_id=uuid4(),
        document_id=uuid4(),
    )
    assert ocr_out.content is None
    assert ocr_out.error_code is not None

    ans_out = await runtime.generate(
        "answer",
        [{"role": "user", "content": "Hỏi đáp"}],
        principal_id=uuid4(),
        document_ids=[uuid4()],
        parse=lambda text: text,
    )
    assert ans_out.content == "Văn bản tìm kiếm vẫn hoạt động."

    emb_out = await runtime.embed(["truy vấn tìm kiếm"], principal_id=uuid4())
    assert emb_out.vectors == [[0.1, 0.2, 0.3]]
