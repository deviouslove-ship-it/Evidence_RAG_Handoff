"""Model Registry stages and their configurable call policy.

Every model use is a stage with its own route per operating mode.  A stage that the
pipeline does not call yet can already be configured; the Admin Portal marks it as
"not used yet" so nobody expects it to change results.
"""

from __future__ import annotations

from dataclasses import dataclass

# Order = order shown to administrators.
STAGES: tuple[str, ...] = (
    "answer", "summarize", "expand", "relation", "label", "ocr", "embedding", "rerank",
)
# Stages the application calls (G1–G4 wired every stage).
ACTIVE_STAGES: frozenset[str] = frozenset(STAGES)
# Stages whose result is checked by code, so a local result that fails the check
# may be retried once on the API escalation profile (Hybrid Auto, API mode only).
ESCALATION_STAGES: frozenset[str] = frozenset({"answer", "summarize"})
# Design §8 & OCR AI v1: embeddings, reranking, and OCR always run on a local model.
LOCAL_ONLY_STAGES: frozenset[str] = frozenset({"embedding", "rerank", "ocr"})

# Text-generation stages: one profile may serve several of them (embedding and ocr
# each have dedicated roles and constraints).
GENERATION_STAGES: tuple[str, ...] = tuple(
    stage for stage in STAGES if stage not in {"embedding", "ocr"}
)

MAX_STAGE_ATTEMPTS = 10
OCR_DEFAULT_TIMEOUT_SECONDS = 180.0
OCR_MAX_TIMEOUT_SECONDS = 300.0
OCR_MAX_OUTPUT_TOKENS = 8_192


@dataclass(frozen=True)
class StagePolicy:
    """Limits for one (mode, stage).  ``None`` means "use the server default"."""

    max_attempts: int
    max_output_tokens: int | None = None
    timeout_seconds: float | None = None
    max_concurrency: int | None = None
    stage: str = "answer"

    def __post_init__(self) -> None:
        if not 1 <= self.max_attempts <= MAX_STAGE_ATTEMPTS:
            raise ValueError("stage attempts must be between 1 and 10")
        if self.stage == "ocr" and self.max_attempts != 1:
            raise ValueError("ocr stage allows only 1 attempt per task")
        if self.max_output_tokens is not None and not 1 <= self.max_output_tokens <= 16_384:
            raise ValueError("stage output tokens out of range")
        max_timeout = OCR_MAX_TIMEOUT_SECONDS if self.stage == "ocr" else 30.0
        if self.timeout_seconds is not None and not 0 < self.timeout_seconds <= max_timeout:
            raise ValueError(
                f"stage timeout must be between 0 and {int(max_timeout)} seconds"
            )
        if self.max_concurrency is not None and not 1 <= self.max_concurrency <= 64:
            raise ValueError("stage concurrency must be between 1 and 64")
