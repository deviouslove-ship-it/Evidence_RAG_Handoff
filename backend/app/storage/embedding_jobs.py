"""Embedding model changes from the Admin Portal (G5): preflight, jobs, worker.

An administrator picks an embedding profile from the Model Registry.  ``preflight``
checks connection, the model listed by the service, a test vector (size, values),
storage compatibility and data policy, and counts the nodes that need a vector.
After the administrator confirms, ``create_job`` queues a job; ``EmbeddingWorker``
(started with the API process, independent of any browser session) fills the index
in batches with progress, pauses/resumes, retries with back-off, survives restarts
(stale ``running`` jobs are re-queued), builds and verifies the vector index and
switches search to it in one transaction (``embeddings.activate_index``).  Until
then the previous index and its model keep serving search; on failure they stay.
Nothing here deletes vectors, indexes, profiles or jobs.

Model, endpoint, provider and dimension come from the Registry and the model's own
answers; nothing is hard-coded.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import math
import os
import socket
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from ..audit import append_audit
from ..model_registry.profiles import OperatingMode, PrivacyZone
from ..model_registry.runtime import (
    EmbeddingOutcome,
    EndpointPolicy,
    RegistryRuntimeError,
    _profile_from_row,
    validate_profile,
)
from .embeddings import (
    PROBE_TEXT,
    EmbeddingIndexError,
    activate_index,
    active_index,
    cosine,
    eligible_count,
    ensure_vector_index,
    find_index,
    node_text,
    open_index,
    parse_vector,
    pending_batch,
    pending_count,
    remote_ineligible_count,
    store_vectors,
    vector_type,
    vectors_valid,
    verify_index,
)

_LOG = logging.getLogger(__name__)

OPEN_STATES = ("queued", "running", "paused", "failed")
DEFAULT_BATCH_SIZE = 16
MAX_BATCH_SIZE = 256
MAX_CONSECUTIVE_FAILURES = 5
BACKOFF_SECONDS = (15.0, 30.0, 60.0, 120.0, 120.0)
ERROR_HISTORY = 20
SAMPLE_MIN_SIMILARITY = 0.95
COUNT_REFRESH_BATCHES = 50
# Errors that retrying cannot fix: the job fails at once with a clear reason.
PERMANENT_ERRORS = frozenset({
    "PROFILE_NOT_FOUND", "PROFILE_UNAPPROVED", "PROFILE_UNHEALTHY",
    "MODEL_CAPABILITY_UNAVAILABLE", "MODEL_SECRET_REF_INVALID", "MODEL_SECRET_UNAVAILABLE",
    "AI_ENDPOINT_INVALID", "AI_EGRESS_DENIED", "AI_LOCAL_ENDPOINT_DENIED",
    "ADAPTER_UNSUPPORTED", "PROFILE_INVALID", "REMOTE_EMBEDDING_DENIED",
    "REMOTE_EMBEDDING_DOCUMENTS_DENIED", "EMBEDDING_MODEL_CHANGED", "EMBEDDING_INVALID",
    "EMBEDDING_DIMENSIONS_UNSUPPORTED", "EMBEDDING_NOT_CONFIGURED",
})
# Errors after which a smaller batch may succeed (slow CPU model, response size).
SHRINK_ERRORS = frozenset({"MODEL_UNREACHABLE", "MODEL_RESPONSE_TOO_LARGE",
                           "MODEL_REQUEST_FAILED"})


class EmbeddingJobError(Exception):
    def __init__(self, code: str, status_code: int = 409,
                 details: dict[str, Any] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.details = details or {}


def _json(value: Any, default: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return default
    return value if value is not None else default


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def remote_embedding_allowed(mode: str, policy: EndpointPolicy) -> bool:
    return (OperatingMode(mode) == OperatingMode.API and policy.remote_processing_allowed
            and policy.remote_embedding_allowed)


# ------------------------------------------------------------------ views

def _job_view(row: Any) -> dict[str, Any]:
    total = int(row["total_nodes"])
    done = min(int(row["done_nodes"]), total) if total else int(row["done_nodes"])
    remaining = max(0, total - done)
    rate = float(row["rate_per_minute"]) if row["rate_per_minute"] else None
    eta = (remaining / rate * 60) if rate and remaining and row["status"] in (
        "running", "queued") else None
    return {
        "id": str(row["id"]),
        "index_id": str(row["embedding_index_id"]),
        "profile_id": row["profile_key"],
        "model_id": row.get("model_id"),
        "dimensions": row.get("dimensions"),
        "kind": row["kind"],
        "status": row["status"],
        "phase": row["phase"],
        "batch_size": row["batch_size"],
        "total_nodes": total,
        "done_nodes": done,
        "remaining_nodes": remaining,
        "embedded_nodes": int(row["embedded_nodes"]),
        "percent": round(100 * done / total, 1) if total else 100.0,
        "rate_per_minute": round(rate, 1) if rate else None,
        "eta_seconds": round(eta) if eta is not None else None,
        "failed_batches": int(row["failed_batches"]),
        "consecutive_failures": int(row["consecutive_failures"]),
        "last_error": row["last_error"],
        "errors": _json(row["errors"], [])[-ERROR_HISTORY:],
        "next_attempt_at": _iso(row["next_attempt_at"]),
        "created_at": _iso(row["created_at"]),
        "started_at": _iso(row["started_at"]),
        "updated_at": _iso(row["updated_at"]),
        "finished_at": _iso(row["finished_at"]),
        "heartbeat_at": _iso(row["heartbeat_at"]),
    }


_JOB_SELECT = """
    SELECT j.*, i.model_id, i.dimensions
    FROM embedding_jobs j JOIN embedding_indices i ON i.id = j.embedding_index_id"""


async def _embedding_profiles(connection: Any) -> list[dict[str, Any]]:
    rows = await connection.fetch(
        """SELECT mp.profile_key, mp.model_id, mp.revision, mp.privacy_zone, mp.health,
                  mp.params, p.approved
           FROM model_profiles mp JOIN providers p ON p.id = mp.provider_id
           WHERE mp.capabilities ? 'embedding'
           ORDER BY mp.profile_key"""
    )
    return [{
        "profile_id": row["profile_key"], "model_id": row["model_id"],
        "revision": row["revision"], "privacy_zone": row["privacy_zone"],
        "health": row["health"], "provider_approved": bool(row["approved"]),
        "requested_dimensions": _json(row["params"], {}).get("dimensions"),
    } for row in rows]


async def embedding_overview(
    pool: Any, *, mode: str, policy: EndpointPolicy, worker: EmbeddingWorker | None,
) -> dict[str, Any]:
    async with pool.acquire() as connection:
        active = await active_index(connection)
        indices = await connection.fetch(
            """SELECT i.id, i.model_id, i.model_revision, i.dimensions, i.index_revision,
                      i.profile_key, i.status, i.is_active, i.node_count, i.created_at,
                      i.completed_at, i.activated_at, i.retired_at, i.verified_at,
                      i.last_error,
                      (SELECT count(*) FROM node_embeddings e
                       WHERE e.embedding_index_id = i.id) AS vectors
               FROM embedding_indices i ORDER BY i.index_revision DESC LIMIT 50"""
        )
        jobs = await connection.fetch(_JOB_SELECT + " ORDER BY j.created_at DESC LIMIT 20")
        eligible = await eligible_count(connection)
        missing = await pending_count(connection, active["id"]) if active else eligible
        route = await connection.fetchval(
            """SELECT mp.profile_key FROM stage_routes sr
               JOIN model_profiles mp ON mp.id = sr.profile_id
               WHERE sr.mode = $1 AND sr.stage = 'embedding'""",
            mode,
        )
        profiles = await _embedding_profiles(connection)
        by_key = {item["profile_id"]: item for item in profiles}
        change: dict[str, Any] = {"detected": False}
        target = route or (active["profile_key"] if active else None)
        target_profile = by_key.get(target) if target else None
        if active is None and profiles:
            change = {"detected": True, "reason": "no_active_index", "profile_id": target,
                      "model_id": target_profile["model_id"] if target_profile else None,
                      "pending_nodes": eligible}
        elif active is not None and target_profile is not None and (
            target_profile["model_id"] != active["model_id"]
            or target_profile["revision"] != active["model_revision"]
        ):
            change = {"detected": True,
                      "reason": "route_changed" if target != active["profile_key"]
                      else "profile_model_changed"}
        if change["detected"] and active is not None and target_profile is not None:
            reusable = await connection.fetchrow(
                """SELECT id FROM embedding_indices
                   WHERE model_id = $1 AND model_revision = $2
                   ORDER BY is_active DESC, index_revision DESC LIMIT 1""",
                target_profile["model_id"], target_profile["revision"],
            )
            change.update({
                "profile_id": target,
                "model_id": target_profile["model_id"],
                "pending_nodes": await pending_count(connection, reusable["id"])
                if reusable else eligible,
            })
    open_jobs = [row for row in jobs if row["status"] in OPEN_STATES]
    if change.get("detected") and target:
        change["open_job_id"] = next(
            (str(row["id"]) for row in open_jobs if row["profile_key"] == target), None
        )
    return {
        "mode": mode,
        "remote_embedding_allowed": remote_embedding_allowed(mode, policy),
        "route_profile_id": route,
        "active_index": _index_view(active, None) if active else None,
        "eligible_nodes": eligible,
        "missing_in_active": missing if active else None,
        "change": change,
        "profiles": profiles,
        "indices": [_index_view(row, row["vectors"]) for row in indices],
        "jobs": [_job_view(row) for row in jobs],
        "worker": worker.status() if worker is not None else {"enabled": False,
                                                              "alive": False},
    }


def _index_view(row: Any, vectors: Any) -> dict[str, Any]:
    status = row["status"] if "status" in row.keys() else "ready"
    is_active = bool(row["is_active"]) if "is_active" in row.keys() else True
    view = {
        "id": str(row["id"]), "model_id": row["model_id"], "revision": row["model_revision"],
        "dimensions": row["dimensions"], "profile_id": row["profile_key"],
        "status": status, "is_active": is_active,
        "state": "active" if is_active and status == "ready" else status,
        "node_count": row["node_count"], "completed_at": _iso(row["completed_at"]),
        "storage": _storage(row["dimensions"]),
    }
    if vectors is not None:
        view["vectors"] = int(vectors)
    for key in ("index_revision", "created_at", "activated_at", "retired_at",
                "verified_at", "last_error"):
        if key in row.keys():
            value = row[key]
            view[key] = _iso(value) if isinstance(value, datetime) else value
    return view


def _storage(dimensions: int) -> str | None:
    try:
        return vector_type(int(dimensions))
    except EmbeddingIndexError:
        return None


# ------------------------------------------------------------- preflight

async def preflight(
    pool: Any, runtime: Any, *, profile_key: str, rebuild: bool, mode: str,
    policy: EndpointPolicy, batch_size: int = DEFAULT_BATCH_SIZE,
) -> dict[str, Any]:
    """Check a profile before a rebuild and count the work; changes only ``health``."""

    checks: list[dict[str, Any]] = []
    problems: list[str] = []

    def check(key: str, ok: bool, detail: str | None = None, code: str | None = None) -> bool:
        checks.append({"key": key, "ok": ok, "detail": detail, "code": None if ok else code})
        if not ok and code:
            problems.append(code)
        return ok

    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            """SELECT mp.profile_key, p.adapter, p.endpoint, p.approved AS provider_approved,
                      mp.model_id, mp.revision, mp.capabilities, mp.privacy_zone, mp.params,
                      mp.secret_ref, mp.fallback, mp.health
               FROM model_profiles mp JOIN providers p ON p.id = mp.provider_id
               WHERE mp.profile_key = $1""",
            profile_key,
        )
    if row is None:
        raise EmbeddingJobError("PROFILE_NOT_FOUND", 404)
    try:
        profile = _profile_from_row(row)
    except RegistryRuntimeError as exc:
        raise EmbeddingJobError(str(exc), 422) from exc
    result: dict[str, Any] = {
        "profile_id": profile.profile_id, "model_id": profile.model_id,
        "revision": profile.revision, "privacy_zone": profile.privacy_zone.value,
        "checks": checks, "problems": problems, "rebuild": rebuild,
    }
    public = profile.privacy_zone == PrivacyZone.PUBLIC
    if not (
        check("capability", "embedding" in profile.capabilities,
              "Hồ sơ có vai trò embedding", "MODEL_CAPABILITY_UNAVAILABLE")
        and check("approved", profile.provider_approved, "Dịch vụ đã được phê duyệt",
                  "PROFILE_UNAPPROVED")
    ):
        return {**result, "ok": False}
    if public and not check(
        "data_policy", remote_embedding_allowed(mode, policy),
        "Chính sách máy chủ cho phép embedding qua API bên ngoài", "REMOTE_EMBEDDING_DENIED",
    ):
        return {**result, "ok": False}
    try:
        validate_profile(profile, mode, policy, "embedding")
        runtime._resolve_secret(profile)
        check("configuration", True, "Địa chỉ dịch vụ và khóa hợp lệ với chính sách")
    except RegistryRuntimeError as exc:
        check("configuration", False, None, str(exc))
        return {**result, "ok": False}

    probe = await runtime.probe(profile_key)
    if not check("connection", probe.get("health") == "ready",
                 "Dịch vụ phản hồi và liệt kê đúng model",
                 "EMBEDDING_PROBE_" + str(probe.get("status", "unknown")).upper()):
        return {**result, "ok": False, "probe_status": probe.get("status")}
    started = time.monotonic()
    outcome: EmbeddingOutcome = await runtime.embed(
        [PROBE_TEXT], profile_key=profile_key, purpose="index"
    )
    latency = time.monotonic() - started
    if not check("test_vector", bool(outcome.vectors), "Model trả về vector thử",
                 outcome.error or "EMBEDDING_UNAVAILABLE"):
        return {**result, "ok": False}
    assert outcome.vectors is not None
    dimensions = outcome.dimensions or 0
    result.update({"dimensions": dimensions, "latency_ms": round(latency * 1000)})
    check("vector_values", vectors_valid(outcome.vectors, dimensions),
          "Vector gồm số hữu hạn, khác 0", "EMBEDDING_INVALID")
    requested = profile.params.get("dimensions")
    if isinstance(requested, int):
        check("requested_dimensions", requested == dimensions,
              f"Số chiều trả về {dimensions} / yêu cầu {requested}",
              "EMBEDDING_DIMENSION_MISMATCH")
    storage = _storage(dimensions)
    result["storage"] = storage
    check("storage", storage is not None,
          f"{dimensions} chiều, lưu và đánh chỉ mục bằng {storage}" if storage else
          f"{dimensions} chiều vượt giới hạn chỉ mục (tối đa 4000)",
          "EMBEDDING_DIMENSIONS_UNSUPPORTED")

    async with pool.acquire() as connection:
        eligible = await eligible_count(connection)
        active = await active_index(connection)
        target = await find_index(connection, model_id=profile.model_id,
                                  revision=profile.revision, dimensions=dimensions,
                                  rebuild=rebuild)
        to_embed = await pending_count(connection, target["id"]) if target else eligible
        open_job = None
        if target is not None:
            open_job = await connection.fetchrow(
                _JOB_SELECT + " WHERE j.embedding_index_id = $1 AND j.status = ANY($2::text[])",
                target["id"], list(OPEN_STATES),
            )
        if public:
            denied = await remote_ineligible_count(connection)
            check("documents_policy", denied == 0,
                  "Mọi văn bản được phép xử lý bên ngoài" if denied == 0 else
                  f"{denied} nút thuộc văn bản không được phép gửi ra ngoài",
                  "REMOTE_EMBEDDING_DOCUMENTS_DENIED")
    same_as_active = bool(target is not None and active is not None
                          and target["id"] == active["id"])
    batches = math.ceil(to_embed / max(1, batch_size))
    result.update({
        "ok": not problems,
        "eligible_nodes": eligible,
        "already_embedded": max(0, eligible - to_embed),
        "to_embed": to_embed,
        "kind": "catch_up" if same_as_active else "rebuild",
        "target_index_id": str(target["id"]) if target else None,
        "target_index_status": target["status"] if target else None,
        "active_index": _index_view(active, None) if active else None,
        # Rough: one test text took ``latency``; a batch costs more on CPU models.
        "estimated_seconds": round(batches * latency * max(1.0, batch_size / 4)),
        "open_job": _job_view(open_job) if open_job else None,
    })
    return result


# ------------------------------------------------------------- job control

async def create_job(
    pool: Any, runtime: Any, *, actor_id: UUID, profile_key: str, batch_size: int,
    rebuild: bool, mode: str, policy: EndpointPolicy,
) -> dict[str, Any]:
    if not 1 <= batch_size <= MAX_BATCH_SIZE:
        raise EmbeddingJobError("INVALID_REQUEST", 422)
    check = await preflight(pool, runtime, profile_key=profile_key, rebuild=rebuild,
                            mode=mode, policy=policy, batch_size=batch_size)
    if not check["ok"]:
        raise EmbeddingJobError("EMBEDDING_PREFLIGHT_FAILED", 409,
                                {"problems": check["problems"]})
    if check["open_job"] is not None:
        raise EmbeddingJobError("EMBEDDING_JOB_EXISTS", 409,
                                {"job_id": check["open_job"]["id"]})
    if check["kind"] == "catch_up" and check["to_embed"] == 0:
        raise EmbeddingJobError("EMBEDDING_UP_TO_DATE", 409)
    async with pool.acquire() as connection, connection.transaction():
        index_id = await open_index(
            connection, model_id=check["model_id"], revision=check["revision"],
            dimensions=int(check["dimensions"]), profile_key=profile_key, rebuild=rebuild,
        )
        await connection.execute(
            """UPDATE embedding_indices SET profile_key = $2, last_error = NULL,
                 status = CASE WHEN is_active THEN status ELSE 'building' END
               WHERE id = $1""",
            index_id, profile_key,
        )
        total = await eligible_count(connection)
        done = total - await pending_count(connection, index_id)
        try:
            job_id = await connection.fetchval(
                """INSERT INTO embedding_jobs
                     (embedding_index_id, profile_key, kind, batch_size, total_nodes,
                      done_nodes, requested_by)
                   VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id""",
                index_id, profile_key, check["kind"], batch_size, total, done, actor_id,
            )
        except Exception as exc:  # unique open job per index (race with another admin)
            if type(exc).__name__ == "UniqueViolationError":
                raise EmbeddingJobError("EMBEDDING_JOB_EXISTS", 409) from exc
            raise
        if check["kind"] == "rebuild":
            # The embedding route names the model the administrator chose; search keeps
            # using the active index (and its profile) until the switch.
            profile_id = await connection.fetchval(
                "SELECT id FROM model_profiles WHERE profile_key = $1", profile_key
            )
            await connection.execute(
                """INSERT INTO stage_routes (mode, stage, profile_id, fallback)
                   VALUES ($1, 'embedding', $2, '[]'::jsonb)
                   ON CONFLICT (mode, stage) DO UPDATE SET
                     profile_id = EXCLUDED.profile_id, fallback = EXCLUDED.fallback,
                     escalation_profile_id = NULL""",
                OperatingMode(mode).value, profile_id,
            )
        await append_audit(
            connection, principal_id=actor_id, action="admin.embedding_job_create",
            target_type="embedding_job", target_id=str(job_id),
            metadata={"profile_id": profile_key, "model_id": check["model_id"],
                      "dimensions": check["dimensions"], "kind": check["kind"],
                      "to_embed": check["to_embed"], "index_id": str(index_id)},
        )
        row = await connection.fetchrow(_JOB_SELECT + " WHERE j.id = $1", job_id)
    return _job_view(row)


_TRANSITIONS: dict[str, tuple[tuple[str, ...], str]] = {
    "pause": (("queued", "running"), "paused"),
    "resume": (("paused",), "queued"),
    "retry": (("failed",), "queued"),
    "cancel": (("queued", "paused", "failed"), "cancelled"),
}


async def control_job(pool: Any, *, actor_id: UUID, job_id: UUID, action: str) -> dict[str, Any]:
    if action not in _TRANSITIONS:
        raise EmbeddingJobError("INVALID_REQUEST", 422)
    allowed, target = _TRANSITIONS[action]
    async with pool.acquire() as connection, connection.transaction():
        row = await connection.fetchrow(
            "SELECT id, status, embedding_index_id FROM embedding_jobs WHERE id = $1 FOR UPDATE",
            job_id,
        )
        if row is None:
            raise EmbeddingJobError("EMBEDDING_JOB_NOT_FOUND", 404)
        if row["status"] not in allowed:
            raise EmbeddingJobError("EMBEDDING_JOB_STATE", 409)
        await connection.execute(
            """UPDATE embedding_jobs SET status = $2, updated_at = now(), next_attempt_at = NULL,
                 consecutive_failures = CASE WHEN $3 THEN 0 ELSE consecutive_failures END,
                 finished_at = CASE WHEN $2 = 'cancelled' THEN now() ELSE finished_at END,
                 phase = CASE WHEN $2 = 'queued' THEN 'embedding' ELSE phase END
               WHERE id = $1""",
            job_id, target, action == "retry",
        )
        index_state = {"pause": "paused", "cancel": "paused"}.get(action, "building")
        await connection.execute(
            """UPDATE embedding_indices SET status = $2
               WHERE id = $1 AND NOT is_active AND status <> 'ready'""",
            row["embedding_index_id"], index_state,
        )
        await append_audit(
            connection, principal_id=actor_id, action=f"admin.embedding_job_{action}",
            target_type="embedding_job", target_id=str(job_id),
            metadata={"from": row["status"], "to": target},
        )
        updated = await connection.fetchrow(_JOB_SELECT + " WHERE j.id = $1", job_id)
    return _job_view(updated)


# ------------------------------------------------------------------ worker

class EmbeddingWorker:
    """Runs queued embedding jobs one at a time inside the API process.

    Claiming takes a transaction-level advisory lock, so several API processes
    sharing one database still run a single job at a time.  A ``running`` job whose
    heartbeat is older than ``stale_seconds`` (process killed, server rebooted) is
    re-queued and resumes from the vectors already stored.
    """

    def __init__(
        self, pool: Any, runtime: Any, *, poll_seconds: float = 3.0,
        heartbeat_seconds: float = 15.0, stale_seconds: float = 60.0,
        backoff_seconds: Sequence[float] = BACKOFF_SECONDS,
        sample_min_similarity: float = SAMPLE_MIN_SIMILARITY,
    ) -> None:
        self.pool = pool
        self.runtime = runtime
        self.poll_seconds = poll_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self.stale_seconds = stale_seconds
        self.backoff_seconds = tuple(backoff_seconds) or BACKOFF_SECONDS
        self.sample_min_similarity = sample_min_similarity
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:8]}"
        self._wake = asyncio.Event()
        self._stopping = False
        self._task: asyncio.Task[None] | None = None
        self.current_job_id: str | None = None
        self.last_poll_at: datetime | None = None
        self.last_error: str | None = None

    # lifecycle ---------------------------------------------------------
    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="embedding-worker")

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
            _LOG.warning("embedding worker stopped with an error", exc_info=True)

    def wake(self) -> None:
        self._wake.set()

    def status(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "alive": self._task is not None and not self._task.done(),
            "worker_id": self.worker_id,
            "current_job_id": self.current_job_id,
            "last_poll_at": _iso(self.last_poll_at),
            "last_error": self.last_error,
        }

    async def _run(self) -> None:
        while not self._stopping:
            try:
                if await self.run_once():
                    continue
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_error = type(exc).__name__
                _LOG.warning("embedding worker poll failed: %s", type(exc).__name__)
            self._wake.clear()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), self.poll_seconds)

    async def run_once(self) -> bool:
        """Claim and run one job; ``False`` when the queue is empty."""

        self.last_poll_at = datetime.now(UTC)
        job = await self._claim()
        if job is None:
            return False
        await self._process(job)
        return True

    # claiming ----------------------------------------------------------
    async def _claim(self) -> Any:
        async with self.pool.acquire() as connection, connection.transaction():
            await connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended("
                "current_database() || ':' || current_schema() || ':embedding_jobs', 0))"
            )
            requeued = await connection.fetch(
                """UPDATE embedding_jobs SET status = 'queued', worker_id = NULL,
                     updated_at = now()
                   WHERE status = 'running'
                     AND (heartbeat_at IS NULL OR heartbeat_at < now() - make_interval(secs => $1))
                   RETURNING id""",
                float(self.stale_seconds),
            )
            for row in requeued:
                _LOG.warning("embedding job %s re-queued after a lost worker", row["id"])
            if await connection.fetchval(
                "SELECT EXISTS (SELECT 1 FROM embedding_jobs WHERE status = 'running')"
            ):
                return None
            job = await connection.fetchrow(
                """SELECT id FROM embedding_jobs
                   WHERE status = 'queued' AND (next_attempt_at IS NULL OR next_attempt_at <= now())
                   ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED"""
            )
            if job is None:
                return None
            await connection.execute(
                """UPDATE embedding_jobs SET status = 'running', worker_id = $2,
                     heartbeat_at = now(), updated_at = now(), next_attempt_at = NULL,
                     started_at = COALESCE(started_at, now())
                   WHERE id = $1""",
                job["id"], self.worker_id,
            )
            row = await connection.fetchrow(_JOB_SELECT + " WHERE j.id = $1", job["id"])
            await connection.execute(
                """UPDATE embedding_indices SET status = 'building', last_error = NULL
                   WHERE id = $1 AND NOT is_active AND status <> 'ready'""",
                row["embedding_index_id"],
            )
        return row

    # processing --------------------------------------------------------
    async def _process(self, job: Any) -> None:
        job_id = UUID(str(job["id"]))
        self.current_job_id = str(job_id)
        beat = asyncio.create_task(self._heartbeat(job_id))
        try:
            outcome = await self._execute(job)
            if outcome == "interrupted":
                await self._requeue(job_id)
        except asyncio.CancelledError:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(asyncio.shield(self._requeue(job_id)), 5)
            raise
        except EmbeddingIndexError as exc:
            await self._fail(job, exc.code)
        except Exception as exc:
            _LOG.warning("embedding job %s failed: %s", job_id, type(exc).__name__,
                         exc_info=True)
            await self._fail(job, "EMBEDDING_WORKER_ERROR", type(exc).__name__)
        finally:
            beat.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await beat
            self.current_job_id = None

    async def _heartbeat(self, job_id: UUID) -> None:
        while True:
            await asyncio.sleep(self.heartbeat_seconds)
            with contextlib.suppress(Exception):
                async with self.pool.acquire() as connection:
                    await connection.execute(
                        """UPDATE embedding_jobs SET heartbeat_at = now()
                           WHERE id = $1 AND worker_id = $2 AND status = 'running'""",
                        job_id, self.worker_id,
                    )

    async def _status(self, job_id: UUID) -> str | None:
        async with self.pool.acquire() as connection:
            status = await connection.fetchval(
                "SELECT status FROM embedding_jobs WHERE id = $1 AND worker_id = $2",
                job_id, self.worker_id,
            )
        return str(status) if status is not None else None

    async def _update(self, job_id: UUID, sql_set: str, *args: Any) -> None:
        async with self.pool.acquire() as connection:
            await connection.execute(
                f"""UPDATE embedding_jobs SET {sql_set}, updated_at = now(), heartbeat_at = now()
                    WHERE id = $1 AND worker_id = $2 AND status = 'running'""",
                job_id, self.worker_id, *args,
            )

    async def _requeue(self, job_id: UUID) -> None:
        async with self.pool.acquire() as connection:
            await connection.execute(
                """UPDATE embedding_jobs SET status = 'queued', worker_id = NULL, updated_at = now()
                   WHERE id = $1 AND worker_id = $2 AND status = 'running'""",
                job_id, self.worker_id,
            )

    async def _record_error(self, job: Any, code: str, detail: str | None,
                            *, failed_batch: bool) -> list[Any]:
        async with self.pool.acquire() as connection:
            current = await connection.fetchval(
                "SELECT errors FROM embedding_jobs WHERE id = $1", job["id"]
            )
        errors = list(_json(current, []))
        errors.append({"at": datetime.now(UTC).isoformat(), "code": code, "detail": detail})
        errors = errors[-ERROR_HISTORY:]
        async with self.pool.acquire() as connection:
            await connection.execute(
                """UPDATE embedding_jobs SET errors = $2::jsonb, last_error = $3,
                     failed_batches = failed_batches + $4, updated_at = now()
                   WHERE id = $1""",
                job["id"], json.dumps(errors, ensure_ascii=False), code, 1 if failed_batch else 0,
            )
        return errors

    async def _fail(self, job: Any, code: str, detail: str | None = None) -> None:
        await self._record_error(job, code, detail, failed_batch=False)
        async with self.pool.acquire() as connection, connection.transaction():
            await connection.execute(
                """UPDATE embedding_jobs SET status = 'failed', worker_id = NULL,
                     next_attempt_at = NULL, updated_at = now()
                   WHERE id = $1 AND status = 'running'""",
                job["id"],
            )
            await connection.execute(
                """UPDATE embedding_indices SET status = 'failed', last_error = $2
                   WHERE id = $1 AND NOT is_active AND status <> 'ready'""",
                job["embedding_index_id"], code,
            )
            await append_audit(
                connection, principal_id=job["requested_by"],
                action="embedding.job_failed", target_type="embedding_job",
                target_id=str(job["id"]), metadata={"code": code},
            )
        _LOG.warning("embedding job %s failed: %s", job["id"], code)

    async def _pause_index(self, job: Any) -> None:
        async with self.pool.acquire() as connection:
            await connection.execute(
                """UPDATE embedding_indices SET status = 'paused'
                   WHERE id = $1 AND NOT is_active AND status <> 'ready'""",
                job["embedding_index_id"],
            )

    async def _wait(self, job_id: UUID, seconds: float) -> str:
        """Back-off that still reacts to pause and shutdown."""

        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self._stopping:
                return "interrupted"
            if await self._status(job_id) != "running":
                return "stopped"
            await asyncio.sleep(min(1.0, max(0.0, deadline - time.monotonic())))
        return "ok"

    async def _refresh_counts(self, job_id: UUID, index_id: UUID) -> tuple[int, int]:
        async with self.pool.acquire() as connection:
            total = await eligible_count(connection)
            done = total - await pending_count(connection, index_id)
        await self._update(job_id, "total_nodes = $3, done_nodes = $4", total, done)
        return total, done

    async def _execute(self, job: Any) -> str:
        job_id = UUID(str(job["id"]))
        index_id = UUID(str(job["embedding_index_id"]))
        async with self.pool.acquire() as connection:
            index = await connection.fetchrow(
                "SELECT id, model_id, model_revision, dimensions, is_active "
                "FROM embedding_indices WHERE id = $1",
                index_id,
            )
            zone = await connection.fetchval(
                "SELECT privacy_zone FROM model_profiles WHERE profile_key = $1",
                job["profile_key"],
            )
        dimensions = int(index["dimensions"])
        vector_type(dimensions)
        public = zone == "public"
        batch_size = int(job["batch_size"])
        consecutive = int(job["consecutive_failures"])
        rate = float(job["rate_per_minute"]) if job["rate_per_minute"] else None
        await self._update(job_id, "phase = 'embedding'")
        total, done = await self._refresh_counts(job_id, index_id)
        batches = 0
        while True:
            if self._stopping:
                return "interrupted"
            if await self._status(job_id) != "running":
                await self._pause_index(job)
                return "stopped"
            async with self.pool.acquire() as connection:
                rows = await pending_batch(connection, index_id, batch_size)
                if rows and public and await remote_ineligible_count(
                    connection, [row["id"] for row in rows]
                ):
                    await self._fail(job, "REMOTE_EMBEDDING_DOCUMENTS_DENIED")
                    return "failed"
            if not rows:
                finished = await self._finalize(job, index, dimensions)
                if finished in ("completed", "failed", "interrupted", "stopped"):
                    return finished
                continue  # new nodes appeared or a transient check failed: go on
            started = time.monotonic()
            outcome: EmbeddingOutcome = await self.runtime.embed(
                [node_text(row) for row in rows], profile_key=job["profile_key"],
                purpose="index",
            )
            elapsed = time.monotonic() - started
            code: str | None = None
            if not outcome.vectors:
                code = outcome.error or "EMBEDDING_UNAVAILABLE"
            elif (outcome.model_id != index["model_id"]
                  or (outcome.revision or "") != index["model_revision"]
                  or outcome.dimensions != dimensions):
                code = "EMBEDDING_MODEL_CHANGED"
            elif not vectors_valid(outcome.vectors, dimensions):
                code = "EMBEDDING_INVALID"
            if code is not None:
                if code in PERMANENT_ERRORS:
                    await self._fail(job, code)
                    return "failed"
                consecutive += 1
                await self._record_error(job, code, f"{len(rows)} nút", failed_batch=True)
                if code in SHRINK_ERRORS and batch_size > 1:
                    batch_size = max(1, batch_size // 2)
                if consecutive >= MAX_CONSECUTIVE_FAILURES:
                    await self._fail(job, code, "hết số lần thử lại")
                    return "failed"
                delay = self.backoff_seconds[min(consecutive - 1, len(self.backoff_seconds) - 1)]
                await self._update(
                    job_id, "consecutive_failures = $3, "
                    "next_attempt_at = now() + make_interval(secs => $4)",
                    consecutive, float(delay),
                )
                waited = await self._wait(job_id, delay)
                if waited == "interrupted":
                    return "interrupted"
                if waited == "stopped":
                    await self._pause_index(job)
                    return "stopped"
                continue
            assert outcome.vectors is not None
            await store_vectors(self.pool, index_id, rows, outcome.vectors)
            consecutive = 0
            done += len(rows)
            batches += 1
            current = len(rows) / max(elapsed, 1e-3) * 60
            rate = current if rate is None else 0.3 * current + 0.7 * rate
            await self._update(
                job_id, "done_nodes = LEAST(total_nodes, done_nodes + $3), "
                "embedded_nodes = embedded_nodes + $3, active_seconds = active_seconds + $4, "
                "rate_per_minute = $5, consecutive_failures = 0, next_attempt_at = NULL",
                len(rows), float(elapsed), float(rate),
            )
            if batches % COUNT_REFRESH_BATCHES == 0:
                total, done = await self._refresh_counts(job_id, index_id)

    async def _finalize(self, job: Any, index: Any, dimensions: int) -> str:
        job_id = UUID(str(job["id"]))
        index_id = UUID(str(index["id"]))
        await self._refresh_counts(job_id, index_id)
        await self._update(job_id, "phase = 'indexing'")
        await ensure_vector_index(self.pool, index_id, dimensions)
        if self._stopping:
            return "interrupted"
        if await self._status(job_id) != "running":
            await self._pause_index(job)
            return "stopped"
        await self._update(job_id, "phase = 'verifying'")
        async with self.pool.acquire() as connection:
            report = await verify_index(connection, index_id, dimensions)
        if report["pending"]:
            await self._update(job_id, "phase = 'embedding'")
            return "pending"
        if report["problems"]:
            await self._fail(job, report["problems"][0], ", ".join(report["problems"]))
            return "failed"
        sample = await self._sample_check(job, index, dimensions)
        if sample is not None:
            if sample in PERMANENT_ERRORS or sample == "EMBEDDING_SAMPLE_MISMATCH":
                await self._fail(job, sample)
                return "failed"
            await self._record_error(job, sample, "kiểm tra mẫu", failed_batch=False)
            waited = await self._wait(job_id, self.backoff_seconds[0])
            return "interrupted" if waited == "interrupted" else (
                "stopped" if waited == "stopped" else "pending")
        await self._update(job_id, "phase = 'switching'")
        switched = await activate_index(self.pool, index_id)
        if switched["status"] == "pending":
            await self._update(job_id, "phase = 'embedding'")
            return "pending"
        async with self.pool.acquire() as connection, connection.transaction():
            await connection.execute(
                """UPDATE embedding_jobs SET status = 'completed', phase = 'done',
                     worker_id = NULL, finished_at = now(), updated_at = now(),
                     done_nodes = total_nodes, next_attempt_at = NULL
                   WHERE id = $1""",
                job_id,
            )
            await append_audit(
                connection, principal_id=job["requested_by"],
                action="embedding.index_activated", target_type="embedding_index",
                target_id=str(index_id),
                metadata={"job_id": str(job_id), "model_id": index["model_id"],
                          "dimensions": dimensions, "vectors": switched["vectors"],
                          "previous_index_id": switched["previous_index_id"]},
            )
        _LOG.info("embedding index %s active (%s vectors)", index_id, switched["vectors"])
        return "completed"

    async def _sample_check(self, job: Any, index: Any, dimensions: int) -> str | None:
        """Re-embed one stored node: the model must still produce the same vector."""

        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                """SELECT e.embedding::text AS vector, n.citation_label, n.label_original,
                          n.text_original, d.title, d.document_number
                   FROM node_embeddings e
                   JOIN document_nodes n ON n.id = e.document_node_id
                   JOIN documents d ON d.id = n.document_id
                   WHERE e.embedding_index_id = $1
                   ORDER BY e.embedded_at DESC LIMIT 1""",
                index["id"],
            )
        if row is None:
            return "EMBEDDING_INDEX_EMPTY"
        outcome: EmbeddingOutcome = await self.runtime.embed(
            [node_text(row)], profile_key=job["profile_key"], purpose="index"
        )
        if not outcome.vectors:
            return outcome.error or "EMBEDDING_UNAVAILABLE"
        if outcome.model_id != index["model_id"] or outcome.dimensions != dimensions:
            return "EMBEDDING_MODEL_CHANGED"
        if cosine(parse_vector(row["vector"]), outcome.vectors[0]) < self.sample_min_similarity:
                return "EMBEDDING_SAMPLE_MISMATCH"
        return None
