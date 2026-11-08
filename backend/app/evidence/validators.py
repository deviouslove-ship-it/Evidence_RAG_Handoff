"""Deterministic evidence and claim validation.

These validators are intentionally conservative.  A passing numeric or polarity
check is not presented as semantic proof.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date

_NUMBER_RE = re.compile(r"(?<!\w)(\d+(?:[.,]\d+)?)\s*(%|ngày|tháng|năm|giờ|lần|lượt)?", re.I)
_MODALITY_MARKERS = {
    "required": (
        r"\bphải\b",
        r"\bbuộc\s+phải\b",
        r"(?<!không )\bbắt\s+buộc\b",
    ),
    "optional": (
        r"\bcó\s+thể\b",
        r"\bkhông\s+bắt\s+buộc\b",
        r"\bđược\s+phép\b",
    ),
    "prohibited": (r"\bkhông\s+được(?:\s+phép)?\b", r"\bcấm\b"),
    "negation": (
        r"\bkhông\s+(?!(?:quá|bắt\s+buộc)\b)\w+",
        r"\bchưa\s+\w+",
    ),
    "upper_bound": (r"\bkhông\s+quá\b", r"\btối\s+đa\b"),
    "lower_bound": (r"\bít\s+nhất\b", r"\btối\s+thiểu\b"),
    "exception": (r"\btrừ\s+trường\s+hợp\b", r"\bngoại\s+lệ\b", r"\btrừ\s+khi\b"),
}


@dataclass(frozen=True)
class ClaimValidation:
    status: str
    reasons: tuple[str, ...]
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class Citation:
    id: str
    text_original: str
    quote_exact: str
    source_hash: str
    approved: bool
    as_of_date: date
    amendment_state: str


def hydrate_quote(text_original: str, start: int, end: int) -> str:
    """Slice the approved original text; never accept a model-provided quote."""

    if start < 0 or end < start or end > len(text_original):
        raise ValueError("invalid source span")
    return text_original[start:end]


def validate_citation(citation: Citation) -> tuple[bool, tuple[str, ...]]:
    reasons: list[str] = []
    if not citation.approved:
        reasons.append("source_not_approved")
    if citation.source_hash != _hash(citation.text_original):
        reasons.append("source_hash_mismatch")
    if citation.quote_exact and citation.quote_exact not in citation.text_original:
        reasons.append("quote_not_in_original")
    if citation.as_of_date and citation.amendment_state == "unknown":
        reasons.append("effectivity_unknown")
    return not reasons, tuple(reasons)


def _hash(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _numbers(value: str) -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for match in _NUMBER_RE.finditer(value):
        number = match.group(1).replace(",", ".")
        unit = (match.group(2) or "").casefold()
        found.add((number, unit))
    return found


def _markers(value: str) -> set[str]:
    lowered = value.casefold()
    return {
        name
        for name, markers in _MODALITY_MARKERS.items()
        if any(re.search(marker, lowered) for marker in markers)
    }


def validate_claim(
    claim_text: str,
    evidence_ids: Iterable[str],
    evidence_by_id: Mapping[str, str],
    memory_evidence_ids: Iterable[str] = (),
) -> ClaimValidation:
    ids = tuple(dict.fromkeys(evidence_ids))
    reasons: list[str] = []
    if not ids:
        return ClaimValidation("blocked", ("claim_without_evidence",), ids)
    if set(ids) & set(memory_evidence_ids):
        return ClaimValidation("blocked", ("memory_is_not_evidence",), ids)
    if any(item not in evidence_by_id or not evidence_by_id[item] for item in ids):
        return ClaimValidation("blocked", ("evidence_not_found",), ids)
    quote_text = "\n".join(evidence_by_id.get(item, "") for item in ids)
    if not quote_text:
        return ClaimValidation("blocked", ("evidence_not_found",), ids)
    claim_numbers = _numbers(claim_text)
    evidence_numbers = _numbers(quote_text)
    if claim_numbers and not claim_numbers.issubset(evidence_numbers):
        reasons.append("numeric_or_date_mismatch")
    claim_markers = _markers(claim_text)
    evidence_markers = _markers(quote_text)
    def add_reason(reason: str) -> None:
        if reason not in reasons:
            reasons.append(reason)

    if "exception" in evidence_markers and "exception" not in claim_markers:
        add_reason("exception_not_preserved")
    if "prohibited" in evidence_markers and "prohibited" not in claim_markers:
        add_reason("polarity_mismatch")
    if "prohibited" in claim_markers and "prohibited" not in evidence_markers:
        add_reason("polarity_mismatch")
    if ("negation" in claim_markers) != ("negation" in evidence_markers):
        add_reason("polarity_mismatch")
    if "required" in evidence_markers and "required" not in claim_markers:
        add_reason("modality_mismatch")
    if "required" in claim_markers and "required" not in evidence_markers:
        add_reason("modality_mismatch")
    if "upper_bound" in evidence_markers and "lower_bound" in claim_markers:
        add_reason("threshold_direction_mismatch")
    if "optional" in evidence_markers and "required" in claim_markers:
        add_reason("modality_mismatch")
    if "required" in evidence_markers and "optional" in claim_markers:
        add_reason("modality_mismatch")
    return ClaimValidation("conditional" if reasons else "supported", tuple(reasons), ids)
