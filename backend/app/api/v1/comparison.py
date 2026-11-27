"""User-facing comparison routes (C2): versions, compare, node timeline, AI summary."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict

from ...auth_acl.policy import Principal
from ...comparison.service import (
    CompareError,
    CompareSelection,
    compare_documents,
    get_authorized_compare_node_source,
    list_document_versions,
    node_timeline_diff,
)
from ...comparison.summarize import summarize_comparison
from ...schemas import EffectivityView
from .dependencies import no_store
from .errors import api_error
from .guards import database_pool
from .original_response import original_file_response
from .user import require_user

router = APIRouter(prefix="/api/v1", tags=["comparison"], dependencies=[Depends(no_store)])

ChangeKindLiteral = Literal["unchanged", "modified", "moved_or_renumbered", "added", "removed"]
AlignmentLiteral = Literal["explicit_amendment", "structural_key", "semantic_lexical"]
ImpactLiteral = Literal["high", "medium", "low"]
ModeLiteral = Literal["versions", "amendment_pair", "cross_document"]


class CompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: ModeLiteral
    left_document_id: UUID
    right_document_id: UUID
    left_version_id: UUID | None = None
    right_version_id: UUID | None = None
    as_of_date: date | None = None
    only_changes: bool = False
    include_embeddings: bool = True


class DocumentMeta(BaseModel):
    id: UUID
    title: str
    document_number: str | None = None
    doc_type: str
    issuing_body: str | None = None


class VersionInfo(BaseModel):
    id: UUID
    version_number: int
    publication_date: date | None = None
    effective_from: date | None = None
    is_current: bool
    based_on_version_id: UUID | None = None
    # DB column reviewed_at (migration 0002); the plan's "approved_at" does not exist.
    reviewed_at: datetime | None = None


class RelatedAmendmentDocument(DocumentMeta):
    directions: list[Literal["amends_this_document", "amended_by_this_document"]]
    actions: list[str]


class DocumentVersionsResponse(BaseModel):
    document: DocumentMeta
    versions: list[VersionInfo]
    related_amendment_documents: list[RelatedAmendmentDocument]


class SpanView(BaseModel):
    value_num: float
    unit_normalized: str
    raw_text: str


class ChangeSignalsView(BaseModel):
    deadlines_changed: list[SpanView] = []
    amounts_changed: list[SpanView] = []
    # (day, month, year) triples exactly as extracted; no calendar validation implied.
    dates_changed: list[tuple[int, int, int]] = []
    modality_shifted: bool = False
    exception_changed: bool = False
    impact_level: ImpactLiteral = "low"


class DiffSegmentView(BaseModel):
    op: Literal["equal", "delete", "insert"]
    text: str


class SideView(BaseModel):
    node_id: UUID
    member_node_ids: list[UUID]
    citation_label: str | None = None
    structural_key: str
    text_original: str
    page_start: int | None = None
    page_end: int | None = None


class AmendmentLinkView(BaseModel):
    action: str | None = None
    valid_from: date | None = None
    source_quote: str | None = None


class ComparisonItem(BaseModel):
    item_key: str
    change_kind: ChangeKindLiteral
    # Meaningful only for moved_or_renumbered; read change_kind first (C1 note 5).
    content_also_modified: bool = False
    alignment_method: AlignmentLiteral | None = None
    alignment_score: float | None = None
    impact_level: ImpactLiteral
    signals: ChangeSignalsView
    amendment_link: AmendmentLinkView | None = None
    left: SideView | None = None
    right: SideView | None = None
    diff_segments: list[DiffSegmentView] = []


class CompareSummary(BaseModel):
    total_items: int
    added: int
    removed: int
    modified: int
    moved_or_renumbered: int
    unchanged: int
    high_impact_changes: int
    explicit_amendment_links: int
    deterministic_highlights: list[str] = []


class DocumentSide(DocumentMeta):
    version_id: UUID
    version_number: int
    effectivity: EffectivityView


class CompareResponse(BaseModel):
    comparison_id: UUID
    mode: ModeLiteral
    as_of_date: date
    left_doc: DocumentSide
    right_doc: DocumentSide
    summary: CompareSummary
    items: list[ComparisonItem]
    disclaimer: str


class NodeVersionRef(BaseModel):
    id: UUID
    version_number: int


class NodeAmendmentView(BaseModel):
    id: UUID
    action: str
    scope: Literal["document", "node"]
    valid_from: date | None = None
    source_quote: str | None = None
    evidence_source: str
    source_node_id: UUID
    source_label: str | None = None
    source_document: DocumentMeta


class NodeDiffResponse(BaseModel):
    node_id: UUID
    document: DocumentMeta
    version: NodeVersionRef
    as_of_date: date
    current: SideView
    # Spec A5: a missing previous version is stated here, never returned as an error.
    has_previous: bool
    previous_version: NodeVersionRef | None = None
    previous: SideView | None = None
    message: str | None = None
    change_kind: ChangeKindLiteral | None = None
    content_also_modified: bool = False
    alignment_method: AlignmentLiteral | None = None
    alignment_score: float | None = None
    impact_level: ImpactLiteral | None = None
    signals: ChangeSignalsView | None = None
    diff_segments: list[DiffSegmentView] = []
    amendments: list[NodeAmendmentView] = []
    effectivity: EffectivityView | None = None
    disclaimer: str


class KeyChangeView(BaseModel):
    point: str
    item_keys: list[str]
    evidence_ids: list[str]
    status: Literal["verified", "needs_review"]
    check_notes: list[str] = []


class SummarizeResponse(BaseModel):
    comparison_id: UUID
    mode_used: Literal["ai", "deterministic_fallback"]
    reason: str | None = None
    executive_summary: str | None = None
    summary_status: Literal["verified", "needs_review"] | None = None
    key_changes: list[KeyChangeView] = []
    deterministic_highlights: list[str] = []
    external_api_used: bool = False
    ai_limited: bool = False
    disclaimer: str


def _selection(body: CompareRequest) -> CompareSelection:
    return CompareSelection(
        mode=body.mode,
        left_document_id=body.left_document_id,
        right_document_id=body.right_document_id,
        as_of_date=body.as_of_date or date.today(),
        left_version_id=body.left_version_id,
        right_version_id=body.right_version_id,
        only_changes=body.only_changes,
        include_embeddings=body.include_embeddings,
    )


@router.get("/documents/{document_id}/versions", response_model=DocumentVersionsResponse)
async def get_document_versions(
    request: Request,
    document_id: UUID,
    principal: Annotated[Principal, Depends(require_user)],
) -> dict[str, Any]:
    try:
        return await list_document_versions(
            database_pool(request), UUID(principal.id), document_id
        )
    except CompareError as exc:
        raise api_error(exc.status_code, exc.code, details=exc.details) from exc


@router.post("/compare/documents", response_model=CompareResponse)
async def compare_documents_route(
    request: Request,
    body: CompareRequest,
    principal: Annotated[Principal, Depends(require_user)],
) -> dict[str, Any]:
    try:
        return await compare_documents(
            database_pool(request), UUID(principal.id), _selection(body)
        )
    except CompareError as exc:
        raise api_error(exc.status_code, exc.code, details=exc.details) from exc


@router.get("/nodes/{node_id}/diff", response_model=NodeDiffResponse)
async def get_node_diff(
    request: Request,
    node_id: UUID,
    principal: Annotated[Principal, Depends(require_user)],
    as_of_date: date | None = None,
) -> dict[str, Any]:
    try:
        return await node_timeline_diff(
            database_pool(request), UUID(principal.id), node_id,
            as_of_date or date.today(),
        )
    except CompareError as exc:
        raise api_error(exc.status_code, exc.code, details=exc.details) from exc


@router.post("/compare/summarize", response_model=SummarizeResponse)
async def summarize_route(
    request: Request,
    body: CompareRequest,
    principal: Annotated[Principal, Depends(require_user)],
) -> dict[str, Any]:
    runtime = getattr(request.app.state, "ai_runtime", None)
    try:
        return await summarize_comparison(
            database_pool(request), runtime, UUID(principal.id), _selection(body)
        )
    except CompareError as exc:
        raise api_error(exc.status_code, exc.code, details=exc.details) from exc


@router.get("/compare/nodes/{node_id}/original")
async def get_compare_node_original(
    request: Request,
    node_id: UUID,
    principal: Annotated[Principal, Depends(require_user)],
) -> Response:
    """Original file for an approved, source-valid comparison node (retired versions ok)."""

    try:
        source = await get_authorized_compare_node_source(
            database_pool(request), UUID(principal.id), node_id
        )
    except CompareError as exc:
        raise api_error(exc.status_code, exc.code, details=exc.details) from exc
    return await original_file_response(request.app.state.settings, source)
