"""Model Registry stages and their configurable call policy.

Every model use is a stage with its own route per operating mode.  A stage that the
pipeline does not call yet can already be configured; the Admin Portal marks it as
"not used yet" so nobody expects it to change results.
"""

from __future__ import annotations

from dataclasses import dataclass

# Order = order shown to administrators.
STAGES: tuple[str, ...] = (
    "answer", "summarize", "expand", "relation", "label", "embedding", "rerank",
)
# Stages the application calls (G1–G4 wired every stage).
ACTIVE_STAGES: frozenset[str] = frozenset(STAGES)
# Stages whose result is checked by code, so a local result that fails the check
# may be retried once on the API escalation profile (Hybrid Auto, API mode only).
ESCALATION_STAGES: frozenset[str] = frozenset({"answer", "summarize"})
# Design §8: embeddings and reranking always run on a local model, in both modes.
LOCAL_ONLY_STAGES: frozenset[str] = frozenset({"embedding", "rerank"})

# Text-generation stages: one profile may serve several of them (an embedding profile
# serves only "embedding", because a vector index belongs to exactly one model).
GENERATION_STAGES: tuple[str, ...] = tuple(stage for stage in STAGES if stage != "embedding")

MAX_STAGE_ATTEMPTS = 10


@dataclass(frozen=True)
class StagePolicy:
    """Limits for one (mode, stage).  ``None`` means "use the server default"."""

    max_attempts: int
    max_output_tokens: int | None = None
    timeout_seconds: float | None = None
    max_concurrency: int | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.max_attempts <= MAX_STAGE_ATTEMPTS:
            raise ValueError("stage attempts must be between 1 and 10")
        if self.max_output_tokens is not None and not 1 <= self.max_output_tokens <= 16_384:
            raise ValueError("stage output tokens out of range")
        if self.timeout_seconds is not None and not 0 < self.timeout_seconds <= 30:
            raise ValueError("stage timeout must be between 0 and 30 seconds")
        if self.max_concurrency is not None and not 1 <= self.max_concurrency <= 64:
            raise ValueError("stage concurrency must be between 1 and 64")
