"""Page documents and clauses in PostgreSQL before transferring source text."""

from __future__ import annotations

import re

_VI_UPPER = "ÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴÈÉẸẺẼÊỀẾỆỂỄÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸĐ"


def number_key_sql(column: str) -> str:
    """SQL search key for a document number; mirrors ``canonical_document_number``."""

    return f"lower(translate(regexp_replace({column}, '\\s+', '', 'g'), 'đĐ–—', 'dd--'))"


def vi_lower_sql(expression: str, *, builtin_unicode: bool = False) -> str:
    """Lower-case Vietnamese text in SQL independent of the database locale.

    Under the ``C`` collation PostgreSQL ``lower()`` and the ``simple`` text
    search parser only fold ASCII, so ``Định`` and ``định`` would not match.
    ``builtin_unicode`` uses the PostgreSQL 17+ ``pg_c_utf8`` collation, which
    applies full Unicode case mapping about 30x faster than ``translate``.
    """

    if builtin_unicode:
        return f"lower(({expression}) COLLATE pg_c_utf8)"
    return f"lower(translate({expression}, '{_VI_UPPER}', '{_VI_UPPER.lower()}'))"


# Stable tie-break for equal-ranked clauses (G2 exact and relation channels, RRF fusion).
# A node UUID is random per import, so two imports of the same files would order equal
# scores differently.  The position of the clause is identical in every import:
#   document number, SHA-256 of the file (separates documents that share a number),
#   then ``document_nodes.path`` whose prefix is the clause's sequence in the text
#   (Điều -> Khoản -> Điểm in reading order, e.g. ``000034:chuong:II/dieu:6/khoan:4``).
# Text is compared bytewise (``COLLATE "C"`` here, code-point order in Python), so the
# result does not depend on the locale of the database server.
_SEQUENCE_PREFIX = re.compile(r"^([0-9]{1,18}):")
NO_STABLE_KEY: tuple[int, str, str, int, int, str] = (1, "", "", 1, 0, "")


def stable_clause_key(
    document_number: str | None, source_hash: str | None, path: str | None
) -> tuple[int, str, str, int, int, str]:
    """Python twin of :func:`stable_order_sql`; the leading 0 ranks known clauses first."""

    match = _SEQUENCE_PREFIX.match(path or "")
    return (0, document_number or "", source_hash or "", 0 if match else 1,
            int(match.group(1)) if match else 0, path or "")


def stable_order_sql(number: str, source_hash: str, path: str, node_id: str) -> str:
    """ORDER BY terms equal to ``stable_clause_key``; ``node_id`` only as the last resort."""

    has_sequence = f"{path} ~ '^[0-9]{{1,18}}:'"
    return (
        f"""COALESCE({number}, '') COLLATE "C", COALESCE({source_hash}, '') COLLATE "C", """
        f"CASE WHEN {has_sequence} THEN 0 ELSE 1 END, "
        f"CASE WHEN {has_sequence} THEN split_part({path}, ':', 1)::bigint ELSE 0 END, "
        f"""COALESCE({path}, '') COLLATE "C", {node_id}"""
    )


_NUMBER_KEY = number_key_sql("document_number")
_CONTENT_LOWER = vi_lower_sql("text_normalized")
_EXACT = f"""(
    position(' ' || $1 || ' ' in ' ' || trim(regexp_replace(
        {_CONTENT_LOWER}, '[^0-9a-zA-ZÀ-ỹĐđ]+', ' ', 'g')) || ' ') > 0
)"""
_FOLDED = """(
    to_tsvector('simple'::regconfig, text_folded)
        @@ phraseto_tsquery('simple'::regconfig, $2)
    AND position(' ' || $2 || ' ' in ' ' || trim(regexp_replace(
        text_folded, '[^0-9a-zA-ZÀ-ỹĐđ]+', ' ', 'g')) || ' ') > 0
)"""
_ALL_TERMS = """(
    to_tsvector('simple'::regconfig, text_indexed)
        @@ plainto_tsquery('simple'::regconfig, $10)
    OR to_tsvector('simple'::regconfig, text_folded)
        @@ plainto_tsquery('simple'::regconfig, $17)
)"""
# Any of the terms ($3, accented + folded variants) as one indexable tsquery.
# Terms are tokenizer output (letters/digits only), so quoting them is safe.
ANY_TERM_TSQUERY = """to_tsquery('simple'::regconfig, array_to_string(ARRAY(
    SELECT '''' || term || '''' FROM unnest($3::text[]) AS term), ' | '))"""
_PARTIAL = f"""(
    to_tsvector('simple'::regconfig, text_indexed) @@ {ANY_TERM_TSQUERY}
    OR to_tsvector('simple'::regconfig, text_folded) @@ {ANY_TERM_TSQUERY}
)"""


def document_page_sql(base_sql: str, kind: str, candidate_limit: int | None = None) -> str:
    """All values are bound parameters; ``kind`` is an internal constant.

    ``candidate_limit`` bounds how many matching clauses are verified, scored
    and counted (configured integer, rendered as a literal).  Callers pass
    ``cap + 1`` so a total above the cap can be detected.
    """
    limit_sql = ""
    if candidate_limit is not None:
        limit_sql = f"\n    LIMIT {max(1, int(candidate_limit))}"
    condition, tier, score = _tier_parts(kind)
    return base_sql + f"""
, candidates AS MATERIALIZED (
    SELECT base.*, {tier} AS tier, {score} AS score
    FROM base WHERE ({condition}) AND ($17::text IS NULL OR TRUE){limit_sql}
), best_documents AS (
    SELECT DISTINCT ON (document_id) document_id, document_number, tier, score, node_id
    FROM candidates ORDER BY document_id, tier, score DESC, node_id
), document_order AS (
    SELECT document_id, row_number() OVER (
        ORDER BY COALESCE($12::text <> '' AND {_NUMBER_KEY} = $12, FALSE) DESC,
                 tier, score DESC, node_id
    ) AS document_position FROM best_documents
), page_documents AS MATERIALIZED (
    -- At most one page of documents; joined below instead of re-evaluating the
    -- window over every candidate clause.
    SELECT document_id, document_position FROM document_order
    WHERE document_position BETWEEN $13::bigint AND $14::bigint
), totals AS (
    SELECT count(*) AS total_clauses, count(DISTINCT document_id) AS total_documents,
           COALESCE(bool_or(tier = 1), FALSE) AS phrase_found FROM candidates
), ranked AS (
    SELECT c.*, d.document_position,
           count(*) OVER (PARTITION BY c.document_id) AS matched_clause_count,
           row_number() OVER (
               PARTITION BY c.document_id ORDER BY c.tier, c.score DESC, c.node_id
           ) AS clause_position
    FROM candidates c JOIN page_documents d USING (document_id)
), page_rows AS (
    SELECT *, clause_position BETWEEN $15::bigint AND $16::bigint AS include_clause
    FROM ranked WHERE clause_position = 1 OR clause_position BETWEEN $15 AND $16
)
SELECT totals.*, page_rows.* FROM totals LEFT JOIN page_rows ON TRUE
ORDER BY document_position, clause_position
"""


def candidates_sql(base_sql: str, kind: str, limit: int) -> str:
    """Every matching clause (up to ``limit``) in rank order, for the G2 exact channel.

    Same 17 parameters as :func:`document_page_sql`; the window bounds are unused.
    """

    condition, tier, score = _tier_parts(kind)
    return base_sql + f"""
, candidates AS MATERIALIZED (
    SELECT base.node_id, base.document_id, base.document_number, base.source_hash,
           {tier} AS tier, {score} AS score
    FROM base WHERE ({condition}) AND ($17::text IS NULL OR TRUE)
      AND ($13::bigint IS NULL OR TRUE) AND ($14::bigint IS NULL OR TRUE)
      AND ($15::bigint IS NULL OR TRUE) AND ($16::bigint IS NULL OR TRUE)
    LIMIT {max(1, int(limit))}
)
SELECT candidates.node_id, candidates.document_id, candidates.tier, candidates.score
FROM candidates JOIN document_nodes kn ON kn.id = candidates.node_id
ORDER BY COALESCE($12::text <> '' AND EXISTS (
    SELECT 1 FROM documents d WHERE d.id = candidates.document_id
      AND {number_key_sql('d.document_number')} = $12), FALSE) DESC,
         candidates.tier, candidates.score DESC,
         {stable_order_sql('candidates.document_number', 'candidates.source_hash',
                           'kn.path', 'candidates.node_id')}
"""


def _tier_parts(kind: str) -> tuple[str, str, str]:
    if kind == "phrase":
        condition = (
            f"$1::text <> '' AND {_FOLDED} "
            f"AND ({_ALL_TERMS} OR ($12::text <> '' AND {_NUMBER_KEY} = $12))"
        )
        tier = f"CASE WHEN {_EXACT} THEN 1 ELSE 2 END"
        score = """ts_rank_cd(to_tsvector('simple'::regconfig, text_folded),
                              phraseto_tsquery('simple'::regconfig, $2))"""
    elif kind == "terms":
        condition = f"{_ALL_TERMS} OR ($12::text <> '' AND {_NUMBER_KEY} = $12)"
        tier = "3"
        score = """GREATEST(
            ts_rank_cd(to_tsvector('simple'::regconfig, text_indexed),
                       plainto_tsquery('simple'::regconfig, $10)),
            ts_rank_cd(to_tsvector('simple'::regconfig, text_folded),
                       plainto_tsquery('simple'::regconfig, $17)))"""
    elif kind == "approximate":
        condition = f"{_PARTIAL} AND NOT {_ALL_TERMS}"
        tier = "4"
        score = """(SELECT count(*) FROM unnest($3::text[]) AS term
            WHERE to_tsvector('simple'::regconfig, text_indexed)
                      @@ plainto_tsquery('simple'::regconfig, term)
               OR to_tsvector('simple'::regconfig, text_folded)
                      @@ plainto_tsquery('simple'::regconfig, term))::real"""
    else:
        raise ValueError("Invalid internal search tier")
    return condition, tier, score
