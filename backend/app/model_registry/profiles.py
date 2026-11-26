"""Model profile types.  Values are configuration, never source defaults."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256
from typing import Any


class OperatingMode(StrEnum):
    API = "API"
    LOCAL = "LOCAL"


class PrivacyZone(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    RESTRICTED = "restricted"


@dataclass(frozen=True)
class ModelProfile:
    profile_id: str
    adapter: str
    endpoint: str
    model_id: str
    capabilities: frozenset[str]
    privacy_zone: PrivacyZone
    revision: str
    secret_ref: str | None = None
    fallback: tuple[str, ...] = ()
    params: dict[str, Any] = field(default_factory=dict)
    # Provider approval and health are persisted beside the profile.  Defaults
    # keep the value safe for callers that construct profiles in memory.
    provider_approved: bool = False
    health: str = "unknown"
    # Prices per million tokens and spending caps (G1.0, ADR-007).  ``None`` = not set.
    input_price_per_mtok: float | None = None
    output_price_per_mtok: float | None = None
    daily_cost_limit: float | None = None
    monthly_cost_limit: float | None = None


def profile_fingerprint(profile: ModelProfile) -> str:
    """Identify the model configuration independently of a mutable profile label."""
    payload = {
        "profile_id": profile.profile_id,
        "adapter": profile.adapter,
        "endpoint": profile.endpoint,
        "model_id": profile.model_id,
        "revision": profile.revision,
        "params": profile.params,
        "capabilities": sorted(profile.capabilities),
        "privacy_zone": profile.privacy_zone,
        "secret_ref": profile.secret_ref,
    }
    return sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
