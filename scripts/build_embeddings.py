"""Build, resume or rebuild the embedding index with the Registry model (G2, G5).

    python scripts/build_embeddings.py                      # route of stage "embedding"
    python scripts/build_embeddings.py --profile <key>      # a named local profile
    python scripts/build_embeddings.py --rebuild            # new index revision (model change)

Only nodes without a vector in the index being built are sent, so the command can be
stopped and resumed.  The previous index stays active until the new one is complete.
Model, endpoint and dimension come from the Model Registry; nothing is hard-coded.

Operators do not need this script: Admin Portal > AI > Embedding runs the same steps as
a background job of the API process (app/storage/embedding_jobs.py).  It remains for
maintenance and uses the same functions (app/storage/embeddings.py).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.config import Settings  # noqa: E402
from app.migrations.runner import apply_migrations  # noqa: E402
from app.model_registry.profiles import OperatingMode  # noqa: E402
from app.model_registry.runtime import EndpointPolicy, RegistryRuntime  # noqa: E402
from app.storage.embeddings import build_embeddings  # noqa: E402
from app.storage.postgres import create_pool  # noqa: E402


async def run(args: argparse.Namespace) -> dict[str, object]:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("DATABASE_URL is required")
    settings = Settings.from_env()
    pool = await create_pool(dsn)
    try:
        async with pool.acquire() as connection:
            await apply_migrations(connection)
        runtime = RegistryRuntime(
            pool, mode=OperatingMode(settings.operating_mode),
            attempt_limit=settings.llm_attempt_budget, policy=EndpointPolicy.from_env(),
        )

        async def embed(texts: list[str]) -> object:
            return await runtime.embed(texts, profile_key=args.profile, purpose="index")

        return await build_embeddings(
            pool, embed, profile_key=args.profile, rebuild=args.rebuild,
            batch_size=args.batch_size, limit=args.limit,
            log=lambda message: print(message, flush=True),
        )
    finally:
        await pool.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--profile", help="Model Registry profile key (default: stage route)")
    parser.add_argument("--rebuild", action="store_true", help="open a new index revision")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--limit", type=int, help="embed at most N nodes (pilot)")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args)), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
