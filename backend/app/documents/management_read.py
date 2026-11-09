"""Paged inventory and restricted source views for the Admin Portal."""

from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID

from ..auth_acl.policy import Permission, Principal
from ..vietnamese_nlp.unicode_norm import fold_text
from .management_access import CAN_READ, STAFF_SCOPE, scope_params
from .provenance import read_immutable_pdf, read_immutable_source
from .review import ReviewError

NODE_PAGE_SIZE = 25
_METADATA_FIELDS = ("title", "doc_type", "document_number", "issuing_body")
_METADATA = ", ".join(
    f"CASE WHEN v.admin_metadata IS NULL THEN d.{field} "
    f"ELSE v.admin_metadata->>'{field}' END AS {field}"
    for field in _METADATA_FIELDS
)
_AVAILABILITY = """CASE WHEN d.deleted_at IS NOT NULL THEN 'deleted'
                        WHEN d.suspended_at IS NOT NULL THEN 'suspended'
                        ELSE 'active' END"""
_RECORD = f"""
    SELECT d.id, {_METADATA}, v.publication_date, v.effective_from, v.official_url,
           v.original_filename, v.review_status::text AS review_status,
           COALESCE(e.effectivity, 'unknown') AS effectivity,
           {_AVAILABILITY} AS availability,
           v.id AS version_id, v.version_number, v.source_review_revision AS revision,
           v.submitted_by, v.original_file_path, v.original_file_sha256,
           v.source_file_sha256, v.source_format,
           {CAN_READ} AS can_read,
           ($2 AND {CAN_READ} AND d.deleted_at IS NULL AND v.retired_at IS NULL
             AND v.version_number = latest.version_number AND
             (v.review_status NOT IN ('draft', 'pending_review')
                OR v.submitted_by IS NULL OR v.submitted_by = $1)) AS can_edit,
           ($3 AND {CAN_READ} AND scope.can_review_all AND d.deleted_at IS NULL
             AND v.review_status = 'pending_review' AND v.submitted_by <> $1) AS can_review
    FROM documents d
    JOIN LATERAL (
      SELECT id, version_number FROM document_versions
      WHERE document_id = d.id ORDER BY version_number DESC LIMIT 1
    ) latest ON TRUE
    JOIN document_versions v ON v.document_id = d.id AND v.id = COALESCE($4::uuid, latest.id)
    CROSS JOIN LATERAL ({STAFF_SCOPE}) scope
    LEFT JOIN LATERAL (
      SELECT i.effective_status AS effectivity FROM document_effective_intervals i
      JOIN effectivity_snapshot_revisions r ON r.id = i.snapshot_revision_id AND r.is_active
      WHERE i.document_id = d.id AND i.valid_from <= $5::date
        AND (i.valid_to IS NULL OR i.valid_to > $5::date)
      ORDER BY i.valid_from DESC LIMIT 1
    ) e ON TRUE
"""
_PUBLIC_FIELDS = (*_METADATA_FIELDS, "id", "publication_date", "review_status", "effectivity",
                  "availability", "version_id", "version_number", "can_read", "can_edit")
_VI_CHARS = "".join(chr(i) for i in range(0x00C0, 0x1EFA)
                    if chr(i).isalpha() and chr(i).lower() in
                    "àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ")
_VI_FOLDED = "".join(fold_text(char) for char in _VI_CHARS)


def _folded(column: str) -> str:
    return f"lower(translate(normalize(coalesce({column}, '')), '{_VI_CHARS}', '{_VI_FOLDED}'))"


def _summary(row: Any) -> dict[str, Any]:
    return {field: row[field] for field in _PUBLIC_FIELDS}


async def list_documents(
    pool: Any, principal: Principal, *, q: str, document_number: str, title: str,
    doc_type: str | None, issuing_body: str, date_from: date | None, date_to: date | None,
    review_status: str | None, effectivity: str | None, availability: str | None,
    page: int, page_size: int, as_of: date,
) -> dict[str, Any]:
    args = (*scope_params(principal), None, as_of, principal.has(Permission.ADMIN),
            fold_text(q.strip()), fold_text(document_number.strip()), fold_text(title.strip()),
            doc_type, fold_text(issuing_body.strip()), date_from, date_to, review_status,
            effectivity, availability)
    where = f"""
        WHERE (can_read OR $6) AND
          position($7 IN ({_folded('document_number')} || ' ' || {_folded('title')})) > 0
          AND position($8 IN {_folded('document_number')}) > 0
          AND position($9 IN {_folded('title')}) > 0
          AND ($10::text IS NULL OR doc_type = $10)
          AND position($11 IN {_folded('issuing_body')}) > 0
          AND ($12::date IS NULL OR publication_date >= $12)
          AND ($13::date IS NULL OR publication_date <= $13)
          AND ($14::text IS NULL OR review_status = $14)
          AND ($15::text IS NULL OR effectivity = $15)
          AND CASE WHEN $16::text IS NULL THEN availability <> 'deleted'
                   ELSE availability = $16 END
    """
    async with pool.acquire() as conn, conn.transaction(isolation="repeatable_read", readonly=True):
        sql = f"WITH inventory AS ({_RECORD}) SELECT {{fields}} FROM inventory {where}"
        total = await conn.fetchval(sql.format(fields="count(*)"), *args)
        rows = await conn.fetch(
            sql.format(fields="*") + """ORDER BY publication_date DESC NULLS LAST,
               document_number COLLATE "C" NULLS LAST, id LIMIT $17 OFFSET $18""",
            *args, page_size, (page - 1) * page_size,
        )
    return {"items": [_summary(row) for row in rows], "total": total,
            "page": page, "page_size": page_size}


async def _record(
    conn: Any, principal: Principal, document_id: UUID, version_id: UUID | None, as_of: date,
) -> Any:
    row = await conn.fetchrow(_RECORD + " WHERE d.id = $6",
                              *scope_params(principal), version_id, as_of, document_id)
    if row is None or not (row["can_read"] or principal.has(Permission.ADMIN)):
        raise ReviewError("DOCUMENT_NOT_FOUND", 404)
    return row


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


async def detail(
    pool: Any, principal: Principal, document_id: UUID, *, version_id: UUID | None,
    page_number: int, node_page: int, as_of: date,
) -> dict[str, Any]:
    async with pool.acquire() as conn, conn.transaction(isolation="repeatable_read", readonly=True):
        row = await _record(conn, principal, document_id, version_id, as_of)
        version_id = row["version_id"]
        readable = row["can_read"] and row["availability"] != "deleted"
        versions = await conn.fetch(
            """SELECT v.id, v.version_number, v.review_status::text, v.publication_date,
                      CASE WHEN $2 THEN v.source_format END AS source_format,
                      CASE WHEN $2 THEN v.original_filename END AS original_filename,
                      v.retired_at IS NOT NULL AS retired
               FROM document_versions v WHERE v.document_id = $1 ORDER BY v.version_number DESC""",
            document_id, readable,
        )
        categories = await conn.fetch(
            """SELECT c.id, c.name FROM categories c JOIN document_categories dc
                 ON dc.category_id = c.id
               WHERE dc.document_id = $1 AND c.deleted_at IS NULL ORDER BY c.name, c.id""",
            document_id,
        )
        result = {
            "document": {**_summary(row), "can_read": readable},
            "versions": [dict(item) for item in versions],
            "categories": [dict(item) for item in categories], "revision": row["revision"],
            "effective_from": row["effective_from"], "page_count": 0, "node_count": 0,
            "node_page_size": NODE_PAGE_SIZE, "page": None, "nodes": [],
            "embedding": {"indexed_nodes": 0, "total_nodes": 0, "index_ready": False},
            "history": [], "open_review_tasks": 0, "can_review": row["can_review"],
            "can_submit": (row["can_edit"] and row["review_status"] == "draft"),
            "official_url": row["official_url"] if readable else None,
            "original_filename": row["original_filename"] if readable else None,
        }
        history = await conn.fetch(
            """SELECT a.action, a.occurred_at, u.display_name AS actor, a.metadata
               FROM audit_events a LEFT JOIN users u ON u.id = a.principal_id
               WHERE a.action LIKE 'document.%' AND (
                 (a.target_type = 'document' AND a.target_id = $1)
                 OR ($3 AND a.target_type = 'document_version' AND a.target_id = ANY($2::text[]))
               ) ORDER BY a.occurred_at DESC, a.id DESC LIMIT 50""",
            str(document_id), [str(item["id"]) for item in versions], readable,
        )
        result["history"] = [{**dict(item), "metadata": _json(item["metadata"])}
                             for item in history]
        if not readable:
            return result
        page = await conn.fetchrow(
            """SELECT page_number, COALESCE(text_original, '') AS text, extraction_method,
                      text_quality, reviewed_at IS NOT NULL AS reviewed,
                      ocr_diagnostics AS diagnostics
               FROM source_pages WHERE document_version_id=$1 AND page_number=$2""",
            version_id, page_number,
        )
        if page is not None:
            result["page"] = {**dict(page), "diagnostics": _json(page["diagnostics"])}
        nodes = await conn.fetch(
            """SELECT id, parent_id, node_type::text, COALESCE(citation_label, label_original) AS
                      label, path, text_original AS text, page_start, page_end
               FROM document_nodes WHERE document_version_id=$1 ORDER BY path, id
               LIMIT $2 OFFSET $3""", version_id, NODE_PAGE_SIZE,
            (node_page - 1) * NODE_PAGE_SIZE,
        )
        counts = await conn.fetchrow(
            """SELECT (SELECT count(*) FROM source_pages WHERE document_version_id=$1) AS pages,
                      (SELECT count(*) FROM curator_review_tasks
                       WHERE document_version_id=$1 AND status='open') AS tasks,
                      EXISTS (SELECT 1 FROM embedding_indices WHERE is_active
                              AND status='ready') AS index_ready,
                      count(n.id) AS nodes, count(e.document_node_id) AS indexed
               FROM document_nodes n
               LEFT JOIN node_embeddings e ON e.document_node_id = n.id
                 AND e.embedding_index_id = (SELECT id FROM embedding_indices
                                             WHERE is_active AND status='ready' LIMIT 1)
               WHERE n.document_version_id = $1""",
            version_id,
        )
        result.update(page_count=counts["pages"], node_count=counts["nodes"],
                      open_review_tasks=counts["tasks"], nodes=[dict(node) for node in nodes],
                      embedding={"indexed_nodes": counts["indexed"], "total_nodes": counts["nodes"],
                                 "index_ready": counts["index_ready"]})
        return result


async def original(
    pool: Any, principal: Principal, *, document_id: UUID, version_id: UUID,
    as_of: date, store_root: Path, max_bytes: int, pdf: bool, for_edit: bool = False,
) -> tuple[bytes, str, str]:
    async with pool.acquire() as conn:
        row = await _record(conn, principal, document_id, version_id, as_of)
    if not row["can_read"] or row["availability"] == "deleted":
        raise ReviewError("DOCUMENT_NOT_FOUND", 404)
    if for_edit and not row["can_edit"]:
        raise ReviewError("DOCUMENT_EDIT_DENIED", 403)
    source_format = "pdf" if pdf else row["source_format"]
    try:
        if source_format == "pdf":
            data = await asyncio.to_thread(
                read_immutable_pdf, store_root, row["original_file_path"],
                row["original_file_sha256"], max_bytes=max_bytes,
            )
        else:
            data = await asyncio.to_thread(
                read_immutable_source, store_root, source_format, row["source_file_sha256"],
                max_bytes=max_bytes,
            )
    except ValueError as exc:
        raise ReviewError("DRAFT_PDF_UNAVAILABLE", 503) from exc
    filename = f"{Path(row['original_filename']).stem}.pdf" if pdf else row["original_filename"]
    return data, source_format, filename
