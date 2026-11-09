"""Database revision used to invalidate lookup caches across server workers."""

from typing import Any


async def lookup_revision(database: Any) -> int:
    return int(await database.fetchval(
        "SELECT revision FROM document_lookup_revision WHERE id"
    ))
