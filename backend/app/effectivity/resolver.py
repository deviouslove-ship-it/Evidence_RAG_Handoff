"""Compute effectivity intervals from approved relations and human attestations.

The hard rules of the design (§4) live here, in code, not in configuration:

1. "active + verified" only comes from a person's attestation with source and time.
2. Without a terminating relation axis A is "unknown" and axis B "not found in the
   store", with the known events as notes (for example "có hiệu lực từ D1").
3. A proposal (rule, AI, person) that nobody approved never changes axis A; it only
   adds the note "có đề xuất chưa xác nhận".
4. A conditional or transitional relation is not computed: axis A "unknown" with the
   condition as a note.
5. An attestation marked "needs re-verification" (database trigger, migration 0011)
   no longer verifies anything.

A status is computed for each date, never copied from today to the past or future.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

STATUSES = (
    "active", "not_yet_effective", "modified", "suspended", "repealed", "replaced", "unknown",
)
VERIFICATIONS = ("verified", "unverified", "not_found")
TERMINATING = {"repeal": "repealed", "replace": "replaced", "suspend": "suspended"}
PARTIAL = {"modify", "add", "repeal_partial"}
UNBOUNDED_START = date.min

NOTE_PENDING = "Có đề xuất quan hệ hiệu lực chưa được xác nhận."
NOTE_NO_TERMINATION = "Không tìm thấy thông tin chấm dứt hiệu lực trong kho."


@dataclass(frozen=True)
class Relation:
    """One effectivity relation touching the document (or node) being resolved."""

    id: str
    action: str
    valid_from: date | None
    approved: bool
    valid_to: date | None = None
    condition: str | None = None
    source_label: str = ""
    reviewed_by: str | None = None
    reviewed_at: str | None = None


@dataclass(frozen=True)
class Attestation:
    id: str
    result: str
    valid_for_from: date
    valid_for_to: date
    status: str
    attested_by: str
    attested_at: str
    source_note: str


@dataclass(frozen=True)
class Interval:
    valid_from: date
    valid_to: date | None
    status: str
    verification: str
    verification_source: str | None = None
    verified_by: str | None = None
    verified_at: str | None = None
    chain: tuple[str, ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)


def _fmt(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def _covers(start: date | None, end: date | None, day: date) -> bool:
    return start is not None and start <= day and (end is None or day < end)


def resolve_intervals(
    *,
    effective_from: date | None,
    relations: Sequence[Relation],
    attestations: Sequence[Attestation] = (),
) -> list[Interval]:
    """Intervals covering every date from ``UNBOUNDED_START`` onwards."""

    approved = [item for item in relations if item.approved]
    pending = any(not item.approved for item in relations)
    usable = [item for item in attestations if item.status == "valid"]
    stale = [item for item in attestations if item.status == "needs_reverify"]
    bounds = {UNBOUNDED_START}
    if effective_from is not None:
        bounds.add(effective_from)
    for relation in approved:
        if relation.valid_from is not None:
            bounds.add(relation.valid_from)
        if relation.valid_to is not None:
            bounds.add(relation.valid_to)
    for attestation in usable:
        bounds.add(attestation.valid_for_from)
        if attestation.valid_for_to < date.max:
            bounds.add(attestation.valid_for_to + timedelta(days=1))
    starts = sorted(bounds)
    intervals: list[Interval] = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else None
        interval = _segment(
            start, end, effective_from=effective_from, approved=approved,
            usable=usable, all_attestations=[*usable, *stale],
        )
        notes = list(interval.notes)
        if pending:
            notes.append(NOTE_PENDING)
        if stale:
            notes.append("Bản xác nhận trước đây cần xác minh lại vì kho có quan hệ mới.")
        intervals.append(replace(interval, notes=tuple(dict.fromkeys(notes))))
    return _merge(intervals)


def _segment(
    start: date,
    end: date | None,
    *,
    effective_from: date | None,
    approved: Sequence[Relation],
    usable: Sequence[Attestation],
    all_attestations: Sequence[Attestation],
) -> Interval:
    active_relations = [
        item for item in approved if _covers(item.valid_from, item.valid_to, start)
    ]
    chain = tuple(item.id for item in active_relations)
    notes: list[str] = []
    if effective_from is not None:
        notes.append(f"Có hiệu lực từ {_fmt(effective_from)} (theo văn bản).")
    for item in approved:
        if item.valid_from is not None and item.valid_from > start and item.action in TERMINATING:
            notes.append(
                f"Sẽ {_ACTION_TEXT[item.action]} từ {_fmt(item.valid_from)}"
                f" theo {item.source_label}."
            )
    conditional = [item for item in active_relations if item.condition]
    terminating = [
        item for item in active_relations if item.action in TERMINATING and not item.condition
    ]
    partial = [item for item in active_relations if item.action in PARTIAL and not item.condition]
    # Segment bounds include every attestation bound, so a segment is either fully
    # inside an attested period or fully outside it.
    attestation = next(
        (item for item in usable if item.valid_for_from <= start <= item.valid_for_to), None
    )
    # Hard rule 4: conditional/transitional relations are never computed.
    if conditional:
        for item in conditional:
            notes.append(
                f"Quan hệ có điều kiện theo {item.source_label}: {(item.condition or '')[:300]}"
            )
        return Interval(start, end, "unknown", "unverified", chain=chain, notes=tuple(notes))
    if terminating:
        statuses = {TERMINATING[item.action] for item in terminating}
        if len(statuses) > 1:
            notes.append("Các quan hệ đã duyệt cho kết quả khác nhau; cần rà soát.")
            return Interval(start, end, "unknown", "unverified", chain=chain, notes=tuple(notes))
        status = statuses.pop()
        lead = terminating[0]
        for item in terminating:
            notes.append(
                f"{_ACTION_TEXT[item.action].capitalize()} từ {_fmt(item.valid_from or start)}"
                f" theo {item.source_label}."
            )
        if attestation is not None and attestation.result != status:
            notes.append("Bản xác nhận khác với quan hệ đã duyệt; cần rà soát.")
            return Interval(start, end, "unknown", "unverified", chain=chain, notes=tuple(notes))
        if attestation is not None:
            return _attested(start, end, attestation, chain, notes)
        # An approved relation carries its reviewer, time and source node.
        return Interval(
            start, end, status, "verified", verification_source="relation",
            verified_by=lead.reviewed_by, verified_at=lead.reviewed_at,
            chain=chain, notes=tuple(notes),
        )
    if attestation is not None:
        for item in partial:
            notes.append(
                f"Được sửa đổi một phần từ {_fmt(item.valid_from or start)}"
                f" theo {item.source_label}."
            )
        return _attested(start, end, attestation, chain, notes)
    if effective_from is not None and start < effective_from:
        return Interval(
            start, end, "not_yet_effective", "unverified", chain=chain, notes=tuple(notes)
        )
    earlier = [item for item in all_attestations
               if not item.valid_for_from <= start <= item.valid_for_to
               or item.status != "valid"]
    for attested in earlier:
        notes.append(
            f"Đã xác minh '{_STATUS_TEXT.get(attested.result, attested.result)}' cho giai đoạn "
            f"{_fmt(attested.valid_for_from)}–{_fmt(attested.valid_for_to)};"
            " chưa xác minh tại ngày này."
        )
    verification = "unverified" if earlier else "not_found"
    if partial:
        for item in partial:
            notes.append(
                f"Được sửa đổi một phần từ {_fmt(item.valid_from or start)}"
                f" theo {item.source_label}."
            )
        notes.append(NOTE_NO_TERMINATION)
        return Interval(start, end, "modified", "unverified", chain=chain, notes=tuple(notes))
    # Hard rule 2: absence of a repeal is not evidence of being in force.
    notes.append(NOTE_NO_TERMINATION)
    return Interval(start, end, "unknown", verification, chain=chain, notes=tuple(notes))


def _attested(
    start: date, end: date | None, attestation: Attestation, chain: tuple[str, ...],
    notes: list[str],
) -> Interval:
    # Hard rule 1: the only path to "verified" without an approved terminating
    # relation is a person's attestation with source and time.
    notes.append(
        f"Đã xác minh cho giai đoạn {_fmt(attestation.valid_for_from)}–"
        f"{_fmt(attestation.valid_for_to)}: {attestation.source_note[:300]}"
    )
    return Interval(
        start, end, attestation.result, "verified", verification_source="attestation",
        verified_by=attestation.attested_by, verified_at=attestation.attested_at,
        chain=(*chain, f"attestation:{attestation.id}"), notes=tuple(notes),
    )


def _merge(intervals: Iterable[Interval]) -> list[Interval]:
    merged: list[Interval] = []
    for item in intervals:
        if merged:
            last = merged[-1]
            same = (
                last.status, last.verification, last.verification_source, last.verified_by,
                last.chain, last.notes,
            ) == (
                item.status, item.verification, item.verification_source, item.verified_by,
                item.chain, item.notes,
            )
            if same and last.valid_to == item.valid_from:
                merged[-1] = replace(last, valid_to=item.valid_to)
                continue
        merged.append(item)
    return merged


def at_date(intervals: Sequence[Interval], day: date) -> Interval | None:
    for item in intervals:
        if item.valid_from <= day and (item.valid_to is None or day < item.valid_to):
            return item
    return None


def cap_verification(
    status: str, verification: str, source: str | None, *, as_of: date, data_date: date | None,
) -> tuple[str, list[str]]:
    """Query-time guards: rule 1 again, and "after the store's data date" (D14)."""

    notes: list[str] = []
    if status == "active" and verification == "verified" and source != "attestation":
        verification = "unverified"
    if verification == "verified" and data_date is not None and as_of > data_date:
        verification = "unverified"
        notes.append(
            f"Ngày tra cứu sau ngày dữ liệu của kho ({_fmt(data_date)}):"
            " chưa xác minh tại ngày này."
        )
    return verification, notes


_ACTION_TEXT = {
    "repeal": "bị bãi bỏ",
    "replace": "bị thay thế",
    "suspend": "bị ngưng hiệu lực",
}
_STATUS_TEXT = {
    "active": "Còn hiệu lực",
    "not_yet_effective": "Chưa có hiệu lực",
    "modified": "Sửa đổi một phần",
    "suspended": "Tạm ngưng",
    "repealed": "Hết hiệu lực",
    "replaced": "Bị thay thế",
    "unknown": "Chưa xác định",
}
