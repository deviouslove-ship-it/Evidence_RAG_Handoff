"""Local identity service: credential check, lockout, revocable opaque-token sessions."""

from __future__ import annotations

import asyncio
import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from ..audit import append_audit
from .passwords import hash_password, password_policy_error, verify_password

MAX_FAILED_LOGINS = 5
LOCKOUT = timedelta(minutes=15)


class AuthError(Exception):
    def __init__(self, code: str, status_code: int = 401) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class SessionUser:
    user_id: UUID
    username: str
    display_name: str
    roles: frozenset[str]
    must_change_password: bool
    token_hash: str
    expires_at: datetime


@dataclass(frozen=True)
class LoginResult:
    token: str
    user: SessionUser


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def login(
    pool: Any, *, username: str, password: str, ttl_seconds: int, client_kind: str = "web"
) -> LoginResult:
    name = username.strip()
    now = datetime.now(UTC)
    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            """SELECT id, username, display_name, password_hash, must_change_password,
                      locked_until, disabled_at
               FROM users WHERE lower(username) = lower($1)""",
            name,
        )
    # Always verify (against a dummy hash for unknown users) to keep timing uniform;
    # scrypt is CPU-bound, so keep it off the event loop.
    valid = await asyncio.to_thread(
        verify_password, password, row["password_hash"] if row else None
    )
    if row is None:
        raise AuthError("INVALID_CREDENTIALS")
    if row["disabled_at"] is not None:
        raise AuthError("ACCOUNT_DISABLED", 403)
    if row["locked_until"] is not None and row["locked_until"] > now:
        raise AuthError("ACCOUNT_LOCKED", 429)
    if not valid:
        await _record_failure(pool, name)
        raise AuthError("INVALID_CREDENTIALS")
    token = secrets.token_urlsafe(32)
    async with pool.acquire() as connection, connection.transaction():
        current = await connection.fetchrow(
            "SELECT password_hash, disabled_at, locked_until, must_change_password "
            "FROM users WHERE id = $1 FOR UPDATE", row["id"],
        )
        now = datetime.now(UTC)
        if current is None or current["password_hash"] != row["password_hash"]:
            raise AuthError("INVALID_CREDENTIALS")
        if current["disabled_at"] is not None:
            raise AuthError("ACCOUNT_DISABLED", 403)
        if current["locked_until"] is not None and current["locked_until"] > now:
            raise AuthError("ACCOUNT_LOCKED", 429)
        expires_at = now + timedelta(seconds=ttl_seconds)
        await connection.execute(
            "DELETE FROM auth_sessions WHERE user_id = $1 "
            "AND (expires_at <= now() OR revoked_at IS NOT NULL)", row["id"],
        )
        await connection.execute(
            """UPDATE users SET failed_login_count = 0, locked_until = NULL,
                                last_login_at = $2 WHERE id = $1""",
            row["id"], now,
        )
        await connection.execute(
            """INSERT INTO auth_sessions (user_id, token_hash, expires_at, client_kind)
               VALUES ($1, $2, $3, $4)""",
            row["id"], token_digest(token), expires_at, client_kind,
        )
        roles = await _roles(connection, row["id"])
        await append_audit(
            connection, principal_id=row["id"], action="auth.login",
            target_type="user", target_id=str(row["id"]), metadata={"client": client_kind},
        )
    return LoginResult(
        token=token,
        user=SessionUser(
            user_id=row["id"], username=row["username"], display_name=row["display_name"],
            roles=roles, must_change_password=current["must_change_password"],
            token_hash=token_digest(token), expires_at=expires_at,
        ),
    )


async def _record_failure(pool: Any, username: str) -> None:
    now = datetime.now(UTC)
    async with pool.acquire() as connection, connection.transaction():
        row = await connection.fetchrow(
            """SELECT id, failed_login_count, locked_until FROM users
               WHERE lower(username) = lower($1) FOR UPDATE""",
            username,
        )
        if row is None:
            return
        failures = row["failed_login_count"] + 1
        locked_until = now + LOCKOUT if failures >= MAX_FAILED_LOGINS else None
        await connection.execute(
            "UPDATE users SET failed_login_count = $2, locked_until = $3 WHERE id = $1",
            row["id"], 0 if locked_until else failures, locked_until,
        )
        await append_audit(
            connection, principal_id=row["id"], action="auth.login_failed",
            target_type="user", target_id=str(row["id"]),
            metadata={"locked": locked_until is not None},
        )


async def _roles(connection: Any, user_id: UUID) -> frozenset[str]:
    rows = await connection.fetch("SELECT role_code FROM user_roles WHERE user_id = $1", user_id)
    return frozenset(row["role_code"] for row in rows)


async def resolve_token(pool: Any, token: str) -> SessionUser | None:
    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            """SELECT u.id, u.username, u.display_name, u.must_change_password,
                      s.token_hash, s.expires_at
               FROM auth_sessions s JOIN users u ON u.id = s.user_id
               WHERE s.token_hash = $1 AND s.revoked_at IS NULL
                 AND s.expires_at > now() AND u.disabled_at IS NULL""",
            token_digest(token),
        )
        if row is None:
            return None
        roles = await _roles(connection, row["id"])
    return SessionUser(
        user_id=row["id"], username=row["username"], display_name=row["display_name"],
        roles=roles, must_change_password=row["must_change_password"],
        token_hash=row["token_hash"], expires_at=row["expires_at"],
    )


async def logout(pool: Any, *, user: SessionUser) -> None:
    async with pool.acquire() as connection, connection.transaction():
        await connection.execute(
            "UPDATE auth_sessions SET revoked_at = now() WHERE token_hash = $1 "
            "AND revoked_at IS NULL",
            user.token_hash,
        )
        await append_audit(
            connection, principal_id=user.user_id, action="auth.logout",
            target_type="user", target_id=str(user.user_id),
        )


async def change_password(
    pool: Any, *, user: SessionUser, current_password: str, new_password: str
) -> None:
    problem = password_policy_error(new_password, user.username)
    if problem:
        raise AuthError(problem, 422)
    async with pool.acquire() as connection, connection.transaction():
        row = await connection.fetchrow(
            "SELECT password_hash FROM users WHERE id = $1 FOR UPDATE", user.user_id
        )
        if row is None or not await asyncio.to_thread(
            verify_password, current_password, row["password_hash"]
        ):
            raise AuthError("INVALID_CREDENTIALS", 403)
        if await asyncio.to_thread(verify_password, new_password, row["password_hash"]):
            raise AuthError("PASSWORD_UNCHANGED", 422)
        new_hash = await asyncio.to_thread(hash_password, new_password)
        await connection.execute(
            """UPDATE users SET password_hash = $2, must_change_password = FALSE,
                                password_changed_at = now() WHERE id = $1""",
            user.user_id, new_hash,
        )
        await connection.execute(
            "UPDATE auth_sessions SET revoked_at = now() WHERE user_id = $1 "
            "AND token_hash <> $2 AND revoked_at IS NULL",
            user.user_id, user.token_hash,
        )
        await append_audit(
            connection, principal_id=user.user_id, action="auth.password_changed",
            target_type="user", target_id=str(user.user_id),
        )
