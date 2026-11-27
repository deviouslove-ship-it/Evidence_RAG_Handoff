"""PostgreSQL store and ACL-scoped CRUD for Phase 2 conflict scans & findings."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from ..audit import append_audit
from ..auth_acl.policy import Permission, Principal
from ..config import Settings
from ..effectivity.service import can_review
from ..storage.authorized_search import ALLOWED_DOCUMENTS_SQL
from .precedence import REFERENCE_NOTICE, AuthorityRule

# Ruling P5: disjoint from OcrAiWorker (7_302_026_101/102/103) and audit (7_302_026_001).
CONFLICT_WORKER_LOCK_KEY = 7_302_026_104
CONFLICT_CLAIM_LOCK_KEY = 7_302_026_105

_ALLOWED_AMENDMENT_ACTIONS = frozenset(
    {"modify", "replace", "add", "repeal", "repeal_partial", "suspend"}
)
_ALLOWED_FINDING_TYPES = frozenset(
    {"contradiction", "overlap", "exception_refinement", "superseded_already"}
)
_ALLOWED_SEVERITIES = frozenset({"high", "medium", "low"})
_ALLOWED_REVIEW_STATUSES = frozenset(
    {"pending", "confirmed", "dismissed", "linked_amendment"}
)


class ConflictStoreError(Exception):
    """Domain error for conflict scan/review store operations (mapped to ``api_error``)."""

    def __init__(
        self, code: str, status_code: int = 422, *, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.details = details or {}


def _decode_json(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime | date):
        return value.isoformat()
    return None if value is None else str(value)


def _unique_sorted_uuids(values: Sequence[UUID]) -> list[UUID]:
    seen: dict[str, UUID] = {}
    for item in values:
        seen[str(item)] = item
    return [seen[key] for key in sorted(seen)]


def _serialize_run(row: Any, *, deduplicated: bool = False) -> dict[str, Any]:
    scope = _decode_json(row["scope_json"]) or {}
    limits = _decode_json(row["limits_json"]) or {}
    summary = _decode_json(row["summary_json"])
    return {
        "id": str(row["id"]),
        "requested_by": str(row["requested_by"]),
        "request_id": row["request_id"],
        "status": row["status"],
        "scope_json": scope,
        "as_of_date": _iso(row["as_of_date"]),
        "use_ai": bool(row["use_ai"]),
        "model_profile_id": (
            str(row["model_profile_id"]) if row["model_profile_id"] is not None else None
        ),
        "limits_json": limits,
        "progress_total": int(row["progress_total"]),
        "progress_done": int(row["progress_done"]),
        "summary_json": summary,
        "error_code": row["error_code"],
        "error_message": row["error_message"],
        "created_at": _iso(row["created_at"]),
        "started_at": _iso(row["started_at"]),
        "completed_at": _iso(row["completed_at"]),
        "expires_at": _iso(row["expires_at"]),
        "reference_notice": REFERENCE_NOTICE,
        "deduplicated": deduplicated,
    }


def _serialize_finding(row: Any) -> dict[str, Any]:
    signals = _decode_json(row["signals_json"]) or {}
    basis = _decode_json(row["precedence_basis_json"]) or {}
    return {
        "id": str(row["id"]),
        "run_id": str(row["run_id"]),
        "document_a_id": str(row["document_a_id"]),
        "document_b_id": str(row["document_b_id"]),
        "node_a_id": str(row["node_a_id"]),
        "node_b_id": str(row["node_b_id"]),
        "document_a_number": row.get("doc_a_number"),
        "document_a_title": row.get("doc_a_title"),
        "document_b_number": row.get("doc_b_number"),
        "document_b_title": row.get("doc_b_title"),
        "node_a_label": row.get("node_a_label"),
        "node_a_path": row.get("node_a_path"),
        "node_a_text": row.get("node_a_text"),
        "node_a_page_start": row.get("node_a_page_start"),
        "node_b_label": row.get("node_b_label"),
        "node_b_path": row.get("node_b_path"),
        "node_b_text": row.get("node_b_text"),
        "node_b_page_start": row.get("node_b_page_start"),
        "finding_type": row["finding_type"],
        "severity": row["severity"],
        "detection_method": row["detection_method"],
        "similarity_score": (
            float(row["similarity_score"]) if row["similarity_score"] is not None else None
        ),
        "shared_labels": list(row["shared_labels"] or ()),
        "signals_json": signals,
        "precedence_result": row["precedence_result"],
        "precedence_basis_json": basis,
        "explanation": row["explanation"],
        "ai_confidence": (
            float(row["ai_confidence"]) if row["ai_confidence"] is not None else None
        ),
        "ai_verified": row["ai_verified"],
        "review_status": row["review_status"],
        "reviewed_by": str(row["reviewed_by"]) if row["reviewed_by"] is not None else None,
        "reviewed_at": _iso(row["reviewed_at"]),
        "review_note": row["review_note"],
        "linked_amendment_id": (
            str(row["linked_amendment_id"])
            if row["linked_amendment_id"] is not None
            else None
        ),
        "created_at": _iso(row["created_at"]),
        "reference_notice": REFERENCE_NOTICE,
    }


async def expire_conflict_runs(conn: Any) -> int:
    """Mark overdue queued/completed conflict scan runs as expired."""
    rows = await conn.fetch(
        """UPDATE conflict_review_runs
           SET status = 'expired',
               error_code = COALESCE(error_code, 'CONFLICT_SCAN_EXPIRED'),
               lease_token = NULL,
               lease_expires_at = NULL,
               completed_at = COALESCE(completed_at, now())
           WHERE expires_at <= now()
             AND status IN ('queued', 'completed')
           RETURNING id"""
    )
    return len(rows)


async def resolve_scoped_document_ids(
    conn: Any,
    principal: Principal,
    *,
    document_ids: Sequence[UUID] = (),
    category_ids: Sequence[UUID] = (),
    limit: int | None = None,
) -> list[UUID]:
    """Resolve authorized document IDs via ``ALLOWED_DOCUMENTS_SQL`` & ``document_categories``.

    Ruling P6: ``documents`` has no ``category_id`` column, so category filtering joins
    ``document_categories(document_id, category_id)`` inside the principal-scoped tx.
    """
    if not principal.has(Permission.QUERY):
        return []
    await conn.execute("SELECT set_config('app.user_id', $1, true)", principal.id)
    doc_param = list(document_ids) if document_ids else None
    cat_param = list(category_ids) if category_ids else None
    limit_sql = "LIMIT $3" if limit is not None else ""
    params: list[Any] = [doc_param, cat_param]
    if limit is not None:
        params.append(max(1, limit))

    rows = await conn.fetch(
        f"""SELECT d.id
            FROM documents d
            JOIN ({ALLOWED_DOCUMENTS_SQL}) allowed ON allowed.document_id = d.id
            WHERE ($1::uuid[] IS NULL OR d.id = ANY($1::uuid[]))
              AND (
                $2::uuid[] IS NULL
                OR EXISTS (
                  SELECT 1 FROM document_categories dc
                  WHERE dc.document_id = d.id
                    AND dc.category_id = ANY($2::uuid[])
                )
              )
            ORDER BY d.created_at DESC, d.id ASC
            {limit_sql}""",
        *params,
    )
    return [row["id"] for row in rows]


async def create_conflict_run(
    pool: Any,
    principal: Principal,
    *,
    request_id: str,
    document_ids: Sequence[UUID] = (),
    category_ids: Sequence[UUID] = (),
    as_of_date: date | None = None,
    use_ai: bool = False,
    include_expired: bool = False,
    settings: Settings | None = None,
    operating_mode: str | None = None,
) -> dict[str, Any]:
    """Queue a new conflict scan run with idempotency, ACL checks, and queue cap."""
    if not principal.has(Permission.QUERY):
        raise ConflictStoreError("QUERY_REQUIRED", 403)
    cleaned_req_id = request_id.strip()
    if not cleaned_req_id or len(cleaned_req_id) > 128:
        raise ConflictStoreError("INVALID_REQUEST", 422)

    max_documents = settings.conflict_scan_max_documents if settings else 20
    max_pairs = settings.conflict_scan_max_pairs if settings else 120
    max_ai_pairs = settings.conflict_scan_max_ai_pairs if settings else 25
    max_queued = settings.conflict_scan_max_queued if settings else 10
    ttl_hours = settings.conflict_scan_ttl_hours if settings else 168
    ai_timeout = settings.conflict_scan_ai_timeout_seconds if settings else 25.0
    mode = (operating_mode or (settings.operating_mode if settings else "LOCAL")).upper()

    actor = UUID(principal.id)
    effective_date = as_of_date or date.today()
    unique_doc_ids = _unique_sorted_uuids(document_ids)
    unique_cat_ids = _unique_sorted_uuids(category_ids)
    requested_scope = {
        "document_ids": [str(item) for item in unique_doc_ids],
        "category_ids": [str(item) for item in unique_cat_ids],
        "include_expired": bool(include_expired),
    }

    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock($1)", CONFLICT_CLAIM_LOCK_KEY)
        await expire_conflict_runs(conn)
        existing = await conn.fetchrow(
            """SELECT * FROM conflict_review_runs
               WHERE requested_by = $1 AND request_id = $2""",
            actor,
            cleaned_req_id,
        )
        if existing is not None:
            existing_scope = _decode_json(existing["scope_json"]) or {}
            if (
                existing_scope.get("document_ids", []) != requested_scope["document_ids"]
                or existing_scope.get("category_ids", []) != requested_scope["category_ids"]
                or bool(existing_scope.get("include_expired", False))
                != requested_scope["include_expired"]
                or existing["as_of_date"] != effective_date
                or bool(existing["use_ai"]) != bool(use_ai)
            ):
                raise ConflictStoreError("CONFLICT_SCAN_IDEMPOTENCY_CONFLICT", 409)
            return _serialize_run(existing, deduplicated=True)

        active_count = await conn.fetchval(
            "SELECT count(*) FROM conflict_review_runs WHERE status IN ('queued', 'running')"
        )
        if int(active_count or 0) >= max_queued:
            raise ConflictStoreError(
                "CONFLICT_SCAN_QUEUE_FULL",
                429,
                details={"max_queued": max_queued},
            )

        if len(unique_doc_ids) > max_documents:
            raise ConflictStoreError(
                "CONFLICT_SCAN_TOO_MANY_DOCUMENTS",
                422,
                details={"max_documents": max_documents, "count": len(unique_doc_ids)},
            )

        allowed_ids = await resolve_scoped_document_ids(
            conn,
            principal,
            document_ids=unique_doc_ids,
            category_ids=unique_cat_ids,
            limit=max_documents + 1,
        )
        if unique_doc_ids and (set(unique_doc_ids) - set(allowed_ids)):
            raise ConflictStoreError("DOCUMENT_NOT_FOUND", 404)
        if len(allowed_ids) > max_documents:
            raise ConflictStoreError(
                "CONFLICT_SCAN_TOO_MANY_DOCUMENTS",
                422,
                details={"max_documents": max_documents},
            )
        if len(allowed_ids) < 2:
            raise ConflictStoreError(
                "CONFLICT_SCAN_INSUFFICIENT_DOCUMENTS",
                422,
                details={"found": len(allowed_ids), "required": 2},
            )

        model_profile_id: UUID | None = None
        if use_ai:
            model_profile_id = await conn.fetchval(
                """SELECT sr.profile_id
                   FROM stage_routes sr
                   JOIN model_profiles mp ON mp.id = sr.profile_id
                   JOIN providers pr ON pr.id = mp.provider_id
                   WHERE sr.mode = $1 AND sr.stage = 'relation'
                     AND pr.approved AND mp.health = 'ready'
                   LIMIT 1""",
                mode,
            )

        scope_to_store = {
            **requested_scope,
            "resolved_document_ids": [str(item) for item in allowed_ids],
        }
        limits_to_store = {
            "max_documents": max_documents,
            "max_pairs": max_pairs,
            "max_ai_pairs": max_ai_pairs,
            "ai_timeout_seconds": ai_timeout,
        }
        run_id = uuid4()
        inserted = await conn.fetchrow(
            """INSERT INTO conflict_review_runs (
                 id, requested_by, request_id, status, scope_json,
                 as_of_date, use_ai, model_profile_id, limits_json,
                 expires_at
               )
               VALUES (
                 $1, $2, $3, 'queued', $4::jsonb,
                 $5, $6, $7, $8::jsonb,
                 now() + make_interval(hours => $9)
               )
               RETURNING *""",
            run_id,
            actor,
            cleaned_req_id,
            json.dumps(scope_to_store, ensure_ascii=False),
            effective_date,
            bool(use_ai),
            model_profile_id,
            json.dumps(limits_to_store, ensure_ascii=False),
            ttl_hours,
        )
        await append_audit(
            conn,
            principal_id=actor,
            action="conflict_scan.create",
            target_type="conflict_review_run",
            target_id=str(run_id),
            metadata={
                "request_id": cleaned_req_id,
                "document_count": len(allowed_ids),
                "as_of_date": effective_date.isoformat(),
                "use_ai": bool(use_ai),
            },
        )
        return _serialize_run(inserted, deduplicated=False)


def _can_view_run(row: Any, principal: Principal) -> bool:
    if str(row["requested_by"]) == principal.id:
        return True
    return principal.has(Permission.REVIEW) or principal.has(Permission.ADMIN)


async def get_conflict_run(
    pool: Any, principal: Principal, run_id: UUID
) -> dict[str, Any]:
    """Fetch one conflict scan run visible to ``principal``."""
    async with pool.acquire() as conn, conn.transaction():
        await expire_conflict_runs(conn)
        row = await conn.fetchrow(
            "SELECT * FROM conflict_review_runs WHERE id = $1",
            run_id,
        )
    if row is None or not _can_view_run(row, principal):
        raise ConflictStoreError("CONFLICT_RUN_NOT_FOUND", 404)
    return _serialize_run(row)


async def list_conflict_runs(
    pool: Any,
    principal: Principal,
    *,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """List conflict scan runs requested by ``principal`` (newest first)."""
    actor = UUID(principal.id)
    async with pool.acquire() as conn, conn.transaction():
        await expire_conflict_runs(conn)
        total = await conn.fetchval(
            "SELECT count(*) FROM conflict_review_runs WHERE requested_by = $1",
            actor,
        )
        rows = await conn.fetch(
            """SELECT * FROM conflict_review_runs
               WHERE requested_by = $1
               ORDER BY created_at DESC, id DESC
               LIMIT $2 OFFSET $3""",
            actor,
            max(1, min(limit, 100)),
            max(0, offset),
        )
    return {
        "total": int(total or 0),
        "items": [_serialize_run(row) for row in rows],
    }


async def cancel_conflict_run(
    pool: Any, principal: Principal, run_id: UUID
) -> dict[str, Any]:
    """Cancel a queued or running conflict scan run."""
    actor = UUID(principal.id)
    async with pool.acquire() as conn, conn.transaction():
        await expire_conflict_runs(conn)
        row = await conn.fetchrow(
            "SELECT * FROM conflict_review_runs WHERE id = $1 FOR UPDATE",
            run_id,
        )
        if row is None or (
            row["requested_by"] != actor and not principal.has(Permission.ADMIN)
        ):
            raise ConflictStoreError("CONFLICT_RUN_NOT_FOUND", 404)
        if row["status"] == "cancelled":
            return _serialize_run(row)
        if row["status"] not in {"queued", "running"}:
            raise ConflictStoreError(
                "CONFLICT_SCAN_INVALID_STATE",
                409,
                details={"status": row["status"]},
            )
        updated = await conn.fetchrow(
            """UPDATE conflict_review_runs
               SET status = 'cancelled',
                   error_code = 'CONFLICT_SCAN_CANCELLED',
                   lease_token = NULL,
                   lease_expires_at = NULL,
                   completed_at = COALESCE(completed_at, now())
               WHERE id = $1
               RETURNING *""",
            run_id,
        )
        await append_audit(
            conn,
            principal_id=actor,
            action="conflict_scan.cancel",
            target_type="conflict_review_run",
            target_id=str(run_id),
            metadata={"previous_status": row["status"]},
        )
    return _serialize_run(updated)


async def list_conflict_findings(
    pool: Any,
    principal: Principal,
    run_id: UUID,
    *,
    severity: str | None = None,
    finding_type: str | None = None,
    review_status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Return ACL-filtered conflict findings for ``run_id``."""
    if not principal.has(Permission.QUERY):
        raise ConflictStoreError("QUERY_REQUIRED", 403)
    if severity is not None and severity not in _ALLOWED_SEVERITIES:
        raise ConflictStoreError("INVALID_REQUEST", 422)
    if finding_type is not None and finding_type not in _ALLOWED_FINDING_TYPES:
        raise ConflictStoreError("INVALID_REQUEST", 422)
    if review_status is not None and review_status not in _ALLOWED_REVIEW_STATUSES:
        raise ConflictStoreError("INVALID_REQUEST", 422)

    async with pool.acquire() as conn, conn.transaction():
        await expire_conflict_runs(conn)
        run_row = await conn.fetchrow(
            "SELECT * FROM conflict_review_runs WHERE id = $1",
            run_id,
        )
        if run_row is None or not _can_view_run(run_row, principal):
            raise ConflictStoreError("CONFLICT_RUN_NOT_FOUND", 404)

        await conn.execute("SELECT set_config('app.user_id', $1, true)", principal.id)
        base_filter = """
            cf.run_id = $1
            AND ($2::text IS NULL OR cf.severity = $2)
            AND ($3::text IS NULL OR cf.finding_type = $3)
            AND ($4::text IS NULL OR cf.review_status = $4)
        """
        total_unfiltered = await conn.fetchval(
            f"SELECT count(*) FROM conflict_findings cf WHERE {base_filter}",
            run_id,
            severity,
            finding_type,
            review_status,
        )
        findings_from_where = f"""
            FROM conflict_findings cf
            JOIN documents da ON da.id = cf.document_a_id
            JOIN documents db ON db.id = cf.document_b_id
            JOIN document_nodes na ON na.id = cf.node_a_id
            JOIN document_nodes nb ON nb.id = cf.node_b_id
            JOIN document_versions dva ON dva.id = na.document_version_id
            JOIN document_versions dvb ON dvb.id = nb.document_version_id
            JOIN source_provenance spa ON spa.document_version_id = dva.id
            JOIN source_provenance spb ON spb.document_version_id = dvb.id
            WHERE {base_filter}
              AND da.deleted_at IS NULL AND da.suspended_at IS NULL
              AND db.deleted_at IS NULL AND db.suspended_at IS NULL
              AND dva.review_status = 'approved'
              AND dvb.review_status = 'approved'
              AND spa.verified_at IS NOT NULL
              AND spb.verified_at IS NOT NULL
              AND na.review_status = 'approved'
              AND nb.review_status = 'approved'
              AND node_source_text_valid(na.id)
              AND node_source_text_valid(nb.id)
              AND EXISTS (
                  SELECT 1 FROM ({ALLOWED_DOCUMENTS_SQL}) a1
                  WHERE a1.document_id = cf.document_a_id
              )
              AND EXISTS (
                  SELECT 1 FROM ({ALLOWED_DOCUMENTS_SQL}) a2
                  WHERE a2.document_id = cf.document_b_id
              )
        """
        total = await conn.fetchval(
            f"SELECT count(*) {findings_from_where}",
            run_id,
            severity,
            finding_type,
            review_status,
        )
        rows = await conn.fetch(
            f"""SELECT cf.*,
                       da.document_number AS doc_a_number, da.title AS doc_a_title,
                       db.document_number AS doc_b_number, db.title AS doc_b_title,
                       na.citation_label AS node_a_label, na.path AS node_a_path,
                       na.text_original AS node_a_text, na.page_start AS node_a_page_start,
                       nb.citation_label AS node_b_label, nb.path AS node_b_path,
                       nb.text_original AS node_b_text, nb.page_start AS node_b_page_start
                {findings_from_where}
                ORDER BY CASE cf.severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
                         cf.similarity_score DESC NULLS LAST,
                         cf.created_at ASC,
                         cf.id ASC
                LIMIT $5 OFFSET $6""",
            run_id,
            severity,
            finding_type,
            review_status,
            max(1, min(limit, 500)),
            max(0, offset),
        )

    visible_total = int(total or 0)
    unfiltered_total = int(total_unfiltered or 0)
    return {
        "run_id": str(run_id),
        "total": visible_total,
        "hidden_due_to_acl": max(0, unfiltered_total - visible_total),
        "items": [_serialize_finding(dict(row)) for row in rows],
        "reference_notice": REFERENCE_NOTICE,
    }


async def review_conflict_finding(
    pool: Any,
    *,
    reviewer_id: UUID,
    finding_id: UUID,
    decision: Literal["confirm", "dismiss"],
    note: str | None = None,
) -> dict[str, Any]:
    """Confirm or dismiss a ``conflict_findings`` item (REVIEWER scope required)."""
    if decision not in {"confirm", "dismiss"}:
        raise ConflictStoreError("INVALID_REQUEST", 422)
    cleaned_note = note.strip()[:2000] if note and note.strip() else None
    new_status = "confirmed" if decision == "confirm" else "dismissed"

    async with pool.acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            "SELECT * FROM conflict_findings WHERE id = $1 FOR UPDATE",
            finding_id,
        )
        if row is None:
            raise ConflictStoreError("CONFLICT_FINDING_NOT_FOUND", 404)
        if row["review_status"] == "linked_amendment":
            raise ConflictStoreError("CONFLICT_FINDING_ALREADY_LINKED", 409)
        if not await can_review(
            conn, reviewer_id, [row["document_a_id"], row["document_b_id"]]
        ):
            raise ConflictStoreError("REVIEW_SCOPE_REQUIRED", 403)

        updated = await conn.fetchrow(
            """UPDATE conflict_findings
               SET review_status = $2,
                   reviewed_by = $3,
                   reviewed_at = now(),
                   review_note = $4
               WHERE id = $1
               RETURNING *""",
            finding_id,
            new_status,
            reviewer_id,
            cleaned_note,
        )
        await append_audit(
            conn,
            principal_id=reviewer_id,
            action="conflict_finding.review",
            target_type="conflict_finding",
            target_id=str(finding_id),
            metadata={"decision": decision, "review_status": new_status},
        )
    return _serialize_finding(dict(updated))


async def _load_verified_approved_node(
    conn: Any, node_id: UUID, document_id: UUID
) -> Any:
    """Load an approved, provenance-verified, source-text-valid node."""
    return await conn.fetchrow(
        """SELECT n.id, n.document_id, n.text_original, n.page_start,
                  n.path, n.citation_label, d.document_number, d.doc_type
           FROM document_nodes n
           JOIN document_versions dv ON dv.id = n.document_version_id
           JOIN source_provenance sp ON sp.document_version_id = dv.id
           JOIN documents d ON d.id = n.document_id
           WHERE n.id = $1 AND n.document_id = $2
             AND n.review_status = 'approved'
             AND dv.review_status = 'approved'
             AND sp.verified_at IS NOT NULL
             AND node_source_text_valid(n.id)
             AND d.deleted_at IS NULL AND d.suspended_at IS NULL""",
        node_id,
        document_id,
    )


async def create_amendment_draft_from_finding(
    pool: Any,
    *,
    reviewer_id: UUID,
    finding_id: UUID,
    amendment_action: str,
    source_side: Literal["a", "b"] = "a",
    note: str | None = None,
    valid_from: date | None = None,
) -> dict[str, Any]:
    """Create a ``node_amendments`` draft from a conflict finding (Ruling P8)."""
    if amendment_action not in _ALLOWED_AMENDMENT_ACTIONS or source_side not in {"a", "b"}:
        raise ConflictStoreError("INVALID_REQUEST", 422)
    cleaned_note = note.strip()[:2000] if note and note.strip() else None

    async with pool.acquire() as conn, conn.transaction():
        finding = await conn.fetchrow(
            "SELECT * FROM conflict_findings WHERE id = $1 FOR UPDATE",
            finding_id,
        )
        if finding is None:
            raise ConflictStoreError("CONFLICT_FINDING_NOT_FOUND", 404)
        if (
            finding["linked_amendment_id"] is not None
            or finding["review_status"] == "linked_amendment"
        ):
            raise ConflictStoreError("CONFLICT_FINDING_ALREADY_LINKED", 409)
        if finding["review_status"] == "dismissed":
            raise ConflictStoreError("CONFLICT_FINDING_DISMISSED", 409)
        if not await can_review(
            conn,
            reviewer_id,
            [finding["document_a_id"], finding["document_b_id"]],
        ):
            raise ConflictStoreError("REVIEW_SCOPE_REQUIRED", 403)

        if source_side == "a":
            source_doc_id = finding["document_a_id"]
            source_node_id = finding["node_a_id"]
            target_doc_id = finding["document_b_id"]
            target_node_id = finding["node_b_id"]
        else:
            source_doc_id = finding["document_b_id"]
            source_node_id = finding["node_b_id"]
            target_doc_id = finding["document_a_id"]
            target_node_id = finding["node_a_id"]

        source_node = await _load_verified_approved_node(
            conn, source_node_id, source_doc_id
        )
        if source_node is None:
            raise ConflictStoreError("SOURCE_NODE_NOT_FOUND", 404)

        target_node = await _load_verified_approved_node(
            conn, target_node_id, target_doc_id
        )
        if target_node is None:
            raise ConflictStoreError("DOCUMENT_NOT_FOUND", 404)

        target_path = target_node["citation_label"] or target_node["path"]
        target_number = target_node["document_number"]
        target_expression = (
            f"{target_path} {target_number}".strip() if target_number else target_path
        )
        source_quote = str(source_node["text_original"] or "")[:1200]
        evidence_source = f"conflict_review:{finding_id}"

        amendment_id = await conn.fetchval(
            """INSERT INTO node_amendments (
                 source_node_id, source_document_id,
                 target_document_id, target_node_id,
                 scope, action, valid_from, evidence_source,
                 review_status, target_number, target_doc_type,
                 target_path, target_expression, resolution_state,
                 condition_text, proposed_by, proposer_id,
                 source_quote, source_page
               )
               VALUES (
                 $1, $2,
                 $3, $4,
                 'node', $5, $6, $7,
                 'draft', $8, $9,
                 $10, $11, 'resolved',
                 $12, 'conflict_review', $13,
                 $14, $15
               )
               RETURNING id""",
            source_node_id,
            source_doc_id,
            target_doc_id,
            target_node_id,
            amendment_action,
            valid_from,
            evidence_source,
            target_number,
            target_node["doc_type"],
            target_path,
            target_expression,
            cleaned_note,
            reviewer_id,
            source_quote,
            source_node["page_start"],
        )

        await conn.execute(
            """UPDATE conflict_findings
               SET review_status = 'linked_amendment',
                   linked_amendment_id = $2,
                   reviewed_by = $3,
                   reviewed_at = now(),
                   review_note = COALESCE($4, review_note)
               WHERE id = $1""",
            finding_id,
            amendment_id,
            reviewer_id,
            cleaned_note,
        )
        await append_audit(
            conn,
            principal_id=reviewer_id,
            action="conflict_finding.create_amendment_draft",
            target_type="conflict_finding",
            target_id=str(finding_id),
            metadata={
                "linked_amendment_id": str(amendment_id),
                "action": amendment_action,
                "source_side": source_side,
                "review_status": "draft",
            },
        )

    return {
        "finding_id": str(finding_id),
        "review_status": "linked_amendment",
        "linked_amendment_id": str(amendment_id),
        "amendment_review_status": "draft",
        "reference_notice": REFERENCE_NOTICE,
    }


async def load_authority_rule_objects(conn: Any) -> list[AuthorityRule]:
    """Load active ``legal_authority_rules`` rows as ``AuthorityRule`` objects."""
    rows = await conn.fetch(
        """SELECT rule_code, doc_type, issuing_body_pattern, authority_rank,
                  authority_tier_label, is_ambiguous_without_issuer,
                  match_priority, is_active, note
           FROM legal_authority_rules
           WHERE is_active
           ORDER BY doc_type ASC, match_priority ASC, rule_code ASC"""
    )
    return [
        AuthorityRule(
            rule_code=row["rule_code"],
            doc_type=row["doc_type"],
            issuing_body_pattern=row["issuing_body_pattern"],
            authority_rank=int(row["authority_rank"]),
            authority_tier_label=row["authority_tier_label"],
            is_ambiguous_without_issuer=bool(row["is_ambiguous_without_issuer"]),
            match_priority=int(row["match_priority"]),
            is_active=bool(row["is_active"]),
            note=row["note"],
        )
        for row in rows
    ]


async def list_authority_rules(
    pool: Any, *, include_inactive: bool = False
) -> list[dict[str, Any]]:
    """List configurable ``legal_authority_rules`` rows for admin inspection."""
    where = "" if include_inactive else "WHERE is_active"
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""SELECT id, rule_code, doc_type, issuing_body_pattern, authority_rank,
                       authority_tier_label, is_ambiguous_without_issuer,
                       match_priority, note, is_active, updated_by, updated_at
                FROM legal_authority_rules
                {where}
                ORDER BY authority_rank ASC, doc_type ASC, match_priority ASC, rule_code ASC"""
        )
    return [
        {
            "id": str(row["id"]),
            "rule_code": row["rule_code"],
            "doc_type": row["doc_type"],
            "issuing_body_pattern": row["issuing_body_pattern"],
            "authority_rank": int(row["authority_rank"]),
            "authority_tier_label": row["authority_tier_label"],
            "is_ambiguous_without_issuer": bool(row["is_ambiguous_without_issuer"]),
            "match_priority": int(row["match_priority"]),
            "note": row["note"],
            "is_active": bool(row["is_active"]),
            "updated_by": str(row["updated_by"]) if row["updated_by"] is not None else None,
            "updated_at": _iso(row["updated_at"]),
        }
        for row in rows
    ]


async def update_authority_rule(
    pool: Any,
    *,
    actor_id: UUID,
    rule_code: str,
    authority_rank: int | None = None,
    authority_tier_label: str | None = None,
    issuing_body_pattern: str | None = None,
    clear_pattern: bool = False,
    is_ambiguous_without_issuer: bool | None = None,
    match_priority: int | None = None,
    note: str | None = None,
    is_active: bool | None = None,
) -> dict[str, Any]:
    """Update an existing ``legal_authority_rules`` entry and record audit trail."""
    if authority_rank is not None and not 1 <= authority_rank <= 1000:
        raise ConflictStoreError("INVALID_REQUEST", 422)
    if issuing_body_pattern is not None:
        try:
            re.compile(issuing_body_pattern)
        except re.error as exc:
            raise ConflictStoreError("INVALID_REGEX_PATTERN", 422) from exc

    async with pool.acquire() as conn, conn.transaction():
        existing = await conn.fetchrow(
            "SELECT * FROM legal_authority_rules WHERE rule_code = $1 FOR UPDATE",
            rule_code,
        )
        if existing is None:
            raise ConflictStoreError("AUTHORITY_RULE_NOT_FOUND", 404)

        next_pattern = (
            None
            if clear_pattern
            else (
                issuing_body_pattern
                if issuing_body_pattern is not None
                else existing["issuing_body_pattern"]
            )
        )
        next_rank = (
            authority_rank if authority_rank is not None else existing["authority_rank"]
        )
        next_label = (
            authority_tier_label.strip()
            if authority_tier_label is not None and authority_tier_label.strip()
            else existing["authority_tier_label"]
        )
        next_ambig = (
            is_ambiguous_without_issuer
            if is_ambiguous_without_issuer is not None
            else existing["is_ambiguous_without_issuer"]
        )
        next_prio = (
            match_priority if match_priority is not None else existing["match_priority"]
        )
        next_note = note if note is not None else existing["note"]
        next_active = is_active if is_active is not None else existing["is_active"]

        updated = await conn.fetchrow(
            """UPDATE legal_authority_rules
               SET issuing_body_pattern = $2,
                   authority_rank = $3,
                   authority_tier_label = $4,
                   is_ambiguous_without_issuer = $5,
                   match_priority = $6,
                   note = $7,
                   is_active = $8,
                   updated_by = $9,
                   updated_at = now()
               WHERE rule_code = $1
               RETURNING *""",
            rule_code,
            next_pattern,
            next_rank,
            next_label,
            next_ambig,
            next_prio,
            next_note,
            next_active,
            actor_id,
        )
        await append_audit(
            conn,
            principal_id=actor_id,
            action="legal_authority_rule.update",
            target_type="legal_authority_rule",
            target_id=rule_code,
            metadata={"authority_rank": next_rank, "is_active": next_active},
        )
    return {
        "id": str(updated["id"]),
        "rule_code": updated["rule_code"],
        "doc_type": updated["doc_type"],
        "issuing_body_pattern": updated["issuing_body_pattern"],
        "authority_rank": int(updated["authority_rank"]),
        "authority_tier_label": updated["authority_tier_label"],
        "is_ambiguous_without_issuer": bool(updated["is_ambiguous_without_issuer"]),
        "match_priority": int(updated["match_priority"]),
        "note": updated["note"],
        "is_active": bool(updated["is_active"]),
        "updated_by": str(updated["updated_by"]) if updated["updated_by"] else None,
        "updated_at": _iso(updated["updated_at"]),
    }
