"""Ordered, idempotent migration runner for the single PostgreSQL database.

Every migration runs in its own transaction and is recorded in `schema_migrations`
with the SHA-256 of the SQL text. A changed file that was already applied is
rejected instead of silently re-applied.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

MIGRATIONS_DIR = Path(__file__).resolve().parent


def migration_files() -> list[Path]:
    return sorted(
        path for path in MIGRATIONS_DIR.glob("*.sql") if not path.name.endswith(".down.sql")
    )


async def apply_migrations(connection: Any) -> list[str]:
    """Apply pending migrations on an asyncpg connection; return the names applied."""
    async with connection.transaction():
        await connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended("
            "current_database() || ':' || current_schema() || ':schema_migrations', 0))"
        )
        return await _apply_locked(connection)


async def _apply_locked(connection: Any) -> list[str]:
    await connection.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
             name TEXT PRIMARY KEY,
             sha256 TEXT NOT NULL,
             applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"""
    )
    applied = {
        row["name"]: row["sha256"]
        for row in await connection.fetch("SELECT name, sha256 FROM schema_migrations")
    }
    done: list[str] = []
    for path in migration_files():
        sql = path.read_text(encoding="utf-8")
        digest = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        if path.name in applied:
            if applied[path.name] != digest:
                raise RuntimeError(f"MIGRATION_CHANGED_AFTER_APPLY:{path.name}")
            continue
        async with connection.transaction():
            await connection.execute(sql)
            await connection.execute(
                "INSERT INTO schema_migrations (name, sha256) VALUES ($1, $2)",
                path.name,
                digest,
            )
        done.append(path.name)
    return done
