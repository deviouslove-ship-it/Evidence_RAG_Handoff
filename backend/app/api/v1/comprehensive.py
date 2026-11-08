"""G2 comprehensive search and the reviewed concept dictionary."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from ...audit import append_audit
from ...auth_acl.policy import Principal
from ...storage.comprehensive import ComprehensiveRequest, ComprehensiveSearch
from ...storage.search import SearchQueryError
from ...vietnamese_nlp.unicode_norm import fold_text
from .errors import api_error
from .guards import database_pool, require_document_reviewer, require_reviewer
from .user import _check_search_rate, require_user

router = APIRouter(prefix="/api/v1", tags=["comprehensive-search"])
ChannelName = Literal["exact", "semantic", "concept", "relation"]


def _all_channels() -> list[ChannelName]:
    return ["exact", "semantic", "concept", "relation"]


class ComprehensiveSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: str = Field(min_length=1, max_length=500)
    category_ids: list[UUID] = Field(default_factory=list, max_length=100)
    doc_types: list[str] = Field(default_factory=list, max_length=30)
    as_of_date: date | None = None
    # default = D9 sections; all = "Tìm toàn bộ"; history = "Đối chiếu lịch sử".
    display: Literal["default", "all", "history"] = "default"
    # Turning a channel off measures its contribution (design §11, G2 check).
    channels: list[ChannelName] = Field(default_factory=_all_channels)
    excluded_concepts: list[str] = Field(default_factory=list, max_length=50)
    # None = server default (EVIDENCE_RERANK_DEFAULT, off). True/False overrides it per request.
    rerank: bool | None = None
    page_size: int = Field(default=20, ge=1, le=50)
    # auto = quoted text is a phrase; phrase = whole query as one exact phrase;
    # keywords = every word anywhere in the clause.
    mode: Literal["auto", "phrase", "keywords"] = "auto"
    # clauses = ranked clause list (default); documents = one entry per document.
    view: Literal["clauses", "documents"] = "clauses"
    clauses_per_document: int = Field(default=5, ge=1, le=20)
    tier: list[Literal["direct", "related", "weak", "unscored"]] = Field(
        default_factory=list, max_length=4)


class ConceptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    term: str = Field(min_length=1, max_length=200)
    expansion: str = Field(min_length=1, max_length=200)


class ConceptReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ids: list[UUID] = Field(min_length=1, max_length=500)
    decision: Literal["approve", "reject"]


def _service(request: Request) -> ComprehensiveSearch:
    service = getattr(request.app.state, "comprehensive_search", None)
    if service is None:
        raise api_error(status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_NOT_CONFIGURED")
    return cast(ComprehensiveSearch, service)


@router.post("/search/comprehensive")
async def comprehensive_search(
    http_request: Request, body: ComprehensiveSearchRequest,
    principal: Annotated[Principal, Depends(require_user)],
) -> dict[str, Any]:
    service = _service(http_request)
    await _check_search_rate(http_request, principal)
    settings = getattr(http_request.app.state, "settings", None)
    use_rerank = body.rerank if body.rerank is not None else bool(
        getattr(settings, "rerank_default", False)
    )
    try:
        result = await service.run(UUID(principal.id), ComprehensiveRequest(
            query=body.q, category_ids=body.category_ids or None,
            doc_types=body.doc_types or None, as_of_date=body.as_of_date,
            display=body.display, channels=tuple(body.channels),
            excluded_concepts=tuple(body.excluded_concepts), rerank=use_rerank,
            mode=body.mode,
        ))
        return await service.page(
            UUID(principal.id), result, page=1, page_size=body.page_size, view=body.view,
            clauses_per_document=body.clauses_per_document, tiers=tuple(body.tier),
        )
    except SearchQueryError as exc:
        raise api_error(exc.status_code, exc.code) from exc


TierName = Literal["direct", "related", "weak", "unscored"]
SectionName = Literal["verified_active", "unverified", "terminated", "all"]


@router.get("/search/comprehensive/{result_set_id}")
async def comprehensive_page(
    http_request: Request, result_set_id: str,
    principal: Annotated[Principal, Depends(require_user)],
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
    effective_status: Annotated[list[str] | None, Query(alias="status")] = None,
    verification: Annotated[list[str] | None, Query()] = None,
    section: Annotated[SectionName | None, Query()] = None,
    tier: Annotated[list[TierName] | None, Query()] = None,
    view: Annotated[Literal["clauses", "documents"], Query()] = "clauses",
    clauses_per_document: Annotated[int, Query(ge=1, le=20)] = 5,
) -> dict[str, Any]:
    service = _service(http_request)
    result = service.store.get(result_set_id, principal.id)
    if result is None:
        raise api_error(status.HTTP_410_GONE, "RESULT_SET_EXPIRED")
    try:
        return await service.page(
            UUID(principal.id), result, page=page, page_size=page_size,
            statuses=effective_status or (), verifications=verification or (), section=section,
            tiers=tier or (), view=view, clauses_per_document=clauses_per_document,
        )
    except SearchQueryError as exc:
        raise api_error(exc.status_code, exc.code) from exc


@router.get("/search/comprehensive/{result_set_id}/documents/{document_id}")
async def comprehensive_document_clauses(
    http_request: Request, result_set_id: str, document_id: UUID,
    principal: Annotated[Principal, Depends(require_user)],
    effective_status: Annotated[list[str] | None, Query(alias="status")] = None,
    verification: Annotated[list[str] | None, Query()] = None,
    section: Annotated[SectionName | None, Query()] = None,
    tier: Annotated[list[TierName] | None, Query()] = None,
) -> dict[str, Any]:
    """Every matching clause of one document of the result set (permissions re-checked)."""

    service = _service(http_request)
    result = service.store.get(result_set_id, principal.id)
    if result is None:
        raise api_error(status.HTTP_410_GONE, "RESULT_SET_EXPIRED")
    try:
        clauses = await service.document_clauses(
            UUID(principal.id), result, str(document_id), statuses=effective_status or (),
            verifications=verification or (), section=section, tiers=tier or (),
        )
    except SearchQueryError as exc:
        raise api_error(exc.status_code, exc.code) from exc
    return {"result_set_id": result.id, "document_id": str(document_id), "clauses": clauses}


@router.get("/admin/concepts")
async def list_concepts(
    request: Request, _principal: Annotated[Principal, Depends(require_document_reviewer)],
    status_filter: Annotated[
        Literal["proposed", "approved", "rejected"] | None, Query(alias="status")
    ] = None,
) -> list[dict[str, Any]]:
    async with database_pool(request).acquire() as connection:
        rows = await connection.fetch(
            """SELECT id, term, expansion, status, source, created_at, reviewed_at
               FROM concept_terms WHERE ($1::text IS NULL OR status = $1)
               ORDER BY term_folded, expansion LIMIT 1000""",
            status_filter,
        )
    return [{**dict(row), "id": str(row["id"]), "created_at": row["created_at"].isoformat(),
             "reviewed_at": row["reviewed_at"].isoformat() if row["reviewed_at"] else None}
            for row in rows]


@router.post("/admin/concepts", status_code=status.HTTP_201_CREATED)
async def propose_concept(
    request: Request, body: ConceptRequest,
    principal: Annotated[Principal, Depends(require_document_reviewer)],
) -> dict[str, Any]:
    term, expansion = body.term.strip(), body.expansion.strip()
    if not term or not expansion or fold_text(term) == fold_text(expansion):
        raise api_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "INVALID_REQUEST")
    async with database_pool(request).acquire() as connection, connection.transaction():
        concept_id = await connection.fetchval(
            """INSERT INTO concept_terms (term, term_folded, expansion, created_by)
               VALUES ($1, $2, $3, $4)
               ON CONFLICT (term_folded, expansion) DO NOTHING RETURNING id""",
            term, " ".join(fold_text(term).split()), expansion, UUID(principal.id),
        )
        if concept_id is None:
            raise api_error(status.HTTP_409_CONFLICT, "CONCEPT_EXISTS")
        await append_audit(connection, principal_id=UUID(principal.id),
                           action="concept.propose", target_type="concept_term",
                           target_id=str(concept_id),
                           metadata={"term": term, "expansion": expansion})
    return {"id": str(concept_id), "status": "proposed"}


@router.post("/admin/concepts/review")
async def review_concepts(
    request: Request, body: ConceptReviewRequest,
    principal: Annotated[Principal, Depends(require_reviewer)],
) -> dict[str, Any]:
    reviewer = UUID(principal.id)
    async with database_pool(request).acquire() as connection, connection.transaction():
        rows = await connection.fetch(
            "SELECT id, created_by, status FROM concept_terms WHERE id = ANY($1::uuid[])"
            " FOR UPDATE",
            body.ids,
        )
        if len(rows) != len(set(body.ids)):
            raise api_error(status.HTTP_404_NOT_FOUND, "CONCEPT_NOT_FOUND")
        if any(row["created_by"] == reviewer for row in rows):
            raise api_error(status.HTTP_403_FORBIDDEN, "SELF_APPROVAL_DENIED")
        new_status = "approved" if body.decision == "approve" else "rejected"
        await connection.execute(
            """UPDATE concept_terms SET status = $2, reviewed_by = $3, reviewed_at = now()
               WHERE id = ANY($1::uuid[])""",
            body.ids, new_status, reviewer,
        )
        for row in rows:
            await append_audit(connection, principal_id=reviewer, action="concept.review",
                               target_type="concept_term", target_id=str(row["id"]),
                               metadata={"decision": body.decision})
    return {"updated": len(rows), "status": new_status}
