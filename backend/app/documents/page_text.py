"""User-facing verified page reading and ephemeral OCR AI fallback."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from ..auth_acl.policy import Permission, Principal
from .ocr_ai import (
    DEFAULT_RENDER_DPI,
    DEFAULT_RENDER_MAX_BYTES,
    DEFAULT_RENDER_MAX_EDGE,
    PROMPT_VERSION,
)
from .ocr_ai_store import MAX_QUEUED_OCR_TASKS, expire_user_tasks, page_text_sha256
from .provenance import read_immutable_pdf
from .review import ReviewError

USER_PAGE_TEXT_TTL_MINUTES = 60
_QUEUE_LOCK_KEY = 7_302_026_101
_DEFAULT_MAX_PDF_BYTES = 32 * 1024 * 1024


def _unverified_warning(page_number: int) -> str:
    return f"AI đọc từ ảnh trang {page_number} — chưa đối chiếu thủ công"


def _pdf_url(document_id: UUID, version_id: UUID) -> str:
    return f"/api/v1/documents/{document_id}/versions/{version_id}/pdf"


async def _load_user_accessible_version(
    conn: Any,
    principal: Principal,
    document_id: UUID,
    version_id: UUID,
) -> Any:
    if not principal.has(Permission.QUERY):
        raise ReviewError("QUERY_REQUIRED", 403)
    user_uuid = UUID(principal.id)
    await conn.execute("SELECT set_config('app.user_id', $1, true)", str(user_uuid))
    row = await conn.fetchrow(
        """SELECT dv.id, dv.document_id, dv.source_review_revision,
                  dv.original_file_path, dv.original_file_sha256, dv.source_format,
                  d.title, d.document_number
           FROM document_versions dv
           JOIN documents d ON d.id = dv.document_id
           JOIN source_provenance prov
             ON prov.document_version_id = dv.id AND prov.verified_at IS NOT NULL
           WHERE dv.id = $1
             AND dv.document_id = $2
             AND dv.review_status = 'approved'
             AND dv.retired_at IS NULL
             AND d.deleted_at IS NULL
             AND d.suspended_at IS NULL
             AND EXISTS (
               SELECT 1 FROM users u WHERE u.id = $3 AND u.disabled_at IS NULL
             )
             AND (
               EXISTS (
                 SELECT 1 FROM document_categories dc
                 JOIN authorized_categories ac ON ac.category_id = dc.category_id
                 WHERE dc.document_id = d.id AND ac.user_id = $3
               )
               OR EXISTS (
                 SELECT 1 FROM document_acl da
                 JOIN users u ON u.id = da.user_id AND u.disabled_at IS NULL
                 WHERE da.document_id = d.id AND da.user_id = $3 AND da.can_query
               )
             )""",
        version_id,
        document_id,
        user_uuid,
    )
    if row is None:
        raise ReviewError("DOCUMENT_NOT_FOUND", 404)
    return row


def _serialize_task(
    row: Any,
    *,
    document_title: str,
    document_number: str | None,
    total_pages: int,
    deduplicated: bool = False,
) -> dict[str, Any]:
    page_number = int(row["page_number"])
    status = str(row["status"])
    candidate = row["candidate_json"] or {}
    if isinstance(candidate, str):
        candidate = json.loads(candidate)
    return {
        "task_id": str(row["id"]),
        "status": status,
        "document_id": str(row["document_id"]),
        "version_id": str(row["version_id"]),
        "document_title": document_title,
        "document_number": document_number,
        "page_number": page_number,
        "total_pages": total_pages,
        "source_kind": "ocr_ai_unverified",
        "verified": False,
        "warning": _unverified_warning(page_number),
        "page_text": row["candidate_text"] if status == "ready" else None,
        "error_code": row["error_code"],
        "warnings": candidate.get("warnings", []) if status == "ready" else [],
        "unreadable": candidate.get("unreadable", []) if status == "ready" else [],
        "pdf_url": _pdf_url(row["document_id"], row["version_id"]),
        "deduplicated": deduplicated,
    }


async def _expire_stale_user_tasks(conn: Any) -> None:
    await expire_user_tasks(conn)


async def _invalidate_changed_task(conn: Any, task: Any, version: Any) -> Any:
    if task["status"] not in ("queued", "running", "ready"):
        return task
    text = await conn.fetchval(
        "SELECT text_original FROM source_pages WHERE document_version_id=$1 AND page_number=$2",
        task["version_id"],
        task["page_number"],
    )
    if (
        task["source_review_revision"] == version["source_review_revision"]
        and task["pdf_sha256"] == version["original_file_sha256"]
        and task["page_text_sha256"] == page_text_sha256(text)
    ):
        return task
    return (
        await conn.fetchrow(
            """UPDATE document_ocr_ai_proposals SET status='stale',
           error_code='DOCUMENT_REVISION_CONFLICT', candidate_text=NULL, candidate_json=NULL,
           lease_token=NULL, lease_expires_at=NULL, finished_at=COALESCE(finished_at, now())
           WHERE id=$1 AND status IN ('queued','running','ready') RETURNING *""",
            task["id"],
        )
        or task
    )


async def request_page_text(
    pool: Any,
    principal: Principal,
    *,
    document_id: UUID,
    version_id: UUID,
    page_number: int,
    prefer_ai: bool = False,
    request_id: UUID | None = None,
    ai_enabled: bool = True,
) -> tuple[int, dict[str, Any]]:
    """Return approved page text directly or queue an ephemeral single-page OCR AI read."""
    actor = UUID(principal.id)
    effective_req_id = request_id or uuid4()

    async with pool.acquire() as conn, conn.transaction():
        version = await _load_user_accessible_version(conn, principal, document_id, version_id)
        total_pages = int(
            await conn.fetchval(
                "SELECT count(*) FROM source_pages WHERE document_version_id = $1",
                version_id,
            )
            or 0
        )
        if total_pages <= 0 or page_number < 1 or page_number > total_pages:
            raise ReviewError("PAGE_OUT_OF_RANGE", 422)

        page_row = await conn.fetchrow(
            """SELECT extraction_method, text_quality, text_original, reviewed_at
               FROM source_pages
               WHERE document_version_id = $1 AND page_number = $2""",
            version_id,
            page_number,
        )
        if page_row is None:
            raise ReviewError("PAGE_OUT_OF_RANGE", 422)

        stored_text = page_row["text_original"] or ""
        usable = bool(stored_text.strip()) and (
            page_row["reviewed_at"] is not None or page_row["text_quality"] == "usable"
        )
        if usable and not prefer_ai:
            source_kind = (
                "native"
                if page_row["extraction_method"] in ("native_text", "native_pdf")
                else "ocr_reviewed"
            )
            return 200, {
                "task_id": None,
                "status": "ready",
                "document_id": str(document_id),
                "version_id": str(version_id),
                "document_title": version["title"],
                "document_number": version["document_number"],
                "page_number": page_number,
                "total_pages": total_pages,
                "source_kind": source_kind,
                "verified": True,
                "warning": None,
                "page_text": stored_text,
                "error_code": None,
                "pdf_url": _pdf_url(document_id, version_id),
                "deduplicated": False,
            }

        if (version["source_format"] or "pdf").lower() != "pdf":
            raise ReviewError("OCR_AI_PDF_REQUIRED", 422)
        if not ai_enabled:
            raise ReviewError("OCR_AI_DISABLED", 503)

        await conn.execute("SELECT pg_advisory_xact_lock($1)", _QUEUE_LOCK_KEY)
        await _expire_stale_user_tasks(conn)

        if request_id is not None:
            existing_req = await conn.fetchrow(
                """SELECT * FROM document_ocr_ai_proposals
                   WHERE requested_by = $1 AND request_id = $2""",
                actor,
                request_id,
            )
            if existing_req is not None:
                if (
                    existing_req["purpose"] != "user_page_text"
                    or existing_req["document_id"] != document_id
                    or existing_req["version_id"] != version_id
                    or existing_req["page_number"] != page_number
                ):
                    raise ReviewError("OCR_AI_IDEMPOTENCY_CONFLICT", 409)
                existing_req = await _invalidate_changed_task(conn, existing_req, version)
                http_code = 200 if existing_req["status"] == "ready" else 202
                return http_code, _serialize_task(
                    existing_req,
                    document_title=version["title"],
                    document_number=version["document_number"],
                    total_pages=total_pages,
                    deduplicated=True,
                )

        pdf_sha = version["original_file_sha256"]
        txt_sha = page_text_sha256(stored_text)
        active = await conn.fetchrow(
            """SELECT * FROM document_ocr_ai_proposals
               WHERE purpose = 'user_page_text'
                 AND requested_by = $1
                 AND document_id = $2
                 AND version_id = $3
                 AND page_number = $4
                 AND source_review_revision = $5
                 AND pdf_sha256 = $6
                 AND page_text_sha256 = $7
                 AND status IN ('queued', 'running', 'ready')
               LIMIT 1""",
            actor,
            document_id,
            version_id,
            page_number,
            version["source_review_revision"],
            pdf_sha,
            txt_sha,
        )
        if active is not None:
            http_code = 200 if active["status"] == "ready" else 202
            return http_code, _serialize_task(
                active,
                document_title=version["title"],
                document_number=version["document_number"],
                total_pages=total_pages,
                deduplicated=True,
            )

        active_count = await conn.fetchval(
            "SELECT count(*) FROM document_ocr_ai_proposals WHERE status IN ('queued', 'running')"
        )
        if int(active_count or 0) >= MAX_QUEUED_OCR_TASKS:
            raise ReviewError("OCR_AI_QUEUE_FULL", 429)

        task_id = uuid4()
        render_params = {
            "dpi": DEFAULT_RENDER_DPI,
            "max_edge": DEFAULT_RENDER_MAX_EDGE,
            "max_bytes": DEFAULT_RENDER_MAX_BYTES,
        }
        inserted = await conn.fetchrow(
            """INSERT INTO document_ocr_ai_proposals (
                 id, purpose, document_id, version_id, page_number,
                 source_review_revision, pdf_sha256, page_text_sha256,
                 prompt_version, render_params, request_id, requested_by,
                 expires_at, status
               )
               VALUES (
                 $1, 'user_page_text', $2, $3, $4,
                 $5, $6, $7,
                 $8, $9::jsonb, $10, $11,
                 now() + make_interval(mins => $12), 'queued'
               )
               RETURNING *""",
            task_id,
            document_id,
            version_id,
            page_number,
            version["source_review_revision"],
            pdf_sha,
            txt_sha,
            PROMPT_VERSION,
            json.dumps(render_params),
            effective_req_id,
            actor,
            USER_PAGE_TEXT_TTL_MINUTES,
        )
        return 202, _serialize_task(
            inserted,
            document_title=version["title"],
            document_number=version["document_number"],
            total_pages=total_pages,
        )


async def get_page_text_task(
    pool: Any,
    principal: Principal,
    task_id: UUID,
) -> dict[str, Any]:
    """Poll status and result of a user's ephemeral single-page OCR AI task."""
    actor = UUID(principal.id)
    # Commit TTL cleanup independently: the 410 response below must not roll it back.
    async with pool.acquire() as cleanup_conn:
        await expire_user_tasks(cleanup_conn)
    async with pool.acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            """SELECT * FROM document_ocr_ai_proposals
               WHERE id = $1 AND purpose = 'user_page_text' AND requested_by = $2""",
            task_id,
            actor,
        )
        if row is None:
            raise ReviewError("PAGE_TEXT_TASK_NOT_FOUND", 404)
        version = await _load_user_accessible_version(
            conn,
            principal,
            row["document_id"],
            row["version_id"],
        )
        if row["error_code"] == "OCR_AI_EXPIRED":
            raise ReviewError("OCR_AI_EXPIRED", 410)
        row = await _invalidate_changed_task(conn, row, version)
        total_pages = int(
            await conn.fetchval(
                "SELECT count(*) FROM source_pages WHERE document_version_id = $1",
                row["version_id"],
            )
            or 0
        )
        return _serialize_task(
            row,
            document_title=version["title"],
            document_number=version["document_number"],
            total_pages=total_pages,
        )


async def cancel_page_text_task(
    pool: Any,
    principal: Principal,
    task_id: UUID,
) -> dict[str, Any]:
    """Cancel a queued or running user page-text task owned by ``principal``."""
    actor = UUID(principal.id)
    async with pool.acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            """SELECT * FROM document_ocr_ai_proposals
               WHERE id = $1 AND purpose = 'user_page_text' AND requested_by = $2
               FOR UPDATE""",
            task_id,
            actor,
        )
        if row is None:
            raise ReviewError("PAGE_TEXT_TASK_NOT_FOUND", 404)
        version = await _load_user_accessible_version(
            conn,
            principal,
            row["document_id"],
            row["version_id"],
        )
        total_pages = int(
            await conn.fetchval(
                "SELECT count(*) FROM source_pages WHERE document_version_id = $1",
                row["version_id"],
            )
            or 0
        )
        if row["status"] in ("queued", "running"):
            row = await conn.fetchrow(
                """UPDATE document_ocr_ai_proposals
                   SET status = 'cancelled',
                       error_code = 'OCR_AI_CANCELLED',
                       lease_token = NULL,
                       lease_expires_at = NULL,
                       finished_at = COALESCE(finished_at, now())
                   WHERE id = $1
                   RETURNING *""",
                task_id,
            )
        return _serialize_task(
            row,
            document_title=version["title"],
            document_number=version["document_number"],
            total_pages=total_pages,
        )


async def read_user_document_pdf(
    pool: Any,
    principal: Principal,
    *,
    document_id: UUID,
    version_id: UUID,
    store_root: Path,
) -> bytes:
    """Return verified PDF bytes for an authorized approved document version."""
    async with pool.acquire() as conn, conn.transaction(readonly=True):
        version = await _load_user_accessible_version(conn, principal, document_id, version_id)
    if (version["source_format"] or "pdf").lower() != "pdf":
        raise ReviewError("OCR_AI_PDF_REQUIRED", 422)
    try:
        return await asyncio.to_thread(
            read_immutable_pdf,
            store_root,
            version["original_file_path"],
            version["original_file_sha256"],
            max_bytes=_DEFAULT_MAX_PDF_BYTES,
        )
    except ValueError as exc:
        raise ReviewError("CITATION_SOURCE_UNAVAILABLE", 503) from exc
