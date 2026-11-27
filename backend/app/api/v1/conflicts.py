"""Phase 2 API routes: conflict scans, reviewer triage, and legal authority rules (D5)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from ...auth_acl.policy import Permission, Principal
from ...conflicts.store import (
    ConflictStoreError,
    cancel_conflict_run,
    create_authority_rule,
    create_conflict_run,
    get_conflict_run,
    list_admin_conflict_findings,
    list_authority_rules,
    list_conflict_findings,
    list_conflict_runs,
    review_conflict_finding_with_draft,
    update_authority_rule,
)
from .dependencies import get_principal, no_store
from .errors import api_error
from .guards import database_pool, require_admin, require_document_reviewer
from .user import require_user

router = APIRouter(prefix="/api/v1", tags=["conflicts"], dependencies=[Depends(no_store)])

_DISCLAIMER = "Gợi ý tự động — cần chuyên viên thẩm định trước khi áp dụng."


def require_user_or_admin(
    principal: Annotated[Principal, Depends(get_principal)],
) -> Principal:
    if not principal.has(Permission.QUERY) and not principal.has(Permission.ADMIN):
        raise api_error(status.HTTP_403_FORBIDDEN, "QUERY_REQUIRED")
    return principal

RunStatusLiteral = Literal[
    "queued", "running", "completed", "failed", "cancelled", "expired"
]
FindingTypeLiteral = Literal[
    "contradiction", "overlap", "exception_refinement", "superseded_already"
]
SeverityLiteral = Literal["high", "medium", "low"]
DetectionMethodLiteral = Literal["rule", "rule_plus_ai"]
ReviewStatusLiteral = Literal["pending", "confirmed", "dismissed", "linked_amendment"]
PrecedenceResultLiteral = Literal[
    "higher_authority_a",
    "higher_authority_b",
    "same_tier_newer_a",
    "same_tier_newer_b",
    "superseded_by_amendment",
    "undetermined_requires_review",
]
AmendmentActionLiteral = Literal[
    "modify", "replace", "add", "repeal", "repeal_partial", "suspend"
]


class CreateConflictScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=8, max_length=64)
    document_ids: list[UUID] = Field(default_factory=list)
    category_id: UUID | None = None
    doc_types: list[str] = Field(default_factory=list, max_length=30)
    taxonomy_codes: list[str] = Field(default_factory=list, max_length=50)
    as_of_date: date | None = None
    include_expired: bool = False
    use_ai: bool = False


class CreateConflictScanResponse(BaseModel):
    run_id: UUID
    status: RunStatusLiteral
    scope_document_count: int
    created_at: datetime
    deduplicated: bool = False


class ConflictScanRunView(BaseModel):
    id: UUID
    run_id: UUID
    requested_by: UUID
    request_id: str
    status: RunStatusLiteral
    scope_json: dict[str, Any]
    scope_document_count: int
    as_of_date: date
    use_ai: bool
    model_profile_id: UUID | None = None
    limits_json: dict[str, Any]
    progress_total: int
    progress_done: int
    summary_json: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    expires_at: datetime
    reference_notice: str
    deduplicated: bool = False


class ConflictScanListResponse(BaseModel):
    total: int
    items: list[ConflictScanRunView]


class ConflictFindingView(BaseModel):
    id: UUID
    run_id: UUID
    document_a_id: UUID
    document_b_id: UUID
    node_a_id: UUID
    node_b_id: UUID
    document_a_number: str | None = None
    document_a_title: str | None = None
    document_b_number: str | None = None
    document_b_title: str | None = None
    node_a_label: str | None = None
    node_a_path: str | None = None
    node_a_text: str | None = None
    node_a_page_start: int | None = None
    node_b_label: str | None = None
    node_b_path: str | None = None
    node_b_text: str | None = None
    node_b_page_start: int | None = None
    finding_type: FindingTypeLiteral
    severity: SeverityLiteral
    detection_method: DetectionMethodLiteral
    similarity_score: float | None = None
    shared_labels: list[str] = Field(default_factory=list)
    signals_json: dict[str, Any]
    precedence_result: PrecedenceResultLiteral
    precedence_basis_json: dict[str, Any]
    explanation: str
    ai_confidence: float | None = None
    ai_verified: bool | None = None
    review_status: ReviewStatusLiteral
    reviewed_by: UUID | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
    linked_amendment_id: UUID | None = None
    created_at: datetime
    reference_notice: str


class ConflictScanDetailResponse(ConflictScanRunView):
    findings: list[ConflictFindingView]
    total_findings: int
    hidden_due_to_acl: int
    disclaimer: str


class AdminConflictFindingsResponse(BaseModel):
    total: int
    items: list[ConflictFindingView]
    disclaimer: str
    reference_notice: str


class ReviewFindingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["confirm", "dismiss"]
    review_note: str | None = Field(default=None, max_length=2000)
    create_amendment_draft: bool = False
    amendment_action: AmendmentActionLiteral | None = None
    source_side: Literal["a", "b"] | None = None
    valid_from: date | None = None


class FindingReviewResponse(BaseModel):
    finding_id: UUID
    review_status: ReviewStatusLiteral
    reviewed_by: UUID | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
    linked_amendment_id: UUID | None = None
    amendment_review_status: Literal["draft"] | None = None
    reference_notice: str


class AuthorityRuleView(BaseModel):
    id: UUID
    rule_code: str
    doc_type: str
    issuing_body_pattern: str | None = None
    authority_rank: int
    authority_tier_label: str
    is_ambiguous_without_issuer: bool
    match_priority: int
    note: str | None = None
    is_active: bool
    updated_by: UUID | None = None
    updated_at: datetime


class AuthorityRuleListResponse(BaseModel):
    total: int
    items: list[AuthorityRuleView]


class CreateAuthorityRuleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_code: str = Field(min_length=1, max_length=100)
    doc_type: str = Field(min_length=1, max_length=80)
    issuing_body_pattern: str | None = Field(default=None, max_length=500)
    authority_rank: int = Field(ge=1, le=1000)
    authority_tier_label: str = Field(min_length=1, max_length=200)
    is_ambiguous_without_issuer: bool = False
    match_priority: int = Field(default=100, ge=0, le=10000)
    note: str | None = Field(default=None, max_length=2000)
    is_active: bool = True


class UpdateAuthorityRuleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authority_rank: int | None = Field(default=None, ge=1, le=1000)
    authority_tier_label: str | None = Field(default=None, min_length=1, max_length=200)
    issuing_body_pattern: str | None = Field(default=None, max_length=500)
    clear_pattern: bool = False
    is_ambiguous_without_issuer: bool | None = None
    match_priority: int | None = Field(default=None, ge=0, le=10000)
    note: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None


def _scope_doc_count(run: dict[str, Any]) -> int:
    scope = run.get("scope_json") or {}
    return len(scope.get("resolved_document_ids") or ())


def _run_view_payload(run: dict[str, Any]) -> dict[str, Any]:
    return {
        **run,
        "run_id": run["id"],
        "scope_document_count": _scope_doc_count(run),
    }


@router.post(
    "/conflicts/scans",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CreateConflictScanResponse,
)
async def create_conflict_scan_route(
    request: Request,
    body: CreateConflictScanRequest,
    principal: Annotated[Principal, Depends(require_user)],
) -> dict[str, Any]:
    settings = getattr(request.app.state, "settings", None)
    operating_mode = settings.operating_mode if settings is not None else None
    try:
        run = await create_conflict_run(
            database_pool(request),
            principal,
            request_id=body.request_id,
            document_ids=body.document_ids,
            category_ids=[body.category_id] if body.category_id is not None else (),
            doc_types=body.doc_types,
            taxonomy_codes=body.taxonomy_codes,
            as_of_date=body.as_of_date,
            use_ai=body.use_ai,
            include_expired=body.include_expired,
            settings=settings,
            operating_mode=operating_mode,
        )
    except ConflictStoreError as exc:
        raise api_error(exc.status_code, exc.code, details=exc.details) from exc

    worker = getattr(request.app.state, "conflict_scan_worker", None)
    if worker is not None and hasattr(worker, "wake"):
        worker.wake()

    return {
        "run_id": run["id"],
        "status": run["status"],
        "scope_document_count": _scope_doc_count(run),
        "created_at": run["created_at"],
        "deduplicated": bool(run.get("deduplicated", False)),
    }


@router.get("/conflicts/scans", response_model=ConflictScanListResponse)
async def list_conflict_scans_route(
    request: Request,
    principal: Annotated[Principal, Depends(require_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    data = await list_conflict_runs(
        database_pool(request), principal, limit=limit, offset=offset
    )
    return {
        "total": data["total"],
        "items": [_run_view_payload(item) for item in data["items"]],
    }


@router.get("/conflicts/scans/{run_id}", response_model=ConflictScanDetailResponse)
async def get_conflict_scan_detail_route(
    request: Request,
    run_id: UUID,
    principal: Annotated[Principal, Depends(require_user)],
    severity: SeverityLiteral | None = None,
    finding_type: FindingTypeLiteral | None = None,
    review_status: ReviewStatusLiteral | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    pool = database_pool(request)
    try:
        run = await get_conflict_run(pool, principal, run_id)
        findings_page = await list_conflict_findings(
            pool,
            principal,
            run_id,
            severity=severity,
            finding_type=finding_type,
            review_status=review_status,
            limit=limit,
            offset=offset,
        )
    except ConflictStoreError as exc:
        raise api_error(exc.status_code, exc.code, details=exc.details) from exc

    return {
        **_run_view_payload(run),
        "findings": findings_page["items"],
        "total_findings": findings_page["total"],
        "hidden_due_to_acl": findings_page["hidden_due_to_acl"],
        "disclaimer": _DISCLAIMER,
    }


@router.post("/conflicts/scans/{run_id}/cancel", response_model=ConflictScanRunView)
async def cancel_conflict_scan_route(
    request: Request,
    run_id: UUID,
    principal: Annotated[Principal, Depends(require_user_or_admin)],
) -> dict[str, Any]:
    try:
        run = await cancel_conflict_run(database_pool(request), principal, run_id)
    except ConflictStoreError as exc:
        raise api_error(exc.status_code, exc.code, details=exc.details) from exc
    return _run_view_payload(run)


@router.get("/admin/conflicts/findings", response_model=AdminConflictFindingsResponse)
async def list_admin_conflict_findings_route(
    request: Request,
    principal: Annotated[Principal, Depends(require_document_reviewer)],
    review_status: ReviewStatusLiteral | None = None,
    severity: SeverityLiteral | None = None,
    finding_type: FindingTypeLiteral | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    try:
        page = await list_admin_conflict_findings(
            database_pool(request),
            UUID(principal.id),
            review_status=review_status,
            severity=severity,
            finding_type=finding_type,
            limit=limit,
            offset=offset,
        )
    except ConflictStoreError as exc:
        raise api_error(exc.status_code, exc.code, details=exc.details) from exc
    return {
        **page,
        "disclaimer": _DISCLAIMER,
    }


@router.post(
    "/admin/conflicts/findings/{finding_id}/review",
    response_model=FindingReviewResponse,
)
async def review_conflict_finding_route(
    request: Request,
    finding_id: UUID,
    body: ReviewFindingRequest,
    principal: Annotated[Principal, Depends(require_document_reviewer)],
) -> dict[str, Any]:
    try:
        return await review_conflict_finding_with_draft(
            database_pool(request),
            reviewer_id=UUID(principal.id),
            finding_id=finding_id,
            decision=body.decision,
            note=body.review_note,
            create_amendment_draft=body.create_amendment_draft,
            amendment_action=body.amendment_action,
            source_side=body.source_side,
            valid_from=body.valid_from,
        )
    except ConflictStoreError as exc:
        raise api_error(exc.status_code, exc.code, details=exc.details) from exc


@router.get("/admin/authority-rules", response_model=AuthorityRuleListResponse)
async def list_authority_rules_route(
    request: Request,
    _principal: Annotated[Principal, Depends(require_admin)],
    include_inactive: bool = False,
) -> dict[str, Any]:
    rules = await list_authority_rules(
        database_pool(request), include_inactive=include_inactive
    )
    return {"total": len(rules), "items": rules}


@router.post(
    "/admin/authority-rules",
    status_code=status.HTTP_201_CREATED,
    response_model=AuthorityRuleView,
)
async def create_authority_rule_route(
    request: Request,
    body: CreateAuthorityRuleRequest,
    principal: Annotated[Principal, Depends(require_admin)],
) -> dict[str, Any]:
    try:
        return await create_authority_rule(
            database_pool(request),
            actor_id=UUID(principal.id),
            rule_code=body.rule_code,
            doc_type=body.doc_type,
            authority_rank=body.authority_rank,
            authority_tier_label=body.authority_tier_label,
            issuing_body_pattern=body.issuing_body_pattern,
            is_ambiguous_without_issuer=body.is_ambiguous_without_issuer,
            match_priority=body.match_priority,
            note=body.note,
            is_active=body.is_active,
        )
    except ConflictStoreError as exc:
        raise api_error(exc.status_code, exc.code, details=exc.details) from exc


@router.put("/admin/authority-rules/{rule_id}", response_model=AuthorityRuleView)
async def update_authority_rule_route(
    request: Request,
    rule_id: UUID,
    body: UpdateAuthorityRuleRequest,
    principal: Annotated[Principal, Depends(require_admin)],
) -> dict[str, Any]:
    clear_pattern = (
        body.clear_pattern
        or ("issuing_body_pattern" in body.model_fields_set and body.issuing_body_pattern is None)
        or (body.issuing_body_pattern == "")
    )
    clear_note = "note" in body.model_fields_set and body.note is None
    try:
        return await update_authority_rule(
            database_pool(request),
            actor_id=UUID(principal.id),
            rule_id=rule_id,
            authority_rank=body.authority_rank,
            authority_tier_label=body.authority_tier_label,
            issuing_body_pattern=None if clear_pattern else body.issuing_body_pattern,
            clear_pattern=clear_pattern,
            is_ambiguous_without_issuer=body.is_ambiguous_without_issuer,
            match_priority=body.match_priority,
            note=body.note,
            clear_note=clear_note,
            is_active=body.is_active,
        )
    except ConflictStoreError as exc:
        raise api_error(exc.status_code, exc.code, details=exc.details) from exc
