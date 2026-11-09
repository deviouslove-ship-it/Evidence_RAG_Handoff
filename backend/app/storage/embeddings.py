"""Embedding indices: build/rebuild with the Registry model, query by meaning (G2, G5).

The vector column has no fixed dimension (migration 0012); each embedding index
records model, revision and dimension and gets its own partial HNSW index on
``embedding::vector(<dimension>)`` (``halfvec`` above 2000 dimensions).  Changing the
model is a new index revision, never a schema change (design §3, G5 "đổi model và
tính lại vector").

The steps below are shared by ``scripts/build_embeddings.py`` and the Admin Portal
background job (``embedding_jobs.py``): open or reuse an index, embed the pending
nodes in batches, build the vector index, verify, then switch the active index in one
transaction.  The active index keeps serving search until the switch; nothing here
deletes vectors or indexes.
"""

from __future__ import annotations

import logging
import math
import re
from collections.abc import Callable, Sequence
from typing import Any
from uuid import UUID

from ..model_registry.runtime import EmbeddingOutcome

_LOG = logging.getLogger(__name__)
EMBED_TEXT_CHARS = 800
TOKENIZER_REVISION = "model-native"
PROBE_TEXT = "kiểm tra số chiều"
# pgvector HNSW limits: ``vector`` up to 2000 dimensions, ``halfvec`` up to 4000.
MAX_VECTOR_DIMENSIONS = 2000
MAX_INDEXED_DIMENSIONS = 4000
# Building HNSW over every vector takes minutes on a CPU-only machine; the pool's
# 30 s per-statement limit is for interactive queries.
INDEX_BUILD_TIMEOUT_SECONDS = 6 * 3600
# Index states that still hold reusable vectors of their model.
REUSABLE_STATES = ("building", "paused", "failed", "ready", "retired")
UNFINISHED_STATES = ("building", "paused", "failed")

# Approved nodes of the latest approved version of every live document: the set the
# index must cover before it may serve search.
ELIGIBLE_NODES_SQL = """
    SELECT n.id, n.document_id, n.citation_label, n.label_original, n.text_original,
           d.title, d.document_number
    FROM document_nodes n
    JOIN documents d ON d.id = n.document_id AND d.deleted_at IS NULL
    JOIN LATERAL (
      SELECT v.id FROM document_versions v
      WHERE v.document_id = n.document_id AND v.review_status = 'approved'
        AND v.retired_at IS NULL
      ORDER BY v.version_number DESC LIMIT 1) latest
      ON latest.id = n.document_version_id
    WHERE n.review_status = 'approved'"""

# A document may be sent to an external (public) embedding model only under the same
# rule as the answer stage: not restricted, at least one category, every category
# allows remote processing.
_REMOTE_INELIGIBLE = """
    NOT (
      EXISTS (SELECT 1 FROM documents d2 WHERE d2.id = e.document_id
              AND d2.classification_level <> 'restricted')
      AND EXISTS (SELECT 1 FROM document_categories dc WHERE dc.document_id = e.document_id)
      AND NOT EXISTS (
        SELECT 1 FROM document_categories dc JOIN categories c ON c.id = dc.category_id
        WHERE dc.document_id = e.document_id
          AND (NOT c.remote_processing_allowed OR c.deleted_at IS NOT NULL)))"""


class EmbeddingIndexError(Exception):
    """A redacted reason why an index cannot be built or switched."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def embedding_text(label: str | None, title: str, number: str | None, text: str) -> str:
    """Number and citation label, then the clause text (CPU-only models: keep it short).

    The title is left out on purpose: it repeats in every clause of a document and
    the exact channel already matches it.
    """

    del title
    head = " · ".join(part for part in (number, label) if part)
    body = re.sub(r"\s+", " ", text).strip()
    return f"{head}\n{body}"[:EMBED_TEXT_CHARS]


def node_text(row: Any) -> str:
    return embedding_text(row["citation_label"] or row["label_original"], row["title"],
                          row["document_number"], row["text_original"])


def vector_literal(values: Sequence[float]) -> str:
    return "[" + ",".join(f"{value:.7g}" for value in values) + "]"


def parse_vector(text: str) -> list[float]:
    return [float(item) for item in text.strip("[]").split(",") if item]


def hnsw_index_name(index_id: UUID) -> str:
    return f"node_embeddings_hnsw_{index_id.hex[:16]}"


def vector_type(dimensions: int) -> str:
    """pgvector type that can be HNSW-indexed at this size."""

    if 1 <= dimensions <= MAX_VECTOR_DIMENSIONS:
        return "vector"
    if MAX_VECTOR_DIMENSIONS < dimensions <= MAX_INDEXED_DIMENSIONS:
        return "halfvec"
    raise EmbeddingIndexError("EMBEDDING_DIMENSIONS_UNSUPPORTED")


def vectors_valid(vectors: Sequence[Sequence[float]], dimensions: int) -> bool:
    """Same size, finite numbers, not all zero (a zero vector has no direction)."""

    for vector in vectors:
        if len(vector) != dimensions or not all(math.isfinite(value) for value in vector):
            return False
        if not any(vector):
            return False
    return True


def cosine(left: Sequence[float], right: Sequence[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return dot / norm if norm else 0.0


async def active_index(connection: Any) -> Any:
    return await connection.fetchrow(
        """SELECT id, model_id, model_revision, dimensions, profile_key, node_count,
                  completed_at
           FROM embedding_indices WHERE is_active AND status = 'ready' LIMIT 1"""
    )


async def eligible_count(connection: Any) -> int:
    return int(await connection.fetchval(f"SELECT count(*) FROM ({ELIGIBLE_NODES_SQL}) e"))


async def pending_count(connection: Any, index_id: UUID) -> int:
    return int(await connection.fetchval(
        f"""SELECT count(*) FROM ({ELIGIBLE_NODES_SQL}) e
            WHERE NOT EXISTS (SELECT 1 FROM node_embeddings v
                              WHERE v.embedding_index_id = $1 AND v.document_node_id = e.id)""",
        index_id,
    ))


async def pending_batch(connection: Any, index_id: UUID, batch_size: int) -> list[Any]:
    return list(await connection.fetch(
        f"""SELECT e.* FROM ({ELIGIBLE_NODES_SQL}) e
            WHERE NOT EXISTS (SELECT 1 FROM node_embeddings v
                              WHERE v.embedding_index_id = $1 AND v.document_node_id = e.id)
            ORDER BY e.id LIMIT $2""",
        index_id, batch_size,
    ))


async def remote_ineligible_count(
    connection: Any, node_ids: Sequence[UUID] | None = None
) -> int:
    """Eligible nodes (or the given ones) whose document may not leave the network."""

    return int(await connection.fetchval(
        f"""SELECT count(*) FROM ({ELIGIBLE_NODES_SQL}) e
            WHERE ($1::uuid[] IS NULL OR e.id = ANY($1::uuid[])) AND {_REMOTE_INELIGIBLE}""",
        list(node_ids) if node_ids is not None else None,
    ))


async def find_index(
    connection: Any, *, model_id: str, revision: str, dimensions: int, rebuild: bool
) -> Any:
    """Index of the same model, revision and size whose vectors can be reused.

    ``rebuild`` reuses only an unfinished index (resume), so a finished one is never
    refilled and a fresh revision is opened instead.
    """

    states = list(UNFINISHED_STATES if rebuild else REUSABLE_STATES)
    return await connection.fetchrow(
        """SELECT id, status, is_active, model_id, model_revision, dimensions, profile_key
           FROM embedding_indices
           WHERE model_id = $1 AND model_revision = $2 AND dimensions = $3
             AND status = ANY($4::text[])
           ORDER BY is_active DESC, index_revision DESC LIMIT 1""",
        model_id, revision, dimensions, states,
    )


async def open_index(
    connection: Any, *, model_id: str, revision: str, dimensions: int,
    profile_key: str | None, rebuild: bool,
) -> UUID:
    vector_type(dimensions)
    found = await find_index(connection, model_id=model_id, revision=revision,
                             dimensions=dimensions, rebuild=rebuild)
    if found is not None:
        return UUID(str(found["id"]))
    next_revision = int(await connection.fetchval(
        "SELECT COALESCE(max(index_revision), 0) + 1 FROM embedding_indices"
    ))
    return UUID(str(await connection.fetchval(
        """INSERT INTO embedding_indices
             (model_id, model_revision, tokenizer_revision, dimensions, index_revision,
              profile_key, status)
           VALUES ($1, $2, $3, $4, $5, $6, 'building') RETURNING id""",
        model_id, revision, TOKENIZER_REVISION, dimensions, next_revision, profile_key,
    )))


async def store_vectors(
    pool: Any, index_id: UUID, rows: Sequence[Any], vectors: Sequence[Sequence[float]]
) -> None:
    async with pool.acquire() as connection, connection.transaction():
        await connection.executemany(
            """INSERT INTO node_embeddings (embedding_index_id, document_node_id, embedding)
               VALUES ($1, $2, $3::vector) ON CONFLICT DO NOTHING""",
            [(index_id, row["id"], vector_literal(vector))
             for row, vector in zip(rows, vectors, strict=True)],
        )


async def _hnsw_state(connection: Any, index_id: UUID) -> bool | None:
    """``None`` = no HNSW index yet, otherwise whether PostgreSQL marks it valid."""

    valid = await connection.fetchval(
        """SELECT i.indisvalid FROM pg_class c JOIN pg_index i ON i.indexrelid = c.oid
           WHERE c.relname = $1 AND c.relnamespace = (
             SELECT oid FROM pg_namespace WHERE nspname = current_schema())""",
        hnsw_index_name(index_id),
    )
    return None if valid is None else bool(valid)


async def ensure_vector_index(pool: Any, index_id: UUID, dimensions: int) -> None:
    """Build the per-index HNSW index without blocking search or vector writes.

    ``CONCURRENTLY`` runs outside a transaction.  An invalid index left by an
    interrupted build is rebuilt in place (``REINDEX``), never dropped.
    """

    kind = vector_type(int(dimensions))
    name = hnsw_index_name(index_id)
    async with pool.acquire() as connection:
        state = await _hnsw_state(connection, index_id)
        if state is None:
            await connection.execute(
                f'CREATE INDEX CONCURRENTLY IF NOT EXISTS "{name}" ON node_embeddings '
                f"USING hnsw ((embedding::{kind}({int(dimensions)})) {kind}_cosine_ops) "
                f"WHERE embedding_index_id = '{index_id}'",
                timeout=INDEX_BUILD_TIMEOUT_SECONDS,
            )
        elif state is False:
            await connection.execute(
                f'REINDEX INDEX CONCURRENTLY "{name}"', timeout=INDEX_BUILD_TIMEOUT_SECONDS
            )


async def verify_index(connection: Any, index_id: UUID, dimensions: int) -> dict[str, Any]:
    """Integrity of a finished index before it may serve search."""

    pending = await pending_count(connection, index_id)
    wrong = int(await connection.fetchval(
        """SELECT count(*) FROM node_embeddings
           WHERE embedding_index_id = $1
             AND (embedding IS NULL OR vector_dims(embedding) <> $2)""",
        index_id, int(dimensions),
    ))
    vectors = int(await connection.fetchval(
        "SELECT count(*) FROM node_embeddings WHERE embedding_index_id = $1", index_id
    ))
    hnsw = await _hnsw_state(connection, index_id)
    problems: list[str] = []
    if pending:
        problems.append("EMBEDDING_PENDING_NODES")
    if wrong:
        problems.append("EMBEDDING_DIMENSION_MISMATCH")
    if hnsw is not True:
        problems.append("EMBEDDING_VECTOR_INDEX_INVALID")
    if vectors == 0:
        problems.append("EMBEDDING_INDEX_EMPTY")
    return {"pending": pending, "wrong_dimensions": wrong, "vectors": vectors,
            "hnsw_valid": hnsw is True, "problems": problems}


async def activate_index(pool: Any, index_id: UUID) -> dict[str, Any]:
    """Switch search to ``index_id`` in one transaction, or report why not.

    The previous active index becomes ``retired`` and keeps its vectors and HNSW
    index.  New nodes approved since the last check make the switch wait
    (``status="pending"``) instead of serving an incomplete index.
    """

    async with pool.acquire() as connection, connection.transaction():
        await connection.execute("LOCK TABLE embedding_indices IN SHARE ROW EXCLUSIVE MODE")
        row = await connection.fetchrow(
            "SELECT id, status, is_active, dimensions FROM embedding_indices WHERE id = $1",
            index_id,
        )
        if row is None:
            raise EmbeddingIndexError("EMBEDDING_INDEX_NOT_FOUND")
        pending = await pending_count(connection, index_id)
        if pending:
            return {"status": "pending", "pending": pending}
        if await _hnsw_state(connection, index_id) is not True:
            raise EmbeddingIndexError("EMBEDDING_VECTOR_INDEX_INVALID")
        previous = await connection.fetchval(
            "SELECT id FROM embedding_indices WHERE is_active AND id <> $1", index_id
        )
        total = int(await connection.fetchval(
            "SELECT count(*) FROM node_embeddings WHERE embedding_index_id = $1", index_id
        ))
        await connection.execute(
            """UPDATE embedding_indices SET is_active = FALSE, status = 'retired',
                 retired_at = now()
               WHERE is_active AND id <> $1""",
            index_id,
        )
        await connection.execute(
            """UPDATE embedding_indices SET status = 'ready', is_active = TRUE,
                 completed_at = now(), verified_at = now(), last_error = NULL,
                 activated_at = CASE WHEN is_active THEN activated_at ELSE now() END,
                 node_count = $2
               WHERE id = $1""",
            index_id, total,
        )
        await connection.execute(
            "UPDATE embedding_indices SET status = 'retired', retired_at = now() "
            "WHERE id <> $1 AND status = 'ready' AND NOT is_active",
            index_id,
        )
    return {"status": "ready", "previous_index_id": str(previous) if previous else None,
            "vectors": total}


async def build_embeddings(
    pool: Any,
    embed: Callable[[list[str]], Any],
    *,
    profile_key: str | None = None,
    rebuild: bool = False,
    batch_size: int = 16,
    limit: int | None = None,
    log: Callable[[str], None] = _LOG.info,
) -> dict[str, Any]:
    """Embed every approved node of the latest approved versions that has no vector yet.

    ``embed`` is ``RegistryRuntime.embed`` (bound to a profile or the route).  A new
    index revision is opened when the model, revision or dimension differs from the
    one being built, or when ``rebuild`` is set; the old index stays active until the
    new one is complete and verified.
    """

    del profile_key  # the probe reports the profile that actually answered
    probe: EmbeddingOutcome = await embed([PROBE_TEXT])
    if not probe.vectors or probe.model_id is None:
        return {"status": "embedding_unavailable", "error": probe.error}
    dimensions = probe.dimensions or 0
    try:
        vector_type(dimensions)
    except EmbeddingIndexError as exc:
        return {"status": "embedding_unavailable", "error": exc.code, "dimensions": dimensions}
    async with pool.acquire() as connection:
        zone = await connection.fetchval(
            "SELECT privacy_zone FROM model_profiles WHERE profile_key = $1", probe.profile_key
        )
        public = zone == "public"
        if public and await remote_ineligible_count(connection):
            return {"status": "embedding_unavailable",
                    "error": "REMOTE_EMBEDDING_DOCUMENTS_DENIED"}
        index_id = await open_index(
            connection, model_id=probe.model_id, revision=probe.revision or "",
            dimensions=dimensions, profile_key=probe.profile_key, rebuild=rebuild,
        )
    embedded = failed = 0
    while True:
        async with pool.acquire() as connection:
            rows = await pending_batch(connection, index_id, batch_size)
            if rows and public and await remote_ineligible_count(
                connection, [row["id"] for row in rows]
            ):
                failed += len(rows)
                log("document not allowed for an external embedding model; stopping")
                break
        if not rows:
            break
        outcome: EmbeddingOutcome = await embed([node_text(row) for row in rows])
        if (
            not outcome.vectors
            or outcome.model_id != probe.model_id
            or (outcome.revision or "") != (probe.revision or "")
            or not vectors_valid(outcome.vectors, dimensions)
        ):
            failed += len(rows)
            log(f"batch failed ({len(rows)} nodes, {outcome.error}); stopping, resume later")
            break
        await store_vectors(pool, index_id, rows, outcome.vectors)
        embedded += len(rows)
        if embedded % (batch_size * 25) == 0:
            log(f"embedded {embedded}")
        if limit is not None and embedded >= limit:
            break
    async with pool.acquire() as connection:
        remaining = await pending_count(connection, index_id)
    status = "building"
    if not failed and not remaining:
        await ensure_vector_index(pool, index_id, dimensions)
        async with pool.acquire() as connection:
            report = await verify_index(connection, index_id, dimensions)
        if report["problems"]:
            log("verification failed: " + ", ".join(report["problems"]))
        elif (await activate_index(pool, index_id))["status"] == "ready":
            status = "ready"
    async with pool.acquire() as connection:
        total = int(await connection.fetchval(
            "SELECT count(*) FROM node_embeddings WHERE embedding_index_id = $1", index_id
        ))
        remaining = await pending_count(connection, index_id)
    return {"status": status, "index_id": str(index_id), "model_id": probe.model_id,
            "dimensions": dimensions, "embedded": embedded, "failed": failed,
            "vectors": total, "remaining": remaining}


async def semantic_candidates(
    connection: Any,
    *,
    index: Any,
    query_vector: Sequence[float],
    version_ids: Sequence[UUID],
    category_ids: Sequence[UUID] | None,
    doc_types: Sequence[str] | None,
    top_n: int,
) -> list[tuple[str, str, float]]:
    """Nearest approved nodes of the eligible versions (node, document, similarity)."""

    dimensions = int(index["dimensions"])
    if len(query_vector) != dimensions:
        return []
    try:
        kind = vector_type(dimensions)
    except EmbeddingIndexError:
        return []
    cast = f"{kind}({dimensions})"
    index_id = UUID(str(index["id"]))
    await connection.execute(f"SET LOCAL hnsw.ef_search = {max(40, min(1000, top_n * 2))}")
    await connection.execute("SET LOCAL hnsw.iterative_scan = relaxed_order")
    rows = await connection.fetch(
        f"""SELECT e.document_node_id::text AS node_id, n.document_id::text AS document_id,
                   1 - (e.embedding::{cast} <=> $1::{cast}) AS similarity
            FROM node_embeddings e
            JOIN document_nodes n ON n.id = e.document_node_id
            JOIN documents d ON d.id = n.document_id
              AND d.deleted_at IS NULL AND d.suspended_at IS NULL
            JOIN document_versions dv ON dv.id = n.document_version_id
              AND dv.review_status = 'approved' AND dv.retired_at IS NULL
            WHERE e.embedding_index_id = '{index_id}'
              AND n.document_version_id = ANY($2::uuid[]) AND n.review_status = 'approved'
              AND ($3::uuid[] IS NULL OR EXISTS (
                    SELECT 1 FROM document_categories dc
                    WHERE dc.document_id = n.document_id AND dc.category_id = ANY($3::uuid[])))
              AND ($4::text[] IS NULL OR d.doc_type = ANY($4::text[]))
            ORDER BY e.embedding::{cast} <=> $1::{cast}
            LIMIT $5""",
        vector_literal(query_vector), list(version_ids), list(category_ids or []) or None,
        list(doc_types or []) or None, top_n,
    )
    return [(row["node_id"], row["document_id"], float(row["similarity"])) for row in rows]


async def missing_vectors(connection: Any, index_id: UUID | None,
                          version_ids: Sequence[UUID]) -> int:
    """Approved nodes in scope without a vector in the active index (reported in scope)."""

    if index_id is None:
        return int(await connection.fetchval(
            "SELECT count(*) FROM document_nodes WHERE document_version_id = ANY($1::uuid[])"
            " AND review_status = 'approved'",
            list(version_ids),
        ))
    return int(await connection.fetchval(
        """SELECT count(*) FROM document_nodes n
           WHERE n.document_version_id = ANY($1::uuid[]) AND n.review_status = 'approved'
             AND NOT EXISTS (SELECT 1 FROM node_embeddings e
                             WHERE e.embedding_index_id = $2 AND e.document_node_id = n.id)""",
        list(version_ids), index_id,
    ))
