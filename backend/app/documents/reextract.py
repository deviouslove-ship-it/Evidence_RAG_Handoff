"""Rebuild missing draft source text from a verified original PDF."""

import json
from typing import Any
from uuid import UUID

from ..audit import append_audit
from .deduplication import content_fingerprint, find_content_matches
from .draft import PreparedDraft
from .node_writer import delete_version_nodes, write_nodes
from .review import ReviewError


async def apply_reextracted_draft(
    pool: Any, *, prepared: PreparedDraft, version_id: UUID, curator_id: UUID,
) -> dict[str, int | str]:
    async with pool.acquire() as conn, conn.transaction():
        version = await conn.fetchrow(
            """SELECT id, review_status, original_file_sha256, native_text_fingerprint_v1
               FROM document_versions WHERE id=$1 FOR UPDATE""", version_id,
        )
        if version is None:
            raise ReviewError("DRAFT_NOT_FOUND", 404)
        if version["review_status"] not in {"draft", "pending_review"}:
            raise ReviewError("INVALID_REVIEW_STATE", 409)
        if version["original_file_sha256"] != prepared.sha256:
            raise ReviewError("SOURCE_REEXTRACTION_CONFLICT", 409)

        pages = await conn.fetch(
            """SELECT id, page_number, text_original FROM source_pages
               WHERE document_version_id=$1 ORDER BY page_number FOR UPDATE""", version_id,
        )
        by_number = {page.page_number: page for page in prepared.pages}
        if len(by_number) != len(prepared.pages) or len(pages) != len(by_number) or any(
            row["page_number"] not in by_number for row in pages
        ):
            raise ReviewError("SOURCE_REEXTRACTION_CONFLICT", 409)

        page_ids: dict[int, UUID] = {}
        pages_restored = 0
        for row in pages:
            extracted = by_number[row["page_number"]]
            page_ids[row["page_number"]] = row["id"]
            if row["text_original"] is not None:
                if row["text_original"] != extracted.text:
                    raise ReviewError("SOURCE_REEXTRACTION_CONFLICT", 409)
                continue
            await conn.execute(
                """UPDATE source_pages SET text_original=$2, extraction_method=$3,
                   text_quality=$4, extraction_error=$5, ocr_diagnostics=$6::jsonb,
                   reviewed_by=NULL, reviewed_at=NULL WHERE id=$1""",
                row["id"], extracted.text, extracted.extraction_method,
                extracted.text_quality, extracted.extraction_error,
                json.dumps(extracted.ocr_diagnostics, ensure_ascii=False)
                if extracted.ocr_diagnostics is not None else None,
            )
            pages_restored += 1

        # A draft's tree is rebuilt as a whole (parent links, page-by-page spans)
        # whenever any node no longer matches its page text, the page text was
        # restored, or the parser now yields a different number of nodes.
        state = await conn.fetchrow(
            """SELECT count(*) AS total,
                      count(*) FILTER (WHERE NOT node_source_text_valid(n.id)) AS invalid
               FROM document_nodes n WHERE n.document_version_id=$1""",
            version_id,
        )
        anchored = unresolved = invalidated = 0
        if pages_restored or state["invalid"] or state["total"] != len(prepared.nodes):
            document = await conn.fetchrow(
                """SELECT d.id, d.title, d.document_number FROM documents d
                   JOIN document_versions dv ON dv.document_id = d.id WHERE dv.id=$1""",
                version_id,
            )
            # A rebuild always counts as a change: review must start again.
            invalidated = max(int(state["invalid"]), 1)
            await delete_version_nodes(conn, version_id)
            anchored, unresolved = await write_nodes(
                conn, document_id=document["id"], version_id=version_id,
                title=document["title"], document_number=document["document_number"],
                page_ids=page_ids,
                page_texts={page.page_number: page.text for page in prepared.pages},
                nodes=prepared.nodes,
            )
        fingerprint = content_fingerprint(prepared.pages)
        previous_fingerprint = version["native_text_fingerprint_v1"]
        if previous_fingerprint is not None and previous_fingerprint != fingerprint:
            raise ReviewError("SOURCE_REEXTRACTION_CONFLICT", 409)
        matches = await find_content_matches(
            conn, fingerprint=fingerprint, viewer_id=curator_id, exclude_version_id=version_id,
        ) if fingerprint is not None else []
        if fingerprint is not None and previous_fingerprint is None:
            await conn.execute(
                "UPDATE document_versions SET native_text_fingerprint_v1=$2 WHERE id=$1",
                version_id, fingerprint,
            )
        changed = pages_restored + anchored + invalidated
        if changed:
            await conn.execute(
                "UPDATE document_versions SET source_review_revision=source_review_revision+1 "
                "WHERE id=$1", version_id,
            )
            await conn.execute(
                "UPDATE source_provenance SET verified_at=NULL WHERE document_version_id=$1",
                version_id,
            )
            await conn.execute(
                "UPDATE document_nodes SET review_status='draft' WHERE document_version_id=$1",
                version_id,
            )
            await _ensure_open_task(conn, version_id, "source_reextraction_review")
        if unresolved:
            await _ensure_open_task(conn, version_id, "unanchored_source_spans")
        if matches:
            await _ensure_open_task(conn, version_id, "possible_duplicate_content")
        await append_audit(
            conn, principal_id=curator_id, action="document.reextract_source",
            target_type="document_version", target_id=str(version_id),
            metadata={"pages_restored": pages_restored, "nodes_anchored": anchored,
                      "nodes_unresolved": unresolved, "possible_duplicates": len(matches)},
        )
    return {"status": "draft_updated", "pages_restored": pages_restored,
            "nodes_anchored": anchored, "nodes_unresolved": unresolved,
            "possible_duplicates": len(matches)}


async def _ensure_open_task(connection: Any, version_id: UUID, reason: str) -> None:
    await connection.execute(
        """INSERT INTO curator_review_tasks (document_version_id, reason, risk)
           SELECT $1, $2, 'high' WHERE NOT EXISTS (
             SELECT 1 FROM curator_review_tasks
             WHERE document_version_id=$1 AND reason=$2 AND status='open')""",
        version_id, reason,
    )
