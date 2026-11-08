"""Role guards shared by the Admin Portal routers and database access helper."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Request, status

from ...auth_acl.policy import Permission, Principal, require_permission
from .dependencies import get_principal
from .errors import api_error


def _guard(permission: Permission, code: str) -> Any:
    def dependency(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
        try:
            require_permission(principal, permission)
        except PermissionError as exc:
            raise api_error(status.HTTP_403_FORBIDDEN, code) from exc
        return principal

    return dependency


require_admin = _guard(Permission.ADMIN, "ADMIN_REQUIRED")
require_curator = _guard(Permission.CURATE, "CURATOR_REQUIRED")
require_reviewer = _guard(Permission.REVIEW, "REVIEWER_REQUIRED")
require_auditor = _guard(Permission.AUDIT, "AUDITOR_REQUIRED")


def require_document_reviewer(
    principal: Annotated[Principal, Depends(get_principal)],
) -> Principal:
    if not principal.has(Permission.CURATE) and not principal.has(Permission.REVIEW):
        raise api_error(status.HTTP_403_FORBIDDEN, "CURATOR_OR_REVIEWER_REQUIRED")
    return principal


def database_pool(request: Request) -> Any:
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise api_error(status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_NOT_CONFIGURED")
    return pool
