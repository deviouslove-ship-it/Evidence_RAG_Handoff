"""Minimal model adapters."""

from .base import AdapterBudget
from .openai_compatible import AdapterError, OpenAICompatibleAdapter

__all__ = [
    "AdapterBudget",
    "AdapterError",
    "OpenAICompatibleAdapter",
]
