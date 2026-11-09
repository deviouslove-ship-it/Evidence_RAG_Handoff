"""Database side of effectivity: extraction, number matching, snapshots, views."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from ..schemas import AmendmentStatus, EffectivityView, VerificationState
from .extract import (
    DocRef,
    NodeText,
    detect_dates,
    extract_relations,
    is_consolidated,
    node_amendment_items,
    node_effective_dates,
    number_key,
)
from .resolver import Attestation, Interval, Relation, cap_verification, resolve_intervals

EXTRACTOR_REVISION = "rule:effectivity-v1"
CLAUSE_LEVEL_WARNING = (
    "Hiệu lực đến cấp Điều, Khoản, Điểm chưa được xác minh; kết quả phản ánh hiệu lực "
    "cấp văn bản."
)
NOTE_PARTIAL_UNMAPPED = (
    "Văn bản đã được sửa đổi một phần; chưa xác định khoản này có bị ảnh hưởng."
)
NOTE_SOURCE_UNAVAILABLE = "Một căn cứ xác định hiệu lực hiện không mở được trong kho."
_TERMINAL = {"repealed", "replaced", "suspended"}
# SQL twin of ``extract.number_key`` (accents folded, spaces removed, lower case).
NUMBER_KEY_SQL = (
    "btrim(lower(translate(regexp_replace({col}, '\\s+', '', 'g'), "
    "'đĐÐ–—', 'ddd--')), '.-/')"
)
_BASE_NUMBER = re.compile(r"\([^)]*\)$")
# Axis A of node ``n`` at ``{as_of}`` for the search SQL: a terminating document
# status wins, otherwise a node exception, otherwise the document interval.
EFFECTIVE_STATUS_LATERAL = """
        SELECT CASE WHEN de.status IN ('repealed', 'replaced', 'suspended') OR ne.status IS NULL
                    THEN de.status ELSE ne.status END AS status
        FROM (SELECT 1) AS one
        LEFT JOIN LATERAL (
            SELECT nei.effective_status::text AS status
            FROM node_effective_intervals nei
            JOIN effectivity_snapshot_revisions esr
              ON esr.id = nei.snapshot_revision_id AND esr.is_active
            WHERE nei.node_id = n.id AND nei.valid_from <= {as_of}::date
              AND (nei.valid_to IS NULL OR nei.valid_to > {as_of}::date)
            ORDER BY nei.valid_from DESC LIMIT 1) ne ON TRUE
        LEFT JOIN LATERAL (
            SELECT dei.effective_status AS status
            FROM document_effective_intervals dei
            JOIN effectivity_snapshot_revisions esr
              ON esr.id = dei.snapshot_revision_id AND esr.is_active
            WHERE dei.document_id = n.document_id AND dei.valid_from <= {as_of}::date
              AND (dei.valid_to IS NULL OR dei.valid_to > {as_of}::date)
            LIMIT 1) de ON TRUE"""


def _number_key_sql(column: str) -> str:
    return NUMBER_KEY_SQL.format(col=column)


# --------------------------------------------------------------- matching
async def match_target(
    connection: Any, ref: DocRef, *, exclude_document: UUID | None = None,
) -> tuple[str, UUID | None]:
    """Identity = number + type + issue date + issuing body (design §5).

    Returns ``resolved`` with one document, ``ambiguous`` (several candidates the
    rules cannot separate; a person decides) or ``unresolved`` (not in the store).
    """

    rows = await connection.fetch(
        f"""/* effectivity match */
        SELECT d.id, d.doc_type, d.title, d.document_number, d.issuing_body,
               dv.publication_date, dv.effective_from,
               {_number_key_sql('d.document_number')} AS key
        FROM documents d
        JOIN LATERAL (
            SELECT publication_date, effective_from FROM document_versions v
            WHERE v.document_id = d.id AND v.review_status = 'approved'
              AND v.retired_at IS NULL
            ORDER BY v.version_number DESC LIMIT 1) dv ON TRUE
        WHERE d.deleted_at IS NULL AND d.document_number IS NOT NULL
          AND ({_number_key_sql('d.document_number')} = $1
               OR regexp_replace({_number_key_sql('d.document_number')}, '\\([^)]*\\)$', '')
                  = $2)
          AND ($3::uuid IS NULL OR d.id <> $3)""",
        ref.number_key, _BASE_NUMBER.sub("", ref.number_key), exclude_document,
    )
    if not rows:
        return "unresolved", None
    exact = [row for row in rows if row["key"] == ref.number_key]
    candidates = exact or rows
    candidates = [row for row in candidates if _type_compatible(ref.doc_type, row)] or []
    if not candidates:
        return "ambiguous", None
    if len(candidates) > 1 and ref.issue_date is not None:
        dated = [row for row in candidates if row["publication_date"] == ref.issue_date]
        candidates = dated or candidates
    if len(candidates) > 1:
        # A main document and its annexes share a number; the main one states
        # its own effective date.
        main = [row for row in candidates if row["effective_from"] is not None]
        candidates = main or candidates
    if len(candidates) == 1:
        return "resolved", candidates[0]["id"]
    return "ambiguous", None


def _type_compatible(ref_type: str, row: Any) -> bool:
    number = str(row["document_number"] or "").upper()
    if ref_type == "consolidated" or "VBHN" in number:
        return ref_type == "consolidated" and "VBHN" in number
    stored = str(row["doc_type"] or "other")
    if stored == "other" or ref_type in {"other", "ordinance", "resolution"}:
        return True
    return stored == ref_type


# ------------------------------------------------------------- extraction
async def load_node_texts(connection: Any, version_id: UUID) -> list[NodeText]:
    rows = await connection.fetch(
        """SELECT id::text, node_type::text, path, text_original, page_start,
                  parent_id::text
           FROM document_nodes WHERE document_version_id = $1 ORDER BY path, id""",
        version_id,
    )
    return [NodeText(r[0], r[1], r[2], r[3], r[4], r[5]) for r in rows]


async def detect_and_store_dates(connection: Any, version_id: UUID) -> dict[str, Any]:
    """Read issue/effective dates by rule and keep them for the source reviewer."""

    meta = await connection.fetchrow(
        """SELECT d.id,
                  CASE WHEN dv.admin_metadata IS NULL THEN d.doc_type
                       ELSE dv.admin_metadata->>'doc_type' END AS doc_type,
                  CASE WHEN dv.admin_metadata IS NULL THEN d.title
                       ELSE dv.admin_metadata->>'title' END AS title,
                  CASE WHEN dv.admin_metadata IS NULL THEN d.document_number
                       ELSE dv.admin_metadata->>'document_number' END AS document_number
           FROM document_versions dv JOIN documents d ON d.id = dv.document_id
           WHERE dv.id = $1""",
        version_id,
    )
    if meta is None:
        return {}
    nodes = await load_node_texts(connection, version_id)
    dates = detect_dates(
        nodes, doc_type=meta["doc_type"],
        consolidated=is_consolidated(meta["document_number"], meta["title"]),
    )
    detected = dates.to_json()
    await connection.execute(
        "UPDATE document_versions SET dates_detected = $2::jsonb WHERE id = $1",
        version_id, json.dumps(detected, ensure_ascii=False),
    )
    return detected


async def confirm_dates(
    connection: Any, version_id: UUID, reviewer_id: UUID, *,
    publication_date: date | None = None, effective_from: date | None = None,
) -> None:
    """At source approval: the reviewer confirms (or corrects) the dates read by rule."""

    row = await connection.fetchrow(
        "SELECT document_id, dates_detected, publication_date, effective_from"
        " FROM document_versions WHERE id = $1",
        version_id,
    )
    if row is None:
        return
    detected = row["dates_detected"]
    if isinstance(detected, str):
        detected = json.loads(detected)
    detected = detected or {}

    def _parse(value: Any) -> date | None:
        return date.fromisoformat(value) if isinstance(value, str) and value else None

    issue = publication_date or row["publication_date"] or _parse(detected.get("issue_date"))
    effective = effective_from or row["effective_from"] or _parse(detected.get("effective_from"))
    await connection.execute(
        """UPDATE document_versions
           SET publication_date = $2, effective_from = $3,
               dates_confirmed_by = $4, dates_confirmed_at = now()
           WHERE id = $1""",
        version_id, issue, effective, reviewer_id,
    )
    body = detected.get("issuing_body")
    if body:
        await connection.execute(
            "UPDATE documents SET issuing_body = COALESCE(issuing_body, $2) WHERE id = $1",
            row["document_id"], str(body)[:300],
        )


async def extract_version_relations(connection: Any, version_id: UUID) -> dict[str, int]:
    """Store rule proposals for one approved version; re-running adds nothing new."""

    meta = await connection.fetchrow(
        """SELECT d.id, d.doc_type, d.title, d.document_number, dv.effective_from
           FROM document_versions dv JOIN documents d ON d.id = dv.document_id
           WHERE dv.id = $1 AND dv.review_status = 'approved' AND dv.retired_at IS NULL""",
        version_id,
    )
    counts = {"relations": 0, "references": 0, "node_dates": 0, "ai_candidates": 0}
    if meta is None:
        return counts
    nodes = await load_node_texts(connection, version_id)
    own_key = number_key(meta["document_number"]) if meta["document_number"] else None
    extraction = extract_relations(
        nodes, own_number_key=own_key, title=meta["title"],
        document_number=meta["document_number"], effective_from=meta["effective_from"],
    )
    counts["ai_candidates"] = len(extraction.ai_candidates)
    for proposal in extraction.relations:
        assert proposal.target is not None
        state, target = await match_target(
            connection, proposal.target, exclude_document=meta["id"]
        )
        inserted = await connection.fetchval(
            """INSERT INTO node_amendments
                 (source_node_id, source_document_id, target_document_id, scope, action,
                  valid_from, evidence_source, review_status, target_number, target_doc_type,
                  target_issue_date, target_path, target_expression, resolution_state,
                  condition_text, proposed_by, confidence, source_quote, source_page,
                  extraction_key, model_version)
               VALUES ($1, $2, $3, 'document', $4, $5, $6, 'draft', $7, $8, $9, $10, $11,
                       $12, $13, 'rule', $14, $15, $16, $17, $6)
               ON CONFLICT (source_node_id, extraction_key) WHERE extraction_key IS NOT NULL
               DO NOTHING RETURNING id""",
            UUID(proposal.source_node_id), meta["id"], target, proposal.action,
            proposal.valid_from, EXTRACTOR_REVISION, proposal.target.number,
            proposal.target.doc_type, proposal.target.issue_date, proposal.target_path,
            f"{proposal.target.type_word} {proposal.target.number}", state,
            proposal.condition, proposal.confidence, proposal.quote, proposal.page,
            proposal.key,
        )
        counts["relations"] += int(inserted is not None)
    for reference in extraction.references:
        state, target = await match_target(
            connection, reference.target, exclude_document=meta["id"]
        )
        inserted = await connection.fetchval(
            """INSERT INTO node_references
                 (source_node_id, source_document_id, target_document_id, target_expression,
                  resolution_state, reference_kind, target_number, source_quote,
                  extraction_key)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
               ON CONFLICT (source_node_id, extraction_key) WHERE extraction_key IS NOT NULL
               DO NOTHING RETURNING id""",
            UUID(reference.source_node_id), meta["id"], target,
            f"{reference.target.type_word} {reference.target.number}", state,
            reference.kind, reference.target.number, reference.quote, reference.key,
        )
        counts["references"] += int(inserted is not None)
    counts["node_dates"] = await _store_node_dates(connection, meta, nodes)
    counts["node_relations"] = await _store_node_amendments(connection, meta, nodes, own_key)
    return counts


async def _store_node_amendments(
    connection: Any, meta: Any, nodes: Sequence[NodeText], own_key: str | None,
) -> int:
    """G3: "Sửa đổi khoản X Điều Y như sau" -> node-level proposal matched on the tree."""

    added = 0
    targets: dict[str, tuple[str, UUID | None]] = {}
    for node, ref, action, path in node_amendment_items(nodes, own_number_key=own_key):
        if ref.number_key not in targets:
            targets[ref.number_key] = await match_target(
                connection, ref, exclude_document=meta["id"]
            )
        state, document = targets[ref.number_key]
        target_node = await _resolve_node_path(connection, document, path) if document else None
        inserted = await connection.fetchval(
            """INSERT INTO node_amendments
                 (source_node_id, source_document_id, target_document_id, target_node_id,
                  scope, action, valid_from, evidence_source, review_status, target_number,
                  target_doc_type, target_path, target_expression, resolution_state,
                  proposed_by, confidence, source_quote, source_page, extraction_key,
                  model_version)
               VALUES ($1, $2, $3, $4, 'node', $5, $6, $7, 'draft', $8, $9, $10, $11, $12,
                       'rule', 0.85, $13, $14, $15, $7)
               ON CONFLICT (source_node_id, extraction_key) WHERE extraction_key IS NOT NULL
               DO NOTHING RETURNING id""",
            UUID(node.node_id), meta["id"], document, target_node, action,
            meta["effective_from"], EXTRACTOR_REVISION, ref.number, ref.doc_type, path,
            f"{path} {ref.type_word} {ref.number}",
            "resolved" if target_node else ("ambiguous" if state == "ambiguous" else
                                            "unresolved"),
            re.sub(r"\s+", " ", node.text)[:1200], node.page,
            f"node|{action}|{ref.number_key}|{path.lower()}",
        )
        added += int(inserted is not None)
    return added


async def _store_node_dates(connection: Any, meta: Any, nodes: Sequence[NodeText]) -> int:
    """"Điều 2 của Thông tư này có hiệu lực từ D": a node-level proposal (G3)."""

    added = 0
    for source_node, path, when, quote, page in node_effective_dates(nodes):
        target = await _resolve_node_path(connection, meta["id"], path)
        inserted = await connection.fetchval(
            """INSERT INTO node_amendments
                 (source_node_id, source_document_id, target_document_id, target_node_id,
                  scope, action, valid_from, evidence_source, review_status, target_path,
                  target_expression, resolution_state, proposed_by, confidence,
                  source_quote, source_page, extraction_key, model_version)
               VALUES ($1, $2, $2, $3, 'node', 'commence', $4, $5, 'draft', $6, $6, $7,
                       'rule', 0.9, $8, $9, $10, $5)
               ON CONFLICT (source_node_id, extraction_key) WHERE extraction_key IS NOT NULL
               DO NOTHING RETURNING id""",
            UUID(source_node), meta["id"], target, when, EXTRACTOR_REVISION, path,
            "resolved" if target else "unresolved", quote, page,
            f"commence|{path.lower()}|{when.isoformat()}",
        )
        added += int(inserted is not None)
    return added


async def _resolve_node_path(connection: Any, document_id: UUID, path: str) -> UUID | None:
    """Find the node "Điều 5" / "khoản 2 Điều 5" / "điểm a khoản 2 Điều 5" in a document."""

    from .node_paths import parse_target_path

    parsed = parse_target_path(path)
    if not parsed:
        return None
    rows = await connection.fetch(
        """SELECT n.id FROM document_nodes n
           JOIN document_versions dv ON dv.id = n.document_version_id
           WHERE n.document_id = $1 AND dv.review_status = 'approved' AND dv.retired_at IS NULL
             AND n.path ~ $2
           ORDER BY dv.version_number DESC, length(n.path) LIMIT 2""",
        document_id, parsed[0],
    )
    return rows[0]["id"] if len(rows) == 1 else None


async def rematch_unresolved(connection: Any, document_id: UUID) -> int:
    """A newly approved document may be the "not in the store yet" target of earlier relations."""

    number = await connection.fetchval(
        "SELECT document_number FROM documents WHERE id = $1", document_id
    )
    if not number:
        return 0
    key = number_key(number)
    base = _BASE_NUMBER.sub("", key)
    changed = 0
    for table in ("node_amendments", "node_references"):
        extra = ", target_doc_type, target_issue_date" if table == "node_amendments" else ""
        rows = await connection.fetch(
            f"""SELECT id, target_number{extra} FROM {table}
                WHERE target_document_id IS NULL AND target_number IS NOT NULL
                  AND source_document_id IS DISTINCT FROM $1
                  AND regexp_replace({_number_key_sql('target_number')}, '\\([^)]*\\)$', '')
                      = $2""",
            document_id, base,
        )
        for row in rows:
            ref = DocRef(
                type_word="", doc_type=(row.get("target_doc_type") if extra else None)
                or ("consolidated" if "VBHN" in row["target_number"].upper() else "other"),
                number=row["target_number"], number_key=number_key(row["target_number"]),
                issue_date=row.get("target_issue_date") if extra else None, start=0, end=0,
            )
            state, target = await match_target(connection, ref)
            if state == "resolved" and target is not None:
                await connection.execute(
                    f"UPDATE {table} SET target_document_id = $2, resolution_state = 'resolved'"
                    " WHERE id = $1",
                    row["id"], target,
                )
                changed += 1
            elif state == "ambiguous":
                await connection.execute(
                    f"UPDATE {table} SET resolution_state = 'ambiguous' WHERE id = $1", row["id"]
                )
    return changed


async def process_approved_version(
    connection: Any, version_id: UUID, *, actor_id: UUID | None
) -> dict[str, Any]:
    """Run after source approval inside the approval transaction."""

    document_id = await connection.fetchval(
        "SELECT document_id FROM document_versions WHERE id = $1", version_id
    )
    counts: dict[str, Any] = dict(await extract_version_relations(connection, version_id))
    counts["rematched"] = await rematch_unresolved(connection, document_id)
    snapshot = await publish_snapshot(connection, actor_id=actor_id)
    counts["snapshot_revision"] = snapshot["revision"]
    return counts


# --------------------------------------------------------------- snapshot
async def publish_snapshot(connection: Any, *, actor_id: UUID | None) -> dict[str, Any]:
    """Recompute every document interval and activate it as a new snapshot."""

    await connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended("
        "current_database() || ':' || current_schema() || ':effectivity_snapshot', 0))"
    )
    documents = await connection.fetch(
        """SELECT d.id, dv.effective_from, dv.reviewed_at
           FROM documents d
           JOIN LATERAL (
             SELECT effective_from, reviewed_at FROM document_versions v
             WHERE v.document_id = d.id AND v.review_status = 'approved'
               AND v.retired_at IS NULL
             ORDER BY v.version_number DESC LIMIT 1) dv ON TRUE
           WHERE d.deleted_at IS NULL"""
    )
    relations = await connection.fetch(
        """SELECT a.id, a.target_document_id, a.target_node_id, a.scope, a.action,
                  a.valid_from, a.valid_to, a.review_status, a.condition_text,
                  COALESCE(sd.document_number, sd.title) AS source_label,
                  a.reviewed_by::text AS reviewer, a.reviewed_at
           FROM node_amendments a
           JOIN document_nodes sn ON sn.id = a.source_node_id
           JOIN document_versions sv ON sv.id = sn.document_version_id
           LEFT JOIN documents sd ON sd.id = a.source_document_id
           WHERE a.target_document_id IS NOT NULL AND a.superseded_by IS NULL
             AND sn.review_status = 'approved'
             AND sv.review_status = 'approved' AND sv.retired_at IS NULL
             AND a.review_status IN ('draft', 'pending_review', 'approved')"""
    )
    attestations = await connection.fetch(
        """SELECT t.id, t.target_document_id, t.target_node_id, t.result, t.valid_for_from,
                  t.valid_for_to, t.status, t.attested_by::text AS attested_by, t.attested_at,
                  t.source_note
           FROM effectivity_attestations t
           WHERE t.status <> 'revoked' AND t.superseded_by IS NULL"""
    )
    by_doc: dict[UUID, list[Relation]] = defaultdict(list)
    node_relations: dict[UUID, list[Any]] = defaultdict(list)
    for row in relations:
        if row["scope"] == "node":
            if row["target_node_id"] is not None:
                node_relations[row["target_node_id"]].append(row)
            continue
        by_doc[row["target_document_id"]].append(_relation(row))
    att_by_doc: dict[UUID, list[Attestation]] = defaultdict(list)
    for row in attestations:
        if row["target_node_id"] is None:
            att_by_doc[row["target_document_id"]].append(Attestation(
                id=str(row["id"]), result=row["result"], valid_for_from=row["valid_for_from"],
                valid_for_to=row["valid_for_to"], status=row["status"],
                attested_by=row["attested_by"], attested_at=row["attested_at"].isoformat(),
                source_note=row["source_note"],
            ))
    revision = int(await connection.fetchval(
        "SELECT COALESCE(max(revision), 0) + 1 FROM effectivity_snapshot_revisions"
    ))
    latest_approval = max(
        (row["reviewed_at"] for row in documents if row["reviewed_at"] is not None),
        default=None,
    )
    today = datetime.now(UTC).date()
    data_date = latest_approval.date() if latest_approval is not None else today
    data_date = max(data_date, today)
    source_revision = int(await connection.fetchval(
        "SELECT COALESCE(max(source_review_revision), 1) FROM document_versions"
    ))
    snapshot_id = await connection.fetchval(
        """INSERT INTO effectivity_snapshot_revisions
             (revision, source_review_revision, is_active, data_date)
           VALUES ($1, $2, FALSE, $3) RETURNING id""",
        revision, source_revision, data_date,
    )
    records: list[tuple[Any, ...]] = []
    for row in documents:
        for item in resolve_intervals(
            effective_from=row["effective_from"], relations=by_doc.get(row["id"], ()),
            attestations=att_by_doc.get(row["id"], ()),
        ):
            records.append(_interval_record(snapshot_id, row["id"], item))
    if records:
        await connection.executemany(
            """INSERT INTO document_effective_intervals
                 (snapshot_revision_id, document_id, valid_from, valid_to, effective_status,
                  verification_state, verification_source, verified_by, verified_at,
                  amendment_chain, notes)
               VALUES ($1, $2, $3, $4, $5, $6, $7,
                       $8::uuid, $9,
                       $10::jsonb, $11::jsonb)""",
            records,
        )
    node_rows = await _node_exception_records(connection, snapshot_id, node_relations)
    if node_rows:
        await connection.executemany(
            """INSERT INTO node_effective_intervals
                 (snapshot_revision_id, node_id, valid_from, valid_to, effective_status,
                  resolved_node_id, amendment_chain, verification_state, notes)
               VALUES ($1, $2, $3, $4, $5::effective_status, $2, $6::jsonb, $7, $8::jsonb)
               ON CONFLICT DO NOTHING""",
            node_rows,
        )
    await connection.execute(
        "UPDATE effectivity_snapshot_revisions SET is_active = FALSE WHERE is_active"
    )
    await connection.execute(
        """UPDATE effectivity_snapshot_revisions
           SET is_active = TRUE, published_at = now(), published_by = $2 WHERE id = $1""",
        snapshot_id, actor_id,
    )
    await connection.execute(
        """DELETE FROM effectivity_snapshot_revisions
           WHERE revision < $1 - 2 AND NOT is_active""",
        revision,
    )
    return {"revision": revision, "documents": len(documents), "intervals": len(records),
            "node_intervals": len(node_rows), "data_date": data_date.isoformat()}


def _relation(row: Any) -> Relation:
    return Relation(
        id=str(row["id"]), action=row["action"], valid_from=row["valid_from"],
        valid_to=row["valid_to"], approved=row["review_status"] == "approved",
        condition=row["condition_text"], source_label=row["source_label"] or "văn bản khác",
        reviewed_by=row["reviewer"],
        reviewed_at=row["reviewed_at"].isoformat() if row["reviewed_at"] else None,
    )


def _interval_record(snapshot_id: UUID, document_id: UUID, item: Interval) -> tuple[Any, ...]:
    return (
        snapshot_id, document_id,
        item.valid_from, item.valid_to, item.status, item.verification, item.verification_source,
        item.verified_by,
        datetime.fromisoformat(item.verified_at) if item.verified_at else None,
        json.dumps(list(item.chain)), json.dumps(list(item.notes), ensure_ascii=False),
    )


async def _node_exception_records(
    connection: Any, snapshot_id: UUID, node_relations: dict[UUID, list[Any]],
) -> list[tuple[Any, ...]]:
    """Approved node-level relations become exceptions for the node and its subtree."""

    from .node_paths import node_exception_intervals

    if not node_relations:
        return []
    # The G0 tree is parent_id; path prefixes carry a per-node ordinal, so the subtree
    # is walked through parent_id.
    subtree = await connection.fetch(
        """WITH RECURSIVE tree AS (
             SELECT id AS target, id AS node FROM document_nodes WHERE id = ANY($1::uuid[])
             UNION ALL
             SELECT tree.target, child.id FROM document_nodes child
             JOIN tree ON child.parent_id = tree.node)
           SELECT target, node FROM tree""",
        list(node_relations),
    )
    # A node gets the relations of its own target and of every ancestor target, and
    # one set of intervals is computed from all of them (later relations win).
    per_node: dict[UUID, list[Any]] = defaultdict(list)
    for row in subtree:
        per_node[row["node"]].extend(node_relations[row["target"]])
    rows: list[tuple[Any, ...]] = []
    for node, relation_rows in per_node.items():
        unique = list({row["id"]: row for row in relation_rows}.values())
        for interval in node_exception_intervals([_relation(row) for row in unique]):
            rows.append((
                snapshot_id, node, interval.valid_from, interval.valid_to, interval.status,
                json.dumps(list(interval.chain)), interval.verification,
                json.dumps(list(interval.notes), ensure_ascii=False),
            ))
    return rows


# ------------------------------------------------------------------ views
async def load_effectivity(
    connection: Any,
    *,
    document_ids: Sequence[UUID | str],
    node_ids: Sequence[UUID | str] = (),
    as_of: date,
) -> tuple[dict[str, EffectivityView], dict[str, EffectivityView], date | None]:
    """Document views, clause views (node exceptions or inherited) and the data date."""

    doc_list = list({UUID(str(item)) for item in document_ids})
    node_list = list({UUID(str(item)) for item in node_ids})
    snapshot = await connection.fetchrow(
        "SELECT id, data_date FROM effectivity_snapshot_revisions WHERE is_active LIMIT 1"
    )
    data_date = snapshot["data_date"] if snapshot else None
    documents: dict[str, EffectivityView] = {}
    if not doc_list:
        return documents, {}, data_date
    doc_rows = await connection.fetch(
        """SELECT dei.document_id, dei.effective_status, dei.verification_state,
                  dei.verification_source, u.display_name, dei.verified_at, dei.notes
           FROM document_effective_intervals dei
           LEFT JOIN users u ON u.id = dei.verified_by
           WHERE dei.snapshot_revision_id = $1 AND dei.document_id = ANY($2::uuid[])
             AND dei.valid_from <= $3 AND (dei.valid_to IS NULL OR dei.valid_to > $3)""",
        snapshot["id"] if snapshot else None, doc_list, as_of,
    ) if snapshot else []
    source_state = await connection.fetch(
        """SELECT target_document_id,
                  count(*) FILTER (WHERE available AND superseded_by IS NULL
                                    AND review_status IN ('draft', 'pending_review')) AS pending,
                  bool_or(NOT available AND review_status = 'approved') AS redact
           FROM (
               SELECT a.target_document_id, a.review_status, a.superseded_by,
                      (d.deleted_at IS NULL AND d.suspended_at IS NULL
                       AND v.review_status = 'approved' AND v.retired_at IS NULL
                       AND n.review_status = 'approved') AS available
               FROM node_amendments a
               JOIN document_nodes n ON n.id = a.source_node_id
               JOIN document_versions v ON v.id = n.document_version_id
               JOIN documents d ON d.id = n.document_id
               WHERE a.target_document_id = ANY($1::uuid[])
           ) sources GROUP BY target_document_id""",
        doc_list,
    )
    pending = {row["target_document_id"]: int(row["pending"]) for row in source_state}
    # A snapshot also carries free-text notes about future relations. Suppress the
    # notes when any related source is unavailable, while preserving legal status.
    redacted = {row["target_document_id"] for row in source_state if row["redact"]}
    reviewed = await clause_level_reviewed(connection, doc_list)
    for row in doc_rows:
        notes = ([NOTE_SOURCE_UNAVAILABLE] if row["document_id"] in redacted
                 else _json_list(row["notes"]))
        verification, extra = cap_verification(
            row["effective_status"], row["verification_state"], row["verification_source"],
            as_of=as_of, data_date=data_date,
        )
        documents[str(row["document_id"])] = EffectivityView(
            status=AmendmentStatus(row["effective_status"]),
            verification=VerificationState(verification), level="document", as_of_date=as_of,
            notes=[*notes, *extra], verification_source=row["verification_source"],
            verified_by=row["display_name"],
            verified_at=row["verified_at"].isoformat() if row["verified_at"] else None,
            pending_proposals=pending.get(row["document_id"], 0),
            clause_level_reviewed=reviewed.get(row["document_id"], False),
            data_date=data_date,
        )
    for document_id in doc_list:
        documents.setdefault(str(document_id), EffectivityView(
            as_of_date=as_of, data_date=data_date,
            notes=["Chưa có dữ liệu hiệu lực (snapshot chưa xuất bản)."],
            pending_proposals=pending.get(document_id, 0),
        ))
    nodes: dict[str, EffectivityView] = {}
    if node_list and snapshot:
        for row in await connection.fetch(
            """SELECT n.id, n.document_id, nei.effective_status::text AS status,
                      nei.verification_state, nei.notes
               FROM document_nodes n
               JOIN node_effective_intervals nei ON nei.node_id = n.id
                AND nei.snapshot_revision_id = $1
                AND nei.valid_from <= $3 AND (nei.valid_to IS NULL OR nei.valid_to > $3)
               WHERE n.id = ANY($2::uuid[])""",
            snapshot["id"], node_list, as_of,
        ):
            # Intervals of one node never overlap (node_exception_intervals).
            parent = documents.get(str(row["document_id"]))
            if parent is not None and parent.status.value in _TERMINAL:
                continue
            nodes[str(row["id"])] = EffectivityView(
                status=AmendmentStatus(row["status"]),
                verification=VerificationState(row["verification_state"]), level="node",
                as_of_date=as_of, notes=([NOTE_SOURCE_UNAVAILABLE]
                                         if row["document_id"] in redacted
                                         else _json_list(row["notes"])),
                pending_proposals=parent.pending_proposals if parent else 0,
                clause_level_reviewed=parent.clause_level_reviewed if parent else False,
                data_date=data_date,
            )
    return documents, nodes, data_date


def clause_view(
    document: EffectivityView | None, node: EffectivityView | None
) -> EffectivityView | None:
    """A clause inherits its document's axes unless a node exception exists."""

    if node is not None:
        return node
    if document is None:
        return None
    if document.status == AmendmentStatus.MODIFIED and not document.clause_level_reviewed:
        return document.model_copy(update={"notes": [*document.notes, NOTE_PARTIAL_UNMAPPED]})
    return document


async def clause_level_reviewed(connection: Any, document_ids: Sequence[UUID]) -> dict[UUID, bool]:
    """Computed, never confirmed by hand (design §4): every known relation that targets
    the document is approved and, when it changes only part of it, mapped to nodes."""

    rows = await connection.fetch(
        """SELECT d.id,
                  NOT EXISTS (
                    SELECT 1 FROM node_amendments a
                    WHERE a.target_document_id = d.id AND a.superseded_by IS NULL
                      AND (a.review_status IN ('draft', 'pending_review')
                           OR (a.scope = 'node' AND a.target_node_id IS NULL
                               AND a.review_status <> 'rejected'))
                  ) AND NOT EXISTS (
                    SELECT 1 FROM node_amendments a
                    WHERE a.target_document_id = d.id AND a.superseded_by IS NULL
                      AND a.scope = 'document' AND a.review_status = 'approved'
                      AND a.action IN ('modify', 'add', 'repeal_partial')
                      AND NOT EXISTS (
                        SELECT 1 FROM node_amendments b
                        WHERE b.source_document_id = a.source_document_id
                          AND b.target_document_id = d.id AND b.scope = 'node'
                          AND b.review_status = 'approved' AND b.superseded_by IS NULL
                          AND b.target_node_id IS NOT NULL)
                  ) AS reviewed
           FROM documents d WHERE d.id = ANY($1::uuid[])""",
        list(document_ids),
    )
    return {row["id"]: bool(row["reviewed"]) for row in rows}


def _json_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = json.loads(value)
    return [str(item) for item in (value or []) if item]
