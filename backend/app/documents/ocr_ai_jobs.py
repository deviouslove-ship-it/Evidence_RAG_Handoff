"""Single-worker background processor for bounded local OCR AI proposals."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import shutil
from collections.abc import Awaitable, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any, TypeVar
from uuid import uuid4

from ..auth_acl.policy import Permission, Principal, normalize_roles
from ..documents.isolated import render_page_isolated
from ..documents.management_read import _record
from ..documents.ocr_ai import (
    DEFAULT_RENDER_DPI,
    DEFAULT_RENDER_MAX_BYTES,
    DEFAULT_RENDER_MAX_EDGE,
    OCR_AI_PROMPT,
    OCR_PAGE_CANDIDATE_SCHEMA,
    parse_ocr_candidate,
)
from ..documents.ocr_ai_store import expire_user_tasks, page_text_sha256
from ..documents.provenance import read_immutable_pdf
from ..documents.review import ReviewError

_LOG = logging.getLogger(__name__)
_JOB_CLAIM_LOCK_KEY = 7_302_026_102
_WORKER_LOCK_KEY = 7_302_026_103
_DEFAULT_MAX_PDF_BYTES = 32 * 1024 * 1024
_Result = TypeVar("_Result")


def cleanup_orphan_temp_dirs(temporary_root: Path | None) -> int:
    """Remove leftover isolated page-render directories after an unclean exit."""
    if temporary_root is None or not temporary_root.is_dir():
        return 0
    removed = 0
    for child in temporary_root.iterdir():
        if child.is_dir() and child.name.startswith("ocr-ai-render-"):
            shutil.rmtree(child, ignore_errors=True)
            removed += 1
    return removed


async def _load_live_principal(conn: Any, user_id: Any) -> Principal | None:
    user = await conn.fetchrow(
        "SELECT id, disabled_at FROM users WHERE id = $1",
        user_id,
    )
    if user is None or user["disabled_at"] is not None:
        return None
    role_rows = await conn.fetch(
        "SELECT role_code FROM user_roles WHERE user_id = $1",
        user_id,
    )
    roles = normalize_roles(row["role_code"] for row in role_rows)
    return Principal(id=str(user["id"]), roles=roles)


async def _user_can_access_approved_version(
    conn: Any,
    principal: Principal,
    *,
    document_id: Any,
    version_id: Any,
) -> Any:
    if not principal.has(Permission.QUERY):
        return None
    user_uuid = principal.id
    await conn.execute("SELECT set_config('app.user_id', $1, true)", user_uuid)
    return await conn.fetchrow(
        """SELECT dv.id, dv.source_review_revision, dv.original_file_path,
                  dv.original_file_sha256, dv.source_format
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
             AND (
               EXISTS (
                 SELECT 1 FROM document_categories dc
                 JOIN authorized_categories ac ON ac.category_id = dc.category_id
                 WHERE dc.document_id = d.id AND ac.user_id = $3::uuid
               )
               OR EXISTS (
                 SELECT 1 FROM document_acl da
                 JOIN users u ON u.id = da.user_id AND u.disabled_at IS NULL
                 WHERE da.document_id = d.id AND da.user_id = $3::uuid AND da.can_query
               )
             )""",
        version_id,
        document_id,
        user_uuid,
    )


class OcrAiWorker:
    """Runs queued single-page OCR AI tasks serially with no automatic retries."""

    def __init__(
        self,
        pool: Any,
        runtime: Any,
        *,
        store_root: Path | None = None,
        poll_seconds: float = 1.0,
        lease_seconds: int = 390,
        job_timeout_seconds: float = 360.0,
        max_pdf_bytes: int = _DEFAULT_MAX_PDF_BYTES,
        backoff_seconds: Sequence[float] = (0.5, 1.0, 2.0),
    ) -> None:
        self.pool = pool
        self.runtime = runtime
        self.store_root = store_root
        self.poll_seconds = poll_seconds
        self.lease_seconds = lease_seconds
        self.job_timeout_seconds = min(job_timeout_seconds, max(1.0, lease_seconds - 1.0))
        self.max_pdf_bytes = max_pdf_bytes
        self.backoff_seconds = tuple(backoff_seconds)
        self._task: asyncio.Task[None] | None = None
        self._wake = asyncio.Event()
        self._stopping = False
        self.worker_id = uuid4().hex
        self.current_proposal_id: str | None = None
        self.last_error: str | None = None
        self.last_poll_at: datetime | None = None

    def start(self) -> None:
        if self._task is None:
            self._stopping = False
            self._task = asyncio.create_task(self._run(), name="ocr-ai-worker")

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
            _LOG.exception("OCR AI worker failed during shutdown")

    def wake(self) -> None:
        self._wake.set()

    async def recover_interrupted_jobs(self) -> int:
        """Mark leftover ``running`` jobs as failed without re-queuing after restart."""
        # A live worker owns this session lock until inference has actually stopped.
        # A second API process must not treat that worker's jobs/temp files as orphans.
        async with self.pool.acquire() as owner:
            if not await owner.fetchval("SELECT pg_try_advisory_lock($1)", _WORKER_LOCK_KEY):
                return 0
            try:
                cleanup_orphan_temp_dirs(self.store_root)
                return await self._recover_orphans()
            finally:
                await owner.execute("SELECT pg_advisory_unlock($1)", _WORKER_LOCK_KEY)

    async def _recover_orphans(self) -> int:
        async with self.pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock($1)", _JOB_CLAIM_LOCK_KEY)
            await expire_user_tasks(conn)
            rows = await conn.fetch(
                """UPDATE document_ocr_ai_proposals
                   SET status = 'failed',
                       error_code = 'OCR_AI_INTERRUPTED',
                       lease_token = NULL,
                       lease_expires_at = NULL,
                       finished_at = COALESCE(finished_at, now())
                   WHERE status = 'running'
                   RETURNING id"""
            )
            return len(rows)

    async def _run(self) -> None:
        with contextlib.suppress(Exception):
            await self.recover_interrupted_jobs()
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
                _LOG.exception("OCR AI worker iteration failed")
                delay = self.backoff_seconds[min(backoff_index, len(self.backoff_seconds) - 1)]
                backoff_index += 1
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._wake.wait(), timeout=delay)
                continue
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), timeout=self.poll_seconds)

    async def _claim_next_job(self) -> dict[str, Any] | None:
        lease_token = uuid4().hex
        async with self.pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock($1)", _JOB_CLAIM_LOCK_KEY)
            await expire_user_tasks(conn)
            await conn.execute(
                """UPDATE document_ocr_ai_proposals
                   SET status = 'failed',
                       error_code = 'OCR_AI_INTERRUPTED',
                       lease_token = NULL,
                       lease_expires_at = NULL,
                       finished_at = COALESCE(finished_at, now())
                   WHERE status = 'running'
                     AND lease_expires_at IS NOT NULL
                     AND lease_expires_at <= now()"""
            )
            await conn.execute(
                """UPDATE document_ocr_ai_proposals
                   SET status = 'stale',
                       error_code = 'OCR_AI_EXPIRED',
                       finished_at = COALESCE(finished_at, now())
                   WHERE status = 'queued'
                     AND expires_at IS NOT NULL
                     AND expires_at <= now()"""
            )
            active_running = await conn.fetchval(
                "SELECT count(*) FROM document_ocr_ai_proposals WHERE status = 'running'"
            )
            if int(active_running or 0) > 0:
                return None
            row = await conn.fetchrow(
                """WITH next_job AS (
                     SELECT id FROM document_ocr_ai_proposals
                     WHERE status = 'queued' AND attempts = 0
                     ORDER BY requested_at ASC
                     FOR UPDATE SKIP LOCKED
                     LIMIT 1
                   )
                   UPDATE document_ocr_ai_proposals p
                   SET status = 'running',
                       attempts = p.attempts + 1,
                       lease_token = $1,
                       lease_expires_at = now() + make_interval(secs => $2),
                       started_at = now()
                   FROM next_job
                   WHERE p.id = next_job.id
                   RETURNING p.*""",
                lease_token,
                float(self.lease_seconds),
            )
            return dict(row) if row is not None else None

    async def _check_live_state(
        self,
        conn: Any,
        job: dict[str, Any],
        *,
        lock_row: bool = False,
    ) -> tuple[str, dict[str, Any] | None]:
        suffix = " FOR UPDATE" if lock_row else ""
        live = await conn.fetchrow(
            f"SELECT *, (expires_at IS NOT NULL AND expires_at <= now()) AS expired "
            f"FROM document_ocr_ai_proposals WHERE id = $1{suffix}",
            job["id"],
        )
        if live is None or live["status"] != "running" or live["lease_token"] != job["lease_token"]:
            return "abort", None
        if live["expired"]:
            return "expired", None

        principal = await _load_live_principal(conn, job["requested_by"])
        if principal is None:
            return "revoked", None

        if job["purpose"] == "admin_correction":
            if not principal.has(Permission.CURATE):
                return "revoked", None
            try:
                record = await _record(
                    conn,
                    principal,
                    job["document_id"],
                    job["version_id"],
                    date.today(),
                )
            except ReviewError:
                return "revoked", None
            if not record["can_edit"]:
                return "revoked", None
            if (
                record["revision"] != job["source_review_revision"]
                or record["original_file_sha256"] != job["pdf_sha256"]
            ):
                return "stale", None
            page_text = await conn.fetchval(
                """SELECT text_original FROM source_pages
                   WHERE document_version_id = $1 AND page_number = $2""",
                job["version_id"],
                job["page_number"],
            )
            if page_text_sha256(page_text) != job["page_text_sha256"]:
                return "stale", None
            return "ok", {
                "original_file_path": record["original_file_path"],
                "original_file_sha256": record["original_file_sha256"],
            }

        approved = await _user_can_access_approved_version(
            conn,
            principal,
            document_id=job["document_id"],
            version_id=job["version_id"],
        )
        if approved is None:
            return "revoked", None
        if (
            approved["original_file_sha256"] != job["pdf_sha256"]
            or approved["source_review_revision"] != job["source_review_revision"]
        ):
            return "stale", None
        page_text = await conn.fetchval(
            "SELECT text_original FROM source_pages "
            "WHERE document_version_id=$1 AND page_number=$2",
            job["version_id"],
            job["page_number"],
        )
        if page_text_sha256(page_text) != job["page_text_sha256"]:
            return "stale", None
        return "ok", {
            "original_file_path": approved["original_file_path"],
            "original_file_sha256": approved["original_file_sha256"],
        }

    async def _finish_terminal(
        self,
        job: dict[str, Any],
        *,
        status: str,
        error_code: str,
        profile_id: str | None = None,
        profile_revision: str | None = None,
        model_digest: str | None = None,
    ) -> None:
        async with self.pool.acquire() as conn, conn.transaction():
            await conn.execute(
                """UPDATE document_ocr_ai_proposals
                   SET status = $3,
                       error_code = $4,
                       profile_id = COALESCE($5, profile_id),
                       profile_revision = COALESCE($6, profile_revision),
                       model_digest = COALESCE($7, model_digest),
                       lease_token = NULL,
                       lease_expires_at = NULL,
                       finished_at = now()
                   WHERE id = $1 AND status = 'running' AND lease_token = $2""",
                job["id"],
                job["lease_token"],
                status,
                error_code,
                profile_id,
                profile_revision,
                model_digest,
            )

    async def _checkpoint(self, job: dict[str, Any]) -> tuple[bool, dict[str, Any] | None]:
        async with self.pool.acquire() as conn, conn.transaction():
            state, version_info = await self._check_live_state(conn, job, lock_row=True)
            if state == "ok":
                return True, version_info
            if state == "stale":
                await conn.execute(
                    """UPDATE document_ocr_ai_proposals
                       SET status = 'stale', error_code = 'DOCUMENT_REVISION_CONFLICT',
                           lease_token = NULL, lease_expires_at = NULL, finished_at = now()
                       WHERE id = $1 AND status = 'running' AND lease_token = $2""",
                    job["id"],
                    job["lease_token"],
                )
            elif state == "expired":
                await conn.execute(
                    """UPDATE document_ocr_ai_proposals
                       SET status = 'stale', error_code = 'OCR_AI_EXPIRED',
                           lease_token = NULL, lease_expires_at = NULL, finished_at = now()
                       WHERE id = $1 AND status = 'running' AND lease_token = $2""",
                    job["id"],
                    job["lease_token"],
                )
            elif state == "revoked":
                await conn.execute(
                    """UPDATE document_ocr_ai_proposals
                       SET status = 'failed', error_code = 'DOCUMENT_EDIT_DENIED',
                           lease_token = NULL, lease_expires_at = NULL, finished_at = now()
                       WHERE id = $1 AND status = 'running' AND lease_token = $2""",
                    job["id"],
                    job["lease_token"],
                )
            return False, None

    async def run_once(self) -> bool:
        """Claim and execute at most one queued OCR AI proposal."""
        async with self.pool.acquire() as owner:
            if not await owner.fetchval("SELECT pg_try_advisory_lock($1)", _WORKER_LOCK_KEY):
                return False
            try:
                return await self._run_locked_once()
            finally:
                await owner.execute("SELECT pg_advisory_unlock($1)", _WORKER_LOCK_KEY)

    async def _await_inference(
        self,
        job: dict[str, Any],
        awaitable: Awaitable[_Result],
    ) -> _Result | None:
        """Cancel the HTTP request promptly when ACL/source/task state changes."""
        task = asyncio.ensure_future(awaitable)
        try:
            while True:
                done, _ = await asyncio.wait({task}, timeout=0.25)
                if task in done:
                    return task.result()
                proceed, _ = await self._checkpoint(job)
                if not proceed:
                    return None
        finally:
            if not task.done():
                task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    async def _run_locked_once(self) -> bool:
        job = await self._claim_next_job()
        if job is None:
            return False

        self.current_proposal_id = str(job["id"])
        try:
            async with asyncio.timeout(self.job_timeout_seconds):
                return await self._execute_job(job)
        except TimeoutError:
            await self._finish_terminal(job, status="failed", error_code="OCR_AI_TIMEOUT")
            return True
        except asyncio.CancelledError:
            await self._finish_terminal(job, status="failed", error_code="OCR_AI_INTERRUPTED")
            raise
        except Exception:
            await self._finish_terminal(job, status="failed", error_code="OCR_AI_FAILED")
            raise
        finally:
            self.current_proposal_id = None

    async def _execute_job(self, job: dict[str, Any]) -> bool:
        proceed, version_info = await self._checkpoint(job)
        if not proceed or version_info is None:
            return True

        if self.store_root is None:
            await self._finish_terminal(
                job,
                status="failed",
                error_code="DOCUMENT_STORE_NOT_CONFIGURED",
            )
            return True

        render_params = job.get("render_params") or {}
        if isinstance(render_params, str):
            render_params = json.loads(render_params)
        dpi = int(render_params.get("dpi", DEFAULT_RENDER_DPI))
        max_edge = int(render_params.get("max_edge", DEFAULT_RENDER_MAX_EDGE))
        max_bytes = int(render_params.get("max_bytes", DEFAULT_RENDER_MAX_BYTES))

        try:
            pdf_bytes = await asyncio.to_thread(
                read_immutable_pdf,
                self.store_root,
                version_info["original_file_path"],
                version_info["original_file_sha256"],
                max_bytes=self.max_pdf_bytes,
            )
            png_bytes, render_meta = await asyncio.to_thread(
                render_page_isolated,
                pdf_bytes,
                page_number=int(job["page_number"]),
                temporary_root=self.store_root,
                dpi=dpi,
                max_edge=max_edge,
                max_bytes=max_bytes,
            )
        except ValueError as exc:
            await self._finish_terminal(job, status="failed", error_code=str(exc))
            return True

        # Checkpoint before spending GPU/CPU on the model call.
        proceed, _ = await self._checkpoint(job)
        if not proceed:
            return True

        async def save_fingerprint(snapshot: Any) -> bool:
            async with self.pool.acquire() as conn, conn.transaction():
                state, _ = await self._check_live_state(conn, job, lock_row=True)
                if state != "ok":
                    return False
                await conn.execute(
                    """UPDATE document_ocr_ai_proposals SET profile_id=$3,
                       profile_revision=$4, model_digest=$5, image_sha256=$6,
                       render_params=render_params || $7::jsonb
                       WHERE id=$1 AND status='running' AND lease_token=$2""",
                    job["id"],
                    job["lease_token"],
                    snapshot.profile_id,
                    snapshot.profile_revision,
                    snapshot.model_digest,
                    render_meta["image_sha256"],
                    json.dumps({"model_profile_sha256": snapshot.profile_fingerprint}),
                )
                return True

        outcome = await self._await_inference(
            job,
            self.runtime.generate_vision(
                image_png=png_bytes,
                prompt=OCR_AI_PROMPT,
                schema=OCR_PAGE_CANDIDATE_SCHEMA,
                principal_id=job["requested_by"],
                document_id=job["document_id"],
                on_fingerprint=save_fingerprint,
            ),
        )
        if outcome is None:
            return True
        if outcome.error_code or outcome.content is None:
            await self._finish_terminal(
                job,
                status="stale" if outcome.error_code == "OCR_AI_MODEL_CHANGED" else "failed",
                error_code=outcome.error_code or "OCR_AI_FAILED",
                profile_id=outcome.profile_id or None,
                profile_revision=outcome.profile_revision or None,
                model_digest=outcome.model_digest or None,
            )
            return True

        try:
            candidate, candidate_text = parse_ocr_candidate(outcome.content)
        except ValueError as exc:
            await self._finish_terminal(
                job,
                status="failed",
                error_code=str(exc),
                profile_id=outcome.profile_id or None,
                profile_revision=outcome.profile_revision or None,
                model_digest=outcome.model_digest or None,
            )
            return True

        # Final atomic check before saving ready output; late outputs on cancelled/stale jobs
        # are discarded cleanly.
        async with self.pool.acquire() as conn, conn.transaction():
            state, _ = await self._check_live_state(conn, job, lock_row=True)
            if state == "ok":
                await conn.execute(
                    """UPDATE document_ocr_ai_proposals
                           SET status = 'ready',
                               candidate_json = $3::jsonb,
                               candidate_text = $4,
                               image_sha256 = $5,
                               profile_id = $6,
                               profile_revision = $7,
                               model_digest = $8,
                               error_code = NULL,
                               lease_token = NULL,
                               lease_expires_at = NULL,
                               finished_at = now()
                           WHERE id = $1 AND status = 'running' AND lease_token = $2""",
                    job["id"],
                    job["lease_token"],
                    json.dumps(candidate.model_dump(), ensure_ascii=False),
                    candidate_text,
                    render_meta["image_sha256"],
                    outcome.profile_id or None,
                    outcome.profile_revision or None,
                    outcome.model_digest or None,
                )
            elif state == "stale":
                await conn.execute(
                    """UPDATE document_ocr_ai_proposals
                           SET status = 'stale', error_code = 'DOCUMENT_REVISION_CONFLICT',
                               lease_token = NULL, lease_expires_at = NULL, finished_at = now()
                           WHERE id = $1 AND status = 'running' AND lease_token = $2""",
                    job["id"],
                    job["lease_token"],
                )
            elif state == "expired":
                await conn.execute(
                    """UPDATE document_ocr_ai_proposals
                           SET status = 'stale', error_code = 'OCR_AI_EXPIRED',
                               lease_token = NULL, lease_expires_at = NULL, finished_at = now()
                           WHERE id = $1 AND status = 'running' AND lease_token = $2""",
                    job["id"],
                    job["lease_token"],
                )
            elif state == "revoked":
                await conn.execute(
                    """UPDATE document_ocr_ai_proposals
                           SET status = 'failed', error_code = 'DOCUMENT_EDIT_DENIED',
                               lease_token = NULL, lease_expires_at = NULL, finished_at = now()
                           WHERE id = $1 AND status = 'running' AND lease_token = $2""",
                    job["id"],
                    job["lease_token"],
                )
        return True
