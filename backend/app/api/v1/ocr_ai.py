"""Admin portal API routes for single-page OCR AI proposals."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, ConfigDict, Field

from ...auth_acl.policy import Principal
from ...documents.ocr_ai_store import (
    apply_candidate,
    cancel_proposal,
    create_proposal,
    get_proposal,
    reject_proposal,
)
from ...documents.review import ReviewError
from .admin import require_admin_or_doc_staff
from .dependencies import no_store
from .errors import api_error
from .guards import database_pool, require_curator

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


class OcrAiCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_number: int = Field(ge=1)
    expected_revision: int = Field(ge=0)
    request_id: UUID


class OcrAiRejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, max_length=1000)


class OcrAiApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=0)
    corrected_text: str | None = Field(default=None, max_length=50_000)
    note: str | None = Field(default=None, max_length=1000)


def _wake_worker(request: Request) -> None:
    worker = getattr(request.app.state, "ocr_ai_worker", None)
    if worker is not None and hasattr(worker, "wake"):
        worker.wake()


@router.post(
    "/documents/{document_id}/versions/{version_id}/ocr-ai",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(no_store)],
)
async def create_ocr_ai_proposal_route(
    request: Request,
    document_id: UUID,
    version_id: UUID,
    body: OcrAiCreateRequest,
    principal: Annotated[Principal, Depends(require_curator)],
) -> dict[str, Any]:
    pool = database_pool(request)
    try:
        result = await create_proposal(
            pool,
            principal,
            document_id=document_id,
            version_id=version_id,
            page_number=body.page_number,
            expected_revision=body.expected_revision,
            request_id=body.request_id,
            ai_enabled=(
                request.app.state.settings.ocr_ai_enabled
                and getattr(request.app.state, "ocr_ai_worker", None) is not None
            ),
        )
    except ReviewError as exc:
        raise api_error(exc.status_code, exc.code) from exc
    if result.get("status") == "queued" and not result.get("deduplicated"):
        _wake_worker(request)
    return result


@router.get("/ocr-ai/{proposal_id}", dependencies=[Depends(no_store)])
async def get_ocr_ai_proposal_route(
    request: Request,
    proposal_id: UUID,
    principal: Annotated[Principal, Depends(require_admin_or_doc_staff)],
) -> dict[str, Any]:
    pool = database_pool(request)
    try:
        return await get_proposal(pool, principal, proposal_id)
    except ReviewError as exc:
        raise api_error(exc.status_code, exc.code) from exc


@router.post("/ocr-ai/{proposal_id}/cancel", dependencies=[Depends(no_store)])
async def cancel_ocr_ai_proposal_route(
    request: Request,
    proposal_id: UUID,
    principal: Annotated[Principal, Depends(require_curator)],
) -> dict[str, Any]:
    pool = database_pool(request)
    try:
        return await cancel_proposal(pool, principal, proposal_id)
    except ReviewError as exc:
        raise api_error(exc.status_code, exc.code) from exc


@router.post("/ocr-ai/{proposal_id}/reject", dependencies=[Depends(no_store)])
async def reject_ocr_ai_proposal_route(
    request: Request,
    proposal_id: UUID,
    principal: Annotated[Principal, Depends(require_curator)],
    body: OcrAiRejectRequest | None = None,
) -> dict[str, Any]:
    pool = database_pool(request)
    try:
        return await reject_proposal(
            pool,
            principal,
            proposal_id,
            note=body.note if body is not None else None,
        )
    except ReviewError as exc:
        raise api_error(exc.status_code, exc.code) from exc


@router.post("/ocr-ai/{proposal_id}/apply", dependencies=[Depends(no_store)])
async def apply_ocr_ai_proposal_route(
    request: Request,
    proposal_id: UUID,
    body: OcrAiApplyRequest,
    principal: Annotated[Principal, Depends(require_curator)],
) -> dict[str, Any]:
    pool = database_pool(request)
    try:
        return await apply_candidate(
            pool,
            principal,
            proposal_id,
            expected_revision=body.expected_revision,
            corrected_text=body.corrected_text,
            note=body.note,
            model_validator=getattr(
                getattr(request.app.state, "ai_runtime", None),
                "validate_vision_snapshot",
                None,
            ),
        )
    except ReviewError as exc:
        raise api_error(exc.status_code, exc.code) from exc
