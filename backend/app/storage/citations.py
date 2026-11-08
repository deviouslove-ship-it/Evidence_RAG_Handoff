"""Recheck ACL and verified source state when a citation is opened."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from ..schemas import AmendmentStatus, CitationResponse, EvidenceRef


@dataclass(frozen=True)
class AuthorizedCitation:
    response: CitationResponse
    original_file_path: str
    source_hash: str
    # What the curator uploaded: "pdf" (served as is, scans included) or a Word/TXT file
    # kept under sources/ next to the PDF rendered from it for citation anchoring.
    source_format: str = "pdf"
    source_file_sha256: str | None = None
    original_filename: str = "document.pdf"


_CITATION_SQL = """SELECT n.id AS node_id, d.id AS document_id,
          dv.id AS document_version_id, d.document_number,
          d.title,
          COALESCE(dn.citation_label, n.label_original, n.node_type::text) AS label,
          n.text_original AS quote_exact,
          sp.page_number AS original_page,
          dv.original_file_sha256 AS source_hash,
          dv.original_file_path, dv.source_format, dv.source_file_sha256,
          dv.original_filename
   FROM authorized_nodes n
   JOIN document_nodes dn ON dn.id = n.id
   JOIN documents d ON d.id = n.document_id
   JOIN document_versions dv ON dv.id = n.document_version_id
   JOIN source_provenance prov
     ON prov.document_version_id = dv.id
    AND prov.verified_at IS NOT NULL
   -- Every span of the quote (one per page) is re-checked; the viewer opens the
   -- first page.
   JOIN source_spans ss ON ss.id = n.source_span_id
   JOIN source_pages sp ON sp.id = ss.page_id
    AND sp.document_version_id = dv.id
    AND node_source_text_valid(n.id)
"""


def _node_id(citation_id: str) -> UUID | None:
    if not citation_id.startswith("ev_"):
        return None
    try:
        return UUID(citation_id[3:])
    except ValueError:
        return None


async def get_authorized_citation(
    pool: Any, *, principal_id: UUID, citation_id: str, as_of_date: date
) -> AuthorizedCitation | None:
    node_id = _node_id(citation_id)
    if node_id is None:
        return None
    async with pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute(
                "SELECT set_config('app.user_id', $1, true)", str(principal_id)
            )
            row = await connection.fetchrow(_CITATION_SQL + " WHERE n.id = $1", node_id)
    if row is None:
        return None
    return _citation(citation_id, row, as_of_date)


async def get_authorized_citations(
    pool: Any, *, principal_id: UUID, citation_ids: list[str], as_of_date: date
) -> dict[str, AuthorizedCitation]:
    """Recheck several citations in one principal-scoped query.

    Citations that are unknown, malformed or no longer authorized are absent
    from the result.
    """

    node_ids = {
        citation_id: node_id
        for citation_id in citation_ids
        if (node_id := _node_id(citation_id)) is not None
    }
    if not node_ids:
        return {}
    async with pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute(
                "SELECT set_config('app.user_id', $1, true)", str(principal_id)
            )
            rows = await connection.fetch(
                _CITATION_SQL + " WHERE n.id = ANY($1::uuid[])", list(set(node_ids.values()))
            )
    by_node = {row["node_id"]: row for row in rows}
    return {
        citation_id: _citation(citation_id, by_node[node_id], as_of_date)
        for citation_id, node_id in node_ids.items()
        if node_id in by_node
    }


def _citation(citation_id: str, row: Any, as_of_date: date) -> AuthorizedCitation:
    evidence = EvidenceRef(
        evidence_id=citation_id,
        document_id=row["document_id"],
        document_version_id=row["document_version_id"],
        node_id=row["node_id"],
        document_number=row["document_number"],
        title=row["title"],
        label=row["label"],
        quote_exact=row["quote_exact"],
        page=row["original_page"],
        source_hash=row["source_hash"],
        as_of_date=as_of_date,
        amendment_state=AmendmentStatus.UNKNOWN,
        viewer_url=(
            f"/api/v1/citations/{citation_id}/pdf?as_of_date={as_of_date.isoformat()}"
        ),
    )
    return AuthorizedCitation(
        response=CitationResponse(
            evidence=evidence,
            quote_exact=row["quote_exact"],
            amendment_state=AmendmentStatus.UNKNOWN,
            as_of_date=as_of_date,
        ),
        original_file_path=row["original_file_path"],
        source_hash=row["source_hash"],
        source_format=row.get("source_format") or "pdf",
        source_file_sha256=row.get("source_file_sha256"),
        original_filename=row.get("original_filename") or "document.pdf",
    )
