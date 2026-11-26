"""Deterministic document comparison engine: alignment and token diff (C1)."""

from .align import AlignedPair, AmendmentLink, align_nodes
from .diff import ChangeSignals, DiffSegment, NodeDiff, compute_token_diff, diff_pair

__all__ = [
    "AlignedPair",
    "AmendmentLink",
    "ChangeSignals",
    "DiffSegment",
    "NodeDiff",
    "align_nodes",
    "compute_token_diff",
    "diff_pair",
]
