"""Hash-chained audit trail. Every privileged change appends one event in its own transaction."""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any
from uuid import UUID

_LOCK_KEY = 7_302_026_001  # pg_advisory_xact_lock key serialising chain appends


def _event_hash(
    previous_hash: str | None,
    principal_id: UUID | None,
    action: str,
    target_type: str,
    target_id: str | None,
    metadata: dict[str, Any],
    occurred_at_iso: str,
) -> str:
    payload = json.dumps(
        [previous_hash, str(principal_id) if principal_id else None, action, target_type,
         target_id, metadata, occurred_at_iso],
        sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def append_audit(
    connection: Any,
    *,
    principal_id: UUID | None,
    action: str,
    target_type: str,
    target_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Append inside the caller's transaction so the change and its audit commit together."""
    metadata = metadata or {}
    await connection.execute("SELECT pg_advisory_xact_lock($1)", _LOCK_KEY)
    previous = await connection.fetchval(
        "SELECT event_hash FROM audit_events ORDER BY event_order DESC LIMIT 1"
    )
    row = await connection.fetchrow("SELECT clock_timestamp() AS now")
    occurred_at = row["now"]
    digest = _event_hash(
        previous, principal_id, action, target_type, target_id, metadata,
        occurred_at.isoformat(),
    )
    await connection.execute(
        """INSERT INTO audit_events
           (principal_id, action, target_type, target_id, metadata,
            previous_hash, event_hash, occurred_at)
           VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8)""",
        principal_id, action, target_type, target_id,
        json.dumps(metadata, ensure_ascii=False), previous, digest, occurred_at,
    )


async def verify_audit_chain(connection: Any, *, limit: int = 10_000) -> dict[str, Any]:
    rows = await connection.fetch(
        """SELECT principal_id, action, target_type, target_id, metadata,
                  previous_hash, event_hash, occurred_at
           FROM audit_events ORDER BY event_order ASC LIMIT $1""",
        limit + 1,
    )
    # Re-hashing up to ``limit`` events is CPU work; keep it off the event loop
    # so other requests are not stalled while an administrator opens the log.
    return await asyncio.to_thread(_verify_rows, rows, limit)


def _verify_rows(rows: Any, limit: int) -> dict[str, Any]:
    previous: str | None = None
    for index, row in enumerate(rows[:limit]):
        metadata = row["metadata"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        expected = _event_hash(
            previous, row["principal_id"], row["action"], row["target_type"],
            row["target_id"], metadata, row["occurred_at"].isoformat(),
        )
        if row["previous_hash"] != previous or row["event_hash"] != expected:
            return {"valid": False, "checked": index + 1, "broken_at": index,
                    "complete": len(rows) <= limit}
        previous = row["event_hash"]
    complete = len(rows) <= limit
    return {"valid": True if complete else None, "checked": min(len(rows), limit),
            "broken_at": None, "complete": complete}
