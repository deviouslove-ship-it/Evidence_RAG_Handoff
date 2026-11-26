"""User-facing API routes for reading verified or AI-read individual PDF pages."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from ...auth_acl.policy import Principal
from ...documents.page_text import (
    cancel_page_text_task,
    get_page_text_task,
    read_user_document_pdf,
    request_page_text,
)
from ...documents.review import ReviewError
from .dependencies import no_store
from .errors import api_error
from .guards import database_pool
from .user import require_user

router = APIRouter(prefix="/api/v1", tags=["user"])


class PageTextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_number: int = Field(ge=1)
    prefer_ai: bool = False
    request_id: UUID | None = None


class PageTextResponse(BaseModel):
    task_id: str | None = None
    status: Literal[
        "queued", "running", "ready", "failed", "cancelled", "stale", "applied", "rejected"
    ]
    document_id: str
    version_id: str
    document_title: str
    document_number: str | None = None
    page_number: int
    total_pages: int
    source_kind: Literal["native", "ocr_reviewed", "ocr_ai_unverified"]
    verified: bool
    warning: str | None = None
    page_text: str | None = None
    error_code: str | None = None
    warnings: list[str] = Field(default_factory=list)
    unreadable: list[str] = Field(default_factory=list)
    pdf_url: str
    deduplicated: bool = False


def _wake_ocr_worker(request: Request) -> None:
    worker = getattr(request.app.state, "ocr_ai_worker", None)
    if worker is not None and hasattr(worker, "wake"):
        worker.wake()


@router.post(
    "/documents/{document_id}/versions/{version_id}/page-text",
    response_model=PageTextResponse,
    dependencies=[Depends(no_store)],
)
async def request_page_text_route(
    request: Request,
    response: Response,
    document_id: UUID,
    version_id: UUID,
    body: PageTextRequest,
    principal: Annotated[Principal, Depends(require_user)],
) -> dict[str, object]:
    pool = database_pool(request)
    try:
        status_code, payload = await request_page_text(
            pool,
            principal,
            document_id=document_id,
            version_id=version_id,
            page_number=body.page_number,
            prefer_ai=body.prefer_ai,
            request_id=body.request_id,
            ai_enabled=(
                request.app.state.settings.ocr_ai_enabled
                and getattr(request.app.state, "ocr_ai_worker", None) is not None
            ),
        )
    except ReviewError as exc:
        raise api_error(exc.status_code, exc.code) from exc
    response.status_code = status_code
    if payload.get("status") == "queued" and not payload.get("deduplicated"):
        _wake_ocr_worker(request)
    return payload


@router.get(
    "/page-text-tasks/{task_id}",
    response_model=PageTextResponse,
    dependencies=[Depends(no_store)],
)
async def get_page_text_task_route(
    request: Request,
    task_id: UUID,
    principal: Annotated[Principal, Depends(require_user)],
) -> dict[str, object]:
    pool = database_pool(request)
    try:
        return await get_page_text_task(pool, principal, task_id)
    except ReviewError as exc:
        raise api_error(exc.status_code, exc.code) from exc


@router.post(
    "/page-text-tasks/{task_id}/cancel",
    response_model=PageTextResponse,
    dependencies=[Depends(no_store)],
)
async def cancel_page_text_task_route(
    request: Request,
    task_id: UUID,
    principal: Annotated[Principal, Depends(require_user)],
) -> dict[str, object]:
    pool = database_pool(request)
    try:
        return await cancel_page_text_task(pool, principal, task_id)
    except ReviewError as exc:
        raise api_error(exc.status_code, exc.code) from exc


@router.get(
    "/documents/{document_id}/versions/{version_id}/pdf",
    dependencies=[Depends(no_store)],
)
async def get_user_document_pdf_route(
    request: Request,
    document_id: UUID,
    version_id: UUID,
    principal: Annotated[Principal, Depends(require_user)],
) -> Response:
    settings = request.app.state.settings
    if not settings.document_store_root:
        raise api_error(503, "DOCUMENT_STORE_NOT_CONFIGURED")
    pool = database_pool(request)
    try:
        content = await read_user_document_pdf(
            pool,
            principal,
            document_id=document_id,
            version_id=version_id,
            store_root=Path(settings.document_store_root),
        )
    except ReviewError as exc:
        raise api_error(exc.status_code, exc.code) from exc
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": "inline",
            "X-Content-Type-Options": "nosniff",
        },
    )
