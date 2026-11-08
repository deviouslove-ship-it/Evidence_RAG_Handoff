"""Deterministic legal-reference detection.

The parser detects intent, not law.  A caller must still verify uniqueness,
approval, ACL, and `as_of_date` in the database before bypassing Analyze.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .unicode_norm import canonical_document_number

_REFERENCE_RE = re.compile(
    r"(?P<article>\bđiều\s+\d+(?:\.\d+)?\b)"
    r"(?:[,\s]*\b(?P<clause>khoản\s+\d+)\b)?"
    r"(?:[,\s]*\b(?P<point>điểm\s+[a-zà-ỹ\d]+)\b)?",
    re.IGNORECASE,
)
_DOCUMENT_RE = re.compile(
    r"\b(?P<number>(?:nđ|nd|tt|qd|qđ|thông tư|nghị định|quyết định)"
    r"(?:\s+số)?\s*[-:]?\s*"
    r"\d+[/\-]\d+(?:/[a-zđ0-9]+(?:-[a-zđ0-9]+)*)?)\b",
    re.IGNORECASE,
)
_DOCUMENT_BODY_RE = re.compile(
    r"\d+[/\-]\d+(?:/[a-zđ0-9]+(?:-[a-zđ0-9]+)*)?", re.IGNORECASE
)


@dataclass(frozen=True)
class LegalReference:
    raw: str
    article: str | None
    clause: str | None
    point: str | None
    document_number: str | None

    @property
    def is_complete_local_reference(self) -> bool:
        return bool(self.article)

    @property
    def canonical_document_number(self) -> str | None:
        return canonical_document_number(self.document_number) if self.document_number else None


@dataclass(frozen=True)
class ParsedReferences:
    references: tuple[LegalReference, ...]
    document_numbers: tuple[str, ...]

    @property
    def is_unique_local_reference(self) -> bool:
        return len(self.references) == 1 and self.references[0].is_complete_local_reference


def _number(value: str | None) -> str | None:
    if value is None:
        return None
    return re.sub(r"\s+", " ", value).strip().lower()


def parse_legal_references(text: str) -> ParsedReferences:
    references: list[LegalReference] = []
    document_numbers: list[str] = []
    for match in _REFERENCE_RE.finditer(text):
        article = _number(match.group("article"))
        clause = _number(match.group("clause"))
        point = _number(match.group("point"))
        references.append(
            LegalReference(
                raw=match.group(0),
                article=article,
                clause=clause,
                point=point,
                document_number=None,
            )
        )
    for match in _DOCUMENT_RE.finditer(text):
        document_numbers.append(match.group("number"))
    return ParsedReferences(tuple(references), tuple(dict.fromkeys(document_numbers)))


def reference_document_number(value: str) -> str | None:
    """Extract the numbered part from a cited type and number."""
    match = _DOCUMENT_BODY_RE.search(value)
    return match.group(0) if match else None
