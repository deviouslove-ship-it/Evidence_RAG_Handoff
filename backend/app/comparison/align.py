"""Deterministic node alignment (C1).

Three tiers in decreasing priority: explicit amendment links, structural keys, then
semantic/lexical matching.  Pure Python: no DB, no LLM, no network.  ACL enforcement is
the caller's job (C2 service); this module only aligns the nodes it is given.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal
from uuid import UUID

from ..analysis.signals import LogicalNode, extract_normative_signals, normalize_structural_key

AlignmentMethod = Literal["explicit_amendment", "structural_key", "semantic_lexical"]
CompareMode = Literal["versions", "amendment_pair", "cross_document"]

# Tier-2 renumber guard: a same-key pair whose content similarity is below LOW while the
# left node matches another right node at >= HIGH is left for tier 3 (inserted article).
RENUMBER_LOW_SIMILARITY = 0.12
RENUMBER_HIGH_SIMILARITY = 0.65
# Tier-3 acceptance thresholds and scoring weights (brief, verbatim).
TIER3_THRESHOLD_VERSIONS = 0.42
TIER3_THRESHOLD_CROSS_DOCUMENT = 0.52
COSINE_WEIGHT = 0.55
LEXICAL_WEIGHT = 0.45
# Added to the lexical score when both nodes are headings and no embeddings are used
# (value chosen by C1; the brief leaves it open).  Scores are capped at 1.0.
HEADING_BONUS = 0.15


@dataclass(frozen=True)
class AmendmentLink:
    """One approved ``node_amendments`` row connecting two aligned nodes.

    ``source_node_id`` may be any member of a stitched logical node (including a
    ``tiep:N`` segment).  When ``direction == "left_to_right"`` (default), the
    source is resolved in ``left`` and the target in ``right``; when
    ``direction == "right_to_left"``, the source is resolved in ``right`` and the
    target in ``left``.  Targets resolve by ``target_node_id`` first, then by
    normalized ``target_path``.  ``action`` is the stored amendment action
    (modify/replace/add/repeal/repeal_partial/suspend/commence).
    """

    source_node_id: UUID
    target_node_id: UUID | None = None
    target_path: str | None = None
    action: str = "modify"
    valid_from: date | None = None
    source_quote: str | None = None
    direction: Literal["left_to_right", "right_to_left"] = "left_to_right"


@dataclass(frozen=True)
class AlignedPair:
    """One alignment result row in natural reading order.

    ``left``/``right``: exactly one is None for removed/added nodes.
    ``alignment_method`` is None for unpaired (added/removed) nodes.
    ``score`` carries the tier-2 content similarity or the tier-3 combined score;
    it is None for explicit links and unpaired nodes.
    """

    left: LogicalNode | None
    right: LogicalNode | None
    alignment_method: AlignmentMethod | None
    score: float | None = None
    amendment_action: str | None = None
    valid_from: date | None = None
    source_quote: str | None = None


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    # Same formula as storage.embeddings.cosine; kept local so the comparison engine
    # does not import the storage package (which pulls in the DB pool at import time).
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return dot / norm if norm else 0.0


def _lexical_tokens(node: LogicalNode) -> frozenset[str]:
    signals = extract_normative_signals(node.text_original)
    return signals.subject_tokens | signals.plain_numbers


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _pair_score(
    left: LogicalNode,
    right: LogicalNode,
    left_tokens: frozenset[str],
    right_tokens: frozenset[str],
) -> float:
    jaccard = _jaccard(left_tokens, right_tokens)
    if left.embedding and right.embedding and len(left.embedding) == len(right.embedding):
        return COSINE_WEIGHT * _cosine(left.embedding, right.embedding) + LEXICAL_WEIGHT * jaccard
    score = jaccard
    if left.node_type == "heading" and right.node_type == "heading":
        score += HEADING_BONUS
    return min(score, 1.0)


def align_nodes(
    left_nodes: Sequence[LogicalNode],
    right_nodes: Sequence[LogicalNode],
    amendment_links: Sequence[AmendmentLink] = (),
    mode: CompareMode = "versions",
) -> list[AlignedPair]:
    """Align two node lists; returns pairs in reading order (A order, B additions in place).

    Tier 1 pairs nodes joined by an approved amendment link.  Tier 2 matches equal
    ``dieu:`` structural keys 1-1; in ``versions``/``cross_document`` mode a same-key pair
    with similarity < 0.12 is deferred to tier 3 when the left node matches another right
    node at >= 0.65 (renumbering by an inserted article).  Tier 3 greedily matches the
    remaining nodes on 0.55*cosine + 0.45*lexical jaccard (lexical + heading bonus without
    embeddings), accepting scores >= 0.42 (versions/amendment_pair) or >= 0.52
    (cross_document).  Leftovers become removed/added pairs.
    """

    left = sorted(left_nodes, key=lambda node: node.ordinal)
    right = sorted(right_nodes, key=lambda node: node.ordinal)
    tokens = {node.primary_node_id: _lexical_tokens(node) for node in (*left, *right)}

    def score_of(a: LogicalNode, b: LogicalNode) -> float:
        return _pair_score(a, b, tokens[a.primary_node_id], tokens[b.primary_node_id])

    left_members: dict[UUID, LogicalNode] = {}
    for node in left:
        for member in node.member_node_ids:
            left_members.setdefault(member, node)
    right_members: dict[UUID, LogicalNode] = {}
    for node in right:
        for member in node.member_node_ids:
            right_members.setdefault(member, node)

    used_left: set[UUID] = set()
    used_right: set[UUID] = set()
    pairs: list[AlignedPair] = []

    # Tier 1: explicit amendment links.
    def resolve_target(
        link: AmendmentLink,
        target_members: dict[UUID, LogicalNode],
        target_nodes: list[LogicalNode],
        used_target: set[UUID],
    ) -> LogicalNode | None:
        target = (
            target_members.get(link.target_node_id)
            if link.target_node_id is not None
            else None
        )
        if target is None and link.target_path:
            key = normalize_structural_key(link.target_path)
            if key:
                target = next(
                    (
                        node
                        for node in target_nodes
                        if node.primary_node_id not in used_target and node.structural_key == key
                    ),
                    None,
                )
        if target is None or target.primary_node_id in used_target:
            return None
        return target

    for link in amendment_links:
        if link.direction == "right_to_left":
            src_members, used_src = right_members, used_right
            tgt_members, tgt_nodes, used_tgt = left_members, left, used_left
        else:
            src_members, used_src = left_members, used_left
            tgt_members, tgt_nodes, used_tgt = right_members, right, used_right
        src = src_members.get(link.source_node_id)
        if src is None or src.primary_node_id in used_src:
            continue
        tgt = resolve_target(link, tgt_members, tgt_nodes, used_tgt)
        if tgt is None:
            continue
        pair_left, pair_right = (tgt, src) if link.direction == "right_to_left" else (src, tgt)
        pairs.append(AlignedPair(
            left=pair_left, right=pair_right, alignment_method="explicit_amendment",
            amendment_action=link.action, valid_from=link.valid_from,
            source_quote=link.source_quote,
        ))
        used_left.add(pair_left.primary_node_id)
        used_right.add(pair_right.primary_node_id)

    # Tier 2: equal dieu structural keys, with the renumber guard.
    for a in left:
        if a.primary_node_id in used_left or not a.structural_key.startswith("dieu:"):
            continue
        b = next(
            (node for node in right
             if node.primary_node_id not in used_right and node.structural_key == a.structural_key),
            None,
        )
        if b is None:
            continue
        similarity = score_of(a, b)
        if (
            mode in ("versions", "cross_document")
            and similarity < RENUMBER_LOW_SIMILARITY
            and any(
                score_of(a, other) >= RENUMBER_HIGH_SIMILARITY
                for other in right
                if other.primary_node_id not in used_right and other is not b
            )
        ):
            continue  # likely renumbered: let tier 3 find the real counterpart
        pairs.append(AlignedPair(left=a, right=b, alignment_method="structural_key",
                                 score=similarity))
        used_left.add(a.primary_node_id)
        used_right.add(b.primary_node_id)

    # Tier 3: greedy best-score matching over the remaining nodes.
    threshold = (
        TIER3_THRESHOLD_CROSS_DOCUMENT if mode == "cross_document" else TIER3_THRESHOLD_VERSIONS
    )
    candidates: list[tuple[float, int, int, LogicalNode, LogicalNode]] = []
    for a in left:
        if a.primary_node_id in used_left:
            continue
        for b in right:
            if b.primary_node_id in used_right:
                continue
            value = score_of(a, b)
            if value >= threshold:
                candidates.append((-value, a.ordinal, b.ordinal, a, b))
    candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    for negative, _, _, a, b in candidates:
        if a.primary_node_id in used_left or b.primary_node_id in used_right:
            continue
        pairs.append(AlignedPair(left=a, right=b, alignment_method="semantic_lexical",
                                 score=-negative))
        used_left.add(a.primary_node_id)
        used_right.add(b.primary_node_id)

    # Leftovers: removed (A only) and added (B only).
    for a in left:
        if a.primary_node_id not in used_left:
            pairs.append(AlignedPair(left=a, right=None, alignment_method=None))
    added = [b for b in right if b.primary_node_id not in used_right]
    for b in added:
        pairs.append(AlignedPair(left=None, right=b, alignment_method=None))

    return _reading_order(pairs, left, right, used_right)


def _reading_order(
    pairs: list[AlignedPair],
    left: list[LogicalNode],
    right: list[LogicalNode],
    used_right: set[UUID],
) -> list[AlignedPair]:
    """A's ordinal order, with B-only additions inserted next to their matched neighbors."""

    by_left = {pair.left.primary_node_id: pair for pair in pairs if pair.left is not None}
    ordered = [by_left[node.primary_node_id] for node in left]
    for pair in (p for p in pairs if p.left is None and p.right is not None):
        added = pair.right
        assert added is not None
        predecessor: LogicalNode | None = None
        successor: LogicalNode | None = None
        for other in right:
            if other.primary_node_id not in used_right:
                continue
            if other.ordinal < added.ordinal:
                predecessor = other
            elif successor is None:
                successor = other
        if predecessor is not None:
            index = _position_of(ordered, predecessor.primary_node_id) + 1
            # Keep earlier additions anchored to the same predecessor before this one.
            while index < len(ordered):
                following = ordered[index]
                if following.left is not None or following.right is None:
                    break
                if following.right.ordinal >= added.ordinal:
                    break
                index += 1
        elif successor is not None:
            index = _position_of(ordered, successor.primary_node_id)
        else:
            index = len(ordered)
        ordered.insert(index, pair)
    return ordered


def _position_of(ordered: list[AlignedPair], right_id: UUID) -> int:
    return next(
        index for index, pair in enumerate(ordered)
        if pair.right is not None and pair.right.primary_node_id == right_id
    )
