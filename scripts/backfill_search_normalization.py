"""Recompute Search v1 normalization columns for rows with a stale revision.

Usage:
    python scripts/backfill_search_normalization.py --dry-run
    python scripts/backfill_search_normalization.py --batch-size 500

Requires DATABASE_URL (or --database-url).  The script never changes
`text_original` or `text_indexed`; it only recomputes `text_normalized` and
`text_folded` and stamps `normalization_revision`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.storage.normalization import (  # noqa: E402
    backfill_normalization,
    normalization_status,
)
from app.storage.postgres import create_pool  # noqa: E402


async def run(args: argparse.Namespace) -> int:
    dsn = args.database_url or os.getenv("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL is required", file=sys.stderr)
        return 2
    pool = await create_pool(dsn)
    try:
        before = await normalization_status(pool)
        print(json.dumps({"before": before}, ensure_ascii=False))
        result = await backfill_normalization(
            pool,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
        )
        print(json.dumps({"result": result}, ensure_ascii=False))
        if not args.dry_run:
            after = await normalization_status(pool)
            print(json.dumps({"after": after}, ensure_ascii=False))
        return 0
    finally:
        await pool.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
