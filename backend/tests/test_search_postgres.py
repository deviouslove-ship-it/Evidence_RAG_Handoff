"""Opt-in PostgreSQL integration test for Search v1.

Run with a disposable database:

    EVIDENCE_TEST_DATABASE_URL=postgresql://user:pass@127.0.0.1:55432/postgres \
        python -m pytest backend/tests/test_search_postgres.py -q

The test creates (and drops) an isolated schema, applies migrations 0001..0006,
then seeds synthetic approved documents.  All fixture text is marked HƯ CẤU.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest

from app.main import create_app
from app.schemas import Scope
from app.storage.normalization import backfill_normalization, normalization_status
from app.storage.search import SearchService, SlidingWindowRateLimiter
from app.vietnamese_nlp.unicode_norm import fold_text, normalize_text

DSN = os.environ.get("EVIDENCE_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DSN, reason="No disposable PostgreSQL test database configured"
)

AS_OF = date(2026, 10, 31)
PHRASE = "báo cáo định kỳ và thường xuyên"


async def _apply_migrations(connection: asyncpg.Connection) -> None:
    migrations = Path(__file__).resolve().parents[1] / "app" / "migrations"
    for path in sorted(migrations.glob("*.sql")):
        if path.name.endswith(".down.sql"):
            continue
        await connection.execute(path.read_text(encoding="utf-8"))


async def _seed_document(
    connection: asyncpg.Connection,
    *,
    principal_id: UUID,
    category_id: UUID,
    document_number: str,
    title: str,
    label: str,
    text: str,
) -> UUID:
    document_id = uuid4()
    version_id = uuid4()
    await connection.execute(
        """INSERT INTO documents (id, doc_type, title, document_number)
           VALUES ($1, 'decree', $2, $3)""",
        document_id,
        title,
        document_number,
    )
    await connection.execute(
        "INSERT INTO document_categories (document_id, category_id) VALUES ($1, $2)",
        document_id,
        category_id,
    )
    await connection.execute(
        """INSERT INTO document_versions (
             id, document_id, version_number, valid_from, original_file_path,
             original_file_sha256, original_filename, review_status
           ) VALUES ($1, $2, 1, '2025-01-01', 'fixture.pdf', $3, 'fixture.pdf', 'approved')""",
        version_id,
        document_id,
        uuid4().hex + uuid4().hex,
    )
    await connection.execute(
        "INSERT INTO source_provenance (document_version_id, verified_at) VALUES ($1, now())",
        version_id,
    )
    page_id = await connection.fetchval(
        """INSERT INTO source_pages (document_version_id, page_number, width, height,
              extraction_method, text_quality, text_original)
           VALUES ($1, 1, 595, 842, 'native_text', 'usable', $2) RETURNING id""",
        version_id,
        text,
    )
    span_id = await connection.fetchval(
        """INSERT INTO source_spans (page_id, original_offset, original_length, text_original)
           VALUES ($1, 0, $2, $3) RETURNING id""",
        page_id,
        len(text),
        text,
    )
    indexed = " ".join((title, document_number, label, text))
    await connection.execute(
        """INSERT INTO document_nodes (
             document_id, document_version_id, node_type, label_original, path,
             text_original, text_indexed, text_normalized, text_folded,
             page_start, parse_confidence, review_status, source_span_id
           ) VALUES ($1, $2, 'clause', $3, $4, $5, $6, $7, $8, 1, 0.9, 'approved', $9)""",
        document_id,
        version_id,
        label,
        f"node/{document_number}",
        text,
        indexed,
        normalize_text(text),
        fold_text(text),
        span_id,
    )
    return document_id


async def test_search_postgres_tiers_acl_and_pagination() -> None:
    assert DSN
    schema = "test_search_" + uuid4().hex
    connection = await asyncpg.connect(DSN)
    pool = None
    try:
        await connection.execute(f'CREATE SCHEMA "{schema}"')
        await connection.execute(f'SET search_path TO "{schema}", public')
        await _apply_migrations(connection)

        principal = uuid4()
        other_principal = uuid4()
        category = uuid4()
        await connection.execute(
            "INSERT INTO users (id, username, display_name) VALUES ($1, 'allowed', 'Allowed')",
            principal,
        )
        await connection.execute(
            "INSERT INTO users (id, username, display_name) VALUES ($1, 'other', 'Other')",
            other_principal,
        )
        await connection.execute(
            "INSERT INTO categories (id, name, code) VALUES ($1, 'Fixture HƯ CẤU', 'hucau')",
            category,
        )
        await connection.execute(
            "INSERT INTO category_acl (category_id, user_id) VALUES ($1, $2)",
            category,
            principal,
        )

        exact_a = await _seed_document(
            connection,
            principal_id=principal,
            category_id=category,
            document_number="HU-CAU/2026/ND-CP",
            title="Nghị định hư cấu A",
            label="Điều 5. Chế độ báo cáo",
            text="Các bộ, ngành thực hiện báo cáo định kỳ và thường xuyên theo quy định.",
        )
        exact_b = await _seed_document(
            connection,
            principal_id=principal,
            category_id=category,
            document_number="HU-CAU/2026/ND-CP-2",
            title="Nghị định hư cấu B",
            label="Điều 9. Trách nhiệm báo cáo",
            text="Ủy ban nhân dân cấp tỉnh gửi báo cáo định kỳ và thường xuyên về Bộ.",
        )
        separated = await _seed_document(
            connection,
            principal_id=principal,
            category_id=category,
            document_number="HU-CAU/2026/ND-CP-3",
            title="Nghị định hư cấu C",
            label="Điều 3. Nội dung khác",
            text="Báo cáo được lập định kỳ và thường xuyên kiểm tra việc thực hiện.",
        )
        # The phrase is contiguous only when title + number + label + content are
        # concatenated into text_indexed; the node's own content does not contain
        # it, so this document must never receive the exact_phrase label.
        boundary = await _seed_document(
            connection,
            principal_id=principal,
            category_id=category,
            document_number="",
            title="Nghị định hư cấu báo cáo định kỳ",
            label="",
            text="và thường xuyên theo quy định.",
        )

        pool = await asyncpg.create_pool(
            DSN,
            min_size=1,
            max_size=2,
            server_settings={"search_path": schema + ",public"},
        )
        service = SearchService(pool, audit_enabled=False)

        async with pool.acquire() as check:
            async with check.transaction():
                await check.execute("SET LOCAL enable_seqscan = off")
                plan_rows = await check.fetch(
                    """EXPLAIN (COSTS OFF)
                       SELECT 1 FROM document_nodes n
                       WHERE n.document_id = ANY($1::uuid[])
                         AND to_tsvector('simple'::regconfig, n.text_indexed)
                             @@ plainto_tsquery('simple'::regconfig, 'báo cáo')""",
                    [exact_a, exact_b, separated],
                )
        plan = "\n".join(row[0] for row in plan_rows)
        assert "document_nodes_search_word_gin" in plan, plan

        exact = await service.search_documents(
            principal_id=principal,
            raw_query=f'"{PHRASE}"',
            mode="auto",
            as_of_date=AS_OF,
        )
        assert exact.phrase_found is True
        assert exact.empty_reason is None
        assert exact.totals.documents == 2
        returned_documents = {item.document_id for item in exact.results}
        assert returned_documents == {str(exact_a), str(exact_b)}
        assert all(
            clause.match_type.value == "exact_phrase"
            for item in exact.results
            for clause in item.clauses
        )
        assert exact.effectivity_snapshot_status == "stale"
        assert boundary not in returned_documents

        variant = await service.search_documents(
            principal_id=principal,
            raw_query='"báo cáo định kì và thường xuyên"',
            mode="phrase",
            as_of_date=AS_OF,
        )
        assert variant.phrase_found is True
        assert variant.totals.documents == 2
        assert all(
            clause.match_type.value == "exact_phrase"
            for item in variant.results
            for clause in item.clauses
        )

        variant_old = await _seed_document(
            connection,
            principal_id=principal,
            category_id=category,
            document_number="HU-CAU/2026/ND-CP-4",
            title="Nghị định hư cấu D",
            label="Điều 4. Báo cáo định kì",
            text="Các bộ thực hiện báo cáo định kì và thường xuyên.",
        )
        old_node = await connection.fetchval(
            "SELECT id FROM document_nodes WHERE document_id = $1", variant_old
        )
        await connection.execute(
            """UPDATE document_nodes
               SET normalization_revision = 'vietnamese-tone-v2',
                   text_normalized = $2,
                   text_folded = $3
               WHERE id = $1""",
            old_node,
            "các bộ thực hiện báo cáo định kì và thường xuyên.",
            "cac bo thuc hien bao cao dinh ki va thuong xuyen.",
        )
        stale_status = await normalization_status(pool)
        assert stale_status["stale_nodes"] >= 1
        assert "vietnamese-tone-v2" in stale_status["revisions"]

        before_backfill = await service.search_documents(
            principal_id=principal,
            raw_query='"báo cáo định kì và thường xuyên"',
            mode="phrase",
            as_of_date=AS_OF,
        )
        assert str(variant_old) not in {
            item.document_id for item in before_backfill.results
        }

        backfilled = await backfill_normalization(pool, batch_size=10)
        assert backfilled["updated"] >= 1
        current_status = await normalization_status(pool)
        assert current_status["stale_nodes"] == 0

        after_backfill = await service.search_documents(
            principal_id=principal,
            raw_query='"báo cáo định kì và thường xuyên"',
            mode="phrase",
            as_of_date=AS_OF,
        )
        old_clauses = [
            clause
            for item in after_backfill.results
            if item.document_id == str(variant_old)
            for clause in item.clauses
        ]
        assert old_clauses
        assert all(clause.match_type.value == "exact_phrase" for clause in old_clauses)
        updated_text = await connection.fetchval(
            "SELECT text_normalized FROM document_nodes WHERE id = $1", old_node
        )
        assert "kỳ" in updated_text

        first_clause = exact.results[0].clauses[0]
        assert first_clause.highlights
        for highlight in first_clause.highlights:
            assert "báo cáo định kỳ" in first_clause.quote_exact[
                highlight.start : highlight.end
            ].lower()

        snapshot_id = uuid4()
        await connection.execute(
            """INSERT INTO effectivity_snapshot_revisions
                 (id, revision, source_review_revision, is_active, published_at)
               VALUES ($1, 1, 1, TRUE, now())""",
            snapshot_id,
        )
        node_a = await connection.fetchval(
            "SELECT id FROM document_nodes WHERE document_id = $1", exact_a
        )
        await connection.execute(
            """INSERT INTO node_effective_intervals
                 (snapshot_revision_id, node_id, valid_from, effective_status)
               VALUES ($1, $2, '2025-01-01', 'modified')""",
            snapshot_id,
            node_a,
        )
        with_effectivity = await service.search_documents(
            principal_id=principal,
            raw_query=f'"{PHRASE}"',
            mode="phrase",
            as_of_date=AS_OF,
        )
        assert with_effectivity.effectivity_snapshot_status == "ok"
        states = {
            clause.amendment_state.value
            for item in with_effectivity.results
            for clause in item.clauses
        }
        assert "modified" in states
        assert "unknown" in states

        missing = await service.search_documents(
            principal_id=principal,
            raw_query='"không tồn tại cụm từ này"',
            mode="phrase",
            as_of_date=AS_OF,
        )
        assert missing.phrase_found is False
        assert missing.empty_reason.value == "PHRASE_NOT_FOUND"

        folded = await service.search_documents(
            principal_id=principal,
            raw_query='"bao cao dinh ky va thuong xuyen"',
            mode="phrase",
            as_of_date=AS_OF,
        )
        assert folded.phrase_found is False
        assert folded.empty_reason.value == "PHRASE_NOT_FOUND"
        assert any(
            clause.match_type.value == "phrase_folded"
            for item in folded.results
            for clause in item.clauses
        )

        keywords = await service.search_documents(
            principal_id=principal,
            raw_query="báo cáo định kỳ",
            mode="keywords",
            as_of_date=AS_OF,
        )
        assert keywords.totals.clauses >= 3
        assert all(
            clause.match_type.value == "all_terms"
            for item in keywords.results
            for clause in item.clauses
        )
        assert separated not in {item.document_id for item in exact.results}

        hidden = await service.search_documents(
            principal_id=other_principal,
            raw_query=f'"{PHRASE}"',
            mode="phrase",
            as_of_date=AS_OF,
        )
        assert hidden.results == []
        assert hidden.empty_reason.value == "NO_AUTHORIZED_DOCUMENTS"

        first_page = await service.search_documents(
            principal_id=principal,
            raw_query=f'"{PHRASE}"',
            mode="phrase",
            as_of_date=AS_OF,
            page=1,
            page_size=1,
        )
        second_page = await service.search_documents(
            principal_id=principal,
            raw_query=f'"{PHRASE}"',
            mode="phrase",
            as_of_date=AS_OF,
            page=2,
            page_size=1,
        )
        third_page = await service.search_documents(
            principal_id=principal,
            raw_query=f'"{PHRASE}"',
            mode="phrase",
            as_of_date=AS_OF,
            page=3,
            page_size=1,
        )
        assert first_page.has_more is True
        assert second_page.has_more is True
        assert third_page.has_more is False
        assert first_page.totals.documents == 3
        assert second_page.totals.documents == 3

        partial = await _seed_document(
            connection,
            principal_id=principal,
            category_id=category,
            document_number="HU-CAU/2026/ND-CP-PARTIAL",
            title="Văn bản HƯ CẤU chỉ khớp một phần",
            label="Điều 1",
            text="Báo cáo tổng hợp hàng năm.",
        )
        approximate = await service.search_approximate(
            principal_id=principal,
            raw_query=f'"{PHRASE}"',
            mode="phrase",
            as_of_date=AS_OF,
        )
        assert all(
            clause.match_type.value == "any_term"
            for item in approximate.results
            for clause in item.clauses
        )
        assert {item.document_id for item in approximate.results} == {str(partial)}
        assert approximate.totals.clauses == 1
        assert approximate.totals.documents == 1

        hidden_approximate = await service.search_approximate(
            principal_id=other_principal,
            raw_query=f'"{PHRASE}"',
            as_of_date=AS_OF,
        )
        assert hidden_approximate.results == []
        assert hidden_approximate.totals.clauses == 0

        partial_second = await _seed_document(
            connection,
            principal_id=principal,
            category_id=category,
            document_number="HU-CAU/2026/ND-CP-PARTIAL-2",
            title="Văn bản HƯ CẤU khớp một phần thứ hai",
            label="Điều 1",
            text="Báo cáo tổng hợp hàng năm.",
        )
        capped_counter = SearchService(pool, approximate_count_limit=1, audit_enabled=False)
        full_approximate = await capped_counter.search_approximate(
            principal_id=principal,
            raw_query=f'"{PHRASE}"',
            as_of_date=AS_OF,
        )
        assert full_approximate.totals.clauses == 2
        assert full_approximate.approximate.total_clauses == 2
        assert full_approximate.approximate.capped is False

        special = await service.search_documents(
            principal_id=principal,
            raw_query='báo "cáo - | & :* <-> \' % _',
            mode="keywords",
            as_of_date=AS_OF,
        )
        assert special.page == 1

        api_app = create_app()
        async with api_app.router.lifespan_context(api_app):
            api_app.state.search_service = service
            api_app.state.search_rate = SlidingWindowRateLimiter(limit=100)
            transport = httpx.ASGITransport(app=api_app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as client:
                api_response = await client.get(
                    "/api/v1/search",
                    headers={
                        "X-Principal-Id": str(principal),
                        "X-Roles": "USER",
                    },
                    params={
                        "q": f'"{PHRASE}"',
                        "mode": "phrase",
                        "as_of_date": "2026-10-31",
                    },
                )
        assert api_response.status_code == 200
        api_body = api_response.json()
        assert api_body["phrase_found"] is True
        assert api_body["totals"]["documents"] == 3
        clause = api_body["results"][0]["clauses"][0]
        assert clause["match_type"] == "exact_phrase"
        assert clause["viewer_url"].startswith("/api/v1/citations/ev_")
        assert clause["viewer_url"].endswith("/pdf?as_of_date=2026-10-31")
        assert clause["source_hash"]
        # Search must return promptly even while an unrelated transaction holds
        # the shared audit-chain lock.
        async with connection.transaction():
            await connection.execute("SELECT pg_advisory_xact_lock(7302026001)")
            audited_service = SearchService(pool, statement_timeout_ms=1000)
            audited = await __import__("asyncio").wait_for(
                audited_service.search_documents(
                    principal_id=principal, raw_query=f'"{PHRASE}"', as_of_date=AS_OF,
                ),
                timeout=0.8,
            )
            assert audited.totals.documents == 3

        # More than the old 5,000-candidate cap must remain reachable, including
        # deep clause windows in a single authorized document.
        await connection.execute(
            """INSERT INTO document_nodes (
                document_id, document_version_id, node_type, label_original, path,
                text_original, text_indexed, text_normalized, text_folded,
                page_start, parse_confidence, review_status, source_span_id
            ) SELECT n.document_id, n.document_version_id, n.node_type,
                     n.label_original, n.path || '/' || s.i, n.text_original,
                     n.text_indexed, n.text_normalized, n.text_folded,
                     n.page_start, n.parse_confidence, n.review_status, n.source_span_id
              FROM document_nodes n CROSS JOIN generate_series(1, 5001) s(i)
              WHERE n.document_id = $1""",
            partial,
        )
        large = await service.search_documents(
            principal_id=principal, raw_query='"báo cáo tổng hợp hàng năm"',
            as_of_date=AS_OF, clause_page=1001, clause_page_size=5,
        )
        bulk = next(item for item in large.results if item.document_id == str(partial))
        assert bulk.matched_clause_count == 5002
        assert len(bulk.clauses) == 2
        assert large.totals.clauses == 5003

        unaccented = await service.search_documents(
            principal_id=principal, raw_query="bao cao dinh ky va thuong xuyen",
            mode="keywords", as_of_date=AS_OF,
        )
        assert unaccented.totals.documents >= 3

        mixed = await service.search_documents(
            principal_id=principal, raw_query='"báo cáo" tổng hợp', as_of_date=AS_OF,
        )
        assert {item.document_id for item in mixed.results} == {
            str(partial), str(partial_second),
        }

        large_partial = await service.search_approximate(
            principal_id=principal, raw_query=f'"{PHRASE}"', as_of_date=AS_OF,
            clause_page=1001, clause_page_size=5,
        )
        partial_group = next(
            item for item in large_partial.results if item.document_id == str(partial)
        )
        assert partial_group.matched_clause_count == 5002
        assert len(partial_group.clauses) == 2
        assert large_partial.totals.clauses == 5003
        assert large_partial.approximate.capped is False

        numbered = await _seed_document(
            connection, principal_id=principal, category_id=category,
            document_number="400/2026/NĐ-CP", title="Văn bản HƯ CẤU có số hiệu",
            label="Điều 1", text=PHRASE,
        )
        number_lookup = await service.search_documents(
            principal_id=principal, raw_query="400/2026/ND-CP", as_of_date=AS_OF,
        )
        assert number_lookup.results[0].document_id == str(numbered)

        chat_lookup = await service.search_clauses(
            principal_id=principal,
            scope=Scope(scope_mode="ALL_AUTHORIZED", as_of_date=AS_OF),
            query='Tìm "báo cáo" theo Nghị định 400/2026/NĐ-CP', limit=1,
        )
        assert chat_lookup[0].document_id == numbered

        uppercase = await _seed_document(
            connection, principal_id=principal, category_id=category,
            document_number="401/2026/NĐ-CP", title="Văn bản HƯ CẤU chữ hoa",
            label="Điều 1", text=PHRASE.upper(),
        )
        casing = await service.search_documents(
            principal_id=principal, raw_query=f'"{PHRASE}"', as_of_date=AS_OF,
        )
        upper_group = next(item for item in casing.results if item.document_id == str(uppercase))
        assert upper_group.clauses[0].match_type.value == "exact_phrase"

        await connection.execute(
            "UPDATE documents SET title = title || ' metadataOnlyMarker' WHERE id=$1", numbered,
        )
        metadata_only = await service.search_clauses(
            principal_id=principal,
            scope=Scope(scope_mode="ALL_AUTHORIZED", as_of_date=AS_OF),
            query="metadataOnlyMarker",
        )
        assert {item.document_id for item in metadata_only} == {numbered}
        await connection.execute(
            "UPDATE document_nodes SET label_original='labelOnlyMarker' WHERE document_id=$1",
            numbered,
        )
        label_only = await service.search_clauses(
            principal_id=principal,
            scope=Scope(scope_mode="ALL_AUTHORIZED", as_of_date=AS_OF),
            query="labelOnlyMarker",
        )
        assert {item.document_id for item in label_only} == {numbered}

        migrations = Path(__file__).resolve().parents[1] / "app" / "migrations"
        await connection.execute(
            (migrations / "0006_search_index.down.sql").read_text(encoding="utf-8")
        )
        assert (
            await connection.fetchval(
                "SELECT to_regclass($1)",
                f'"{schema}".document_nodes_search_word_gin',
            )
            is None
        )
    finally:
        if pool is not None:
            await pool.close()
        await connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await connection.close()
