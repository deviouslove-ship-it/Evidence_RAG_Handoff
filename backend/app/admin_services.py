"""Admin Portal persistence services for categories, users, ACL, model registry and audit."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable
from typing import Any
from uuid import UUID

import asyncpg

from .audit import append_audit, verify_audit_chain
from .auth_acl.passwords import hash_password, password_policy_error
from .auth_acl.policy import normalize_roles
from .model_registry.profiles import ModelProfile, OperatingMode, PrivacyZone
from .model_registry.runtime import EndpointPolicy, RegistryRuntimeError, validate_profile
from .model_registry.stages import ACTIVE_STAGES, ESCALATION_STAGES, STAGES, StagePolicy

_VALID_ROLES = frozenset({"USER", "CURATOR", "REVIEWER", "SYS_ADMIN", "AUDITOR"})
_SECRET_REF = re.compile(
    r"^(?:env:[A-Za-z_][A-Za-z0-9_]{0,127}|secret:[A-Za-z0-9][A-Za-z0-9_.-]{0,99})$")


class AdminServiceError(Exception):
    def __init__(self, code: str, status_code: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


async def list_authorized_categories(pool: Any, *, principal_id: UUID) -> list[dict[str, Any]]:
    async with pool.acquire() as connection, connection.transaction():
        await connection.execute("SELECT set_config('app.user_id', $1, true)", str(principal_id))
        rows = await connection.fetch(
            """SELECT c.id, c.code, c.name, c.remote_processing_allowed
               FROM categories c
               JOIN authorized_categories ac ON ac.category_id = c.id
               WHERE c.deleted_at IS NULL
               ORDER BY c.name ASC, c.code ASC"""
        )
    return [
        {
            "id": str(row["id"]),
            "code": row["code"],
            "name": row["name"],
            "remote_processing_allowed": bool(row["remote_processing_allowed"]),
        }
        for row in rows
    ]


async def list_all_categories(pool: Any) -> list[dict[str, Any]]:
    async with pool.acquire() as connection:
        rows = await connection.fetch(
            """SELECT c.id, c.code, c.name, c.remote_processing_allowed, c.created_at,
                      (SELECT count(*) FROM document_categories dc WHERE dc.category_id = c.id)
                        AS document_count
               FROM categories c
               WHERE c.deleted_at IS NULL
               ORDER BY c.name ASC, c.code ASC"""
        )
    return [
        {
            "id": str(row["id"]),
            "code": row["code"],
            "name": row["name"],
            "remote_processing_allowed": bool(row["remote_processing_allowed"]),
            "document_count": int(row["document_count"] or 0),
            "created_at": row["created_at"].isoformat(),
        }
        for row in rows
    ]


async def create_category(
    pool: Any,
    *,
    actor_id: UUID,
    code: str,
    name: str,
    remote_processing_allowed: bool = False,
) -> dict[str, Any]:
    clean_code = code.strip().upper()
    clean_name = name.strip()
    if not clean_code or not clean_name:
        raise AdminServiceError("INVALID_REQUEST", 422)
    try:
        async with pool.acquire() as connection, connection.transaction():
            row = await connection.fetchrow(
                """INSERT INTO categories (code, name, remote_processing_allowed, deleted_at)
                   VALUES ($1, $2, $3, NULL)
                   RETURNING id, code, name, remote_processing_allowed, created_at""",
                clean_code,
                clean_name,
                remote_processing_allowed,
            )
            doc_count = await connection.fetchval(
                "SELECT count(*) FROM document_categories WHERE category_id = $1",
                row["id"],
            )
            await append_audit(
                connection,
                principal_id=actor_id,
                action="admin.create_category",
                target_type="category",
                target_id=str(row["id"]),
                metadata={"code": clean_code, "remote": remote_processing_allowed},
            )
    except asyncpg.UniqueViolationError as exc:
        raise AdminServiceError("DUPLICATE_RESOURCE", 409) from exc
    return {
        "id": str(row["id"]),
        "code": row["code"],
        "name": row["name"],
        "remote_processing_allowed": bool(row["remote_processing_allowed"]),
        "document_count": int(doc_count or 0),
        "created_at": row["created_at"].isoformat(),
    }


async def delete_category(
    pool: Any,
    *,
    actor_id: UUID,
    category_id: UUID,
) -> dict[str, Any]:
    async with pool.acquire() as connection, connection.transaction():
        row = await connection.fetchrow(
            """UPDATE categories
               SET deleted_at = now()
               WHERE id = $1 AND deleted_at IS NULL
               RETURNING id, code, name""",
            category_id,
        )
        if row is None:
            raise AdminServiceError("CATEGORY_NOT_FOUND", 404)
        await connection.execute(
            "DELETE FROM category_acl WHERE category_id = $1",
            category_id,
        )
        await append_audit(
            connection,
            principal_id=actor_id,
            action="admin.delete_category",
            target_type="category",
            target_id=str(row["id"]),
            metadata={"code": row["code"], "name": row["name"]},
        )
    return {"id": str(row["id"]), "code": row["code"], "status": "deleted"}


async def update_category(
    pool: Any, *, actor_id: UUID, category_id: UUID, code: str, name: str,
    remote_processing_allowed: bool,
) -> dict[str, Any]:
    if not code.strip() or not name.strip():
        raise AdminServiceError("INVALID_REQUEST", 422)
    try:
        async with pool.acquire() as connection, connection.transaction():
            row = await connection.fetchrow(
                """UPDATE categories SET code=$2, name=$3, remote_processing_allowed=$4
                   WHERE id=$1 AND deleted_at IS NULL RETURNING id, code, name,
                   remote_processing_allowed""",
                category_id, code.strip().upper(), name.strip(), remote_processing_allowed,
            )
            if row is None:
                raise AdminServiceError("CATEGORY_NOT_FOUND", 404)
            await append_audit(
                connection, principal_id=actor_id, action="admin.update_category",
                target_type="category", target_id=str(category_id),
                metadata={"code": row["code"], "remote": remote_processing_allowed},
            )
    except asyncpg.UniqueViolationError as exc:
        raise AdminServiceError("DUPLICATE_RESOURCE", 409) from exc
    return {**dict(row), "id": str(row["id"])}


async def list_users(pool: Any) -> list[dict[str, Any]]:
    async with pool.acquire() as connection:
        rows = await connection.fetch(
            """SELECT u.id, u.username, u.display_name, u.must_change_password,
                      u.disabled_at, u.last_login_at, u.created_at, u.remote_ai_allowed,
                      COALESCE(
                        ARRAY(
                          SELECT ur.role_code FROM user_roles ur
                          WHERE ur.user_id = u.id ORDER BY ur.role_code
                        ),
                        ARRAY[]::text[]
                      ) AS roles,
                      COALESCE(
                        ARRAY(
                          SELECT ca.category_id::text FROM category_acl ca
                          WHERE ca.user_id = u.id AND ca.can_query
                        ),
                        ARRAY[]::text[]
                      ) AS category_ids,
                      COALESCE(
                        ARRAY(
                          SELECT ca.category_id::text FROM category_acl ca
                          WHERE ca.user_id = u.id AND ca.can_review
                        ),
                        ARRAY[]::text[]
                      ) AS review_category_ids
               FROM users u
               ORDER BY u.username ASC"""
        )
    return [
        {
            "id": str(row["id"]),
            "username": row["username"],
            "display_name": row["display_name"],
            "roles": list(row["roles"] or []),
            "category_ids": list(row["category_ids"] or []),
            "review_category_ids": list(row["review_category_ids"] or []),
            "must_change_password": bool(row["must_change_password"]),
            "disabled": row["disabled_at"] is not None,
            "remote_ai_allowed": bool(row["remote_ai_allowed"]),
            "last_login_at": row["last_login_at"].isoformat() if row["last_login_at"] else None,
            "created_at": row["created_at"].isoformat(),
        }
        for row in rows
    ]


async def create_or_update_user(
    pool: Any,
    *,
    actor_id: UUID,
    username: str,
    display_name: str,
    password: str | None,
    roles: list[str],
    category_ids: list[UUID],
    must_change_password: bool = True,
    disabled: bool = False,
    remote_ai_allowed: bool = False,
    review_category_ids: list[UUID] | None = None,
) -> dict[str, Any]:
    clean_user = username.strip()
    review_ids = set(review_category_ids or [])
    # Effectivity review scope (D10) only means something for REVIEWER accounts.
    if review_ids and "REVIEWER" not in normalize_roles(roles):
        raise AdminServiceError("INVALID_REQUEST", 422)
    clean_display = display_name.strip()
    norm_roles = sorted(normalize_roles(roles))
    if not clean_user or not clean_display or not norm_roles:
        raise AdminServiceError("INVALID_REQUEST", 422)
    if not set(norm_roles).issubset(_VALID_ROLES):
        raise AdminServiceError("INVALID_REQUEST", 422)
    if password is not None:
        err = password_policy_error(password, clean_user)
        if err:
            raise AdminServiceError(err, 422)
    pw_hash = await asyncio.to_thread(hash_password, password) if password is not None else None
    async with pool.acquire() as connection, connection.transaction():
        for role_code in norm_roles:
            await connection.execute(
                "INSERT INTO roles (code, name) VALUES ($1, $1) ON CONFLICT DO NOTHING",
                role_code,
            )
        existing = await connection.fetchrow(
            "SELECT id FROM users WHERE lower(username) = lower($1) FOR UPDATE", clean_user
        )
        if existing is None:
            if pw_hash is None:
                raise AdminServiceError("PASSWORD_TOO_SHORT", 422)
            row = await connection.fetchrow(
                """INSERT INTO users
                   (username, display_name, password_hash, must_change_password, disabled_at,
                    remote_ai_allowed)
                   VALUES ($1, $2, $3, $4, CASE WHEN $5 THEN now() ELSE NULL END, $6)
                   RETURNING id, username, display_name, must_change_password,
                             disabled_at, last_login_at, created_at, remote_ai_allowed""",
                clean_user,
                clean_display,
                pw_hash,
                must_change_password,
                disabled,
                remote_ai_allowed,
            )
            user_id = row["id"]
            action = "admin.create_user"
        else:
            user_id = existing["id"]
            row = await connection.fetchrow(
                """UPDATE users
                   SET display_name = $2,
                       password_hash = COALESCE($3, password_hash),
                       must_change_password = $4,
                       disabled_at = CASE WHEN $5 THEN COALESCE(disabled_at, now()) ELSE NULL END,
                       failed_login_count = 0,
                       locked_until = NULL,
                       remote_ai_allowed = $6
                   WHERE id = $1
                   RETURNING id, username, display_name, must_change_password,
                             disabled_at, last_login_at, created_at, remote_ai_allowed""",
                user_id,
                clean_display,
                pw_hash,
                must_change_password,
                disabled,
                remote_ai_allowed,
            )
            if disabled or pw_hash is not None:
                await connection.execute(
                    "UPDATE auth_sessions SET revoked_at = now() "
                    "WHERE user_id = $1 AND revoked_at IS NULL",
                    user_id,
                )
            action = "admin.update_user"

        await connection.execute("DELETE FROM user_roles WHERE user_id = $1", user_id)
        for role_code in norm_roles:
            await connection.execute(
                "INSERT INTO user_roles (user_id, role_code) VALUES ($1, $2)",
                user_id,
                role_code,
            )

        actor_exists = await connection.fetchval(
            "SELECT 1 FROM users WHERE id = $1", actor_id
        )
        granted_by = actor_id if actor_exists else None
        await connection.execute("DELETE FROM category_acl WHERE user_id = $1", user_id)
        query_ids = set(category_ids)
        for cat_id in query_ids | review_ids:
            await connection.execute(
                """INSERT INTO category_acl
                     (category_id, user_id, can_query, can_review, granted_by)
                   VALUES ($1, $2, $3, $4, $5)""",
                cat_id,
                user_id,
                cat_id in query_ids,
                cat_id in review_ids,
                granted_by,
            )

        await append_audit(
            connection,
            principal_id=actor_id,
            action=action,
            target_type="user",
            target_id=str(user_id),
            metadata={
                "username": clean_user,
                "roles": norm_roles,
                "category_ids": [str(c) for c in set(category_ids)],
                "review_category_ids": [str(c) for c in review_ids],
                "disabled": disabled,
                "remote_ai_allowed": remote_ai_allowed,
            },
        )
    return {
        "id": str(row["id"]),
        "username": row["username"],
        "display_name": row["display_name"],
        "roles": norm_roles,
        "category_ids": [str(c) for c in set(category_ids)],
        "review_category_ids": [str(c) for c in review_ids],
        "must_change_password": bool(row["must_change_password"]),
        "disabled": row["disabled_at"] is not None,
        "remote_ai_allowed": bool(row["remote_ai_allowed"]),
        "last_login_at": row["last_login_at"].isoformat() if row["last_login_at"] else None,
        "created_at": row["created_at"].isoformat(),
    }


async def delete_user(
    pool: Any,
    *,
    actor_id: UUID,
    user_id: UUID,
) -> dict[str, Any]:
    """Disable access while retaining reviewer identity and audit references."""
    if user_id == actor_id:
        raise AdminServiceError("CANNOT_DELETE_SELF", 409)
    async with pool.acquire() as connection, connection.transaction():
        existing = await connection.fetchrow(
            "UPDATE users SET disabled_at = COALESCE(disabled_at, now()) "
            "WHERE id = $1 RETURNING id, username, display_name", user_id,
        )
        if existing is None:
            raise AdminServiceError("USER_NOT_FOUND", 404)
        await connection.execute(
            "UPDATE auth_sessions SET revoked_at = now() "
            "WHERE user_id = $1 AND revoked_at IS NULL", user_id,
        )
        await append_audit(
            connection, principal_id=actor_id, action="admin.disable_user",
            target_type="user", target_id=str(user_id),
            metadata={"username": existing["username"]},
        )
    return {"id": str(user_id), "username": existing["username"], "status": "disabled"}


async def list_model_registry(pool: Any) -> dict[str, Any]:
    async with pool.acquire() as connection:
        profiles = await connection.fetch(
            """SELECT mp.id, mp.profile_key, p.adapter, p.endpoint, p.approved,
                      mp.model_id, mp.revision, mp.capabilities, mp.privacy_zone,
                      mp.secret_ref, mp.fallback, mp.health, mp.params, mp.created_at,
                      mp.input_price_per_mtok, mp.output_price_per_mtok,
                      mp.daily_cost_limit, mp.monthly_cost_limit
               FROM model_profiles mp
               JOIN providers p ON p.id = mp.provider_id
               ORDER BY mp.profile_key ASC"""
        )
        routes = await connection.fetch(
            """SELECT sr.mode, sr.stage, mp.profile_key, sr.fallback,
                      ep.profile_key AS escalation_profile_id
               FROM stage_routes sr
               JOIN model_profiles mp ON mp.id = sr.profile_id
               LEFT JOIN model_profiles ep ON ep.id = sr.escalation_profile_id
               ORDER BY sr.mode ASC, sr.stage ASC"""
        )
        policies = await connection.fetch(
            """SELECT mode, stage, max_attempts, max_output_tokens, timeout_seconds,
                      max_concurrency, updated_at
               FROM stage_policies ORDER BY mode ASC, stage ASC"""
        )
        usage = await connection.fetch(
            """SELECT profile_key,
                      COUNT(*) FILTER (WHERE occurred_at >= date_trunc('day', now()))
                        AS calls_today,
                      COUNT(*) AS calls_month,
                      COALESCE(SUM(estimated_cost) FILTER (
                        WHERE occurred_at >= date_trunc('day', now())), 0) AS cost_today,
                      COALESCE(SUM(estimated_cost), 0) AS cost_month,
                      COUNT(*) FILTER (WHERE escalated) AS escalations_month
               FROM ai_usage_events
               WHERE occurred_at >= date_trunc('month', now())
               GROUP BY profile_key ORDER BY profile_key"""
        )
    return {
        "profiles": [
            {
                "id": str(row["id"]),
                "profile_id": row["profile_key"],
                "adapter": row["adapter"],
                "endpoint": row["endpoint"],
                "provider_approved": bool(row["approved"]),
                "model_id": row["model_id"],
                "revision": row["revision"],
                "capabilities": json.loads(row["capabilities"])
                if isinstance(row["capabilities"], str)
                else list(row["capabilities"]),
                "privacy_zone": row["privacy_zone"],
                "secret_ref": (
                    row["secret_ref"]
                    if row["secret_ref"] and _SECRET_REF.fullmatch(row["secret_ref"]) else None
                ),
                "fallback": json.loads(row["fallback"])
                if isinstance(row["fallback"], str)
                else list(row["fallback"]),
                "health": row["health"],
                "params": _json_object(row["params"]),
                "input_price_per_mtok": _number(row["input_price_per_mtok"]),
                "output_price_per_mtok": _number(row["output_price_per_mtok"]),
                "daily_cost_limit": _number(row["daily_cost_limit"]),
                "monthly_cost_limit": _number(row["monthly_cost_limit"]),
            }
            for row in profiles
        ],
        "routes": [
            {
                "mode": row["mode"],
                "stage": row["stage"],
                "profile_id": row["profile_key"],
                "fallback": json.loads(row["fallback"])
                if isinstance(row["fallback"], str)
                else list(row["fallback"]),
                "escalation_profile_id": row["escalation_profile_id"],
            }
            for row in routes
        ],
        "stage_policies": [
            {
                "mode": row["mode"],
                "stage": row["stage"],
                "max_attempts": row["max_attempts"],
                "max_output_tokens": row["max_output_tokens"],
                "timeout_seconds": _number(row["timeout_seconds"]),
                "max_concurrency": row["max_concurrency"],
                "updated_at": row["updated_at"].isoformat(),
            }
            for row in policies
        ],
        "usage": [
            {
                "profile_id": row["profile_key"],
                "calls_today": row["calls_today"],
                "calls_month": row["calls_month"],
                "cost_today": _number(row["cost_today"]) or 0.0,
                "cost_month": _number(row["cost_month"]) or 0.0,
                "escalations_month": row["escalations_month"],
            }
            for row in usage
        ],
        "stages": [
            {
                "stage": stage,
                "active": stage in ACTIVE_STAGES,
                "escalation_allowed": stage in ESCALATION_STAGES,
            }
            for stage in STAGES
        ],
    }


def valid_roles(roles: frozenset[str]) -> bool:
    """A profile serves one or more text stages, or embedding alone (one vector index per
    model)."""

    return bool(roles) and roles <= frozenset(STAGES) and (
        "embedding" not in roles or len(roles) == 1)


async def upsert_model_profile(
    pool: Any,
    *,
    actor_id: UUID,
    profile_id: str,
    adapter: str,
    endpoint: str,
    model_id: str,
    capabilities: list[str],
    privacy_zone: str,
    revision: str,
    secret_ref: str | None,
    fallback: list[str],
    provider_approved: bool = False,
    params: dict[str, Any] | None = None,
    costs: dict[str, float | None] | None = None,
    secret_writer: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """``secret_writer`` stores a typed API key; it runs inside the transaction after every
    check passed, so a refused profile never replaces a stored key."""

    costs = costs or {}
    if privacy_zone not in {"public", "internal", "restricted"}:
        raise AdminServiceError("INVALID_REQUEST", 422)
    proposed = ModelProfile(
        profile_id=profile_id.strip(), adapter=adapter.strip(), endpoint=endpoint.strip(),
        model_id=model_id.strip(), capabilities=frozenset(capabilities),
        privacy_zone=PrivacyZone(privacy_zone), revision=revision.strip(),
        secret_ref=secret_ref, fallback=tuple(fallback), provider_approved=provider_approved,
    )
    try:
        roles = proposed.capabilities
        if not valid_roles(roles):
            raise AdminServiceError("MODEL_STAGE_UNSUPPORTED", 422)
        stage = sorted(roles)[0]
        validate_profile(proposed, stage=stage)
        if proposed.privacy_zone != PrivacyZone.PUBLIC:
            validate_profile(proposed, OperatingMode.LOCAL, EndpointPolicy.from_env(), stage)
    except RegistryRuntimeError as exc:
        raise AdminServiceError(str(exc), 422) from exc
    async with pool.acquire() as connection, connection.transaction():
        await connection.execute("LOCK TABLE model_profiles IN SHARE ROW EXCLUSIVE MODE")
        rows = await connection.fetch(
            "SELECT profile_key, privacy_zone, fallback FROM model_profiles"
        )
        profiles = {row["profile_key"]: dict(row) for row in rows}
        profiles[proposed.profile_id] = {
            "privacy_zone": privacy_zone, "fallback": list(fallback),
        }
        _validate_fallbacks(proposed.profile_id, profiles)
        routes = await connection.fetch(
            """SELECT sr.mode, mp.profile_key, sr.fallback FROM stage_routes sr
               JOIN model_profiles mp ON mp.id = sr.profile_id"""
        )
        if privacy_zone == "public" and any(
            row["mode"] == "LOCAL" and (
                row["profile_key"] == proposed.profile_id
                or proposed.profile_id in _json_list(row["fallback"])
            ) for row in routes
        ):
            raise AdminServiceError("REMOTE_AI_DENIED", 409)
        if privacy_zone != "public" and await connection.fetchval(
            """SELECT EXISTS (SELECT 1 FROM stage_routes sr
                              JOIN model_profiles ep ON ep.id = sr.escalation_profile_id
                              WHERE ep.profile_key = $1)""",
            proposed.profile_id,
        ):
            # An escalation profile is, by definition, the external API model.
            raise AdminServiceError("MODEL_ESCALATION_NOT_PUBLIC", 409)
        # Re-saving a profile updates its own provider row; a fresh row is created only
        # for a new profile or when the old provider is shared with another profile.
        provider_id = await connection.fetchval(
            """SELECT mp.provider_id FROM model_profiles mp
               WHERE mp.profile_key = $1
                 AND NOT EXISTS (
                     SELECT 1 FROM model_profiles other
                     WHERE other.provider_id = mp.provider_id AND other.profile_key <> $1
                 )""",
            profile_id.strip(),
        )
        if provider_id is not None:
            await connection.execute(
                """UPDATE providers SET adapter = $2, endpoint = $3, approved = $4,
                          approved_by = CASE WHEN $4 THEN $5::uuid ELSE NULL END,
                          approved_at = CASE WHEN $4 THEN now() ELSE NULL END
                   WHERE id = $1""",
                provider_id,
                adapter.strip(),
                endpoint.strip(),
                provider_approved,
                actor_id if provider_approved else None,
            )
        else:
            provider_id = await connection.fetchval(
                """INSERT INTO providers (adapter, endpoint, approved, approved_by, approved_at)
                   VALUES ($1, $2, $3, $4, CASE WHEN $3 THEN now() ELSE NULL END)
                   RETURNING id""",
                adapter.strip(),
                endpoint.strip(),
                provider_approved,
                actor_id if provider_approved else None,
            )
        row = await connection.fetchrow(
            """INSERT INTO model_profiles
               (profile_key, provider_id, model_id, revision, capabilities,
                privacy_zone, secret_ref, fallback, params, input_price_per_mtok,
                output_price_per_mtok, daily_cost_limit, monthly_cost_limit)
               VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8::jsonb, $9::jsonb,
                       $10, $11, $12, $13)
               ON CONFLICT (profile_key) DO UPDATE SET
                 input_price_per_mtok = EXCLUDED.input_price_per_mtok,
                 output_price_per_mtok = EXCLUDED.output_price_per_mtok,
                 daily_cost_limit = EXCLUDED.daily_cost_limit,
                 monthly_cost_limit = EXCLUDED.monthly_cost_limit,
                 provider_id = EXCLUDED.provider_id,
                 model_id = EXCLUDED.model_id,
                 revision = EXCLUDED.revision,
                 capabilities = EXCLUDED.capabilities,
                 privacy_zone = EXCLUDED.privacy_zone,
                 secret_ref = EXCLUDED.secret_ref,
                  fallback = EXCLUDED.fallback,
                 params = EXCLUDED.params,
                  health = 'unknown'
               RETURNING id, profile_key""",
            profile_id.strip(),
            provider_id,
            model_id.strip(),
            revision.strip(),
            json.dumps(capabilities),
            privacy_zone,
            secret_ref,
            json.dumps(fallback),
            json.dumps(params or {}),
            costs.get("input_price_per_mtok"),
            costs.get("output_price_per_mtok"),
            costs.get("daily_cost_limit"),
            costs.get("monthly_cost_limit"),
        )
        if secret_writer is not None:
            secret_writer()
        await append_audit(
            connection,
            principal_id=actor_id,
            action="admin.upsert_model_profile",
            target_type="model_profile",
            target_id=row["profile_key"],
            metadata={
                "adapter": adapter.strip(),
                "endpoint": endpoint.strip(),
                "model_id": model_id.strip(),
                "privacy_zone": privacy_zone,
                "capabilities": sorted(capabilities),
                "secret": ("stored" if secret_writer is not None
                           else "reference" if secret_ref else "none"),
            },
        )
    return {"id": str(row["id"]), "profile_id": row["profile_key"], "status": "saved_unverified"}


async def upsert_stage_route(
    pool: Any,
    *,
    actor_id: UUID,
    mode: str,
    stage: str,
    profile_id: str,
    fallback: list[str],
    escalation_profile_id: str | None = None,
) -> dict[str, Any]:
    clean_mode = mode.strip().upper()
    clean_stage = stage.strip()
    escalation_key = (escalation_profile_id or "").strip() or None
    if clean_mode not in {"API", "LOCAL"}:
        raise AdminServiceError("INVALID_REQUEST", 422)
    if clean_stage not in STAGES:
        raise AdminServiceError("MODEL_STAGE_UNSUPPORTED", 422)
    if escalation_key is not None and (
        clean_mode != "API" or clean_stage not in ESCALATION_STAGES
    ):
        # Local Only never has a way out to an API; other stages have no code check
        # that could decide a local result is not good enough.
        raise AdminServiceError("MODEL_ESCALATION_NOT_ALLOWED", 422)
    async with pool.acquire() as connection, connection.transaction():
        await connection.execute("LOCK TABLE model_profiles IN SHARE ROW EXCLUSIVE MODE")
        prof = await connection.fetchrow(
            """SELECT mp.id, mp.privacy_zone, mp.capabilities, p.adapter, p.endpoint,
                      mp.profile_key, mp.model_id, mp.revision, mp.secret_ref
               FROM model_profiles mp JOIN providers p ON p.id = mp.provider_id
               WHERE mp.profile_key = $1""",
            profile_id.strip(),
        )
        if prof is None:
            raise AdminServiceError("PROFILE_NOT_FOUND", 404)
        if clean_mode == "LOCAL" and prof["privacy_zone"] == "public":
            raise AdminServiceError("REMOTE_AI_DENIED", 409)
        rows = await connection.fetch(
            "SELECT profile_key, privacy_zone, fallback FROM model_profiles"
        )
        profiles = {row["profile_key"]: dict(row) for row in rows}
        _validate_fallbacks(profile_id.strip(), profiles, route_fallback=fallback)
        policy = EndpointPolicy.from_env()
        try:
            validate_profile(
                _route_profile(prof), OperatingMode(clean_mode), policy, clean_stage
            )
        except RegistryRuntimeError as exc:
            raise AdminServiceError(str(exc), 422) from exc
        escalation_row_id = None
        if escalation_key is not None:
            esc = await connection.fetchrow(
                """SELECT mp.id, mp.privacy_zone, mp.capabilities, p.adapter, p.endpoint,
                          mp.profile_key, mp.model_id, mp.revision, mp.secret_ref
                   FROM model_profiles mp JOIN providers p ON p.id = mp.provider_id
                   WHERE mp.profile_key = $1""",
                escalation_key,
            )
            if esc is None:
                raise AdminServiceError("PROFILE_NOT_FOUND", 404)
            if esc["privacy_zone"] != "public" or escalation_key == profile_id.strip():
                raise AdminServiceError("MODEL_ESCALATION_NOT_PUBLIC", 422)
            try:
                validate_profile(_route_profile(esc), OperatingMode.API, policy, clean_stage)
            except RegistryRuntimeError as exc:
                raise AdminServiceError(str(exc), 422) from exc
            escalation_row_id = esc["id"]
        await connection.execute(
            """INSERT INTO stage_routes (mode, stage, profile_id, fallback, escalation_profile_id)
               VALUES ($1, $2, $3, $4::jsonb, $5)
               ON CONFLICT (mode, stage) DO UPDATE SET
                 profile_id = EXCLUDED.profile_id,
                 fallback = EXCLUDED.fallback,
                 escalation_profile_id = EXCLUDED.escalation_profile_id""",
            clean_mode,
            clean_stage,
            prof["id"],
            json.dumps(fallback),
            escalation_row_id,
        )
        await append_audit(
            connection,
            principal_id=actor_id,
            action="admin.upsert_stage_route",
            target_type="stage_route",
            target_id=f"{clean_mode}:{clean_stage}",
            metadata={"profile_id": profile_id.strip(), "escalation_profile_id": escalation_key},
        )
    return {
        "mode": clean_mode, "stage": clean_stage, "profile_id": profile_id.strip(),
        "escalation_profile_id": escalation_key,
    }


async def upsert_stage_policy(
    pool: Any,
    *,
    actor_id: UUID,
    mode: str,
    stage: str,
    max_attempts: int,
    max_output_tokens: int | None,
    timeout_seconds: float | None,
    max_concurrency: int | None,
) -> dict[str, Any]:
    """Store the call limits of one (mode, stage); replaces the fixed 2 attempts (ADR-007)."""

    clean_mode = mode.strip().upper()
    clean_stage = stage.strip()
    if clean_mode not in {"API", "LOCAL"}:
        raise AdminServiceError("INVALID_REQUEST", 422)
    if clean_stage not in STAGES:
        raise AdminServiceError("MODEL_STAGE_UNSUPPORTED", 422)
    try:
        StagePolicy(
            max_attempts=max_attempts, max_output_tokens=max_output_tokens,
            timeout_seconds=timeout_seconds, max_concurrency=max_concurrency,
        )
    except ValueError as exc:
        raise AdminServiceError("INVALID_REQUEST", 422) from exc
    async with pool.acquire() as connection, connection.transaction():
        await connection.execute(
            """INSERT INTO stage_policies
               (mode, stage, max_attempts, max_output_tokens, timeout_seconds,
                max_concurrency, updated_by, updated_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, now())
               ON CONFLICT (mode, stage) DO UPDATE SET
                 max_attempts = EXCLUDED.max_attempts,
                 max_output_tokens = EXCLUDED.max_output_tokens,
                 timeout_seconds = EXCLUDED.timeout_seconds,
                 max_concurrency = EXCLUDED.max_concurrency,
                 updated_by = EXCLUDED.updated_by,
                 updated_at = now()""",
            clean_mode, clean_stage, max_attempts, max_output_tokens, timeout_seconds,
            max_concurrency, actor_id,
        )
        await append_audit(
            connection,
            principal_id=actor_id,
            action="admin.upsert_stage_policy",
            target_type="stage_policy",
            target_id=f"{clean_mode}:{clean_stage}",
            metadata={
                "max_attempts": max_attempts, "max_output_tokens": max_output_tokens,
                "timeout_seconds": timeout_seconds, "max_concurrency": max_concurrency,
            },
        )
    return {
        "mode": clean_mode, "stage": clean_stage, "max_attempts": max_attempts,
        "max_output_tokens": max_output_tokens, "timeout_seconds": timeout_seconds,
        "max_concurrency": max_concurrency,
    }


def _route_profile(row: Any) -> ModelProfile:
    return ModelProfile(
        profile_id=row["profile_key"], adapter=row["adapter"],
        endpoint=row["endpoint"], model_id=row["model_id"],
        revision=row["revision"], privacy_zone=PrivacyZone(row["privacy_zone"]),
        capabilities=frozenset(_json_list(row["capabilities"])),
        secret_ref=row["secret_ref"],
    )


def _number(value: Any) -> float | None:
    return None if value is None else float(value)


def _json_object(value: Any) -> dict[str, Any]:
    decoded = json.loads(value) if isinstance(value, str) else value
    return dict(decoded) if isinstance(decoded, dict) else {}


def _json_list(value: Any) -> list[str]:
    decoded = json.loads(value) if isinstance(value, str) else value
    return [item for item in decoded if isinstance(item, str)] if isinstance(decoded, list) else []


def _validate_fallbacks(
    profile_id: str, profiles: dict[str, dict[str, Any]], *,
    route_fallback: list[str] | None = None,
) -> None:
    zone = profiles[profile_id]["privacy_zone"]

    def visit(key: str, ancestors: frozenset[str], depth: int) -> None:
        if key in ancestors or depth > 16:
            raise AdminServiceError("MODEL_FALLBACK_CYCLE", 422)
        profile = profiles.get(key)
        if profile is None:
            raise AdminServiceError("PROFILE_NOT_FOUND", 404)
        if profile["privacy_zone"] != zone:
            raise AdminServiceError("MODEL_FALLBACK_ZONE_MISMATCH", 422)
        keys = _json_list(profile["fallback"])
        if len(keys) > 1 or len(keys) != len(set(keys)):
            raise AdminServiceError("INVALID_REQUEST", 422)
        for fallback_id in keys:
            visit(fallback_id, ancestors | {key}, depth + 1)

    visit(profile_id, frozenset(), 0)
    if route_fallback is not None:
        if len(route_fallback) > 1 or len(route_fallback) != len(set(route_fallback)):
            raise AdminServiceError("INVALID_REQUEST", 422)
        for key in route_fallback:
            visit(key, frozenset({profile_id}), 1)


async def list_audit_events(pool: Any, *, limit: int = 100) -> dict[str, Any]:
    async with pool.acquire() as connection:
        rows = await connection.fetch(
            """SELECT a.id, a.principal_id, u.username, a.action, a.target_type,
                      a.target_id, a.metadata, a.previous_hash, a.event_hash, a.occurred_at
               FROM audit_events a
               LEFT JOIN users u ON u.id = a.principal_id
               ORDER BY a.occurred_at DESC, a.id DESC
               LIMIT $1""",
            min(max(limit, 1), 500),
        )
        chain = await verify_audit_chain(connection)
    return {
        "chain": chain,
        "events": [
            {
                "id": str(row["id"]),
                "principal_id": str(row["principal_id"]) if row["principal_id"] else None,
                "username": row["username"],
                "action": row["action"],
                "target_type": row["target_type"],
                "target_id": row["target_id"],
                "metadata": json.loads(row["metadata"])
                if isinstance(row["metadata"], str)
                else dict(row["metadata"] or {}),
                "previous_hash": row["previous_hash"],
                "event_hash": row["event_hash"],
                "occurred_at": row["occurred_at"].isoformat(),
            }
            for row in rows
        ],
    }
