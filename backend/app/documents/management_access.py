"""Keep managed revisions within the document's existing ACL."""

import re
from typing import Any
from uuid import UUID

from ..auth_acl.policy import Permission, Principal

# Assigned documents inherit their existing category/direct grants. The draft
# workflow still lets staff collaborate before a document has any category.
STAFF_SCOPE = """
    SELECT
      NOT EXISTS (SELECT 1 FROM document_categories dc WHERE dc.document_id = d.id)
      AND NOT EXISTS (SELECT 1 FROM document_acl da WHERE da.document_id = d.id) AS unassigned,
      EXISTS (
        SELECT 1 FROM document_acl da
        WHERE da.document_id = d.id AND da.user_id = $1 AND da.can_query
        UNION ALL
        SELECT 1 FROM document_categories dc
        JOIN categories c ON c.id = dc.category_id AND c.deleted_at IS NULL
        JOIN category_acl ca ON ca.category_id = c.id
        WHERE dc.document_id = d.id AND ca.user_id = $1
          AND (ca.can_query OR ($3 AND ca.can_review))
      ) AS granted,
      NOT EXISTS (
        SELECT 1 FROM document_categories dc
        JOIN categories c ON c.id = dc.category_id AND c.deleted_at IS NULL
        WHERE dc.document_id = d.id AND NOT EXISTS (
          SELECT 1 FROM category_acl ca WHERE ca.category_id = c.id
            AND ca.user_id = $1 AND ca.can_review
        )
      ) AS can_review_all
"""

CAN_READ = """
    (scope.granted OR (scope.unassigned AND
      ($3 OR ($2 AND (v.submitted_by IS NULL OR v.submitted_by = $1)))))
"""


def managed_read_sql(first_parameter: int) -> tuple[str, str]:
    """Keep legacy intake access and scope managed revisions on the same routes."""
    offset = first_parameter - 1

    def shift(sql: str) -> str:
        return re.sub(r"\$(\d+)", lambda match: f"${int(match[1]) + offset}", sql)

    return (f"CROSS JOIN LATERAL ({shift(STAFF_SCOPE)}) scope",
            f"AND (v.admin_metadata IS NULL OR {shift(CAN_READ)})")


def scope_params(principal: Principal) -> tuple[UUID, bool, bool]:
    return UUID(principal.id), principal.has(Permission.CURATE), principal.has(Permission.REVIEW)


async def version_scope(
    connection: Any, version_id: UUID, actor_id: UUID, *, curator: bool, reviewer: bool,
) -> Any:
    return await connection.fetchrow(
        f"""SELECT d.deleted_at, v.admin_metadata IS NOT NULL AS managed,
                  v.submitted_by, {CAN_READ} AS can_read,
                  scope.can_review_all
            FROM document_versions v JOIN documents d ON d.id = v.document_id
            CROSS JOIN LATERAL ({STAFF_SCOPE}) scope
            WHERE v.id = $4""",
        actor_id, curator, reviewer, version_id,
    )


async def lock_review_version(connection: Any, version_id: UUID) -> Any:
    # Lifecycle actions, editors and reviewers take the document lock first.
    document = await connection.fetchrow(
        """SELECT d.id, d.deleted_at FROM documents d
           JOIN document_versions v ON v.document_id = d.id
           WHERE v.id = $1 FOR UPDATE OF d""", version_id,
    )
    if document is None or document["deleted_at"] is not None:
        return None
    return await connection.fetchrow(
        "SELECT * FROM document_versions WHERE id = $1 FOR UPDATE", version_id,
    )
