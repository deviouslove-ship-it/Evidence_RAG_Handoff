"""PDF intake invariants: magic bytes, immutable hash and provenance."""

from __future__ import annotations

import hashlib
import os
import re
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock
from uuid import UUID

PDF_MAGIC = b"%PDF-"


@dataclass(frozen=True)
class SourceFile:
    path: Path
    sha256: str
    size: int
    mime_type: str = "application/pdf"


@dataclass(frozen=True)
class Provenance:
    source_url: str | None
    publisher_domain: str | None
    retrieved_at: str | None
    sha256: str
    redirect_chain: tuple[str, ...] = ()
    source_verified_by: UUID | None = None


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def validate_pdf_bytes(content: bytes) -> None:
    if len(content) < 5 or not content.startswith(PDF_MAGIC):
        raise ValueError("INVALID_PDF_MAGIC")
    if b"%%EOF" not in content[-4096:]:
        raise ValueError("INVALID_PDF_STRUCTURE")


def save_immutable_pdf(content: bytes, destination: Path) -> SourceFile:
    validate_pdf_bytes(content)
    digest = sha256_bytes(content)
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / f"{digest}.pdf"
    if not target.exists():
        with NamedTemporaryFile(
            mode="wb", prefix=".incoming-", suffix=".pdf", dir=destination, delete=False
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            staged = Path(temporary.name)
        try:
            try:
                os.link(staged, target)
            except FileExistsError:
                pass
        finally:
            staged.unlink(missing_ok=True)
    if sha256_bytes(target.read_bytes()) != digest:
        raise ValueError("IMMUTABLE_FILE_CONFLICT")
    return SourceFile(path=target, sha256=digest, size=len(content))


def save_source_file(
    content: bytes, source_format: str, destination: Path
) -> str:
    """Keep the uploaded Word/TXT file next to the PDF rendered from it."""
    digest = sha256_bytes(content)
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / f"{digest}.{source_format}"
    if not target.exists():
        with NamedTemporaryFile(
            mode="wb", prefix=".incoming-", dir=destination, delete=False
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            staged = Path(temporary.name)
        try:
            try:
                os.link(staged, target)
            except FileExistsError:
                pass
        finally:
            staged.unlink(missing_ok=True)
    if sha256_bytes(target.read_bytes()) != digest:
        raise ValueError("IMMUTABLE_FILE_CONFLICT")
    return digest


def _stored_pdf_path(store_root: Path, relative_path: str, digest: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{64}", digest) or relative_path != f"originals/{digest}.pdf":
        raise ValueError("PDF_STORAGE_CONFLICT")
    return store_root / "originals" / f"{digest}.pdf"


# (resolved path, digest) -> (size, mtime_ns, ctime_ns) of the file when its
# SHA-256 last matched.  Bounded; any change to the file invalidates the entry.
_VERIFIED_FILES: OrderedDict[tuple[str, str], tuple[int, int, int]] = OrderedDict()
_VERIFIED_FILES_LIMIT = 512
_VERIFIED_FILES_LOCK = Lock()


def verify_immutable_pdf(
    store_root: Path, relative_path: str, digest: str, *, max_bytes: int
) -> None:
    """Check a stored PDF still matches its digest without loading it into memory.

    Used to re-validate evidence for every chat turn.  The file is hashed in
    chunks; when its size and timestamps are unchanged since the last
    successful check the hash is not recomputed.  Serving bytes to a user
    always goes through ``read_immutable_pdf``, which re-hashes the content.
    """

    target = _stored_pdf_path(store_root, relative_path, digest)
    try:
        resolved = target.resolve()
        if not resolved.is_relative_to(store_root.resolve()):
            raise ValueError("PDF_STORAGE_CONFLICT")
        stat = resolved.stat()
        if stat.st_size > max_bytes:
            raise ValueError("PDF_STORAGE_CONFLICT")
        key = (str(resolved), digest)
        signature = (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
        with _VERIFIED_FILES_LOCK:
            if _VERIFIED_FILES.get(key) == signature:
                _VERIFIED_FILES.move_to_end(key)
                return
        hasher = hashlib.sha256()
        read = 0
        with resolved.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                read += len(chunk)
                if read > max_bytes:
                    raise ValueError("PDF_STORAGE_CONFLICT")
                hasher.update(chunk)
    except OSError as exc:
        raise ValueError("PDF_STORAGE_CONFLICT") from exc
    if hasher.hexdigest() != digest:
        with _VERIFIED_FILES_LOCK:
            _VERIFIED_FILES.pop(key, None)
        raise ValueError("PDF_STORAGE_CONFLICT")
    with _VERIFIED_FILES_LOCK:
        _VERIFIED_FILES[key] = signature
        _VERIFIED_FILES.move_to_end(key)
        while len(_VERIFIED_FILES) > _VERIFIED_FILES_LIMIT:
            _VERIFIED_FILES.popitem(last=False)


SOURCE_FORMATS = ("docx", "doc", "txt")


def read_immutable_source(
    store_root: Path, source_format: str, digest: str | None, *, max_bytes: int
) -> bytes:
    """Bytes of the Word/TXT file the curator uploaded, checked against its own SHA-256.

    The PDF rendered from it is only an anchoring copy for citations; users who open
    the source get this file.  Paths are derived from the digest, never taken from data.
    """

    if source_format not in SOURCE_FORMATS or not digest or not re.fullmatch(
        r"[0-9a-f]{64}", digest
    ):
        raise ValueError("SOURCE_STORAGE_CONFLICT")
    target = store_root / "sources" / f"{digest}.{source_format}"
    try:
        if not target.resolve().is_relative_to(store_root.resolve()):
            raise ValueError("SOURCE_STORAGE_CONFLICT")
        with target.open("rb") as stream:
            content = stream.read(max_bytes + 1)
        if len(content) > max_bytes:
            raise ValueError("SOURCE_STORAGE_CONFLICT")
    except OSError as exc:
        raise ValueError("SOURCE_STORAGE_CONFLICT") from exc
    if sha256_bytes(content) != digest:
        raise ValueError("SOURCE_STORAGE_CONFLICT")
    return content


def read_immutable_pdf(
    store_root: Path, relative_path: str, digest: str, *, max_bytes: int
) -> bytes:
    """Never follow an arbitrary stored path or serve bytes with a changed hash."""
    target = _stored_pdf_path(store_root, relative_path, digest)
    try:
        if not target.resolve().is_relative_to(store_root.resolve()):
            raise ValueError("PDF_STORAGE_CONFLICT")
        with target.open("rb") as stream:
            content = stream.read(max_bytes + 1)
        if len(content) > max_bytes:
            raise ValueError("PDF_STORAGE_CONFLICT")
    except OSError as exc:
        raise ValueError("PDF_STORAGE_CONFLICT") from exc
    if sha256_bytes(content) != digest:
        raise ValueError("PDF_STORAGE_CONFLICT")
    return content
