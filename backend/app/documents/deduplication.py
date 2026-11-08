"""Conservative detection of PDF content duplicates."""

from hashlib import sha256
from typing import Any
from unicodedata import normalize
from uuid import UUID

from ..schemas import PotentialDuplicate
from .native_pdf import ExtractedPage


def content_fingerprint(pages: list[ExtractedPage]) -> str | None:
    if not pages or any(
        page.extraction_method != "native_text"
        or page.text_quality != "usable"
        or not page.text.strip()
        for page in pages
    ):
        return None
    text = " ".join(" ".join(normalize("NFC", page.text).split()) for page in pages)
    return sha256(("pdf-native-text-v1\0" + text).encode("utf-8")).hexdigest()


async def find_content_matches(
    connection: Any, *, fingerprint: str, viewer_id: UUID | None,
    exclude_version_id: UUID | None = None,
    lock: bool = True,
) -> list[PotentialDuplicate]:
    """Serialize matching imports and reveal only drafts or authorized sources."""
    if lock:
        await connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
            f"pdf-native-text-v1:{fingerprint}",
        )
    rows = await connection.fetch(
        """SELECT dv.id AS document_version_id, d.title, d.document_number,
                  dv.review_status::text AS status
           FROM document_versions dv JOIN documents d ON d.id = dv.document_id
           WHERE dv.native_text_fingerprint_v1 = $1 AND d.deleted_at IS NULL
             AND ($3::uuid IS NULL OR dv.id <> $3::uuid)
             AND (dv.review_status IN ('draft', 'pending_review')
               OR EXISTS (
                 SELECT 1 FROM document_acl da
                 JOIN users u ON u.id = da.user_id AND u.disabled_at IS NULL
                 WHERE da.document_id = d.id AND da.user_id = $2::uuid AND da.can_query
               ) OR EXISTS (
                 SELECT 1 FROM document_categories dc
                 JOIN category_acl ca ON ca.category_id = dc.category_id
                 JOIN categories c ON c.id = ca.category_id AND c.deleted_at IS NULL
                 JOIN users u ON u.id = ca.user_id AND u.disabled_at IS NULL
                 WHERE dc.document_id = d.id AND ca.user_id = $2::uuid AND ca.can_query
               ))
           ORDER BY dv.captured_at DESC NULLS LAST, dv.id LIMIT 5""",
        fingerprint, viewer_id, exclude_version_id,
    )
    return [PotentialDuplicate.model_validate(dict(row)) for row in rows]
