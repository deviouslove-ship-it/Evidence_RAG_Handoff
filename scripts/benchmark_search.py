"""Synthetic Search v1 benchmark (HƯ CẤU — not legal data).

Creates a disposable PostgreSQL schema, applies migrations, seeds a synthetic
approved corpus (default 1,000 documents x 100 clauses = 100,000 nodes), then
measures SearchService latency and captures the real planner plan/config for the
phrase query.  It never forces `enable_seqscan=off`.

Usage:
    python scripts/benchmark_search.py --documents 1000 --nodes-per-document 100
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import sys
import time
from datetime import date
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import asyncpg  # noqa: E402

from app.migrations.runner import apply_migrations  # noqa: E402
from app.storage.search import (  # noqa: E402
    _BASE_SQL,
    SearchQueryError,
    SearchService,
    parse_search_query,
)
from app.storage.search_paging import document_page_sql  # noqa: E402
from app.schemas import Scope, ScopeMode  # noqa: E402
from app.vietnamese_nlp.unicode_norm import NORMALIZER_REVISION  # noqa: E402

PHRASE = "báo cáo định kỳ và thường xuyên"
AS_OF = date(2026, 10, 31)


PLANNER_SETTINGS = [
    "enable_seqscan",
    "enable_indexscan",
    "enable_bitmapscan",
    "random_page_cost",
    "seq_page_cost",
    "effective_cache_size",
    "work_mem",
    "maintenance_work_mem",
    "default_statistics_target",
    "jit",
    "max_parallel_workers_per_gather",
]


async def _seed(connection: asyncpg.Connection, docs: int, nodes: int) -> None:
    await connection.execute(
        "INSERT INTO users (id, username, display_name) VALUES ($1, 'bench', 'Bench')",
        uuid4(),
    )
    category = uuid4()
    await connection.execute(
        "INSERT INTO categories (id, name, code) VALUES ($1, 'Benchmark HƯ CẤU', 'bench-hucau')",
        category,
    )
    principal = await connection.fetchval("SELECT id FROM users WHERE username='bench'")
    await connection.execute(
        "INSERT INTO category_acl (category_id, user_id) VALUES ($1, $2)",
        category,
        principal,
    )
    await connection.execute(
        """
        INSERT INTO documents (id, doc_type, title, document_number, issuing_body)
        SELECT ('00000000-0000-0000-0000-' || lpad(i::text, 12, '0'))::uuid,
               'decree',
               'Văn bản tổng hợp HƯ CẤU số ' || i,
               'HU-CAU/2026/' || lpad(i::text, 6, '0'),
               'Cơ quan HƯ CẤU'
        FROM generate_series(1, $1) AS i
        """,
        docs,
    )
    await connection.execute(
        """
        INSERT INTO document_categories (document_id, category_id)
        SELECT id, $1 FROM documents
        """,
        category,
    )
    await connection.execute(
        """
        INSERT INTO document_versions (
          id, document_id, version_number, valid_from, original_file_path,
          original_file_sha256, original_filename, review_status,
          official_url
        )
        SELECT ('10000000-0000-0000-0000-' || lpad(i::text, 12, '0'))::uuid,
               ('00000000-0000-0000-0000-' || lpad(i::text, 12, '0'))::uuid,
               1, '2025-01-01', 'originals/' || md5(i::text) || '.pdf',
               md5('a' || i::text) || md5('b' || i::text),
               'bench.pdf', 'approved',
               'https://example.test/hu-cau/' || i
        FROM generate_series(1, $1) AS i
        """,
        docs,
    )
    await connection.execute(
        """
        INSERT INTO source_provenance (document_version_id, verified_at)
        SELECT dv.id, now() FROM document_versions dv
        """
    )
    await connection.execute(
        """
        CREATE TEMP TABLE bench_spec AS
        SELECT d.id AS document_id, dv.id AS version_id, gs.j AS idx,
               d.title, d.document_number,
               gen_random_uuid() AS page_id,
               gen_random_uuid() AS span_id,
               CASE WHEN gs.j = 1
                    THEN 'Các bộ, ngành thực hiện báo cáo định kỳ và thường xuyên theo quy định.'
                    ELSE 'Nội dung tổng hợp HƯ CẤU số ' || gs.j
                         || ' về quản lý nhà nước và cải cách hành chính.' END AS content,
               CASE WHEN gs.j = 1 THEN 'Điều 1. Báo cáo định kỳ'
                    ELSE 'Điều ' || (gs.j + 1)::text || '. Nội dung tổng hợp' END AS label
        FROM documents d
        JOIN document_versions dv ON dv.document_id = d.id
        CROSS JOIN generate_series(1, $1) AS gs(j)
        """,
        nodes,
    )
    await connection.execute(
        """
        INSERT INTO source_pages (id, document_version_id, page_number, width, height,
              extraction_method, text_quality, text_original)
        SELECT page_id, version_id, idx, 595, 842, 'native_text', 'usable', content
        FROM bench_spec
        """
    )
    await connection.execute(
        """
        INSERT INTO source_spans (id, page_id, original_offset, original_length, text_original)
        SELECT span_id, page_id, 0, length(content), content
        FROM bench_spec
        """
    )
    await connection.execute(
        """
        INSERT INTO document_nodes (
          document_id, document_version_id, node_type, label_original, path,
          text_original, text_indexed, text_normalized, text_folded,
          page_start, parse_confidence, review_status, source_span_id,
          normalization_revision
        )
        SELECT document_id, version_id, 'clause', label, 'node/' || idx,
               content,
               title || ' ' || document_number || ' ' || label || ' ' || content,
               lower(content), lower(content),
               1, 0.9, 'approved', span_id, $1
        FROM bench_spec
        """,
        NORMALIZER_REVISION,
    )
    await connection.execute("ANALYZE document_nodes")
    await connection.execute("ANALYZE documents")
    await connection.execute("ANALYZE document_versions")


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round((p / 100) * (len(ordered) - 1)))))
    return ordered[index]


def _plan_summary(node: dict, depth: int = 0) -> list[dict]:
    rows: list[dict] = []
    if depth > 12:
        return rows
    rows.append(
        {
            "depth": depth,
            "node_type": node.get("Node Type"),
            "relation": node.get("Relation Name"),
            "index": node.get("Index Name"),
            "actual_time_ms": round(float(node.get("Actual Total Time", 0.0)), 3),
            "actual_rows": node.get("Actual Rows"),
            "plan_rows": node.get("Plan Rows"),
            "loops": node.get("Actual Loops"),
        }
    )
    for child in node.get("Plans", []) or []:
        rows.extend(_plan_summary(child, depth + 1))
    return rows


async def run(args: argparse.Namespace) -> int:
    dsn = args.database_url or os.getenv("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL is required", file=sys.stderr)
        return 2
    schema = "search_bench_" + uuid4().hex
    connection = await asyncpg.connect(dsn)
    pool = None
    result: dict[str, object] = {
        "label": "HU_CAU_TONG_HOP",
        "documents": args.documents,
        "nodes_per_document": args.nodes_per_document,
        "nodes": args.documents * args.nodes_per_document,
        "phrase": PHRASE,
        "as_of_date": AS_OF.isoformat(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "iterations": args.iterations,
    }
    try:
        await connection.execute(f'CREATE SCHEMA "{schema}"')
        await connection.execute(f'SET search_path TO "{schema}", public')
        await apply_migrations(connection)
        started = time.perf_counter()
        async with connection.transaction():
            await connection.execute("SET LOCAL synchronous_commit = off")
            await _seed(connection, args.documents, args.nodes_per_document)
        result["seed_seconds"] = round(time.perf_counter() - started, 2)
        counts = await connection.fetchrow(
            "SELECT count(*) AS nodes FROM document_nodes;"
        )
        result["node_count_verified"] = int(counts["nodes"])

        pool = await asyncpg.create_pool(
            dsn,
            min_size=1,
            max_size=4,
            server_settings={"search_path": schema + ",public"},
        )
        service = SearchService(
            pool,
            statement_timeout_ms=args.statement_timeout_ms,
            audit_enabled=False,
        )
        principal = await connection.fetchval("SELECT id FROM users WHERE username='bench'")

        async def measure(query: str, mode: str = "phrase") -> list[float]:
            # Two warm-up calls, then measured calls.
            for _ in range(2):
                await service.search_documents(
                    principal_id=principal,
                    raw_query=query,
                    mode=mode,
                    as_of_date=AS_OF,
                    page_size=20,
                    include_approximate_count=False,
                )
            timings: list[float] = []
            for _ in range(args.iterations):
                tick = time.perf_counter()
                response = await service.search_documents(
                    principal_id=principal,
                    raw_query=query,
                    mode=mode,
                    as_of_date=AS_OF,
                    page_size=20,
                    include_approximate_count=False,
                )
                timings.append((time.perf_counter() - tick) * 1000)
                if not response.results:
                    break
            return timings

        phrase_timings = await measure(f'"{PHRASE}"', "phrase")
        keyword_timings = await measure("báo cáo định kỳ", "keywords")
        empty_timings = await measure('"không có cụm từ này"', "phrase")
        api_default: dict[str, object] = {}
        try:
            tick = time.perf_counter()
            default_response = await service.search_documents(
                principal_id=principal,
                raw_query=f'"{PHRASE}"',
                mode="phrase",
                as_of_date=AS_OF,
                page_size=20,
            )
            api_default = {
                "latency_ms": round((time.perf_counter() - tick) * 1000, 2),
                "documents": default_response.totals.documents,
                "approximate_hidden": default_response.totals.approximate_matches_hidden,
            }
        except Exception as exc:  # record timeout/error instead of hiding it
            api_default = {"error": type(exc).__name__}
        result["api_default_call"] = api_default
        chat_timings = []
        for _ in range(5):
            tick = time.perf_counter()
            chat_result = await service.search_clauses(
                principal_id=principal,
                scope=Scope(scope_mode=ScopeMode.ALL_AUTHORIZED, as_of_date=AS_OF),
                query="báo cáo định kỳ", limit=12,
            )
            chat_timings.append((time.perf_counter() - tick) * 1000)
        result["chat_retrieval"] = {
            "p50_ms": round(_percentile(chat_timings, 50), 2),
            "p95_ms": round(_percentile(chat_timings, 95), 2),
            "samples": len(chat_timings), "evidence_count": len(chat_result),
        }
        if args.concurrency:
            gaps: list[float] = []
            stop = asyncio.Event()

            async def heartbeat() -> None:
                previous = time.perf_counter()
                while not stop.is_set():
                    await asyncio.sleep(0.01)
                    current = time.perf_counter()
                    gaps.append((current - previous) * 1000)
                    previous = current

            async def concurrent_search() -> dict[str, object]:
                tick = time.perf_counter()
                code = "ok"
                try:
                    await service.search_documents(
                        principal_id=principal, raw_query=f'"{PHRASE}"', as_of_date=AS_OF,
                    )
                except SearchQueryError as exc:
                    code = exc.code
                return {"code": code, "latency_ms": round((time.perf_counter() - tick) * 1000, 2)}

            pulse = asyncio.create_task(heartbeat())
            try:
                calls = await asyncio.gather(*(
                    concurrent_search() for _ in range(args.concurrency)
                ))
            finally:
                stop.set()
                await pulse
            result["concurrency"] = {
                "requests": args.concurrency, "results": calls,
                "event_loop_max_gap_ms": round(max(gaps, default=0), 2),
                "available_search_slots_after": service._search_slots._value,
                "database_responsive_after": await connection.fetchval("SELECT 1") == 1,
            }
        result["latency_ms"] = {
            "phrase": {
                "p50": round(_percentile(phrase_timings, 50), 2),
                "p95": round(_percentile(phrase_timings, 95), 2),
                "min": round(min(phrase_timings), 2),
                "max": round(max(phrase_timings), 2),
                "samples": len(phrase_timings),
            },
            "keywords": {
                "p50": round(_percentile(keyword_timings, 50), 2),
                "p95": round(_percentile(keyword_timings, 95), 2),
                "samples": len(keyword_timings),
            },
            "empty": {
                "p50": round(_percentile(empty_timings, 50), 2),
                "p95": round(_percentile(empty_timings, 95), 2),
                "samples": len(empty_timings),
            },
            "target_p95_ms": 300,
        }

        settings = await connection.fetch(
            "SELECT name, setting, unit FROM pg_settings WHERE name = ANY($1::text[])",
            PLANNER_SETTINGS,
        )
        result["planner_settings"] = {
            row["name"]: {"setting": row["setting"], "unit": row["unit"]}
            for row in settings
        }

        parsed = parse_search_query(f'"{PHRASE}"', "phrase")
        async with pool.acquire() as check:
            async with check.transaction():
                await check.execute("SELECT set_config('app.user_id', $1, true)", str(principal))
                allowed = [
                    row["document_id"]
                    for row in await check.fetch(
                        "SELECT DISTINCT document_id FROM authorized_nodes"
                    )
                ]
                params = service._params(
                    parsed=parsed,
                    category_ids=None,
                    doc_types=None,
                    issuing_body=None,
                    as_of_date=AS_OF,
                    only_active=False,
                    limit=50,
                    terms_array=list(parsed.terms),
                    version_ids=await service._selected_version_ids(check, allowed, AS_OF),
                )
                explain_rows = await check.fetch(
                    "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) "
                    + document_page_sql(_BASE_SQL, "phrase"),
                    *params, "", 1, 20, 1, 5, parsed.phrase_folded,
                )
                plan = json.loads(explain_rows[0][0])[0]
        result["plan"] = {
            "execution_time_ms": round(float(plan.get("Execution Time", 0.0)), 3),
            "planning_time_ms": round(float(plan.get("Planning Time", 0.0)), 3),
            "planning_settings_forced_off": False,
            "nodes": _plan_summary(plan["Plan"]),
        }
        result["plan"]["uses_document_nodes_search_word_gin"] = any(
            node.get("index") == "document_nodes_search_word_gin"
            for node in result["plan"]["nodes"]
        )
        result["approximate_count_limit"] = service._approximate_count_limit
        return_code = 0
    finally:
        if pool is not None:
            await pool.close()
        await connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await connection.close()

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "benchmark.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    lines = [
        "# Search v1 synthetic benchmark (HƯ CẤU)",
        "",
        f"- Dataset: {result['documents']} documents x {result['nodes_per_document']} nodes = {result['nodes']} nodes",
        f"- Verified node count: {result['node_count_verified']}",
        f"- Seed time: {result['seed_seconds']} s",
        f"- Phrase p50/p95: {result['latency_ms']['phrase']['p50']} / {result['latency_ms']['phrase']['p95']} ms",
        f"- Keywords p50/p95: {result['latency_ms']['keywords']['p50']} / {result['latency_ms']['keywords']['p95']} ms",
        f"- Empty p50/p95: {result['latency_ms']['empty']['p50']} / {result['latency_ms']['empty']['p95']} ms",
        f"- API default call (approximate count capped at {result['approximate_count_limit']}): {result['api_default_call']}",
        "- Target p95 (tạm, chưa chốt): 300 ms — chỉ có hiệu lực trên máy Windows đích.",
        f"- Synthetic target verdict: phrase p95 = {result['latency_ms']['phrase']['p95']} ms "
        f"({'meets' if result['latency_ms']['phrase']['p95'] <= 300 else 'exceeds'} the provisional 300 ms target).",
        "- `enable_seqscan` is left at its default; no seqscan was forced off.",
        "",
        "## Planner settings",
        "",
        "| Setting | Value |",
        "|---|---|",
    ]
    for name, value in result["planner_settings"].items():
        lines.append(f"| {name} | {value['setting']} {value['unit'] or ''} |")
    lines += [
        "",
        "## Phrase query plan (EXPLAIN ANALYZE)",
        "",
        f"- Execution: {result['plan']['execution_time_ms']} ms; planning: {result['plan']['planning_time_ms']} ms",
        f"- `document_nodes_search_word_gin` in plan: {result['plan']['uses_document_nodes_search_word_gin']}",
        "",
        "| Depth | Node | Relation | Index | Actual time (ms) | Actual rows | Loops |",
        "|---|---|---|---|---|---|---|",
    ]
    for node in result["plan"]["nodes"]:
        lines.append(
            "| {depth} | {node_type} | {relation} | {index} | {actual_time_ms} | "
            "{actual_rows} | {loops} |".format(**node)
        )
    lines += [
        "",
        "Dữ liệu sinh tổng hợp, không phải văn bản pháp luật; không dùng số này để tuyên bố chất lượng search.",
        "",
    ]
    (output / "benchmark.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2)[:4000])
    return return_code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--documents", type=int, default=1000)
    parser.add_argument("--nodes-per-document", type=int, default=100)
    parser.add_argument("--iterations", type=int, default=15)
    parser.add_argument("--concurrency", type=int, choices=range(0, 65), default=0)
    parser.add_argument("--statement-timeout-ms", type=int, default=120000)
    parser.add_argument(
        "--output",
        default=str(ROOT / "docs" / "evidence" / "2026-10-31-search-v1" / "benchmark"),
    )
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
