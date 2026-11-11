"""End-to-end check of node-scoped relations on a disposable PostgreSQL database.

Skipped unless ``EVIDENCE_TEST_DATABASE_URL`` points at a database where a throw-away
schema may be created (the schema is dropped at the end).  Fixture texts are HƯ CẤU.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import pytest

DSN = os.environ.get("EVIDENCE_TEST_DATABASE_URL")
TARGET_NUMBER = "12/2020/TT-BCA"
SOURCE_NUMBER = "99/2026/TT-BCA"
TT = f"Thông tư số {TARGET_NUMBER}"


async def _node(
    connection: asyncpg.Connection, doc: UUID, version: UUID, kind: str, path: str,
    text: str, parent: UUID | None = None,
) -> UUID:
    node = await connection.fetchval(
        """INSERT INTO document_nodes (document_id, document_version_id, node_type, path,
             text_original, text_indexed, text_normalized, text_folded, parse_confidence,
             review_status, parent_id)
           VALUES ($1, $2, $3, $4, $5, '', '', '', 0.9, 'approved', $6) RETURNING id""",
        doc, version, kind, path, text, parent,
    )
    assert isinstance(node, UUID)
    return node


@pytest.mark.skipif(not DSN, reason="No disposable PostgreSQL test database configured")
async def test_node_scoped_relations_end_to_end() -> None:
    from app.effectivity.service import EffectivityError, review_proposals
    from app.effectivity.store import extract_version_relations, load_effectivity

    assert DSN
    schema = "test_scope_" + uuid4().hex
    connection = await asyncpg.connect(DSN)
    pool: asyncpg.Pool | None = None
    try:
        await connection.execute(f'CREATE SCHEMA "{schema}"')
        await connection.execute(f'SET search_path TO "{schema}", public')
        migrations = Path(__file__).resolve().parents[1] / "app" / "migrations"
        for path in sorted(migrations.glob("*.sql")):
            if not path.name.endswith(".down.sql"):
                await connection.execute(path.read_text(encoding="utf-8"))
        reviewer, category = uuid4(), uuid4()
        await connection.execute(
            "INSERT INTO users (id, username, display_name) VALUES ($1, 'rv', 'rv')", reviewer
        )
        await connection.execute(
            "INSERT INTO categories (id, name, code) VALUES ($1, 'HƯ CẤU', 'hc')", category
        )
        await connection.execute(
            "INSERT INTO category_acl (category_id, user_id, can_query, can_review)"
            " VALUES ($1, $2, TRUE, TRUE)", category, reviewer,
        )
        ids: dict[str, tuple[UUID, UUID]] = {}
        for number, effective in ((TARGET_NUMBER, "2020-03-01"), (SOURCE_NUMBER, "2026-07-01")):
            doc, version = uuid4(), uuid4()
            ids[number] = (doc, version)
            await connection.execute(
                "INSERT INTO documents (id, doc_type, title, document_number)"
                " VALUES ($1, 'circular', 'Thông tư HƯ CẤU', $2)", doc, number,
            )
            await connection.execute("INSERT INTO document_categories VALUES ($1, $2)",
                                     doc, category)
            await connection.execute(
                """INSERT INTO document_versions (id, document_id, version_number,
                     original_file_path, original_file_sha256, original_filename,
                     review_status, effective_from)
                   VALUES ($1, $2, 1, 'x.pdf', $3, 'x.pdf', 'approved', $4::date)""",
                version, doc, uuid4().hex + uuid4().hex, date.fromisoformat(effective),
            )
        target, target_version = ids[TARGET_NUMBER]
        source, source_version = ids[SOURCE_NUMBER]
        # The amended document: Điều 3, Điều 4 (khoản 2), Điều 5.
        n3 = await _node(connection, target, target_version, "article", "000003:dieu:3",
                         "Điều 3. HƯ CẤU")
        n4 = await _node(connection, target, target_version, "article", "000004:dieu:4",
                         "Điều 4. HƯ CẤU")
        k2 = await _node(connection, target, target_version, "clause",
                         "000004:dieu:4/khoan:2", "2. HƯ CẤU", parent=n4)
        n5 = await _node(connection, target, target_version, "article", "000005:dieu:5",
                         "Điều 5. HƯ CẤU")
        # The amending document.
        await _node(connection, source, source_version, "article", "000001:dieu:1",
                    "Điều 1. Điều 1 và Điều 2 của Thông tư này thay thế Điều 3 và Điều 4 "
                    f"của {TT}.")
        await _node(connection, source, source_version, "article", "000002:dieu:2",
                    f"Điều 2. Thông tư này thay thế một phần {TT}.")
        await _node(connection, source, source_version, "article", "000003:dieu:3",
                    f"Điều 3. Bãi bỏ Điều 5 của {TT}.")
        await _node(connection, source, source_version, "article", "000004:dieu:4",
                    f"Điều 4. Sửa đổi khoản 2 Điều 4 của {TT}.")
        heading = await _node(
            connection, source, source_version, "article", "000005:dieu:5",
            f"Điều 5. Sửa đổi, bổ sung một số điều của {TT}",
        )
        await _node(
            connection, source, source_version, "clause", "000005:dieu:5/khoan:1",
            "1. Sửa đổi khoản 2 Điều 4 kể từ ngày 01 tháng 01 năm 2027 như sau: mới.",
            parent=heading,
        )

        await extract_version_relations(connection, source_version)
        rows = await connection.fetch(
            """SELECT id, scope, action, target_path, target_node_id, target_document_id,
                      valid_from, extraction_key
               FROM node_amendments WHERE source_document_id = $1""",
            source,
        )

        def pick(action: str, path: str | None) -> list[asyncpg.Record]:
            return [r for r in rows if r["action"] == action and r["target_path"] == path]

        # Item 3: one relation per unit, each matched to its own node.
        (replace_3,) = pick("replace", "Điều 3")
        (replace_4,) = pick("replace", "Điều 4")
        assert (replace_3["scope"], replace_3["target_node_id"]) == ("node", n3)
        assert (replace_4["scope"], replace_4["target_node_id"]) == ("node", n4)
        # Item 4: partial replacement with no unit named -> node scope, empty target.
        (partial,) = (r for r in rows if r["action"] == "replace" and r["target_path"] is None)
        assert (partial["scope"], partial["target_node_id"]) == ("node", None)
        assert partial["target_document_id"] == target
        # Item 2: named units make modify / repeal_partial node-scoped and matched.
        (repeal_5,) = pick("repeal_partial", "Điều 5")
        assert (repeal_5["scope"], repeal_5["target_node_id"]) == ("node", n5)
        modify_rows = pick("modify", "khoản 2 Điều 4")
        assert modify_rows and {r["scope"] for r in modify_rows} == {"node"}
        assert {r["target_node_id"] for r in modify_rows} == {k2}
        # Item 1: the item's own date, not the document's.
        (item_row,) = (r for r in modify_rows if r["extraction_key"].startswith("node|"))
        assert item_row["valid_from"] == date(2027, 1, 1)
        sentence_row = next(r for r in modify_rows if not r["extraction_key"].startswith("node|"))
        assert sentence_row["valid_from"] == date(2026, 7, 1)

        pool = await asyncpg.create_pool(
            DSN, min_size=1, max_size=2, server_settings={"search_path": f"{schema},public"}
        )
        # The reviewer must choose the target node before approving the partial replacement.
        with pytest.raises(EffectivityError, match="RELATION_TARGET_REQUIRED"):
            await review_proposals(pool, reviewer_id=reviewer, note="x", decisions=[
                {"relation_id": partial["id"], "decision": "approve"}])
        await review_proposals(pool, reviewer_id=reviewer, note="Duyệt HƯ CẤU", decisions=[
            {"relation_id": repeal_5["id"], "decision": "approve"},
            {"relation_id": sentence_row["id"], "decision": "approve"},
        ])
        async with pool.acquire() as conn:
            _, nodes, _ = await load_effectivity(
                conn, document_ids=[target], node_ids=[n3, n5, k2], as_of=date(2026, 8, 1)
            )
        assert nodes[str(n5)].status.value == "repealed"
        assert nodes[str(k2)].status.value == "modified"
        assert str(n3) not in nodes  # only a proposal: nothing changes until it is approved
    finally:
        if pool is not None:
            await pool.close()
        await connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await connection.close()
