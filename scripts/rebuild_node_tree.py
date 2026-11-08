"""Rebuild the clause tree of unapproved document versions from their stored page text.

    python scripts/rebuild_node_tree.py            # dry-run: report only, writes nothing
    python scripts/rebuild_node_tree.py --apply    # rebuild drafts and versions pending review

Versions imported before page text was stored (migration 0003) are re-extracted from the
original PDF when EVIDENCE_DOCUMENT_STORE_ROOT is set.

Uses the page text already in the database (no PDF re-extraction).  For each version it
re-runs the parser, then writes parent links (Chương → Mục → Điều → Khoản → Điểm),
citation labels and page-by-page source spans.  Approved versions are never touched:
their nodes are what reviewers approved.  The database comes from DATABASE_URL, as for
the other scripts; nothing else is configured here.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.audit import append_audit  # noqa: E402
from app.documents.draft import prepare_draft  # noqa: E402
from app.documents.draft_read import load_draft_pdf  # noqa: E402
from app.documents.native_pdf import ExtractedPage  # noqa: E402
from app.documents.node_writer import (  # noqa: E402
    anchor_nodes,
    delete_version_nodes,
    write_nodes,
)
from app.documents.reextract import apply_reextracted_draft  # noqa: E402
from app.documents.tree_parser import parse_legal_tree  # noqa: E402
from app.migrations.runner import apply_migrations  # noqa: E402
from app.storage.postgres import create_pool  # noqa: E402

_MAX_BYTES = int(os.environ.get("EVIDENCE_MAX_UPLOAD_BYTES", str(32 * 1024 * 1024)))
_MAX_PAGES = 1000


async def _pages(conn: Any, version_id: UUID) -> list[Any]:
    return list(await conn.fetch(
        """SELECT id, page_number, width, height, rotation, extraction_method,
                  text_quality, text_original, extraction_error
           FROM source_pages WHERE document_version_id=$1 ORDER BY page_number""",
        version_id,
    ))


def _extracted(rows: list[Any]) -> list[ExtractedPage]:
    return [
        ExtractedPage(
            page_number=row["page_number"], width=float(row["width"]),
            height=float(row["height"]), rotation=int(row["rotation"]),
            text=row["text_original"] or "", character_boxes=(),
            extraction_method=row["extraction_method"], text_quality=row["text_quality"],
            extraction_error=row["extraction_error"],
        )
        for row in rows
    ]


async def _reextract(pool: Any, version: Any, store_root: Path) -> dict[str, Any]:
    async with pool.acquire() as conn:
        curator = await conn.fetchval(
            """SELECT COALESCE(dv.submitted_by, (
                 SELECT u.id FROM users u JOIN user_roles r ON r.user_id = u.id
                 WHERE r.role_code = 'CURATOR' AND u.disabled_at IS NULL ORDER BY u.id LIMIT 1))
               FROM document_versions dv WHERE dv.id = $1""",
            version["id"],
        )
    if curator is None:
        return {"action": "skipped_no_curator"}
    try:
        content = await load_draft_pdf(
            pool, store_root=store_root, version_id=version["id"], max_bytes=_MAX_BYTES,
        )
        prepared = await asyncio.to_thread(
            prepare_draft, content, max_pages=_MAX_PAGES, temporary_root=store_root,
            isolate=True, timeout_seconds=300,
        )
        result = await apply_reextracted_draft(
            pool, prepared=prepared, version_id=version["id"], curator_id=curator,
        )
    except Exception as exc:  # report and continue with the next version
        return {"action": "reextract_failed", "detail": (str(exc) or type(exc).__name__)[:200]}
    return {"action": "reextracted", "nodes_after": len(prepared.nodes),
            "unanchored_after": int(result["nodes_unresolved"])}


async def run(apply: bool, only: set[str]) -> dict[str, Any]:
    pool = await create_pool(os.environ["DATABASE_URL"])
    store_value = os.environ.get("EVIDENCE_DOCUMENT_STORE_ROOT")
    store_root = Path(store_value) if store_value and Path(store_value).is_absolute() else None
    report: dict[str, Any] = {"mode": "apply" if apply else "dry-run", "versions": []}
    try:
        async with pool.acquire() as conn:
            await apply_migrations(conn)
            versions = await conn.fetch(
                """SELECT dv.id, dv.review_status::text AS status, d.id AS document_id,
                          d.title, d.document_number, dv.original_filename,
                          (SELECT count(*) FROM document_nodes n
                           WHERE n.document_version_id = dv.id) AS nodes,
                          (SELECT count(*) FROM document_nodes n
                           WHERE n.document_version_id = dv.id
                             AND NOT node_source_text_valid(n.id)) AS unanchored
                   FROM document_versions dv JOIN documents d ON d.id = dv.document_id
                   WHERE d.deleted_at IS NULL ORDER BY dv.captured_at NULLS LAST, dv.id""",
            )
        for version in versions:
            entry: dict[str, Any] = {
                "version_id": str(version["id"]), "file": version["original_filename"],
                "status": version["status"], "nodes_before": int(version["nodes"]),
                "unanchored_before": int(version["unanchored"]),
            }
            if only and str(version["id"]) not in only:
                continue
            if version["status"] not in {"draft", "pending_review"}:
                entry["action"] = "skipped_not_editable"
                report["versions"].append(entry)
                continue
            async with pool.acquire() as conn:
                rows = await _pages(conn, version["id"])
            pages = _extracted(rows)
            if any(row["text_original"] is None for row in rows):
                # Legacy rows (before migration 0003) kept no page text: read the
                # stored original PDF again, as the curator "re-extract" action does.
                if store_root is None:
                    entry["action"] = "skipped_page_text_missing"
                elif not apply:
                    entry["action"] = "would_reextract_from_pdf"
                else:
                    entry.update(await _reextract(pool, version, store_root))
                report["versions"].append(entry)
                continue
            nodes = parse_legal_tree(pages)
            page_texts = {page.page_number: page.text for page in pages}
            anchors = anchor_nodes(page_texts, nodes)
            entry.update(
                nodes_after=len(nodes),
                unanchored_after=sum(anchor is None for anchor in anchors),
                multi_page_after=sum(
                    anchor is not None and len(anchor) > 1 for anchor in anchors
                ),
            )
            if not apply:
                entry["action"] = "would_rebuild"
                report["versions"].append(entry)
                continue
            async with pool.acquire() as conn, conn.transaction():
                await conn.fetchval(
                    "SELECT id FROM document_versions WHERE id=$1 FOR UPDATE", version["id"],
                )
                await delete_version_nodes(conn, version["id"])
                _, unanchored = await write_nodes(
                    conn, document_id=version["document_id"], version_id=version["id"],
                    title=version["title"], document_number=version["document_number"],
                    page_ids={row["page_number"]: row["id"] for row in rows},
                    page_texts=page_texts, nodes=nodes,
                )
                await conn.execute(
                    "UPDATE document_versions SET source_review_revision="
                    "source_review_revision+1 WHERE id=$1", version["id"],
                )
                await conn.execute(
                    "UPDATE source_provenance SET verified_at=NULL WHERE document_version_id=$1",
                    version["id"],
                )
                if unanchored:
                    await conn.execute(
                        """INSERT INTO curator_review_tasks (document_version_id, reason, risk)
                           SELECT $1, 'unanchored_source_spans', 'high' WHERE NOT EXISTS (
                             SELECT 1 FROM curator_review_tasks WHERE document_version_id=$1
                               AND reason='unanchored_source_spans' AND status='open')""",
                        version["id"],
                    )
                else:
                    # The condition the task reported no longer exists.
                    await conn.execute(
                        """UPDATE curator_review_tasks SET status='resolved', resolved_at=now(),
                             resolution_note='Dựng lại cây: mọi khoản đã neo được vào trang nguồn.'
                           WHERE document_version_id=$1 AND reason='unanchored_source_spans'
                             AND status='open'""",
                        version["id"],
                    )
                await append_audit(
                    conn, principal_id=None, action="maintenance.rebuild_node_tree",
                    target_type="document_version", target_id=str(version["id"]),
                    metadata={"nodes": len(nodes), "unanchored": unanchored},
                )
            entry["action"] = "rebuilt"
            report["versions"].append(entry)
    finally:
        await pool.close()
    done = report["versions"]
    report["summary"] = {
        "versions": len(done),
        "unanchored_before": sum(v["unanchored_before"] for v in done),
        "unanchored_after": sum(v.get("unanchored_after", 0) for v in done),
        "skipped": sum(v["action"].startswith("skipped") for v in done),
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true", help="write the rebuilt trees")
    parser.add_argument("--version", action="append", default=[],
                        help="limit to this document_version id (repeatable)")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.apply, set(args.version))),
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
