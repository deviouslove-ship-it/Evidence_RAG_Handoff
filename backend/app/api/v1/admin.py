"""Admin routes with explicit role checks.

CURATOR creates/submits drafts, REVIEWER resolves review tasks and approves/rejects
versions, SYS_ADMIN manages categories/users/ACL/Model Registry, and AUDITOR/SYS_ADMIN
inspects the hash-chained audit log.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Annotated, Any, Literal, TypeVar, cast
from urllib.parse import quote
from uuid import UUID

import asyncpg
import pypdfium2 as pdfium
from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from ...admin_services import (
    AdminServiceError,
    create_category,
    create_or_update_user,
    delete_category,
    delete_user,
    list_all_categories,
    list_audit_events,
    list_model_registry,
    list_users,
    update_category,
    upsert_model_profile,
    upsert_stage_policy,
    upsert_stage_route,
    valid_roles,
)
from ...audit import append_audit
from ...auth_acl.policy import Permission, Principal
from ...documents.convert import PDF_MAGIC, ConvertedSource, convert_to_pdf
from ...documents.deduplication import find_content_matches
from ...documents.draft import new_original_base, persist_draft, prepare_draft
from ...documents.draft_read import list_document_drafts, load_draft_pdf
from ...documents.management_access import scope_params, version_scope
from ...documents.management_read import detail as managed_document_detail
from ...documents.management_read import list_documents
from ...documents.management_read import original as managed_document_original
from ...documents.management_write import DocumentAction, change_availability, change_version
from ...documents.ocr import configured_ocr_engine
from ...documents.preview import inspect_pdf_preview
from ...documents.provenance import sha256_bytes
from ...documents.reextract import apply_reextracted_draft
from ...documents.review import (
    ReviewError,
    approve_document_version,
    list_review_tasks,
    reject_document_version,
    resolve_review_task,
    submit_draft_for_review,
)
from ...model_registry.diagnostics import diagnose_profile, diagnose_saved
from ...model_registry.profiles import ModelProfile, PrivacyZone
from ...model_registry.runtime import EndpointPolicy, RegistryRuntime
from ...model_registry.secret_store import SecretStoreError
from ...model_registry.stages import STAGES
from ...schemas import (
    AmendmentStatus,
    ModelProfileRequest,
    PdfContentDuplicates,
    PdfDraftListItem,
    PdfDraftResponse,
    PdfPreviewResponse,
    PdfReextractResponse,
    StagePolicyRequest,
)
from ...storage.embedding_jobs import (
    DEFAULT_BATCH_SIZE,
    MAX_BATCH_SIZE,
    EmbeddingJobError,
    control_job,
    create_job,
    embedding_overview,
    preflight,
)
from .dependencies import get_principal, no_store
from .errors import api_error
from .guards import (
    database_pool,
    require_admin,
    require_curator,
    require_document_reviewer,
    require_reviewer,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
_USERS_PATH = "/" + "users"
_PdfResult = TypeVar("_PdfResult")
_CONVERSION_ERRORS = frozenset({
    "UNSUPPORTED_FILE_TYPE", "DOCUMENT_ENCRYPTED", "DOCUMENT_TEXT_EMPTY",
    "DOCUMENT_CONVERT_FAILED", "TXT_ENCODING_UNSUPPORTED",
})


async def _run_pdf_work(
    request: Request, function: Callable[..., _PdfResult], *args: Any, **kwargs: Any
) -> _PdfResult:
    slots = request.app.state.pdf_slots
    try:
        await asyncio.wait_for(slots.acquire(), timeout=0.1)
    except TimeoutError as exc:
        raise api_error(429, "PDF_WORKER_BUSY") from exc
    try:
        return await run_in_threadpool(function, *args, **kwargs)
    finally:
        slots.release()


async def _convert_upload(
    request: Request, upload: bytes, filename: str | None, max_pages: int
) -> ConvertedSource:
    """PDFs pass straight through; Word/TXT are rendered to PDF on the worker pool."""
    if upload.startswith(PDF_MAGIC):
        return convert_to_pdf(upload, filename, max_pages=max_pages)
    return await _run_pdf_work(request, convert_to_pdf, upload, filename, max_pages=max_pages)


def require_admin_or_auditor(
    principal: Annotated[Principal, Depends(get_principal)],
) -> Principal:
    if not principal.has(Permission.ADMIN) and not principal.has(Permission.AUDIT):
        raise api_error(status.HTTP_403_FORBIDDEN, "AUDITOR_REQUIRED")
    return principal


def require_admin_or_doc_staff(
    principal: Annotated[Principal, Depends(get_principal)],
) -> Principal:
    if (
        not principal.has(Permission.ADMIN)
        and not principal.has(Permission.CURATE)
        and not principal.has(Permission.REVIEW)
    ):
        raise api_error(status.HTTP_403_FORBIDDEN, "ADMIN_REQUIRED")
    return principal


class CategoryCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=250)
    remote_processing_allowed: bool = False


class UserUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=150)
    display_name: str = Field(min_length=1, max_length=250)
    password: str | None = Field(default=None, min_length=1, max_length=256)
    roles: list[str] = Field(min_length=1)
    category_ids: list[UUID] = Field(default_factory=list)
    # D10: categories in which a REVIEWER may confirm effectivity (can_review).
    review_category_ids: list[UUID] = Field(default_factory=list)
    must_change_password: bool = True
    disabled: bool = False
    remote_ai_allowed: bool = False


class ReviewTaskResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolution_note: str = Field(min_length=1, max_length=2000)


class VersionApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_ids: list[UUID] = Field(min_length=1)
    review_note: str = Field(min_length=1, max_length=2000)
    resolve_all_tasks: bool = False
    # Dates read by rule are confirmed with the approval; these correct them.
    publication_date: date | None = None
    effective_from: date | None = None
    revision: int | None = Field(default=None, ge=1)


class VersionRejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_note: str = Field(min_length=1, max_length=2000)
    revision: int | None = Field(default=None, ge=1)


class StageRouteUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str = Field(min_length=1, max_length=16)
    stage: str = Field(min_length=1, max_length=80)
    profile_id: str = Field(min_length=1, max_length=100)
    fallback: list[str] = Field(default_factory=list, max_length=1)
    # API mode only (Hybrid Auto): public profile tried when local output fails the check.
    escalation_profile_id: str | None = Field(default=None, max_length=100)


class EmbeddingPreflightRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str = Field(min_length=1, max_length=100)
    # True = open a fresh index even if finished vectors of this model exist.
    rebuild: bool = False
    batch_size: int = Field(default=DEFAULT_BATCH_SIZE, ge=1, le=MAX_BATCH_SIZE)


class EmbeddingJobRequest(EmbeddingPreflightRequest):
    # The administrator saw the preflight counts and confirmed the rebuild.
    confirmed: bool = False


@router.post("/documents/preview", response_model=PdfPreviewResponse)
async def preview_document(
    request: Request,
    file: Annotated[UploadFile, File()],
    _principal: Annotated[Principal, Depends(require_curator)],
) -> PdfPreviewResponse:
    upload = await _read_bounded_pdf(file, request.app.state.settings.max_upload_bytes)
    try:
        converted = await _convert_upload(
            request, upload, file.filename, request.app.state.settings.max_preview_pages,
        )
        content = converted.pdf
        return await _run_pdf_work(
            request,
            inspect_pdf_preview,
            content,
            max_pages=request.app.state.settings.max_preview_pages,
            ocr_engine=configured_ocr_engine(),
            isolate=True,
            timeout_seconds=request.app.state.settings.pdf_timeout_seconds,
            temporary_root=(
                Path(request.app.state.settings.document_store_root)
                if request.app.state.settings.document_store_root else None
            ),
        )
    except ValueError as exc:
        code = str(exc)
        if code in {"PDF_PAGE_LIMIT_EXCEEDED", "PDF_RESOURCE_LIMIT_EXCEEDED"}:
            raise api_error(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, code) from exc
        if code == "PDF_PARSE_TIMEOUT":
            raise api_error(504, code) from exc
        if code in {"INVALID_PDF_MAGIC", "INVALID_PDF_STRUCTURE", "PDF_PARSE_FAILED",
                    *_CONVERSION_ERRORS}:
            raise api_error(status.HTTP_422_UNPROCESSABLE_ENTITY, code) from exc
        raise


@router.post(
    "/documents/drafts",
    response_model=PdfDraftResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_document_draft(
    request: Request,
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form(min_length=1, max_length=500)],
    doc_type: Annotated[str, Form(min_length=1, max_length=80)],
    principal: Annotated[Principal, Depends(require_curator)],
    document_number: Annotated[str | None, Form(max_length=100)] = None,
    issuing_body: Annotated[str | None, Form(max_length=300)] = None,
    publication_date: Annotated[date | None, Form()] = None,
    official_url: Annotated[str | None, Form(max_length=2000)] = None,
    document_id: Annotated[UUID | None, Form()] = None,
    revision: Annotated[int | None, Form(ge=1)] = None,
) -> PdfDraftResponse:
    settings = request.app.state.settings
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None or not settings.document_store_root:
        raise api_error(status.HTTP_503_SERVICE_UNAVAILABLE, "DRAFT_STORE_NOT_CONFIGURED")
    title = title.strip()
    doc_type = doc_type.strip()
    if not title or not doc_type:
        raise api_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "INVALID_DOCUMENT_METADATA")
    existing_document = None
    if document_id is not None:
        if revision is None:
            raise api_error(422, "INVALID_REQUEST")
        try:
            async with pool.acquire() as connection:
                await new_original_base(connection, principal, document_id, revision)
        except ReviewError as exc:
            raise api_error(exc.status_code, exc.code) from exc
        existing_document = (document_id, revision, principal)
    upload = await _read_bounded_pdf(file, settings.max_upload_bytes)
    try:
        converted = await _convert_upload(
            request, upload, file.filename, settings.max_preview_pages,
        )
    except ValueError as exc:
        code = str(exc)
        if code in {"PDF_PAGE_LIMIT_EXCEEDED", "PDF_RESOURCE_LIMIT_EXCEEDED"}:
            raise api_error(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, code) from exc
        if code == "INVALID_PDF_MAGIC" or code in _CONVERSION_ERRORS:
            raise api_error(status.HTTP_422_UNPROCESSABLE_ENTITY, code) from exc
        raise
    content = converted.pdf
    async with pool.acquire() as connection:
        already_exists = await connection.fetchval(
            "SELECT EXISTS(SELECT 1 FROM document_versions WHERE original_file_sha256=$1)",
            sha256_bytes(content),
        )
    if already_exists:
        raise api_error(409, "DUPLICATE_PDF_HASH")
    try:
        prepared = await _run_pdf_work(
            request,
            prepare_draft,
            content,
            max_pages=settings.max_preview_pages,
            ocr_engine=configured_ocr_engine(),
            temporary_root=Path(settings.document_store_root),
            isolate=True,
            timeout_seconds=settings.pdf_timeout_seconds,
        )
        return await persist_draft(
            prepared,
            pool=pool,
            store_root=Path(settings.document_store_root),
            title=title,
            doc_type=doc_type,
            original_filename=file.filename or "document.pdf",
            document_number=(document_number.strip() or None) if document_number else None,
            issuing_body=(issuing_body.strip() or None) if issuing_body else None,
            publication_date=publication_date,
            official_url=official_url,
            submitted_by=UUID(principal.id),
            converted=converted if converted.source_format != "pdf" else None,
            existing_document=existing_document,
        )
    except ReviewError as exc:
        raise api_error(exc.status_code, exc.code) from exc
    except asyncpg.UniqueViolationError as exc:
        raise api_error(status.HTTP_409_CONFLICT, "DUPLICATE_PDF_HASH") from exc
    except pdfium.PdfiumError as exc:
        raise api_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "PDF_PARSE_FAILED") from exc
    except ValueError as exc:
        code = str(exc)
        if code in {"PDF_PAGE_LIMIT_EXCEEDED", "PDF_RESOURCE_LIMIT_EXCEEDED"}:
            raise api_error(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, code) from exc
        if code == "PDF_PARSE_TIMEOUT":
            raise api_error(504, code) from exc
        if code in {"INVALID_PDF_MAGIC", "INVALID_PDF_STRUCTURE", "INVALID_SOURCE_URL",
                    "PDF_PARSE_FAILED"}:
            raise api_error(status.HTTP_422_UNPROCESSABLE_ENTITY, code) from exc
        raise


@router.post(
    "/documents/drafts/{version_id}/reextract", response_model=PdfReextractResponse,
)
async def reextract_document_draft(
    version_id: UUID,
    request: Request,
    principal: Annotated[Principal, Depends(require_curator)],
) -> dict[str, int | str]:
    settings = request.app.state.settings
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None or not settings.document_store_root:
        raise api_error(status.HTTP_503_SERVICE_UNAVAILABLE, "DRAFT_STORE_NOT_CONFIGURED")
    try:
        content = await load_draft_pdf(
            pool, store_root=Path(settings.document_store_root), version_id=version_id,
            max_bytes=settings.max_upload_bytes, staff=scope_params(principal),
            legacy_reextract=True,
        )
        prepared = await _run_pdf_work(
            request, prepare_draft, content, max_pages=settings.max_preview_pages,
            ocr_engine=configured_ocr_engine(), temporary_root=Path(settings.document_store_root),
            isolate=True, timeout_seconds=settings.pdf_timeout_seconds,
        )
        return await apply_reextracted_draft(
            pool, prepared=prepared, version_id=version_id, curator_id=UUID(principal.id),
        )
    except KeyError as exc:
        raise api_error(404, "DRAFT_NOT_FOUND") from exc
    except ReviewError as exc:
        raise api_error(exc.status_code, exc.code) from exc
    except ValueError as exc:
        code = str(exc)
        if code == "DRAFT_STORAGE_CONFLICT":
            raise api_error(503, "DRAFT_PDF_UNAVAILABLE") from exc
        if code == "PDF_PARSE_TIMEOUT":
            raise api_error(504, code) from exc
        if code in {"PDF_PAGE_LIMIT_EXCEEDED", "PDF_RESOURCE_LIMIT_EXCEEDED"}:
            raise api_error(413, code) from exc
        if code in {"INVALID_PDF_MAGIC", "INVALID_PDF_STRUCTURE", "PDF_PARSE_FAILED"}:
            raise api_error(422, code) from exc
        raise
    except pdfium.PdfiumError as exc:
        raise api_error(422, "PDF_PARSE_FAILED") from exc


@router.get("/documents/drafts/{version_id}/duplicates", response_model=PdfContentDuplicates)
async def get_draft_content_duplicates(
    version_id: UUID,
    request: Request,
    principal: Annotated[Principal, Depends(require_document_reviewer)],
) -> PdfContentDuplicates:
    pool = database_pool(request)
    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            """SELECT dv.native_text_fingerprint_v1 FROM document_versions dv
               JOIN documents d ON d.id=dv.document_id
               WHERE dv.id=$1 AND dv.review_status IN ('draft', 'pending_review')
                 AND d.deleted_at IS NULL""", version_id,
        )
        if row is None:
            raise api_error(404, "DRAFT_NOT_FOUND")
        actor, curator, reviewer = scope_params(principal)
        scope = await version_scope(connection, version_id, actor, curator=curator,
                                    reviewer=reviewer)
        if scope is None or (scope["managed"] and not scope["can_read"]):
            raise api_error(404, "DRAFT_NOT_FOUND")
        fingerprint = row["native_text_fingerprint_v1"]
        matches = await find_content_matches(
            connection, fingerprint=fingerprint, viewer_id=UUID(principal.id),
            exclude_version_id=version_id, lock=False,
        ) if fingerprint is not None else []
    return PdfContentDuplicates(
        content_check_available=fingerprint is not None, potential_duplicates=matches,
    )


@router.get("/documents/drafts", response_model=list[PdfDraftListItem])
async def list_drafts(
    request: Request,
    principal: Annotated[Principal, Depends(require_document_reviewer)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[PdfDraftListItem]:
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise api_error(status.HTTP_503_SERVICE_UNAVAILABLE, "DRAFT_STORE_NOT_CONFIGURED")
    return await list_document_drafts(pool, limit=limit, offset=offset,
                                      staff=scope_params(principal))


@router.get("/documents/drafts/{version_id}/pdf")
async def draft_pdf(
    request: Request,
    version_id: UUID,
    principal: Annotated[Principal, Depends(require_document_reviewer)],
) -> Response:
    settings = request.app.state.settings
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None or not settings.document_store_root:
        raise api_error(status.HTTP_503_SERVICE_UNAVAILABLE, "DRAFT_STORE_NOT_CONFIGURED")
    try:
        content = await load_draft_pdf(
            pool, store_root=Path(settings.document_store_root),
            version_id=version_id, max_bytes=settings.max_upload_bytes,
            staff=scope_params(principal),
        )
    except KeyError as exc:
        raise api_error(status.HTTP_404_NOT_FOUND, "DRAFT_NOT_FOUND") from exc
    except ValueError as exc:
        raise api_error(status.HTTP_503_SERVICE_UNAVAILABLE, "DRAFT_PDF_UNAVAILABLE") from exc
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": 'inline; filename="document.pdf"',
        },
    )


@router.post("/documents/drafts/{version_id}/submit")
async def submit_draft(
    request: Request,
    version_id: UUID,
    principal: Annotated[Principal, Depends(require_curator)],
) -> dict[str, Any]:
    try:
        return await submit_draft_for_review(
            database_pool(request), version_id=version_id, curator_id=UUID(principal.id)
        )
    except ReviewError as exc:
        raise api_error(exc.status_code, exc.code) from exc


@router.get("/documents/review-tasks")
async def get_review_tasks(
    request: Request,
    principal: Annotated[Principal, Depends(require_document_reviewer)],
    version_id: UUID | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> list[dict[str, Any]]:
    return await list_review_tasks(
        database_pool(request), version_id=version_id, status_filter=status_filter,
        staff=scope_params(principal),
    )


@router.post("/documents/review-tasks/{task_id}/resolve")
async def resolve_task(
    request: Request,
    task_id: UUID,
    body: ReviewTaskResolveRequest,
    principal: Annotated[Principal, Depends(require_reviewer)],
) -> dict[str, Any]:
    try:
        return await resolve_review_task(
            database_pool(request),
            task_id=task_id,
            reviewer_id=UUID(principal.id),
            resolution_note=body.resolution_note,
        )
    except ReviewError as exc:
        raise api_error(exc.status_code, exc.code) from exc


@router.post("/documents/drafts/{version_id}/approve")
async def approve_version(
    request: Request,
    version_id: UUID,
    body: VersionApproveRequest,
    principal: Annotated[Principal, Depends(require_reviewer)],
) -> dict[str, Any]:
    settings = request.app.state.settings
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None or not settings.document_store_root:
        raise api_error(status.HTTP_503_SERVICE_UNAVAILABLE, "DRAFT_STORE_NOT_CONFIGURED")
    try:
        return await approve_document_version(
            pool,
            store_root=Path(settings.document_store_root),
            max_bytes=settings.max_upload_bytes,
            version_id=version_id,
            reviewer_id=UUID(principal.id),
            category_ids=body.category_ids,
            review_note=body.review_note,
            resolve_all_tasks=body.resolve_all_tasks,
            publication_date=body.publication_date,
            effective_from=body.effective_from,
            revision=body.revision,
        )
    except ReviewError as exc:
        raise api_error(exc.status_code, exc.code) from exc


@router.post("/documents/drafts/{version_id}/reject")
async def reject_version(
    request: Request,
    version_id: UUID,
    body: VersionRejectRequest,
    principal: Annotated[Principal, Depends(require_reviewer)],
) -> dict[str, Any]:
    try:
        return await reject_document_version(
            database_pool(request),
            version_id=version_id,
            reviewer_id=UUID(principal.id),
            review_note=body.review_note,
            revision=body.revision,
        )
    except ReviewError as exc:
        raise api_error(exc.status_code, exc.code) from exc


@router.get("/categories")
async def admin_categories(
    request: Request,
    _principal: Annotated[Principal, Depends(require_admin_or_doc_staff)],
) -> list[dict[str, Any]]:
    return await list_all_categories(database_pool(request))


@router.post("/categories", status_code=status.HTTP_201_CREATED)
async def admin_create_category(
    request: Request,
    body: CategoryCreateRequest,
    principal: Annotated[Principal, Depends(require_admin)],
) -> dict[str, Any]:
    try:
        return await create_category(
            database_pool(request),
            actor_id=UUID(principal.id),
            code=body.code,
            name=body.name,
            remote_processing_allowed=body.remote_processing_allowed,
        )
    except AdminServiceError as exc:
        raise api_error(exc.status_code, exc.code) from exc


@router.delete("/categories/{category_id}")
async def admin_delete_category(
    request: Request,
    category_id: UUID,
    principal: Annotated[Principal, Depends(require_admin)],
) -> dict[str, Any]:
    try:
        return await delete_category(
            database_pool(request),
            actor_id=UUID(principal.id),
            category_id=category_id,
        )
    except AdminServiceError as exc:
        raise api_error(exc.status_code, exc.code) from exc


@router.patch("/categories/{category_id}")
async def admin_update_category(
    request: Request, category_id: UUID, body: CategoryCreateRequest,
    principal: Annotated[Principal, Depends(require_admin)],
) -> dict[str, Any]:
    try:
        return await update_category(
            database_pool(request), actor_id=UUID(principal.id), category_id=category_id,
            code=body.code, name=body.name,
            remote_processing_allowed=body.remote_processing_allowed,
        )
    except AdminServiceError as exc:
        raise api_error(exc.status_code, exc.code) from exc


@router.get(_USERS_PATH)
async def admin_users(
    request: Request,
    _principal: Annotated[Principal, Depends(require_admin)],
) -> list[dict[str, Any]]:
    return await list_users(database_pool(request))


@router.post(_USERS_PATH, status_code=status.HTTP_201_CREATED)
async def admin_upsert_user(
    request: Request,
    body: UserUpsertRequest,
    principal: Annotated[Principal, Depends(require_admin)],
) -> dict[str, Any]:
    try:
        return await create_or_update_user(
            database_pool(request),
            actor_id=UUID(principal.id),
            username=body.username,
            display_name=body.display_name,
            password=body.password,
            roles=body.roles,
            category_ids=body.category_ids,
            review_category_ids=body.review_category_ids,
            must_change_password=body.must_change_password,
            disabled=body.disabled,
            remote_ai_allowed=body.remote_ai_allowed,
        )
    except AdminServiceError as exc:
        raise api_error(exc.status_code, exc.code) from exc


@router.delete(_USERS_PATH + "/{user_id}")
async def admin_delete_user(
    request: Request,
    user_id: UUID,
    principal: Annotated[Principal, Depends(require_admin)],
) -> dict[str, Any]:
    try:
        return await delete_user(
            database_pool(request),
            actor_id=UUID(principal.id),
            user_id=user_id,
        )
    except AdminServiceError as exc:
        raise api_error(exc.status_code, exc.code) from exc


async def _read_bounded_pdf(file: UploadFile, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    try:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                raise api_error(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "PDF_SIZE_LIMIT_EXCEEDED")
            chunks.append(chunk)
    finally:
        await file.close()
    return b"".join(chunks)


@router.get("/model-registry")
async def model_registry(
    request: Request,
    _principal: Annotated[Principal, Depends(require_admin)],
) -> dict[str, Any] | list[dict[str, object]]:
    registry = await list_model_registry(database_pool(request))
    registry["effective_mode"] = request.app.state.settings.operating_mode
    registry["supported_stages"] = list(STAGES)
    # Whether a typed API key can be stored on this server (never the keys themselves).
    registry["secret_store"] = {"available": _registry_runtime(request).secrets.available}
    return registry


def _registry_runtime(request: Request) -> RegistryRuntime:
    runtime = getattr(request.app.state, "ai_runtime", None)
    if runtime is not None:
        return cast(RegistryRuntime, runtime)
    return RegistryRuntime(
        database_pool(request), mode=request.app.state.settings.operating_mode,
        attempt_limit=request.app.state.settings.llm_attempt_budget,
        policy=EndpointPolicy.from_env(),
    )


def _secret_key_name(profile_id: str) -> str:
    """Store name of a profile's typed key: readable, unique per profile id."""

    clean = re.sub(r"[^A-Za-z0-9_.-]+", "_", profile_id.strip()).strip("._-")[:80] or "profile"
    return f"{clean}-{hashlib.sha256(profile_id.strip().encode()).hexdigest()[:8]}"


def _typed_key(body: ModelProfileRequest) -> str | None:
    return body.api_key.get_secret_value() if body.api_key else None


def _draft_profile(body: ModelProfileRequest) -> ModelProfile:
    if not valid_roles(frozenset(body.capabilities)):
        raise api_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "MODEL_STAGE_UNSUPPORTED")
    try:
        zone = PrivacyZone(body.privacy_zone)
    except ValueError as exc:
        raise api_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "INVALID_REQUEST") from exc
    return ModelProfile(
        profile_id=body.profile_id.strip(), adapter=body.adapter.strip(),
        endpoint=body.endpoint.strip(), model_id=body.model_id.strip(),
        capabilities=frozenset(body.capabilities), privacy_zone=zone,
        revision=body.revision.strip(), secret_ref=body.secret_ref,
        params=body.params.to_stored() if body.params else {}, provider_approved=True,
    )


@router.post("/model-registry", status_code=status.HTTP_201_CREATED)
async def create_model_profile(
    request: Request,
    body: ModelProfileRequest,
    principal: Annotated[Principal, Depends(require_admin)],
) -> dict[str, str]:
    pool = database_pool(request)
    secret_ref = body.secret_ref
    secret_writer = None
    if body.api_key:
        store = _registry_runtime(request).secrets
        if not store.available:
            raise api_error(status.HTTP_503_SERVICE_UNAVAILABLE, "SECRET_STORE_UNAVAILABLE")
        key_name = _secret_key_name(body.profile_id)
        key_value = body.api_key.get_secret_value()
        secret_ref = f"secret:{key_name}"

        def secret_writer() -> None:
            store.put(key_name, key_value)
    try:
        result = await upsert_model_profile(
            pool,
            actor_id=UUID(principal.id),
            profile_id=body.profile_id,
            adapter=body.adapter,
            endpoint=body.endpoint,
            model_id=body.model_id,
            capabilities=body.capabilities,
            privacy_zone=body.privacy_zone,
            revision=body.revision,
            secret_ref=secret_ref,
            fallback=body.fallback,
            provider_approved=body.provider_approved,
            params=body.params.to_stored() if body.params else {},
            costs={
                "input_price_per_mtok": body.input_price_per_mtok,
                "output_price_per_mtok": body.output_price_per_mtok,
                "daily_cost_limit": body.daily_cost_limit,
                "monthly_cost_limit": body.monthly_cost_limit,
            },
            secret_writer=secret_writer,
        )
        return {"profile_id": result["profile_id"], "status": result["status"]}
    except AdminServiceError as exc:
        raise api_error(exc.status_code, exc.code) from exc
    except SecretStoreError as exc:
        raise api_error(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc


# Checking a model may need a list call, one chat call and a slow first load of a local
# model; each call is bounded by the AI timeout (30 s at most), a dead server by 5 s.
_DIAGNOSIS_SECONDS = 95


@router.post("/model-registry/test")
async def test_model_profile_draft(
    request: Request, body: ModelProfileRequest,
    principal: Annotated[Principal, Depends(require_admin)],
) -> dict[str, Any]:
    """Check a profile that is not saved yet: configuration, key, connection, model and one
    synthetic request.  Nothing is stored; a typed key is used for this call only."""

    runtime = _registry_runtime(request)
    profile = _draft_profile(body)
    result: dict[str, Any] = await request.app.state.execution.run(
        request, lambda: diagnose_profile(runtime, profile, api_key=_typed_key(body)),
        principal_id=principal.id, timeout=_DIAGNOSIS_SECONDS,
    )
    result["profile_id"] = profile.profile_id
    result["model_id"] = profile.model_id
    async with database_pool(request).acquire() as connection, connection.transaction():
        await append_audit(
            connection, principal_id=UUID(principal.id), action="admin.test_model_draft",
            target_type="model_profile", target_id=profile.profile_id,
            metadata={"ok": result["ok"], "usable": result["usable"],
                      "failed": [item["id"] for item in result["checks"]
                                 if item["status"] == "fail"]},
        )
    return result


@router.post("/model-registry/{profile_id}/test")
async def test_saved_model_profile(
    request: Request, profile_id: str,
    principal: Annotated[Principal, Depends(require_admin)],
) -> dict[str, Any]:
    """Check a saved profile the same way and record its health (``ready`` only after a
    complete pass), which is what a stage assignment needs before it can be used."""

    runtime = _registry_runtime(request)
    result: dict[str, Any] = await request.app.state.execution.run(
        request, lambda: diagnose_saved(runtime, profile_id),
        principal_id=principal.id, timeout=_DIAGNOSIS_SECONDS,
    )
    async with database_pool(request).acquire() as connection, connection.transaction():
        await append_audit(
            connection, principal_id=UUID(principal.id), action="admin.test_model",
            target_type="model_profile", target_id=profile_id,
            metadata={"health": result.get("health"), "status": result.get("status"),
                      "failed": [item["id"] for item in result["checks"]
                                 if item["status"] == "fail"]},
        )
    return result


@router.post("/model-registry/routes")
async def configure_stage_route(
    request: Request,
    body: StageRouteUpsertRequest,
    principal: Annotated[Principal, Depends(require_admin)],
) -> dict[str, Any]:
    try:
        return await upsert_stage_route(
            database_pool(request),
            actor_id=UUID(principal.id),
            mode=body.mode,
            stage=body.stage,
            profile_id=body.profile_id,
            fallback=body.fallback,
            escalation_profile_id=body.escalation_profile_id,
        )
    except AdminServiceError as exc:
        raise api_error(exc.status_code, exc.code) from exc


@router.post("/model-registry/policies")
async def configure_stage_policy(
    request: Request,
    body: StagePolicyRequest,
    principal: Annotated[Principal, Depends(require_admin)],
) -> dict[str, Any]:
    try:
        return await upsert_stage_policy(
            database_pool(request),
            actor_id=UUID(principal.id),
            mode=body.mode,
            stage=body.stage,
            max_attempts=body.max_attempts,
            max_output_tokens=body.max_output_tokens,
            timeout_seconds=body.timeout_seconds,
            max_concurrency=body.max_concurrency,
        )
    except AdminServiceError as exc:
        raise api_error(exc.status_code, exc.code) from exc


@router.post("/model-registry/{profile_id}/probe")
async def probe_model_profile(
    request: Request, profile_id: str,
    principal: Annotated[Principal, Depends(require_admin)],
) -> dict[str, Any]:
    pool = database_pool(request)
    runtime = getattr(request.app.state, "ai_runtime", None) or RegistryRuntime(
        pool, mode=request.app.state.settings.operating_mode,
        attempt_limit=request.app.state.settings.llm_attempt_budget,
        policy=EndpointPolicy.from_env(),
    )
    result: dict[str, Any] = await request.app.state.execution.run(
        request, lambda: runtime.probe(profile_id), principal_id=principal.id,
        timeout=min(35, request.app.state.settings.query_timeout_seconds),
    )
    async with pool.acquire() as connection, connection.transaction():
        await append_audit(
            connection, principal_id=UUID(principal.id), action="admin.probe_model",
            target_type="model_profile", target_id=profile_id,
            metadata={"health": result.get("health"), "status": result.get("status")},
        )
    return result


def _embedding_context(request: Request) -> tuple[Any, Any, str]:
    pool = database_pool(request)
    runtime = getattr(request.app.state, "ai_runtime", None)
    if runtime is None:
        raise api_error(503, "AI_NOT_CONFIGURED")
    return pool, runtime, request.app.state.settings.operating_mode


def _embedding_error(exc: EmbeddingJobError) -> Exception:
    return api_error(exc.status_code, exc.code, details=exc.details)


@router.get("/embeddings")
async def embedding_status(
    request: Request,
    _principal: Annotated[Principal, Depends(require_admin)],
) -> dict[str, Any]:
    """Active index, all indices with their state, jobs with progress, change detection."""

    pool, runtime, mode = _embedding_context(request)
    return await embedding_overview(
        pool, mode=mode, policy=runtime.policy,
        worker=getattr(request.app.state, "embedding_worker", None),
    )


@router.post("/embeddings/preflight")
async def embedding_preflight(
    request: Request,
    body: EmbeddingPreflightRequest,
    principal: Annotated[Principal, Depends(require_admin)],
) -> dict[str, Any]:
    """Connection, model, test vector, size and policy checks plus the nodes to embed."""

    pool, runtime, mode = _embedding_context(request)
    try:
        result = await asyncio.wait_for(
            preflight(pool, runtime, profile_key=body.profile_id, rebuild=body.rebuild,
                      mode=mode, policy=runtime.policy, batch_size=body.batch_size),
            timeout=90,
        )
    except TimeoutError as exc:
        raise api_error(504, "EMBEDDING_PREFLIGHT_TIMEOUT") from exc
    except EmbeddingJobError as exc:
        raise _embedding_error(exc) from exc
    async with pool.acquire() as connection, connection.transaction():
        await append_audit(
            connection, principal_id=UUID(principal.id), action="admin.embedding_preflight",
            target_type="model_profile", target_id=body.profile_id,
            metadata={"ok": result["ok"], "problems": result["problems"],
                      "dimensions": result.get("dimensions"),
                      "to_embed": result.get("to_embed")},
        )
    return result


@router.post("/embeddings/jobs", status_code=status.HTTP_201_CREATED)
async def embedding_job_create(
    request: Request,
    body: EmbeddingJobRequest,
    principal: Annotated[Principal, Depends(require_admin)],
) -> dict[str, Any]:
    """Queue a rebuild after confirmation; search keeps the active index until the switch."""

    if not body.confirmed:
        raise api_error(422, "EMBEDDING_CONFIRMATION_REQUIRED")
    pool, runtime, mode = _embedding_context(request)
    try:
        job = await asyncio.wait_for(
            create_job(pool, runtime, actor_id=UUID(principal.id), profile_key=body.profile_id,
                       batch_size=body.batch_size, rebuild=body.rebuild, mode=mode,
                       policy=runtime.policy),
            timeout=90,
        )
    except TimeoutError as exc:
        raise api_error(504, "EMBEDDING_PREFLIGHT_TIMEOUT") from exc
    except EmbeddingJobError as exc:
        raise _embedding_error(exc) from exc
    worker = getattr(request.app.state, "embedding_worker", None)
    if worker is not None:
        worker.wake()
    return job


@router.post("/embeddings/jobs/{job_id}/{action}")
async def embedding_job_control(
    request: Request,
    job_id: UUID,
    action: str,
    principal: Annotated[Principal, Depends(require_admin)],
) -> dict[str, Any]:
    """``pause``, ``resume``, ``retry`` or ``cancel`` (keeps every stored vector)."""

    pool, _runtime, _mode = _embedding_context(request)
    try:
        job = await control_job(pool, actor_id=UUID(principal.id), job_id=job_id, action=action)
    except EmbeddingJobError as exc:
        raise _embedding_error(exc) from exc
    worker = getattr(request.app.state, "embedding_worker", None)
    if worker is not None:
        worker.wake()
    return job


@router.get("/audit-events")
async def get_audit_events(
    request: Request,
    _principal: Annotated[Principal, Depends(require_admin_or_auditor)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> dict[str, Any]:
    return await list_audit_events(database_pool(request), limit=limit)


class DocumentOcrEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_number: int = Field(ge=1, le=100_000)
    text: str = Field(max_length=50_000)


class DocumentRevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int = Field(ge=1, le=9_223_372_036_854_775_807)


class DocumentEditRequest(DocumentRevisionRequest):
    title: str | None = Field(default=None, max_length=500)
    doc_type: str | None = Field(default=None, max_length=80)
    document_number: str | None = Field(default=None, max_length=120)
    issuing_body: str | None = Field(default=None, max_length=300)
    publication_date: date | None = None
    effective_from: date | None = None
    official_url: str | None = Field(default=None, max_length=2048)
    ocr_page: DocumentOcrEdit | None = None


class DocumentActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_ids: list[UUID] = Field(min_length=1, max_length=100)
    action: DocumentAction
    reason: str = Field(min_length=1, max_length=2000)
    confirmed: Literal[True]


@router.get("/documents", dependencies=[Depends(no_store)])
async def admin_documents(
    request: Request,
    principal: Annotated[Principal, Depends(require_admin_or_doc_staff)],
    q: Annotated[str, Query(max_length=500)] = "",
    document_number: Annotated[str, Query(max_length=120)] = "",
    title: Annotated[str, Query(max_length=500)] = "",
    doc_type: Annotated[str | None, Query(max_length=80)] = None,
    issuing_body: Annotated[str, Query(max_length=300)] = "",
    date_from: date | None = None,
    date_to: date | None = None,
    review_status: Literal["draft", "pending_review", "approved", "rejected"] | None = None,
    effectivity: AmendmentStatus | None = None,
    availability: Literal["active", "suspended", "deleted"] | None = None,
    page: Annotated[int, Query(ge=1, le=1_000_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict[str, Any]:
    if date_from and date_to and date_from > date_to:
        raise api_error(422, "INVALID_REQUEST")
    return await list_documents(
        database_pool(request), principal, q=q, document_number=document_number,
        title=title, doc_type=doc_type, issuing_body=issuing_body, date_from=date_from,
        date_to=date_to, review_status=review_status, effectivity=effectivity,
        availability=availability, page=page, page_size=page_size, as_of=date.today(),
    )


@router.post("/documents/actions")
async def admin_document_actions(
    request: Request, body: DocumentActionRequest,
    principal: Annotated[Principal, Depends(require_admin)],
) -> dict[str, int]:
    if not body.reason.strip():
        raise api_error(422, "INVALID_REQUEST")
    try:
        updated = await change_availability(
            database_pool(request), actor_id=UUID(principal.id),
            document_ids=body.document_ids, action=body.action, reason=body.reason.strip(),
        )
    except ReviewError as exc:
        raise api_error(exc.status_code, exc.code) from exc
    return {"updated": updated}


@router.get("/documents/{document_id}", dependencies=[Depends(no_store)])
async def admin_document_detail(
    request: Request, document_id: UUID,
    principal: Annotated[Principal, Depends(require_admin_or_doc_staff)],
    version_id: UUID | None = None,
    page_number: Annotated[int, Query(ge=1, le=100_000)] = 1,
    node_page: Annotated[int, Query(ge=1, le=100_000)] = 1,
) -> dict[str, Any]:
    try:
        return await managed_document_detail(
            database_pool(request), principal, document_id, version_id=version_id,
            page_number=page_number, node_page=node_page, as_of=date.today(),
        )
    except ReviewError as exc:
        raise api_error(exc.status_code, exc.code) from exc


_MANAGED_VERSION = "/documents/{document_id}/versions/{version_id}"
_SOURCE_MIME = {
    "pdf": "application/pdf",
    "txt": "text/plain",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@router.get(_MANAGED_VERSION + "/original")
async def admin_document_original(
    request: Request, document_id: UUID, version_id: UUID,
    principal: Annotated[Principal, Depends(require_admin_or_doc_staff)],
    pdf: bool = False,
) -> Response:
    settings = request.app.state.settings
    if not settings.document_store_root:
        raise api_error(503, "DOCUMENT_STORE_NOT_CONFIGURED")
    try:
        content, source_format, filename = await managed_document_original(
            database_pool(request), principal, document_id=document_id, version_id=version_id,
            as_of=date.today(), store_root=Path(settings.document_store_root),
            max_bytes=settings.max_upload_bytes, pdf=pdf,
        )
    except ReviewError as exc:
        raise api_error(exc.status_code, exc.code) from exc
    disposition = "inline" if pdf else "attachment"
    safe_name = quote(filename, safe="")
    return Response(content, media_type=_SOURCE_MIME[source_format], headers={
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        "Content-Disposition": f"{disposition}; filename*=UTF-8''{safe_name}",
    })


@router.patch(_MANAGED_VERSION)
async def admin_edit_document(
    request: Request, document_id: UUID, version_id: UUID, body: DocumentEditRequest,
    principal: Annotated[Principal, Depends(require_curator)],
) -> dict[str, Any]:
    changes = body.model_dump(exclude_unset=True, exclude={"revision", "ocr_page"})
    for key, value in changes.items():
        if isinstance(value, str):
            changes[key] = value.strip() or None
    if any(key in changes and not changes[key] for key in ("title", "doc_type")):
        raise api_error(422, "INVALID_DOCUMENT_METADATA")
    if not changes and body.ocr_page is None:
        raise api_error(422, "INVALID_REQUEST")
    ocr_page = (body.ocr_page.page_number, body.ocr_page.text) if body.ocr_page else None
    if any(isinstance(value, str) and "\x00" in value for value in changes.values()) or (
        ocr_page is not None and "\x00" in ocr_page[1]
    ):
        raise api_error(422, "INVALID_REQUEST")
    try:
        return await change_version(
            database_pool(request), principal, document_id, version_id, revision=body.revision,
            changes=changes, ocr_page=ocr_page, prepared=None, as_of=date.today(),
        )
    except ReviewError as exc:
        raise api_error(exc.status_code, exc.code) from exc
    except ValueError as exc:
        if str(exc) == "INVALID_SOURCE_URL":
            raise api_error(422, "INVALID_SOURCE_URL") from exc
        raise


@router.post(_MANAGED_VERSION + "/reprocess")
async def admin_reprocess_document(
    request: Request, document_id: UUID, version_id: UUID, body: DocumentRevisionRequest,
    principal: Annotated[Principal, Depends(require_curator)],
) -> dict[str, Any]:
    settings = request.app.state.settings
    if not settings.document_store_root:
        raise api_error(503, "DOCUMENT_STORE_NOT_CONFIGURED")
    pool = database_pool(request)
    root = Path(settings.document_store_root)
    as_of = date.today()
    try:
        content, _, _ = await managed_document_original(
            pool, principal, document_id=document_id, version_id=version_id,
            as_of=as_of, store_root=root, max_bytes=settings.max_upload_bytes,
            pdf=True, for_edit=True,
        )
        prepared = await _run_pdf_work(
            request, prepare_draft, content, max_pages=settings.max_preview_pages,
            ocr_engine=configured_ocr_engine(), temporary_root=root, isolate=True,
            timeout_seconds=settings.pdf_timeout_seconds,
        )
        return await change_version(
            pool, principal, document_id, version_id, revision=body.revision,
            changes={}, ocr_page=None, prepared=prepared, as_of=as_of,
        )
    except ReviewError as exc:
        raise api_error(exc.status_code, exc.code) from exc
    except ValueError as exc:
        code = str(exc)
        if code == "PDF_PARSE_TIMEOUT":
            raise api_error(504, code) from exc
        if code in {"PDF_PAGE_LIMIT_EXCEEDED", "PDF_RESOURCE_LIMIT_EXCEEDED"}:
            raise api_error(413, code) from exc
        if code in {"INVALID_PDF_MAGIC", "INVALID_PDF_STRUCTURE", "PDF_PARSE_FAILED"}:
            raise api_error(422, code) from exc
        raise
    except pdfium.PdfiumError as exc:
        raise api_error(422, "PDF_PARSE_FAILED") from exc
