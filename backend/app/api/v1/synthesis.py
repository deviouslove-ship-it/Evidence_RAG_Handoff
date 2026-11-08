"""G4 routes: checked synthesis, content groups, label review, synthesis budget."""

from __future__ import annotations

from typing import Annotated, Any, Literal, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, ConfigDict, Field

from ...audit import append_audit
from ...auth_acl.policy import Permission, Principal
from ...synthesis.service import SynthesisService, load_settings, save_settings
from ...vietnamese_nlp.unicode_norm import fold_text
from .dependencies import get_principal
from .errors import api_error
from .guards import database_pool, require_admin, require_reviewer
from .user import require_user

router = APIRouter(prefix="/api/v1", tags=["synthesis"])


class SynthesisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result_set_id: str = Field(min_length=1, max_length=80)
    restart: bool = False
    # "Phân tích sâu" (Hybrid Auto, API mode only) and "mở rộng phạm vi tổng hợp".
    deep_analysis: bool = False
    expand: bool = False
    # Summarise only the clauses relevant to the question (chat answer, search page).
    only_relevant: bool = False


class LabelDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: UUID
    taxonomy_code: str = Field(min_length=2, max_length=60)


class LabelReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[LabelDecision] = Field(min_length=1, max_length=500)
    decision: Literal["approve", "reject"]


class GroupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(pattern=r"^[a-z0-9_]{2,60}$")
    name: str = Field(min_length=1, max_length=200)
    sort_order: int = Field(default=100, ge=0, le=10_000)


class RuleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phrase: str = Field(min_length=2, max_length=200)
    scope: Literal["text", "heading"] = "text"


class SynthesisSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_evidence_per_batch: int = Field(ge=1, le=50)
    token_budget: int = Field(ge=1000, le=200_000)
    max_batches_per_run: int = Field(ge=1, le=20)
    ai_label_budget: int = Field(ge=0, le=500)


def _service(request: Request) -> SynthesisService:
    service = getattr(request.app.state, "synthesis", None)
    if service is None:
        raise api_error(status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_NOT_CONFIGURED")
    return cast(SynthesisService, service)


@router.post("/synthesis")
async def synthesize(
    request: Request, body: SynthesisRequest,
    principal: Annotated[Principal, Depends(require_user)],
) -> dict[str, Any]:
    search = getattr(request.app.state, "comprehensive_search", None)
    result = search.store.get(body.result_set_id, principal.id) if search else None
    if result is None:
        raise api_error(status.HTTP_410_GONE, "RESULT_SET_EXPIRED")
    return await _service(request).run(
        UUID(principal.id), result, restart=body.restart, deep_analysis=body.deep_analysis,
        expand=body.expand, only_relevant=body.only_relevant,
    )


def _admin_or_doc_staff(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
    if not any(principal.has(item) for item in (Permission.ADMIN, Permission.CURATE,
                                                  Permission.REVIEW)):
        raise api_error(status.HTTP_403_FORBIDDEN, "ADMIN_REQUIRED")
    return principal


@router.get("/admin/content-groups")
async def list_groups(
    request: Request, _principal: Annotated[Principal, Depends(_admin_or_doc_staff)],
) -> list[dict[str, Any]]:
    async with database_pool(request).acquire() as connection:
        rows = await connection.fetch(
            """SELECT t.code, t.name, t.sort_order, t.active,
                      COALESCE(array_agg(r.phrase || ' [' || r.scope || ']' ORDER BY r.phrase)
                               FILTER (WHERE r.id IS NOT NULL), ARRAY[]::text[]) AS rules,
                      (SELECT count(*) FROM node_labels l WHERE l.taxonomy_id = t.id
                         AND l.status <> 'rejected') AS labelled
               FROM content_taxonomy t LEFT JOIN labeling_rules r
                 ON r.taxonomy_id = t.id AND r.active
               GROUP BY t.id ORDER BY t.sort_order"""
        )
    return [{**dict(row), "rules": list(row["rules"]), "labelled": int(row["labelled"])}
            for row in rows]


@router.post("/admin/content-groups", status_code=status.HTTP_201_CREATED)
async def create_group(
    request: Request, body: GroupRequest,
    principal: Annotated[Principal, Depends(require_admin)],
) -> dict[str, Any]:
    async with database_pool(request).acquire() as connection, connection.transaction():
        created = await connection.fetchval(
            """INSERT INTO content_taxonomy (code, name, sort_order, created_by)
               VALUES ($1, $2, $3, $4) ON CONFLICT (code) DO NOTHING RETURNING id""",
            body.code, body.name.strip(), body.sort_order, UUID(principal.id),
        )
        if created is None:
            raise api_error(status.HTTP_409_CONFLICT, "CONTENT_GROUP_EXISTS")
        await append_audit(connection, principal_id=UUID(principal.id),
                           action="content_group.create", target_type="content_taxonomy",
                           target_id=body.code, metadata={"name": body.name})
    return {"code": body.code, "status": "created"}


@router.post("/admin/content-groups/{code}/rules", status_code=status.HTTP_201_CREATED)
async def create_rule(
    request: Request, code: str, body: RuleRequest,
    principal: Annotated[Principal, Depends(require_admin)],
) -> dict[str, Any]:
    async with database_pool(request).acquire() as connection, connection.transaction():
        taxonomy = await connection.fetchval(
            "SELECT id FROM content_taxonomy WHERE code = $1", code
        )
        if taxonomy is None:
            raise api_error(status.HTTP_404_NOT_FOUND, "CONTENT_GROUP_NOT_FOUND")
        await connection.execute(
            """INSERT INTO labeling_rules (taxonomy_id, phrase, phrase_folded, scope, created_by)
               VALUES ($1, $2, $3, $4, $5) ON CONFLICT DO NOTHING""",
            taxonomy, body.phrase.strip(), " ".join(fold_text(body.phrase).split()),
            body.scope, UUID(principal.id),
        )
        await append_audit(connection, principal_id=UUID(principal.id),
                           action="content_group.add_rule", target_type="content_taxonomy",
                           target_id=code, metadata={"phrase": body.phrase, "scope": body.scope})
    return {"code": code, "status": "rule_added"}


@router.get("/admin/labels/proposals")
async def label_proposals(
    request: Request, principal: Annotated[Principal, Depends(require_reviewer)],
) -> list[dict[str, Any]]:
    async with database_pool(request).acquire() as connection:
        rows = await connection.fetch(
            """SELECT l.node_id::text AS node_id, t.code, t.name, l.source, l.model_version,
                      COALESCE(n.citation_label, n.label_original) AS label,
                      left(n.text_original, 400) AS text, d.document_number
               FROM node_labels l
               JOIN content_taxonomy t ON t.id = l.taxonomy_id
               JOIN document_nodes n ON n.id = l.node_id
               JOIN documents d ON d.id = n.document_id
               WHERE l.status = 'proposed' AND EXISTS (
                 SELECT 1 FROM document_categories dc
                 JOIN category_acl ca ON ca.category_id = dc.category_id AND ca.can_review
                 WHERE dc.document_id = n.document_id AND ca.user_id = $1)
               ORDER BY d.document_number, n.path LIMIT 500""",
            UUID(principal.id),
        )
    return [dict(row) for row in rows]


@router.post("/admin/labels/review")
async def review_labels(
    request: Request, body: LabelReviewRequest,
    principal: Annotated[Principal, Depends(require_reviewer)],
) -> dict[str, Any]:
    reviewer = UUID(principal.id)
    batch = uuid4()
    updated = 0
    async with database_pool(request).acquire() as connection, connection.transaction():
        for item in body.items:
            allowed = await connection.fetchval(
                """SELECT EXISTS (SELECT 1 FROM document_nodes n
                     JOIN document_categories dc ON dc.document_id = n.document_id
                     JOIN category_acl ca ON ca.category_id = dc.category_id AND ca.can_review
                     WHERE n.id = $1 AND ca.user_id = $2)""",
                item.node_id, reviewer,
            )
            if not allowed:
                raise api_error(status.HTTP_403_FORBIDDEN, "REVIEW_SCOPE_REQUIRED")
            result = await connection.execute(
                """UPDATE node_labels l SET status = $3, reviewed_by = $4, reviewed_at = now(),
                     review_batch_id = $5
                   FROM content_taxonomy t
                   WHERE l.taxonomy_id = t.id AND l.node_id = $1 AND t.code = $2
                     AND l.status = 'proposed'""",
                item.node_id, item.taxonomy_code,
                "approved" if body.decision == "approve" else "rejected", reviewer, batch,
            )
            if result.endswith(" 1"):
                updated += 1
                await append_audit(connection, principal_id=reviewer, action="label.review",
                                   target_type="node_label", target_id=str(item.node_id),
                                   metadata={"code": item.taxonomy_code,
                                             "decision": body.decision,
                                             "batch_id": str(batch)})
    return {"updated": updated, "batch_id": str(batch)}


@router.get("/admin/synthesis-settings")
async def get_synthesis_settings(
    request: Request, _principal: Annotated[Principal, Depends(require_admin)],
) -> dict[str, int]:
    async with database_pool(request).acquire() as connection:
        return await load_settings(connection)


@router.put("/admin/synthesis-settings")
async def put_synthesis_settings(
    request: Request, body: SynthesisSettingsRequest,
    principal: Annotated[Principal, Depends(require_admin)],
) -> dict[str, int]:
    try:
        return await save_settings(database_pool(request), UUID(principal.id), body.model_dump())
    except ValueError as exc:
        raise api_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "INVALID_REQUEST") from exc
