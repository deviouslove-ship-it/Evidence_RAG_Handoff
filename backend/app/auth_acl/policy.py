"""Small, explicit policy layer.

The real deployment plugs a local identity provider into this module.  The policy
rules deliberately do not infer document access from an administrative role.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum


class Permission(StrEnum):
    QUERY = "rag.query"
    CURATE = "rag.curate"
    REVIEW = "rag.review"
    ADMIN = "admin.config"
    AUDIT = "audit.read"


_ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "USER": frozenset({Permission.QUERY}),
    "CURATOR": frozenset({Permission.CURATE}),
    "REVIEWER": frozenset({Permission.REVIEW}),
    "SYS_ADMIN": frozenset({Permission.ADMIN}),
    "AUDITOR": frozenset({Permission.AUDIT}),
}


@dataclass(frozen=True)
class Principal:
    id: str
    roles: frozenset[str] = field(default_factory=frozenset)
    category_ids: frozenset[str] = field(default_factory=frozenset)
    document_ids: frozenset[str] = field(default_factory=frozenset)

    @property
    def permissions(self) -> frozenset[Permission]:
        result: set[Permission] = set()
        for role in self.roles:
            result.update(_ROLE_PERMISSIONS.get(role.upper(), frozenset()))
        return frozenset(result)

    def has(self, permission: Permission) -> bool:
        return permission in self.permissions

    def can_access_category(self, category_id: str) -> bool:
        return category_id in self.category_ids

    def can_access_document(self, document_id: str) -> bool:
        return document_id in self.document_ids


def permission_for_role(role: str) -> frozenset[Permission]:
    return _ROLE_PERMISSIONS.get(role.upper(), frozenset())


def require_permission(principal: Principal, permission: Permission) -> None:
    if not principal.has(permission):
        raise PermissionError(f"missing permission: {permission.value}")


def normalize_roles(roles: Iterable[str]) -> frozenset[str]:
    return frozenset(role.strip().upper() for role in roles if role.strip())
