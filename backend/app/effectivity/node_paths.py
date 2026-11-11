"""Article/clause/point targets: parse "khoản 2 Điều 5", match the G0 tree paths."""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date

from .extract import _paths
from .resolver import Interval, Relation

_PART = re.compile(
    r"(?:(?:điểm|Điểm)\s+(?P<point>[a-zđ])\s+)?(?:(?:khoản|Khoản)\s+(?P<clause>\d+)\s+)?"
    r"(?:Điều|điều)\s+(?P<article>\d+[a-z]?)\b"
)
NODE_ACTIONS = {
    "modify": "modified", "add": "modified", "replace": "replaced",
    "repeal": "repealed", "repeal_partial": "repealed", "suspend": "suspended",
}


def parse_target_path(text: str) -> list[str]:
    """Regexes for ``document_nodes.path`` of every part cited in ``text``."""

    patterns: list[str] = []
    expanded = _paths(text) or [text]
    for part_text in expanded:
        for match in _PART.finditer(part_text):
            segment = f"dieu:{match.group('article')}"
            if match.group("clause"):
                segment += f"/khoan:{match.group('clause')}"
            if match.group("point"):
                segment += f"/diem:{match.group('point')}"
            pattern = rf"(^|[:/]){re.escape(segment)}$"
            if pattern not in patterns:
                patterns.append(pattern)
    return patterns


def node_exception_intervals(relations: Sequence[Relation]) -> list[Interval]:
    """Exceptions for one node from its approved node-level relations.

    ``commence`` (the node takes effect later than its document, e.g. Điều 2 of
    Thông tư 28/2024 from 01/8/2024) makes the node "not yet effective" before the
    date and adds no exception after it, so the node inherits its document again.
    """

    approved = [item for item in relations if item.approved and item.valid_from is not None]
    pending = any(not item.approved for item in relations)
    intervals: list[Interval] = []
    for item in sorted(approved, key=lambda relation: relation.valid_from or date.min):
        assert item.valid_from is not None
        note = f"Theo {item.source_label} (đã duyệt)."
        if item.action == "commence":
            intervals.append(Interval(
                date.min, item.valid_from, "not_yet_effective", "verified",
                verification_source="relation", verified_by=item.reviewed_by,
                verified_at=item.reviewed_at, chain=(item.id,),
                notes=(f"Có hiệu lực từ {item.valid_from:%d/%m/%Y}. {note}",),
            ))
            continue
        if item.condition:
            intervals.append(Interval(
                item.valid_from, item.valid_to, "unknown", "unverified", chain=(item.id,),
                notes=(f"Quan hệ có điều kiện: {item.condition[:300]}",),
            ))
            continue
        status = NODE_ACTIONS.get(item.action, "unknown")
        verification = (
            "verified" if status in {"repealed", "suspended", "replaced"} else "unverified"
        )
        intervals.append(Interval(
            item.valid_from, item.valid_to, status, verification,
            verification_source="relation" if verification == "verified" else None,
            verified_by=item.reviewed_by if verification == "verified" else None,
            verified_at=item.reviewed_at if verification == "verified" else None,
            chain=(item.id,),
            notes=(f"{_TEXT.get(item.action, item.action)} từ {item.valid_from:%d/%m/%Y}. {note}",),
        ))
    if pending:
        intervals = [
            Interval(**{**item.__dict__, "notes": (*item.notes, "Có đề xuất chưa xác nhận.")})
            for item in intervals
        ]
    return _non_overlapping(intervals)


def _non_overlapping(intervals: list[Interval]) -> list[Interval]:
    """Later relations win; cut earlier intervals at the next start."""

    result: list[Interval] = []
    for index, item in enumerate(intervals):
        nxt = intervals[index + 1].valid_from if index + 1 < len(intervals) else None
        end = item.valid_to
        if nxt is not None and (end is None or nxt < end):
            end = nxt
        if end is not None and end <= item.valid_from:
            continue
        result.append(Interval(**{**item.__dict__, "valid_to": end}))
    return result


_TEXT = {
    "modify": "Được sửa đổi", "add": "Được bổ sung", "replace": "Được thay thế nội dung",
    "repeal": "Bị bãi bỏ", "repeal_partial": "Bị bãi bỏ", "suspend": "Bị ngưng hiệu lực",
}
