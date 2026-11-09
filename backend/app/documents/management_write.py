"""Transactional document edits, version creation and operational lifecycle."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import date
from typing import Any, Literal
from uuid import UUID

from ..audit import append_audit
from ..auth_acl.policy import Principal
from ..effectivity.store import detect_and_store_dates
from .deduplication import content_fingerprint
from .draft import PreparedDraft, validate_source_url
from .management_access import lock_review_version
from .management_read import _METADATA_FIELDS, _record
from .native_pdf import ExtractedPage, max_document_characters
from .node_writer import delete_version_nodes, suspect_text_layer, write_nodes
from .review import PAGE_TASK_SQL, ReviewError
from .tree_parser import parse_legal_tree

DocumentAction = Literal["suspend", "resume", "delete", "restore"]

_ACTIONS = {
    "suspend": ("suspended_at = now()", "suspended_at IS NULL AND deleted_at IS NULL"),
    "resume": ("suspended_at = NULL", "suspended_at IS NOT NULL AND deleted_at IS NULL"),
    "delete": ("deleted_at = now()", "deleted_at IS NULL"),
    "restore": ("deleted_at = NULL", "deleted_at IS NOT NULL"),
}


async def change_availability(
    pool: Any, *, actor_id: UUID, document_ids: list[UUID], action: DocumentAction, reason: str,
) -> int:
    assignments, condition = _ACTIONS[action]
    async with pool.acquire() as conn, conn.transaction():
        locked = await conn.fetch(
            "SELECT id FROM documents WHERE id=ANY($1::uuid[]) ORDER BY id FOR UPDATE",
            document_ids,
        )
        if len(locked) != len(set(document_ids)):
            raise ReviewError("DOCUMENT_NOT_FOUND", 404)
        changed = await conn.fetch(
            f"UPDATE documents SET {assignments} WHERE id=ANY($1::uuid[]) AND {condition} "
            "RETURNING id",
            document_ids,
        )
        for row in sorted(changed, key=lambda item: item["id"]):
            await append_audit(conn, principal_id=actor_id, action=f"document.{action}",
                               target_type="document", target_id=str(row["id"]),
                               metadata={"reason": reason})
    return len(changed)


def _page(row: Any) -> ExtractedPage:
    diagnostics = row["ocr_diagnostics"]
    return ExtractedPage(
        row["page_number"], float(row["width"]), float(row["height"]), row["rotation"],
        row["text_original"] or "", (), row["extraction_method"], row["text_quality"],
        row["extraction_error"], json.loads(diagnostics) if isinstance(diagnostics, str)
        else diagnostics,
    )


async def _new_revision(conn: Any, version: Any, metadata: dict[str, Any], actor: UUID) -> UUID:
    base_id = version["id"]
    await conn.execute(
        """UPDATE document_versions SET admin_metadata = COALESCE(admin_metadata, $2::jsonb)
           WHERE id=$1""", base_id, json.dumps(metadata, ensure_ascii=False),
    )
    new_id: UUID = await conn.fetchval(
        """INSERT INTO document_versions
              (document_id, version_number, based_on_version_id, original_file_path,
               original_file_sha256, original_filename, captured_at, source_format,
               source_file_sha256, native_text_fingerprint_v1, official_url, publication_date,
               effective_from, valid_from, valid_to, submitted_by, source_review_revision)
           SELECT document_id, version_number+1, id, original_file_path,
                  original_file_sha256, original_filename, captured_at, source_format,
                  source_file_sha256, native_text_fingerprint_v1, official_url, publication_date,
                  effective_from, valid_from, valid_to, $2, source_review_revision
           FROM document_versions WHERE id=$1 RETURNING id""",
        base_id, actor,
    )
    await conn.execute(
        """INSERT INTO source_pages
             (document_version_id, page_number, width, height, rotation, crop_box, media_box,
              extraction_method, text_quality, text_original, extraction_error, ocr_diagnostics,
              reviewed_by, reviewed_at)
           SELECT $2, page_number, width, height, rotation, crop_box, media_box,
                  extraction_method, text_quality, text_original, extraction_error,
                  ocr_diagnostics, reviewed_by, reviewed_at
           FROM source_pages WHERE document_version_id=$1""",
        base_id, new_id,
    )
    await conn.execute(
        """INSERT INTO source_provenance
             (document_version_id, official_url, publisher_domain, captured_at, redirect_chain,
              fetched_checksum)
           SELECT $2, official_url, publisher_domain, captured_at, redirect_chain, fetched_checksum
           FROM source_provenance WHERE document_version_id=$1""",
        base_id, new_id,
    )
    return new_id


async def _record_ocr_edits(
    conn: Any, version_id: UUID, actor: UUID, before: dict[int, Any], pages: list[ExtractedPage],
) -> None:
    edits = [(version_id, page.page_number, before[page.page_number]["text_original"],
              page.text, actor) for page in pages
             if before[page.page_number]["text_original"] != page.text]
    if edits:
        await conn.executemany(
            """INSERT INTO document_ocr_edits
                 (document_version_id, page_number, previous_text, corrected_text, edited_by)
               VALUES ($1, $2, $3, $4, $5)""", edits,
        )


async def change_version(
    pool: Any, principal: Principal, document_id: UUID, version_id: UUID, *,
    revision: int, changes: dict[str, Any], ocr_page: tuple[int, str] | None,
    prepared: PreparedDraft | None, as_of: date,
) -> dict[str, Any]:
    actor = UUID(principal.id)
    async with pool.acquire() as conn, conn.transaction():
        version = await lock_review_version(conn, version_id)
        if version is None or version["document_id"] != document_id:
            raise ReviewError("DOCUMENT_NOT_FOUND", 404)
        row = await _record(conn, principal, document_id, version_id, as_of)
        if version["source_review_revision"] != revision:
            raise ReviewError("DOCUMENT_REVISION_CONFLICT", 409)
        if not row["can_edit"]:
            if row["can_read"] and row["version_number"] != await conn.fetchval(
                "SELECT max(version_number) FROM document_versions WHERE document_id=$1",
                document_id,
            ):
                raise ReviewError("DOCUMENT_REVISION_CONFLICT", 409)
            raise ReviewError("DOCUMENT_EDIT_DENIED", 403)

        previous_metadata = {key: row[key] for key in _METADATA_FIELDS}
        metadata = {**previous_metadata, **{k: v for k, v in changes.items()
                                           if k in _METADATA_FIELDS}}
        official_url, domain = validate_source_url(changes.get("official_url", row["official_url"]))
        rows = await conn.fetch(
            "SELECT * FROM source_pages WHERE document_version_id=$1 ORDER BY page_number",
            version_id,
        )
        previous_pages = {item["page_number"]: item for item in rows}
        if not rows:
            raise ReviewError("DOCUMENT_TEXT_NOT_READY", 409)
        pages = [_page(item) for item in rows]
        changed_pages: list[ExtractedPage] = []
        if prepared is not None:
            if (prepared.sha256 != version["original_file_sha256"]
                    or [page.page_number for page in prepared.pages] != list(previous_pages)):
                raise ReviewError("SOURCE_REEXTRACTION_CONFLICT", 409)
            pages = changed_pages = prepared.pages
        elif ocr_page is not None:
            number, correction = ocr_page
            current = previous_pages.get(number)
            if current is None:
                raise ReviewError("DOCUMENT_NOT_FOUND", 404)
            if (current["extraction_method"] != "local_ocr"
                    and current["text_quality"] != "needs_ocr"):
                raise ReviewError("OCR_EDIT_DENIED", 409)
            changed_pages = [replace(_page(current), text=correction, extraction_method="local_ocr",
                                     text_quality="needs_review", extraction_error=None,
                                     ocr_diagnostics=None)]
            pages = [changed_pages[0] if page.page_number == number else page for page in pages]
        elif any(item["text_original"] is None and item["text_quality"] == "usable"
                 and item["reviewed_at"] is None for item in rows):
            raise ReviewError("DOCUMENT_REPROCESS_REQUIRED", 409)
        if sum(len(page.text) for page in pages) > max_document_characters():
            raise ReviewError("PDF_RESOURCE_LIMIT_EXCEEDED", 413)

        version_is_new = version["review_status"] in {"approved", "rejected"}
        target_id = version_id
        if version_is_new:
            target_id = await _new_revision(conn, version, previous_metadata, actor)
        else:
            await delete_version_nodes(conn, version_id)

        await _record_ocr_edits(conn, target_id, actor, previous_pages, changed_pages)
        await conn.executemany(
            """UPDATE source_pages SET extraction_method=$3, text_quality=$4, text_original=$5,
                 extraction_error=$6, ocr_diagnostics=$7::jsonb, reviewed_by=NULL, reviewed_at=NULL
               WHERE document_version_id=$1 AND page_number=$2""",
            [(target_id, page.page_number, page.extraction_method, page.text_quality,
              page.text, page.extraction_error, json.dumps(page.ocr_diagnostics)
              if page.ocr_diagnostics is not None else None) for page in changed_pages],
        )
        if changed_pages:
            # A draft's old whole-page spans refer to the old text. New legal
            # nodes will write their own exact spans below.
            await conn.execute(
                """DELETE FROM source_spans WHERE page_id IN (SELECT id FROM source_pages
                   WHERE document_version_id=$1 AND page_number=ANY($2::int[]))""",
                target_id, [page.page_number for page in changed_pages],
            )
        page_ids = {item["page_number"]: item["id"] for item in await conn.fetch(
            "SELECT id, page_number FROM source_pages WHERE document_version_id=$1", target_id,
        )}
        fingerprint = (content_fingerprint(prepared.pages) if prepared is not None
                       else version["native_text_fingerprint_v1"])
        next_revision = await conn.fetchval(
            """UPDATE document_versions
               SET review_status='draft', admin_metadata=$2::jsonb, submitted_by=$3,
                   official_url=$4, publication_date=$5, effective_from=$6,
                   dates_confirmed_at=NULL, dates_confirmed_by=NULL,
                   source_review_revision=source_review_revision+1,
                   native_text_fingerprint_v1=$7
               WHERE id=$1 RETURNING source_review_revision""",
            target_id, json.dumps(metadata, ensure_ascii=False), actor, official_url,
            changes.get("publication_date", row["publication_date"]),
            changes.get("effective_from", row["effective_from"]),
            fingerprint,
        )
        await conn.execute(
            """INSERT INTO source_provenance
                 (document_version_id, official_url, publisher_domain, fetched_checksum)
               VALUES ($1, $2, $3, $4) ON CONFLICT (document_version_id) DO UPDATE
               SET official_url=$2, publisher_domain=$3, verified_at=NULL,
                   authenticity_reviewer=NULL""",
            target_id, official_url, domain, version["original_file_sha256"],
        )
        nodes = prepared.nodes if prepared else await asyncio.to_thread(parse_legal_tree, pages)
        _, unanchored = await write_nodes(
            conn, document_id=document_id, version_id=target_id, title=metadata["title"],
            document_number=metadata["document_number"], page_ids=page_ids,
            page_texts={page.page_number: page.text for page in pages}, nodes=nodes,
        )
        await detect_and_store_dates(conn, target_id)
        await _review_tasks(conn, version_id, target_id, pages, changed_pages, unanchored)
        await append_audit(
            conn, principal_id=actor,
            action="document.reprocess" if prepared else "document.edit",
            target_type="document_version", target_id=str(target_id),
            metadata={
                "document_id": str(document_id), "base_version_id": str(version_id),
                "revision": next_revision, "pages": [page.page_number for page in changed_pages],
                "changes": {
                    key: {"from": str(row[key]) if isinstance(row[key], date) else row[key],
                          "to": str(value) if isinstance(value, date) else value}
                    for key, value in changes.items() if row[key] != value
                },
            },
        )
    return {"version_id": target_id, "revision": next_revision, "status": "draft"}


async def _review_tasks(
    conn: Any, base_id: UUID, target_id: UUID, pages: list[ExtractedPage],
    changed_pages: list[ExtractedPage], unanchored: int,
) -> None:
    changed_numbers = {page.page_number for page in changed_pages}
    reasons = {"metadata_and_source_verification"}
    if unanchored:
        reasons.add("unanchored_source_spans")
    if base_id != target_id:
        reasons.update(await conn.fetchval(
            """SELECT COALESCE(array_agg(DISTINCT reason), '{}') FROM curator_review_tasks
               WHERE document_version_id=$1 AND status='open' AND reason !~ $2
                 AND reason <> 'unanchored_source_spans'""", base_id, PAGE_TASK_SQL,
        ))
    elif changed_numbers:
        # Replace the open task ID, so a stale review tab cannot confirm the new text.
        await conn.execute(
            """DELETE FROM curator_review_tasks
               WHERE document_version_id=$1 AND status='open'
                 AND (reason ~ $2 AND substring(reason FROM '^page_([0-9]+)_')::int
                      = ANY($3::int[]) OR reason='unanchored_source_spans')""",
            target_id, PAGE_TASK_SQL, sorted(changed_numbers),
        )
    for page in pages:
        if page.text_quality in {"needs_review", "needs_ocr"}:
            reasons.add(f"page_{page.page_number}_{page.text_quality}")
        elif page.page_number in changed_numbers and suspect_text_layer(page.text):
            reasons.add(f"page_{page.page_number}_text_layer_suspect")
    await conn.executemany(
        """INSERT INTO curator_review_tasks (document_version_id, reason, risk)
           SELECT $1, $2, 'high' WHERE NOT EXISTS (
             SELECT 1 FROM curator_review_tasks
             WHERE document_version_id=$1 AND reason=$2 AND status='open')""",
        [(target_id, reason) for reason in sorted(reasons)],
    )
