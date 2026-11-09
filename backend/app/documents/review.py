"""Document review and approval workflow.

Enforces separation of duties: CURATOR prepares/submits drafts, REVIEWER resolves
review tasks and approves or rejects document versions. Approval verifies the
stored PDF hash, marks provenance as verified, approves document nodes, and
assigns categories so `authorized_nodes` can expose the version to authorized users.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from ..audit import append_audit
from ..effectivity.store import confirm_dates, detect_and_store_dates, process_approved_version
from .management_access import lock_review_version, managed_read_sql, version_scope
from .provenance import read_immutable_pdf

_LOG = logging.getLogger(__name__)


class ReviewError(Exception):
    def __init__(self, code: str, status_code: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


PAGE_TASK = re.compile(r"^page_(\d+)_(needs_review|needs_ocr)$")
PAGE_TASK_SQL = "^page_[0-9]+_(needs_review|needs_ocr)$"
PAGE_TEXT_PREVIEW = 8000


def _page_view(row: Any) -> dict[str, Any] | None:
    if row["page_number"] is None:
        return None
    diagnostics = row["ocr_diagnostics"]
    if isinstance(diagnostics, str):
        diagnostics = json.loads(diagnostics)
    text = row["page_text"] or ""
    return {
        "page_number": row["page_number"], "extraction_method": row["extraction_method"],
        "text_quality": row["text_quality"], "extraction_error": row["extraction_error"],
        "ocr_diagnostics": diagnostics, "text": text[:PAGE_TEXT_PREVIEW],
        "text_truncated": len(text) > PAGE_TEXT_PREVIEW,
        "reviewed_at": row["page_reviewed_at"].isoformat() if row["page_reviewed_at"] else None,
    }


async def list_review_tasks(
    pool: Any, *, version_id: UUID | None = None, status_filter: str | None = None,
    staff: tuple[UUID, bool, bool] | None = None,
) -> list[dict[str, Any]]:
    join, allowed = managed_read_sql(4) if staff else ('', '')
    async with pool.acquire() as connection:
        rows = await connection.fetch(
            f"""SELECT t.id, t.document_version_id, t.node_id, t.reason, t.risk,
                      t.status, t.created_at, t.resolved_by, t.resolved_at,
                      t.resolution_note, COALESCE(v.admin_metadata->>'title', d.title) AS title,
                      CASE WHEN v.admin_metadata IS NULL THEN d.document_number
                           ELSE v.admin_metadata->>'document_number' END AS document_number,
                      sp.page_number, sp.extraction_method, sp.text_quality,
                      sp.extraction_error, sp.ocr_diagnostics,
                      sp.text_original AS page_text, sp.reviewed_at AS page_reviewed_at
               FROM curator_review_tasks t
               JOIN document_versions v ON v.id = t.document_version_id
               JOIN documents d ON d.id = v.document_id
               {join}
               LEFT JOIN source_pages sp ON sp.document_version_id = t.document_version_id
                AND t.reason ~ $3
                AND sp.page_number = substring(t.reason FROM '^page_([0-9]+)_')::int
               WHERE ($1::uuid IS NULL OR t.document_version_id = $1)
                 AND ($2::text IS NULL OR t.status = $2)
                 AND d.deleted_at IS NULL {allowed}
               ORDER BY t.created_at ASC, t.id ASC""",
            version_id,
            status_filter,
            PAGE_TASK_SQL, *(staff or ()),
        )
    return [
        {
            "page": _page_view(row),
            "id": str(row["id"]),
            "document_version_id": str(row["document_version_id"]),
            "node_id": str(row["node_id"]) if row["node_id"] else None,
            "reason": row["reason"],
            "risk": row["risk"],
            "status": row["status"],
            "created_at": row["created_at"].isoformat(),
            "resolved_by": str(row["resolved_by"]) if row["resolved_by"] else None,
            "resolved_at": row["resolved_at"].isoformat() if row["resolved_at"] else None,
            "resolution_note": row["resolution_note"],
            "title": row["title"],
            "document_number": row["document_number"],
        }
        for row in rows
    ]


async def submit_draft_for_review(
    pool: Any, *, version_id: UUID, curator_id: UUID
) -> dict[str, Any]:
    async with pool.acquire() as connection, connection.transaction():
        row = await lock_review_version(connection, version_id)
        if row is None:
            raise ReviewError("DRAFT_NOT_FOUND", 404)
        if row["review_status"] not in {"draft", "pending_review"}:
            raise ReviewError("INVALID_REQUEST", 409)
        if row["admin_metadata"] is not None:
            scope = await version_scope(connection, version_id, curator_id,
                                        curator=True, reviewer=False)
            if not scope["can_read"] or row["submitted_by"] != curator_id:
                raise ReviewError("DOCUMENT_EDIT_DENIED", 403)
        await connection.execute(
            """UPDATE document_versions
               SET review_status = 'pending_review', submitted_by = COALESCE(submitted_by, $2)
               WHERE id = $1""",
            version_id,
            curator_id,
        )
        await append_audit(
            connection,
            principal_id=curator_id,
            action="document.submit_review",
            target_type="document_version",
            target_id=str(version_id),
        )
    return {"document_version_id": str(version_id), "status": "pending_review"}


async def resolve_review_task(
    pool: Any, *, task_id: UUID, reviewer_id: UUID, resolution_note: str
) -> dict[str, Any]:
    note = resolution_note.strip()
    if not note:
        raise ReviewError("INVALID_REQUEST", 422)
    async with pool.acquire() as connection, connection.transaction():
        version_id = await connection.fetchval(
            "SELECT document_version_id FROM curator_review_tasks WHERE id = $1", task_id
        )
        version = await lock_review_version(connection, version_id)
        if version is None:
            raise ReviewError("DRAFT_NOT_FOUND", 404)
        if version["review_status"] != "pending_review":
            raise ReviewError("INVALID_REVIEW_STATE", 409)
        await _check_reviewer(connection, version, reviewer_id)
        row = await connection.fetchrow(
            "SELECT id, document_version_id, status, reason "
            "FROM curator_review_tasks WHERE id = $1 FOR UPDATE",
            task_id,
        )
        if row is None:
            raise ReviewError("DRAFT_NOT_FOUND", 404)
        if row["status"] != "open":
            raise ReviewError("REVIEW_TASK_ALREADY_RESOLVED", 409)
        page_task = PAGE_TASK.match(row["reason"] or "")
        if page_task:
            # The reviewer compared this page's extracted (OCR) text with the scan.  Only
            # now may its text become evidence; the text itself is not changed here.
            page = await connection.fetchrow(
                """SELECT id, extraction_method, text_quality, ocr_diagnostics
                   FROM source_pages WHERE document_version_id = $1 AND page_number = $2
                   FOR UPDATE""",
                row["document_version_id"], int(page_task.group(1)),
            )
            if page is None:
                raise ReviewError("DRAFT_NOT_FOUND", 404)
            await connection.execute(
                """UPDATE source_pages SET text_quality = 'usable', reviewed_by = $2,
                     reviewed_at = now() WHERE id = $1""",
                page["id"], reviewer_id,
            )
            diagnostics = page["ocr_diagnostics"]
            if isinstance(diagnostics, str):
                diagnostics = json.loads(diagnostics)
            await append_audit(
                connection, principal_id=reviewer_id, action="document.confirm_page_text",
                target_type="source_page", target_id=str(page["id"]),
                metadata={"document_version_id": str(row["document_version_id"]),
                          "page_number": int(page_task.group(1)),
                          "extraction_method": page["extraction_method"],
                          "previous_quality": page["text_quality"],
                          "ocr_flags": (diagnostics or {}).get("flags", [])},
            )
        await connection.execute(
            """UPDATE curator_review_tasks
               SET status = 'resolved', resolved_by = $2, resolved_at = now(), resolution_note = $3
               WHERE id = $1""",
            task_id,
            reviewer_id,
            note,
        )
        await append_audit(
            connection,
            principal_id=reviewer_id,
            action="document.resolve_review_task",
            target_type="curator_review_task",
            target_id=str(task_id),
            metadata={"document_version_id": str(row["document_version_id"])},
        )
    return {"task_id": str(task_id), "status": "resolved"}


async def approve_document_version(
    pool: Any,
    *,
    store_root: Path,
    max_bytes: int,
    version_id: UUID,
    reviewer_id: UUID,
    category_ids: list[UUID],
    review_note: str,
    resolve_all_tasks: bool = False,
    publication_date: date | None = None,
    effective_from: date | None = None,
    revision: int | None = None,
) -> dict[str, Any]:
    if not category_ids:
        raise ReviewError("CATEGORY_REQUIRED", 422)
    note = review_note.strip()
    if not note:
        raise ReviewError("INVALID_DOCUMENT_METADATA", 422)
    now = datetime.now(UTC)
    async with pool.acquire() as connection, connection.transaction():
        row = await lock_review_version(connection, version_id)
        if row is None:
            raise ReviewError("DRAFT_NOT_FOUND", 404)
        if row["review_status"] != "pending_review" or row["submitted_by"] is None:
            raise ReviewError("INVALID_REVIEW_STATE", 409)
        await _check_reviewer(connection, row, reviewer_id)
        _check_revision(row, revision)
        if row["admin_metadata"] is not None:
            assigned = await connection.fetch(
                """SELECT dc.category_id FROM document_categories dc
                   JOIN categories c ON c.id = dc.category_id AND c.deleted_at IS NULL
                   WHERE dc.document_id=$1 FOR KEY SHARE OF c""", row["document_id"],
            )
            if assigned and {item["category_id"] for item in assigned} != set(category_ids):
                raise ReviewError("DOCUMENT_CATEGORIES_CHANGED", 409)
        try:
            await asyncio.to_thread(
                read_immutable_pdf,
                store_root,
                row["original_file_path"],
                row["original_file_sha256"],
                max_bytes=max_bytes,
            )
        except ValueError as exc:
            raise ReviewError("DRAFT_PDF_UNAVAILABLE", 503) from exc

        if resolve_all_tasks:
            # Page-text tasks (OCR, unreadable text layer) are confirmed page by page
            # against the scan; a bulk approval never confirms them.
            await connection.execute(
                """UPDATE curator_review_tasks
                   SET status = 'resolved', resolved_by = $2, resolved_at = $3,
                       resolution_note = COALESCE(resolution_note, $4)
                   WHERE document_version_id = $1 AND status = 'open'
                     AND reason !~ $5""",
                version_id,
                reviewer_id,
                now,
                note,
                PAGE_TASK_SQL,
            )
        open_tasks = await connection.fetchval(
            "SELECT count(*) FROM curator_review_tasks "
            "WHERE document_version_id = $1 AND status = 'open'",
            version_id,
        )
        if open_tasks and int(open_tasks) > 0:
            raise ReviewError("OPEN_REVIEW_TASKS_REMAIN", 409)

        # A page without text is accepted only when a reviewer confirmed it (a seal or
        # signature page the OCR could not read as text).
        unreadable_pages = await connection.fetchval(
            "SELECT count(*) FROM source_pages WHERE document_version_id = $1 "
            "AND (text_quality <> 'usable' OR ((text_original IS NULL OR text_original = '') "
            "AND reviewed_at IS NULL))",
            version_id,
        )
        node_count = await connection.fetchval(
            "SELECT count(*) FROM document_nodes WHERE document_version_id = $1", version_id
        )
        if unreadable_pages or not node_count:
            raise ReviewError("DOCUMENT_TEXT_NOT_READY", 409)
        # Every node, including one that continues across pages, must match its
        # page text exactly span by span (migration 0009).
        invalid_spans = await connection.fetchval(
            """SELECT count(*) FROM document_nodes n
               WHERE n.document_version_id = $1 AND NOT node_source_text_valid(n.id)""",
            version_id,
        )
        if invalid_spans:
            raise ReviewError("SOURCE_SPANS_REQUIRE_REVIEW", 409)

        found_cats = await connection.fetchval(
            "SELECT count(*) FROM categories WHERE id = ANY($1::uuid[]) AND deleted_at IS NULL",
            category_ids,
        )
        if int(found_cats or 0) != len(set(category_ids)):
            raise ReviewError("CATEGORY_NOT_FOUND", 404)

        for cat_id in set(category_ids):
            await connection.execute(
                """INSERT INTO document_categories (document_id, category_id)
                   VALUES ($1, $2) ON CONFLICT DO NOTHING""",
                row["document_id"],
                cat_id,
            )

        if row["admin_metadata"] is not None:
            await _publish_managed_version(connection, row)
        await connection.execute(
            """UPDATE document_versions
               SET review_status = 'approved', reviewed_by = $2, reviewed_at = $3,
                   review_note = $4, source_review_revision = source_review_revision + 1
               WHERE id = $1""",
            version_id,
            reviewer_id,
            now,
            note,
        )
        await connection.execute(
            """UPDATE source_provenance
               SET authenticity_reviewer = $2, verified_at = $3,
                   fetched_checksum = COALESCE(fetched_checksum, $4)
               WHERE document_version_id = $1""",
            version_id,
            reviewer_id,
            now,
            row["original_file_sha256"],
        )
        approved_nodes = await connection.fetchval(
            """WITH updated AS (
                 UPDATE document_nodes SET review_status = 'approved'
                 WHERE document_version_id = $1 RETURNING 1
               ) SELECT count(*) FROM updated""",
            version_id,
        )
        # G1: confirm the dates read by rule (or the reviewer's correction), then
        # read relations, retry "not in the store yet" targets and publish the
        # effectivity snapshot.  A failure here never blocks the source approval.
        effectivity: dict[str, Any] = {}
        try:
            async with connection.transaction():
                if not await connection.fetchval(
                    "SELECT dates_detected <> '{}'::jsonb FROM document_versions WHERE id = $1",
                    version_id,
                ):
                    await detect_and_store_dates(connection, version_id)
                await confirm_dates(
                    connection, version_id, reviewer_id,
                    publication_date=publication_date, effective_from=effective_from,
                )
                if row["admin_metadata"] is not None and row["based_on_version_id"] is None:
                    await connection.execute(
                        """UPDATE document_versions SET valid_from=COALESCE(
                             valid_from, publication_date, reviewed_at::date)
                           WHERE id=$1 AND version_number>1""", version_id,
                    )
                effectivity = await process_approved_version(
                    connection, version_id, actor_id=reviewer_id
                )
        except Exception:  # noqa: BLE001 - logged; approval stands without relations
            _LOG.warning("effectivity processing failed after approval", exc_info=True)
            if row["admin_metadata"] is not None:
                raise ReviewError("EFFECTIVITY_PROCESSING_FAILED", 503) from None
            effectivity = {"error": "EFFECTIVITY_PROCESSING_FAILED"}
        await append_audit(
            connection,
            principal_id=reviewer_id,
            action="document.approve_version",
            target_type="document_version",
            target_id=str(version_id),
            metadata={
                "document_id": str(row["document_id"]),
                "category_ids": [str(c) for c in set(category_ids)],
                "approved_nodes": int(approved_nodes or 0),
                "effectivity": effectivity,
            },
        )
    return {
        "document_id": str(row["document_id"]),
        "document_version_id": str(version_id),
        "status": "approved",
        "approved_nodes": int(approved_nodes or 0),
        "effectivity": effectivity,
    }


async def _check_reviewer(connection: Any, version: Any, reviewer_id: UUID) -> None:
    if version["submitted_by"] == reviewer_id:
        raise ReviewError("SELF_APPROVAL_DENIED", 403)
    if version["admin_metadata"] is not None:
        scope = await version_scope(connection, version["id"], reviewer_id,
                                    curator=False, reviewer=True)
        if not scope["can_read"] or not scope["can_review_all"]:
            raise ReviewError("DOCUMENT_REVIEW_SCOPE_REQUIRED", 403)


def _check_revision(version: Any, revision: int | None) -> None:
    if revision != version["source_review_revision"] and (
        revision is not None or version["admin_metadata"] is not None
    ):
        raise ReviewError("DOCUMENT_REVISION_CONFLICT", 409)


async def _publish_managed_version(connection: Any, version: Any) -> None:
    metadata = version["admin_metadata"]
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    await connection.execute(
        """UPDATE documents SET title=$2, doc_type=$3, document_number=$4, issuing_body=$5
           WHERE id=$1""",
        version["document_id"], metadata["title"], metadata["doc_type"],
        metadata["document_number"], metadata["issuing_body"],
    )
    if version["based_on_version_id"] is not None:
        # Corrections replace the reviewed interpretation of the same source.
        # Earlier distinct originals remain available to historical queries.
        await connection.execute(
            """UPDATE document_versions SET retired_at=now()
               WHERE document_id=$1 AND original_file_sha256=$2 AND id<>$3
                 AND review_status='approved' AND retired_at IS NULL""",
            version["document_id"], version["original_file_sha256"], version["id"],
        )
        await _reopen_node_effectivity(connection, version)


async def _reopen_node_effectivity(connection: Any, version: Any) -> None:
    # A relation reviewed against an earlier tree cannot silently change which
    # text it affects. Carry it into the existing review queue and preserve
    # the original approved record as history.
    retired_nodes = """
        SELECT n.id, regexp_replace(n.path, '^[0-9]+:?', '') AS legal_path
        FROM document_nodes n JOIN document_versions v ON v.id=n.document_version_id
        WHERE v.document_id=$1 AND v.original_file_sha256=$2 AND v.retired_at IS NOT NULL
    """
    await connection.execute(
        f"""WITH retired AS ({retired_nodes}), pending AS MATERIALIZED (
              SELECT a.*, gen_random_uuid() AS next_id, replacement.id AS next_node,
                     retired.legal_path, sn.document_id AS originating_document
              FROM node_amendments a JOIN retired ON retired.id=a.target_node_id
              JOIN document_nodes sn ON sn.id=a.source_node_id
              JOIN document_versions sv ON sv.id=sn.document_version_id
              LEFT JOIN LATERAL (
                SELECT (array_agg(n.id))[1] AS id FROM document_nodes n
                WHERE n.document_version_id=$3 AND retired.legal_path<>''
                  AND regexp_replace(n.path, '^[0-9]+:?', '')=retired.legal_path
                HAVING count(*)=1
              ) replacement ON TRUE
              WHERE a.superseded_by IS NULL AND a.review_status<>'rejected'
                AND sv.retired_at IS NULL
              FOR UPDATE OF a
            ), reopened AS (
              INSERT INTO node_amendments
                (id, source_node_id, source_document_id, target_document_id, target_node_id,
                 scope, action, valid_from, valid_to, evidence_source, target_number,
                 target_doc_type, target_issue_date, target_path, target_expression,
                 resolution_state, condition_text, proposed_by, source_quote, source_page)
              SELECT next_id, source_node_id, COALESCE(source_document_id, originating_document),
                     $1, next_node, 'node', action, valid_from, valid_to, evidence_source,
                     target_number, target_doc_type, target_issue_date,
                     COALESCE(target_path, NULLIF(legal_path,'')), target_expression,
                     CASE WHEN next_node IS NULL THEN 'unresolved' ELSE 'resolved' END,
                     condition_text, 'rule', source_quote, source_page
              FROM pending RETURNING id
            )
            UPDATE node_amendments a SET superseded_by=p.next_id
            FROM pending p JOIN reopened r ON r.id=p.next_id WHERE a.id=p.id""",
        version["document_id"], version["original_file_sha256"], version["id"],
    )
    await connection.execute(
        f"""WITH retired AS ({retired_nodes})
            UPDATE effectivity_attestations a
            SET status='needs_reverify', status_reason='document_version_corrected',
                status_changed_at=now()
            FROM retired
            WHERE a.target_node_id=retired.id AND a.status='valid' AND a.superseded_by IS NULL""",
        version["document_id"], version["original_file_sha256"],
    )


async def reject_document_version(
    pool: Any, *, version_id: UUID, reviewer_id: UUID, review_note: str,
    revision: int | None = None,
) -> dict[str, Any]:
    note = review_note.strip()
    if not note:
        raise ReviewError("INVALID_DOCUMENT_METADATA", 422)
    async with pool.acquire() as connection, connection.transaction():
        row = await lock_review_version(connection, version_id)
        if row is None:
            raise ReviewError("DRAFT_NOT_FOUND", 404)
        if row["review_status"] != "pending_review":
            raise ReviewError("INVALID_REVIEW_STATE", 409)
        await _check_reviewer(connection, row, reviewer_id)
        _check_revision(row, revision)
        await connection.execute(
            """UPDATE document_versions
               SET review_status = 'rejected', reviewed_by = $2, reviewed_at = now(),
                   review_note = $3
               WHERE id = $1""",
            version_id,
            reviewer_id,
            note,
        )
        await connection.execute(
            "UPDATE document_nodes SET review_status = 'rejected' WHERE document_version_id = $1",
            version_id,
        )
        await append_audit(
            connection,
            principal_id=reviewer_id,
            action="document.reject_version",
            target_type="document_version",
            target_id=str(version_id),
            metadata={"reason": note, "document_id": str(row["document_id"])},
        )
    return {"document_version_id": str(version_id), "status": "rejected"}
