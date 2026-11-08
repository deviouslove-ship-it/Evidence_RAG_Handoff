"""Small OpenAI-compatible chat adapter used by the answer stage.

The adapter deliberately has no provider-specific SDK.  vLLM, llama.cpp,
Ollama's OpenAI-compatible endpoint, and hosted OpenAI-compatible services all
use the same bounded HTTP contract here.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from ..profiles import ModelProfile


class AdapterError(RuntimeError):
    """A redacted adapter failure safe to report to application callers.

    ``unreachable`` marks connection failures and timeouts (as opposed to an
    HTTP error status or an invalid body) so the runtime can stop retrying a
    dead endpoint for a while.
    """

    def __init__(
        self, code: str, *, unreachable: bool = False, status: int | None = None,
    ) -> None:
        super().__init__(code)
        self.unreachable = unreachable
        # HTTP status of a refused request (401 key, 404 path/model, 400 parameters);
        # never the response body, which may echo request data.
        self.status = status


# Connecting to a reachable OpenAI-compatible server takes well under a second;
# a dead or firewalled host should not hold a chat turn for the full timeout.
_CONNECT_TIMEOUT_SECONDS = 5.0
_TOKEN_FIELDS = frozenset({"max_tokens", "max_completion_tokens"})
_REASONING_EFFORTS = frozenset({"none", "minimal", "low", "medium", "high"})


class OpenAICompatibleAdapter:
    def __init__(
        self,
        *,
        timeout_seconds: float,
        max_response_bytes: int = 2_000_000,
        max_tokens: int = 2_048,
        api_key: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.max_tokens = max_tokens
        self.api_key = api_key
        self.transport = transport
        # (prompt_tokens, completion_tokens) of the last generate() call, when reported.
        self.last_usage: tuple[int | None, int | None] = (None, None)

    async def generate(
        self,
        messages: Sequence[dict[str, str]],
        profile: ModelProfile,
        *,
        stream: bool = False,
    ) -> str:
        if stream:
            raise AdapterError("STREAM_UNSUPPORTED")
        if not messages:
            raise AdapterError("MODEL_REQUEST_INVALID")

        params = profile.params
        token_field = params.get("token_limit_field")
        if token_field not in _TOKEN_FIELDS:
            token_field = "max_tokens"
        payload: dict[str, Any] = {
            "model": profile.model_id,
            "messages": [dict(item) for item in messages],
            token_field: self._bounded_tokens(params.get("max_tokens")),
        }
        effort = params.get("reasoning_effort")
        if effort in _REASONING_EFFORTS:
            payload["reasoning_effort"] = effort
        for name in ("temperature", "top_p"):
            value = params.get(name)
            if isinstance(value, int | float) and not isinstance(value, bool):
                payload[name] = value
        response_format = params.get("response_format")
        if isinstance(response_format, dict):
            payload["response_format"] = response_format

        data = await self._request(
            "POST",
            f"{profile.endpoint.rstrip('/')}/chat/completions",
            headers=self._headers(),
            json_body=payload,
        )
        try:
            decoded = json.loads(data)
        except (ValueError, TypeError) as exc:
            raise AdapterError("MODEL_RESPONSE_INVALID") from exc
        if not isinstance(decoded, dict):
            raise AdapterError("MODEL_RESPONSE_INVALID")
        usage = decoded.get("usage")
        if isinstance(usage, dict):
            self.last_usage = (_count(usage.get("prompt_tokens")),
                               _count(usage.get("completion_tokens")))
        choices = decoded.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise AdapterError("MODEL_RESPONSE_INVALID")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise AdapterError("MODEL_RESPONSE_INVALID")
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
            if parts:
                return "".join(parts)
        raise AdapterError("MODEL_RESPONSE_INVALID")

    async def embed(self, inputs: Sequence[str], profile: ModelProfile) -> list[list[float]]:
        """OpenAI-compatible ``POST /embeddings`` (Ollama, vLLM, llama.cpp, hosted)."""

        if not inputs:
            return []
        body: dict[str, Any] = {"model": profile.model_id, "input": list(inputs)}
        # Optional output size for models that support shortened vectors (the
        # OpenAI-compatible "dimensions" field); omitted = the model's native size.
        dimensions = profile.params.get("dimensions") if isinstance(profile.params, dict) else None
        if isinstance(dimensions, int) and not isinstance(dimensions, bool) and dimensions > 0:
            body["dimensions"] = dimensions
        data = await self._request(
            "POST",
            f"{profile.endpoint.rstrip('/')}/embeddings",
            headers=self._headers(),
            json_body=body,
        )
        try:
            decoded = json.loads(data)
        except (ValueError, TypeError) as exc:
            raise AdapterError("MODEL_RESPONSE_INVALID") from exc
        entries = decoded.get("data") if isinstance(decoded, dict) else None
        if not isinstance(entries, list) or len(entries) != len(inputs):
            raise AdapterError("MODEL_RESPONSE_INVALID")
        usage = decoded.get("usage")
        if isinstance(usage, dict):
            self.last_usage = (_count(usage.get("prompt_tokens")), 0)
        ordered = sorted(
            entries, key=lambda item: item.get("index", 0) if isinstance(item, dict) else 0
        )
        vectors: list[list[float]] = []
        for item in ordered:
            vector = item.get("embedding") if isinstance(item, dict) else None
            if not isinstance(vector, list) or not vector or not all(
                isinstance(value, int | float) and not isinstance(value, bool) for value in vector
            ):
                raise AdapterError("MODEL_RESPONSE_INVALID")
            vectors.append([float(value) for value in vector])
        if len({len(vector) for vector in vectors}) != 1:
            raise AdapterError("MODEL_RESPONSE_INVALID")
        return vectors

    async def list_models(self, profile: ModelProfile) -> frozenset[str]:
        data = await self._request(
            "GET",
            f"{profile.endpoint.rstrip('/')}/models",
            headers=self._headers(),
            json_body=None,
        )
        try:
            decoded = json.loads(data)
        except (ValueError, TypeError) as exc:
            raise AdapterError("MODEL_RESPONSE_INVALID") from exc
        entries = decoded.get("data") if isinstance(decoded, dict) else None
        if not isinstance(entries, list):
            raise AdapterError("MODEL_RESPONSE_INVALID")
        return frozenset(
            item["id"]
            for item in entries
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        )

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _bounded_tokens(self, value: Any) -> int:
        if isinstance(value, bool):
            return self.max_tokens
        try:
            requested = int(value)
        except (TypeError, ValueError):
            requested = self.max_tokens
        return max(1, min(requested, self.max_tokens))

    async def _request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        json_body: dict[str, Any] | None,
    ) -> bytes:
        try:
            # Do not resolve the special local hostname through DNS or a hosts
            # file: LOCAL mode must connect to loopback even if name resolution
            # has been changed. Preserve Host and TLS SNI for local HTTPS.
            parsed = urlsplit(url)
            extensions: dict[str, str] = {}
            if parsed.hostname and parsed.hostname.lower().rstrip(".") == "localhost":
                if parsed.username is not None or parsed.password is not None:
                    raise AdapterError("MODEL_REQUEST_INVALID")
                authority = f"127.0.0.1:{parsed.port}" if parsed.port else "127.0.0.1"
                headers = {**headers, "Host": parsed.netloc}
                if parsed.scheme == "https":
                    extensions["sni_hostname"] = "localhost"
                url = urlunsplit(
                    (parsed.scheme, authority, parsed.path, parsed.query, parsed.fragment)
                )
            async with asyncio.timeout(self.timeout_seconds):
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(
                        self.timeout_seconds,
                        connect=min(_CONNECT_TIMEOUT_SECONDS, self.timeout_seconds),
                    ),
                    follow_redirects=False,
                    trust_env=False,
                    transport=self.transport,
                ) as client:
                    async with client.stream(
                        method, url, headers=headers, json=json_body, extensions=extensions
                    ) as response:
                        if response.status_code < 200 or response.status_code >= 300:
                            raise AdapterError(
                                "MODEL_REQUEST_FAILED", status=response.status_code)
                        content_length = response.headers.get("content-length")
                        if content_length is not None:
                            try:
                                if int(content_length) > self.max_response_bytes:
                                    raise AdapterError("MODEL_RESPONSE_TOO_LARGE")
                            except ValueError:
                                raise AdapterError("MODEL_RESPONSE_INVALID") from None
                        chunks: list[bytes] = []
                        total = 0
                        async for chunk in response.aiter_bytes():
                            total += len(chunk)
                            if total > self.max_response_bytes:
                                raise AdapterError("MODEL_RESPONSE_TOO_LARGE")
                            chunks.append(chunk)
                        return b"".join(chunks)
        except AdapterError:
            raise
        except (httpx.TransportError, TimeoutError) as exc:
            raise AdapterError("MODEL_REQUEST_FAILED", unreachable=True) from exc
        except httpx.HTTPError as exc:
            raise AdapterError("MODEL_REQUEST_FAILED") from exc


def _count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
