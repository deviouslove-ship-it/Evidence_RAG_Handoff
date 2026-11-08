"""Read dates and effectivity relations by rule for every approved document (G1).

    python scripts/extract_effectivity.py            # apply migrations, extract, publish

Idempotent: proposals already stored are not added again.  Proposals stay drafts until
a REVIEWER with can_review on the category approves them.  The database comes from
DATABASE_URL; nothing is hard-coded.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.effectivity.service import extract_all  # noqa: E402
from app.migrations.runner import apply_migrations  # noqa: E402
from app.storage.postgres import create_pool  # noqa: E402


async def run() -> dict[str, object]:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("DATABASE_URL is required")
    pool = await create_pool(dsn)
    try:
        async with pool.acquire() as connection:
            await apply_migrations(connection)
        return await extract_all(pool, actor_id=None)
    finally:
        await pool.close()


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run()), ensure_ascii=False, indent=1, default=str))
