"""Shared normative-signal extraction (C1).

Pure, deterministic helpers reused by the comparison engine (C2) and the conflict
detector (D3).  The regex/stopword tables live in ``synthesis.checks`` and the Unicode
helpers in ``vietnamese_nlp.unicode_norm``; this module imports them instead of copying.

``text_original`` is never mutated: every derived value (folded text, structural key,
signals) is returned separately.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from ..synthesis.checks import (
    _CONDITION,
    _DATE_SLASH,
    _DATE_WORDS,
    _EXCEPTION,
    _NEGATION,
    _OBLIGATION,
    _PERMISSION,
    _content,
    _facts,
    _fold_words,
    _has_accented,
)
from ..vietnamese_nlp.unicode_norm import fold_text, normalize_text

# node_writer.py writes "{index + 1:06d}:{path_key}" (or a bare ordinal when the parsed
# node has no path_key); tree_parser.py appends "/tiep:N" to continuation segments.
_ORDINAL_PREFIX = re.compile(r"^\d{6}:")
_BARE_ORDINAL = re.compile(r"^\d{6}$")
_TIEP_SUFFIX = re.compile(r"/tiep:\d+$")
_DIEU_KEY = re.compile(
    r"(?:^|/)dieu:(\d+)(?:/khoan:(\d+))?(?:/diem:([a-zà-ỹ]))?",
    re.IGNORECASE,
)

# Prohibition cues are the subset of checks._NEGATION that forbids conduct; the remaining
# generic cues ("không", "chưa", "không phải") only yield "negation" when no prohibition
# is present (controller ruling 1).
_PROHIBITION = ("nghiêm cấm", "không được", "cấm")

_DEADLINE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(ngày làm việc|ngày|tháng|năm|giờ)\b", re.IGNORECASE
)
# Partial dates are stripped before _DEADLINE runs so "tháng 7 năm 2030" / "ngày 01 tháng 7"
# are not read as durations.  Targeted additions to the reused checks._DATE_WORDS/_DATE_SLASH;
# a genuine duration ("trong 7 năm", "gia hạn 01 tháng") has no leading ngày/tháng keyword
# before its number and is kept.
_MONTH_YEAR = re.compile(r"\btháng\s+\d{1,2}\s+năm\s+\d{4}\b", re.IGNORECASE)
_DAY_MONTH = re.compile(r"\bngày\s+\d{1,2}\s+tháng\s+\d{1,2}\b", re.IGNORECASE)
_MONEY = re.compile(r"(\d+(?:[.,]\d+)*)\s*(triệu\s+đồng|tỷ\s+đồng|đồng)", re.IGNORECASE)
_PERCENT = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")
_COUNT_UNITS = ("bản", "bộ", "người", "lần", "chiếc", "cái")
_COUNT = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(" + "|".join(_COUNT_UNITS) + r")\b", re.IGNORECASE
)


def normalize_structural_key(raw_path: str | None) -> str:
    """Canonical comparison key for a ``document_nodes.path`` or amendment ``target_path``.

    Strips the 6-digit ordinal prefix and any ``/tiep:N`` continuation suffix, then
    extracts ``dieu:N(/khoan:M)?(/diem:x)?`` when present (chapter/section prefixes are
    dropped, leading zeros normalized).  Without a ``dieu`` component the remainder is
    kept verbatim (``chuong:I``, ``muc:2``, ``phuluc:1``, ``doan``).  None/empty input and
    a bare ordinal path (no structural remainder) yield the empty string.
    """

    if not raw_path:
        return ""
    value = _ORDINAL_PREFIX.sub("", raw_path.strip())
    if _BARE_ORDINAL.fullmatch(value):
        return ""
    value = _TIEP_SUFFIX.sub("", value)
    match = _DIEU_KEY.search(value)
    if match is None:
        return value
    key = f"dieu:{int(match.group(1))}"
    if match.group(2) is not None:
        key += f"/khoan:{int(match.group(2))}"
    if match.group(3) is not None:
        key += f"/diem:{match.group(3).casefold()}"
    return key


@dataclass(frozen=True)
class LogicalNode:
    """One logical unit after stitching its ``tiep:N`` continuation segments."""

    primary_node_id: UUID
    member_node_ids: tuple[UUID, ...]
    node_type: str
    structural_key: str
    raw_path: str
    citation_label: str | None
    label_original: str | None
    text_original: str
    text_folded: str
    page_start: int | None
    page_end: int | None
    ordinal: int
    embedding: tuple[float, ...] | None = None
    taxonomy_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class NodeRecord:
    """One stored ``document_nodes`` row as read by the comparison service (C2).

    ``path`` is the raw stored path (ordinal prefix included).  Records must be passed
    to ``stitch_logical_nodes`` in reading order.
    """

    node_id: UUID
    node_type: str
    path: str
    text_original: str
    citation_label: str | None = None
    label_original: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    embedding: tuple[float, ...] | None = None
    taxonomy_codes: tuple[str, ...] = ()


def stitch_logical_nodes(records: Sequence[NodeRecord]) -> list[LogicalNode]:
    """Merge ``tiep:N`` continuation segments into their parent logical node.

    Continuation segments are ``paragraph`` nodes whose path is the owner's path plus
    ``/tiep:N`` (tree_parser.py), so grouping follows the path prefix in reading order,
    never node_type equality.  All member ids are preserved in order; ``page_start`` is
    the minimum and ``page_end`` the maximum over members; texts are joined with a
    single ``\\n``.  The first member supplies type, key, labels, embedding and taxonomy.
    """

    groups: list[list[NodeRecord]] = []
    for record in records:
        stripped = _ORDINAL_PREFIX.sub("", record.path)
        parent = _TIEP_SUFFIX.sub("", stripped)
        if (
            parent != stripped
            and groups
            and _ORDINAL_PREFIX.sub("", groups[-1][0].path) == parent
        ):
            groups[-1].append(record)
        else:
            groups.append([record])
    return [_build_logical_node(group, ordinal) for ordinal, group in enumerate(groups)]


def _build_logical_node(group: list[NodeRecord], ordinal: int) -> LogicalNode:
    first = group[0]
    text = "\n".join(record.text_original for record in group)
    starts = [record.page_start for record in group if record.page_start is not None]
    ends = [record.page_end for record in group if record.page_end is not None]
    return LogicalNode(
        primary_node_id=first.node_id,
        member_node_ids=tuple(record.node_id for record in group),
        node_type=first.node_type,
        structural_key=normalize_structural_key(first.path),
        raw_path=first.path,
        citation_label=first.citation_label,
        label_original=first.label_original,
        text_original=text,
        text_folded=fold_text(text),
        page_start=min(starts) if starts else None,
        page_end=max(ends) if ends else None,
        ordinal=ordinal,
        embedding=first.embedding,
        taxonomy_codes=first.taxonomy_codes,
    )


@dataclass(frozen=True)
class DeadlineSpan:
    value_num: float
    unit_normalized: str  # ngay_lam_viec | ngay | thang | nam | gio
    raw_text: str


@dataclass(frozen=True)
class QuantitySpan:
    value_num: float
    unit_normalized: str  # dong | trieu_dong | ty_dong | percent | bản/bộ/người/... folded
    raw_text: str


@dataclass(frozen=True)
class NormativeSignals:
    deadlines: tuple[DeadlineSpan, ...]
    amounts_and_percents: tuple[QuantitySpan, ...]
    dates: frozenset[tuple[int, int, int]]
    plain_numbers: frozenset[str]
    deontic_polarities: frozenset[str]  # prohibition | obligation | permission | negation
    has_exception: bool
    has_condition: bool
    exception_phrases: tuple[str, ...]
    subject_tokens: frozenset[str]


_THOUSANDS_DOT = re.compile(r"\d{1,3}(?:\.\d{3})+")
_THOUSANDS_COMMA = re.compile(r"[1-9]\d{0,2}(?:,\d{3}){2,}")


def _parse_vi_number(raw: str) -> float:
    """Total parser for every number form the signal regexes accept — never raises.

    Documented normalization: repeated groups of three ("15.000.000", "1,234,567") are
    thousands separators; otherwise the LAST separator is the decimal one and any earlier
    separators are dropped ("1,5" -> 1.5, "1.234,56" and "1,234.56" -> 1234.56).  Mangled
    forms the money regex still accepts ("1.23.45") get the same last-separator best
    effort (-> 123.45) instead of an exception.
    """

    value = raw.strip()
    if _THOUSANDS_DOT.fullmatch(value) or _THOUSANDS_COMMA.fullmatch(value):
        value = value.replace(".", "").replace(",", "")
    elif "," in value or "." in value:
        decimal_at = max(value.rfind(","), value.rfind("."))
        value = (
            value[:decimal_at].replace(",", "").replace(".", "")
            + "."
            + value[decimal_at + 1:]
        )
    try:
        return float(value)
    except ValueError:  # defensive: the normalization above always yields a valid literal
        return 0.0


def _unit_key(unit: str) -> str:
    return fold_text(unit).replace(" ", "_")


def extract_normative_signals(text: str) -> NormativeSignals:
    """Deterministic normative signals for one node text (no LLM, no network).

    Deadlines are read on date-stripped text so full and partial dates ("ngày 01 tháng 7
    năm 2030", "tháng 7 năm 2030", "ngày 01 tháng 7") are dates, not durations.
    ``dates``/``plain_numbers`` come from ``checks._facts``
    (indices 1 and 3 of its 4-tuple).  Deontic labels distinguish prohibition
    ("nghiêm cấm"/"không được"/"cấm"), permission (``_PERMISSION``), obligation
    (``_OBLIGATION``) and generic negation (``_NEGATION`` without a prohibition cue);
    a text may carry several labels at once.
    """

    normalized = normalize_text(text)
    _, dates, _, plain = _facts(text)
    stripped = normalized
    for date_pattern in (_DATE_WORDS, _MONTH_YEAR, _DAY_MONTH, _DATE_SLASH):
        stripped = date_pattern.sub(" ", stripped)
    deadlines = tuple(
        DeadlineSpan(_parse_vi_number(match.group(1)), _unit_key(match.group(2)),
                     match.group(0))
        for match in _DEADLINE.finditer(stripped)
    )
    amounts: list[QuantitySpan] = [
        QuantitySpan(_parse_vi_number(match.group(1)), _unit_key(match.group(2)),
                     match.group(0))
        for match in _MONEY.finditer(normalized)
    ]
    amounts.extend(
        QuantitySpan(_parse_vi_number(match.group(1)), "percent", match.group(0))
        for match in _PERCENT.finditer(normalized)
    )
    amounts.extend(
        QuantitySpan(_parse_vi_number(match.group(1)), _unit_key(match.group(2)),
                     match.group(0))
        for match in _COUNT.finditer(normalized)
    )
    polarities: set[str] = set()
    if _has_accented(normalized, _PROHIBITION):
        polarities.add("prohibition")
    if _has_accented(normalized, _PERMISSION):
        polarities.add("permission")
    if _has_accented(normalized, _OBLIGATION):
        polarities.add("obligation")
    if _has_accented(normalized, _NEGATION) and "prohibition" not in polarities:
        polarities.add("negation")
    exception_phrases = tuple(
        cue for cue in _EXCEPTION if _has_accented(normalized, (cue,))
    )
    return NormativeSignals(
        deadlines=deadlines,
        amounts_and_percents=tuple(amounts),
        dates=frozenset(dates),
        plain_numbers=frozenset(plain),
        deontic_polarities=frozenset(polarities),
        has_exception=_has_accented(normalized, _EXCEPTION),
        has_condition=_has_accented(normalized, _CONDITION),
        exception_phrases=exception_phrases,
        subject_tokens=frozenset(_content(_fold_words(text))),
    )
