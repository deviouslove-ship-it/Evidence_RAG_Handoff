"""Single-worker background processor for Phase 2 cross-document conflict scans."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections import defaultdict
from collections.abc import Sequence
from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from ..analysis.signals import NodeRecord
from ..audit import append_audit
from ..auth_acl.policy import Permission, Principal
from ..config import Settings
from ..documents.ocr_ai_jobs import _load_live_principal
from ..effectivity.store import load_effectivity
from ..schemas import AmendmentStatus
from .ai_screen import is_relation_stage_ready, screen_conflict_finding
from .detector import (
    ApprovedNodeAmendment,
    ApprovedNodeReference,
    DocumentNodesInput,
    classify_candidate_pair,
    fetch_pgvector_candidate_similarities,
    filter_normative_nodes,
    generate_candidate_pairs,
)
from .precedence import (
    REFERENCE_NOTICE,
    AmendmentBetweenPair,
    AuthorityRule,
    DocumentAuthorityMeta,
    evaluate_precedence,
)
from .store import (
    CONFLICT_CLAIM_LOCK_KEY,
    CONFLICT_WORKER_LOCK_KEY,
    expire_conflict_runs,
    load_authority_rule_objects,
    resolve_scoped_document_ids,
)

_LOG = logging.getLogger(__name__)
_PROGRESS_BATCH_SIZE = 5


def _decode_json(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


def _clamp_score(value: float | None, *, digits: int) -> float | None:
    if value is None:
        return None
    clamped = max(0.0, min(1.0, float(value)))
    return round(clamped, digits)


class ConflictScanWorker:
    """Runs queued conflict review scans serially with lease & cancellation checks."""

    def __init__(
        self,
        pool: Any,
        runtime: Any,
        *,
        settings: Settings | None = None,
        poll_seconds: float = 1.0,
        lease_seconds: int = 300,
        job_timeout_seconds: float = 290.0,
        backoff_seconds: Sequence[float] = (0.5, 1.0, 2.0),
    ) -> None:
        self.pool = pool
        self.runtime = runtime
        self.settings = settings
        self.poll_seconds = poll_seconds
        self.lease_seconds = lease_seconds
        self.job_timeout_seconds = min(job_timeout_seconds, max(1.0, lease_seconds - 1.0))
        self.backoff_seconds = tuple(backoff_seconds)
        self._task: asyncio.Task[None] | None = None
        self._wake = asyncio.Event()
        self._stopping = False
        self.worker_id = uuid4().hex
        self.current_run_id: str | None = None
        self.last_error: str | None = None
        self.last_poll_at: datetime | None = None

    def start(self) -> None:
        if self._task is None:
            self._stopping = False
            self._task = asyncio.create_task(self._run(), name="conflict-scan-worker")

    async def stop(self, timeout: float = 10.0) -> None:
        self._stopping = True
        self._wake.set()
        task, self._task = self._task, None
        if task is None:
            return
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout)
        except (TimeoutError, asyncio.CancelledError):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        except Exception:
            _LOG.exception("Conflict scan worker failed during shutdown")

    def wake(self) -> None:
        self._wake.set()

    async def recover_interrupted_runs(self) -> int:
        """Mark leftover ``running`` runs as failed without re-queuing after restart."""
        async with self.pool.acquire() as owner:
            if not await owner.fetchval(
                "SELECT pg_try_advisory_lock($1)", CONFLICT_WORKER_LOCK_KEY
            ):
                return 0
            try:
                return await self._recover_orphans()
            finally:
                await owner.execute("SELECT pg_advisory_unlock($1)", CONFLICT_WORKER_LOCK_KEY)

    async def _recover_orphans(self) -> int:
        async with self.pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock($1)", CONFLICT_CLAIM_LOCK_KEY)
            await expire_conflict_runs(conn)
            rows = await conn.fetch(
                """UPDATE conflict_review_runs
                   SET status = 'failed',
                       error_code = 'CONFLICT_SCAN_INTERRUPTED',
                       error_message = 'Tiến trình quét mâu thuẫn bị gián đoạn trước khi hoàn tất.',
                       lease_token = NULL,
                       lease_expires_at = NULL,
                       completed_at = COALESCE(completed_at, now())
                   WHERE status = 'running'
                   RETURNING id"""
            )
            return len(rows)

    async def _run(self) -> None:
        with contextlib.suppress(Exception):
            await self.recover_interrupted_runs()
        backoff_index = 0
        while not self._stopping:
            self._wake.clear()
            try:
                worked = await self.run_once()
                backoff_index = 0
                if worked:
                    continue
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_error = str(exc)
                _LOG.exception("Conflict scan worker iteration failed")
                delay = self.backoff_seconds[
                    min(backoff_index, len(self.backoff_seconds) - 1)
                ]
                backoff_index += 1
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._wake.wait(), timeout=delay)
                continue
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), timeout=self.poll_seconds)

    async def _claim_next_run(self) -> dict[str, Any] | None:
        lease_token = uuid4()
        async with self.pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock($1)", CONFLICT_CLAIM_LOCK_KEY)
            await expire_conflict_runs(conn)
            await conn.execute(
                """UPDATE conflict_review_runs
                   SET status = 'failed',
                       error_code = 'CONFLICT_SCAN_INTERRUPTED',
                       error_message = 'Quá thời hạn giữ lượt xử lý của tiến trình quét.',
                       lease_token = NULL,
                       lease_expires_at = NULL,
                       completed_at = COALESCE(completed_at, now())
                   WHERE status = 'running'
                     AND lease_expires_at IS NOT NULL
                     AND lease_expires_at <= now()"""
            )
            # Respect partial unique index conflict_review_runs_one_running.
            active_running = await conn.fetchval(
                "SELECT count(*) FROM conflict_review_runs WHERE status = 'running'"
            )
            if int(active_running or 0) > 0:
                return None
            row = await conn.fetchrow(
                """WITH next_run AS (
                     SELECT id FROM conflict_review_runs
                     WHERE status = 'queued'
                       AND (expires_at IS NULL OR expires_at > now())
                     ORDER BY created_at ASC, id ASC
                     FOR UPDATE SKIP LOCKED
                     LIMIT 1
                   )
                   UPDATE conflict_review_runs r
                   SET status = 'running',
                       lease_token = $1,
                       lease_expires_at = now() + make_interval(secs => $2),
                       started_at = COALESCE(started_at, now())
                   FROM next_run
                   WHERE r.id = next_run.id
                   RETURNING r.*""",
                lease_token,
                float(self.lease_seconds),
            )
            return dict(row) if row is not None else None

    async def _finish_terminal(
        self,
        run: dict[str, Any],
        *,
        status: str,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        async with self.pool.acquire() as conn, conn.transaction():
            await conn.execute(
                """UPDATE conflict_review_runs
                   SET status = $3,
                       error_code = $4,
                       error_message = $5,
                       lease_token = NULL,
                       lease_expires_at = NULL,
                       completed_at = COALESCE(completed_at, now())
                   WHERE id = $1 AND status = 'running' AND lease_token = $2""",
                run["id"],
                run["lease_token"],
                status,
                error_code,
                error_message,
            )

    async def _check_live_state_in_tx(
        self,
        conn: Any,
        run: dict[str, Any],
        *,
        progress_done: int | None = None,
        progress_total: int | None = None,
    ) -> tuple[str, Principal | None]:
        live = await conn.fetchrow(
            """SELECT *, (expires_at IS NOT NULL AND expires_at <= now()) AS expired
               FROM conflict_review_runs
               WHERE id = $1 FOR UPDATE""",
            run["id"],
        )
        if (
            live is None
            or live["status"] != "running"
            or live["lease_token"] != run["lease_token"]
        ):
            return "abort", None
        if live["expired"]:
            await conn.execute(
                """UPDATE conflict_review_runs
                   SET status = 'expired',
                       error_code = 'CONFLICT_SCAN_EXPIRED',
                       lease_token = NULL,
                       lease_expires_at = NULL,
                       completed_at = COALESCE(completed_at, now())
                   WHERE id = $1""",
                run["id"],
            )
            return "expired", None

        principal = await _load_live_principal(conn, run["requested_by"])
        if principal is None or not principal.has(Permission.QUERY):
            await conn.execute(
                """UPDATE conflict_review_runs
                   SET status = 'failed',
                       error_code = 'CONFLICT_SCAN_ACCESS_REVOKED',
                       error_message = 'Tài khoản đã bị khóa hoặc mất quyền tra cứu.',
                       lease_token = NULL,
                       lease_expires_at = NULL,
                       completed_at = COALESCE(completed_at, now())
                   WHERE id = $1""",
                run["id"],
            )
            return "revoked", None

        await conn.execute(
            """UPDATE conflict_review_runs
               SET lease_expires_at = now() + make_interval(secs => $2),
                   progress_done = COALESCE($3, progress_done),
                   progress_total = COALESCE($4, progress_total)
               WHERE id = $1""",
            run["id"],
            float(self.lease_seconds),
            progress_done,
            progress_total,
        )
        return "ok", principal

    async def _checkpoint(
        self,
        run: dict[str, Any],
        *,
        progress_done: int | None = None,
        progress_total: int | None = None,
    ) -> tuple[str, Principal | None]:
        async with self.pool.acquire() as conn, conn.transaction():
            return await self._check_live_state_in_tx(
                conn,
                run,
                progress_done=progress_done,
                progress_total=progress_total,
            )

    async def run_once(self) -> bool:
        """Claim and execute at most one queued conflict scan run."""
        async with self.pool.acquire() as owner:
            if not await owner.fetchval(
                "SELECT pg_try_advisory_lock($1)", CONFLICT_WORKER_LOCK_KEY
            ):
                return False
            try:
                return await self._run_locked_once()
            finally:
                await owner.execute("SELECT pg_advisory_unlock($1)", CONFLICT_WORKER_LOCK_KEY)

    async def _run_locked_once(self) -> bool:
        run = await self._claim_next_run()
        if run is None:
            return False
        self.current_run_id = str(run["id"])
        try:
            async with asyncio.timeout(self.job_timeout_seconds):
                return await self._execute_run(run)
        except TimeoutError:
            await self._finish_terminal(
                run,
                status="failed",
                error_code="CONFLICT_SCAN_TIMEOUT",
                error_message="Quá thời gian xử lý lượt rà soát mâu thuẫn.",
            )
            return True
        except asyncio.CancelledError:
            await self._finish_terminal(
                run,
                status="failed",
                error_code="CONFLICT_SCAN_INTERRUPTED",
                error_message="Tiến trình rà soát mâu thuẫn đã dừng.",
            )
            raise
        except Exception:
            await self._finish_terminal(
                run,
                status="failed",
                error_code="CONFLICT_SCAN_FAILED",
                error_message="Lỗi xử lý nội bộ khi quét mâu thuẫn.",
            )
            raise
        finally:
            self.current_run_id = None

    def _run_limits(self, run: dict[str, Any]) -> tuple[int, int, int, float]:
        limits = _decode_json(run["limits_json"]) or {}
        default_docs = self.settings.conflict_scan_max_documents if self.settings else 20
        default_pairs = self.settings.conflict_scan_max_pairs if self.settings else 120
        default_ai = self.settings.conflict_scan_max_ai_pairs if self.settings else 25
        default_timeout = (
            self.settings.conflict_scan_ai_timeout_seconds if self.settings else 25.0
        )
        max_docs = int(limits.get("max_documents") or default_docs)
        max_pairs = int(limits.get("max_pairs") or default_pairs)
        max_ai_pairs = int(limits.get("max_ai_pairs") or default_ai)
        ai_timeout = float(limits.get("ai_timeout_seconds") or default_timeout)
        return max_docs, max_pairs, max_ai_pairs, ai_timeout

    async def _load_scan_inputs(
        self,
        conn: Any,
        principal: Principal,
        *,
        scope: dict[str, Any],
        as_of_date: date,
        max_documents: int,
    ) -> dict[str, Any]:
        req_docs = [UUID(str(x)) for x in scope.get("document_ids") or ()]
        req_cats = [UUID(str(x)) for x in scope.get("category_ids") or ()]
        resolved_before = [UUID(str(x)) for x in scope.get("resolved_document_ids") or ()]

        if req_docs or req_cats:
            live_doc_ids = await resolve_scoped_document_ids(
                conn,
                principal,
                document_ids=req_docs,
                category_ids=req_cats,
                limit=max_documents,
            )
        else:
            live_doc_ids = await resolve_scoped_document_ids(
                conn,
                principal,
                document_ids=resolved_before,
                limit=max_documents,
            )

        dropped_by_acl = max(0, len(set(resolved_before) - set(live_doc_ids)))
        if len(live_doc_ids) < 2:
            return {
                "live_doc_ids": live_doc_ids,
                "dropped_by_acl": dropped_by_acl,
                "doc_inputs": [],
                "doc_meta_map": {},
                "vector_sims": {},
                "approved_amendments": [],
                "pair_amendments": defaultdict(list),
                "approved_refs": [],
                "rules": [],
            }

        # Enforce approved + verified-provenance version on every scoped document.
        doc_rows = await conn.fetch(
            """SELECT d.id, d.doc_type, d.title, d.document_number, d.issuing_body,
                      dv.id AS version_id, dv.publication_date, dv.effective_from
               FROM documents d
               JOIN LATERAL (
                   SELECT v.id, v.publication_date, v.effective_from
                   FROM document_versions v
                   JOIN source_provenance sp ON sp.document_version_id = v.id
                   WHERE v.document_id = d.id
                     AND v.review_status = 'approved'
                     AND v.retired_at IS NULL
                     AND sp.verified_at IS NOT NULL
                   ORDER BY v.version_number DESC
                   LIMIT 1
               ) dv ON TRUE
               WHERE d.id = ANY($1::uuid[])
                 AND d.deleted_at IS NULL
                 AND d.suspended_at IS NULL
               ORDER BY d.id ASC""",
            live_doc_ids,
        )
        valid_doc_ids = [row["id"] for row in doc_rows]
        valid_version_ids = [row["version_id"] for row in doc_rows]
        dropped_by_acl += max(0, len(live_doc_ids) - len(valid_doc_ids))
        if len(valid_doc_ids) < 2:
            return {
                "live_doc_ids": valid_doc_ids,
                "dropped_by_acl": dropped_by_acl,
                "doc_inputs": [],
                "doc_meta_map": {},
                "vector_sims": {},
                "approved_amendments": [],
                "pair_amendments": defaultdict(list),
                "approved_refs": [],
                "rules": [],
            }

        eff_docs, _, _ = await load_effectivity(
            conn, document_ids=valid_doc_ids, node_ids=[], as_of=as_of_date
        )

        node_rows = await conn.fetch(
            """SELECT n.id, n.document_id, n.node_type, n.path, n.text_original,
                      n.citation_label, n.label_original, n.page_start, n.page_end
               FROM document_nodes n
               WHERE n.document_version_id = ANY($1::uuid[])
                 AND n.review_status = 'approved'
                 AND node_source_text_valid(n.id)
               ORDER BY n.document_id ASC, n.path ASC, n.id ASC""",
            valid_version_ids,
        )
        all_node_ids = [row["id"] for row in node_rows]
        taxonomies: dict[UUID, tuple[str, ...]] = {}
        if all_node_ids:
            label_rows = await conn.fetch(
                """SELECT nl.node_id, t.code
                   FROM node_labels nl
                   JOIN content_taxonomy t ON t.id = nl.taxonomy_id
                   WHERE nl.node_id = ANY($1::uuid[])
                     AND nl.status IN ('auto', 'approved')
                     AND t.active
                   ORDER BY t.sort_order, t.code""",
                all_node_ids,
            )
            for lrow in label_rows:
                nid = lrow["node_id"]
                taxonomies[nid] = (*taxonomies.get(nid, ()), lrow["code"])

        records_by_doc: dict[UUID, list[NodeRecord]] = defaultdict(list)
        for nrow in node_rows:
            records_by_doc[nrow["document_id"]].append(
                NodeRecord(
                    node_id=nrow["id"],
                    node_type=nrow["node_type"],
                    path=nrow["path"],
                    text_original=nrow["text_original"],
                    citation_label=nrow["citation_label"],
                    label_original=nrow["label_original"],
                    page_start=nrow["page_start"],
                    page_end=nrow["page_end"],
                    taxonomy_codes=taxonomies.get(nrow["id"], ()),
                )
            )

        doc_inputs: list[DocumentNodesInput] = []
        doc_meta_map: dict[UUID, DocumentAuthorityMeta] = {}
        for drow in doc_rows:
            doc_id = drow["id"]
            eff_view = eff_docs.get(str(doc_id))
            eff_status = eff_view.status if eff_view is not None else AmendmentStatus.UNKNOWN
            doc_meta_map[doc_id] = DocumentAuthorityMeta(
                document_id=str(doc_id),
                doc_type=drow["doc_type"],
                issuing_body=drow["issuing_body"],
                document_number=drow["document_number"],
                effective_from=drow["effective_from"],
                publication_date=drow["publication_date"],
                effective_status_at_date=eff_status,
            )
            doc_inputs.append(
                DocumentNodesInput(
                    document_id=doc_id,
                    records=records_by_doc.get(doc_id, []),
                    effective_status_at_date=eff_status,
                    document_number=drow["document_number"],
                )
            )

        # Ruling P7: read stored pgvector similarities only; never call embedding model.
        include_expired = bool(scope.get("include_expired", False))
        scoped_nodes = filter_normative_nodes(doc_inputs, include_expired=include_expired)
        scoped_node_ids = [sn.node.primary_node_id for sn in scoped_nodes]
        vector_sims = await fetch_pgvector_candidate_similarities(conn, scoped_node_ids)

        amend_rows = await conn.fetch(
            """SELECT a.id, a.source_document_id, a.target_document_id, a.source_node_id,
                      a.target_node_id, a.target_path, a.action, a.valid_from, a.source_quote
               FROM node_amendments a
               JOIN document_nodes sn ON sn.id = a.source_node_id
               JOIN document_versions sv ON sv.id = sn.document_version_id
               WHERE a.review_status = 'approved'
                 AND a.superseded_by IS NULL
                 AND sv.review_status = 'approved'
                 AND sv.retired_at IS NULL
                 AND a.source_document_id = ANY($1::uuid[])
                 AND a.target_document_id = ANY($1::uuid[])""",
            valid_doc_ids,
        )
        approved_amendments: list[ApprovedNodeAmendment] = []
        pair_amendments: dict[tuple[UUID, UUID], list[AmendmentBetweenPair]] = defaultdict(list)
        for arow in amend_rows:
            src_doc = arow["source_document_id"]
            tgt_doc = arow["target_document_id"]
            approved_amendments.append(
                ApprovedNodeAmendment(
                    source_document_id=src_doc,
                    target_document_id=tgt_doc,
                    source_node_id=arow["source_node_id"],
                    target_node_id=arow["target_node_id"],
                    target_path=arow["target_path"],
                    action=arow["action"],
                    amendment_id=arow["id"],
                    valid_from=arow["valid_from"],
                    approved=True,
                )
            )
            if src_doc is not None and tgt_doc is not None:
                pair_key = (min(src_doc, tgt_doc), max(src_doc, tgt_doc))
                pair_amendments[pair_key].append(
                    AmendmentBetweenPair(
                        source_document_id=str(src_doc),
                        target_document_id=str(tgt_doc),
                        action=arow["action"],
                        amendment_id=str(arow["id"]),
                        effective_from=arow["valid_from"],
                        description=arow["source_quote"],
                        approved=True,
                    )
                )

        # node_references has NO review_status column; check verified_at / resolution_state.
        ref_rows = (
            await conn.fetch(
                """SELECT r.source_node_id, r.target_node_id, r.target_document_id,
                          r.target_expression, r.resolution_state, r.verified_at
                   FROM node_references r
                   WHERE r.source_node_id = ANY($1::uuid[])
                     AND (r.verified_at IS NOT NULL OR r.resolution_state = 'resolved')""",
                all_node_ids,
            )
            if all_node_ids
            else []
        )
        approved_refs = [
            ApprovedNodeReference(
                source_node_id=rrow["source_node_id"],
                target_node_id=rrow["target_node_id"],
                target_document_id=rrow["target_document_id"],
                target_expression=rrow["target_expression"],
                verified=(
                    rrow["verified_at"] is not None
                    or rrow["resolution_state"] == "resolved"
                ),
            )
            for rrow in ref_rows
        ]
        rules: list[AuthorityRule] = await load_authority_rule_objects(conn)

        return {
            "live_doc_ids": valid_doc_ids,
            "dropped_by_acl": dropped_by_acl,
            "scoped_nodes": scoped_nodes,
            "doc_meta_map": doc_meta_map,
            "vector_sims": vector_sims,
            "approved_amendments": approved_amendments,
            "pair_amendments": pair_amendments,
            "approved_refs": approved_refs,
            "rules": rules,
        }

    async def _execute_run(self, run: dict[str, Any]) -> bool:
        state, principal = await self._checkpoint(run)
        if state != "ok" or principal is None:
            return True

        scope = _decode_json(run["scope_json"]) or {}
        as_of_date = run["as_of_date"]
        if isinstance(as_of_date, str):
            as_of_date = date.fromisoformat(as_of_date)
        max_docs, max_pairs, max_ai_pairs, ai_timeout = self._run_limits(run)

        async with self.pool.acquire() as conn, conn.transaction():
            inputs = await self._load_scan_inputs(
                conn,
                principal,
                scope=scope,
                as_of_date=as_of_date,
                max_documents=max_docs,
            )

        if len(inputs["live_doc_ids"]) < 2:
            summary = self._build_summary(
                total_documents=len(inputs["live_doc_ids"]),
                total_nodes=0,
                pairs_evaluated=0,
                findings=[],
                ai_calls_used=0,
                ai_verified=0,
                ai_filtered=0,
                ai_fallbacks=0,
                dropped_by_acl=inputs["dropped_by_acl"],
            )
            await self._commit_completion(run, progress_total=0, findings=[], summary=summary)
            return True

        scoped_nodes = inputs["scoped_nodes"]
        pairs = generate_candidate_pairs(
            scoped_nodes,
            vector_similarities=inputs["vector_sims"],
            max_pairs=max_pairs,
        )

        state, _ = await self._checkpoint(
            run, progress_done=0, progress_total=len(pairs)
        )
        if state != "ok":
            return True

        ai_active = (
            bool(run["use_ai"])
            and max_ai_pairs > 0
            and await is_relation_stage_ready(self.runtime)
        )
        principal_uuid = UUID(principal.id)
        findings_to_insert: list[dict[str, Any]] = []
        ai_calls_used = 0
        ai_verified_count = 0
        ai_filtered_count = 0
        ai_fallback_count = 0

        for idx, pair in enumerate(pairs):
            candidate = classify_candidate_pair(
                pair,
                approved_amendments=inputs["approved_amendments"],
                approved_references=inputs["approved_refs"],
            )
            if candidate is not None:
                pair_doc_key = (
                    min(candidate.document_a_id, candidate.document_b_id),
                    max(candidate.document_a_id, candidate.document_b_id),
                )
                assessment = evaluate_precedence(
                    inputs["doc_meta_map"][candidate.document_a_id],
                    inputs["doc_meta_map"][candidate.document_b_id],
                    inputs["rules"],
                    inputs["pair_amendments"].get(pair_doc_key, ()),
                    as_of_date=as_of_date,
                )

                signals_json = dict(candidate.signals_json)
                detection_method = "rule"
                ai_confidence: float | None = None
                ai_verified: bool | None = None
                dropped = False

                if ai_active and ai_calls_used < max_ai_pairs:
                    ai_calls_used += 1
                    screen = await screen_conflict_finding(
                        candidate,
                        pair.node_a,
                        pair.node_b,
                        runtime=self.runtime,
                        pool=self.pool,
                        principal_id=principal_uuid,
                        timeout_seconds=ai_timeout,
                        relation_ready=True,
                    )
                    if screen.dropped:
                        dropped = True
                        ai_filtered_count += 1
                    elif screen.detection_method == "rule_plus_ai":
                        detection_method = "rule_plus_ai"
                        ai_confidence = _clamp_score(screen.ai_confidence, digits=3)
                        ai_verified = screen.ai_verified
                        signals_json["ai_screen"] = {
                            "classification": screen.ai_classification,
                            "confidence": ai_confidence,
                            "summary_vi": screen.ai_summary_vi,
                            "quote_a": screen.quote_a,
                            "quote_b": screen.quote_b,
                            "external_api_used": screen.external_api_used,
                        }
                        if ai_verified:
                            ai_verified_count += 1
                    elif screen.fallback_reason is not None:
                        ai_fallback_count += 1
                        signals_json["ai_fallback_reason"] = screen.fallback_reason

                if not dropped:
                    findings_to_insert.append(
                        {
                            "document_a_id": candidate.document_a_id,
                            "document_b_id": candidate.document_b_id,
                            "node_a_id": candidate.node_a_id,
                            "node_b_id": candidate.node_b_id,
                            "finding_type": candidate.finding_type,
                            "severity": candidate.severity,
                            "detection_method": detection_method,
                            "similarity_score": _clamp_score(
                                candidate.similarity_score, digits=4
                            ),
                            "shared_labels": list(candidate.shared_labels),
                            "signals_json": signals_json,
                            "precedence_result": assessment.precedence_result,
                            "precedence_basis_json": assessment.to_basis_json(),
                            "explanation": candidate.explanation,
                            "ai_confidence": ai_confidence,
                            "ai_verified": ai_verified,
                        }
                    )

            if (idx + 1) % _PROGRESS_BATCH_SIZE == 0 or (idx + 1) == len(pairs):
                state, _ = await self._checkpoint(run, progress_done=idx + 1)
                if state != "ok":
                    return True

        summary = self._build_summary(
            total_documents=len(inputs["live_doc_ids"]),
            total_nodes=len(scoped_nodes),
            pairs_evaluated=len(pairs),
            findings=findings_to_insert,
            ai_calls_used=ai_calls_used,
            ai_verified=ai_verified_count,
            ai_filtered=ai_filtered_count,
            ai_fallbacks=ai_fallback_count,
            dropped_by_acl=inputs["dropped_by_acl"],
        )
        await self._commit_completion(
            run,
            progress_total=len(pairs),
            findings=findings_to_insert,
            summary=summary,
        )
        return True

    def _build_summary(
        self,
        *,
        total_documents: int,
        total_nodes: int,
        pairs_evaluated: int,
        findings: Sequence[dict[str, Any]],
        ai_calls_used: int,
        ai_verified: int,
        ai_filtered: int,
        ai_fallbacks: int,
        dropped_by_acl: int,
    ) -> dict[str, Any]:
        return {
            "total_documents": total_documents,
            "total_normative_nodes": total_nodes,
            "candidate_pairs_evaluated": pairs_evaluated,
            "total_findings": len(findings),
            "by_severity": {
                "high": sum(1 for item in findings if item["severity"] == "high"),
                "medium": sum(1 for item in findings if item["severity"] == "medium"),
                "low": sum(1 for item in findings if item["severity"] == "low"),
            },
            "by_type": {
                "contradiction": sum(
                    1 for item in findings if item["finding_type"] == "contradiction"
                ),
                "overlap": sum(1 for item in findings if item["finding_type"] == "overlap"),
                "exception_refinement": sum(
                    1
                    for item in findings
                    if item["finding_type"] == "exception_refinement"
                ),
                "superseded_already": sum(
                    1 for item in findings if item["finding_type"] == "superseded_already"
                ),
            },
            "ai_used": ai_calls_used > 0,
            "ai_pairs_screened": ai_calls_used,
            "ai_verified": ai_verified,
            "ai_filtered": ai_filtered,
            "ai_fallbacks": ai_fallbacks,
            "dropped_documents_by_acl": dropped_by_acl,
            "disclaimer": REFERENCE_NOTICE,
        }

    async def _commit_completion(
        self,
        run: dict[str, Any],
        *,
        progress_total: int,
        findings: Sequence[dict[str, Any]],
        summary: dict[str, Any],
    ) -> None:
        async with self.pool.acquire() as conn, conn.transaction():
            state, principal = await self._check_live_state_in_tx(
                conn,
                run,
                progress_done=progress_total,
                progress_total=progress_total,
            )
            if state != "ok" or principal is None:
                return
            for item in findings:
                await conn.execute(
                    """INSERT INTO conflict_findings (
                         run_id, document_a_id, document_b_id, node_a_id, node_b_id,
                         finding_type, severity, detection_method, similarity_score,
                         shared_labels, signals_json, precedence_result,
                         precedence_basis_json, explanation, ai_confidence, ai_verified
                       )
                       VALUES (
                         $1, $2, $3, $4, $5,
                         $6, $7, $8, $9,
                         $10, $11::jsonb, $12,
                         $13::jsonb, $14, $15, $16
                       )""",
                    run["id"],
                    item["document_a_id"],
                    item["document_b_id"],
                    item["node_a_id"],
                    item["node_b_id"],
                    item["finding_type"],
                    item["severity"],
                    item["detection_method"],
                    item["similarity_score"],
                    item["shared_labels"],
                    json.dumps(item["signals_json"], ensure_ascii=False),
                    item["precedence_result"],
                    json.dumps(item["precedence_basis_json"], ensure_ascii=False),
                    item["explanation"],
                    item["ai_confidence"],
                    item["ai_verified"],
                )
            await conn.execute(
                """UPDATE conflict_review_runs
                   SET status = 'completed',
                       progress_total = $2,
                       progress_done = $2,
                       summary_json = $3::jsonb,
                       lease_token = NULL,
                       lease_expires_at = NULL,
                       completed_at = now()
                   WHERE id = $1""",
                run["id"],
                progress_total,
                json.dumps(summary, ensure_ascii=False),
            )
            await append_audit(
                conn,
                principal_id=UUID(principal.id),
                action="conflict_scan.complete",
                target_type="conflict_review_run",
                target_id=str(run["id"]),
                metadata={
                    "total_findings": len(findings),
                    "candidate_pairs_evaluated": progress_total,
                    "ai_pairs_screened": summary["ai_pairs_screened"],
                },
            )
