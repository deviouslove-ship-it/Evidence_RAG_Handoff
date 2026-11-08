"""Node-level amendment chain resolution.

This module resolves verified graph edges only.  It does not infer effectivity
from a document date and it never silently truncates a chain.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class AmendmentEdge:
    source: str
    target: str
    action: str
    effective_from: date
    effective_to: date | None = None
    verified: bool = True


@dataclass(frozen=True)
class EffectivityResult:
    node_id: str
    status: str
    resolved_node_id: str | None
    chain: tuple[str, ...]
    reasons: tuple[str, ...]


def resolve_amendment_chain(
    node_id: str,
    edges: Mapping[str, tuple[AmendmentEdge, ...]],
    as_of_date: date,
    max_nodes: int = 10_000,
) -> EffectivityResult:
    """Resolve a verified chain to a fixed point.

    Missing, cyclic, conflicting, or over-budget graphs fail closed as
    `unknown` rather than returning an unverified effective status.
    """

    visited: set[str] = set()
    path: list[str] = []
    reasons: list[str] = []

    def visit(current: str) -> str:
        if current in visited:
            reasons.append("cycle_detected")
            return "unknown"
        if len(visited) > max_nodes:
            reasons.append("resource_guard_exceeded")
            return "unknown"
        visited.add(current)
        path.append(current)
        candidates = [
            edge
            for edge in edges.get(current, ())
            if edge.verified
            and edge.effective_from <= as_of_date
            and (edge.effective_to is None or as_of_date < edge.effective_to)
        ]
        if not candidates:
            return "active"
        actions = {edge.action for edge in candidates}
        if len(actions) > 1 or len(candidates) > 1:
            reasons.append("conflicting_edges")
            return "unknown"
        edge = candidates[0]
        child_status = visit(edge.target)
        if child_status == "unknown":
            return "unknown"
        if edge.action in {"repeal", "suspend"}:
            return edge.action
        if edge.action in {"modify", "replace", "add"}:
            return "modified"
        return child_status

    status = visit(node_id)
    if status == "unknown" and not reasons:
        reasons.append("unverified_chain")
    return EffectivityResult(
        node_id=node_id,
        status=status,
        resolved_node_id=path[-1] if status != "unknown" else None,
        chain=tuple(path),
        reasons=tuple(dict.fromkeys(reasons)),
    )
