"""Database store and authorization checks for admin OCR AI proposals."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Awaitable, Callable, Mapping
from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from ..audit import append_audit
from ..auth_acl.policy import Principal
from ..model_registry.profiles import profile_fingerprint
from ..model_registry.runtime import RegistryRuntime, _profile_from_row
from .management_access import lock_review_version
from .management_read import _record
from .management_write import apply_version_change_in_tx
from .ocr_ai import (
    DEFAULT_RENDER_DPI,
    DEFAULT_RENDER_MAX_BYTES,
    DEFAULT_RENDER_MAX_EDGE,
    PROMPT_VERSION,
    compute_line_diff,
)
from .review import ReviewError

MAX_QUEUED_OCR_TASKS = 20
_QUEUE_LOCK_KEY = 7_302_026_101


def page_text_sha256(text: str | None) -> str:
    """Return a deterministic SHA-256 hex digest of normalized page text."""
    normalized = unicodedata.normalize("NFC", text or "")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


async def expire_user_tasks(conn: Any) -> None:
    """Remove ephemeral page contents even when nobody polls the task again."""
    await conn.execute(
        """UPDATE document_ocr_ai_proposals
           SET status='stale', error_code='OCR_AI_EXPIRED',
               candidate_text=NULL, candidate_json=NULL, lease_token=NULL,
               lease_expires_at=NULL, finished_at=COALESCE(finished_at, now())
           WHERE purpose='user_page_text' AND expires_at <= now()
             AND (status IN ('queued','running','ready')
                  OR candidate_text IS NOT NULL OR candidate_json IS NOT NULL)"""
    )


def _decode_json(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return None if value is None else str(value)


def _serialize_proposal(
    row: Any,
    *,
    current_page_text: str | None = None,
    live_revision: int | None = None,
    live_pdf_sha: str | None = None,
    deduplicated: bool = False,
) -> dict[str, Any]:
    candidate_raw = _decode_json(row["candidate_json"])
    render_params = _decode_json(row["render_params"]) or {}
    candidate_text = row["candidate_text"]
    stale = row["status"] == "stale"
    if (
        row["status"] == "ready"
        and live_revision is not None
        and live_pdf_sha is not None
        and (
            live_revision != row["source_review_revision"]
            or live_pdf_sha != row["pdf_sha256"]
            or (
                current_page_text is not None
                and page_text_sha256(current_page_text) != row["page_text_sha256"]
            )
        )
    ):
        stale = True
    reported_status = "stale" if (stale and row["status"] == "ready") else row["status"]
    diff = (
        compute_line_diff(current_page_text, candidate_text)
        if candidate_text is not None and current_page_text is not None
        else None
    )
    return {
        "proposal_id": str(row["id"]),
        "purpose": row["purpose"],
        "document_id": str(row["document_id"]),
        "version_id": str(row["version_id"]),
        "page_number": row["page_number"],
        "source_review_revision": row["source_review_revision"],
        "pdf_sha256": row["pdf_sha256"],
        "page_text_sha256": row["page_text_sha256"],
        "image_sha256": row["image_sha256"],
        "profile_id": row["profile_id"],
        "profile_revision": row["profile_revision"],
        "model_digest": row["model_digest"],
        "prompt_version": row["prompt_version"],
        "render_params": render_params,
        "request_id": str(row["request_id"]),
        "requested_by": str(row["requested_by"]),
        "requested_at": _iso(row["requested_at"]),
        "expires_at": _iso(row["expires_at"]),
        "status": reported_status,
        "stale": stale,
        "attempts": row["attempts"],
        "started_at": _iso(row["started_at"]),
        "finished_at": _iso(row["finished_at"]),
        "candidate": candidate_raw,
        "candidate_text": candidate_text,
        "current_page_text": current_page_text,
        "diff": diff,
        "error_code": row["error_code"],
        "applied_version_id": (
            str(row["applied_version_id"]) if row["applied_version_id"] is not None else None
        ),
        "decided_by": str(row["decided_by"]) if row["decided_by"] is not None else None,
        "decided_at": _iso(row["decided_at"]),
        "note": row["note"],
        "deduplicated": deduplicated,
    }


def _ensure_editable(row: Any, conn_max_version: int | None) -> None:
    if row["can_edit"]:
        return
    if (
        row["can_read"]
        and conn_max_version is not None
        and row["version_number"] != conn_max_version
    ):
        raise ReviewError("DOCUMENT_REVISION_CONFLICT", 409)
    raise ReviewError("DOCUMENT_EDIT_DENIED", 403)


async def create_proposal(
    pool: Any,
    principal: Principal,
    *,
    document_id: UUID,
    version_id: UUID,
    page_number: int,
    expected_revision: int,
    request_id: UUID,
    ai_enabled: bool = True,
) -> dict[str, Any]:
    """Queue a single-page OCR AI proposal with idempotency, dedup and queue cap."""
    actor = UUID(principal.id)
    async with pool.acquire() as conn, conn.transaction():
        version = await lock_review_version(conn, version_id)
        if version is None or version["document_id"] != document_id:
            raise ReviewError("DOCUMENT_NOT_FOUND", 404)
        row = await _record(conn, principal, document_id, version_id, as_of=date.today())
        max_version = (
            await conn.fetchval(
                "SELECT max(version_number) FROM document_versions WHERE document_id = $1",
                document_id,
            )
            if not row["can_edit"] and row["can_read"]
            else None
        )
        _ensure_editable(row, max_version)
        if not ai_enabled:
            raise ReviewError("OCR_AI_DISABLED", 503)

        existing_by_req = await conn.fetchrow(
            """SELECT * FROM document_ocr_ai_proposals
               WHERE requested_by = $1 AND request_id = $2""",
            actor,
            request_id,
        )
        if existing_by_req is not None:
            if (
                existing_by_req["purpose"] != "admin_correction"
                or existing_by_req["document_id"] != document_id
                or existing_by_req["version_id"] != version_id
                or existing_by_req["page_number"] != page_number
                or existing_by_req["source_review_revision"] != expected_revision
            ):
                raise ReviewError("OCR_AI_IDEMPOTENCY_CONFLICT", 409)
            page_text = await conn.fetchval(
                "SELECT text_original FROM source_pages "
                "WHERE document_version_id = $1 AND page_number = $2",
                version_id,
                page_number,
            )
            return _serialize_proposal(
                existing_by_req,
                current_page_text=page_text,
                live_revision=version["source_review_revision"],
                live_pdf_sha=version["original_file_sha256"],
                deduplicated=True,
            )

        if version["source_review_revision"] != expected_revision:
            raise ReviewError("DOCUMENT_REVISION_CONFLICT", 409)
        if (version["source_format"] or "pdf").lower() != "pdf":
            raise ReviewError("OCR_AI_PDF_REQUIRED", 422)

        page_row = await conn.fetchrow(
            """SELECT extraction_method, text_quality, text_original
               FROM source_pages
               WHERE document_version_id = $1 AND page_number = $2""",
            version_id,
            page_number,
        )
        if page_row is None:
            raise ReviewError("PAGE_OUT_OF_RANGE", 422)
        if page_row["extraction_method"] != "local_ocr" and page_row["text_quality"] != "needs_ocr":
            raise ReviewError("OCR_EDIT_DENIED", 409)

        pdf_sha = version["original_file_sha256"]
        txt_sha = page_text_sha256(page_row["text_original"])

        await conn.execute("SELECT pg_advisory_xact_lock($1)", _QUEUE_LOCK_KEY)
        active = await conn.fetchrow(
            """SELECT * FROM document_ocr_ai_proposals
               WHERE purpose = 'admin_correction'
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
            expected_revision,
            pdf_sha,
            txt_sha,
        )
        if active is not None:
            return _serialize_proposal(
                active,
                current_page_text=page_row["text_original"],
                live_revision=version["source_review_revision"],
                live_pdf_sha=pdf_sha,
                deduplicated=True,
            )

        active_count = await conn.fetchval(
            "SELECT count(*) FROM document_ocr_ai_proposals WHERE status IN ('queued', 'running')"
        )
        if int(active_count or 0) >= MAX_QUEUED_OCR_TASKS:
            raise ReviewError("OCR_AI_QUEUE_FULL", 429)

        proposal_id = uuid4()
        render_params = {
            "dpi": DEFAULT_RENDER_DPI,
            "max_edge": DEFAULT_RENDER_MAX_EDGE,
            "max_bytes": DEFAULT_RENDER_MAX_BYTES,
        }
        inserted = await conn.fetchrow(
            """INSERT INTO document_ocr_ai_proposals (
                 id, purpose, document_id, version_id, page_number,
                 source_review_revision, pdf_sha256, page_text_sha256,
                 prompt_version, render_params, request_id, requested_by, status
               )
               VALUES (
                 $1, 'admin_correction', $2, $3, $4,
                 $5, $6, $7,
                 $8, $9::jsonb, $10, $11, 'queued'
               )
               RETURNING *""",
            proposal_id,
            document_id,
            version_id,
            page_number,
            expected_revision,
            pdf_sha,
            txt_sha,
            PROMPT_VERSION,
            json.dumps(render_params),
            request_id,
            actor,
        )
        await append_audit(
            conn,
            principal_id=actor,
            action="document.ocr_ai.request",
            target_type="document_ocr_ai_proposal",
            target_id=str(proposal_id),
            metadata={
                "document_id": str(document_id),
                "version_id": str(version_id),
                "page_number": page_number,
                "source_review_revision": expected_revision,
                "request_id": str(request_id),
            },
        )
        return _serialize_proposal(
            inserted,
            current_page_text=page_row["text_original"],
            live_revision=version["source_review_revision"],
            live_pdf_sha=pdf_sha,
        )


async def get_proposal(pool: Any, principal: Principal, proposal_id: UUID) -> dict[str, Any]:
    """Return an admin OCR AI proposal with line diff against the current page text."""
    actor = UUID(principal.id)
    async with pool.acquire() as conn, conn.transaction(isolation="repeatable_read", readonly=True):
        prop = await conn.fetchrow(
            """SELECT * FROM document_ocr_ai_proposals
               WHERE id = $1 AND purpose = 'admin_correction'""",
            proposal_id,
        )
        if prop is None:
            raise ReviewError("OCR_AI_PROPOSAL_NOT_FOUND", 404)
        row = await _record(conn, principal, prop["document_id"], prop["version_id"], date.today())
        if not row["can_read"] or not (
            row["can_edit"] or row["can_review"] or prop["requested_by"] == actor
        ):
            raise ReviewError("DOCUMENT_EDIT_DENIED", 403)
        page_text = await conn.fetchval(
            """SELECT text_original FROM source_pages
               WHERE document_version_id = $1 AND page_number = $2""",
            prop["version_id"],
            prop["page_number"],
        )
        return _serialize_proposal(
            prop,
            current_page_text=page_text,
            live_revision=row["revision"],
            live_pdf_sha=row["original_file_sha256"],
        )


async def cancel_proposal(pool: Any, principal: Principal, proposal_id: UUID) -> dict[str, Any]:
    """Cancel a queued or running OCR AI proposal."""
    actor = UUID(principal.id)
    async with pool.acquire() as conn, conn.transaction():
        prop = await conn.fetchrow(
            """SELECT * FROM document_ocr_ai_proposals
               WHERE id = $1 AND purpose = 'admin_correction' FOR UPDATE""",
            proposal_id,
        )
        if prop is None:
            raise ReviewError("OCR_AI_PROPOSAL_NOT_FOUND", 404)
        await lock_review_version(conn, prop["version_id"])
        row = await _record(conn, principal, prop["document_id"], prop["version_id"], date.today())
        if not (row["can_edit"] or (row["can_read"] and prop["requested_by"] == actor)):
            raise ReviewError("DOCUMENT_EDIT_DENIED", 403)
        page_text = await conn.fetchval(
            """SELECT text_original FROM source_pages
               WHERE document_version_id = $1 AND page_number = $2""",
            prop["version_id"],
            prop["page_number"],
        )
        if prop["status"] == "cancelled":
            return _serialize_proposal(
                prop,
                current_page_text=page_text,
                live_revision=row["revision"],
                live_pdf_sha=row["original_file_sha256"],
            )
        if prop["status"] not in ("queued", "running"):
            raise ReviewError("OCR_AI_PROPOSAL_INVALID_STATE", 409)
        updated = await conn.fetchrow(
            """UPDATE document_ocr_ai_proposals
               SET status = 'cancelled',
                   error_code = 'OCR_AI_CANCELLED',
                   lease_token = NULL,
                   lease_expires_at = NULL,
                   finished_at = COALESCE(finished_at, now()),
                   decided_by = $2,
                   decided_at = now()
               WHERE id = $1
               RETURNING *""",
            proposal_id,
            actor,
        )
        await append_audit(
            conn,
            principal_id=actor,
            action="document.ocr_ai.cancel",
            target_type="document_ocr_ai_proposal",
            target_id=str(proposal_id),
            metadata={
                "document_id": str(prop["document_id"]),
                "version_id": str(prop["version_id"]),
                "page_number": prop["page_number"],
            },
        )
        return _serialize_proposal(
            updated,
            current_page_text=page_text,
            live_revision=row["revision"],
            live_pdf_sha=row["original_file_sha256"],
        )


async def reject_proposal(
    pool: Any,
    principal: Principal,
    proposal_id: UUID,
    *,
    note: str | None = None,
) -> dict[str, Any]:
    """Reject a ready or stale OCR AI proposal without modifying source pages."""
    actor = UUID(principal.id)
    cleaned_note = note.strip() if note else None
    async with pool.acquire() as conn, conn.transaction():
        prop = await conn.fetchrow(
            """SELECT * FROM document_ocr_ai_proposals
               WHERE id = $1 AND purpose = 'admin_correction' FOR UPDATE""",
            proposal_id,
        )
        if prop is None:
            raise ReviewError("OCR_AI_PROPOSAL_NOT_FOUND", 404)
        await lock_review_version(conn, prop["version_id"])
        row = await _record(conn, principal, prop["document_id"], prop["version_id"], date.today())
        if not row["can_edit"]:
            raise ReviewError("DOCUMENT_EDIT_DENIED", 403)
        page_text = await conn.fetchval(
            """SELECT text_original FROM source_pages
               WHERE document_version_id = $1 AND page_number = $2""",
            prop["version_id"],
            prop["page_number"],
        )
        if prop["status"] == "rejected":
            return _serialize_proposal(
                prop,
                current_page_text=page_text,
                live_revision=row["revision"],
                live_pdf_sha=row["original_file_sha256"],
            )
        if prop["status"] not in ("ready", "stale"):
            raise ReviewError("OCR_AI_PROPOSAL_INVALID_STATE", 409)
        updated = await conn.fetchrow(
            """UPDATE document_ocr_ai_proposals
               SET status = 'rejected',
                   decided_by = $2,
                   decided_at = now(),
                   note = $3
               WHERE id = $1
               RETURNING *""",
            proposal_id,
            actor,
            cleaned_note,
        )
        await append_audit(
            conn,
            principal_id=actor,
            action="document.ocr_ai.reject",
            target_type="document_ocr_ai_proposal",
            target_id=str(proposal_id),
            metadata={
                "document_id": str(prop["document_id"]),
                "version_id": str(prop["version_id"]),
                "page_number": prop["page_number"],
                "note": cleaned_note,
            },
        )
        return _serialize_proposal(
            updated,
            current_page_text=page_text,
            live_revision=row["revision"],
            live_pdf_sha=row["original_file_sha256"],
        )


async def apply_candidate(
    pool: Any,
    principal: Principal,
    proposal_id: UUID,
    *,
    expected_revision: int,
    corrected_text: str | None = None,
    note: str | None = None,
    model_validator: Callable[[Mapping[str, Any]], Awaitable[bool]] | None = None,
) -> dict[str, Any]:
    """Atomically apply an admin OCR AI candidate into a draft revision."""
    actor = UUID(principal.id)
    cleaned_note = note.strip() if note else None
    if model_validator is not None:
        snapshot = await get_proposal(pool, principal, proposal_id)
        if snapshot["status"] == "ready" and (
            snapshot["prompt_version"] != PROMPT_VERSION or not await model_validator(snapshot)
        ):
            async with pool.acquire() as conn:
                await conn.execute(
                    """UPDATE document_ocr_ai_proposals SET status='stale',
                       error_code='OCR_AI_MODEL_CHANGED' WHERE id=$1 AND status='ready'""",
                    proposal_id,
                )
            raise ReviewError("OCR_AI_MODEL_CHANGED", 409)
    async with pool.acquire() as conn, conn.transaction():
        prop = await conn.fetchrow(
            "SELECT * FROM document_ocr_ai_proposals WHERE id = $1 FOR UPDATE",
            proposal_id,
        )
        if prop is None or prop["purpose"] != "admin_correction":
            raise ReviewError("OCR_AI_PROPOSAL_NOT_FOUND", 404)
        if prop["status"] != "ready":
            raise ReviewError("OCR_AI_PROPOSAL_NOT_READY", 409)
        if prop["source_review_revision"] != expected_revision:
            raise ReviewError("DOCUMENT_REVISION_CONFLICT", 409)
        if prop["prompt_version"] != PROMPT_VERSION:
            raise ReviewError("OCR_AI_MODEL_CHANGED", 409)
        if prop["profile_id"]:
            profile_row = await RegistryRuntime._fetch_profile(conn, prop["profile_id"])
            render_params = _decode_json(prop["render_params"]) or {}
            if (
                profile_row is None
                or profile_row["revision"] != prop["profile_revision"]
                or profile_fingerprint(_profile_from_row(profile_row))
                != render_params.get("model_profile_sha256")
            ):
                raise ReviewError("OCR_AI_MODEL_CHANGED", 409)

        version = await lock_review_version(conn, prop["version_id"])
        if version is None or version["document_id"] != prop["document_id"]:
            raise ReviewError("DOCUMENT_NOT_FOUND", 404)
        if (
            version["source_review_revision"] != prop["source_review_revision"]
            or version["original_file_sha256"] != prop["pdf_sha256"]
        ):
            raise ReviewError("DOCUMENT_REVISION_CONFLICT", 409)

        current_page_text = await conn.fetchval(
            """SELECT text_original FROM source_pages
               WHERE document_version_id = $1 AND page_number = $2""",
            prop["version_id"],
            prop["page_number"],
        )
        if page_text_sha256(current_page_text) != prop["page_text_sha256"]:
            raise ReviewError("DOCUMENT_REVISION_CONFLICT", 409)

        raw_text = corrected_text if corrected_text is not None else (prop["candidate_text"] or "")
        text_to_apply = unicodedata.normalize("NFC", raw_text.strip())
        if not text_to_apply:
            raise ReviewError("OCR_AI_TEXT_EMPTY", 422)

        result = await apply_version_change_in_tx(
            conn,
            principal,
            prop["document_id"],
            prop["version_id"],
            revision=expected_revision,
            changes={},
            ocr_page=(prop["page_number"], text_to_apply),
            prepared=None,
            as_of=date.today(),
        )
        updated = await conn.fetchrow(
            """UPDATE document_ocr_ai_proposals
               SET status = 'applied',
                   applied_version_id = $2,
                   decided_by = $3,
                   decided_at = now(),
                   note = $4
               WHERE id = $1
               RETURNING *""",
            proposal_id,
            result["version_id"],
            actor,
            cleaned_note,
        )
        original_normalized = unicodedata.normalize("NFC", (prop["candidate_text"] or "").strip())
        await append_audit(
            conn,
            principal_id=actor,
            action="document.ocr_ai.apply",
            target_type="document_version",
            target_id=str(result["version_id"]),
            metadata={
                "proposal_id": str(proposal_id),
                "document_id": str(prop["document_id"]),
                "base_version_id": str(prop["version_id"]),
                "page_number": prop["page_number"],
                "revision": result["revision"],
                "edited_before_apply": (
                    corrected_text is not None and text_to_apply != original_normalized
                ),
                "note": cleaned_note,
            },
        )
        return {
            "version_id": str(result["version_id"]),
            "revision": int(result["revision"]),
            "status": result["status"],
            "proposal": _serialize_proposal(
                updated,
                current_page_text=current_page_text,
                live_revision=result["revision"],
                live_pdf_sha=version["original_file_sha256"],
            ),
        }
