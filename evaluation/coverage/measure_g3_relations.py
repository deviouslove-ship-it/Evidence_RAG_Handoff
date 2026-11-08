"""Precision/recall of the G3 rule reader against g3_relations_reference.json.

    python evaluation/coverage/measure_g3_relations.py [--out report.json]

Reads node-level proposals from DATABASE_URL (any review state except rejected or
superseded) for the source documents listed in the reference file.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from pathlib import Path

import asyncpg

HERE = Path(__file__).resolve().parent


def norm(path: str) -> str:
    return re.sub(r"\s+", " ", path.strip().lower())


async def run(out: str | None) -> dict[str, object]:
    reference = json.loads((HERE / "g3_relations_reference.json").read_text(encoding="utf-8"))
    expected = {(r["source"], r["target"], r["action"], norm(r["path"]))
                for r in reference["relations"]}
    sources = sorted({item[0] for item in expected})
    targets = {item[1] for item in expected}
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        rows = await conn.fetch(
            """SELECT sd.document_number AS source, td.document_number AS target, a.action,
                      a.target_path, a.target_node_id IS NOT NULL AS node_matched
               FROM node_amendments a
               JOIN documents sd ON sd.id = a.source_document_id
               LEFT JOIN documents td ON td.id = a.target_document_id
               WHERE a.scope = 'node' AND a.superseded_by IS NULL
                 AND a.review_status <> 'rejected' AND sd.document_number = ANY($1::text[])""",
            sources,
        )
    finally:
        await conn.close()
    found = {(r["source"], r["target"], r["action"], norm(r["target_path"] or ""))
             for r in rows if r["target"] in targets}
    matched = expected & found
    node_matched = sum(1 for r in rows if r["target"] in targets and r["node_matched"])
    report = {
        "reference_relations": len(expected),
        "extracted_relations": len(found),
        "correct": len(matched),
        "precision": round(len(matched) / len(found), 3) if found else None,
        "recall": round(len(matched) / len(expected), 3) if expected else None,
        "extracted_with_node_matched": node_matched,
        "missed": sorted(" | ".join(item) for item in expected - found),
        "unexpected": sorted(" | ".join(item) for item in found - expected),
        "note": reference["description"],
    }
    if out:
        Path(out).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out")
    print(json.dumps(asyncio.run(run(parser.parse_args().out)), ensure_ascii=False, indent=1))
