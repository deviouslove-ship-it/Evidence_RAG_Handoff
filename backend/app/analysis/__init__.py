"""Shared normative-signal extraction for comparison and conflict review (C1)."""

from .signals import (
    DeadlineSpan,
    LogicalNode,
    NodeRecord,
    NormativeSignals,
    QuantitySpan,
    extract_normative_signals,
    normalize_structural_key,
    stitch_logical_nodes,
)

__all__ = [
    "DeadlineSpan",
    "LogicalNode",
    "NodeRecord",
    "NormativeSignals",
    "QuantitySpan",
    "extract_normative_signals",
    "normalize_structural_key",
    "stitch_logical_nodes",
]
