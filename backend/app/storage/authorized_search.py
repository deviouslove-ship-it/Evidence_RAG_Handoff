"""ACL-first authorized node search.

Eligible versions (ACL, approval, validity on ``as_of_date``, verified
provenance and scope) are resolved inside the same principal-scoped transaction
before indexed candidate retrieval. Source integrity is checked again when
hydrating candidates; the wide UNION security view is not materialized.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from typing import Any, Protocol
from uuid import UUID

from ..effectivity.store import EFFECTIVE_STATUS_LATERAL, clause_view, load_effectivity
from ..evidence.mapper import to_evidence_ref
from ..schemas import AmendmentStatus, EvidenceRef, Scope, ScopeMode
from ..vietnamese_nlp.legal_citation_parser import (
    parse_legal_references,
    reference_document_number,
)
from ..vietnamese_nlp.unicode_norm import canonical_document_number, fold_text, normalize_text
from .search_paging import number_key_sql, vi_lower_sql


async def attach_effectivity(connection: Any, refs: list[EvidenceRef], as_of: date) -> None:
    """Both effectivity axes on every evidence card (design §4, D12)."""

    if not refs:
        return
    documents, nodes, _ = await load_effectivity(
        connection, document_ids=[ref.document_id for ref in refs],
        node_ids=[ref.node_id for ref in refs], as_of=as_of,
    )
    for ref in refs:
        ref.effectivity = clause_view(
            documents.get(str(ref.document_id)), nodes.get(str(ref.node_id))
        )


ALLOWED_DOCUMENTS_SQL = """
SELECT DISTINCT d.id AS document_id
FROM documents d
WHERE d.deleted_at IS NULL AND d.suspended_at IS NULL
  AND EXISTS (
      SELECT 1 FROM document_versions dv
      WHERE dv.document_id = d.id AND dv.review_status = 'approved'
        AND dv.retired_at IS NULL
  )
  AND (
      EXISTS (
          SELECT 1
          FROM document_categories dc
          JOIN authorized_categories ac ON ac.category_id = dc.category_id
          WHERE dc.document_id = d.id
      )
      OR EXISTS (
          SELECT 1
          FROM document_acl da
          JOIN users u ON u.id = da.user_id AND u.disabled_at IS NULL
          WHERE da.document_id = d.id
            AND da.user_id = current_setting('app.user_id', true)::uuid
            AND da.can_query
      )
  )
"""


_VI_QUESTION_STOPWORDS = frozenset(
    {
        "gì",
        "nào",
        "thế",
        "sao",
        "ai",
        "đâu",
        "bao",
        "nhiêu",
        "những",
        "các",
        "là",
        "có",
        "không",
        "như",
        "vậy",
        "cho",
        "hỏi",
        "tôi",
        "xin",
        "về",
        "của",
        "tại",
        "trong",
        "theo",
        "với",
        "này",
        "đó",
    }
)


_MAX_KEYWORDS = 16
_TOKEN_RE = re.compile(r"[0-9a-zA-ZÀ-ỹĐđ]+")


def _query_tokens(query: str) -> list[str]:
    return [token.casefold() for token in _TOKEN_RE.findall(normalize_text(query))]


_ARTICLE_REFERENCE_RE = re.compile(
    r"\b(?:điều|khoản|điểm)\s+(?:\d+(?:\.\d+)?|[a-zđ])\b", re.IGNORECASE
)
_NUMBER_BODY_RE = re.compile(r"\b\d{1,4}/\d{4}(?:/[0-9A-Za-zÀ-ỹĐđ]+(?:-[0-9A-Za-zÀ-ỹĐđ]+)*)?")


def _extract_search_keywords(query: str, *, strip_references: bool = False) -> list[str]:
    """Content keywords in query order (NFC, tone-normalized, case-folded).

    Question words are dropped so "là gì"/"như thế nào" do not dominate the
    match; when nothing else is left the raw tokens are kept instead.  With
    ``strip_references`` the cited article/clause/point and document number are
    removed first: they are matched by dedicated channels, and their digits or
    "nđ"/"cp" fragments would otherwise match almost every clause.
    """

    text = normalize_text(query)
    if strip_references:
        text = _NUMBER_BODY_RE.sub(" ", _ARTICLE_REFERENCE_RE.sub(" ", text))
    tokens = _query_tokens(text)
    keywords = [tok for tok in tokens if len(tok) > 1 and tok not in _VI_QUESTION_STOPWORDS]
    return list(dict.fromkeys(keywords or tokens))[:_MAX_KEYWORDS]


def _or_tsquery(tokens: list[str]) -> str:
    # Tokens only contain letters/digits, so quoting them as lexemes is safe.
    return " | ".join(f"'{token}'" for token in tokens if token)


def query_document_number_key(raw: str) -> str | None:
    """Canonical key of the single document number cited in ``raw`` (if any)."""

    parsed = parse_legal_references(raw)
    if len(parsed.document_numbers) == 1:
        number = reference_document_number(parsed.document_numbers[0])
        if number:
            return canonical_document_number(number)
    bare = re.search(
        r"\b\d{1,4}/\d{4}/[A-Za-zÀ-ỹĐđ-]+(?:-[A-Za-zÀ-ỹĐđ]+)*\b", raw
    )
    return canonical_document_number(bare.group(0)) if bare else None


# Selects, per authorized document, the newest approved version valid on the
# requested date whose source provenance is verified.  Scope filters are applied
# here so the node query only ever touches eligible versions.
_SELECTED_VERSIONS_SQL = (
    "WITH allowed AS (" + ALLOWED_DOCUMENTS_SQL + """),
latest AS (
    SELECT DISTINCT ON (dv.document_id) dv.document_id, dv.id AS version_id
    FROM document_versions dv
    JOIN allowed a ON a.document_id = dv.document_id
    JOIN documents d ON d.id = dv.document_id AND d.deleted_at IS NULL
    WHERE dv.review_status = 'approved' AND dv.retired_at IS NULL
      AND (dv.valid_from IS NULL OR dv.valid_from <= $1::date)
      AND (dv.valid_to IS NULL OR dv.valid_to > $1::date)
      AND ($2::uuid[] IS NULL OR EXISTS (
            SELECT 1 FROM document_categories scoped
            WHERE scoped.document_id = dv.document_id
              AND scoped.category_id = ANY($2::uuid[])))
      AND ($3::text[] IS NULL OR d.doc_type = ANY($3::text[]))
    ORDER BY dv.document_id, dv.version_number DESC
)
SELECT l.version_id
FROM latest l
JOIN source_provenance prov
  ON prov.document_version_id = l.version_id AND prov.verified_at IS NOT NULL
"""
)

_DOC_NUMBER_KEY = number_key_sql("d.document_number")

# Parameters:
#  $1 eligible version ids   $2 as_of date        $3 keywords (accented)
#  $4 keywords (folded)      $5 OR tsquery        $6 OR tsquery (folded)
#  $7 document number key    $8 article regex     $9 per-channel candidate cap
#  $10 result limit          $11 requested category scope (outside_scope flag)
#
# Candidate channels are bounded GIN/metadata lookups.  The wide OR channel and
# the legacy label channel run only when the precise channels found fewer
# candidates than requested.  Expensive work (tsvector, ranking, span checks)
# is done on the bounded candidate set only.  ``$8`` matches the raw label with
# explicit case classes, so no per-label lower-casing is needed for it.
@lru_cache(maxsize=2)
def _chat_search_sql(builtin_unicode: bool) -> str:
    def lower(expression: str) -> str:
        return vi_lower_sql(expression, builtin_unicode=builtin_unicode)

    return f"""
WITH number_docs AS MATERIALIZED (
    SELECT dv.id AS version_id
    FROM document_versions dv
    JOIN documents d ON d.id = dv.document_id
    WHERE dv.id = ANY($1::uuid[]) AND $7::text <> '' AND {_DOC_NUMBER_KEY} = $7::text
), title_docs AS MATERIALIZED (
    SELECT dv.id AS version_id
    FROM document_versions dv
    JOIN documents d ON d.id = dv.document_id
    WHERE dv.id = ANY($1::uuid[]) AND $3::text <> ''
      AND to_tsvector('simple'::regconfig,
              {lower("concat_ws(' ', d.document_number, d.title)")})
          @@ plainto_tsquery('simple'::regconfig, $3::text)
), primary_ids AS MATERIALIZED (
    (SELECT n.id, 1 AS channel
     FROM document_nodes n
     WHERE n.document_version_id IN (SELECT version_id FROM number_docs)
       AND n.review_status = 'approved'
     ORDER BY ($8::text <> '' AND COALESCE(n.label_original ~ $8::text, FALSE)) DESC,
              n.page_start NULLS LAST, n.id
     LIMIT $9)
    UNION ALL
    (SELECT n.id, 2
     FROM document_nodes n
     WHERE $3::text <> ''
       AND n.document_version_id = ANY($1::uuid[]) AND n.review_status = 'approved'
       AND (to_tsvector('simple'::regconfig, n.text_indexed)
                @@ plainto_tsquery('simple'::regconfig, $3::text)
         OR to_tsvector('simple'::regconfig, n.text_folded)
                @@ plainto_tsquery('simple'::regconfig, $4::text))
     LIMIT $9)
    UNION ALL
    (SELECT n.id, 3
     FROM document_nodes n
     WHERE n.document_version_id IN (SELECT version_id FROM title_docs)
       AND n.review_status = 'approved'
     ORDER BY n.page_start NULLS LAST, n.id
     LIMIT $9)
    UNION ALL
    -- "Điều N" without a (known) document number: every eligible article N.
    (SELECT n.id, 6
     FROM document_nodes n
     WHERE $8::text <> '' AND NOT EXISTS (SELECT 1 FROM number_docs)
       AND n.document_version_id = ANY($1::uuid[]) AND n.review_status = 'approved'
       AND n.label_original IS NOT NULL AND n.label_original ~ $8::text
     LIMIT $9)
), primary_count AS (
    SELECT count(DISTINCT id) AS found FROM primary_ids
), fallback_ids AS MATERIALIZED (
    (SELECT n.id, 4 AS channel
     FROM document_nodes n
     WHERE (SELECT found FROM primary_count) < $10 AND $5::text <> ''
       AND n.document_version_id = ANY($1::uuid[]) AND n.review_status = 'approved'
       AND (to_tsvector('simple'::regconfig, n.text_indexed)
                @@ to_tsquery('simple'::regconfig, $5::text)
         OR to_tsvector('simple'::regconfig, n.text_folded)
                @@ to_tsquery('simple'::regconfig, $6::text))
     LIMIT $9)
    UNION ALL
    -- Old records may not have their label in text_indexed yet.
    (SELECT n.id, 5
     FROM document_nodes n
     WHERE (SELECT found FROM primary_count) < $10 AND $5::text <> ''
       AND n.document_version_id = ANY($1::uuid[]) AND n.review_status = 'approved'
       AND n.label_original IS NOT NULL
       AND position(n.label_original in n.text_indexed) = 0
       AND to_tsvector('simple'::regconfig, {lower('n.label_original')})
           @@ to_tsquery('simple'::regconfig, $5::text)
     LIMIT $9)
), candidate_ids AS MATERIALIZED (
    SELECT id AS node_id, min(channel) AS channel
    FROM (SELECT id, channel FROM primary_ids
          UNION ALL SELECT id, channel FROM fallback_ids) found
    GROUP BY id
), scored AS MATERIALIZED (
    SELECT
        n.id AS node_id, d.id AS document_id, dv.id AS document_version_id,
        d.document_number, d.title,
        COALESCE(n.citation_label, n.label_original, n.node_type::text) AS label,
        n.text_original,
        COALESCE(src.page_number, n.page_start) AS original_page,
        n.path,
        dv.original_file_sha256,
        COALESCE(eff.status, 'unknown') AS amendment_state,
        ($7::text <> '' AND {_DOC_NUMBER_KEY} = $7::text) AS number_match,
        ($8::text <> '' AND COALESCE(n.label_original ~ $8::text, FALSE)) AS article_match,
        ($3::text <> '' AND (
            lex.exact @@ plainto_tsquery('simple'::regconfig, $3::text)
            OR lex.folded @@ plainto_tsquery('simple'::regconfig, $4::text)
            OR ci.channel = 3)) AS all_terms,
        ($3::text <> '' AND lex.exact @@ plainto_tsquery('simple'::regconfig, $3::text))
            AS all_terms_exact,
        CASE WHEN $5::text = '' THEN 0 ELSE
            ts_rank_cd(lex.exact, to_tsquery('simple'::regconfig, $5::text))
            + ts_rank_cd(lex.folded, to_tsquery('simple'::regconfig, $6::text))
        END AS score
    FROM candidate_ids ci
    JOIN document_nodes n ON n.id = ci.node_id
    JOIN document_versions dv ON dv.id = n.document_version_id
    JOIN documents d ON d.id = n.document_id
      AND d.deleted_at IS NULL AND d.suspended_at IS NULL
    -- Per-candidate span/page verification; LIMIT keeps it a keyed lookup.
    CROSS JOIN LATERAL (
        SELECT sp.page_number
        FROM source_spans ss
        JOIN source_pages sp ON sp.id = ss.page_id
        -- A clause continuing on the next page is checked by its first-page span
        -- here; approval and citation opening check every span (node_source_text_valid).
        WHERE ss.id = n.source_span_id AND (ss.text_original = n.text_original
               OR (n.page_end > n.page_start
                   AND starts_with(n.text_original, ss.text_original || E'\n')))
          AND sp.document_version_id = n.document_version_id
          AND sp.text_quality = 'usable'
          AND substring(sp.text_original FROM ss.original_offset + 1
                        FOR ss.original_length) = ss.text_original
        LIMIT 1
    ) src
    CROSS JOIN LATERAL (
        -- Computed once per candidate and reused for matching and ranking.
        SELECT
            to_tsvector('simple'::regconfig, {lower(
                "concat_ws(' ', d.document_number, d.title, n.label_original, n.text_indexed)"
            )}) AS exact,
            to_tsvector('simple'::regconfig, n.text_folded) AS folded
    ) lex
    LEFT JOIN LATERAL ({EFFECTIVE_STATUS_LATERAL.format(as_of="$2")}
    ) eff ON TRUE
    WHERE n.review_status = 'approved' AND dv.id = ANY($1::uuid[])
      AND dv.review_status = 'approved' AND dv.retired_at IS NULL
), ranked AS (
    SELECT * FROM scored
    ORDER BY (number_match AND article_match) DESC, number_match DESC,
             article_match DESC, all_terms DESC, all_terms_exact DESC,
             score DESC, document_id, original_page NULLS LAST, path, node_id
    LIMIT $10
)
SELECT
    r.node_id::text AS node_id, r.document_id::text AS document_id,
    r.document_version_id::text AS document_version_id,
    r.document_number, r.title, r.label, r.text_original, r.original_page,
    r.original_file_sha256, r.amendment_state,
    COALESCE(ARRAY(
        SELECT dc.category_id::text FROM document_categories dc
        WHERE dc.document_id = r.document_id
    ), ARRAY[]::text[]) AS category_ids,
    CASE WHEN $11::uuid[] IS NULL THEN FALSE ELSE EXISTS (
        SELECT 1 FROM document_categories dc
        WHERE dc.document_id = r.document_id
          AND NOT (dc.category_id = ANY($11::uuid[]))
    ) END AS outside_scope
FROM ranked r
ORDER BY (r.number_match AND r.article_match) DESC, r.number_match DESC,
         r.article_match DESC, r.all_terms DESC, r.all_terms_exact DESC,
         r.score DESC, r.document_id, r.original_page NULLS LAST, r.path, r.node_id
"""


class RetrievalTimeoutError(TimeoutError):
    """Evidence retrieval exceeded its database budget."""


@dataclass(frozen=True)
class AuthorizedNode:
    evidence_id: str
    document_id: UUID
    document_version_id: UUID
    node_id: UUID
    document_number: str | None
    title: str
    label: str
    quote_exact: str
    page: int | None
    source_hash: str
    as_of_date: date
    amendment_state: AmendmentStatus
    outside_scope: bool = False
    category_ids: tuple[UUID, ...] = ()

    @property
    def viewer_url(self) -> str:
        return (
            f"/api/v1/citations/{self.evidence_id}/pdf"
            f"?as_of_date={self.as_of_date.isoformat()}"
        )


class AuthorizedNodeSearch(Protocol):
    async def search(
        self,
        *,
        principal_id: UUID,
        scope: Scope,
        query: str,
        limit: int = 12,
    ) -> list[EvidenceRef]: ...


class PostgresAuthorizedNodeSearch:
    """Chat evidence retrieval over approved, source-verified clauses.

    Retrieval is bounded: the number of concurrent database lookups, the
    statement time and the number of candidates per channel are all capped, so
    a broad question cannot occupy the connection pool or the database CPU.
    """

    CANDIDATES_PER_CHANNEL = 1500

    def __init__(
        self,
        pool: Any,
        *,
        statement_timeout_ms: int = 5000,
        max_concurrency: int = 4,
        candidates_per_channel: int = CANDIDATES_PER_CHANNEL,
    ) -> None:
        self._pool = pool
        self._statement_timeout_ms = max(100, min(int(statement_timeout_ms), 60000))
        self._slots = asyncio.Semaphore(max(1, int(max_concurrency)))
        self._candidates_per_channel = max(50, int(candidates_per_channel))
        # Detected once: PostgreSQL 17+ ships the fast ``pg_c_utf8`` collation.
        self._unicode_lower: bool | None = None

    async def __call__(
        self,
        *,
        principal_id: UUID,
        scope: Scope,
        query: str,
        limit: int = 12,
    ) -> list[EvidenceRef]:
        return await self.search(
            principal_id=principal_id, scope=scope, query=query, limit=limit
        )

    async def search(
        self,
        *,
        principal_id: UUID,
        scope: Scope,
        query: str,
        limit: int = 12,
    ) -> list[EvidenceRef]:
        if scope.scope_mode == ScopeMode.SELECTED and not scope.category_ids:
            raise ValueError("CATEGORY_REQUIRED")
        category_ids = list(scope.category_ids)
        document_types = list(scope.document_types)
        as_of_date = scope.as_of_date
        parsed = parse_legal_references(query)
        number_key = query_document_number_key(query) or ""
        article = parsed.references[0].article if parsed.is_unique_local_reference else None
        article_number = re.search(r"\d+(?:\.\d+)?$", article) if article else None
        # Explicit case classes: PostgreSQL ``~*`` does not fold "Đ"/"Ề" under
        # the C locale, so "ĐIỀU 5" and "điều 5" both need to match here.
        article_pattern = (
            rf"^[[:space:]]*[ĐđÐ][Ii][Ềề][Uu][[:space:]]+{re.escape(article_number.group())}"
            r"([.]([^0-9]|$)|[[:space:]]|$)"
            if article_number
            else ""
        )
        keywords = _extract_search_keywords(
            query, strip_references=bool(number_key or article_pattern)
        )
        if not keywords and not number_key and not article_pattern:
            return []
        folded_keywords = list(dict.fromkeys(fold_text(token) for token in keywords))
        limit = min(max(limit, 1), 50)
        try:
            async with self._slots:
                async with asyncio.timeout(self._statement_timeout_ms / 1000 + 1):
                    async with self._pool.acquire() as connection:
                        async with connection.transaction():
                            await connection.execute(
                                "SELECT set_config('app.user_id', $1, true)",
                                str(principal_id),
                            )
                            await connection.execute(
                                f"SET LOCAL statement_timeout = {self._statement_timeout_ms}"
                            )
                            # Generic cached plans ignore the actual terms/ids.
                            await connection.execute(
                                "SET LOCAL plan_cache_mode = force_custom_plan"
                            )
                            versions = [
                                row["version_id"]
                                for row in await connection.fetch(
                                    _SELECTED_VERSIONS_SQL,
                                    as_of_date,
                                    category_ids or None,
                                    document_types or None,
                                )
                            ]
                            if not versions:
                                return []
                            if self._unicode_lower is None:
                                self._unicode_lower = bool(await connection.fetchval(
                                    "SELECT EXISTS (SELECT 1 FROM pg_collation"
                                    " WHERE collname = 'pg_c_utf8')"
                                ))
                            rows = await connection.fetch(
                                _chat_search_sql(self._unicode_lower),
                                versions,
                                as_of_date,
                                " ".join(keywords),
                                " ".join(folded_keywords),
                                _or_tsquery(keywords),
                                _or_tsquery(folded_keywords),
                                number_key,
                                article_pattern,
                                self._candidates_per_channel,
                                limit,
                                category_ids or None,
                            )
                            refs = [to_evidence_ref(self._to_node(row, as_of_date))
                                    for row in rows]
                            await attach_effectivity(connection, refs, as_of_date)
        except TimeoutError as exc:
            raise RetrievalTimeoutError("EVIDENCE_RETRIEVAL_TIMEOUT") from exc
        except Exception as exc:
            if exc.__class__.__name__ == "QueryCanceledError":
                raise RetrievalTimeoutError("EVIDENCE_RETRIEVAL_TIMEOUT") from exc
            raise
        return refs

    @staticmethod
    def _to_node(row: Any, as_of_date: date) -> AuthorizedNode:
        return AuthorizedNode(
            evidence_id=f"ev_{row['node_id']}",
            document_id=UUID(row["document_id"]),
            document_version_id=UUID(row["document_version_id"]),
            node_id=UUID(row["node_id"]),
            document_number=row["document_number"],
            title=row["title"],
            label=row["label"],
            quote_exact=row["text_original"],
            page=row["original_page"],
            source_hash=row["original_file_sha256"],
            as_of_date=as_of_date,
            amendment_state=AmendmentStatus(row["amendment_state"]),
            outside_scope=bool(row["outside_scope"]),
            category_ids=tuple(UUID(item) for item in (row["category_ids"] or ())),
        )


class InMemoryAuthorizedNodeSearch:
    """Deterministic test double with the same ACL boundary."""

    def __init__(
        self,
        nodes: Sequence[AuthorizedNode],
        principal_categories: dict[UUID, set[UUID]],
    ) -> None:
        self._nodes = list(nodes)
        self._principal_categories = principal_categories

    async def search(
        self,
        *,
        principal_id: UUID,
        scope: Scope,
        query: str,
        limit: int = 12,
    ) -> list[EvidenceRef]:
        allowed = self._principal_categories.get(principal_id, set())
        requested = set(scope.category_ids)
        if scope.scope_mode == ScopeMode.SELECTED:
            if not requested:
                raise ValueError("CATEGORY_REQUIRED")
            if not requested.issubset(allowed):
                return []
        terms = [term.casefold() for term in query.split() if term]
        parsed = parse_legal_references(query)
        reference_number = (
            reference_document_number(parsed.document_numbers[0])
            if len(parsed.document_numbers) == 1
            else None
        )
        canonical_number = (
            canonical_document_number(reference_number) if reference_number else None
        )
        article = parsed.references[0].article if parsed.is_unique_local_reference else None
        article_pattern = (
            re.compile(
                r"^\s*" + re.escape(article).replace(r"\ ", r"\s+") + r"(?:\.(?!\d)|\s|$)",
                re.I,
            )
            if article
            else None
        )
        ranked: list[tuple[tuple[bool, bool, bool, int], AuthorizedNode]] = []
        for node in self._nodes:
            node_categories = set(node.category_ids)
            if not node_categories.intersection(allowed):
                continue
            if scope.scope_mode == ScopeMode.SELECTED and not node_categories.intersection(
                requested
            ):
                continue
            haystack = (
                f"{node.document_number or ''} {node.title} {node.label} {node.quote_exact}"
            ).casefold()
            score = sum(term in haystack for term in terms)
            if score:
                document_match = bool(
                    canonical_number
                    and node.document_number
                    and canonical_document_number(node.document_number) == canonical_number
                )
                article_match = bool(article_pattern and article_pattern.search(node.label))
                ranked.append(
                    (
                        (document_match and article_match, document_match, article_match, score),
                        node,
                    )
                )
        ranked.sort(
            key=lambda item: (
                -int(item[0][0]),
                -int(item[0][1]),
                -int(item[0][2]),
                -item[0][3],
                str(item[1].node_id),
            )
        )
        return [to_evidence_ref(node) for _, node in ranked[:limit]]
