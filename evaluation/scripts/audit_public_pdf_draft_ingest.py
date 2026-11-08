"""Import the public test corpus into a disposable PostgreSQL schema as drafts."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import asyncpg

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.documents.draft import persist_draft, prepare_draft  # noqa: E402
from app.documents.provenance import sha256_bytes  # noqa: E402
from app.migrations.runner import apply_migrations  # noqa: E402


async def audit(manifest_path: Path, store_base: Path, dsn: str) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = manifest["documents"]
    if not 10 <= len(entries) <= 20:
        raise ValueError("TEST_CORPUS_COUNT_OUT_OF_RANGE")
    store_base = store_base.resolve()
    store_base.mkdir(parents=True, exist_ok=True)
    test_store = (store_base / ("draft-smoke-" + uuid4().hex)).resolve()
    if test_store.parent != store_base:
        raise ValueError("UNSAFE_TEST_STORE")
    test_store.mkdir()
    schema = "test_draft_corpus_" + uuid4().hex
    connection = await asyncpg.connect(dsn)
    pool = None
    started = perf_counter()
    try:
        await connection.execute(f'CREATE SCHEMA "{schema}"')
        await connection.execute(f'SET search_path TO "{schema}", public')
        await apply_migrations(connection)
        pool = await asyncpg.create_pool(
            dsn, min_size=1, max_size=1,
            server_settings={"search_path": schema + ",public"},
        )
        principal_id, category_id = uuid4(), uuid4()
        await connection.execute(
            "INSERT INTO users (id, username, display_name) VALUES ($1, 'tester', 'Tester')",
            principal_id,
        )
        await connection.execute(
            "INSERT INTO categories (id, name, code) VALUES ($1, 'Test', 'test')",
            category_id,
        )
        await connection.execute(
            "INSERT INTO category_acl (category_id, user_id) VALUES ($1, $2)",
            category_id, principal_id,
        )

        result_rows: list[dict[str, object]] = []
        for entry in entries:
            source = (manifest_path.parent / entry["local_file"]).resolve()
            if not source.is_relative_to(manifest_path.parent.resolve()) or not source.is_file():
                raise ValueError("MISSING_OR_UNSAFE_LOCAL_FILE")
            content = source.read_bytes()
            if sha256_bytes(content) != entry["sha256"] or len(content) != entry["size_bytes"]:
                raise ValueError("CORPUS_INTEGRITY_MISMATCH")
            file_started = perf_counter()
            prepared = await asyncio.to_thread(
                prepare_draft, content, max_pages=200, temporary_root=test_store,
                isolate=True, timeout_seconds=120,
            )
            response = await persist_draft(
                prepared, pool=pool, store_root=test_store,
                title=entry["title"], doc_type="decree",
                original_filename=source.name,
                document_number=entry["document_number"],
                official_url=entry["pdf_url"],
            )
            if response.sha256 != entry["sha256"]:
                raise ValueError("DRAFT_HASH_MISMATCH")
            await connection.execute(
                "INSERT INTO document_categories (document_id, category_id) VALUES ($1, $2)",
                response.document_id, category_id,
            )
            result_rows.append({
                "document_number": entry["document_number"],
                "page_count": response.page_count,
                "node_count": response.node_count,
                "review_required_pages": response.review_required_pages,
                "status": response.status,
                "elapsed_seconds": round(perf_counter() - file_started, 3),
            })
        await connection.execute("SELECT set_config('app.user_id', $1, false)", str(principal_id))
        counts = await connection.fetchrow(
            """SELECT
                 (SELECT count(*) FROM documents) AS documents,
                 (SELECT count(*) FROM document_versions WHERE review_status = 'draft') AS drafts,
                 (SELECT count(*) FROM source_pages) AS pages,
                 (SELECT count(*) FROM source_spans) AS spans,
                 (SELECT count(*) FROM document_nodes WHERE review_status = 'draft') AS nodes,
                 (SELECT count(*) FROM document_nodes WHERE source_span_id IS NOT NULL)
                   AS nodes_with_exact_text_span,
                 (SELECT count(*) FROM curator_review_tasks WHERE status = 'open') AS tasks,
                 (SELECT count(*) FROM authorized_nodes) AS authorized_nodes"""
        )
        assert counts is not None
        if counts["documents"] != len(entries) or counts["drafts"] != len(entries):
            raise ValueError("DRAFT_COUNT_MISMATCH")
        if counts["authorized_nodes"] != 0:
            raise ValueError("DRAFT_LEAKED_INTO_RETRIEVAL")
        if counts["pages"] != sum(int(row["page_count"]) for row in result_rows):
            raise ValueError("DRAFT_PAGE_COUNT_MISMATCH")
        if counts["nodes"] != sum(int(row["node_count"]) for row in result_rows):
            raise ValueError("DRAFT_NODE_COUNT_MISMATCH")
        return {
            "purpose": "Disposable draft-ingest test; no source approval or legal assertion",
            "tested_at_utc": datetime.now(UTC).isoformat(),
            "document_count": counts["documents"],
            "draft_count": counts["drafts"],
            "page_count": counts["pages"],
            "source_span_count": counts["spans"],
            "node_count": counts["nodes"],
            "nodes_with_exact_text_span": counts["nodes_with_exact_text_span"],
            "open_review_tasks": counts["tasks"],
            "authorized_nodes_visible": counts["authorized_nodes"],
            "test_store_cleaned": True,
            "test_schema_dropped": True,
            "isolated_pdf_process": True,
            "elapsed_seconds": round(perf_counter() - started, 3),
            "documents": result_rows,
        }
    finally:
        if pool is not None:
            await pool.close()
        await connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await connection.close()
        if test_store.parent != store_base or not test_store.name.startswith("draft-smoke-"):
            raise ValueError("UNSAFE_TEST_STORE_CLEANUP")
        shutil.rmtree(test_store)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path,
        default=PROJECT_ROOT / "evaluation" / "corpus_public_real" / "manifest.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    dsn = os.environ.get("EVIDENCE_TEST_DATABASE_URL")
    store = os.environ.get("EVIDENCE_TEST_DOCUMENT_STORE_ROOT")
    if not dsn or not store:
        parser.error("EVIDENCE_TEST_DATABASE_URL and EVIDENCE_TEST_DOCUMENT_STORE_ROOT required")
    result = asyncio.run(audit(args.manifest.resolve(), Path(store), dsn))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
