"""ACL-safe comparison data layer (C2).

Every query runs inside one principal-scoped transaction
(``set_config('app.user_id', ..., true)`` + ``SET LOCAL statement_timeout``).
Documents must pass ``ALLOWED_DOCUMENTS_SQL``; versions must be approved with
verified source provenance; nodes must be approved and pass
``node_source_text_valid``.  The deterministic engine (C1) receives only rows
this layer has already authorized — it performs no ACL of its own.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID, uuid4

from ..analysis.signals import (
    LogicalNode,
    NodeRecord,
    stitch_logical_nodes,
)
from ..audit import append_audit
from ..effectivity.store import clause_view, load_effectivity
from ..storage.authorized_search import ALLOWED_DOCUMENTS_SQL
from ..storage.embeddings import EmbeddingIndexError, active_index, parse_vector, vector_type
from .align import AlignedPair, AmendmentLink, CompareMode, align_nodes
from .diff import ChangeSignals, NodeDiff, diff_pair

MAX_COMPARE_NODES = 1500
MAX_HIGHLIGHTS = 15
_STATEMENT_TIMEOUT_MS = 60_000
DISCLAIMER = "Gợi ý tự động — cần chuyên viên thẩm định trước khi áp dụng"
_IMPACT_RANK = {"high": 0, "medium": 1, "low": 2}
# Actions the brief names for 1-click amendment suggestions (sửa đổi/bổ sung/thay thế).
_RELATED_ACTIONS = ("modify", "add", "replace")


class CompareError(Exception):
    """A comparison failure the router maps to ``api_error`` (code-only, no internals)."""

    def __init__(
        self, code: str, status_code: int = 422, *, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.details = details or {}


@dataclass(frozen=True)
class CompareSelection:
    """The two sides one comparison request selects (shared with summarize)."""

    mode: CompareMode
    left_document_id: UUID
    right_document_id: UUID
    as_of_date: date
    left_version_id: UUID | None = None
    right_version_id: UUID | None = None
    only_changes: bool = False
    include_embeddings: bool = True


@asynccontextmanager
async def _scoped(pool: Any, principal_id: UUID) -> AsyncIterator[Any]:
    async with pool.acquire() as connection, connection.transaction():
        await connection.execute(
            "SELECT set_config('app.user_id', $1, true)", str(principal_id)
        )
        await connection.execute(f"SET LOCAL statement_timeout = {_STATEMENT_TIMEOUT_MS}")
        yield connection


async def _allowed(connection: Any, document_ids: Sequence[UUID]) -> set[UUID]:
    if not document_ids:
        return set()
    rows = await connection.fetch(
        f"SELECT document_id FROM ({ALLOWED_DOCUMENTS_SQL}) allowed "
        "WHERE document_id = ANY($1::uuid[])",
        list(document_ids),
    )
    return {row["document_id"] for row in rows}


async def _document_meta(connection: Any, document_id: UUID) -> dict[str, Any]:
    row = await connection.fetchrow(
        "SELECT id, title, document_number, doc_type, issuing_body FROM documents WHERE id = $1",
        document_id,
    )
    return dict(row)


_VERSION_COLUMNS = """dv.id, dv.version_number, dv.publication_date, dv.effective_from,
       dv.retired_at, dv.based_on_version_id, dv.reviewed_at"""


async def _resolve_version(
    connection: Any, *, document_id: UUID, version_id: UUID | None
) -> Any:
    """An explicit approved+verified version (retired ones included, plan R1),
    or the latest active approved+verified version when ``version_id`` is None."""

    if version_id is not None:
        row = await connection.fetchrow(
            f"""SELECT {_VERSION_COLUMNS}
                FROM document_versions dv
                JOIN source_provenance sp ON sp.document_version_id = dv.id
                WHERE dv.id = $1 AND dv.document_id = $2
                  AND dv.review_status = 'approved' AND sp.verified_at IS NOT NULL""",
            version_id, document_id,
        )
    else:
        row = await connection.fetchrow(
            f"""SELECT {_VERSION_COLUMNS}
                FROM document_versions dv
                JOIN source_provenance sp ON sp.document_version_id = dv.id
                WHERE dv.document_id = $1 AND dv.review_status = 'approved'
                  AND dv.retired_at IS NULL AND sp.verified_at IS NOT NULL
                ORDER BY dv.version_number DESC LIMIT 1""",
            document_id,
        )
    if row is None:
        raise CompareError("COMPARE_VERSION_NOT_FOUND", 404)
    return row


async def _load_side(
    connection: Any, version_id: UUID, *, side: str, include_embeddings: bool
) -> list[LogicalNode]:
    """Approved, source-valid nodes of one version in reading order, stitched (C1)."""

    rows = await connection.fetch(
        """SELECT n.id, n.node_type, n.path, n.text_original, n.citation_label,
                  n.label_original, n.page_start, n.page_end
           FROM document_nodes n
           WHERE n.document_version_id = $1 AND n.review_status = 'approved'
             AND node_source_text_valid(n.id)
           ORDER BY n.path
           LIMIT $2""",
        version_id, MAX_COMPARE_NODES + 1,
    )
    if len(rows) > MAX_COMPARE_NODES:
        raise CompareError(
            "COMPARE_DOCUMENT_TOO_LARGE", 422,
            details={"side": side, "max_nodes": MAX_COMPARE_NODES,
                     "hint": "Chọn phạm vi hẹp hơn (Chương/Điều) rồi so sánh lại."},
        )
    if not rows:
        return []
    node_ids = [row["id"] for row in rows]
    embeddings: dict[UUID, tuple[float, ...]] = {}
    if include_embeddings:
        embeddings = await _existing_embeddings(connection, node_ids)
    taxonomies: dict[UUID, tuple[str, ...]] = {}
    label_rows = await connection.fetch(
        """SELECT nl.node_id, t.code
           FROM node_labels nl
           JOIN content_taxonomy t ON t.id = nl.taxonomy_id
           WHERE nl.node_id = ANY($1::uuid[]) AND nl.status IN ('auto', 'approved')
             AND t.active
           ORDER BY t.sort_order, t.code""",
        node_ids,
    )
    for row in label_rows:
        taxonomies[row["node_id"]] = (*taxonomies.get(row["node_id"], ()), row["code"])
    records = [
        NodeRecord(
            node_id=row["id"],
            node_type=row["node_type"],
            path=row["path"],
            text_original=row["text_original"],
            citation_label=row["citation_label"],
            label_original=row["label_original"],
            page_start=row["page_start"],
            page_end=row["page_end"],
            embedding=embeddings.get(row["id"]),
            taxonomy_codes=taxonomies.get(row["id"], ()),
        )
        for row in rows
    ]
    return stitch_logical_nodes(records)


async def _existing_embeddings(
    connection: Any, node_ids: Sequence[UUID]
) -> dict[UUID, tuple[float, ...]]:
    """Read stored vectors of the active ready index only — never embed at request time."""

    index = await active_index(connection)
    if index is None:
        return {}
    dimensions = int(index["dimensions"])
    try:
        cast = f"{vector_type(dimensions)}({dimensions})"
    except EmbeddingIndexError:
        return {}
    rows = await connection.fetch(
        f"""SELECT e.document_node_id, e.embedding::{cast}::text AS vec
            FROM node_embeddings e
            WHERE e.embedding_index_id = $1 AND e.document_node_id = ANY($2::uuid[])""",
        index["id"], list(node_ids),
    )
    return {row["document_node_id"]: tuple(parse_vector(row["vec"])) for row in rows}


async def _amendment_links(
    connection: Any, left_ids: Sequence[UUID], right_ids: Sequence[UUID],
    right_document_id: UUID,
) -> list[AmendmentLink]:
    """Approved links whose source is a loaded left node and whose target resolves
    to a loaded right node (by id) or to the right document (by stored path)."""

    if not left_ids or not right_ids:
        return []
    rows = await connection.fetch(
        """SELECT a.source_node_id, a.target_node_id, a.target_path, a.action,
                  a.valid_from, a.source_quote
           FROM node_amendments a
           WHERE a.review_status = 'approved' AND a.superseded_by IS NULL
             AND a.source_node_id = ANY($1::uuid[])
             AND (a.target_node_id = ANY($2::uuid[])
                  OR (a.target_node_id IS NULL AND a.target_path IS NOT NULL
                      AND a.target_document_id = $3))
           ORDER BY a.id""",
        list(left_ids), list(right_ids), right_document_id,
    )
    return [
        AmendmentLink(
            source_node_id=row["source_node_id"],
            target_node_id=row["target_node_id"],
            target_path=row["target_path"],
            action=row["action"],
            valid_from=row["valid_from"],
            source_quote=row["source_quote"],
        )
        for row in rows
    ]


def _side_view(node: LogicalNode | None) -> dict[str, Any] | None:
    if node is None:
        return None
    return {
        "node_id": node.primary_node_id,
        "member_node_ids": list(node.member_node_ids),
        "citation_label": node.citation_label,
        "structural_key": node.structural_key,
        "text_original": node.text_original,
        "page_start": node.page_start,
        "page_end": node.page_end,
    }


def _signals_view(signals: ChangeSignals) -> dict[str, Any]:
    return {
        "deadlines_changed": [
            {"value_num": span.value_num, "unit_normalized": span.unit_normalized,
             "raw_text": span.raw_text}
            for span in signals.deadlines_changed
        ],
        "amounts_changed": [
            {"value_num": span.value_num, "unit_normalized": span.unit_normalized,
             "raw_text": span.raw_text}
            for span in signals.amounts_changed
        ],
        "dates_changed": [list(item) for item in signals.dates_changed],
        "modality_shifted": signals.modality_shifted,
        "exception_changed": signals.exception_changed,
        "impact_level": signals.impact_level,
    }


def _item_view(index: int, pair: AlignedPair, node_diff: NodeDiff) -> dict[str, Any]:
    return {
        "item_key": f"item_{index:04d}",
        "change_kind": node_diff.change_kind,
        "content_also_modified": node_diff.content_also_modified,
        "alignment_method": pair.alignment_method,
        "alignment_score": pair.score,
        "impact_level": node_diff.signals.impact_level,
        "signals": _signals_view(node_diff.signals),
        "amendment_link": (
            {"action": pair.amendment_action, "valid_from": pair.valid_from,
             "source_quote": pair.source_quote}
            if pair.alignment_method == "explicit_amendment" else None
        ),
        "left": _side_view(pair.left),
        "right": _side_view(pair.right),
        "diff_segments": [{"op": seg.op, "text": seg.text} for seg in node_diff.segments],
    }


def _highlight(item: dict[str, Any]) -> str:
    """One deterministic Vietnamese sentence for a changed item (fallback summary)."""

    side = item["right"] or item["left"]
    label = side["citation_label"] or side["structural_key"] or "Đoạn văn"
    kind_text = {
        "added": "thêm mới",
        "removed": "lược bỏ",
        "modified": "sửa đổi nội dung",
        "moved_or_renumbered": "đánh số lại/di chuyển",
    }.get(item["change_kind"], item["change_kind"])
    if item["change_kind"] == "moved_or_renumbered" and item["content_also_modified"]:
        kind_text += " kèm sửa nội dung"
    signals = item["signals"]
    parts: list[str] = []
    if signals["deadlines_changed"]:
        parts.append("thời hạn: " + ", ".join(
            span["raw_text"] for span in signals["deadlines_changed"]))
    if signals["amounts_changed"]:
        parts.append("mức tiền/số lượng: " + ", ".join(
            span["raw_text"] for span in signals["amounts_changed"]))
    if signals["dates_changed"]:
        parts.append("ngày: " + ", ".join(
            f"{day:02d}/{month:02d}/{year}" for day, month, year in signals["dates_changed"]))
    if signals["modality_shifted"]:
        parts.append("thay đổi mức độ bắt buộc/cho phép/cấm")
    if signals["exception_changed"]:
        parts.append("thay đổi ngoại lệ")
    text = f"{label}: {kind_text}"
    if parts:
        text += " — " + "; ".join(parts)
    return text


def changed_sorted(items: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Changed items only, high impact first, reading order inside one impact level."""

    changed = [item for item in items if item["change_kind"] != "unchanged"]
    # Stable sort keeps the original reading order inside one impact level.
    return sorted(changed, key=lambda item: _IMPACT_RANK[item["impact_level"]])


async def compare_documents(
    pool: Any, principal_id: UUID, selection: CompareSelection
) -> dict[str, Any]:
    """Deterministic comparison of two authorized sides; audits ``document.compare``."""

    if selection.mode == "versions":
        if selection.left_document_id != selection.right_document_id:
            raise CompareError(
                "COMPARE_MODE_MISMATCH", 422,
                details={"mode": selection.mode,
                         "rule": "versions cần cùng một văn bản ở hai vế"},
            )
        if (selection.left_version_id is not None
                and selection.left_version_id == selection.right_version_id):
            raise CompareError("COMPARE_SAME_TARGET", 422)
    async with _scoped(pool, principal_id) as connection:
        allowed = await _allowed(
            connection, [selection.left_document_id, selection.right_document_id]
        )
        if (selection.left_document_id not in allowed
                or selection.right_document_id not in allowed):
            raise CompareError("DOCUMENT_NOT_FOUND", 404)
        left_version = await _resolve_version(
            connection, document_id=selection.left_document_id,
            version_id=selection.left_version_id,
        )
        right_version = await _resolve_version(
            connection, document_id=selection.right_document_id,
            version_id=selection.right_version_id,
        )
        if left_version["id"] == right_version["id"]:
            raise CompareError("COMPARE_SAME_TARGET", 422)
        left_nodes = await _load_side(
            connection, left_version["id"], side="left",
            include_embeddings=selection.include_embeddings,
        )
        right_nodes = await _load_side(
            connection, right_version["id"], side="right",
            include_embeddings=selection.include_embeddings,
        )
        links = await _amendment_links(
            connection,
            [node_id for node in left_nodes for node_id in node.member_node_ids],
            [node_id for node in right_nodes for node_id in node.member_node_ids],
            selection.right_document_id,
        )
        pairs = align_nodes(left_nodes, right_nodes, links, selection.mode)
        items = [_item_view(index, pair, diff_pair(pair)) for index, pair in enumerate(pairs)]
        ordered = changed_sorted(items)
        counts = {kind: 0 for kind in
                  ("added", "removed", "modified", "moved_or_renumbered", "unchanged")}
        for item in items:
            counts[item["change_kind"]] += 1
        doc_views, _, _ = await load_effectivity(
            connection,
            document_ids=[selection.left_document_id, selection.right_document_id],
            as_of=selection.as_of_date,
        )
        comparison_id = uuid4()
        await append_audit(
            connection, principal_id=principal_id, action="document.compare",
            target_type="document", target_id=str(selection.left_document_id),
            metadata={
                "comparison_id": str(comparison_id), "mode": selection.mode,
                "right_document_id": str(selection.right_document_id),
                "left_version_id": str(left_version["id"]),
                "right_version_id": str(right_version["id"]),
                "as_of_date": selection.as_of_date.isoformat(),
                "total_items": len(items), "only_changes": selection.only_changes,
                "include_embeddings": selection.include_embeddings,
            },
        )
        return {
            "comparison_id": comparison_id,
            "mode": selection.mode,
            "as_of_date": selection.as_of_date,
            "left_doc": {
                **await _document_meta(connection, selection.left_document_id),
                "version_id": left_version["id"],
                "version_number": left_version["version_number"],
                "effectivity": doc_views[str(selection.left_document_id)].model_dump(mode="json"),
            },
            "right_doc": {
                **await _document_meta(connection, selection.right_document_id),
                "version_id": right_version["id"],
                "version_number": right_version["version_number"],
                "effectivity": doc_views[str(selection.right_document_id)].model_dump(mode="json"),
            },
            "summary": {
                "total_items": len(items),
                **counts,
                "high_impact_changes": sum(
                    1 for item in ordered if item["impact_level"] == "high"),
                "explicit_amendment_links": sum(
                    1 for item in items if item["alignment_method"] == "explicit_amendment"),
                "deterministic_highlights": [
                    _highlight(item) for item in ordered[:MAX_HIGHLIGHTS]
                ],
            },
            "items": ordered if selection.only_changes else items,
            "disclaimer": DISCLAIMER,
        }


async def list_document_versions(
    pool: Any, principal_id: UUID, document_id: UUID
) -> dict[str, Any]:
    """Approved+verified versions of one authorized document and amendment neighbors."""

    async with _scoped(pool, principal_id) as connection:
        if document_id not in await _allowed(connection, [document_id]):
            raise CompareError("DOCUMENT_NOT_FOUND", 404)
        meta = await _document_meta(connection, document_id)
        versions = await connection.fetch(
            """SELECT dv.id, dv.version_number, dv.publication_date, dv.effective_from,
                      dv.retired_at IS NULL AS is_current, dv.based_on_version_id, dv.reviewed_at
               FROM document_versions dv
               JOIN source_provenance sp ON sp.document_version_id = dv.id
               WHERE dv.document_id = $1 AND dv.review_status = 'approved'
                 AND sp.verified_at IS NOT NULL
               ORDER BY dv.version_number DESC""",
            document_id,
        )
        related = await _related_amendment_documents(connection, document_id)
        return {
            "document": meta,
            "versions": [dict(row) for row in versions],
            "related_amendment_documents": related,
        }


async def _related_amendment_documents(
    connection: Any, document_id: UUID
) -> list[dict[str, Any]]:
    """Other ALLOWED documents linked to this one by approved amendment relations."""

    rows = await connection.fetch(
        """SELECT a.action,
                  sn.document_id AS source_document_id,
                  COALESCE(a.target_document_id, tn.document_id) AS target_document_id
           FROM node_amendments a
           JOIN document_nodes sn ON sn.id = a.source_node_id
           LEFT JOIN document_nodes tn ON tn.id = a.target_node_id
           WHERE a.review_status = 'approved' AND a.superseded_by IS NULL
             AND a.action = ANY($2::text[])
             AND (sn.document_id = $1
                  OR COALESCE(a.target_document_id, tn.document_id) = $1)""",
        document_id, list(_RELATED_ACTIONS),
    )
    directions: dict[UUID, set[str]] = {}
    actions: dict[UUID, set[str]] = {}
    for row in rows:
        source, target = row["source_document_id"], row["target_document_id"]
        other = target if source == document_id else source
        if other is None or other == document_id:
            continue
        direction = ("amends_this_document" if target == document_id
                     else "amended_by_this_document")
        directions.setdefault(other, set()).add(direction)
        actions.setdefault(other, set()).add(row["action"])
    allowed = await _allowed(connection, list(directions))
    result: list[dict[str, Any]] = []
    for other in allowed:
        meta = await _document_meta(connection, other)
        result.append({
            **meta,
            "directions": sorted(directions[other]),
            "actions": sorted(actions[other]),
        })
    result.sort(key=lambda entry: (entry["title"], str(entry["id"])))
    return result


async def node_timeline_diff(
    pool: Any, principal_id: UUID, node_id: UUID, as_of: date
) -> dict[str, Any]:
    """Spec A5: one clause's timeline — previous version, approved amendments, diff.

    A missing previous version is stated explicitly in the response, never an error.
    """

    async with _scoped(pool, principal_id) as connection:
        row = await connection.fetchrow(
            """SELECT n.id, n.document_id, n.document_version_id,
                      dv.version_number, dv.based_on_version_id,
                      dv.review_status AS version_status, sp.verified_at
               FROM document_nodes n
               JOIN document_versions dv ON dv.id = n.document_version_id
               LEFT JOIN source_provenance sp ON sp.document_version_id = dv.id
               WHERE n.id = $1 AND n.review_status = 'approved'
                 AND node_source_text_valid(n.id)""",
            node_id,
        )
        if (row is None or row["version_status"] != "approved"
                or row["verified_at"] is None):
            raise CompareError("DOCUMENT_NOT_FOUND", 404)
        document_id = row["document_id"]
        if document_id not in await _allowed(connection, [document_id]):
            raise CompareError("DOCUMENT_NOT_FOUND", 404)
        current_nodes = await _load_side(
            connection, row["document_version_id"], side="current", include_embeddings=True
        )
        current = next(
            (node for node in current_nodes if node_id in node.member_node_ids), None
        )
        if current is None:
            raise CompareError("DOCUMENT_NOT_FOUND", 404)
        previous_version: dict[str, Any] | None = None
        previous: dict[str, Any] | None = None
        message: str | None = None
        pair: AlignedPair | None = None
        if row["based_on_version_id"] is None:
            message = "Không có phiên bản trước của văn bản này trong kho."
        else:
            prev_row = await connection.fetchrow(
                """SELECT dv.id, dv.version_number
                   FROM document_versions dv
                   JOIN source_provenance sp ON sp.document_version_id = dv.id
                   WHERE dv.id = $1 AND dv.document_id = $2
                     AND dv.review_status = 'approved' AND sp.verified_at IS NOT NULL""",
                row["based_on_version_id"], document_id,
            )
            if prev_row is None:
                message = (
                    "Phiên bản trước chưa được duyệt hoặc chưa kiểm chứng nguồn "
                    "nên không thể đối chiếu."
                )
            else:
                previous_version = {
                    "id": prev_row["id"], "version_number": prev_row["version_number"]
                }
                previous_nodes = await _load_side(
                    connection, prev_row["id"], side="previous", include_embeddings=True
                )
                pairs = align_nodes(previous_nodes, current_nodes, (), "versions")
                pair = next(
                    (item for item in pairs
                     if item.right is not None and node_id in item.right.member_node_ids),
                    None,
                )
                if pair is not None and pair.left is not None:
                    previous = _side_view(pair.left)
                else:
                    message = "Không tìm thấy Điều/Khoản tương ứng trong phiên bản trước."
        node_diff = diff_pair(pair) if pair is not None else None
        amendments = await _node_amendments(connection, node_id, document_id)
        doc_views, node_views, _ = await load_effectivity(
            connection, document_ids=[document_id], node_ids=[node_id], as_of=as_of
        )
        effectivity = clause_view(
            doc_views.get(str(document_id)), node_views.get(str(node_id))
        )
        return {
            "node_id": node_id,
            "document": await _document_meta(connection, document_id),
            "version": {"id": row["document_version_id"],
                        "version_number": row["version_number"]},
            "as_of_date": as_of,
            "current": _side_view(current),
            "has_previous": previous is not None,
            "previous_version": previous_version,
            "previous": previous,
            "message": message,
            "change_kind": node_diff.change_kind if node_diff else None,
            "content_also_modified": node_diff.content_also_modified if node_diff else False,
            "alignment_method": pair.alignment_method if pair else None,
            "alignment_score": pair.score if pair else None,
            "impact_level": node_diff.signals.impact_level if node_diff else None,
            "signals": _signals_view(node_diff.signals) if node_diff else None,
            "diff_segments": (
                [{"op": seg.op, "text": seg.text} for seg in node_diff.segments]
                if node_diff else []
            ),
            "amendments": amendments,
            "effectivity": effectivity.model_dump(mode="json") if effectivity else None,
            "disclaimer": DISCLAIMER,
        }


async def _node_amendments(
    connection: Any, node_id: UUID, document_id: UUID
) -> list[dict[str, Any]]:
    """Approved relations acting on this node (or its whole document) from other
    ALLOWED documents whose source node is itself approved and source-valid."""

    rows = await connection.fetch(
        """SELECT a.id, a.action, a.scope, a.valid_from, a.source_quote, a.evidence_source,
                  a.source_node_id, sn.document_id AS source_document_id,
                  sn.citation_label AS source_label,
                  sd.title AS source_title, sd.document_number AS source_number,
                  sd.doc_type AS source_doc_type, sd.issuing_body AS source_issuing_body
           FROM node_amendments a
           JOIN document_nodes sn ON sn.id = a.source_node_id
           JOIN document_versions sv ON sv.id = sn.document_version_id
           JOIN source_provenance sp ON sp.document_version_id = sv.id
           JOIN documents sd ON sd.id = sn.document_id
           WHERE a.review_status = 'approved' AND a.superseded_by IS NULL
             AND (a.target_node_id = $1
                  OR (a.scope = 'document' AND a.target_document_id = $2))
             AND sn.document_id <> $2
             AND sn.review_status = 'approved' AND node_source_text_valid(sn.id)
             AND sv.review_status = 'approved' AND sp.verified_at IS NOT NULL
           ORDER BY a.valid_from NULLS LAST, a.id""",
        node_id, document_id,
    )
    allowed = await _allowed(connection, list({row["source_document_id"] for row in rows}))
    return [
        {
            "id": row["id"], "action": row["action"], "scope": row["scope"],
            "valid_from": row["valid_from"], "source_quote": row["source_quote"],
            "evidence_source": row["evidence_source"],
            "source_node_id": row["source_node_id"], "source_label": row["source_label"],
            "source_document": {
                "id": row["source_document_id"], "title": row["source_title"],
                "document_number": row["source_number"],
                "doc_type": row["source_doc_type"],
                "issuing_body": row["source_issuing_body"],
            },
        }
        for row in rows if row["source_document_id"] in allowed
    ]
