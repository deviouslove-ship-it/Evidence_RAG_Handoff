"""User-facing API routes.

This module keeps USER and Admin permissions separate while sharing the same
backend and domain services.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status

from ...auth_acl.policy import Permission, Principal, require_permission
from ...schemas import AnalyzeRequest, AnalyzeResponse, QueryResponse, SearchResponse
from ...storage.lookup_visibility import lookup_revision
from ...storage.search import SearchQueryError, SearchService
from ...workflow.fixed_pipeline import FixedPipeline
from .dependencies import get_principal, no_store
from .errors import api_error

router = APIRouter(prefix="/api/v1", tags=["user"])


def require_user(
    principal: Annotated[Principal, Depends(get_principal)],
) -> Principal:
    try:
        require_permission(principal, Permission.QUERY)
    except PermissionError as exc:
        raise api_error(status.HTTP_403_FORBIDDEN, "QUERY_REQUIRED") from exc
    return principal


def get_pipeline(request: Request) -> FixedPipeline:
    return cast(FixedPipeline, request.app.state.pipeline)


@router.post("/query/analyze", response_model=AnalyzeResponse)
async def analyze(
    request: AnalyzeRequest,
    _principal: Annotated[Principal, Depends(require_user)],
    pipeline: Annotated[FixedPipeline, Depends(get_pipeline)],
) -> AnalyzeResponse:
    return await pipeline.analyze(request)


@router.post("/query/evidence", response_model=QueryResponse, dependencies=[Depends(no_store)])
async def evidence(
    request: AnalyzeRequest,
    http_request: Request,
    principal: Annotated[Principal, Depends(require_user)],
    pipeline: Annotated[FixedPipeline, Depends(get_pipeline)],
) -> QueryResponse:
    pool = getattr(http_request.app.state, "db_pool", None)
    revision = await lookup_revision(pool) if pool is not None else None
    try:
        result = await http_request.app.state.execution.run(
            http_request, lambda: pipeline.execute(request, principal_id=UUID(principal.id)),
            principal_id=principal.id,
            timeout=http_request.app.state.settings.query_timeout_seconds,
        )
    except SearchQueryError as exc:
        raise api_error(exc.status_code, exc.code) from exc
    if pool is not None and await lookup_revision(pool) != revision:
        raise api_error(status.HTTP_410_GONE, "RESULT_SET_EXPIRED")
    return cast(QueryResponse, result)


def _search_service(http_request: Request) -> SearchService:
    service = getattr(http_request.app.state, "search_service", None)
    if service is None:
        raise api_error(status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_NOT_CONFIGURED")
    return cast(SearchService, service)


async def _check_search_rate(http_request: Request, principal: Principal) -> None:
    limiter = getattr(http_request.app.state, "search_rate", None)
    if limiter is not None:
        try:
            await limiter.check(UUID(principal.id))
        except SearchQueryError as exc:
            raise api_error(exc.status_code, exc.code) from exc


@router.get("/search", response_model=SearchResponse, dependencies=[Depends(no_store)])
async def search_documents(
    http_request: Request,
    q: Annotated[str, Query(min_length=1)],
    principal: Annotated[Principal, Depends(require_user)],
    mode: Annotated[str, Query(pattern="^(auto|phrase|keywords)$")] = "auto",
    category_id: Annotated[list[UUID] | None, Query()] = None,
    doc_type: Annotated[list[str] | None, Query()] = None,
    issuing_body: Annotated[str | None, Query(max_length=200)] = None,
    as_of_date: date | None = None,
    only_active: bool = False,
    group_by: Annotated[str, Query(pattern="^document$")] = "document",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
    clause_page: Annotated[int, Query(ge=1)] = 1,
    clause_page_size: Annotated[int, Query(ge=1, le=50)] = 5,
) -> SearchResponse:
    del group_by
    service = _search_service(http_request)
    await _check_search_rate(http_request, principal)
    try:
        return await service.search_documents(
            principal_id=UUID(principal.id),
            raw_query=q,
            mode=mode,
            category_ids=category_id,
            doc_types=doc_type,
            issuing_body=issuing_body,
            as_of_date=as_of_date,
            only_active=only_active,
            page=page,
            page_size=page_size,
            clause_page=clause_page,
            clause_page_size=clause_page_size,
        )
    except SearchQueryError as exc:
        raise api_error(exc.status_code, exc.code) from exc


@router.get("/search/approximate", response_model=SearchResponse, dependencies=[Depends(no_store)])
async def approximate_search(
    http_request: Request,
    q: Annotated[str, Query(min_length=1)],
    principal: Annotated[Principal, Depends(require_user)],
    mode: Annotated[str, Query(pattern="^(auto|phrase|keywords)$")] = "auto",
    category_id: Annotated[list[UUID] | None, Query()] = None,
    doc_type: Annotated[list[str] | None, Query()] = None,
    issuing_body: Annotated[str | None, Query(max_length=200)] = None,
    as_of_date: date | None = None,
    only_active: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
    clause_page: Annotated[int, Query(ge=1)] = 1,
    clause_page_size: Annotated[int, Query(ge=1, le=50)] = 5,
) -> SearchResponse:
    service = _search_service(http_request)
    await _check_search_rate(http_request, principal)
    try:
        return await service.search_approximate(
            principal_id=UUID(principal.id),
            raw_query=q,
            mode=mode,
            category_ids=category_id,
            doc_types=doc_type,
            issuing_body=issuing_body,
            as_of_date=as_of_date,
            only_active=only_active,
            page=page,
            page_size=page_size,
            clause_page=clause_page,
            clause_page_size=clause_page_size,
        )
    except SearchQueryError as exc:
        raise api_error(exc.status_code, exc.code) from exc
