"""Normalization revision status and backfill for Search v1.

`text_normalized` and `text_folded` are derived at ingest time.  When the
versioned normalization table changes (for example ``kì -> kỳ``), previously
ingested rows keep the old derived text; the query-side normalizer then no
longer agrees with them.  This module detects that state and can recompute the
derived columns without touching ``text_original``.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from ..audit import append_audit
from ..vietnamese_nlp.unicode_norm import (
    NORMALIZER_REVISION,
    fold_text,
    normalize_text,
)

logger = logging.getLogger(__name__)


async def normalization_status_connection(connection: Any) -> dict[str, Any]:
    rows = await connection.fetch(
        """SELECT normalization_revision, count(*) AS nodes
           FROM document_nodes
           GROUP BY normalization_revision"""
    )
    revisions = {row["normalization_revision"]: int(row["nodes"]) for row in rows}
    total = sum(revisions.values())
    stale = sum(
        count for revision, count in revisions.items() if revision != NORMALIZER_REVISION
    )
    return {
        "current_revision": NORMALIZER_REVISION,
        "total_nodes": total,
        "stale_nodes": stale,
        "revisions": revisions,
    }


async def normalization_status(pool: Any) -> dict[str, Any]:
    async with pool.acquire() as connection:
        return await normalization_status_connection(connection)


async def backfill_normalization(
    pool: Any,
    *,
    batch_size: int = 500,
    dry_run: bool = False,
    actor_id: UUID | None = None,
) -> dict[str, Any]:
    """Recompute derived normalization columns for every stale node.

    The loop reads a bounded batch, recomputes in Python with exactly the same
    functions used at ingest, updates the three derived fields and increments
    only ``normalization_revision``.  ``text_original`` and ``text_indexed`` are
    deliberately not modified.
    """

    batch_size = max(1, min(int(batch_size), 5000))
    scanned = 0
    updated = 0
    async with pool.acquire() as connection:
        if dry_run:
            stale = int(
                await connection.fetchval(
                    "SELECT count(*) FROM document_nodes WHERE normalization_revision <> $1",
                    NORMALIZER_REVISION,
                )
                or 0
            )
            return {
                "current_revision": NORMALIZER_REVISION,
                "scanned": stale,
                "updated": stale,
                "dry_run": True,
            }
        while True:
            rows = await connection.fetch(
                """SELECT id, text_original
                   FROM document_nodes
                   WHERE normalization_revision <> $1
                   ORDER BY id
                   LIMIT $2""",
                NORMALIZER_REVISION,
                batch_size,
            )
            if not rows:
                break
            scanned += len(rows)
            async with connection.transaction():
                for row in rows:
                    await connection.execute(
                        """UPDATE document_nodes
                           SET text_normalized = $2,
                               text_folded = $3,
                               normalization_revision = $4
                           WHERE id = $1
                             AND normalization_revision <> $4""",
                        row["id"],
                        normalize_text(row["text_original"]),
                        fold_text(row["text_original"]),
                        NORMALIZER_REVISION,
                    )
                    updated += 1
                if actor_id is not None:
                    await append_audit(
                        connection,
                        principal_id=actor_id,
                        action="search.normalization_backfill",
                        target_type="document_nodes",
                        target_id=None,
                        metadata={
                            "batch_nodes": len(rows),
                            "normalization_revision": NORMALIZER_REVISION,
                        },
                    )
    return {
        "current_revision": NORMALIZER_REVISION,
        "scanned": scanned,
        "updated": updated,
        "dry_run": dry_run,
    }
