"""Compare a database with a copy restored from its pg_dump (rows, vectors, indexes).

    SOURCE_DATABASE_URL=... RESTORED_DATABASE_URL=... python scripts/verify_db_restore.py --out report.json

Read-only on both databases.  Checks, and exits non-zero when any fails:

* every public table has the same number of rows;
* the same checksum of document text and of every vector (node_embeddings);
* the same set of indexes, all valid, including the HNSW index of the active embedding index;
* the restored HNSW index answers a nearest-neighbour query (the plan uses it) and returns
  the same nearest neighbours as the source for a few stored vectors.

Connection strings come from the environment; nothing is hard-coded.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import asyncpg

SAMPLES = 5


async def tables(connection: Any) -> dict[str, int]:
    names = [row["tablename"] for row in await connection.fetch(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1")]
    return {name: int(await connection.fetchval(f'SELECT count(*) FROM "{name}"')) for name in names}


async def checksums(connection: Any) -> dict[str, str | None]:
    return {
        "document_text": await connection.fetchval(
            """SELECT md5(string_agg(md5(id::text || text_original), '' ORDER BY id))
               FROM document_nodes"""),
        "vectors": await connection.fetchval(
            """SELECT md5(string_agg(md5(embedding_index_id::text || document_node_id::text
                                          || embedding::text), '' ORDER BY embedding_index_id,
                                                                         document_node_id))
               FROM node_embeddings"""),
    }


async def indexes(connection: Any) -> dict[str, bool]:
    rows = await connection.fetch(
        """SELECT c.relname AS name, i.indisvalid AS valid
           FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
           JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public'""")
    return {row["name"]: bool(row["valid"]) for row in rows}


async def neighbours(connection: Any, index: Any, node_ids: list[str]) -> dict[str, Any]:
    dim = int(index["dimensions"])
    out: dict[str, Any] = {}
    plan_uses_hnsw = None
    async with connection.transaction():
        await connection.execute("SET LOCAL enable_seqscan = off")
        for node_id in node_ids:
            vector = await connection.fetchval(
                "SELECT embedding::text FROM node_embeddings WHERE document_node_id = $1::uuid"
                " AND embedding_index_id = $2", node_id, index["id"])
            sql = f"""SELECT document_node_id::text FROM node_embeddings
                      WHERE embedding_index_id = $2
                      ORDER BY embedding::vector({dim}) <=> $1::vector({dim}) LIMIT 5"""
            out[node_id] = [row[0] for row in await connection.fetch(sql, vector, index["id"])]
            if plan_uses_hnsw is None:
                plan = await connection.fetch("EXPLAIN " + sql, vector, index["id"])
                plan_uses_hnsw = any("hnsw" in row[0].lower() for row in plan)
    return {"neighbours": out, "plan_uses_hnsw": plan_uses_hnsw}


async def main_async(args: argparse.Namespace) -> dict[str, Any]:
    source = await asyncpg.connect(os.environ["SOURCE_DATABASE_URL"])
    restored = await asyncpg.connect(os.environ["RESTORED_DATABASE_URL"])
    report: dict[str, Any] = {}
    try:
        t_src, t_res = await tables(source), await tables(restored)
        report["tables"] = {"count": len(t_src), "rows_total": sum(t_src.values()),
                            "identical_row_counts": t_src == t_res,
                            "differences": {k: [t_src.get(k), t_res.get(k)]
                                            for k in set(t_src) | set(t_res)
                                            if t_src.get(k) != t_res.get(k)}}
        report["key_tables"] = {k: t_src.get(k) for k in (
            "documents", "document_versions", "document_nodes", "node_embeddings",
            "embedding_indices", "model_profiles") if k in t_src}
        c_src, c_res = await checksums(source), await checksums(restored)
        report["checksums"] = {"source": c_src, "restored": c_res, "identical": c_src == c_res}
        i_src, i_res = await indexes(source), await indexes(restored)
        report["indexes"] = {"count": len(i_src), "identical_names": set(i_src) == set(i_res),
                             "all_valid_in_restored": all(i_res.values()),
                             "missing_in_restored": sorted(set(i_src) - set(i_res)),
                             "hnsw": sorted(name for name in i_res if "hnsw" in name)}
        index = await restored.fetchrow(
            "SELECT id, dimensions, node_count, status, is_active FROM embedding_indices"
            " WHERE is_active AND status = 'ready'")
        report["active_embedding_index"] = (
            {"id": str(index["id"]), "dimensions": index["dimensions"],
             "node_count": index["node_count"]} if index else None)
        if index is not None:
            ids = [row[0] for row in await source.fetch(
                """SELECT document_node_id::text FROM node_embeddings WHERE embedding_index_id = $1
                   ORDER BY md5(document_node_id::text) LIMIT $2""", index["id"], SAMPLES)]
            n_src = await neighbours(source, index, ids)
            n_res = await neighbours(restored, index, ids)
            report["nearest_neighbours"] = {
                "samples": len(ids), "identical": n_src["neighbours"] == n_res["neighbours"],
                "restored_plan_uses_hnsw": n_res["plan_uses_hnsw"],
                "source_plan_uses_hnsw": n_src["plan_uses_hnsw"]}
    finally:
        await source.close()
        await restored.close()
    nn = report.get("nearest_neighbours", {})
    report["passed"] = bool(
        report["tables"]["identical_row_counts"] and report["checksums"]["identical"]
        and report["indexes"]["identical_names"] and report["indexes"]["all_valid_in_restored"]
        and nn.get("identical") and nn.get("restored_plan_uses_hnsw"))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    report = asyncio.run(main_async(args))
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    sys.exit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
