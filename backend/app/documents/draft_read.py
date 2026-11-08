"""Read unapproved draft metadata and its hash-checked original PDF."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from uuid import UUID

from ..schemas import PdfDraftListItem
from .provenance import read_immutable_pdf


async def list_document_drafts(pool: Any, *, limit: int, offset: int) -> list[PdfDraftListItem]:
    async with pool.acquire() as connection:
        rows = await connection.fetch(
            """SELECT d.id AS document_id, dv.id AS document_version_id,
                      d.title, d.doc_type, d.document_number,
                      dv.review_status::text AS status, dv.original_file_sha256 AS sha256,
                      (SELECT count(*) FROM source_pages p
                       WHERE p.document_version_id = dv.id) AS page_count,
                      (SELECT count(*) FROM curator_review_tasks t
                       WHERE t.document_version_id = dv.id AND t.status = 'open')
                         AS open_review_tasks,
                      dv.dates_detected->>'issue_date' AS detected_issue_date,
                      dv.dates_detected->>'effective_from' AS detected_effective_from,
                      dv.dates_detected->>'effective_quote' AS detected_effective_quote
               FROM document_versions dv
               JOIN documents d ON d.id = dv.document_id
               WHERE dv.review_status IN ('draft', 'pending_review')
                 AND d.deleted_at IS NULL
               ORDER BY dv.captured_at DESC NULLS LAST, dv.id
               LIMIT $1 OFFSET $2""",
            min(max(limit, 1), 100), max(offset, 0),
        )
    return [PdfDraftListItem.model_validate(dict(row)) for row in rows]


async def load_draft_pdf(
    pool: Any, *, store_root: Path, version_id: UUID, max_bytes: int
) -> bytes:
    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            """SELECT dv.original_file_path, dv.original_file_sha256
               FROM document_versions dv
               JOIN documents d ON d.id = dv.document_id
               WHERE dv.id = $1 AND dv.review_status IN ('draft', 'pending_review')
                 AND d.deleted_at IS NULL""",
            version_id,
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
