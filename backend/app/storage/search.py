"""Search v1: authorized document/clause search over approved sources.

Design decisions (see docs/architecture-decisions/ADR-005-search-v1.md):

* PostgreSQL FTS only; no tokenizer, embedding or external search engine.
* ``text_indexed`` is the indexed content (breadcrumb + title + number + label +
  node text) and ``text_folded`` is the accent-folded content.  The two GIN
  indexes in migration 0006 must match the expressions below exactly.
* ``exact_phrase`` is only assigned after the phrase is verified on the node's
  own content, never on ``text_indexed`` alone.
* Chat keeps its historical behaviour when the question has no quoted phrase;
  the legacy search is delegated unchanged.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any
from uuid import UUID

from ..audit import append_audit
from ..effectivity.store import (
    CLAUSE_LEVEL_WARNING,
    EFFECTIVE_STATUS_LATERAL,
    clause_view,
    load_effectivity,
)
from ..schemas import (
    AmendmentStatus,
    EvidenceRef,
    ScopeMode,
    SearchApproximate,
    SearchClause,
    SearchDocument,
    SearchEmptyReason,
    SearchHighlight,
    SearchMatchType,
    SearchQueryInfo,
    SearchResponse,
    SearchTotals,
)
from ..vietnamese_nlp.unicode_norm import (
    NORMALIZER_REVISION,
    canonical_document_number,
    fold_text,
    normalize_text,
)
from .authorized_search import (
    ALLOWED_DOCUMENTS_SQL,
    PostgresAuthorizedNodeSearch,
    query_document_number_key,
)
from .search_paging import ANY_TERM_TSQUERY, document_page_sql

logger = logging.getLogger(__name__)

MAX_QUERY_CHARS = 500
MAX_TERMS = 20
MAX_PHRASE_CHARS = 200
MAX_PAGE_SIZE = 50
MAX_CANDIDATES = 5000
CLAUSES_PER_DOCUMENT = 5

_TOKEN_RE = re.compile(r"[0-9a-zA-ZÀ-ỹĐđ]+")


class SearchQueryError(ValueError):
    """A validation/rate/timeout error mapped to a stable API error code."""

    def __init__(self, code: str, status_code: int = 422) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class SearchQuery:
    original: str
    mode: str  # auto | phrase | keywords (resolved)
    phrase: str | None
    phrase_tokens: tuple[str, ...]
    terms: tuple[str, ...]
    document_number: str | None
    normalization_revision: str = NORMALIZER_REVISION

    @property
    def is_phrase(self) -> bool:
        return self.phrase is not None

    @property
    def terms_text(self) -> str:
        return " ".join(self.terms)

    @property
    def phrase_normalized(self) -> str:
        return _normalize_content(self.phrase) if self.phrase else ""

    @property
    def phrase_folded(self) -> str:
        return _fold_content(self.phrase) if self.phrase else ""


@dataclass
class SearchHit:
    node_id: str
    document_id: str
    document_version_id: str
    document_number: str | None
    title: str
    doc_type: str
    issuing_body: str | None
    official_url: str | None
    source_hash: str
    label: str
    page: int | None
    quote_exact: str
    text_normalized: str
    text_folded: str
    amendment_state: str
    score: float
    tier: int
    match_type: SearchMatchType
    snippet: str = ""
    snippet_start: int = 0
    highlights: list[SearchHighlight] = field(default_factory=list)


@dataclass(frozen=True)
class SearchPage:
    response: SearchResponse


def _tokens(text: str) -> list[str]:
    return [token.casefold() for token in _TOKEN_RE.findall(normalize_text(text))]


def _normalize_content(text: str) -> str:
    """Normalize content/phrase for substring verification (tone + NFC + case)."""

    return " ".join(_TOKEN_RE.findall(normalize_text(text).casefold()))


def _fold_content(text: str) -> str:
    return " ".join(_TOKEN_RE.findall(fold_text(text).casefold()))


def _verify_phrase(content: str, phrase: str) -> bool:
    """True only when the normalized phrase appears as whole tokens."""

    if not phrase:
        return False
    content_norm = _normalize_content(content)
    phrase_norm = _normalize_content(phrase)
    if not phrase_norm:
        return False
    return f" {phrase_norm} " in f" {content_norm} "


def _quoted_phrase(raw: str) -> str | None:
    match = re.search(r"[\"“]([^\"”]+)[\"”]", raw)
    if match is None:
        return None
    value = match.group(1).strip()
    return value or None


def parse_search_query(raw: str, mode: str = "auto") -> SearchQuery:
    """Parse untrusted user text without ever building a tsquery string.

    Quoted text is the only way a user can request a phrase; the phrase is later
    passed as a bind parameter to ``phraseto_tsquery``.
    """

    original = raw.strip()
    if not original:
        raise SearchQueryError("QUERY_EMPTY")
    if len(original) > MAX_QUERY_CHARS:
        raise SearchQueryError("QUERY_TOO_LONG")

    quoted = _quoted_phrase(original)
    resolved = mode
    if mode not in {"auto", "phrase", "keywords"}:
        raise SearchQueryError("INVALID_REQUEST")
    if mode == "auto":
        resolved = "phrase" if quoted is not None else "keywords"
    if resolved == "phrase":
        phrase = quoted or original
        if len(phrase) > MAX_PHRASE_CHARS:
            raise SearchQueryError("QUERY_TOO_LONG")
        phrase_tokens = tuple(dict.fromkeys(_tokens(phrase)))
        terms = tuple(dict.fromkeys(_tokens(original)))
        if not terms:
            raise SearchQueryError("QUERY_EMPTY")
        if len(terms) > MAX_TERMS:
            raise SearchQueryError("TOO_MANY_TERMS")
        return SearchQuery(
            original=original,
            mode="phrase",
            phrase=phrase,
            phrase_tokens=phrase_tokens,
            terms=terms,
            document_number=_query_document_number(original),
        )

    terms = tuple(dict.fromkeys(_tokens(original)))
    if not terms:
        raise SearchQueryError("QUERY_EMPTY")
    if len(terms) > MAX_TERMS:
        raise SearchQueryError("TOO_MANY_TERMS")
    return SearchQuery(
        original=original,
        mode="keywords",
        phrase=None,
        phrase_tokens=(),
        terms=terms,
        document_number=_query_document_number(original),
    )


def _query_document_number(raw: str) -> str | None:
    return query_document_number_key(raw)


def _phrase_regex(phrase: str) -> re.Pattern[str] | None:
    tokens = _tokens(phrase)
    if not tokens:
        return None
    separator = r"[\s\W_]+"
    pattern = separator.join(re.escape(token) for token in tokens)
    return re.compile(rf"(?<!\w){pattern}(?!\w)", re.IGNORECASE)


def _find_phrase_span(original: str, phrase: str) -> tuple[int, int] | None:
    regex = _phrase_regex(phrase)
    if regex is None:
        return None
    match = regex.search(original)
    if match is None:
        return None
    return match.start(), match.end()


def _find_term_spans(
    original: str, terms: tuple[str, ...], limit: int = 12
) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for term in terms:
        if len(term) < 2:
            continue
        for match in re.finditer(rf"(?<!\w){re.escape(term)}(?!\w)", original, re.IGNORECASE):
            spans.append((match.start(), match.end()))
            if len(spans) >= limit:
                return spans
    return spans


def _build_snippet(
    original: str, spans: list[tuple[int, int]]
) -> tuple[str, int, list[SearchHighlight]]:
    """Return snippet, its start offset in ``original`` and absolute highlights.

    When the exact span cannot be located the caller receives an empty highlight
    list, which the UI must render without any <mark>.
    """

    if not spans:
        snippet = re.sub(r"\s+", " ", original).strip()
        if len(snippet) > 240:
            snippet = snippet[:237].rstrip() + "…"
        return snippet, 0, []

    ordered = sorted(spans)
    start = max(0, ordered[0][0] - 60)
    end = min(len(original), ordered[-1][1] + 90)
    # Keep a bounded window without splitting the final highlight.
    if end - start > 320:
        end = min(len(original), start + 320)
    snippet = original[start:end]
    highlights: list[SearchHighlight] = []
    for span_start, span_end in ordered:
        if span_end <= start or span_start >= end:
            continue
        highlights.append(SearchHighlight(start=span_start, end=span_end))
    return snippet, start, highlights


def _row_to_hit(row: Any, tier: int, score: float) -> SearchHit:
    return SearchHit(
        node_id=str(row["node_id"]),
        document_id=str(row["document_id"]),
        document_version_id=str(row["document_version_id"]),
        document_number=row["document_number"],
        title=row["title"],
        doc_type=row["doc_type"],
        issuing_body=row["issuing_body"],
        official_url=row["official_url"],
        source_hash=row["source_hash"],
        label=row["label"] or "",
        page=row["page_number"],
        quote_exact=row["text_original"],
        text_normalized=row["text_normalized"],
        text_folded=row["text_folded"],
        amendment_state=str(row["amendment_state"]),
        score=float(score or 0.0),
        tier=tier,
        match_type={
            1: SearchMatchType.EXACT_PHRASE,
            2: SearchMatchType.PHRASE_FOLDED,
            3: SearchMatchType.ALL_TERMS,
            4: SearchMatchType.ANY_TERM,
        }[tier],
    )


# Newest approved version per authorized document that is valid on the
# requested date and has verified provenance.  Resolved in its own statement and
# passed to the page query as an array: as a join inside the page query the
# planner badly under-estimated matching nodes and re-scanned the version list
# once per node (about 30 s for a term present in 100,000 nodes).
_SELECTED_VERSIONS_SQL = """
SELECT sv.version_id
FROM (
    SELECT DISTINCT ON (dv.document_id) dv.document_id, dv.id AS version_id
    FROM document_versions dv
    WHERE dv.review_status = 'approved'
      AND dv.document_id = ANY($1::uuid[])
      AND (dv.valid_from IS NULL OR dv.valid_from <= $2::date)
      AND (dv.valid_to IS NULL OR dv.valid_to > $2::date)
    ORDER BY dv.document_id, dv.version_number DESC
) sv
JOIN source_provenance prov
  ON prov.document_version_id = sv.version_id AND prov.verified_at IS NOT NULL
"""

# $11 holds the version ids returned by ``_SELECTED_VERSIONS_SQL``; nodes are
# restricted to them once, and the version row is then a primary-key lookup.
_BASE_SQL = """
WITH base AS (
    SELECT n.id AS node_id, n.document_id, n.document_version_id,
           COALESCE(n.citation_label, n.label_original) AS label,
           n.text_original, n.text_normalized,
           n.text_folded, n.text_indexed, n.page_start,
           d.document_number, d.title, d.doc_type, d.issuing_body,
           sv.official_url, sv.original_file_sha256 AS source_hash,
           COALESCE(sp.page_number, n.page_start) AS page_number,
           COALESCE(eff.status, 'unknown') AS amendment_state
    FROM document_nodes n
    JOIN document_versions sv ON sv.id = n.document_version_id
    JOIN documents d ON d.id = n.document_id AND d.deleted_at IS NULL
    JOIN source_spans ss
      ON ss.id = n.source_span_id AND (ss.text_original = n.text_original
          OR (n.page_end > n.page_start
              AND starts_with(n.text_original, ss.text_original || E'\n')))
    JOIN source_pages sp
      ON sp.id = ss.page_id AND sp.document_version_id = sv.id
     AND sp.text_quality = 'usable'
     AND substring(sp.text_original FROM ss.original_offset + 1
                   FOR ss.original_length) = ss.text_original
    LEFT JOIN LATERAL (""" + EFFECTIVE_STATUS_LATERAL.format(as_of="$7") + """
    ) eff ON TRUE
    WHERE n.document_version_id = ANY($11::uuid[])
      AND n.review_status = 'approved'
      AND ($4::uuid[] IS NULL OR EXISTS (
              SELECT 1 FROM document_categories dc
              WHERE dc.document_id = n.document_id
                AND dc.category_id = ANY($4::uuid[])))
      AND ($5::text[] IS NULL OR d.doc_type = ANY($5::text[]))
      AND ($6::text IS NULL OR position(lower($6) in lower(COALESCE(d.issuing_body, ''))) > 0)
      AND (NOT $8::boolean OR COALESCE(eff.status, 'unknown') = 'active')
      -- Type anchors: every prepared statement receives all 11 parameters, so
      -- parameters unused by a specific tier still need a declared type.
      AND ($1::text IS NULL OR TRUE)
      AND ($2::text IS NULL OR TRUE)
      AND ($3::text[] IS NULL OR TRUE)
      AND ($9::int IS NULL OR TRUE)
      AND ($10::text IS NULL OR TRUE)
)
"""

# One OR-tsquery over all terms lets PostgreSQL use the GIN indexes; a per-term
# EXISTS re-parsed every clause once per term (> 5 s on 100,000 nodes when no
# clause matched).
_APPROX_WHERE_SQL = f"""
WHERE $3::text[] IS NOT NULL
      AND (to_tsvector('simple'::regconfig, base.text_indexed) @@ {ANY_TERM_TSQUERY}
        OR to_tsvector('simple'::regconfig, base.text_folded) @@ {ANY_TERM_TSQUERY})
      AND NOT (
            ($1::text <> '' AND to_tsvector('simple'::regconfig, base.text_indexed)
                 @@ phraseto_tsquery('simple'::regconfig, $1))
         OR ($2::text <> '' AND to_tsvector('simple'::regconfig, base.text_folded)
                 @@ phraseto_tsquery('simple'::regconfig, $2))
         OR ($10::text <> '' AND to_tsvector('simple'::regconfig, base.text_indexed)
                 @@ plainto_tsquery('simple'::regconfig, $10))
      )
"""

_APPROX_COUNT_SQL_TEMPLATE = _BASE_SQL + """
SELECT count(*) AS approximate
FROM (
    SELECT 1 FROM base
""" + _APPROX_WHERE_SQL + """
LIMIT {limit}
) capped
"""

_SNAPSHOT_SQL = """
SELECT EXISTS (SELECT 1 FROM effectivity_snapshot_revisions WHERE is_active) AS is_active
"""




class SearchService:
    def __init__(
        self,
        pool: Any,
        *,
        statement_timeout_ms: int = 5000,
        max_page_depth: int = 1000,
        clauses_per_document: int = CLAUSES_PER_DOCUMENT,
        approximate_count_limit: int = 500,
        audit_enabled: bool = True,
        count_cap: int = 8000,
    ) -> None:
        self._pool = pool
        self._search_slots = asyncio.Semaphore(4)
        self._statement_timeout_ms = max(100, min(int(statement_timeout_ms), 60000))
        self._max_page_depth = max(50, int(max_page_depth))
        self._clauses_per_document = max(1, int(clauses_per_document))
        self._approximate_count_limit = max(1, min(int(approximate_count_limit), 5000))
        self._audit_enabled = audit_enabled
        self._count_cap = max(1, int(count_cap))
        self._legacy = PostgresAuthorizedNodeSearch(
            pool, statement_timeout_ms=self._statement_timeout_ms
        )

    # ------------------------------------------------------------------ chat
    async def search_clauses(
        self,
        *,
        principal_id: UUID,
        scope: Any,
        query: str,
        limit: int = 12,
    ) -> list[EvidenceRef]:
        """Chat adapter: only quoted input changes behaviour (phrase mode)."""

        if (
            getattr(scope, "scope_mode", None) == ScopeMode.SELECTED
            and not getattr(scope, "category_ids", None)
        ):
            raise ValueError("CATEGORY_REQUIRED")
        phrase = _quoted_phrase(query)
        if phrase is None:
            return await self._legacy.search(
                principal_id=principal_id, scope=scope, query=query, limit=limit
            )
        parsed = replace(
            parse_search_query(f'"{phrase}"', mode="phrase"),
            document_number=_query_document_number(query),
        )
        requested = max(1, min(limit, MAX_PAGE_SIZE))
        documents, _, _, _, _ = await self._read_document_page(
            principal_id=principal_id, parsed=parsed,
            category_ids=list(scope.category_ids) or None,
            doc_types=list(scope.document_types) or None,
            issuing_body=None, as_of_date=scope.as_of_date, only_active=False,
            page=1, page_size=requested, clause_page=1, clause_page_size=requested,
            approximate_only=False, include_approximate_count=False,
        )
        if not documents:
            return await self._legacy.search(
                principal_id=principal_id, scope=scope, query=query, limit=limit
            )
        refs: list[EvidenceRef] = []
        for document in documents:
            for clause in document.clauses:
                refs.append(
                    EvidenceRef(
                        evidence_id=f"ev_{clause.node_id}",
                        document_id=UUID(document.document_id),
                        document_version_id=UUID(document.document_version_id),
                        node_id=UUID(clause.node_id),
                        document_number=document.document_number,
                        title=document.title,
                        label=clause.label,
                        quote_exact=clause.quote_exact,
                        page=clause.page,
                        source_hash=clause.source_hash,
                        as_of_date=scope.as_of_date,
                        amendment_state=clause.amendment_state,
                        viewer_url=clause.viewer_url,
                        effectivity=clause.effectivity,
                    )
                )
        return refs[:limit]

    async def __call__(
        self,
        *,
        principal_id: UUID,
        scope: Any,
        query: str,
        limit: int = 12,
    ) -> list[EvidenceRef]:
        return await self.search_clauses(
            principal_id=principal_id, scope=scope, query=query, limit=limit
        )

    # --------------------------------------------------------------- search
    async def search_documents(
        self,
        *,
        principal_id: UUID,
        raw_query: str,
        mode: str = "auto",
        category_ids: list[UUID] | None = None,
        doc_types: list[str] | None = None,
        issuing_body: str | None = None,
        as_of_date: date | None = None,
        only_active: bool = False,
        page: int = 1,
        page_size: int = 20,
        clause_page: int = 1,
        clause_page_size: int = 5,
        include_approximate_count: bool = True,
    ) -> SearchResponse:
        started = time.perf_counter()
        parsed = parse_search_query(raw_query, mode)
        as_of = as_of_date or date.today()
        page = max(1, int(page))
        page_size = max(1, min(int(page_size), MAX_PAGE_SIZE))
        clause_page = max(1, int(clause_page))
        clause_page_size = max(1, min(int(clause_page_size), MAX_PAGE_SIZE))
        if page * page_size > self._max_page_depth:
            raise SearchQueryError("PAGE_TOO_DEEP")

        results, totals, authorized_documents, snapshot_ok, phrase_found = (
            await self._read_document_page(
                principal_id=principal_id, parsed=parsed, category_ids=category_ids,
                doc_types=doc_types, issuing_body=issuing_body, as_of_date=as_of,
                only_active=only_active, page=page, page_size=page_size,
                clause_page=clause_page, clause_page_size=clause_page_size,
                approximate_only=False, include_approximate_count=include_approximate_count,
            )
        )
        approximate_total = totals["approximate"]
        capped = bool(totals["capped"])
        empty_reason = self._empty_reason(
            parsed=parsed,
            results=results,
            total_clauses=totals["clauses"],
            authorized_documents=authorized_documents,
            # Beyond the cap an exact phrase may exist among unexamined clauses.
            phrase_found=phrase_found or capped,
        )
        response = SearchResponse(
            query=self._query_info(parsed),
            phrase_found=phrase_found,
            totals=SearchTotals(
                documents=totals["documents"],
                clauses=totals["clauses"],
                approximate_matches_hidden=approximate_total,
                capped=capped,
                count_cap=self._count_cap,
            ),
            page=page,
            page_size=page_size,
            has_more=page * page_size < totals["documents"],
            effectivity_snapshot_status="ok" if snapshot_ok else "stale",
            results=results,
            approximate=SearchApproximate(
                collapsed=approximate_total > 0,
                total_clauses=approximate_total,
                capped=approximate_total >= self._approximate_count_limit,
            ),
            empty_reason=empty_reason,
            clause_level_warning=_clause_level_warning(results),
            data_date=_data_date(results),
        )
        await self._audit(
            principal_id,
            parsed,
            response,
            started,
            filters={
                "category_ids": [str(item) for item in (category_ids or [])],
                "doc_types": list(doc_types or []),
                "issuing_body": issuing_body or None,
                "as_of_date": as_of.isoformat(),
                "only_active": bool(only_active),
            },
        )
        return response

    async def search_approximate(
        self,
        *,
        principal_id: UUID,
        raw_query: str,
        mode: str = "auto",
        category_ids: list[UUID] | None = None,
        doc_types: list[str] | None = None,
        issuing_body: str | None = None,
        as_of_date: date | None = None,
        only_active: bool = False,
        page: int = 1,
        page_size: int = 20,
        clause_page: int = 1,
        clause_page_size: int = 5,
    ) -> SearchResponse:
        parsed = parse_search_query(raw_query, mode)
        as_of = as_of_date or date.today()
        page = max(1, int(page))
        page_size = max(1, min(int(page_size), MAX_PAGE_SIZE))
        clause_page = max(1, int(clause_page))
        clause_page_size = max(1, min(int(clause_page_size), MAX_PAGE_SIZE))
        if page * page_size > self._max_page_depth:
            raise SearchQueryError("PAGE_TOO_DEEP")
        results, totals, _, snapshot_ok, _ = await self._read_document_page(
            principal_id=principal_id, parsed=parsed, category_ids=category_ids,
            doc_types=doc_types, issuing_body=issuing_body, as_of_date=as_of,
            only_active=only_active, page=page, page_size=page_size,
            clause_page=clause_page, clause_page_size=clause_page_size,
            approximate_only=True, include_approximate_count=False,
        )
        total_documents = totals["documents"]
        approximate_total = totals["clauses"]
        return SearchResponse(
            query=self._query_info(parsed),
            phrase_found=False,
            totals=SearchTotals(
                documents=total_documents,
                clauses=approximate_total,
                approximate_matches_hidden=0,
                capped=bool(totals["capped"]),
                count_cap=self._count_cap,
            ),
            page=page,
            page_size=page_size,
            has_more=page * page_size < total_documents,
            effectivity_snapshot_status="ok" if snapshot_ok else "stale",
            results=results,
            approximate=SearchApproximate(
                collapsed=False,
                total_clauses=approximate_total,
                capped=bool(totals["capped"]),
            ),
            empty_reason=None if results else SearchEmptyReason.NO_RESULTS,
            clause_level_warning=_clause_level_warning(results),
            data_date=_data_date(results),
        )

    # ------------------------------------------------------------- internals
    @asynccontextmanager
    async def _search_connection(self, principal_id: UUID) -> AsyncIterator[Any]:
        try:
            await asyncio.wait_for(self._search_slots.acquire(), timeout=0.1)
        except TimeoutError as exc:
            raise SearchQueryError("SEARCH_BUSY", 429) from exc
        try:
            # One wall-clock budget includes pool acquisition, ACL, counts and
            # all tier queries. PostgreSQL's timeout alone only covers one statement.
            async with asyncio.timeout(self._statement_timeout_ms / 1000):
                async with self._pool.acquire() as connection:
                    async with connection.transaction():
                        await self._set_session(connection, principal_id)
                        yield connection
        except Exception as exc:
            if isinstance(exc, TimeoutError) or exc.__class__.__name__ == "QueryCanceledError":
                raise SearchQueryError("SEARCH_TIMEOUT", 504) from exc
            raise
        finally:
            self._search_slots.release()

    async def _read_document_page(
        self, *, principal_id: UUID, parsed: SearchQuery,
        category_ids: list[UUID] | None, doc_types: list[str] | None,
        issuing_body: str | None, as_of_date: date, only_active: bool,
        page: int, page_size: int, clause_page: int, clause_page_size: int,
        approximate_only: bool, include_approximate_count: bool,
    ) -> tuple[list[SearchDocument], dict[str, int], int, bool, bool]:
        clause_end = clause_page * clause_page_size
        if clause_end > 2**63 - 1:
            raise SearchQueryError("PAGE_TOO_DEEP")
        totals = {"documents": 0, "clauses": 0, "approximate": 0, "capped": 0}
        candidate_limit = self._count_cap + 1
        async with self._search_connection(principal_id) as connection:
            snapshot_ok = bool(await connection.fetchval(_SNAPSHOT_SQL))
            allowed = await self._allowed_document_ids(connection)
            if not allowed:
                return [], totals, 0, snapshot_ok, False
            versions = await self._selected_version_ids(connection, allowed, as_of_date)
            if not versions:
                return [], totals, len(allowed), snapshot_ok, False
            params = self._params(
                parsed=parsed, category_ids=category_ids, doc_types=doc_types,
                issuing_body=issuing_body.strip() if issuing_body else None,
                as_of_date=as_of_date, only_active=only_active, limit=MAX_CANDIDATES,
                terms_array=list(dict.fromkeys([*parsed.terms, *map(fold_text, parsed.terms)])),
                version_ids=versions,
            )
            window_params = (*params, parsed.document_number or "",
                             (page - 1) * page_size + 1, page * page_size,
                             clause_end - clause_page_size + 1, clause_end,
                             fold_text(parsed.terms_text))
            kind = "approximate" if approximate_only else "phrase" if parsed.is_phrase else "terms"
            rows = await self._fetch_rows(
                connection, document_page_sql(_BASE_SQL, kind, candidate_limit), window_params,
            )
            if kind == "phrase" and not rows[0]["total_clauses"]:
                kind = "terms"
                rows = await self._fetch_rows(
                    connection, document_page_sql(_BASE_SQL, kind, candidate_limit),
                    window_params,
                )
            totals["documents"] = int(rows[0]["total_documents"])
            totals["clauses"] = int(rows[0]["total_clauses"])
            if totals["clauses"] > self._count_cap:
                # Owner decision 05/11: above the cap show "more than N" and rank
                # within the clauses examined instead of scoring every match.
                totals["clauses"] = self._count_cap
                totals["capped"] = 1
            phrase_found = bool(rows[0]["phrase_found"])
            if include_approximate_count and kind == "terms" and totals["clauses"] <= 200:
                count = await connection.fetchrow(self._approx_count_sql(), *params)
                totals["approximate"] = int(count["approximate"] or 0)
            page_rows = [row for row in rows if row["node_id"] is not None]
            doc_views, node_views, data_date = await load_effectivity(
                connection, document_ids=[row["document_id"] for row in page_rows],
                node_ids=[row["node_id"] for row in page_rows], as_of=as_of_date,
            )
            del data_date
        hits = []
        included = set()
        matched_counts = {}
        for row in rows:
            if row["node_id"] is None:
                continue
            hit = _row_to_hit(row, int(row["tier"]), row["score"])
            self._decorate(hit, parsed)
            hits.append(hit)
            matched_counts[hit.document_id] = int(row["matched_clause_count"])
            if row["include_clause"]:
                included.add(hit.node_id)
        groups, _, _ = self._group_hits(
            hits, parsed=parsed, page=1, page_size=page_size, as_of=as_of_date,
            clause_page=1, clause_page_size=MAX_PAGE_SIZE + 1,
        )
        for group in groups:
            group.clauses = [clause for clause in group.clauses if clause.node_id in included]
            group.effectivity = doc_views.get(group.document_id)
            for clause in group.clauses:
                clause.effectivity = clause_view(group.effectivity, node_views.get(clause.node_id))
            group.matched_clause_count = matched_counts[group.document_id]
            group.clause_page = clause_page
            group.clause_page_size = clause_page_size
            group.has_more_clauses = clause_end < group.matched_clause_count
        return groups, totals, len(allowed), snapshot_ok, phrase_found

    async def _fetch_rows(self, connection: Any, sql: str, params: tuple[Any, ...]) -> list[Any]:
        try:
            return list(await connection.fetch(sql, *params))
        except Exception as exc:  # asyncpg.QueryCanceledError and friends
            if exc.__class__.__name__ in {"QueryCanceledError", "TimeoutError"}:
                raise SearchQueryError("SEARCH_TIMEOUT", 504) from exc
            raise

    async def _set_session(self, connection: Any, principal_id: UUID) -> None:
        await connection.execute(
            "SELECT set_config('app.user_id', $1, true)", str(principal_id)
        )
        await connection.execute(
            f"SET LOCAL statement_timeout = {self._statement_timeout_ms}"
        )
        # asyncpg re-uses prepared statements; after five runs PostgreSQL may
        # switch to a generic plan that ignores the actual terms/ids and scans
        # every node (seconds instead of milliseconds).  Always plan per query.
        await connection.execute("SET LOCAL plan_cache_mode = force_custom_plan")

    async def _allowed_document_ids(self, connection: Any) -> list[UUID]:
        return [
            row["document_id"]
            for row in await connection.fetch(ALLOWED_DOCUMENTS_SQL)
        ]

    @staticmethod
    async def _selected_version_ids(
        connection: Any, allowed_doc_ids: list[UUID], as_of_date: date
    ) -> list[UUID]:
        return [
            row["version_id"]
            for row in await connection.fetch(
                _SELECTED_VERSIONS_SQL, list(allowed_doc_ids), as_of_date
            )
        ]

    def _approx_count_sql(self) -> str:
        return _APPROX_COUNT_SQL_TEMPLATE.format(limit=self._approximate_count_limit)

    def _params(
        self,
        *,
        parsed: SearchQuery,
        category_ids: list[UUID] | None,
        doc_types: list[str] | None,
        issuing_body: str | None,
        as_of_date: date,
        only_active: bool,
        limit: int,
        terms_array: list[str],
        version_ids: list[UUID],
    ) -> tuple[Any, ...]:
        """Parameter positions are fixed by the SQL constants above."""

        return (
            parsed.phrase_normalized,
            parsed.phrase_folded,
            terms_array or None,
            category_ids or None,
            doc_types or None,
            issuing_body or None,
            as_of_date,
            bool(only_active),
            max(1, min(int(limit), MAX_CANDIDATES)),
            parsed.terms_text,
            list(version_ids),
        )

    def _decorate(self, hit: SearchHit, parsed: SearchQuery) -> None:
        spans: list[tuple[int, int]] = []
        if hit.tier == 1 and parsed.phrase:
            span = _find_phrase_span(hit.quote_exact, parsed.phrase)
            if span is not None:
                spans = [span]
        elif hit.tier == 3:
            spans = _find_term_spans(hit.quote_exact, parsed.terms)
        snippet, snippet_start, highlights = _build_snippet(hit.quote_exact, spans)
        hit.snippet = snippet
        hit.snippet_start = snippet_start
        hit.highlights = highlights

    @staticmethod
    def _verify_phrase(content: str, phrase: str) -> bool:
        return _verify_phrase(content, phrase)

    @staticmethod
    def _query_info(parsed: SearchQuery) -> SearchQueryInfo:
        return SearchQueryInfo(
            original=parsed.original,
            phrase=parsed.phrase,
            mode=parsed.mode,
            normalization_revision=parsed.normalization_revision,
        )

    def _group_hits(
        self,
        hits: list[SearchHit],
        *,
        parsed: SearchQuery,
        page: int,
        page_size: int,
        as_of: date,
        clause_page: int = 1,
        clause_page_size: int = 5,
    ) -> tuple[list[SearchDocument], int, int]:
        documents: dict[str, list[SearchHit]] = {}
        for hit in hits:
            documents.setdefault(hit.document_id, []).append(hit)
        total_clauses = len(hits)
        ordered = sorted(
            documents.items(),
            key=lambda item: min(
                (hit.tier, -hit.score, hit.node_id) for hit in item[1]
            ),
        )
        if parsed.document_number:
            ordered.sort(
                key=lambda item: (
                    canonical_document_number(item[1][0].document_number or "")
                    != parsed.document_number
                )
            )
        total_documents = len(ordered)
        start = (page - 1) * page_size
        page_items = ordered[start : start + page_size]
        results: list[SearchDocument] = []
        for document_id, doc_hits in page_items:
            doc_hits = sorted(doc_hits, key=lambda hit: (hit.tier, -hit.score, hit.node_id))
            first = doc_hits[0]
            clause_start = (clause_page - 1) * clause_page_size
            clause_end = clause_start + clause_page_size
            page_hits = doc_hits[clause_start:clause_end]
            clauses = [
                SearchClause(
                    node_id=hit.node_id,
                    label=hit.label,
                    page=hit.page,
                    match_type=hit.match_type,
                    amendment_state=AmendmentState.of(hit.amendment_state),
                    amendment_as_of=as_of,
                    quote_exact=hit.quote_exact,
                    snippet=hit.snippet,
                    snippet_start=hit.snippet_start,
                    highlights=hit.highlights,
                    viewer_url=self._viewer_url(hit.node_id, as_of),
                    source_hash=hit.source_hash,
                )
                for hit in page_hits
            ]
            results.append(
                SearchDocument(
                    document_id=document_id,
                    document_version_id=first.document_version_id,
                    document_number=first.document_number,
                    title=first.title,
                    doc_type=first.doc_type,
                    issuing_body=first.issuing_body,
                    official_url=first.official_url,
                    matched_clause_count=len(doc_hits),
                    clause_page=clause_page,
                    clause_page_size=clause_page_size,
                    has_more_clauses=clause_end < len(doc_hits),
                    clauses=clauses,
                )
            )
        return results, total_documents, total_clauses

    @staticmethod
    def _empty_reason(
        *,
        parsed: SearchQuery,
        results: list[SearchDocument],
        total_clauses: int,
        authorized_documents: int,
        phrase_found: bool,
    ) -> SearchEmptyReason | None:
        if total_clauses == 0:
            if authorized_documents == 0:
                return SearchEmptyReason.NO_AUTHORIZED_DOCUMENTS
            if parsed.is_phrase:
                return SearchEmptyReason.PHRASE_NOT_FOUND
            return SearchEmptyReason.NO_RESULTS
        if parsed.is_phrase and not phrase_found:
            return SearchEmptyReason.PHRASE_NOT_FOUND
        return None

    @staticmethod
    def _viewer_url(node_id: str, as_of: date) -> str:
        return f"/api/v1/citations/ev_{node_id}/pdf?as_of_date={as_of.isoformat()}"

    async def _audit(
        self,
        principal_id: UUID,
        parsed: SearchQuery,
        response: SearchResponse,
        started: float,
        filters: dict[str, Any] | None = None,
    ) -> None:
        if not self._audit_enabled:
            return
        try:
            metadata = {
                "query_sha256": hashlib.sha256(parsed.original.encode("utf-8")).hexdigest(),
                "query_length": len(parsed.original),
                "mode": parsed.mode,
                "filters": {
                    **(filters or {}),
                    "page": response.page,
                    "page_size": response.page_size,
                },
                "documents": response.totals.documents,
                "clauses": response.totals.clauses,
                # Lets operators tune EVIDENCE_SEARCH_COUNT_CAP from real usage.
                "capped": response.totals.capped,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            }
            async with asyncio.timeout(0.25), self._pool.acquire() as connection:
                async with connection.transaction():
                    await append_audit(
                        connection,
                        principal_id=principal_id,
                        action="search.query",
                        target_type="search",
                        target_id=None,
                        metadata=metadata,
                    )
        except TimeoutError:
            logger.warning("search audit append timed out")
        except Exception:  # audit must never turn a read into a failure
            logger.warning("search audit append failed", exc_info=True)


def _clause_level_warning(results: list[SearchDocument]) -> str | None:
    """Shown while any listed document lacks a computed clause-level review."""

    if any(
        result.effectivity is None or not result.effectivity.clause_level_reviewed
        for result in results
    ):
        return CLAUSE_LEVEL_WARNING
    return None


def _data_date(results: list[SearchDocument]) -> date | None:
    return next(
        (item.effectivity.data_date for item in results if item.effectivity is not None), None
    )


class AmendmentState:
    """Small adapter so invalid stored values fail safe instead of raising."""

    @staticmethod
    def of(value: str) -> AmendmentStatus:
        try:
            return AmendmentStatus(value)
        except ValueError:
            return AmendmentStatus.UNKNOWN


class SlidingWindowRateLimiter:
    def __init__(self, *, limit: int, window_seconds: float = 60.0) -> None:
        self._limit = max(1, int(limit))
        self._window = float(window_seconds)
        self._events: dict[str, deque[float]] = {}
        self._lock: asyncio.Lock | None = None

    async def check(self, principal_id: UUID) -> None:
        if self._lock is None:
            self._lock = asyncio.Lock()
        now = time.monotonic()
        key = str(principal_id)
        async with self._lock:
            bucket = self._events.setdefault(key, deque())
            while bucket and bucket[0] <= now - self._window:
                bucket.popleft()
            if len(bucket) >= self._limit:
                raise SearchQueryError("RATE_LIMITED", 429)
            bucket.append(now)
