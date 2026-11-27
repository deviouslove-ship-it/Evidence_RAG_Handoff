"""Deterministic cross-document candidate pairing & conflict signal detector (Phase 2, D3).

Pure-Python candidate pairing, normative signal comparison, and deterministic
classification for ``contradiction``, ``overlap``, ``exception_refinement``, and
``superseded_already`` findings.  Also provides an optional async pgvector helper
``fetch_pgvector_candidate_similarities`` for Channel 2 when PostgreSQL embeddings exist;
when embeddings are unavailable it smoothly falls back to Channel 1 + lexical bigrams.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal
from uuid import UUID

from app.analysis.signals import (
    DeadlineSpan,
    LogicalNode,
    NodeRecord,
    NormativeSignals,
    QuantitySpan,
    extract_normative_signals,
    normalize_structural_key,
    stitch_logical_nodes,
)
from app.conflicts.precedence import (
    INACTIVE_STATUSES,
    _normalize_status,
    normalize_issuing_authority,
)
from app.schemas import AmendmentStatus
from app.storage.embeddings import EmbeddingIndexError, active_index, vector_type
from app.synthesis.checks import _DOC_NUMBER, _bigrams, _content, _fold_words
from app.vietnamese_nlp.unicode_norm import canonical_document_number, normalize_text

FindingType = Literal[
    "contradiction",
    "overlap",
    "exception_refinement",
    "superseded_already",
]
Severity = Literal["high", "medium", "low"]

MIN_STRUCTURAL_HEADING_CHARS = 40
STRUCTURAL_HEADING_TYPES: frozenset[str] = frozenset(
    {"part", "chapter", "section", "heading"}
)
EXCLUDED_INACTIVE_STATUSES: frozenset[str] = frozenset(
    {
        AmendmentStatus.REPEALED.value,
        AmendmentStatus.REPLACED.value,
        AmendmentStatus.NOT_YET_EFFECTIVE.value,
    }
)

TAXONOMY_SUBJECT_OVERLAP_THRESHOLD = 0.22
SEMANTIC_SIMILARITY_THRESHOLD = 0.72
OVERLAP_SIMILARITY_THRESHOLD = 0.84
OVERLAP_LEXICAL_THRESHOLD = 0.55
LEXICAL_FALLBACK_SUBJECT_THRESHOLD = 0.30
LEXICAL_FALLBACK_BIGRAM_THRESHOLD = 0.18

DIVERGENCE_SUBJECT_OVERLAP_THRESHOLD = 0.28
AUTHORITY_SUBJECT_OVERLAP_THRESHOLD = 0.25

DEFAULT_MAX_PAIRS = 120
DEFAULT_MAX_PAIRS_PER_NODE = 3

_MONEY_MULTIPLIERS: dict[str, float] = {
    "dong": 1.0,
    "trieu_dong": 1_000_000.0,
    "ty_dong": 1_000_000_000.0,
}

_AUTHORITY_VERBS_RE = re.compile(
    r"\b(?:quyet dinh|cap|phe duyet|tham dinh|thu hoi|kiem tra|ban hanh|thanh tra)\b"
)

_FIXED_AUTHORITY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:uy ban thuong vu quoc hoi|ubtvqh)\b"),
    re.compile(r"(?<!uy ban thuong vu )\bquoc hoi\b"),
    re.compile(r"\bchu tich nuoc\b"),
    re.compile(r"\bthu tuong(?:\s+chinh phu)?\b"),
    re.compile(r"(?<!thu tuong )\bchinh phu\b"),
    re.compile(
        r"\b(?:chu tich\s+)?(?:uy ban nhan dan|ubnd)"
        r"(?:\s+(?:cap\s+)?(?:tinh|thanh pho|huyen|quan|thi xa|xa|phuong|thi tran))?\b"
    ),
    re.compile(
        r"\b(?:hoi dong nhan dan|hdnd)"
        r"(?:\s+(?:cap\s+)?(?:tinh|thanh pho|huyen|quan|thi xa|xa|phuong|thi tran))?\b"
    ),
    re.compile(r"\bngan hang nha nuoc\b"),
)

_AGENCY_TITLE_RE = re.compile(
    r"(?:(?:Bộ\s+trưởng\s+)?Bộ|(?:Giám\s+đốc\s+)?Sở|(?:Tổng\s+)?Cục|Chi\s+cục)\s+"
    r"[A-ZĐÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴ]"
    r"[A-Za-zÀ-ỹĐđ0-9\s\-–&,]{1,80}"
)
_AGENCY_STOP_SPLIT_RE = re.compile(
    r"(?<!\w)(?:"
    r"quyết định|cấp|phê duyệt|thẩm định|thu hồi|kiểm tra|ban hành|thanh tra|"
    r"thực hiện|quy định|hướng dẫn|có trách nhiệm|chủ trì|phối hợp|báo cáo|"
    r"tổ chức|xem xét|giải quyết|tiếp nhận|quản lý|nộp|gửi|tại|theo|của|"
    r"cho|đối với|là|phải|được|không|trên|trong|về|và các|hoặc"
    r")(?!\w)"
)


@dataclass(frozen=True)
class DocumentNodesInput:
    """Raw ordered ``NodeRecord`` rows of one document entering conflict screening."""

    document_id: UUID
    records: Sequence[NodeRecord]
    effective_status_at_date: AmendmentStatus | str = AmendmentStatus.UNKNOWN
    document_number: str | None = None


@dataclass(frozen=True)
class ScopedLogicalNode:
    """One stitched normative node eligible for cross-document conflict pairing."""

    document_id: UUID
    node: LogicalNode
    effective_status_at_date: str = AmendmentStatus.UNKNOWN.value
    document_number: str | None = None


@dataclass(frozen=True)
class ApprovedNodeAmendment:
    """One approved ``node_amendments`` relation between nodes or document paths."""

    source_document_id: UUID
    target_document_id: UUID | None
    source_node_id: UUID
    target_node_id: UUID | None = None
    target_path: str | None = None
    action: str = "modify"
    amendment_id: UUID | None = None
    valid_from: date | None = None
    approved: bool = True


@dataclass(frozen=True)
class ApprovedNodeReference:
    """One verified/resolved ``node_references`` relation linking clauses or documents."""

    source_node_id: UUID
    target_node_id: UUID | None = None
    target_document_id: UUID | None = None
    target_expression: str = ""
    verified: bool = True


@dataclass(frozen=True)
class CandidatePair:
    """One cross-document candidate node pair in canonical ``node_a < node_b`` order."""

    node_a: ScopedLogicalNode
    node_b: ScopedLogicalNode
    shared_labels: tuple[str, ...]
    subject_overlap: float
    lexical_bigram: float
    similarity_score: float | None
    channels: tuple[str, ...]
    priority_score: float


@dataclass(frozen=True)
class ConflictCandidateFinding:
    """Deterministic conflict/overlap/refinement finding ready for worker persistence."""

    document_a_id: UUID
    document_b_id: UUID
    node_a_id: UUID
    node_b_id: UUID
    finding_type: FindingType
    severity: Severity
    similarity_score: float | None
    shared_labels: tuple[str, ...]
    signals_json: dict[str, Any]
    explanation: str


def filter_normative_nodes(
    documents: Sequence[DocumentNodesInput],
    *,
    include_expired: bool = False,
) -> list[ScopedLogicalNode]:
    """Stitch ``tiep:N`` segments, drop short structural headings, and filter inactive docs.

    When ``include_expired=False`` (default), documents whose ``effective_status_at_date``
    is in ``{"repealed", "replaced", "not_yet_effective"}`` are excluded (Ruling P3),
    while ``active``, ``modified``, ``suspended``, and ``unknown`` are retained.
    """

    scoped: list[ScopedLogicalNode] = []
    for doc in documents:
        status = _normalize_status(doc.effective_status_at_date)
        if not include_expired and status in EXCLUDED_INACTIVE_STATUSES:
            continue
        for logical in stitch_logical_nodes(doc.records):
            stripped = logical.text_original.strip()
            if not stripped:
                continue
            if (
                logical.node_type.strip().lower() in STRUCTURAL_HEADING_TYPES
                and len(stripped) < MIN_STRUCTURAL_HEADING_CHARS
            ):
                continue
            scoped.append(
                ScopedLogicalNode(
                    document_id=doc.document_id,
                    node=logical,
                    effective_status_at_date=status,
                    document_number=doc.document_number,
                )
            )
    return scoped


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return dot / norm if norm else 0.0


def _jaccard(
    left: frozenset[str] | set[tuple[str, str]],
    right: frozenset[str] | set[tuple[str, str]],
) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _canonical_pair_key(id_a: UUID, id_b: UUID) -> tuple[UUID, UUID]:
    return (id_a, id_b) if id_a < id_b else (id_b, id_a)


async def fetch_pgvector_candidate_similarities(
    connection: Any,
    scoped_node_ids: Sequence[UUID],
    *,
    min_similarity: float = SEMANTIC_SIMILARITY_THRESHOLD,
    limit: int = 1000,
) -> dict[tuple[UUID, UUID], float]:
    """Query pgvector cosine similarities on the active ready embedding index (Ruling P7).

    Returns canonical ``(min_node_id, max_node_id) -> similarity`` pairs restricted to
    ``scoped_node_ids`` and cross-document pairs (``n1.document_id <> n2.document_id``).
    Returns ``{}`` cleanly when fewer than 2 nodes are scoped or no active index exists.
    """

    unique_ids = list(dict.fromkeys(scoped_node_ids))
    if len(unique_ids) < 2:
        return {}
    index = await active_index(connection)
    if index is None:
        return {}
    dimensions = int(index["dimensions"])
    try:
        cast = f"{vector_type(dimensions)}({dimensions})"
    except EmbeddingIndexError:
        return {}
    index_id = UUID(str(index["id"]))
    rows = await connection.fetch(
        f"""SELECT LEAST(e1.document_node_id, e2.document_node_id) AS node_a_id,
                   GREATEST(e1.document_node_id, e2.document_node_id) AS node_b_id,
                   1 - (e1.embedding::{cast} <=> e2.embedding::{cast}) AS similarity
            FROM node_embeddings e1
            JOIN embedding_indices ei
              ON ei.id = e1.embedding_index_id
             AND ei.is_active = TRUE
             AND ei.status = 'ready'
            JOIN node_embeddings e2
              ON e2.embedding_index_id = e1.embedding_index_id
            JOIN document_nodes n1 ON n1.id = e1.document_node_id
            JOIN document_nodes n2 ON n2.id = e2.document_node_id
            WHERE e1.embedding_index_id = $1
              AND e1.document_node_id = ANY($2::uuid[])
              AND e2.document_node_id = ANY($2::uuid[])
              AND e1.document_node_id < e2.document_node_id
              AND n1.document_id <> n2.document_id
              AND 1 - (e1.embedding::{cast} <=> e2.embedding::{cast}) >= $3
            ORDER BY similarity DESC
            LIMIT $4""",
        index_id,
        unique_ids,
        min_similarity,
        max(1, limit),
    )
    similarities: dict[tuple[UUID, UUID], float] = {}
    for row in rows:
        key = _canonical_pair_key(row["node_a_id"], row["node_b_id"])
        similarities[key] = round(float(row["similarity"]), 4)
    return similarities


def _pair_similarity(
    left: LogicalNode,
    right: LogicalNode,
    vector_similarities: Mapping[tuple[UUID, UUID], float] | None,
) -> float | None:
    if vector_similarities is not None:
        key = _canonical_pair_key(left.primary_node_id, right.primary_node_id)
        if key in vector_similarities:
            return round(float(vector_similarities[key]), 4)
    if (
        left.embedding is not None
        and right.embedding is not None
        and len(left.embedding) == len(right.embedding)
        and len(left.embedding) > 0
    ):
        return round(_cosine(left.embedding, right.embedding), 4)
    return None


def generate_candidate_pairs(
    scoped_nodes: Sequence[ScopedLogicalNode],
    *,
    vector_similarities: Mapping[tuple[UUID, UUID], float] | None = None,
    max_pairs: int = DEFAULT_MAX_PAIRS,
    max_pairs_per_node: int = DEFAULT_MAX_PAIRS_PER_NODE,
) -> list[CandidatePair]:
    """Generate bounded, deduplicated cross-document candidate pairs (Channel 1 + Channel 2).

    Enforces ``doc_a != doc_b``, canonical ``node_a_id < node_b_id`` ordering, descending
    priority sorting, per-node degree cap ``<= max_pairs_per_node``, and total cap
    ``<= max_pairs``.  Falls back cleanly to Channel 1 + lexical bigrams when vector
    embeddings are absent.
    """

    if max_pairs <= 0 or max_pairs_per_node <= 0 or len(scoped_nodes) < 2:
        return []

    tokens_by_id: dict[UUID, frozenset[str]] = {}
    bigrams_by_id: dict[UUID, set[tuple[str, str]]] = {}
    labels_by_id: dict[UUID, set[str]] = {}
    for item in scoped_nodes:
        nid = item.node.primary_node_id
        content_words = _content(_fold_words(item.node.text_original))
        tokens_by_id[nid] = frozenset(content_words)
        bigrams_by_id[nid] = _bigrams(content_words)
        labels_by_id[nid] = set(item.node.taxonomy_codes)

    seen_keys: set[tuple[UUID, UUID]] = set()
    candidates: list[CandidatePair] = []

    for idx, first in enumerate(scoped_nodes):
        for second in scoped_nodes[idx + 1 :]:
            if first.document_id == second.document_id:
                continue
            if first.node.primary_node_id == second.node.primary_node_id:
                continue
            node_a, node_b = (
                (first, second)
                if first.node.primary_node_id < second.node.primary_node_id
                else (second, first)
            )
            key = (node_a.node.primary_node_id, node_b.node.primary_node_id)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            shared_labels = tuple(sorted(labels_by_id[key[0]] & labels_by_id[key[1]]))
            subject_overlap = round(_jaccard(tokens_by_id[key[0]], tokens_by_id[key[1]]), 4)
            lexical_bigram = round(_jaccard(bigrams_by_id[key[0]], bigrams_by_id[key[1]]), 4)
            similarity = _pair_similarity(node_a.node, node_b.node, vector_similarities)

            channels: list[str] = []
            if shared_labels and subject_overlap >= TAXONOMY_SUBJECT_OVERLAP_THRESHOLD:
                channels.append("taxonomy")
            if similarity is not None and similarity >= SEMANTIC_SIMILARITY_THRESHOLD:
                channels.append("vector")
            if (
                not channels
                and similarity is None
                and subject_overlap >= LEXICAL_FALLBACK_SUBJECT_THRESHOLD
                and lexical_bigram >= LEXICAL_FALLBACK_BIGRAM_THRESHOLD
            ):
                channels.append("lexical_fallback")

            if not channels:
                continue

            if similarity is not None:
                base_score = (
                    0.55 * max(0.0, similarity)
                    + 0.35 * subject_overlap
                    + (0.10 if shared_labels else 0.0)
                )
            else:
                base_score = (
                    0.65 * subject_overlap
                    + 0.25 * lexical_bigram
                    + (0.10 if shared_labels else 0.0)
                )
            dual_bonus = 0.08 if len(channels) > 1 else 0.0
            priority_score = round(min(1.0, base_score + dual_bonus), 4)

            candidates.append(
                CandidatePair(
                    node_a=node_a,
                    node_b=node_b,
                    shared_labels=shared_labels,
                    subject_overlap=subject_overlap,
                    lexical_bigram=lexical_bigram,
                    similarity_score=similarity,
                    channels=tuple(channels),
                    priority_score=priority_score,
                )
            )

    candidates.sort(
        key=lambda c: (
            -c.priority_score,
            c.node_a.node.primary_node_id,
            c.node_b.node.primary_node_id,
        )
    )

    selected: list[CandidatePair] = []
    degree: dict[UUID, int] = {}
    for candidate in candidates:
        if len(selected) >= max_pairs:
            break
        id_a = candidate.node_a.node.primary_node_id
        id_b = candidate.node_b.node.primary_node_id
        if degree.get(id_a, 0) >= max_pairs_per_node or degree.get(id_b, 0) >= max_pairs_per_node:
            continue
        selected.append(candidate)
        degree[id_a] = degree.get(id_a, 0) + 1
        degree[id_b] = degree.get(id_b, 0) + 1
    return selected


# ------------------------------------------------------------------ Signal checks


def _deadline_pair_comparable_values(
    da: DeadlineSpan, db: DeadlineSpan
) -> tuple[float, float] | None:
    """Convert two deadlines to a common scale if convertible, else return None."""

    ua, ub = da.unit_normalized, db.unit_normalized
    if ua == ub:
        return (da.value_num, db.value_num)
    pair = {ua, ub}
    if pair == {"gio", "ngay"}:
        va = da.value_num * (24.0 if ua == "ngay" else 1.0)
        vb = db.value_num * (24.0 if ub == "ngay" else 1.0)
        return (va, vb)
    if pair == {"thang", "nam"}:
        va = da.value_num * (12.0 if ua == "nam" else 1.0)
        vb = db.value_num * (12.0 if ub == "nam" else 1.0)
        return (va, vb)
    if pair == {"ngay", "thang"}:
        va = da.value_num * (30.0 if ua == "thang" else 1.0)
        vb = db.value_num * (30.0 if ub == "thang" else 1.0)
        return (va, vb)
    return None


def _has_deadline_divergence(sig_a: NormativeSignals, sig_b: NormativeSignals) -> bool:
    if not sig_a.deadlines or not sig_b.deadlines:
        return False

    # Same-unit comparison via normalized sets prevents false mismatches on multi-deadline clauses.
    by_unit_a: dict[str, set[float]] = {}
    by_unit_b: dict[str, set[float]] = {}
    for item in sig_a.deadlines:
        by_unit_a.setdefault(item.unit_normalized, set()).add(round(item.value_num, 6))
    for item in sig_b.deadlines:
        by_unit_b.setdefault(item.unit_normalized, set()).add(round(item.value_num, 6))

    for unit in set(by_unit_a) & set(by_unit_b):
        if by_unit_a[unit] != by_unit_b[unit]:
            return True

    # Cross-unit convertible calendar check when units differ (e.g. 1 tháng vs 15 ngày).
    for da in sig_a.deadlines:
        for db in sig_b.deadlines:
            if da.unit_normalized == db.unit_normalized:
                continue
            converted = _deadline_pair_comparable_values(da, db)
            if converted is None:
                continue
            va, vb = converted
            if abs(va - vb) > 1e-6:
                # Guard against another span on side B already matching da equivalently.
                if not any(
                    (eq := _deadline_pair_comparable_values(da, other_b)) is not None
                    and abs(eq[0] - eq[1]) <= 1e-6
                    for other_b in sig_b.deadlines
                ):
                    return True
    return False


def _quantity_family_and_value(span: QuantitySpan) -> tuple[str, float]:
    unit = span.unit_normalized
    if unit in _MONEY_MULTIPLIERS:
        return ("money", round(span.value_num * _MONEY_MULTIPLIERS[unit], 6))
    if unit == "percent":
        return ("percent", round(span.value_num, 6))
    return (f"count:{unit}", round(span.value_num, 6))


def _has_numeric_threshold_divergence(sig_a: NormativeSignals, sig_b: NormativeSignals) -> bool:
    if not sig_a.amounts_and_percents or not sig_b.amounts_and_percents:
        return False
    fam_a: dict[str, set[float]] = {}
    fam_b: dict[str, set[float]] = {}
    for span in sig_a.amounts_and_percents:
        family, value = _quantity_family_and_value(span)
        fam_a.setdefault(family, set()).add(value)
    for span in sig_b.amounts_and_percents:
        family, value = _quantity_family_and_value(span)
        fam_b.setdefault(family, set()).add(value)
    return any(fam_a[family] != fam_b[family] for family in set(fam_a) & set(fam_b))


def _has_deontic_polarity_conflict(sig_a: NormativeSignals, sig_b: NormativeSignals) -> bool:
    pol_a = sig_a.deontic_polarities
    pol_b = sig_b.deontic_polarities
    positive = {"permission", "obligation"}
    return (
        ("prohibition" in pol_a and "prohibition" not in pol_b and bool(pol_b & positive))
        or ("prohibition" in pol_b and "prohibition" not in pol_a and bool(pol_a & positive))
    )


def _extract_authority_phrases(node: LogicalNode) -> tuple[str, ...]:
    found: set[str] = set()
    for pattern in _FIXED_AUTHORITY_PATTERNS:
        for match in pattern.finditer(node.text_folded):
            norm = normalize_issuing_authority(match.group(0))
            if norm:
                found.add(norm)

    normalized_orig = normalize_text(node.text_original)
    for match in _AGENCY_TITLE_RE.finditer(normalized_orig):
        cut = _AGENCY_STOP_SPLIT_RE.split(match.group(0), maxsplit=1)[0]
        norm = normalize_issuing_authority(cut)
        if norm and len(norm.split()) >= 2:
            found.add(norm)
    return tuple(sorted(found))


def _has_authority_divergence(
    pair: CandidatePair,
) -> tuple[bool, tuple[str, ...], tuple[str, ...]]:
    auth_a = _extract_authority_phrases(pair.node_a.node)
    auth_b = _extract_authority_phrases(pair.node_b.node)
    if not auth_a or not auth_b or set(auth_a) == set(auth_b):
        return (False, auth_a, auth_b)

    has_authority_context = "tham_quyen_trach_nhiem" in pair.shared_labels or (
        bool(_AUTHORITY_VERBS_RE.search(pair.node_a.node.text_folded))
        and bool(_AUTHORITY_VERBS_RE.search(pair.node_b.node.text_folded))
    )
    return (has_authority_context, auth_a, auth_b)


def _matching_amendment_actions(
    pair: CandidatePair,
    approved_amendments: Sequence[ApprovedNodeAmendment],
) -> tuple[str, ...]:
    ids_a = set(pair.node_a.node.member_node_ids)
    ids_b = set(pair.node_b.node.member_node_ids)
    key_a = pair.node_a.node.structural_key
    key_b = pair.node_b.node.structural_key
    doc_a = pair.node_a.document_id
    doc_b = pair.node_b.document_id

    actions: list[str] = []
    for am in approved_amendments:
        if not am.approved:
            continue
        if am.source_node_id in ids_a:
            target_matches = (
                (am.target_node_id is not None and am.target_node_id in ids_b)
                or (
                    am.target_node_id is None
                    and am.target_document_id == doc_b
                    and (
                        am.target_path is None
                        or normalize_structural_key(am.target_path) == key_b
                    )
                )
            )
            if target_matches:
                actions.append(am.action.strip().lower())
        elif am.source_node_id in ids_b:
            target_matches = (
                (am.target_node_id is not None and am.target_node_id in ids_a)
                or (
                    am.target_node_id is None
                    and am.target_document_id == doc_a
                    and (
                        am.target_path is None
                        or normalize_structural_key(am.target_path) == key_a
                    )
                )
            )
            if target_matches:
                actions.append(am.action.strip().lower())
    return tuple(sorted(set(actions)))


def _has_cross_reference(
    pair: CandidatePair,
    approved_references: Sequence[ApprovedNodeReference],
) -> bool:
    ids_a = set(pair.node_a.node.member_node_ids)
    ids_b = set(pair.node_b.node.member_node_ids)
    doc_a = pair.node_a.document_id
    doc_b = pair.node_b.document_id

    for ref in approved_references:
        if not ref.verified:
            continue
        if ref.source_node_id in ids_a and (
            (ref.target_node_id is not None and ref.target_node_id in ids_b)
            or ref.target_document_id == doc_b
        ):
            return True
        if ref.source_node_id in ids_b and (
            (ref.target_node_id is not None and ref.target_node_id in ids_a)
            or ref.target_document_id == doc_a
        ):
            return True

    if pair.node_a.document_number:
        canon_a = canonical_document_number(pair.node_a.document_number)
        cited_in_b = {
            canonical_document_number(m)
            for m in _DOC_NUMBER.findall(pair.node_b.node.text_original)
        }
        if canon_a and canon_a in cited_in_b:
            return True
    if pair.node_b.document_number:
        canon_b = canonical_document_number(pair.node_b.document_number)
        cited_in_a = {
            canonical_document_number(m)
            for m in _DOC_NUMBER.findall(pair.node_a.node.text_original)
        }
        if canon_b and canon_b in cited_in_a:
            return True
    return False


def _serialize_deadlines(spans: tuple[DeadlineSpan, ...]) -> list[dict[str, Any]]:
    return [
        {"value_num": s.value_num, "unit": s.unit_normalized, "raw_text": s.raw_text}
        for s in spans
    ]


def _serialize_quantities(spans: tuple[QuantitySpan, ...]) -> list[dict[str, Any]]:
    return [
        {"value_num": s.value_num, "unit": s.unit_normalized, "raw_text": s.raw_text}
        for s in spans
    ]


def _build_explanation(
    finding_type: FindingType,
    signals: Sequence[str],
    *,
    amendment_actions: Sequence[str] = (),
    auth_a: Sequence[str] = (),
    auth_b: Sequence[str] = (),
) -> str:
    if finding_type == "superseded_already":
        acts = ", ".join(amendment_actions) or "modify"
        return (
            f"Cặp điều khoản đã có quan hệ sửa đổi/thay thế được phê duyệt ({acts}) "
            "— không phải mâu thuẫn mới."
        )
    if finding_type == "exception_refinement":
        return (
            "Hai điều khoản có điểm khác biệt nhưng tồn tại cụm ngoại lệ tường minh hoặc "
            "dẫn chiếu liên văn bản — gợi ý đây là quy định ngoại lệ/chi tiết hóa."
        )
    if finding_type == "overlap":
        return (
            "Hai văn bản cùng hiệu lực có nội dung tương đồng cao nhưng chưa có liên kết "
            "sửa đổi hoặc dẫn chiếu — cần rà soát nguy cơ trùng lặp/chồng chéo."
        )
    parts: list[str] = []
    if "deadline_divergence" in signals:
        parts.append("chênh lệch thời hạn")
    if "numeric_threshold_divergence" in signals:
        parts.append("chênh lệch ngưỡng số/tiền/tỷ lệ")
    if "deontic_polarity_conflict" in signals:
        parts.append("trái ngược tính chất bắt buộc/cấm/cho phép")
    if "authority_divergence" in signals:
        parts.append(
            f"khác cơ quan có thẩm quyền ({', '.join(auth_a)} vs {', '.join(auth_b)})"
        )
    detail = "; ".join(parts) if parts else "có tín hiệu xung đột quy phạm"
    return f"Phát hiện dấu hiệu mâu thuẫn quy phạm trên cùng chủ thể: {detail}."


def classify_candidate_pair(
    pair: CandidatePair,
    *,
    approved_amendments: Sequence[ApprovedNodeAmendment] = (),
    approved_references: Sequence[ApprovedNodeReference] = (),
) -> ConflictCandidateFinding | None:
    """Deterministically classify one candidate pair or return ``None`` if benign."""

    node_a = pair.node_a
    node_b = pair.node_b
    sig_a = extract_normative_signals(node_a.node.text_original)
    sig_b = extract_normative_signals(node_b.node.text_original)

    amendment_actions = _matching_amendment_actions(pair, approved_amendments)
    if amendment_actions:
        signals: tuple[str, ...] = ("superseded_by_approved_amendment",)
        return ConflictCandidateFinding(
            document_a_id=node_a.document_id,
            document_b_id=node_b.document_id,
            node_a_id=node_a.node.primary_node_id,
            node_b_id=node_b.node.primary_node_id,
            finding_type="superseded_already",
            severity="low",
            similarity_score=pair.similarity_score,
            shared_labels=pair.shared_labels,
            signals_json={
                "signals": list(signals),
                "channels": list(pair.channels),
                "subject_overlap": pair.subject_overlap,
                "lexical_bigram": pair.lexical_bigram,
                "amendment_actions": list(amendment_actions),
            },
            explanation=_build_explanation(
                "superseded_already", signals, amendment_actions=amendment_actions
            ),
        )

    divergence_signals: list[str] = []
    if pair.subject_overlap >= DIVERGENCE_SUBJECT_OVERLAP_THRESHOLD:
        if _has_deadline_divergence(sig_a, sig_b):
            divergence_signals.append("deadline_divergence")
        if _has_numeric_threshold_divergence(sig_a, sig_b):
            divergence_signals.append("numeric_threshold_divergence")
        if _has_deontic_polarity_conflict(sig_a, sig_b):
            divergence_signals.append("deontic_polarity_conflict")

    auth_a: tuple[str, ...] = ()
    auth_b: tuple[str, ...] = ()
    if pair.subject_overlap >= AUTHORITY_SUBJECT_OVERLAP_THRESHOLD:
        has_auth_div, auth_a, auth_b = _has_authority_divergence(pair)
        if has_auth_div:
            divergence_signals.append("authority_divergence")

    cross_ref_matched = _has_cross_reference(pair, approved_references)
    base_signals_json: dict[str, Any] = {
        "channels": list(pair.channels),
        "subject_overlap": pair.subject_overlap,
        "lexical_bigram": pair.lexical_bigram,
        "deadlines_a": _serialize_deadlines(sig_a.deadlines),
        "deadlines_b": _serialize_deadlines(sig_b.deadlines),
        "amounts_a": _serialize_quantities(sig_a.amounts_and_percents),
        "amounts_b": _serialize_quantities(sig_b.amounts_and_percents),
        "polarities_a": sorted(sig_a.deontic_polarities),
        "polarities_b": sorted(sig_b.deontic_polarities),
        "authorities_a": list(auth_a),
        "authorities_b": list(auth_b),
        "exception_phrases_a": list(sig_a.exception_phrases),
        "exception_phrases_b": list(sig_b.exception_phrases),
        "cross_reference_matched": cross_ref_matched,
    }

    if divergence_signals:
        if sig_a.has_exception or sig_b.has_exception or cross_ref_matched:
            all_signals = (*divergence_signals, "exception_qualification")
            base_signals_json["signals"] = list(all_signals)
            return ConflictCandidateFinding(
                document_a_id=node_a.document_id,
                document_b_id=node_b.document_id,
                node_a_id=node_a.node.primary_node_id,
                node_b_id=node_b.node.primary_node_id,
                finding_type="exception_refinement",
                severity="low",
                similarity_score=pair.similarity_score,
                shared_labels=pair.shared_labels,
                signals_json=base_signals_json,
                explanation=_build_explanation(
                    "exception_refinement", all_signals, auth_a=auth_a, auth_b=auth_b
                ),
            )

        high_signals = {
            "deadline_divergence",
            "numeric_threshold_divergence",
            "deontic_polarity_conflict",
        }
        severity: Severity = (
            "high" if any(s in high_signals for s in divergence_signals) else "medium"
        )
        all_signals = tuple(divergence_signals)
        base_signals_json["signals"] = list(all_signals)
        return ConflictCandidateFinding(
            document_a_id=node_a.document_id,
            document_b_id=node_b.document_id,
            node_a_id=node_a.node.primary_node_id,
            node_b_id=node_b.node.primary_node_id,
            finding_type="contradiction",
            severity=severity,
            similarity_score=pair.similarity_score,
            shared_labels=pair.shared_labels,
            signals_json=base_signals_json,
            explanation=_build_explanation(
                "contradiction", all_signals, auth_a=auth_a, auth_b=auth_b
            ),
        )

    co_effective = (
        node_a.effective_status_at_date not in INACTIVE_STATUSES
        and node_b.effective_status_at_date not in INACTIVE_STATUSES
    )
    high_overlap = (
        (
            pair.similarity_score is not None
            and pair.similarity_score >= OVERLAP_SIMILARITY_THRESHOLD
        )
        or pair.subject_overlap >= OVERLAP_LEXICAL_THRESHOLD
        or pair.lexical_bigram >= OVERLAP_LEXICAL_THRESHOLD
    )
    if co_effective and not cross_ref_matched and high_overlap:
        overlap_signals: tuple[str, ...] = ("scope_overlap_without_link",)
        base_signals_json["signals"] = list(overlap_signals)
        return ConflictCandidateFinding(
            document_a_id=node_a.document_id,
            document_b_id=node_b.document_id,
            node_a_id=node_a.node.primary_node_id,
            node_b_id=node_b.node.primary_node_id,
            finding_type="overlap",
            severity="medium",
            similarity_score=pair.similarity_score,
            shared_labels=pair.shared_labels,
            signals_json=base_signals_json,
            explanation=_build_explanation("overlap", overlap_signals),
        )

    return None


def detect_conflict_candidates(
    scoped_nodes: Sequence[ScopedLogicalNode],
    *,
    vector_similarities: Mapping[tuple[UUID, UUID], float] | None = None,
    approved_amendments: Sequence[ApprovedNodeAmendment] = (),
    approved_references: Sequence[ApprovedNodeReference] = (),
    max_pairs: int = DEFAULT_MAX_PAIRS,
    max_pairs_per_node: int = DEFAULT_MAX_PAIRS_PER_NODE,
) -> list[ConflictCandidateFinding]:
    """Run candidate pairing + deterministic signal classification over filtered nodes."""

    pairs = generate_candidate_pairs(
        scoped_nodes,
        vector_similarities=vector_similarities,
        max_pairs=max_pairs,
        max_pairs_per_node=max_pairs_per_node,
    )
    findings: list[ConflictCandidateFinding] = []
    for pair in pairs:
        finding = classify_candidate_pair(
            pair,
            approved_amendments=approved_amendments,
            approved_references=approved_references,
        )
        if finding is not None:
            findings.append(finding)
    return findings
