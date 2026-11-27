"""Shared FastAPI response helper for serving SHA-verified original source files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from ...documents.provenance import (
    SOURCE_MEDIA,
    content_disposition,
    read_original_source_bytes,
)
from .errors import api_error


async def original_file_response(
    settings: Any,
    source: Any,
    *,
    unavailable_code: str = "CITATION_SOURCE_UNAVAILABLE",
) -> Response:
    """Build a ``no-store`` Response for an already-authorized original source file."""

    if not settings.document_store_root:
        raise api_error(503, "DOCUMENT_STORE_NOT_CONFIGURED")
    root = Path(settings.document_store_root)
    try:
        content, digest = await run_in_threadpool(
            read_original_source_bytes,
            root,
            original_file_path=source.original_file_path,
            source_hash=source.source_hash,
            source_format=source.source_format,
            source_file_sha256=source.source_file_sha256,
            max_bytes=settings.max_upload_bytes,
        )
    except ValueError as exc:
        raise api_error(503, unavailable_code) from exc
    media_type, disposition = SOURCE_MEDIA.get(
        source.source_format, ("application/octet-stream", "attachment")
    )
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": content_disposition(
                disposition, source.original_filename, source.source_format
            ),
            "X-Source-Format": source.source_format,
            "X-Source-SHA256": digest,
        },
    )
