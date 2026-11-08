"""Model profile types.  Values are configuration, never source defaults."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
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
