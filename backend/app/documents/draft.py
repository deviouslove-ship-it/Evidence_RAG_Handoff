"""Persist an inspected PDF as an unapproved, immutable document draft."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from ipaddress import ip_address
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from ..audit import append_audit
from ..auth_acl.policy import Principal
from ..effectivity.store import detect_and_store_dates
from ..schemas import PdfDraftResponse, PotentialDuplicate
from ..vietnamese_nlp.unicode_norm import fold_text
from .convert import ConvertedSource
from .deduplication import content_fingerprint, find_content_matches
from .isolated import extract_isolated
from .management_read import _METADATA_FIELDS, _record
from .native_pdf import ExtractedPage, extract_native_pdf
from .node_writer import suspect_text_layer, write_nodes
from .ocr import OcrEngine
from .provenance import save_immutable_pdf, save_source_file
from .review import ReviewError
from .tree_parser import ParsedNode, parse_legal_tree


@dataclass(frozen=True)
class PreparedDraft:
    content: bytes
    sha256: str
    pages: list[ExtractedPage]
    nodes: list[ParsedNode]


def prepare_draft(
    content: bytes,
    *,
    max_pages: int,
    ocr_engine: OcrEngine | None = None,
    temporary_root: Path | None = None,
    isolate: bool = False,
    timeout_seconds: float = 120,
) -> PreparedDraft:
    """Reject malformed/oversized-page PDFs before touching the persistent store."""
    if isolate:
        pages, digest = extract_isolated(
            content, max_pages=max_pages, temporary_root=temporary_root,
            enable_ocr=ocr_engine is not None, timeout_seconds=timeout_seconds,
        )
        return PreparedDraft(content, digest, pages, parse_legal_tree(pages))
    if temporary_root is not None:
        temporary_root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="evidence-pdf-draft-", dir=temporary_root) as temporary:
        source = save_immutable_pdf(content, Path(temporary))
        pages, digest = extract_native_pdf(
            source.path, ocr_engine=ocr_engine, max_pages=max_pages
        )
    return PreparedDraft(content, digest, pages, parse_legal_tree(pages))


def validate_source_url(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("INVALID_SOURCE_URL") from exc
    if parsed.scheme != "https" or not hostname or parsed.username or parsed.password:
        raise ValueError("INVALID_SOURCE_URL")
    if (
        port not in {None, 443}
        or not re.fullmatch(
            r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}",
            hostname.lower(),
        )
    ):
        raise ValueError("INVALID_SOURCE_URL")
    if hostname.lower().endswith((".local", ".internal", ".localhost")):
        raise ValueError("INVALID_SOURCE_URL")
    try:
        ip_address(hostname)
    except ValueError:
        pass
    else:
        raise ValueError("INVALID_SOURCE_URL")
    return value, hostname.lower()


async def new_original_base(
    connection: Any, principal: Principal, document_id: UUID, revision: int, *, lock: bool = False,
) -> Any:
    if lock:
        await connection.fetchval("SELECT id FROM documents WHERE id=$1 FOR UPDATE", document_id)
    row = await _record(connection, principal, document_id, None, date.today())
    if not row["can_edit"]:
        raise ReviewError("DOCUMENT_EDIT_DENIED", 403)
    if row["revision"] != revision or row["review_status"] not in {"approved", "rejected"}:
        raise ReviewError("DOCUMENT_REVISION_CONFLICT", 409)
    return row


async def persist_draft(
    prepared: PreparedDraft,
    *,
    pool: Any,
    store_root: Path,
    title: str,
    doc_type: str,
    original_filename: str,
    document_number: str | None = None,
    issuing_body: str | None = None,
    publication_date: date | None = None,
    official_url: str | None = None,
    submitted_by: UUID | None = None,
    converted: ConvertedSource | None = None,
    existing_document: tuple[UUID, int, Principal] | None = None,
) -> PdfDraftResponse:
    """Write the original and one DB transaction; retrieval remains approval-gated.

    ``converted`` is set when the upload was Word/TXT: ``prepared`` then describes the
    PDF rendered from it and the uploaded file is kept under ``sources/``.
    """
    official_url, publisher_domain = validate_source_url(official_url)
    source = await asyncio.to_thread(save_immutable_pdf, prepared.content, store_root / "originals")
    if source.sha256 != prepared.sha256:
        raise ValueError("PDF_HASH_CHANGED")
    source_format = converted.source_format if converted else "pdf"
    source_file_sha256: str | None = None
    if converted is not None and converted.source_bytes is not None:
        source_file_sha256 = await asyncio.to_thread(
            save_source_file, converted.source_bytes, converted.source_format,
            store_root / "sources",
        )
    document_id, version_id = uuid4(), uuid4()
    version_number = 1
    source_revision = 1
    fingerprint = content_fingerprint(prepared.pages)
    captured_at = datetime.now(UTC)
    safe_filename = "".join(
        char for char in original_filename.replace("\\", "/").rsplit("/", 1)[-1]
        if char.isprintable()
    ).strip()[:255]
    if not safe_filename:
        safe_filename = "document.pdf"
    async with pool.acquire() as connection:
        async with connection.transaction():
            matches: list[PotentialDuplicate] = []
            if fingerprint is not None:
                matches = await find_content_matches(
                    connection, fingerprint=fingerprint, viewer_id=submitted_by,
                )
            metadata_json = None
            if existing_document is None:
                await connection.execute(
                    """INSERT INTO documents (id, doc_type, title, document_number, issuing_body)
                       VALUES ($1, $2, $3, $4, $5)""",
                    document_id, doc_type, title, document_number, issuing_body,
                )
            else:
                document_id, expected_revision, principal = existing_document
                current = await new_original_base(connection, principal, document_id,
                                                  expected_revision, lock=True)
                version_number = current["version_number"] + 1
                source_revision = current["revision"] + 1
                metadata_json = json.dumps({
                    "title": title, "doc_type": doc_type, "document_number": document_number,
                    "issuing_body": issuing_body,
                }, ensure_ascii=False)
                await connection.execute(
                    """UPDATE document_versions
                       SET admin_metadata = COALESCE(admin_metadata, $2::jsonb)
                       WHERE id=$1""", current["version_id"],
                    json.dumps({key: current[key] for key in _METADATA_FIELDS},
                               ensure_ascii=False),
                )
            await connection.execute(
                """INSERT INTO document_versions
                   (id, document_id, official_url, publication_date,
                    original_file_path, original_file_sha256, original_filename,
                    captured_at, review_status, submitted_by, native_text_fingerprint_v1,
                    source_format, source_file_sha256, version_number, admin_metadata,
                    source_review_revision)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'draft', $9, $10, $11, $12,
                           $13, $14::jsonb, $15)""",
                version_id, document_id, official_url, publication_date,
                f"originals/{source.sha256}.pdf", source.sha256, safe_filename,
                captured_at, submitted_by, fingerprint, source_format, source_file_sha256,
                version_number, metadata_json, source_revision,
            )
            await connection.execute(
                """INSERT INTO source_provenance
                   (document_version_id, official_url, publisher_domain,
                    captured_at, fetched_checksum)
                   VALUES ($1, $2, $3, $4, $5)""",
                version_id, official_url, publisher_domain, captured_at, source.sha256,
            )
            page_ids: dict[int, UUID] = {}
            for page in prepared.pages:
                page_id = uuid4()
                page_ids[page.page_number] = page_id
                await connection.execute(
                    """INSERT INTO source_pages
                       (id, document_version_id, page_number, width, height, rotation,
                        extraction_method, text_quality, text_original, extraction_error,
                        ocr_diagnostics)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb)""",
                    page_id, version_id, page.page_number, page.width, page.height,
                    page.rotation, page.extraction_method, page.text_quality,
                    page.text, page.extraction_error,
                    json.dumps(page.ocr_diagnostics, ensure_ascii=False)
                    if page.ocr_diagnostics is not None else None,
                )
                if page.text:
                    span_id = uuid4()
                    await connection.execute(
                        """INSERT INTO source_spans
                           (id, page_id, original_offset, original_length, text_original)
                           VALUES ($1, $2, 0, $3, $4)""",
                        span_id, page_id, len(page.text), page.text,
                    )
                if page.text_quality == "usable" and suspect_text_layer(page.text):
                    await connection.execute(
                        """INSERT INTO curator_review_tasks
                           (document_version_id, reason, risk)
                           VALUES ($1, $2, 'high')""",
                        version_id, f"page_{page.page_number}_text_layer_suspect",
                    )
                if page.text_quality != "usable":
                    flags = (page.ocr_diagnostics or {}).get("flags") or []
                    await connection.execute(
                        """INSERT INTO curator_review_tasks
                           (document_version_id, reason, risk)
                           VALUES ($1, $2, $3)""",
                        version_id, f"page_{page.page_number}_{page.text_quality}",
                        "high" if page.text_quality == "needs_ocr" or flags else "medium",
                    )
            if document_number and any(
                    page.extraction_method == "local_ocr" for page in prepared.pages):
                # OCR misreads digits too; the declared number must be visible in the scan.
                wanted = "".join(fold_text(document_number).split())
                head = "".join(fold_text(" ".join(page.text for page in prepared.pages[:2]))
                               .split())
                if wanted not in head:
                    await connection.execute(
                        """INSERT INTO curator_review_tasks
                           (document_version_id, reason, risk)
                           VALUES ($1, 'document_number_not_in_ocr_text', 'high')""",
                        version_id,
                    )
            _, unanchored_nodes = await write_nodes(
                connection, document_id=document_id, version_id=version_id, title=title,
                document_number=document_number, page_ids=page_ids,
                page_texts={page.page_number: page.text for page in prepared.pages},
                nodes=prepared.nodes,
            )
            # G1: issue/effective dates read by rule, shown to the source reviewer.
            await detect_and_store_dates(connection, version_id)
            if unanchored_nodes:
                await connection.execute(
                    """INSERT INTO curator_review_tasks
                       (document_version_id, reason, risk)
                       VALUES ($1, 'unanchored_source_spans', 'high')""",
                    version_id,
                )
            if matches:
                await connection.execute(
                    """INSERT INTO curator_review_tasks
                       (document_version_id, reason, risk)
                       VALUES ($1, 'possible_duplicate_content', 'high')""",
                    version_id,
                )
            await connection.execute(
                """INSERT INTO curator_review_tasks
                   (document_version_id, reason, risk)
                   VALUES ($1, 'metadata_and_source_verification', 'high')""",
                version_id,
            )
            if existing_document is not None:
                await append_audit(
                    connection, principal_id=submitted_by, action="document.add_version",
                    target_type="document_version", target_id=str(version_id),
                    metadata={"document_id": str(document_id), "version_number": version_number},
                )
    return PdfDraftResponse(
        document_id=document_id,
        document_version_id=version_id,
        sha256=source.sha256,
        page_count=len(prepared.pages),
        node_count=len(prepared.nodes),
        review_required_pages=sum(
            page.text_quality != "usable" for page in prepared.pages
        ),
        content_check_available=fingerprint is not None,
        potential_duplicates=matches,
    )
