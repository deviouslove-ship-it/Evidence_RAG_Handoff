"""Effectivity routes: review queue, attestations, snapshots, document view (G1)."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from ...audit import append_audit
from ...auth_acl.policy import Permission, Principal
from ...effectivity.ai import propose_with_ai
from ...effectivity.service import (
    EffectivityError,
    create_attestation,
    create_proposal,
    document_effectivity,
    extract_all,
    list_attestations,
    list_proposals,
    review_proposals,
    revoke_attestation,
)
from ...effectivity.store import publish_snapshot
from .dependencies import get_principal, no_store
from .errors import api_error
from .guards import database_pool, require_document_reviewer, require_reviewer
from .user import require_user

router = APIRouter(prefix="/api/v1", tags=["effectivity"])


def require_reviewer_or_admin(
    principal: Annotated[Principal, Depends(get_principal)],
) -> Principal:
    if not principal.has(Permission.REVIEW) and not principal.has(Permission.ADMIN):
        raise api_error(status.HTTP_403_FORBIDDEN, "REVIEWER_REQUIRED")
    return principal


class RelationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relation_id: UUID
    decision: Literal["approve", "reject"]
    valid_from: date | None = None
    action: Literal[
        "modify", "replace", "add", "repeal", "repeal_partial", "suspend", "commence"
    ] | None = None
    target_document_id: UUID | None = None
    target_node_id: UUID | None = None


class ReviewBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decisions: list[RelationDecision] = Field(min_length=1, max_length=500)
    note: str = Field(min_length=1, max_length=2000)


class ProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_node_id: UUID
    action: Literal["modify", "replace", "add", "repeal", "repeal_partial", "suspend", "commence"]
    target_document_id: UUID | None = None
    target_number: str | None = Field(default=None, max_length=120)
    target_node_id: UUID | None = None
    target_path: str | None = Field(default=None, max_length=300)
    valid_from: date | None = None
    condition_text: str | None = Field(default=None, max_length=1000)
    source_quote: str | None = Field(default=None, max_length=1200)


class AttestationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: UUID
    result: Literal[
        "active", "not_yet_effective", "modified", "suspended", "repealed", "replaced"
    ]
    valid_for_from: date
    valid_for_to: date
    source_note: str = Field(min_length=1, max_length=2000)
    source_document_id: UUID | None = None


class RevokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=500)


def _error(exc: EffectivityError) -> Exception:
    return api_error(exc.status_code, exc.code)


@router.get("/admin/effectivity/proposals")
async def get_proposals(
    request: Request,
    principal: Annotated[Principal, Depends(require_reviewer)],
    status_filter: Annotated[
        Literal["draft", "approved", "rejected"] | None, Query(alias="status")
    ] = "draft",
    source_document_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    return await list_proposals(
        database_pool(request), reviewer_id=UUID(principal.id), status=status_filter,
        source_document_id=source_document_id, limit=limit, offset=offset,
    )


@router.post("/admin/effectivity/proposals/review")
async def post_review(
    request: Request, body: ReviewBatchRequest,
    principal: Annotated[Principal, Depends(require_reviewer)],
) -> dict[str, Any]:
    try:
        return await review_proposals(
            database_pool(request), reviewer_id=UUID(principal.id),
            decisions=[item.model_dump() for item in body.decisions], note=body.note,
        )
    except EffectivityError as exc:
        raise _error(exc) from exc


@router.post("/admin/effectivity/proposals", status_code=status.HTTP_201_CREATED)
async def post_proposal(
    request: Request, body: ProposalRequest,
    principal: Annotated[Principal, Depends(require_document_reviewer)],
) -> dict[str, Any]:
    try:
        return await create_proposal(
            database_pool(request), proposer_id=UUID(principal.id),
            source_node_id=body.source_node_id, action=body.action,
            target_document_id=body.target_document_id, target_number=body.target_number,
            target_node_id=body.target_node_id, target_path=body.target_path,
            valid_from=body.valid_from, condition_text=body.condition_text,
            source_quote=body.source_quote,
        )
    except EffectivityError as exc:
        raise _error(exc) from exc


@router.get("/admin/effectivity/attestations")
async def get_attestations(
    request: Request, document_id: UUID,
    _principal: Annotated[Principal, Depends(require_reviewer_or_admin)],
) -> list[dict[str, Any]]:
    return await list_attestations(database_pool(request), document_id=document_id)


@router.post("/admin/effectivity/attestations", status_code=status.HTTP_201_CREATED)
async def post_attestation(
    request: Request, body: AttestationRequest,
    principal: Annotated[Principal, Depends(require_reviewer)],
) -> dict[str, Any]:
    try:
        return await create_attestation(
            database_pool(request), reviewer_id=UUID(principal.id),
            document_id=body.document_id, result=body.result,
            valid_for_from=body.valid_for_from, valid_for_to=body.valid_for_to,
            source_note=body.source_note, source_document_id=body.source_document_id,
        )
    except EffectivityError as exc:
        raise _error(exc) from exc


@router.post("/admin/effectivity/attestations/{attestation_id}/revoke")
async def post_revoke(
    request: Request, attestation_id: UUID, body: RevokeRequest,
    principal: Annotated[Principal, Depends(require_reviewer)],
) -> dict[str, Any]:
    try:
        return await revoke_attestation(
            database_pool(request), reviewer_id=UUID(principal.id),
            attestation_id=attestation_id, reason=body.reason,
        )
    except EffectivityError as exc:
        raise _error(exc) from exc


@router.post("/admin/effectivity/extract")
async def post_extract(
    request: Request, principal: Annotated[Principal, Depends(require_reviewer_or_admin)],
) -> dict[str, Any]:
    """Re-run the rules on every approved version (idempotent)."""

    return await extract_all(database_pool(request), actor_id=UUID(principal.id))


class AiProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: UUID
    limit: int = Field(default=20, ge=1, le=100)


@router.post("/admin/effectivity/ai-proposals")
async def post_ai_proposals(
    request: Request, body: AiProposalRequest,
    principal: Annotated[Principal, Depends(require_reviewer)],
) -> dict[str, Any]:
    """Stage ``relation`` on sentences the rules could not read; results are drafts."""

    runtime = getattr(request.app.state, "ai_runtime", None)
    if runtime is None:
        raise api_error(status.HTTP_503_SERVICE_UNAVAILABLE, "AI_NOT_CONFIGURED")
    pool = database_pool(request)
    result = await propose_with_ai(pool, runtime, document_id=body.document_id,
                                   principal_id=UUID(principal.id), limit=body.limit)
    async with pool.acquire() as connection, connection.transaction():
        await append_audit(connection, principal_id=UUID(principal.id),
                           action="effectivity.ai_proposals", target_type="document",
                           target_id=str(body.document_id), metadata=result)
    return result


@router.post("/admin/effectivity/snapshots/publish")
async def post_publish(
    request: Request, principal: Annotated[Principal, Depends(require_reviewer_or_admin)],
) -> dict[str, Any]:
    pool = database_pool(request)
    async with pool.acquire() as connection, connection.transaction():
        result = await publish_snapshot(connection, actor_id=UUID(principal.id))
        await append_audit(
            connection, principal_id=UUID(principal.id), action="effectivity.publish_snapshot",
            target_type="effectivity_snapshot", target_id=str(result["revision"]),
            metadata=result,
        )
    return result


@router.get("/effectivity/documents/{document_id}", dependencies=[Depends(no_store)])
async def get_document_effectivity(
    request: Request, document_id: UUID,
    principal: Annotated[Principal, Depends(require_user)],
    as_of_date: date | None = None,
) -> dict[str, Any]:
    found = await document_effectivity(
        database_pool(request), principal_id=UUID(principal.id), document_id=document_id,
        as_of=as_of_date or date.today(),
    )
    if found is None:
        raise api_error(status.HTTP_404_NOT_FOUND, "DOCUMENT_NOT_FOUND")
    return found
