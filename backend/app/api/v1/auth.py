"""Authentication dependency and the login/logout/password routes.

Development headers are intentionally limited to the explicit in-memory POC.
Production uses the local identity service backed by PostgreSQL; the API
contract is bearer based with opaque, revocable tokens.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from ...auth_acl import service
from ...auth_acl.policy import Principal, normalize_roles, permission_for_role
from ...config import Settings
from .capacity import operation_slot
from .errors import api_error

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# Routes a user may call while a password change is still pending.
_PASSWORD_PENDING_ALLOWED = frozenset(
    {"/api/v1/auth/password", "/api/v1/auth/logout", "/api/v1/auth/me"}
)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=256)
    client: Literal["web", "desktop"] = "web"


class PasswordChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class UserInfo(BaseModel):
    id: UUID
    username: str
    display_name: str
    roles: list[str]
    permissions: list[str]
    must_change_password: bool


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: str
    user: UserInfo


def _user_info(user: service.SessionUser) -> UserInfo:
    permissions = sorted(
        {permission.value for role in user.roles for permission in permission_for_role(role)}
    )
    return UserInfo(
        id=user.user_id, username=user.username, display_name=user.display_name,
        roles=sorted(user.roles), permissions=permissions,
        must_change_password=user.must_change_password,
    )


def _pool(request: Request) -> Any:
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise api_error(status.HTTP_503_SERVICE_UNAVAILABLE, "AUTH_PROVIDER_NOT_CONFIGURED")
    return pool


async def get_session_user(
    request: Request, authorization: Annotated[str | None, Header()] = None
) -> service.SessionUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise api_error(status.HTTP_401_UNAUTHORIZED, "AUTH_REQUIRED")
    user = await service.resolve_token(_pool(request), authorization[7:].strip())
    if user is None:
        raise api_error(status.HTTP_401_UNAUTHORIZED, "AUTH_REQUIRED")
    return user


async def get_principal(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_principal_id: Annotated[str | None, Header()] = None,
    x_roles: Annotated[str | None, Header()] = None,
) -> Principal:
    settings: Settings = request.app.state.settings
    if settings.dev_allow_in_memory_store:
        if not x_principal_id:
            raise api_error(status.HTTP_401_UNAUTHORIZED, "AUTH_REQUIRED")
        try:
            principal_id = UUID(x_principal_id)
        except (TypeError, ValueError) as exc:
            raise api_error(status.HTTP_401_UNAUTHORIZED, "INVALID_PRINCIPAL") from exc
        return Principal(
            id=str(principal_id),
            roles=normalize_roles((x_roles or "").split(",")),
        )
    user = await get_session_user(request, authorization)
    if user.must_change_password and request.url.path not in _PASSWORD_PENDING_ALLOWED:
        raise api_error(status.HTTP_403_FORBIDDEN, "PASSWORD_CHANGE_REQUIRED")
    return Principal(id=str(user.user_id), roles=normalize_roles(user.roles))


def _auth_failure(exc: service.AuthError) -> Exception:
    return api_error(exc.status_code, exc.code)


@router.post("/login", response_model=LoginResponse)
async def login(request: Request, body: LoginRequest) -> LoginResponse:
    if request.app.state.settings.dev_allow_in_memory_store:
        raise api_error(status.HTTP_503_SERVICE_UNAVAILABLE, "AUTH_PROVIDER_NOT_CONFIGURED")
    async with operation_slot(request.app.state.auth_slots, "AUTH_BUSY"):
        try:
            result = await service.login(
                _pool(request), username=body.username, password=body.password,
                ttl_seconds=request.app.state.settings.auth_ttl_seconds, client_kind=body.client,
            )
        except service.AuthError as exc:
            raise _auth_failure(exc) from exc
    return LoginResponse(
        access_token=result.token, expires_at=result.user.expires_at.isoformat(),
        user=_user_info(result.user),
    )


@router.get("/me", response_model=UserInfo)
async def me(user: Annotated[service.SessionUser, Depends(get_session_user)]) -> UserInfo:
    return _user_info(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request, user: Annotated[service.SessionUser, Depends(get_session_user)]
) -> Response:
    await service.logout(_pool(request), user=user)
    principal_id = str(user.user_id)
    request.app.state.execution.cancel_principal(principal_id)
    memory = getattr(request.app.state, "memory", None)
    if memory is not None:
        memory.delete_principal(principal_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    request: Request,
    body: PasswordChangeRequest,
    user: Annotated[service.SessionUser, Depends(get_session_user)],
) -> Response:
    async with operation_slot(request.app.state.auth_slots, "AUTH_BUSY"):
        try:
            await service.change_password(
                _pool(request), user=user,
                current_password=body.current_password, new_password=body.new_password,
            )
        except service.AuthError as exc:
            raise _auth_failure(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
