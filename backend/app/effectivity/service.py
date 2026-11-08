"""Review queue, attestations and the user-facing effectivity view (design §9, D7, D10)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

from ..audit import append_audit
from ..storage.authorized_search import ALLOWED_DOCUMENTS_SQL
from .resolver import STATUSES
from .store import (
    clause_view,
    detect_and_store_dates,
    extract_version_relations,
    load_effectivity,
    publish_snapshot,
    rematch_unresolved,
)

ACTIONS = ("modify", "replace", "add", "repeal", "repeal_partial", "suspend", "commence")


class EffectivityError(Exception):
    def __init__(self, code: str, status_code: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


async def can_review(connection: Any, user_id: UUID, document_ids: Sequence[UUID | None]) -> bool:
    """D10: REVIEWER with ``can_review`` on a category of the source or target document."""

    ids = [item for item in document_ids if item is not None]
    if not ids:
        return False
    return bool(await connection.fetchval(
        """SELECT EXISTS (
             SELECT 1 FROM document_categories dc
             JOIN category_acl ca ON ca.category_id = dc.category_id AND ca.can_review
             JOIN categories c ON c.id = ca.category_id AND c.deleted_at IS NULL
             JOIN users u ON u.id = ca.user_id AND u.disabled_at IS NULL
             WHERE ca.user_id = $1 AND dc.document_id = ANY($2::uuid[]))""",
        user_id, ids,
    ))


_PROPOSAL_SQL = """
SELECT a.id, a.action, a.scope, a.valid_from, a.valid_to, a.review_status, a.proposed_by,
       a.confidence, a.condition_text, a.source_quote, a.source_page, a.target_number,
       a.target_path, a.target_expression, a.resolution_state, a.model_version,
       a.recorded_at, a.reviewed_at, a.review_note, a.review_batch_id,
       a.source_document_id, sd.document_number AS source_number, sd.title AS source_title,
       a.target_document_id, td.document_number AS target_doc_number,
       td.title AS target_title, a.target_node_id, tn.citation_label AS target_label,
       a.source_node_id, sn.citation_label AS source_label, ru.display_name AS reviewer
FROM node_amendments a
JOIN documents sd ON sd.id = a.source_document_id
LEFT JOIN documents td ON td.id = a.target_document_id
LEFT JOIN document_nodes tn ON tn.id = a.target_node_id
LEFT JOIN document_nodes sn ON sn.id = a.source_node_id
LEFT JOIN users ru ON ru.id = a.reviewed_by
WHERE a.superseded_by IS NULL
  AND ($2::text IS NULL OR a.review_status::text = $2)
  AND ($3::uuid IS NULL OR a.source_document_id = $3)
  AND EXISTS (
      SELECT 1 FROM document_categories dc
      JOIN category_acl ca ON ca.category_id = dc.category_id AND ca.can_review
      JOIN categories c ON c.id = ca.category_id AND c.deleted_at IS NULL
      WHERE ca.user_id = $1
        AND dc.document_id IN (a.source_document_id, a.target_document_id))
ORDER BY sd.document_number NULLS LAST, a.source_document_id, a.recorded_at, a.id
LIMIT $4 OFFSET $5
"""


def _proposal(row: Any) -> dict[str, Any]:
    return {
        "id": str(row["id"]), "action": row["action"], "scope": row["scope"],
        "valid_from": row["valid_from"].isoformat() if row["valid_from"] else None,
        "valid_to": row["valid_to"].isoformat() if row["valid_to"] else None,
        "review_status": row["review_status"], "proposed_by": row["proposed_by"],
        "confidence": float(row["confidence"]) if row["confidence"] is not None else None,
        "condition_text": row["condition_text"], "source_quote": row["source_quote"],
        "source_page": row["source_page"], "source_label": row["source_label"],
        "source_node_id": str(row["source_node_id"]),
        "target_number": row["target_number"], "target_path": row["target_path"],
        "target_expression": row["target_expression"],
        "resolution_state": row["resolution_state"],
        "target_document_id": str(row["target_document_id"]) if row["target_document_id"]
        else None,
        "target_document_number": row["target_doc_number"], "target_title": row["target_title"],
        "target_node_id": str(row["target_node_id"]) if row["target_node_id"] else None,
        "target_label": row["target_label"], "model_version": row["model_version"],
        "reviewed_by": row["reviewer"],
        "reviewed_at": row["reviewed_at"].isoformat() if row["reviewed_at"] else None,
        "review_note": row["review_note"],
        "review_batch_id": str(row["review_batch_id"]) if row["review_batch_id"] else None,
    }


async def list_proposals(
    pool: Any, *, reviewer_id: UUID, status: str | None = "draft",
    source_document_id: UUID | None = None, limit: int = 200, offset: int = 0,
) -> dict[str, Any]:
    """Proposals grouped by the document that states them (the amending document)."""

    async with pool.acquire() as connection:
        rows = await connection.fetch(
            _PROPOSAL_SQL, reviewer_id, status, source_document_id, limit, offset
        )
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row["source_document_id"])
        group = groups.setdefault(key, {
            "source_document_id": key, "source_number": row["source_number"],
            "source_title": row["source_title"], "proposals": [],
        })
        group["proposals"].append(_proposal(row))
    return {"groups": list(groups.values()), "count": len(rows), "limit": limit,
            "offset": offset}


async def review_proposals(
    pool: Any, *, reviewer_id: UUID, decisions: Sequence[dict[str, Any]], note: str,
) -> dict[str, Any]:
    """Approve/reject a batch.  One audit record per relation, sharing the batch id.

    A correction (other date, target or action) keeps the proposal as history and
    stores the corrected relation as a new row (``superseded_by``).
    """

    note = note.strip()
    if not note or not decisions:
        raise EffectivityError("INVALID_REQUEST", 422)
    batch_id = uuid4()
    now = datetime.now(UTC)
    results: list[dict[str, Any]] = []
    async with pool.acquire() as connection, connection.transaction():
        for decision in decisions:
            relation_id = UUID(str(decision["relation_id"]))
            row = await connection.fetchrow(
                "SELECT * FROM node_amendments WHERE id = $1 FOR UPDATE", relation_id
            )
            if row is None:
                raise EffectivityError("RELATION_NOT_FOUND", 404)
            if row["superseded_by"] is not None or row["review_status"] not in {
                "draft", "pending_review"
            }:
                raise EffectivityError("RELATION_ALREADY_REVIEWED", 409)
            target_document = (
                UUID(str(decision["target_document_id"])) if decision.get("target_document_id")
                else row["target_document_id"]
            )
            if not await can_review(
                connection, reviewer_id, [row["source_document_id"], target_document]
            ):
                raise EffectivityError("REVIEW_SCOPE_REQUIRED", 403)
            # The person (or account) that proposed a relation never confirms it.
            if row["proposer_id"] is not None and row["proposer_id"] == reviewer_id:
                raise EffectivityError("SELF_APPROVAL_DENIED", 403)
            verdict = decision.get("decision")
            if verdict == "reject":
                await connection.execute(
                    """UPDATE node_amendments SET review_status = 'rejected', reviewed_by = $2,
                         reviewed_at = $3, review_batch_id = $4, review_note = $5
                       WHERE id = $1""",
                    relation_id, reviewer_id, now, batch_id, note,
                )
                final_id = relation_id
            elif verdict == "approve":
                final_id = await _approve(
                    connection, row, decision, target_document, reviewer_id, now, batch_id, note
                )
            else:
                raise EffectivityError("INVALID_REQUEST", 422)
            await append_audit(
                connection, principal_id=reviewer_id, action="effectivity.review_relation",
                target_type="node_amendment", target_id=str(final_id),
                metadata={"batch_id": str(batch_id), "decision": verdict,
                          "proposal_id": str(relation_id),
                          "corrected": final_id != relation_id},
            )
            results.append({"relation_id": str(relation_id), "decision": verdict,
                            "stored_id": str(final_id)})
        snapshot = await publish_snapshot(connection, actor_id=reviewer_id)
    return {"batch_id": str(batch_id), "results": results, "snapshot": snapshot}


async def _approve(
    connection: Any, row: Any, decision: dict[str, Any], target_document: UUID | None,
    reviewer_id: UUID, now: datetime, batch_id: UUID, note: str,
) -> UUID:
    valid_from = _date(decision.get("valid_from")) or row["valid_from"]
    action = decision.get("action") or row["action"]
    if action not in ACTIONS:
        raise EffectivityError("INVALID_REQUEST", 422)
    if target_document is None:
        raise EffectivityError("RELATION_TARGET_REQUIRED", 422)
    if valid_from is None:
        raise EffectivityError("RELATION_DATE_REQUIRED", 422)
    target_node = (
        UUID(str(decision["target_node_id"])) if decision.get("target_node_id")
        else row["target_node_id"]
    )
    if row["scope"] == "node" and target_node is None:
        raise EffectivityError("RELATION_TARGET_REQUIRED", 422)
    changed = (
        valid_from != row["valid_from"] or action != row["action"]
        or target_document != row["target_document_id"] or target_node != row["target_node_id"]
    )
    if not changed:
        await connection.execute(
            """UPDATE node_amendments SET review_status = 'approved', reviewed_by = $2,
                 reviewed_at = $3, review_batch_id = $4, review_note = $5
               WHERE id = $1""",
            row["id"], reviewer_id, now, batch_id, note,
        )
        return UUID(str(row["id"]))
    new_id = await connection.fetchval(
        """INSERT INTO node_amendments
             (source_node_id, source_document_id, target_document_id, target_node_id, scope,
              action, valid_from, valid_to, evidence_source, review_status, reviewed_by,
              reviewed_at, review_batch_id, review_note, target_number, target_doc_type,
              target_issue_date, target_path, target_expression, resolution_state,
              condition_text, proposed_by, proposer_id, confidence, model_version,
              source_quote, source_page)
           SELECT source_node_id, source_document_id, $2, $3, scope, $4, $5, valid_to,
                  evidence_source, 'approved', $6, $7, $8, $9, target_number,
                  target_doc_type, target_issue_date, target_path, target_expression,
                  'resolved', condition_text, proposed_by, proposer_id, confidence,
                  model_version, source_quote, source_page
           FROM node_amendments WHERE id = $1 RETURNING id""",
        row["id"], target_document, target_node, action, valid_from, reviewer_id, now,
        batch_id, note,
    )
    await connection.execute(
        """UPDATE node_amendments SET superseded_by = $2, review_status = 'rejected',
             reviewed_by = $3, reviewed_at = $4, review_batch_id = $5,
             review_note = 'Đã sửa khi duyệt'
           WHERE id = $1""",
        row["id"], new_id, reviewer_id, now, batch_id,
    )
    return UUID(str(new_id))


def _date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


async def create_proposal(
    pool: Any, *, proposer_id: UUID, source_node_id: UUID, action: str,
    target_document_id: UUID | None, target_number: str | None, target_node_id: UUID | None,
    target_path: str | None, valid_from: date | None, condition_text: str | None,
    source_quote: str | None,
) -> dict[str, Any]:
    """A person's proposal; another reviewer must confirm it."""

    if action not in ACTIONS or (target_document_id is None and not target_number):
        raise EffectivityError("INVALID_REQUEST", 422)
    async with pool.acquire() as connection, connection.transaction():
        source = await connection.fetchrow(
            """SELECT n.document_id, n.page_start, n.text_original FROM document_nodes n
               JOIN document_versions dv ON dv.id = n.document_version_id
               WHERE n.id = $1 AND dv.review_status = 'approved'""",
            source_node_id,
        )
        if source is None:
            raise EffectivityError("SOURCE_NODE_NOT_FOUND", 404)
        if not await can_review(connection, proposer_id, [source["document_id"],
                                                          target_document_id]):
            raise EffectivityError("REVIEW_SCOPE_REQUIRED", 403)
        relation_id = await connection.fetchval(
            """INSERT INTO node_amendments
                 (source_node_id, source_document_id, target_document_id, target_node_id,
                  scope, action, valid_from, evidence_source, review_status, target_number,
                  target_path, target_expression, resolution_state, condition_text,
                  proposed_by, proposer_id, source_quote, source_page)
               VALUES ($1, $2, $3, $4, $5, $6, $7, 'person', 'draft', $8, $9, $10, $11, $12,
                       'person', $13, $14, $15) RETURNING id""",
            source_node_id, source["document_id"], target_document_id, target_node_id,
            "node" if target_node_id else "document", action, valid_from, target_number,
            target_path, target_number or target_path,
            "resolved" if target_document_id else "unresolved", condition_text, proposer_id,
            (source_quote or source["text_original"])[:1200], source["page_start"],
        )
        await append_audit(
            connection, principal_id=proposer_id, action="effectivity.propose_relation",
            target_type="node_amendment", target_id=str(relation_id),
            metadata={"action": action},
        )
        await publish_snapshot(connection, actor_id=proposer_id)
    return {"id": str(relation_id), "review_status": "draft"}


async def create_attestation(
    pool: Any, *, reviewer_id: UUID, document_id: UUID, result: str, valid_for_from: date,
    valid_for_to: date, source_note: str, source_document_id: UUID | None = None,
) -> dict[str, Any]:
    """Hard rule 1: the only way to "active + verified" is this human statement."""

    today = datetime.now(UTC).date()
    if result not in STATUSES or result == "unknown" or not source_note.strip():
        raise EffectivityError("INVALID_REQUEST", 422)
    if valid_for_to < valid_for_from:
        raise EffectivityError("INVALID_REQUEST", 422)
    # D14: "còn hiệu lực" is stated up to the verification date, not into the future.
    if result == "active" and valid_for_to > today:
        raise EffectivityError("ATTESTATION_FUTURE_DATE", 422)
    async with pool.acquire() as connection, connection.transaction():
        if not await can_review(connection, reviewer_id, [document_id]):
            raise EffectivityError("REVIEW_SCOPE_REQUIRED", 403)
        attestation_id = await connection.fetchval(
            """INSERT INTO effectivity_attestations
                 (target_document_id, result, valid_for_from, valid_for_to, source_note,
                  source_document_id, attested_by)
               VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id""",
            document_id, result, valid_for_from, valid_for_to, source_note.strip()[:2000],
            source_document_id, reviewer_id,
        )
        await connection.execute(
            """UPDATE effectivity_attestations SET superseded_by = $2,
                 status_changed_at = now(), status_reason = 'superseded'
               WHERE target_document_id = $1 AND target_node_id IS NULL AND id <> $2
                 AND superseded_by IS NULL AND status <> 'revoked'""",
            document_id, attestation_id,
        )
        await append_audit(
            connection, principal_id=reviewer_id, action="effectivity.attest",
            target_type="document", target_id=str(document_id),
            metadata={"attestation_id": str(attestation_id), "result": result,
                      "valid_for_from": valid_for_from.isoformat(),
                      "valid_for_to": valid_for_to.isoformat()},
        )
        snapshot = await publish_snapshot(connection, actor_id=reviewer_id)
    return {"id": str(attestation_id), "status": "valid", "snapshot": snapshot}


async def revoke_attestation(
    pool: Any, *, reviewer_id: UUID, attestation_id: UUID, reason: str
) -> dict[str, Any]:
    if not reason.strip():
        raise EffectivityError("INVALID_REQUEST", 422)
    async with pool.acquire() as connection, connection.transaction():
        row = await connection.fetchrow(
            "SELECT target_document_id, status FROM effectivity_attestations WHERE id = $1"
            " FOR UPDATE",
            attestation_id,
        )
        if row is None:
            raise EffectivityError("ATTESTATION_NOT_FOUND", 404)
        if not await can_review(connection, reviewer_id, [row["target_document_id"]]):
            raise EffectivityError("REVIEW_SCOPE_REQUIRED", 403)
        await connection.execute(
            """UPDATE effectivity_attestations SET status = 'revoked', status_reason = $2,
                 status_changed_at = now() WHERE id = $1""",
            attestation_id, reason.strip()[:500],
        )
        await append_audit(
            connection, principal_id=reviewer_id, action="effectivity.revoke_attestation",
            target_type="effectivity_attestation", target_id=str(attestation_id),
            metadata={"reason": reason.strip()[:500]},
        )
        snapshot = await publish_snapshot(connection, actor_id=reviewer_id)
    return {"id": str(attestation_id), "status": "revoked", "snapshot": snapshot}


async def list_attestations(pool: Any, *, document_id: UUID) -> list[dict[str, Any]]:
    async with pool.acquire() as connection:
        rows = await connection.fetch(
            """SELECT t.*, u.display_name FROM effectivity_attestations t
               JOIN users u ON u.id = t.attested_by
               WHERE t.target_document_id = $1 ORDER BY t.attested_at DESC""",
            document_id,
        )
    return [{
        "id": str(row["id"]), "result": row["result"],
        "valid_for_from": row["valid_for_from"].isoformat(),
        "valid_for_to": row["valid_for_to"].isoformat(), "source_note": row["source_note"],
        "attested_by": row["display_name"], "attested_at": row["attested_at"].isoformat(),
        "status": row["status"], "status_reason": row["status_reason"],
        "superseded_by": str(row["superseded_by"]) if row["superseded_by"] else None,
    } for row in rows]


async def document_effectivity(
    pool: Any, *, principal_id: UUID, document_id: UUID, as_of: date,
) -> dict[str, Any] | None:
    """Both axes, approved relations in both directions and the document group,
    limited to documents the user may see (design §5: no leak outside the ACL)."""

    async with pool.acquire() as connection, connection.transaction():
        await connection.execute(
            "SELECT set_config('app.user_id', $1, true)", str(principal_id)
        )
        allowed = {
            row["document_id"] for row in await connection.fetch(ALLOWED_DOCUMENTS_SQL)
        }
        if document_id not in allowed:
            return None
        documents, _, data_date = await load_effectivity(
            connection, document_ids=[document_id], as_of=as_of
        )
        relations = await connection.fetch(
            """SELECT a.id, a.action, a.scope, a.valid_from, a.review_status, a.target_path,
                      a.source_document_id, a.target_document_id, a.source_quote,
                      a.source_page, a.source_node_id, sn.citation_label AS source_label,
                      tn.citation_label AS target_label,
                      sd.document_number AS source_number, sd.title AS source_title,
                      td.document_number AS target_number, td.title AS target_title
               FROM node_amendments a
               JOIN documents sd ON sd.id = a.source_document_id
               LEFT JOIN documents td ON td.id = a.target_document_id
               LEFT JOIN document_nodes sn ON sn.id = a.source_node_id
               LEFT JOIN document_nodes tn ON tn.id = a.target_node_id
               WHERE (a.target_document_id = $1 OR a.source_document_id = $1)
                 AND a.superseded_by IS NULL AND a.review_status <> 'rejected'
                 AND a.target_document_id IS NOT NULL
               ORDER BY a.valid_from NULLS LAST, a.id""",
            document_id,
        )
        references = await connection.fetch(
            """SELECT r.reference_kind, r.source_document_id, r.target_document_id,
                      sd.document_number AS source_number, sd.title AS source_title,
                      td.document_number AS target_number, td.title AS target_title
               FROM node_references r
               JOIN documents sd ON sd.id = r.source_document_id
               JOIN documents td ON td.id = r.target_document_id
               WHERE r.target_document_id = $1 OR r.source_document_id = $1""",
            document_id,
        )
    hidden = 0
    items: list[dict[str, Any]] = []
    for row in relations:
        other = row["source_document_id"] if row["target_document_id"] == document_id \
            else row["target_document_id"]
        if other not in allowed:
            hidden += 1
            continue
        items.append({
            "id": str(row["id"]), "action": row["action"], "scope": row["scope"],
            "valid_from": row["valid_from"].isoformat() if row["valid_from"] else None,
            "review_status": row["review_status"],
            "direction": "incoming" if row["target_document_id"] == document_id else "outgoing",
            "source_document_id": str(row["source_document_id"]),
            "source_number": row["source_number"], "source_title": row["source_title"],
            "source_label": row["source_label"], "source_page": row["source_page"],
            "source_quote": row["source_quote"],
            "source_node_id": str(row["source_node_id"]),
            "target_document_id": str(row["target_document_id"]),
            "target_number": row["target_number"], "target_title": row["target_title"],
            "target_label": row["target_label"], "target_path": row["target_path"],
        })
    related: list[dict[str, Any]] = []
    for row in references:
        other = row["source_document_id"] if row["target_document_id"] == document_id \
            else row["target_document_id"]
        if other not in allowed:
            hidden += 1
            continue
        related.append({
            "kind": row["reference_kind"],
            "direction": "incoming" if row["target_document_id"] == document_id else "outgoing",
            "document_id": str(other),
            "document_number": row["source_number"] if other == row["source_document_id"]
            else row["target_number"],
            "title": row["source_title"] if other == row["source_document_id"]
            else row["target_title"],
        })
    view = clause_view(documents.get(str(document_id)), None)
    return {
        "document_id": str(document_id), "as_of_date": as_of.isoformat(),
        "data_date": data_date.isoformat() if data_date else None,
        "effectivity": view.model_dump(mode="json") if view else None,
        "relations": items, "related_documents": related,
        "outside_scope_relations": hidden,
        "outside_scope_note": (
            "Có văn bản liên quan ngoài phạm vi được cấp quyền." if hidden else None
        ),
    }


async def extract_all(pool: Any, *, actor_id: UUID | None) -> dict[str, Any]:
    """Run the rules on every approved version (idempotent), then publish a snapshot."""

    totals: dict[str, int] = {"versions": 0, "relations": 0, "references": 0, "node_dates": 0,
                              "ai_candidates": 0, "rematched": 0}
    async with pool.acquire() as connection:
        versions = await connection.fetch(
            """SELECT DISTINCT ON (document_id) id, document_id FROM document_versions
               WHERE review_status = 'approved' ORDER BY document_id, version_number DESC"""
        )
    for version in versions:
        async with pool.acquire() as connection, connection.transaction():
            if not await connection.fetchval(
                "SELECT dates_detected <> '{}'::jsonb FROM document_versions WHERE id = $1",
                version["id"],
            ):
                # Approved before G1: use the dates read by rule; nobody confirmed
                # them, so dates_confirmed_by stays empty.
                detected = await detect_and_store_dates(connection, version["id"])
                await connection.execute(
                    """UPDATE document_versions
                       SET effective_from = COALESCE(effective_from, $2::date),
                           publication_date = COALESCE(publication_date, $3::date)
                       WHERE id = $1""",
                    version["id"], _date(detected.get("effective_from")),
                    _date(detected.get("issue_date")),
                )
                totals["dates_detected"] = totals.get("dates_detected", 0) + 1
            counts = await extract_version_relations(connection, version["id"])
            for key, value in counts.items():
                totals[key] = totals.get(key, 0) + int(value)
            totals["versions"] += 1
    async with pool.acquire() as connection, connection.transaction():
        for version in versions:
            totals["rematched"] += await rematch_unresolved(connection, version["document_id"])
        snapshot = await publish_snapshot(connection, actor_id=actor_id)
        await append_audit(
            connection, principal_id=actor_id, action="effectivity.extract_all",
            target_type="effectivity", target_id=None, metadata=totals,
        )
    return {**totals, "snapshot": snapshot}
