"""Read unapproved draft metadata and its hash-checked original PDF."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from uuid import UUID

from ..schemas import PdfDraftListItem
from .management_access import managed_read_sql
from .provenance import read_immutable_pdf


async def list_document_drafts(
    pool: Any, *, limit: int, offset: int, staff: tuple[UUID, bool, bool] | None = None,
) -> list[PdfDraftListItem]:
    join, allowed = managed_read_sql(3) if staff else ("", "")
    async with pool.acquire() as connection:
        rows = await connection.fetch(
            f"""SELECT d.id AS document_id, v.id AS document_version_id,
                      COALESCE(v.admin_metadata->>'title', d.title) AS title,
                      COALESCE(v.admin_metadata->>'doc_type', d.doc_type) AS doc_type,
                      CASE WHEN v.admin_metadata IS NULL THEN d.document_number
                           ELSE v.admin_metadata->>'document_number' END AS document_number,
                      v.source_review_revision,
                      v.review_status::text AS status, v.original_file_sha256 AS sha256,
                      (SELECT count(*) FROM source_pages p
                       WHERE p.document_version_id = v.id) AS page_count,
                      (SELECT count(*) FROM curator_review_tasks t
                       WHERE t.document_version_id = v.id AND t.status = 'open')
                         AS open_review_tasks,
                      v.dates_detected->>'issue_date' AS detected_issue_date,
                      v.dates_detected->>'effective_from' AS detected_effective_from,
                      v.dates_detected->>'effective_quote' AS detected_effective_quote
               FROM document_versions v
               JOIN documents d ON d.id = v.document_id
               {join}
               WHERE v.review_status IN ('draft', 'pending_review')
                 AND d.deleted_at IS NULL {allowed}
               ORDER BY v.captured_at DESC NULLS LAST, v.id
               LIMIT $1 OFFSET $2""",
            min(max(limit, 1), 100), max(offset, 0), *(staff or ()),
        )
    return [PdfDraftListItem.model_validate(dict(row)) for row in rows]


async def load_draft_pdf(
    pool: Any, *, store_root: Path, version_id: UUID, max_bytes: int,
    staff: tuple[UUID, bool, bool] | None = None, legacy_reextract: bool = False,
) -> bytes:
    join, allowed = managed_read_sql(2) if staff else ("", "")
    if legacy_reextract:
        allowed += " AND v.admin_metadata IS NULL"
    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            f"""SELECT v.original_file_path, v.original_file_sha256
               FROM document_versions v
               JOIN documents d ON d.id = v.document_id
               {join}
               WHERE v.id = $1 AND v.review_status IN ('draft', 'pending_review')
                 AND d.deleted_at IS NULL {allowed}""",
            version_id, *(staff or ()),
        )
    if row is None:
        raise KeyError("DRAFT_NOT_FOUND")
    try:
        return await asyncio.to_thread(
            read_immutable_pdf,
            store_root, row["original_file_path"], row["original_file_sha256"],
            max_bytes=max_bytes,
        )
    except ValueError as exc:
        raise ValueError("DRAFT_STORAGE_CONFLICT") from exc
