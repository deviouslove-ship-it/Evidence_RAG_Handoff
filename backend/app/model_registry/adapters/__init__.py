"""Minimal model adapters."""

from .base import AdapterBudget
from .ollama_local import OllamaLocalAdapter
from .openai_compatible import AdapterError, OpenAICompatibleAdapter

__all__ = [
    "AdapterBudget",
    "AdapterError",
    "OllamaLocalAdapter",
    "OpenAICompatibleAdapter",
]
