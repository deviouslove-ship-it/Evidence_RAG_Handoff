"""Deterministic token diff and change classification (C1).

Vietnamese diacritics are preserved (NFC); tokens are whitespace-delimited runs so a
syllable is never cut in half.  Pure-whitespace noise (extra spaces, OCR line breaks) is
not reported as a content modification.  No DB, no LLM, no network.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, TypeVar

from ..analysis.signals import (
    DeadlineSpan,
    NormativeSignals,
    QuantitySpan,
    extract_normative_signals,
)
from ..vietnamese_nlp.unicode_norm import normalize_text, unicode_nfc
from .align import AlignedPair

ChangeKind = Literal["unchanged", "modified", "moved_or_renumbered", "added", "removed"]
DiffOp = Literal["equal", "delete", "insert"]

_TOKEN = re.compile(r"\S+|\s+")
_EMPTY_SIGNALS = extract_normative_signals("")


@dataclass(frozen=True)
class DiffSegment:
    op: DiffOp
    text: str


def compute_token_diff(text_a: str, text_b: str) -> list[DiffSegment]:
    """NFC token diff; adjacent segments with the same op are merged.

    ``replace`` opcodes are emitted as a ``delete`` followed by an ``insert``.  Equal
    input yields a single ``equal`` segment; two empty inputs yield no segments.
    """

    a = _TOKEN.findall(unicode_nfc(text_a))
    b = _TOKEN.findall(unicode_nfc(text_b))
    matcher = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    segments: list[DiffSegment] = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            _append(segments, "equal", "".join(a[i1:i2]))
        elif op == "delete":
            _append(segments, "delete", "".join(a[i1:i2]))
        elif op == "insert":
            _append(segments, "insert", "".join(b[j1:j2]))
        else:  # replace
            _append(segments, "delete", "".join(a[i1:i2]))
            _append(segments, "insert", "".join(b[j1:j2]))
    return segments


def _append(segments: list[DiffSegment], op: DiffOp, text: str) -> None:
    if not text:
        return
    if segments and segments[-1].op == op:
        segments[-1] = DiffSegment(op=op, text=segments[-1].text + text)
    else:
        segments.append(DiffSegment(op=op, text=text))


@dataclass(frozen=True)
class ChangeSignals:
    """Normative-signal changes for one paired modification.

    ``deadlines_changed``/``amounts_changed`` hold the spans whose (value, unit) key is
    absent on the other side (left-only spans first, then right-only spans); non-empty
    means the deadline/amount set changed.  ``dates_changed`` is the sorted symmetric
    difference of the date sets.  ``impact_level`` is high when a deadline, amount,
    deontic modality or exception changed; medium for added/removed/moved nodes and for
    date/number-only modifications; low otherwise.
    """

    deadlines_changed: tuple[DeadlineSpan, ...] = ()
    amounts_changed: tuple[QuantitySpan, ...] = ()
    dates_changed: tuple[tuple[int, int, int], ...] = ()
    modality_shifted: bool = False
    exception_changed: bool = False
    impact_level: Literal["high", "medium", "low"] = "low"


@dataclass(frozen=True)
class NodeDiff:
    change_kind: ChangeKind
    content_also_modified: bool  # True only for moved_or_renumbered pairs with text changes
    segments: tuple[DiffSegment, ...]
    signals: ChangeSignals


def _content_equal(left: str, right: str) -> bool:
    # normalize_text + full whitespace collapse: spacing/line-break noise is not a change.
    return " ".join(normalize_text(left).split()) == " ".join(normalize_text(right).split())


_SpanT = TypeVar("_SpanT", DeadlineSpan, QuantitySpan)


def _span_diff(
    left: tuple[_SpanT, ...],
    right: tuple[_SpanT, ...],
    key: Callable[[_SpanT], tuple[float, str]],
) -> tuple[_SpanT, ...]:
    right_keys = {key(span) for span in right}
    left_keys = {key(span) for span in left}
    return tuple(span for span in left if key(span) not in right_keys) + tuple(
        span for span in right if key(span) not in left_keys
    )


def _span_key(span: DeadlineSpan | QuantitySpan) -> tuple[float, str]:
    return (span.value_num, span.unit_normalized)


def _change_signals(
    left: NormativeSignals, right: NormativeSignals, kind: ChangeKind
) -> ChangeSignals:
    deadlines = _span_diff(left.deadlines, right.deadlines, _span_key)
    amounts = _span_diff(left.amounts_and_percents, right.amounts_and_percents, _span_key)
    dates = tuple(sorted(left.dates ^ right.dates))
    modality = left.deontic_polarities != right.deontic_polarities
    exception = left.has_exception != right.has_exception or (
        set(left.exception_phrases) != set(right.exception_phrases)
    )
    impact: Literal["high", "medium", "low"]
    if deadlines or amounts or modality or exception:
        impact = "high"
    elif kind in ("added", "removed", "moved_or_renumbered"):
        impact = "medium"
    elif dates or left.plain_numbers != right.plain_numbers:
        impact = "medium"
    else:
        impact = "low"
    return ChangeSignals(
        deadlines_changed=deadlines,
        amounts_changed=amounts,
        dates_changed=dates,
        modality_shifted=modality,
        exception_changed=exception,
        impact_level=impact,
    )


def diff_pair(pair: AlignedPair) -> NodeDiff:
    """Classify one aligned pair and compute its token diff + change signals.

    ``moved_or_renumbered`` applies when a tier-3 (semantic_lexical) pair has different
    structural keys; ``content_also_modified`` then tells whether the text changed too.
    Unchanged pairs keep the left text as a single equal segment and carry empty signals.
    """

    left, right = pair.left, pair.right
    if left is None and right is None:
        raise ValueError("AlignedPair must carry at least one node")
    if left is None:
        assert right is not None
        return NodeDiff(
            change_kind="added",
            content_also_modified=False,
            segments=tuple(compute_token_diff("", right.text_original)),
            signals=_change_signals(
                _EMPTY_SIGNALS, extract_normative_signals(right.text_original), "added"
            ),
        )
    if right is None:
        return NodeDiff(
            change_kind="removed",
            content_also_modified=False,
            segments=tuple(compute_token_diff(left.text_original, "")),
            signals=_change_signals(
                extract_normative_signals(left.text_original), _EMPTY_SIGNALS, "removed"
            ),
        )
    equal = _content_equal(left.text_original, right.text_original)
    renumbered = (
        pair.alignment_method == "semantic_lexical"
        and left.structural_key != right.structural_key
    )
    if equal and not renumbered:
        return NodeDiff(
            change_kind="unchanged",
            content_also_modified=False,
            segments=(DiffSegment(op="equal", text=left.text_original),),
            signals=ChangeSignals(),
        )
    kind: ChangeKind = "moved_or_renumbered" if renumbered else "modified"
    if equal:
        # Renumbered with identical content: no token noise, citation change only.
        return NodeDiff(
            change_kind=kind,
            content_also_modified=False,
            segments=(DiffSegment(op="equal", text=left.text_original),),
            signals=_change_signals(
                extract_normative_signals(left.text_original),
                extract_normative_signals(right.text_original),
                kind,
            ),
        )
    return NodeDiff(
        change_kind=kind,
        content_also_modified=renumbered,
        segments=tuple(compute_token_diff(left.text_original, right.text_original)),
        signals=_change_signals(
            extract_normative_signals(left.text_original),
            extract_normative_signals(right.text_original),
            kind,
        ),
    )
