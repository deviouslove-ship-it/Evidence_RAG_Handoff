"""Opt-in schema/query smoke test on an explicitly supplied disposable database."""

import os
from datetime import date
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest

from app.schemas import Scope, ScopeMode
from app.storage.authorized_search import PostgresAuthorizedNodeSearch

DSN = os.environ.get("EVIDENCE_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DSN, reason="No disposable PostgreSQL/pgvector test database configured"
)


async def test_migrations_and_search_query_compile_on_postgresql() -> None:
    assert DSN
    schema = "test_evidence_" + uuid4().hex
    migrations = Path(__file__).resolve().parents[1] / "app" / "migrations"
    connection = await asyncpg.connect(DSN)
    pool = None
    try:
        await connection.execute(f'CREATE SCHEMA "{schema}"')
        await connection.execute(f'SET search_path TO "{schema}", public')
        # The search SQL targets the current schema, so apply every up migration.
        for migration in sorted(migrations.glob("[0-9][0-9][0-9][0-9]_*.sql")):
            if not migration.name.endswith(".down.sql"):
                await connection.execute(migration.read_text(encoding="utf-8"))
        pool = await asyncpg.create_pool(
            DSN,
            min_size=1,
            max_size=1,
            server_settings={"search_path": schema + ",public"},
        )
        result = await PostgresAuthorizedNodeSearch(pool).search(
            principal_id=uuid4(),
            scope=Scope(scope_mode=ScopeMode.ALL_AUTHORIZED, as_of_date=date(2026, 10, 22)),
            query="fixture",
        )
        assert result == []
        principal_id, other_principal_id = uuid4(), uuid4()
        category_id, document_id, version_id = uuid4(), uuid4(), uuid4()
        await connection.execute(
            "INSERT INTO users (id, username, display_name) VALUES ($1, 'allowed', 'Allowed')",
            principal_id,
        )
        await connection.execute(
            "INSERT INTO categories (id, name, code) VALUES ($1, 'Fixture', 'fixture')",
            category_id,
        )
        await connection.execute(
            "INSERT INTO category_acl (category_id, user_id) VALUES ($1, $2)",
            category_id,
            principal_id,
        )
        await connection.execute(
            """INSERT INTO documents (id, doc_type, title, document_number)
               VALUES ($1, 'decree', 'Quy định phụ cấp công vụ', '381/2026/NĐ-CP')""",
            document_id,
        )
        await connection.execute(
            "INSERT INTO document_categories (document_id, category_id) VALUES ($1, $2)",
            document_id,
            category_id,
        )
        await connection.execute(
            """INSERT INTO document_versions (
                 id, document_id, version_number, original_file_path,
                 original_file_sha256, original_filename, review_status
               ) VALUES ($1, $2, 1, 'fixture.pdf', $3, 'fixture.pdf', 'approved')""",
            version_id,
            document_id,
            "a" * 64,
        )
        text = "Nội dung kỹ thuật trong fixture."
        await connection.execute(
            "INSERT INTO source_provenance (document_version_id, verified_at) VALUES ($1, now())",
            version_id,
        )
        page = await connection.fetchval(
            """INSERT INTO source_pages (document_version_id, page_number, width, height,
                  extraction_method, text_quality, text_original)
               VALUES ($1,1,595,842,'native_text','usable',$2) RETURNING id""", version_id, text,
        )
        span = await connection.fetchval(
            """INSERT INTO source_spans (page_id, original_offset, original_length, text_original)
               VALUES ($1,0,$2,$3) RETURNING id""", page, len(text), text,
        )
        for label in ("Điều 30. Nội dung khác", "Điều 3. Mức phụ cấp công vụ"):
            await connection.execute(
                """INSERT INTO document_nodes (
                     document_id, document_version_id, node_type, label_original,
                     path, text_original, text_indexed, text_normalized, text_folded,
                     page_start, parse_confidence, review_status, source_span_id
                   ) VALUES ($1, $2, 'article', $3, $3, $4, $4, $4, $4,
                             1, 0.95, 'approved', $5)""",
                document_id,
                version_id,
                label,
                text, span,
            )
        search = PostgresAuthorizedNodeSearch(pool)
        scope = Scope(scope_mode=ScopeMode.ALL_AUTHORIZED, as_of_date=date(2026, 10, 22))
        found = await search.search(
            principal_id=principal_id,
            scope=scope,
            query="Điều 3 Nghị định 381/2026/NĐ-CP",
        )
        assert [item.label for item in found] == [
            "Điều 3. Mức phụ cấp công vụ",
            "Điều 30. Nội dung khác",
        ]
        hidden = await search.search(
            principal_id=other_principal_id,
            scope=scope,
            query="Điều 3 Nghị định 381/2026/NĐ-CP",
        )
        assert hidden == []
        await pool.close()
        pool = None
        # Every down migration, newest first, then every up migration again.
        for migration in sorted(migrations.glob("[0-9][0-9][0-9][0-9]_*.down.sql"),
                                reverse=True):
            await connection.execute(migration.read_text(encoding="utf-8"))
        assert await connection.fetchval(f"SELECT to_regclass('{schema}.document_nodes')") is None
        for migration in sorted(migrations.glob("[0-9][0-9][0-9][0-9]_*.sql")):
            if not migration.name.endswith(".down.sql"):
                await connection.execute(migration.read_text(encoding="utf-8"))
    finally:
        if pool is not None:
            await pool.close()
        await connection.execute("ROLLBACK")
        await connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await connection.close()
