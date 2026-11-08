"""PostgreSQL pool factory."""

from __future__ import annotations

from typing import Any


async def create_pool(database_url: str) -> Any:
    try:
        import asyncpg
    except ImportError as exc:  # pragma: no cover - deployment dependency
        raise RuntimeError("POSTGRES_RUNTIME_NOT_CONFIGURED") from exc
    return await asyncpg.create_pool(
        dsn=database_url,
        min_size=1,
        max_size=10,
        command_timeout=30,
        server_settings={"application_name": "vietnamese-evidence-agent"},
    )
