"""Typed API keys (secret store) and the connection / usability check of a model profile.

HTTP to the model is a mock transport; nothing leaves the machine.  Keys are invented.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.model_registry.diagnostics import PROMPT, diagnose_profile
from app.model_registry.profiles import ModelProfile, PrivacyZone
from app.model_registry.runtime import (
    EndpointPolicy,
    RegistryRuntime,
    SecretError,
    model_advertised,
    secret_ref_valid,
)
from app.model_registry.secret_store import SecretStore, SecretStoreError, secret_name

KEY = "sk-invented-key-1234567890"


def _fake_store(root: Path) -> SecretStore:
    # Reversible stand-in for DPAPI so the tests run on any platform.
    return SecretStore(root, (lambda data: data[::-1], lambda data: data[::-1]))


# ------------------------------------------------------------------ secret store
def test_store_round_trip_overwrite_and_missing(tmp_path: Path) -> None:
    store = _fake_store(tmp_path)
    assert store.available and store.get("p1") is None and not store.has("p1")
    store.put("p1", f"  {KEY}\n")
    assert store.get("p1") == KEY and store.has("p1")
    store.put("p1", "second")
    assert store.get("p1") == "second"
    store.delete("p1")
    assert store.get("p1") is None
    assert not list(tmp_path.glob(".tmp-*")), "no temporary file is left behind"


def test_store_rejects_bad_names_and_values(tmp_path: Path) -> None:
    store = _fake_store(tmp_path)
    for name in ("../x", "a/b", ".hidden", "", "a b"):
        with pytest.raises(SecretStoreError, match="MODEL_SECRET_REF_INVALID"):
            store.put(name, KEY)
    for value in ("", "   ", "two\nlines", "x" * 5000):
        with pytest.raises(SecretStoreError, match="MODEL_SECRET_INVALID"):
            store.put("p1", value)
    assert list(tmp_path.iterdir()) == []


def test_store_is_unavailable_without_directory_or_protector(tmp_path: Path) -> None:
    assert not SecretStore(None).available
    with pytest.raises(SecretStoreError, match="SECRET_STORE_UNAVAILABLE"):
        SecretStore(None).put("p1", KEY)
    no_protector = SecretStore(tmp_path, None)
    if sys.platform != "win32":
        assert not no_protector.available
    unreadable = _fake_store(tmp_path)
    (tmp_path / "bad.key").write_bytes(b"not a protected file")
    with pytest.raises(SecretStoreError, match="MODEL_SECRET_UNAVAILABLE"):
        unreadable.get("bad")


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI exists on Windows only")
def test_windows_store_never_writes_the_key_in_clear(tmp_path: Path) -> None:
    store = SecretStore(tmp_path)
    assert store.available
    store.put("real", KEY)
    raw = (tmp_path / "real.key").read_bytes()
    assert KEY.encode() not in raw and b"invented" not in raw
    assert store.get("real") == KEY
    # Another store instance (a new server process of the same account) reads it.
    assert SecretStore(tmp_path).get("real") == KEY


def test_secret_reference_syntax() -> None:
    assert secret_name("secret:local-answer-1a2b3c4d") == "local-answer-1a2b3c4d"
    assert secret_name("env:KEY") is None and secret_name("secret:../x") is None
    assert secret_ref_valid("env:GEMINI_API_KEY") and secret_ref_valid("secret:a.b-c_d")
    assert not secret_ref_valid("sk-raw-key") and not secret_ref_valid("secret:")
    assert not secret_ref_valid("env:DATABASE_URL")  # application variables stay denied


def test_runtime_resolves_stored_keys_and_fails_closed(tmp_path: Path) -> None:
    store = _fake_store(tmp_path)
    store.put("p1", KEY)
    runtime = RegistryRuntime(object(), mode="API", attempt_limit=1, policy=EndpointPolicy(),
                              secrets=store)
    profile = _profile(secret_ref="secret:p1")
    assert runtime._resolve_secret(profile) == KEY
    with pytest.raises(SecretError, match="MODEL_SECRET_UNAVAILABLE"):
        runtime._resolve_secret(_profile(secret_ref="secret:absent"))
    with pytest.raises(SecretError, match="MODEL_SECRET_REF_INVALID"):
        runtime._resolve_secret(_profile(secret_ref="secret:../p1"))
    nowhere = RegistryRuntime(object(), mode="API", attempt_limit=1, policy=EndpointPolicy(),
                              secrets=SecretStore(None))
    with pytest.raises(SecretError, match="MODEL_SECRET_UNAVAILABLE"):
        nowhere._resolve_secret(profile)


# ------------------------------------------------------------------ diagnostics
def _profile(**changes: Any) -> ModelProfile:
    values: dict[str, Any] = dict(
        profile_id="p", adapter="openai_compatible", endpoint="https://api.example.test/v1",
        model_id="model-a", capabilities=frozenset({"answer", "summarize"}),
        privacy_zone=PrivacyZone.PUBLIC, revision="v1", secret_ref=None,
        params={"max_tokens": 256}, provider_approved=True)
    values.update(changes)
    return ModelProfile(**values)


class Server:
    """A model server that records what it was sent."""

    def __init__(self, *, models: list[str] | None = None, chat: Any = None,
                 embed: Any = None, key: str | None = KEY, list_status: int = 200) -> None:
        self.models = ["model-a"] if models is None else models
        self.chat = chat if chat is not None else {"choices": [{"message": {
            "content": '{"ok": true}'}}]}
        self.embed = embed
        self.key = key
        self.list_status = list_status
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.key is not None and request.headers.get("authorization") != f"Bearer {self.key}":
            return httpx.Response(401, json={"error": "bad key"}, request=request)
        if request.url.path.endswith("/models"):
            if self.list_status != 200:
                return httpx.Response(self.list_status, request=request)
            return httpx.Response(200, request=request, json={
                "data": [{"id": name} for name in self.models]})
        if request.url.path.endswith("/embeddings"):
            vector = {"data": [{"index": 0, "embedding": [0.1] * 8}]}
            return self._reply(self.embed, request, vector)
        return self._reply(self.chat, request, None)

    @staticmethod
    def _reply(value: Any, request: httpx.Request, default: Any) -> httpx.Response:
        value = default if value is None else value
        if isinstance(value, int):
            return httpx.Response(value, request=request)
        return httpx.Response(200, json=value, request=request)


def _runtime(server: Server, tmp_path: Path, *, mode: str = "API", remote: bool = True,
             domains: tuple[str, ...] = ("api.example.test",)) -> RegistryRuntime:
    return RegistryRuntime(
        object(), mode=mode, attempt_limit=1,
        policy=EndpointPolicy(allowed_remote_domains=frozenset(domains),
                              remote_processing_allowed=remote, timeout_seconds=5),
        transport=httpx.MockTransport(server.handler), secrets=_fake_store(tmp_path))


def _by_id(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in result["checks"]}


async def test_complete_pass_with_typed_key(tmp_path: Path) -> None:
    server = Server()
    result = await diagnose_profile(_runtime(server, tmp_path), _profile(), api_key=KEY)
    checks = _by_id(result)
    assert result["ok"] and result["usable"]
    assert [c["id"] for c in result["checks"]] == [
        "config", "secret", "connect", "model", "generate", "json"]
    assert all(c["status"] == "ok" for c in result["checks"])
    assert result["latency_ms"] is not None and checks["connect"]["ms"] is not None
    # The key goes only to the model server, never into the result.
    assert KEY not in json.dumps(result)
    assert all(r.headers["authorization"] == f"Bearer {KEY}" for r in server.requests)
    sent = json.loads(server.requests[-1].content)
    # The profile's own parameters, and only the fixed synthetic prompt (no document text).
    assert sent["max_tokens"] == 256 and sent["messages"] == PROMPT


async def test_stored_and_environment_keys_are_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime(Server(), tmp_path)
    runtime.secrets.put("p1", KEY)
    assert (await diagnose_profile(runtime, _profile(secret_ref="secret:p1")))["usable"]
    monkeypatch.setenv("INVENTED_AI_KEY", KEY)
    assert (await diagnose_profile(runtime, _profile(secret_ref="env:INVENTED_AI_KEY")))["usable"]
    missing = await diagnose_profile(runtime, _profile(secret_ref="env:ABSENT_AI_KEY"))
    assert not missing["ok"] and _by_id(missing)["secret"]["code"] == "MODEL_SECRET_UNAVAILABLE"
    assert "connect" not in _by_id(missing), "no request is made without the key"


@pytest.mark.parametrize(("server", "step", "code"), [
    (Server(key="another-key"), "connect", "AUTH_FAILED"),
    (Server(list_status=500), "connect", "REQUEST_REFUSED"),
    (Server(models=["other"]), "model", "MODEL_NOT_FOUND"),
    (Server(chat=400), "generate", "REQUEST_PARAMS_REJECTED"),
    (Server(chat=404), "generate", "CHAT_ENDPOINT_NOT_FOUND"),
    (Server(chat=429), "generate", "RATE_LIMITED"),
    (Server(chat={"unexpected": True}), "generate", "RESPONSE_INVALID"),
    (Server(chat={"choices": [{"message": {"content": "<think>hmm</think>"}}]}),
     "generate", "EMPTY_ANSWER"),
])
async def test_each_failure_has_its_own_code(
    server: Server, step: str, code: str, tmp_path: Path,
) -> None:
    result = await diagnose_profile(_runtime(server, tmp_path), _profile(), api_key=KEY)
    assert not result["ok"] and not result["usable"]
    assert _by_id(result)[step]["status"] == "fail" and _by_id(result)[step]["code"] == code
    assert result["checks"][-1]["id"] == step, "later steps are not run after a failure"


async def test_model_not_found_lists_what_the_server_has(tmp_path: Path) -> None:
    result = await diagnose_profile(_runtime(Server(models=["x-1", "x-2"]), tmp_path),
                                    _profile(), api_key=KEY)
    assert result["models"] == ["x-1", "x-2"]
    assert _by_id(result)["model"]["info"] == {"count": 2}


async def test_google_style_model_prefix_and_missing_models_endpoint(tmp_path: Path) -> None:
    assert model_advertised(frozenset({"models/gemini-x"}), "gemini-x")
    assert not model_advertised(frozenset({"gemini-y"}), "gemini-x")
    prefixed = await diagnose_profile(
        _runtime(Server(models=["models/model-a"]), tmp_path), _profile(), api_key=KEY)
    assert prefixed["usable"]
    # A service without GET /models can still chat: warned, not failed, not "verified".
    nolist = await diagnose_profile(_runtime(Server(list_status=404), tmp_path), _profile(),
                                    api_key=KEY)
    assert nolist["usable"]
    assert _by_id(nolist)["connect"] == {"id": "connect", "status": "warn",
                                         "code": "MODELS_LIST_UNSUPPORTED"}
    assert _by_id(nolist)["model"]["status"] == "skip"


async def test_json_that_is_not_json_is_a_warning(tmp_path: Path) -> None:
    server = Server(chat={"choices": [{"message": {"content": "Xin chào"}}]})
    result = await diagnose_profile(_runtime(server, tmp_path), _profile(), api_key=KEY)
    assert result["usable"] and _by_id(result)["json"] == {
        "id": "json", "status": "warn", "code": "JSON_NOT_RETURNED"}


async def test_egress_policy_is_checked_before_any_request(tmp_path: Path) -> None:
    server = Server()
    denied = await diagnose_profile(_runtime(server, tmp_path, domains=()), _profile(),
                                    api_key=KEY)
    assert not denied["ok"] and _by_id(denied)["config"]["code"] == "AI_EGRESS_DENIED"
    off = await diagnose_profile(_runtime(server, tmp_path, remote=False), _profile(),
                                 api_key=KEY)
    assert _by_id(off)["config"]["code"] == "AI_EGRESS_DENIED"
    lan = await diagnose_profile(
        _runtime(server, tmp_path), _profile(
            privacy_zone=PrivacyZone.INTERNAL, endpoint="http://192.168.1.20:8000/v1"))
    assert _by_id(lan)["config"]["code"] == "AI_LOCAL_ENDPOINT_DENIED"
    bad_adapter = await diagnose_profile(_runtime(server, tmp_path), _profile(adapter="soap"),
                                         api_key=KEY)
    assert _by_id(bad_adapter)["config"]["code"] == "ADAPTER_UNSUPPORTED"
    assert server.requests == [], "a refused configuration never reaches the network"


async def test_api_profile_while_server_runs_local_mode_is_warned(tmp_path: Path) -> None:
    result = await diagnose_profile(_runtime(Server(), tmp_path, mode="LOCAL"), _profile(),
                                    api_key=KEY)
    assert result["usable"] and _by_id(result)["mode"] == {
        "id": "mode", "status": "warn", "code": "API_MODE_INACTIVE"}


async def test_local_profile_needs_no_key_and_api_without_key_is_warned(tmp_path: Path) -> None:
    local = _profile(privacy_zone=PrivacyZone.INTERNAL, adapter="ollama_local",
                     endpoint="http://127.0.0.1:11434/v1")
    result = await diagnose_profile(_runtime(Server(key=None), tmp_path, mode="LOCAL"), local)
    assert result["usable"] and _by_id(result)["secret"]["status"] == "skip"
    keyless = await diagnose_profile(_runtime(Server(key=None), tmp_path), _profile())
    assert keyless["usable"] and _by_id(keyless)["secret"]["code"] == "NO_API_KEY"


async def test_embedding_profile_reports_dimensions_and_skips_chat(tmp_path: Path) -> None:
    server = Server(key=None)
    profile = _profile(capabilities=frozenset({"embedding"}), privacy_zone=PrivacyZone.INTERNAL,
                       adapter="ollama_local", endpoint="http://127.0.0.1:11434/v1", params={})
    result = await diagnose_profile(_runtime(server, tmp_path, mode="LOCAL"), profile)
    assert result["usable"] and result["dimensions"] == 8 and result["stage"] == "embedding"
    assert [c["id"] for c in result["checks"]][-1] == "embed"
    assert not any(r.url.path.endswith("/chat/completions") for r in server.requests)
    broken = await diagnose_profile(
        _runtime(Server(key=None, embed={"data": []}), tmp_path, mode="LOCAL"), profile)
    assert _by_id(broken)["embed"]["code"] == "RESPONSE_INVALID" and not broken["usable"]


async def test_unreachable_server_stops_at_connect(tmp_path: Path) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    runtime = RegistryRuntime(
        object(), mode="LOCAL", attempt_limit=1, policy=EndpointPolicy(timeout_seconds=5),
        transport=httpx.MockTransport(refuse), secrets=_fake_store(tmp_path))
    result = await diagnose_profile(runtime, _profile(
        privacy_zone=PrivacyZone.INTERNAL, adapter="vllm_local",
        endpoint="http://127.0.0.1:8000/v1"))
    assert _by_id(result)["connect"]["code"] == "CONNECTION_FAILED"
    assert result["checks"][-1]["id"] == "connect"
