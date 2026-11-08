"""The shared LLM attempt budget."""

from __future__ import annotations

from dataclasses import dataclass

from ..stages import MAX_STAGE_ATTEMPTS


@dataclass
class AdapterBudget:
    """Counts every HTTP send, including timeouts, errors and fallbacks.

    The limit comes from the stage policy an administrator configures (ADR-007);
    it is bounded so a misconfiguration cannot turn a request into a loop.
    """

    limit: int = 2
    used: int = 0

    def __post_init__(self) -> None:
        if self.limit < 0 or self.limit > MAX_STAGE_ATTEMPTS:
            raise ValueError(f"LLM attempt budget must be at most {MAX_STAGE_ATTEMPTS}")
        if self.used < 0 or self.used > self.limit:
            raise ValueError("used attempts must be within the budget")

    def consume(self) -> None:
        if self.used >= self.limit:
            raise RuntimeError("LLM_BUDGET_EXHAUSTED")
        self.used += 1
