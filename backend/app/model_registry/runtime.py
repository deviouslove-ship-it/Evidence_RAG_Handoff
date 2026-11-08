"""Bounded, registry-backed runtime for OpenAI-compatible answer models.

The runtime intentionally owns only the answer selection call.  It loads the
active route and profile from the database for every operation, applies the
egress and document policy before sending evidence-derived content, and
returns a small canonical JSON selection for the caller to validate.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import math
import os
import re
import time
from collections import deque
from collections.abc import Callable, Coroutine, Mapping, Sequence
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv6Address
from typing import Any, cast
from urllib.parse import SplitResult, urlsplit
from uuid import UUID

import httpx

from ..ai_limits import MAX_AI_OUTPUT_TOKENS
from .adapters import AdapterBudget, AdapterError, OpenAICompatibleAdapter
from .profiles import ModelProfile, OperatingMode, PrivacyZone
from .secret_store import SecretStore, SecretStoreError, secret_name
from .stages import (
    ESCALATION_STAGES,
    LOCAL_ONLY_STAGES,
    MAX_STAGE_ATTEMPTS,
    STAGES,
    StagePolicy,
)

_SUPPORTED_ADAPTERS = frozenset(
    {"openai_compatible", "vllm_local", "llama_cpp_local", "ollama_local"}
)
_SECRET_REF = re.compile(r"^env:[A-Za-z_][A-Za-z0-9_]{0,127}$")


def secret_ref_valid(ref: str) -> bool:
    """``env:NAME`` (not a database/application variable) or ``secret:NAME`` (key store)."""

    if _SECRET_REF.fullmatch(ref):
        return not _SECRET_DENIED.fullmatch(ref[4:])
    return secret_name(ref) is not None


# Base paths under which an OpenAI-compatible server exposes /chat/completions.
# "/v1" covers OpenAI, Ollama, vLLM, llama.cpp; the others are the documented bases of
# Google Gemini ("/v1beta/openai"), Groq ("/openai/v1") and OpenRouter ("/api/v1").
# Where requests may go is still decided by EndpointPolicy, not by this list.
ALLOWED_ENDPOINT_PATHS = frozenset({"/v1", "/v1beta/openai", "/openai/v1", "/api/v1"})
# A profile may only name variables meant for AI providers; database and application
# secrets must never be forwarded to a model endpoint as a bearer token.
_SECRET_DENIED = re.compile(
    r"^(?:DATABASE_URL|PG[A-Z0-9_]*|POSTGRES[A-Z0-9_]*|[A-Z0-9_]*PASSWORD[A-Z0-9_]*|"
    r"EVIDENCE_(?!AI_)[A-Z0-9_]*)$",
    re.IGNORECASE,
)
_LOG = logging.getLogger(__name__)
# The caller cross-checks IDs against the authorized evidence set.  Keep the
# runtime format-neutral while excluding whitespace, control characters, and
# JSON/path-like delimiters from model output.
_EVIDENCE_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,200}$")
_SAFE_PROFILE_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,200}$")
_MAX_CANDIDATES = 16
# How long a profile that timed out or could not be reached is skipped before
# chat turns try it again (a successful probe clears it immediately).
UNREACHABLE_COOLDOWN_SECONDS = 60.0


def model_advertised(advertised: frozenset[str], model_id: str) -> bool:
    """Whether ``GET /models`` lists the model.  Google's OpenAI-compatible endpoint lists
    ``models/<id>``; every other server lists the bare id."""

    return model_id in advertised or f"models/{model_id}" in advertised


class RegistryRuntimeError(ValueError):
    """A redacted configuration or policy error."""


class PolicyError(RegistryRuntimeError):
    """An endpoint is outside the configured egress policy."""


class ProfileValidationError(RegistryRuntimeError):
    """A profile cannot be used by the bounded answer adapter."""


class SecretError(RegistryRuntimeError):
    """A secret reference is absent or not in the supported syntax."""


def _strict_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None or not value.strip():
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError("invalid boolean environment value")


def _csv(value: str | None) -> tuple[str, ...]:
    if value is None:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _authority(parsed: SplitResult) -> str:
    host = parsed.hostname
    if not host:
        raise PolicyError("AI_ENDPOINT_INVALID")
    host = host.lower().rstrip(".")
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    try:
        port = parsed.port
    except ValueError as exc:
        raise PolicyError("AI_ENDPOINT_INVALID") from exc
    if port is not None:
        host = f"{host}:{port}"
    return host


def _normalise_endpoint(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise PolicyError("AI_ENDPOINT_INVALID") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise PolicyError("AI_ENDPOINT_INVALID")
    path = parsed.path.rstrip("/")
    return f"{parsed.scheme.lower()}://{_authority(parsed)}{path}"


def _normalise_domain(value: str) -> str:
    # A domain list is an authority allowlist, never a URL or a suffix rule.
    if not value or any(char in value for char in "/?#@"):
        raise ValueError("invalid remote domain")
    try:
        parsed = urlsplit(f"//{value}")
        authority = _authority(parsed)
    except (PolicyError, ValueError) as exc:
        raise ValueError("invalid remote domain") from exc
    return authority


@dataclass(frozen=True)
class EndpointPolicy:
    """The only network destinations the AI runtime may use."""

    allowed_remote_domains: frozenset[str] = frozenset()
    allowed_lan_endpoints: frozenset[str] = frozenset()
    remote_processing_allowed: bool = False
    # Embeddings run on a local model unless the operator also allows a public
    # (external API) embedding profile; see RegistryRuntime.embed.
    remote_embedding_allowed: bool = False
    timeout_seconds: float = 30.0
    max_response_bytes: int = 2_000_000
    max_tokens: int = MAX_AI_OUTPUT_TOKENS

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
            or self.timeout_seconds > 30
        ):
            raise ValueError("AI timeout must be between 0 and 30 seconds")
        if self.max_response_bytes < 1 or self.max_response_bytes > 10_000_000:
            raise ValueError("AI response limit is invalid")
        if self.max_tokens < 1 or self.max_tokens > 16_384:
            raise ValueError("AI token limit is invalid")

    @classmethod
    def from_env(cls) -> EndpointPolicy:
        timeout_text = os.getenv("EVIDENCE_AI_TIMEOUT_SECONDS", "30").strip()
        try:
            timeout_seconds = float(timeout_text)
        except ValueError as exc:
            raise ValueError("invalid AI timeout") from exc
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0 or timeout_seconds > 30:
            raise ValueError("AI timeout must be between 0 and 30 seconds")

        remote_domains = frozenset(_normalise_domain(item) for item in _csv(
            os.getenv("EVIDENCE_AI_ALLOWED_REMOTE_DOMAINS")
        ))
        lan_endpoints = frozenset(
            _normalise_endpoint(item)
            for item in _csv(os.getenv("EVIDENCE_AI_ALLOWED_LAN_ENDPOINTS"))
        )
        return cls(
            allowed_remote_domains=remote_domains,
            allowed_lan_endpoints=lan_endpoints,
            remote_processing_allowed=_strict_bool(
                os.getenv("EVIDENCE_REMOTE_PROCESSING_ALLOWED")
            ),
            remote_embedding_allowed=_strict_bool(
                os.getenv("EVIDENCE_REMOTE_EMBEDDING_ALLOWED")
            ),
            timeout_seconds=timeout_seconds,
        )

    def validate_endpoint(self, endpoint: str, mode: OperatingMode) -> None:
        try:
            parsed = urlsplit(endpoint)
        except ValueError as exc:
            raise PolicyError("AI_ENDPOINT_INVALID") from exc
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise PolicyError("AI_ENDPOINT_INVALID")
        authority = _authority(parsed)
        host = parsed.hostname
        if not host:
            raise PolicyError("AI_ENDPOINT_INVALID")
        if mode == OperatingMode.API:
            if parsed.scheme != "https":
                raise PolicyError("AI_EGRESS_DENIED")
            try:
                ipaddress.ip_address(host)
            except ValueError:
                pass
            else:
                raise PolicyError("AI_EGRESS_DENIED")
            if not self.remote_processing_allowed or authority not in self.allowed_remote_domains:
                raise PolicyError("AI_EGRESS_DENIED")
            return

        # Local mode accepts literal loopback addresses without an allowlist.
        # Other private addresses need an exact, normalized base URL entry.
        # The reserved name "localhost" is the usual way to address Ollama,
        # llama.cpp and vLLM on the same machine; it never leaves loopback.
        if host.lower().rstrip(".") == "localhost":
            return
        try:
            address: IPv4Address | IPv6Address = ipaddress.ip_address(host)
        except ValueError as exc:
            raise PolicyError("AI_LOCAL_ENDPOINT_DENIED") from exc
        if address.is_loopback:
            return
        if not address.is_private:
            raise PolicyError("AI_LOCAL_ENDPOINT_DENIED")
        if _normalise_endpoint(endpoint) not in self.allowed_lan_endpoints:
            raise PolicyError("AI_LOCAL_ENDPOINT_DENIED")

    def allows_endpoint(self, endpoint: str, mode: OperatingMode) -> bool:
        try:
            self.validate_endpoint(endpoint, mode)
        except (PolicyError, ValueError):
            return False
        return True


def validate_profile(
    profile: ModelProfile,
    mode: OperatingMode | str | None = None,
    policy: EndpointPolicy | None = None,
    stage: str = "answer",
) -> None:
    """Validate a profile for one stage without exposing endpoint or secret values."""

    if not profile.profile_id or len(profile.profile_id) > 200:
        raise ProfileValidationError("PROFILE_INVALID")
    if not profile.model_id or len(profile.model_id) > 256:
        raise ProfileValidationError("PROFILE_INVALID")
    if not profile.revision or len(profile.revision) > 256:
        raise ProfileValidationError("PROFILE_INVALID")
    adapter = profile.adapter.strip().lower()
    if adapter not in _SUPPORTED_ADAPTERS:
        raise ProfileValidationError("ADAPTER_UNSUPPORTED")
    if stage not in profile.capabilities:
        raise ProfileValidationError("MODEL_CAPABILITY_UNAVAILABLE")
    if profile.secret_ref is not None and not secret_ref_valid(profile.secret_ref):
        raise SecretError("MODEL_SECRET_REF_INVALID")

    try:
        parsed = urlsplit(profile.endpoint)
    except ValueError as exc:
        raise ProfileValidationError("AI_ENDPOINT_INVALID") from exc
    if (
        len(profile.endpoint) > 2048
        or parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not parsed.hostname
    ):
        raise ProfileValidationError("AI_ENDPOINT_INVALID")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ProfileValidationError("AI_ENDPOINT_INVALID") from exc
    if port is not None and not 1 <= port <= 65535:
        raise ProfileValidationError("AI_ENDPOINT_INVALID")
    if parsed.path.rstrip("/") not in ALLOWED_ENDPOINT_PATHS:
        raise ProfileValidationError("AI_ENDPOINT_INVALID")

    try:
        zone = profile.privacy_zone
        if not isinstance(zone, PrivacyZone):
            zone = PrivacyZone(str(zone))
    except ValueError as exc:
        raise ProfileValidationError("PROFILE_INVALID") from exc

    if mode is not None:
        selected_mode = OperatingMode(mode)
        if selected_mode == OperatingMode.LOCAL and zone == PrivacyZone.PUBLIC:
            raise PolicyError("AI_LOCAL_ENDPOINT_DENIED")
        # Hybrid Auto: in API mode a non-public profile is a local model and must pass
        # the local endpoint rules; only a public profile may leave the network.
        endpoint_mode = OperatingMode.API if zone == PrivacyZone.PUBLIC else OperatingMode.LOCAL
        (policy or EndpointPolicy()).validate_endpoint(profile.endpoint, endpoint_mode)


def _as_json(value: Any, default: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return default
    return value if value is not None else default


def _strings(value: Any) -> tuple[str, ...]:
    decoded = _as_json(value, value)
    if isinstance(decoded, str):
        return (decoded,)
    if not isinstance(decoded, list | tuple | set):
        return ()
    return tuple(item for item in decoded if isinstance(item, str) and item)


def _profile_from_row(row: Mapping[str, Any]) -> ModelProfile:
    try:
        zone = PrivacyZone(str(row.get("privacy_zone", "")))
    except ValueError as exc:
        raise ProfileValidationError("PROFILE_INVALID") from exc
    params = _as_json(row.get("params"), {})
    if not isinstance(params, dict):
        params = {}
    return ModelProfile(
        profile_id=str(row.get("profile_key", "")),
        adapter=str(row.get("adapter", "")),
        endpoint=str(row.get("endpoint", "")),
        model_id=str(row.get("model_id", "")),
        capabilities=frozenset(_strings(row.get("capabilities"))),
        privacy_zone=zone,
        revision=str(row.get("revision", "")),
        secret_ref=row.get("secret_ref") if isinstance(row.get("secret_ref"), str) else None,
        fallback=_strings(row.get("fallback")),
        params=params,
        provider_approved=bool(row.get("provider_approved", row.get("approved", False))),
        health=str(row.get("health", "unknown")).lower(),
        input_price_per_mtok=_optional_number(row.get("input_price_per_mtok")),
        output_price_per_mtok=_optional_number(row.get("output_price_per_mtok")),
        daily_cost_limit=_optional_number(row.get("daily_cost_limit")),
        monthly_cost_limit=_optional_number(row.get("monthly_cost_limit")),
    )


def _optional_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_CODE_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL | re.IGNORECASE)


def _unwrap_model_text(content: str) -> str:
    """Drop reasoning blocks and a single markdown fence that local models add."""

    text = _THINK_BLOCK.sub("", content).strip()
    fenced = _CODE_FENCE.match(text)
    return fenced.group(1) if fenced else text


def _canonical_selection(content: str) -> str | None:
    try:
        payload = json.loads(_unwrap_model_text(content))
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict) or set(payload) != {"evidence_ids"}:
        return None
    if not isinstance(payload.get("evidence_ids"), list):
        return None
    if len(payload["evidence_ids"]) > 3:
        return None
    evidence_ids: list[str] = []
    for value in payload["evidence_ids"]:
        if not isinstance(value, str) or not _EVIDENCE_ID.fullmatch(value):
            return None
        if value not in evidence_ids:
            evidence_ids.append(value)
        else:
            return None
    return json.dumps({"evidence_ids": evidence_ids}, separators=(",", ":"))


def _reason(exc: BaseException) -> str:
    """Log only a redacted code or exception class, never URLs or secrets."""
    if isinstance(exc, RegistryRuntimeError | AdapterError):
        return str(exc)
    return type(exc).__name__


def _safe_profile_id(value: str) -> str:
    return value if _SAFE_PROFILE_ID.fullmatch(value) else "unknown"


@dataclass(frozen=True)
class GenerationOutcome:
    """What one stage call produced, without prompt or answer details for logs.

    ``external_api_used`` is true when evidence-derived content was sent to a
    public profile; ``escalated`` when that was the Hybrid Auto escalation
    profile; ``limited`` when a cost cap kept a configured profile from being
    called, so the caller can tell the user the model step was skipped.
    """

    content: str | None = None
    external_api_used: bool = False
    escalated: bool = False
    limited: bool = False


@dataclass(frozen=True)
class EmbeddingOutcome:
    """Vectors from the ``embedding`` stage and the model that made them.

    ``error`` is a redacted code (never a URL or secret) explaining why no vector
    was produced, so callers can report it to the administrator.
    """

    vectors: list[list[float]] | None = None
    profile_key: str | None = None
    model_id: str | None = None
    revision: str | None = None
    error: str | None = None

    @property
    def dimensions(self) -> int | None:
        return len(self.vectors[0]) if self.vectors else None


@dataclass
class _CallState:
    local_sends: int = 0
    external_api_used: bool = False
    escalated: bool = False
    limited: bool = False
    remote_allowed: bool | None = None

    def outcome(self, content: str | None) -> GenerationOutcome:
        return GenerationOutcome(
            content=content,
            external_api_used=self.external_api_used,
            escalated=self.escalated,
            limited=self.limited,
        )


@dataclass(frozen=True)
class _StagePlan:
    candidates: list[ModelProfile]
    escalation: ModelProfile | None
    policy: StagePolicy


def _estimated_input_tokens(messages: Sequence[dict[str, str]]) -> int:
    # Used only for cost estimates when the server does not report usage:
    # about three characters per token for Vietnamese text, rounded up.
    characters = sum(len(str(item.get("content", ""))) for item in messages)
    return max(1, math.ceil(characters / 3))


class RegistryRuntime:
    """Resolve the configured route of a stage and make a bounded number of sends.

    ``attempt_limit`` is the server default; a ``stage_policies`` row for the
    (mode, stage) overrides it (ADR-007).  In API mode (Hybrid Auto) the route
    may start with a local profile and name one public escalation profile that
    is tried once when no local result passes the caller's check, or first when
    the user asks for a deeper analysis.  LOCAL mode never sends to a public
    profile.
    """

    def __init__(
        self,
        pool: Any,
        mode: OperatingMode | str,
        attempt_limit: int,
        policy: EndpointPolicy,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        secrets: SecretStore | None = None,
    ) -> None:
        self.pool = pool
        # Keys typed in the Admin Portal ("secret:NAME"); "env:NAME" never uses it.
        self.secrets = secrets if secrets is not None else SecretStore.from_env()
        self.mode = OperatingMode(mode)
        if attempt_limit < 1 or attempt_limit > MAX_STAGE_ATTEMPTS:
            raise ValueError(f"LLM attempt budget must be between 1 and {MAX_STAGE_ATTEMPTS}")
        self.attempt_limit = attempt_limit
        # (mode, stage) -> (configured size, semaphore) bounding concurrent sends.
        self._semaphores: dict[tuple[str, str], tuple[int, asyncio.Semaphore]] = {}
        self._background: set[asyncio.Future[None]] = set()
        self.policy = policy
        self.transport = transport
        # (profile, endpoint, model) -> monotonic time until which the profile is
        # skipped after it was unreachable or too slow.  Health stays "ready" in
        # the database until an administrator probes again, so without this every
        # chat turn would wait for the full timeout of a stopped model server.
        self._cooldown_until: dict[tuple[str, str, str], float] = {}

    @staticmethod
    def _cooldown_key(profile: ModelProfile) -> tuple[str, str, str]:
        return (profile.profile_id, profile.endpoint, profile.model_id)

    def _cooling_down(self, profile: ModelProfile) -> bool:
        until = self._cooldown_until.get(self._cooldown_key(profile))
        if until is None:
            return False
        if time.monotonic() >= until:
            self._cooldown_until.pop(self._cooldown_key(profile), None)
            return False
        return True

    def _start_cooldown(self, profile: ModelProfile) -> None:
        if len(self._cooldown_until) >= 64:
            self._cooldown_until.clear()
        self._cooldown_until[self._cooldown_key(profile)] = (
            time.monotonic() + UNREACHABLE_COOLDOWN_SECONDS
        )

    async def generate_selection(
        self,
        messages: Sequence[dict[str, str]],
        *,
        principal_id: UUID | str,
        document_ids: Sequence[UUID | str],
        accept: Callable[[str], bool] | None = None,
        deep_analysis: bool = False,
    ) -> GenerationOutcome:
        """Generate only a canonical evidence-id selection for the answer stage.

        ``accept`` is the caller's check of the canonical selection (for example
        "every id belongs to the evidence offered").  A local result that fails
        it counts as "not good enough" for Hybrid Auto escalation.
        """

        return await self.generate(
            "answer", messages, principal_id=principal_id, document_ids=document_ids,
            parse=_canonical_selection, accept=accept, deep_analysis=deep_analysis,
        )

    async def generate(
        self,
        stage: str,
        messages: Sequence[dict[str, str]],
        *,
        principal_id: UUID | str,
        document_ids: Sequence[UUID | str],
        parse: Callable[[str], str | None],
        accept: Callable[[str], bool] | None = None,
        deep_analysis: bool = False,
    ) -> GenerationOutcome:
        """Run one stage through its route, fallbacks and optional escalation.

        Callers invoke this only when there is evidence to work on: missing
        evidence, no match or unverified effectivity never reach a model, so
        they can never trigger an API escalation either.
        """

        state = _CallState()
        if self.pool is None or not messages:
            return state.outcome(None)
        try:
            plan = await self._load_plan(stage)
            if plan is None:
                return state.outcome(None)
            escalation = plan.escalation if stage in ESCALATION_STAGES else None
            if deep_analysis and escalation is not None:
                content = await self._send(
                    escalation, stage, messages, plan.policy, state,
                    principal_id=principal_id, document_ids=document_ids,
                    parse=parse, accept=accept, escalation=True,
                )
                if content is not None:
                    return state.outcome(content)
            budget = AdapterBudget(limit=plan.policy.max_attempts)
            for profile in plan.candidates:
                if budget.used >= budget.limit:
                    break
                content = await self._send(
                    profile, stage, messages, plan.policy, state,
                    principal_id=principal_id, document_ids=document_ids,
                    parse=parse, accept=accept, budget=budget,
                )
                if content is not None:
                    return state.outcome(content)
            # Hybrid Auto: escalate once, only after a local model actually ran and
            # none of its results passed the check.  A local route that could not
            # be used at all is a configuration problem, not a quality problem.
            if escalation is not None and not deep_analysis and state.local_sends > 0:
                content = await self._send(
                    escalation, stage, messages, plan.policy, state,
                    principal_id=principal_id, document_ids=document_ids,
                    parse=parse, accept=accept, escalation=True,
                )
                if content is not None:
                    return state.outcome(content)
        except Exception as exc:
            # Database and transport details never cross the runtime boundary.
            _LOG.warning("AI %s unavailable: %s", stage, _reason(exc))
        return state.outcome(None)

    async def embed(
        self,
        texts: Sequence[str],
        *,
        principal_id: UUID | str | None = None,
        profile_key: str | None = None,
        purpose: str = "query",
    ) -> EmbeddingOutcome:
        """Embed with the ``embedding`` route (or one named profile).

        Embeddings use a local model.  A public (external API) profile is used only
        when the operator allows it (API mode, ``EVIDENCE_REMOTE_PROCESSING_ALLOWED``,
        ``EVIDENCE_REMOTE_EMBEDDING_ALLOWED`` and the domain allowlist) and, for a
        search query (``purpose="query"``), the user may send data to external AI.
        ``purpose="index"`` is used only by the embedding build, which checks that
        every document it sends may be processed outside first.
        """

        if self.pool is None or not texts:
            return EmbeddingOutcome(error="EMBEDDING_NOT_CONFIGURED")
        error = "EMBEDDING_NOT_CONFIGURED"
        try:
            if profile_key:
                named = await self._load_profile(profile_key)
                candidates = [named] if named is not None else []
                error = "PROFILE_NOT_FOUND"
                async with self.pool.acquire() as connection:
                    policy_row = await connection.fetchrow(
                        """/* stage policy */
                           SELECT max_attempts, max_output_tokens, timeout_seconds,
                                  max_concurrency
                           FROM stage_policies WHERE mode = $1 AND stage = 'embedding'
                           LIMIT 1""",
                        self.mode.value,
                    )
                loaded = self._stage_policy(policy_row)
                stage_policy = StagePolicy(
                    max_attempts=1, timeout_seconds=loaded.timeout_seconds,
                    max_concurrency=loaded.max_concurrency,
                )
            else:
                plan = await self._load_plan("embedding")
                if plan is None:
                    return EmbeddingOutcome(error="EMBEDDING_NOT_CONFIGURED")
                candidates, stage_policy = plan.candidates, plan.policy
            for profile in candidates[: stage_policy.max_attempts]:
                if not profile.provider_approved:
                    error = "PROFILE_UNAPPROVED"
                    continue
                if profile.health == "unhealthy":
                    error = "PROFILE_UNHEALTHY"
                    continue
                # The background build has its own back-off; the cool-down protects
                # interactive searches from waiting on a stopped model server.
                if purpose != "index" and self._cooling_down(profile):
                    error = "MODEL_UNREACHABLE"
                    continue
                if profile.privacy_zone == PrivacyZone.PUBLIC:
                    denied = await self._remote_embedding_denied(principal_id, purpose)
                    if denied is not None:
                        error = denied
                        continue
                try:
                    validate_profile(profile, self.mode, self.policy, "embedding")
                    secret = self._resolve_secret(profile)
                except RegistryRuntimeError as exc:
                    _LOG.warning("AI embedding profile skipped: %s", exc)
                    error = str(exc)
                    continue
                adapter = OpenAICompatibleAdapter(
                    timeout_seconds=min(
                        stage_policy.timeout_seconds or self.policy.timeout_seconds,
                        self.policy.timeout_seconds,
                    ),
                    max_response_bytes=max(self.policy.max_response_bytes, 10_000_000)
                    if len(texts) > 1 else self.policy.max_response_bytes,
                    api_key=secret, transport=self.transport,
                )
                started = time.monotonic()
                payload = [{"content": "\n".join(texts)}]
                try:
                    async with self._semaphore("embedding", stage_policy):
                        vectors = await adapter.embed(texts, profile)
                except (AdapterError, httpx.HTTPError, TimeoutError) as exc:
                    unreachable = isinstance(exc, TimeoutError | httpx.TransportError) or (
                        isinstance(exc, AdapterError) and exc.unreachable
                    )
                    if unreachable:
                        self._start_cooldown(profile)
                    error = "MODEL_UNREACHABLE" if unreachable else (
                        str(exc) if isinstance(exc, AdapterError) else "MODEL_REQUEST_FAILED"
                    )
                    await self._record_usage(
                        profile, "embedding", adapter, payload, 0, started, "error",
                        principal_id=principal_id or "", escalated=False,
                    )
                    continue
                await self._record_usage(
                    profile, "embedding", adapter, payload, 0, started, "ok",
                    principal_id=principal_id or "", escalated=False,
                )
                return EmbeddingOutcome(
                    vectors, profile.profile_id, profile.model_id, profile.revision
                )
        except Exception as exc:
            _LOG.warning("AI embedding unavailable: %s", _reason(exc))
            error = "EMBEDDING_UNAVAILABLE"
        return EmbeddingOutcome(error=error)

    async def _remote_embedding_denied(
        self, principal_id: UUID | str | None, purpose: str
    ) -> str | None:
        """Why a public embedding profile may not be used now (``None`` = allowed)."""

        if self.mode != OperatingMode.API or not (
            self.policy.remote_processing_allowed and self.policy.remote_embedding_allowed
        ):
            return "REMOTE_EMBEDDING_DENIED"
        if purpose == "index":
            return None
        try:
            principal = UUID(str(principal_id))
        except (TypeError, ValueError):
            return "REMOTE_EMBEDDING_DENIED"
        async with self.pool.acquire() as connection:
            user = await connection.fetchrow(
                "SELECT remote_ai_allowed, disabled_at FROM users WHERE id = $1 LIMIT 1",
                principal,
            )
        if user is None or not bool(user.get("remote_ai_allowed")) or (
            user.get("disabled_at") is not None
        ):
            return "REMOTE_EMBEDDING_DENIED"
        return None

    async def _send(
        self,
        profile: ModelProfile,
        stage: str,
        messages: Sequence[dict[str, str]],
        stage_policy: StagePolicy,
        state: _CallState,
        *,
        principal_id: UUID | str,
        document_ids: Sequence[UUID | str],
        parse: Callable[[str], str | None],
        accept: Callable[[str], bool] | None,
        budget: AdapterBudget | None = None,
        escalation: bool = False,
    ) -> str | None:
        """Send once to ``profile`` if every gate allows it; return the accepted text."""

        if not profile.provider_approved or profile.health != "ready":
            return None
        if self._cooling_down(profile):
            return None
        try:
            validate_profile(profile, self.mode, self.policy, stage)
            secret = self._resolve_secret(profile)
        except RegistryRuntimeError as exc:
            _LOG.warning("AI profile skipped: %s", exc)
            return None
        public = profile.privacy_zone == PrivacyZone.PUBLIC
        if public:
            if self.mode != OperatingMode.API or stage in LOCAL_ONLY_STAGES:
                return None
            if state.remote_allowed is None:
                state.remote_allowed = await self._remote_authorized(principal_id, document_ids)
            if not state.remote_allowed:
                return None
        if await self._over_cost_limit(profile):
            state.limited = True
            _LOG.warning("AI profile skipped: AI_COST_LIMIT_REACHED")
            return None
        if budget is not None:
            budget.consume()
        if public:
            state.external_api_used = True
            state.escalated = state.escalated or escalation
        else:
            state.local_sends += 1
        timeout = min(
            stage_policy.timeout_seconds or self.policy.timeout_seconds,
            self.policy.timeout_seconds,
        )
        max_tokens = min(
            stage_policy.max_output_tokens or self.policy.max_tokens, self.policy.max_tokens
        )
        adapter = OpenAICompatibleAdapter(
            timeout_seconds=timeout,
            max_response_bytes=self.policy.max_response_bytes,
            max_tokens=max_tokens,
            api_key=secret,
            transport=self.transport,
        )
        started = time.monotonic()

        def record(outcome: str) -> Coroutine[Any, Any, None]:
            return self._record_usage(
                profile, stage, adapter, messages, max_tokens, started, outcome,
                principal_id=principal_id, escalated=escalation,
            )

        try:
            async with self._semaphore(stage, stage_policy):
                content = await adapter.generate(messages, profile, stream=False)
        except asyncio.CancelledError:
            # The caller's budget expired while this model was still answering:
            # treat it as too slow for the next turns.  The send may still be
            # billed, so log it without holding up the cancellation.
            self._start_cooldown(profile)
            task = asyncio.ensure_future(record("cancelled"))
            self._background.add(task)
            task.add_done_callback(self._background.discard)
            raise
        except (AdapterError, httpx.HTTPError, TimeoutError) as exc:
            unreachable = isinstance(exc, TimeoutError | httpx.TransportError) or (
                isinstance(exc, AdapterError) and exc.unreachable
            )
            if unreachable:
                self._start_cooldown(profile)
            _LOG.warning("AI %s attempt failed: %s", stage, _reason(exc))
            await record("unreachable" if unreachable else "error")
            return None
        parsed = parse(content)
        if parsed is None:
            outcome = "unusable"
        elif accept is not None and not accept(parsed):
            outcome = "rejected"
        else:
            outcome = "ok"
        await record(outcome)
        if outcome != "ok":
            _LOG.warning("AI %s attempt returned an unusable answer", stage)
            return None
        return parsed

    def _semaphore(self, stage: str, stage_policy: StagePolicy) -> asyncio.Semaphore:
        size = stage_policy.max_concurrency or 64
        key = (self.mode.value, stage)
        current = self._semaphores.get(key)
        if current is None or current[0] != size:
            current = (size, asyncio.Semaphore(size))
            self._semaphores[key] = current
        return current[1]

    async def _over_cost_limit(self, profile: ModelProfile) -> bool:
        if profile.daily_cost_limit is None and profile.monthly_cost_limit is None:
            return False
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                """/* ai usage cost */
                   SELECT
                     COALESCE(SUM(estimated_cost) FILTER (
                       WHERE occurred_at >= date_trunc('day', now())), 0) AS day_cost,
                     COALESCE(SUM(estimated_cost), 0) AS month_cost
                   FROM ai_usage_events
                   WHERE profile_key = $1 AND occurred_at >= date_trunc('month', now())""",
                profile.profile_id,
            )
        day_cost = _optional_number(row.get("day_cost")) if row else None
        month_cost = _optional_number(row.get("month_cost")) if row else None
        if profile.daily_cost_limit is not None and (day_cost or 0) >= profile.daily_cost_limit:
            return True
        return (
            profile.monthly_cost_limit is not None
            and (month_cost or 0) >= profile.monthly_cost_limit
        )

    async def _record_usage(
        self,
        profile: ModelProfile,
        stage: str,
        adapter: OpenAICompatibleAdapter,
        messages: Sequence[dict[str, str]],
        max_tokens: int,
        started: float,
        outcome: str,
        *,
        principal_id: UUID | str,
        escalated: bool,
    ) -> None:
        """Log one send: tokens, duration, cost.  Never prompt or answer content."""

        input_tokens, output_tokens = adapter.last_usage
        cost: float | None = None
        if profile.input_price_per_mtok is not None or profile.output_price_per_mtok is not None:
            # Unreported usage is estimated high (full output budget) so a cap errs
            # on the side of stopping early.
            billed_in = input_tokens if input_tokens is not None else _estimated_input_tokens(
                messages
            )
            billed_out = output_tokens if output_tokens is not None else max_tokens
            cost = (
                billed_in * (profile.input_price_per_mtok or 0)
                + billed_out * (profile.output_price_per_mtok or 0)
            ) / 1_000_000
        try:
            principal: UUID | None = UUID(str(principal_id))
        except (TypeError, ValueError):
            principal = None
        try:
            async with self.pool.acquire() as connection:
                await connection.execute(
                    """INSERT INTO ai_usage_events
                       (mode, stage, profile_key, principal_id, outcome, escalated,
                        input_tokens, output_tokens, duration_ms, estimated_cost)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)""",
                    self.mode.value,
                    stage,
                    profile.profile_id,
                    principal,
                    outcome,
                    escalated,
                    input_tokens,
                    output_tokens,
                    int((time.monotonic() - started) * 1000),
                    cost,
                )
        except Exception as exc:
            _LOG.warning("AI usage event not recorded: %s", _reason(exc))
    async def probe(self, profile_id: str) -> dict[str, Any]:
        """Probe ``GET /models`` and persist only a sanitized health state."""

        safe_id = _safe_profile_id(profile_id)
        if self.pool is None:
            return {"profile_id": safe_id, "status": "not_configured", "health": "unknown"}
        try:
            profile = await self._load_profile(profile_id)
        except Exception:
            return {"profile_id": safe_id, "status": "unavailable", "health": "unknown"}
        if profile is None:
            return {"profile_id": safe_id, "status": "not_configured", "health": "unknown"}

        base = {"profile_id": safe_id, "model_id": profile.model_id}
        if not profile.provider_approved:
            return await self._probe_health_result(profile, base, "unapproved", "unknown")
        try:
            stage = next(iter(sorted(profile.capabilities)), "answer")
            validate_profile(profile, self.mode, self.policy, stage)
            secret = self._resolve_secret(profile)
        except SecretError:
            return await self._probe_health_result(profile, base, "secret_missing", "unknown")
        except PolicyError:
            return await self._probe_health_result(profile, base, "denied", "unknown")
        except ProfileValidationError:
            return await self._probe_health_result(profile, base, "unsupported", "unknown")

        adapter = OpenAICompatibleAdapter(
            timeout_seconds=self.policy.timeout_seconds,
            max_response_bytes=self.policy.max_response_bytes,
            max_tokens=self.policy.max_tokens,
            api_key=secret,
            transport=self.transport,
        )
        try:
            advertised = await adapter.list_models(profile)
        except (AdapterError, httpx.HTTPError, TimeoutError):
            return await self._probe_health_result(profile, base, "unhealthy", "unhealthy")
        if not model_advertised(advertised, profile.model_id):
            return await self._probe_health_result(profile, base, "unhealthy", "unhealthy")
        # A successful probe is the administrator's signal that the server is back.
        self._cooldown_until.pop(self._cooldown_key(profile), None)
        return await self._probe_health_result(profile, base, "ready", "ready")

    async def _probe_health_result(
        self,
        profile: ModelProfile,
        base: dict[str, Any],
        status: str,
        health: str,
    ) -> dict[str, Any]:
        if not await self._set_health(profile, health):
            return {**base, "status": "config_changed", "health": "unknown"}
        return {**base, "status": status, "health": health}

    async def _load_plan(self, stage: str) -> _StagePlan | None:
        if stage not in STAGES:
            return None
        async with self.pool.acquire() as connection:
            candidates, escalation_key = await self._load_route(connection, stage)
            if not candidates:
                return None
            escalation: ModelProfile | None = None
            # The escalation profile exists only in API mode (Hybrid Auto) and must
            # be public; LOCAL mode never loads it, so it can never be called.
            if self.mode == OperatingMode.API and escalation_key:
                row = await self._fetch_profile(connection, escalation_key)
                if row is not None:
                    try:
                        loaded = _profile_from_row(row)
                    except ProfileValidationError:
                        loaded = None
                    if loaded is not None and loaded.privacy_zone == PrivacyZone.PUBLIC:
                        escalation = loaded
            policy_row = await connection.fetchrow(
                """/* stage policy */
                   SELECT max_attempts, max_output_tokens, timeout_seconds, max_concurrency
                   FROM stage_policies WHERE mode = $1 AND stage = $2 LIMIT 1""",
                self.mode.value,
                stage,
            )
        return _StagePlan(candidates, escalation, self._stage_policy(policy_row))

    def _stage_policy(self, row: Mapping[str, Any] | None) -> StagePolicy:
        default = StagePolicy(max_attempts=self.attempt_limit)
        if row is None:
            return default
        try:
            timeout = _optional_number(row.get("timeout_seconds"))
            return StagePolicy(
                max_attempts=int(row.get("max_attempts") or self.attempt_limit),
                max_output_tokens=row.get("max_output_tokens"),
                timeout_seconds=timeout,
                max_concurrency=row.get("max_concurrency"),
            )
        except (TypeError, ValueError):
            return default

    async def _load_candidates(self, stage: str = "answer") -> list[ModelProfile]:
        async with self.pool.acquire() as connection:
            candidates, _ = await self._load_route(connection, stage)
        return candidates

    async def _load_route(
        self, connection: Any, stage: str
    ) -> tuple[list[ModelProfile], str | None]:
        route = await connection.fetchrow(
            """/* registry route */
               SELECT mp.profile_key AS profile_key, sr.fallback AS route_fallback,
                      ep.profile_key AS escalation_key
               FROM stage_routes sr
               JOIN model_profiles mp ON mp.id = sr.profile_id
               LEFT JOIN model_profiles ep ON ep.id = sr.escalation_profile_id
               WHERE sr.mode = $1 AND sr.stage = $2
               LIMIT 1""",
            self.mode.value,
            stage,
        )
        if route is None:
            return [], None
        escalation_key = route.get("escalation_key")
        if not isinstance(escalation_key, str) or not escalation_key:
            escalation_key = None
        primary_id = route.get("profile_key") or route.get("profile_id")
        if not isinstance(primary_id, str) or not primary_id:
            return [], None
        primary_row = await self._fetch_profile(connection, primary_id)
        if primary_row is None:
            return [], None
        try:
            primary = _profile_from_row(primary_row)
        except ProfileValidationError:
            return [], None
        candidates = [primary]
        primary_zone = primary.privacy_zone
        pending: deque[str] = deque(
            _strings(route.get("route_fallback", route.get("fallback")))[:_MAX_CANDIDATES]
        )
        pending.extend(primary.fallback[:_MAX_CANDIDATES])
        seen = {primary.profile_id}
        examined = 1
        while pending and examined < _MAX_CANDIDATES:
            profile_id = pending.popleft()
            examined += 1
            if profile_id in seen:
                continue
            seen.add(profile_id)
            row = await self._fetch_profile(connection, profile_id)
            if row is None:
                continue
            try:
                candidate = _profile_from_row(row)
            except ProfileValidationError:
                continue
            if candidate.privacy_zone != primary_zone:
                continue
            candidates.append(candidate)
            pending.extend(candidate.fallback[:_MAX_CANDIDATES])
        return candidates, escalation_key

    async def _load_profile(self, profile_id: str) -> ModelProfile | None:
        async with self.pool.acquire() as connection:
            row = await self._fetch_profile(connection, profile_id)
        if row is None:
            return None
        try:
            return _profile_from_row(row)
        except ProfileValidationError:
            return None

    @staticmethod
    async def _fetch_profile(connection: Any, profile_id: str) -> Mapping[str, Any] | None:
        row = await connection.fetchrow(
            """/* registry profile */
               SELECT mp.profile_key, p.adapter, p.endpoint, p.approved AS provider_approved,
                      mp.model_id, mp.revision, mp.capabilities, mp.privacy_zone,
                      mp.params, mp.secret_ref, mp.fallback, mp.health,
                      mp.input_price_per_mtok, mp.output_price_per_mtok,
                      mp.daily_cost_limit, mp.monthly_cost_limit
               FROM model_profiles mp
               JOIN providers p ON p.id = mp.provider_id
               WHERE mp.profile_key = $1
               LIMIT 1""",
            profile_id,
        )
        if row is None:
            return None
        return cast(Mapping[str, Any], row)

    async def _remote_authorized(
        self,
        principal_id: UUID | str,
        document_ids: Sequence[UUID | str],
    ) -> bool:
        try:
            principal = UUID(str(principal_id))
            requested = [UUID(str(item)) for item in document_ids]
        except (TypeError, ValueError, AttributeError):
            return False
        if not requested:
            return False

        async with self.pool.acquire() as connection:
            user = await connection.fetchrow(
                """SELECT remote_ai_allowed, disabled_at
                   FROM users WHERE id = $1 LIMIT 1""",
                principal,
            )
            if user is None or not bool(user.get("remote_ai_allowed")):
                return False
            if user.get("disabled_at") is not None:
                return False
            async with connection.transaction():
                await connection.execute(
                    "SELECT set_config('app.user_id', $1, true)", str(principal)
                )
                allowed = await connection.fetchval(
                    """/* registry evidence gate */
                    WITH requested(document_id) AS (
                        SELECT unnest($1::uuid[])
                    ), authorized AS (
                        SELECT DISTINCT n.document_id
                        FROM authorized_nodes n
                        WHERE n.document_id = ANY($1::uuid[])
                    ), flags AS (
                        SELECT r.document_id,
                               a.document_id IS NOT NULL AS authorized,
                               d.id IS NOT NULL
                                   AND d.deleted_at IS NULL
                                   AND d.classification_level <> 'restricted'
                                   AS classification_ok,
                               COUNT(c.id) > 0 AS has_category,
                               COALESCE(
                                   BOOL_AND(c.remote_processing_allowed AND c.deleted_at IS NULL),
                                   FALSE
                               ) AS categories_ok
                        FROM requested r
                        LEFT JOIN authorized a ON a.document_id = r.document_id
                        LEFT JOIN documents d ON d.id = r.document_id
                        LEFT JOIN document_categories dc ON dc.document_id = r.document_id
                        LEFT JOIN categories c ON c.id = dc.category_id
                        GROUP BY r.document_id, a.document_id, d.id,
                                 d.deleted_at, d.classification_level
                    )
                    SELECT COALESCE(
                        BOOL_AND(
                            authorized AND classification_ok AND has_category AND categories_ok
                        ),
                        FALSE
                    )
                    FROM flags""",
                    requested,
                )
        return bool(allowed)

    def _resolve_secret(self, profile: ModelProfile) -> str | None:
        if profile.secret_ref is None:
            return None
        if not secret_ref_valid(profile.secret_ref):
            raise SecretError("MODEL_SECRET_REF_INVALID")
        stored = secret_name(profile.secret_ref)
        if stored is not None:
            try:
                key = self.secrets.get(stored)
            except SecretStoreError as exc:
                raise SecretError("MODEL_SECRET_UNAVAILABLE") from exc
            if not key:
                raise SecretError("MODEL_SECRET_UNAVAILABLE")
            return key
        value = os.getenv(profile.secret_ref[4:])
        if not value:
            raise SecretError("MODEL_SECRET_UNAVAILABLE")
        return value

    async def _set_health(self, profile: ModelProfile, health: str) -> bool:
        if self.pool is None:
            return False
        try:
            async with self.pool.acquire() as connection:
                status = await connection.execute(
                    """UPDATE model_profiles AS mp
                       SET health = $1
                       FROM providers AS p
                       WHERE mp.provider_id = p.id
                         AND mp.profile_key = $2
                         AND mp.model_id = $3
                         AND mp.revision = $4
                         AND mp.secret_ref IS NOT DISTINCT FROM $5
                         AND p.endpoint = $6
                         AND p.adapter = $7
                         AND p.approved = $8""",
                    health,
                    profile.profile_id,
                    profile.model_id,
                    profile.revision,
                    profile.secret_ref,
                    profile.endpoint,
                    profile.adapter,
                    profile.provider_approved,
                )
                return isinstance(status, str) and status.rsplit(" ", 1)[-1] == "1"
        except Exception:
            return False


__all__ = [
    "EndpointPolicy",
    "GenerationOutcome",
    "PolicyError",
    "ProfileValidationError",
    "RegistryRuntime",
    "RegistryRuntimeError",
    "SecretError",
    "validate_profile",
]
