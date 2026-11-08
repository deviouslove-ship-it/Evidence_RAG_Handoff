"""Authentication and ABAC policy primitives."""

from .policy import Principal, permission_for_role, require_permission

__all__ = ["Principal", "permission_for_role", "require_permission"]
