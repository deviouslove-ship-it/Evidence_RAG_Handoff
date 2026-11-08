"""Connection and usability check of a model profile, before it is saved or activated.

``diagnose_profile`` answers one question: *can the application use this model?*  It runs
in order and stops where a later step cannot mean anything:

1. ``config``   the profile passes the same rules a save and a stage assignment apply
                (adapter, endpoint form, egress policy, secret reference);
2. ``mode``     warning when an API profile is checked while the server runs in LOCAL mode;
3. ``secret``   the API key is present (typed, stored or in the environment);
4. ``connect``  ``GET /models`` answers (a bad key, wrong path or dead server shows here);
5. ``model``    the service lists the configured model id;
6. ``generate`` / ``embed``  one tiny request with the profile's own parameters, using a
                synthetic sentence (never document text), proves the model answers, and for
                text models that it can return JSON, which every stage needs.

The result is a list of coded checks; the Admin Portal turns codes into advice.  Nothing
here writes to the database; ``diagnose_saved`` additionally records the health that the
runtime requires (``ready``) after a complete pass.  No key, URL or response body leaves
this module; only codes, timings and the names of models the service itself listed.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from .adapters import AdapterError, OpenAICompatibleAdapter
from .profiles import ModelProfile, OperatingMode, PrivacyZone
from .runtime import (
    RegistryRuntime,
    RegistryRuntimeError,
    SecretError,
    model_advertised,
    validate_profile,
)

PROMPT = [
    {"role": "system", "content": "Bạn là bộ kiểm tra kết nối. Chỉ trả lời bằng JSON."},
    {"role": "user", "content": 'Trả về đúng JSON {"ok": true} và không viết gì khác.'},
]
EMBED_TEXT = "Kiểm tra kết nối model."
SAMPLE_MODELS = 8
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
_JSON = re.compile(r"\{.*\}", re.DOTALL)


def _check(
    check_id: str, status: str, *, code: str | None = None, ms: int | None = None,
    **info: Any,
) -> dict[str, Any]:
    entry: dict[str, Any] = {"id": check_id, "status": status}
    if code:
        entry["code"] = code
    if ms is not None:
        entry["ms"] = ms
    if info:
        entry["info"] = info
    return entry


def _failure_code(exc: BaseException, step: str) -> str:
    """A stable code for an adapter failure; never the response body."""

    if isinstance(exc, AdapterError):
        if exc.unreachable:
            return "CONNECTION_FAILED"
        status = exc.status
        if status in (401, 403):
            return "AUTH_FAILED"
        if status == 404:
            return "ENDPOINT_NOT_FOUND" if step == "connect" else "CHAT_ENDPOINT_NOT_FOUND"
        if status == 429:
            return "RATE_LIMITED"
        if status in (400, 422):
            return "REQUEST_PARAMS_REJECTED"
        if str(exc) == "MODEL_RESPONSE_INVALID":
            return "RESPONSE_INVALID"
        if str(exc) == "MODEL_RESPONSE_TOO_LARGE":
            return "RESPONSE_TOO_LARGE"
        return "REQUEST_REFUSED"
    return "CONNECTION_FAILED"


def _stage_of(profile: ModelProfile) -> str:
    return next(iter(sorted(profile.capabilities)), "answer")


async def _timed(call: Callable[[], Awaitable[Any]]) -> tuple[Any, int]:
    started = time.monotonic()
    value = await call()
    return value, round((time.monotonic() - started) * 1000)


def _json_answer(text: str) -> bool:
    cleaned = _THINK.sub("", text).strip()
    match = _JSON.search(cleaned)
    if not match:
        return False
    try:
        value = json.loads(match.group(0))
    except ValueError:
        return False
    return isinstance(value, dict)


async def diagnose_profile(
    runtime: RegistryRuntime, profile: ModelProfile, *, api_key: str | None = None,
) -> dict[str, Any]:
    """Run the checks.  ``api_key`` is a key typed but not yet saved (used only here)."""

    checks: list[dict[str, Any]] = []
    stage = _stage_of(profile)
    public = profile.privacy_zone == PrivacyZone.PUBLIC
    result: dict[str, Any] = {"stage": stage, "checks": checks, "ok": False, "usable": False,
                              "latency_ms": None, "dimensions": None, "models": []}

    def finish() -> dict[str, Any]:
        failed = any(item["status"] == "fail" for item in checks)
        result["ok"] = not failed
        result["usable"] = not failed and any(
            item["id"] in ("generate", "embed") and item["status"] == "ok" for item in checks)
        return result

    try:
        validate_profile(
            profile, OperatingMode.API if public else OperatingMode.LOCAL, runtime.policy, stage)
    except RegistryRuntimeError as exc:
        checks.append(_check("config", "fail", code=str(exc)))
        return finish()
    checks.append(_check("config", "ok"))

    if public and runtime.mode != OperatingMode.API:
        checks.append(_check("mode", "warn", code="API_MODE_INACTIVE"))

    secret = api_key.strip() if api_key and api_key.strip() else None
    if secret is None:
        try:
            secret = runtime._resolve_secret(profile)
        except SecretError as exc:
            checks.append(_check("secret", "fail", code=str(exc)))
            return finish()
    if secret is not None:
        checks.append(_check("secret", "ok"))
    elif public:
        checks.append(_check("secret", "warn", code="NO_API_KEY"))
    else:
        checks.append(_check("secret", "skip"))

    adapter = OpenAICompatibleAdapter(
        timeout_seconds=runtime.policy.timeout_seconds,
        max_response_bytes=runtime.policy.max_response_bytes,
        max_tokens=runtime.policy.max_tokens,
        api_key=secret,
        transport=runtime.transport,
    )
    listed: frozenset[str] | None = None
    try:
        listed, ms = await _timed(lambda: adapter.list_models(profile))
    except (AdapterError, httpx.HTTPError, TimeoutError) as exc:
        code = _failure_code(exc, "connect")
        # A server without GET /models (404/405) may still chat: continue, unverified.
        if isinstance(exc, AdapterError) and exc.status in (404, 405):
            checks.append(_check("connect", "warn", code="MODELS_LIST_UNSUPPORTED"))
            checks.append(_check("model", "skip"))
        else:
            checks.append(_check("connect", "fail", code=code))
            return finish()
    else:
        checks.append(_check("connect", "ok", ms=ms))
        result["models"] = sorted(listed)[:SAMPLE_MODELS]
        if model_advertised(listed, profile.model_id):
            checks.append(_check("model", "ok"))
        else:
            checks.append(_check("model", "fail", code="MODEL_NOT_FOUND", count=len(listed)))
            return finish()

    if stage == "embedding":
        try:
            vectors, ms = await _timed(lambda: adapter.embed([EMBED_TEXT], profile))
        except (AdapterError, httpx.HTTPError, TimeoutError) as exc:
            checks.append(_check("embed", "fail", code=_failure_code(exc, "embed")))
            return finish()
        result["dimensions"] = len(vectors[0])
        result["latency_ms"] = ms
        checks.append(_check("embed", "ok", ms=ms, dimensions=len(vectors[0])))
        return finish()

    try:
        text, ms = await _timed(lambda: adapter.generate(PROMPT, profile))
    except (AdapterError, httpx.HTTPError, TimeoutError) as exc:
        checks.append(_check("generate", "fail", code=_failure_code(exc, "generate")))
        return finish()
    result["latency_ms"] = ms
    if not _THINK.sub("", text).strip():
        # Typical of reasoning models that spend the whole token budget on thinking.
        checks.append(_check("generate", "fail", code="EMPTY_ANSWER", ms=ms))
        return finish()
    checks.append(_check("generate", "ok", ms=ms))
    if _json_answer(text):
        checks.append(_check("json", "ok"))
    else:
        checks.append(_check("json", "warn", code="JSON_NOT_RETURNED"))
    return finish()


async def diagnose_saved(runtime: RegistryRuntime, profile_id: str) -> dict[str, Any]:
    """Diagnose a stored profile and record the health the runtime needs.

    ``ready`` only after a complete pass of an approved profile; a refused connection or a
    missing model records ``unhealthy`` (so selection skips it); configuration, key and
    approval problems leave it ``unknown`` rather than blaming the server.
    """

    if runtime.pool is None:
        return {"profile_id": profile_id, "ok": False, "usable": False, "checks": [],
                "health": "unknown", "status": "not_configured"}
    profile = await runtime._load_profile(profile_id)
    if profile is None:
        return {"profile_id": profile_id, "ok": False, "usable": False, "checks": [],
                "health": "unknown", "status": "not_configured"}
    result = await diagnose_profile(runtime, profile)
    result["profile_id"] = profile.profile_id
    result["model_id"] = profile.model_id
    network_failure = any(
        item["status"] == "fail" and item["id"] in ("connect", "model", "generate", "embed")
        for item in result["checks"])
    if not profile.provider_approved:
        health, status = "unknown", "unapproved"
        result["checks"].insert(1, _check("approval", "fail", code="PROVIDER_UNAPPROVED"))
        result["ok"], result["usable"] = False, False
    elif result["usable"]:
        health, status = "ready", "ready"
        # The administrator's explicit check lifts a cooldown, as a probe does.
        runtime._cooldown_until.pop(runtime._cooldown_key(profile), None)
    elif network_failure:
        health, status = "unhealthy", "unhealthy"
    else:
        health, status = "unknown", "unusable"
    if not await runtime._set_health(profile, health):
        # The profile was edited while it was being checked: the result is stale.
        health, status = "unknown", "config_changed"
    result["health"] = health
    result["status"] = status
    return result

