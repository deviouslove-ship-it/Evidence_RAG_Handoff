"""Client for the local cross-encoder reranker service (experimental, G5 benchmark).

The service (``scripts/local_reranker_server.py``) runs Qwen3-Reranker on the CPU of the same
machine.  Only a loopback address is accepted, so no clause text can reach an external API
through this path.  Nothing here is used unless ``EVIDENCE_RERANK_BACKEND=cross_encoder``.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

import httpx

MAX_DOCUMENTS = 200


class CrossEncoderError(RuntimeError):
    """The local reranker is unreachable or returned something unusable."""


def validate_loopback_url(url: str) -> str:
    parts = urlsplit(url)
    host = parts.hostname or ""
    if parts.scheme != "http" or parts.username or parts.password:
        raise ValueError("EVIDENCE_CROSS_ENCODER_URL must be a plain http:// loopback URL")
    try:
        loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = host == "localhost"
    if not loopback:
        raise ValueError("EVIDENCE_CROSS_ENCODER_URL must point to this machine (loopback)")
    return url.rstrip("/")


class CrossEncoderClient:
    def __init__(self, url: str, *, timeout_seconds: float, instruction: str | None = None):
        self._url = validate_loopback_url(url)
        self._timeout = timeout_seconds
        self._instruction = instruction

    async def score(self, query: str, documents: list[str]) -> list[float]:
        if not documents or len(documents) > MAX_DOCUMENTS:
            raise CrossEncoderError("document count out of range")
        body: dict[str, object] = {"query": query, "documents": documents}
        if self._instruction:
            body["instruction"] = self._instruction
        try:
            async with httpx.AsyncClient(timeout=self._timeout, trust_env=False) as client:
                response = await client.post(f"{self._url}/rerank", json=body)
                response.raise_for_status()
                scores = response.json().get("scores")
        except (httpx.HTTPError, ValueError) as exc:
            raise CrossEncoderError(type(exc).__name__) from exc
        if (not isinstance(scores, list) or len(scores) != len(documents)
                or not all(isinstance(v, int | float) and not isinstance(v, bool)
                           and 0 <= v <= 1 for v in scores)):
            raise CrossEncoderError("unexpected response")
        return [float(value) for value in scores]
