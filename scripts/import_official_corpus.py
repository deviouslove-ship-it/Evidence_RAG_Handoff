"""Create categories from a folder tree and load its documents as drafts.

    python scripts/import_official_corpus.py --source-dir <folder>            # dry-run
    python scripts/import_official_corpus.py --source-dir <folder> --apply    # write

Layout: ``<source-dir>/<Folder>/[<code>]_<title>.<pdf|docx|doc|txt>``.  One category per
folder (code/name from FOLDERS below; unknown folders get a category named after the
folder).  A document lands in the category of the folder that holds it.

* Dry-run reads and converts every file but touches no database or store.
* ``--apply`` creates missing categories (never renames or revives deleted ones), grants
  query access to ``--grant-user`` and writes each file as a *draft* submitted by the
  CURATOR account.  Re-running skips files already imported (same PDF SHA-256).
* ``--approve`` additionally submits and approves the drafts through the normal review
  rules, as a REVIEWER other than the submitter.  It exists for test corpora only and
  records that in the review note; real corpora must be reviewed by people.

A ``.txt`` file whose code matches exactly one document in the same folder is read as its
metadata record (title, issue date, issuing body, official link); other ``.txt`` files are
ignored.  Document numbers come from the ``[code]`` in the file name, never from OCR.
No path, host or credential is hard-coded: the database comes from DATABASE_URL and the
store from EVIDENCE_DOCUMENT_STORE_ROOT, exactly like seed_local_runtime.py.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
import unicodedata
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.admin_services import create_category  # noqa: E402
from app.audit import append_audit  # noqa: E402
from app.documents.convert import convert_to_pdf  # noqa: E402
from app.documents.draft import persist_draft, prepare_draft, validate_source_url  # noqa: E402
from app.documents.provenance import sha256_bytes  # noqa: E402
from app.documents.review import approve_document_version, submit_draft_for_review  # noqa: E402
from app.migrations.runner import apply_migrations  # noqa: E402
from app.storage.postgres import create_pool  # noqa: E402

# folder -> (category code, category name, doc_type)
FOLDERS: dict[str, tuple[str, str, str]] = {
    "Luat": ("LUAT", "Luật", "law"),
    "Nghi_dinh": ("NGHI_DINH", "Nghị định", "decree"),
    "Quyet_dinh": ("QUYET_DINH", "Quyết định", "decision"),
    "Thong_tu": ("THONG_TU", "Thông tư", "circular"),
    "Thong_tu_lien_tich": ("THONG_TU_LIEN_TICH", "Thông tư liên tịch", "joint_circular"),
    "Chi_thi": ("CHI_THI", "Chỉ thị", "directive"),
    "Cac_loai_van_ban_khac": ("CAC_LOAI_VAN_BAN_KHAC", "Các loại văn bản khác", "other"),
}
DOC_SUFFIXES = {".pdf", ".docx", ".doc"}
_NAME = re.compile(r"^\[(?P<code>[^\]]+)\]_?(?P<title>.*)$")
_NUMBER = re.compile(r"^(?P<no>\d+[A-Za-z]?)_(?P<year>\d{4})_(?P<kind>.+)$")
_NUMBER_NO_YEAR = re.compile(r"^(?P<no>\d+[A-Za-z]?)_(?P<kind>.+)$")
_TYPE_LINE = re.compile(
    r"^(LUẬT|NGHỊ ĐỊNH|THÔNG TƯ LIÊN TỊCH|THÔNG TƯ|QUYẾT ĐỊNH|CHỈ THỊ|VĂN BẢN HỢP NHẤT"
    r"|QUY CHẾ|QUY ĐỊNH|KẾ HOẠCH|CHƯƠNG TRÌNH|HƯỚNG DẪN)\s*$"
)
_STOP_LINE = re.compile(
    r"^(Căn cứ|Theo |Xét |Điều\s+\d|Chương |BỘ TRƯỞNG|CHÍNH PHỦ|QUỐC HỘI|THỦ TƯỚNG|Kính gửi)",
    re.IGNORECASE,
)


@dataclass
class Item:
    folder: str
    path: Path
    code: str
    number: str
    doc_type: str
    category_code: str
    title: str = ""
    from_record: bool = False
    issuing_body: str | None = None
    publication_date: date | None = None
    official_url: str | None = None
    status: str = "pending"
    detail: str = ""
    version_id: str | None = None
    pages: int = 0
    nodes: int = 0
    seconds: float = 0.0
    warnings: list[str] = field(default_factory=list)


def canonical_code(raw: str) -> str:
    return unicodedata.normalize("NFC", raw).replace("\u00d0", "\u0110").strip()


def document_number(code: str) -> str:
    """01_2012_TT-BCA -> 01/2012/TT-BCA; 1670_BCA-V28 -> 1670/BCA-V28."""
    code = re.sub(r"^(?:so|số)[_ ]+", "", code, flags=re.IGNORECASE)
    match = _NUMBER.match(code)
    if match:
        return f"{match['no']}/{match['year']}/{match['kind']}"
    match = _NUMBER_NO_YEAR.match(code)
    if match:
        return f"{match['no']}/{match['kind']}"
    return code.replace("_", "/")


def read_record(path: Path) -> dict[str, str]:
    """Parse the 'KEY: value' metadata record some folders ship as .txt."""
    try:
        text = path.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError:
        return {}
    record: dict[str, str] = {}
    for line in text.splitlines():
        key, separator, value = line.partition(":")
        if separator and key.strip().isupper() and value.strip():
            record[unicodedata.normalize("NFC", key.strip())] = value.strip()
    return record


def parse_date(value: str | None) -> date | None:
    match = re.search(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", value or "")
    if not match:
        return None
    try:
        return date(int(match[3]), int(match[2]), int(match[1]))
    except ValueError:
        return None


def filename_title(name: str, label: str, number: str) -> str:
    match = _NAME.match(Path(name).stem)
    raw = (match["title"] if match else Path(name).stem).replace("_", " ")
    raw = re.sub(r"\s+", " ", raw).strip(" .")
    # Names such as "TT-BCA" or "Van ban so 08" say nothing a user could search for.
    if len(raw.split()) < 3:
        return f"{label} số {number}"
    return raw


def content_title(first_page: str) -> str | None:
    """'THÔNG TƯ' + the subject lines that follow it, when the page has that shape."""
    lines = [unicodedata.normalize("NFC", ln).strip() for ln in first_page.splitlines()]
    lines = [ln for ln in lines if ln][:40]
    for index, line in enumerate(lines):
        if not _TYPE_LINE.match(line):
            continue
        subject: list[str] = []
        for follower in lines[index + 1:index + 5]:
            if _STOP_LINE.match(follower) or follower.startswith(("-", "—", "_")):
                break
            subject.append(follower)
        title = " ".join([line.title() if line.isupper() else line, *subject]).strip()
        title = re.sub(r"\s+", " ", title)
        if len(subject) and 15 <= len(title) <= 400:
            return title
    return None


def discover(source: Path, only: set[str], limit: int | None) -> tuple[list[Item], list[str]]:
    notes: list[str] = []
    items: list[Item] = []
    records: dict[tuple[str, str], list[Path]] = defaultdict(list)
    for folder in sorted(p for p in source.iterdir() if p.is_dir()):
        if only and folder.name not in only:
            continue
        category_code, label, doc_type = FOLDERS.get(
            folder.name,
            (re.sub(r"\W+", "_", folder.name).strip("_").upper(),
             folder.name.replace("_", " "), "other"),
        )
        files = sorted(p for p in folder.iterdir() if p.is_file())
        for path in files:
            match = _NAME.match(path.name)
            code = canonical_code(match["code"] if match else path.stem)
            if path.suffix.lower() == ".txt":
                records[(folder.name, code)].append(path)
        for path in files:
            if path.suffix.lower() not in DOC_SUFFIXES:
                continue
            match = _NAME.match(path.name)
            code = canonical_code(match["code"] if match else path.stem)
            items.append(Item(
                folder=folder.name, path=path, code=code, number=document_number(code),
                doc_type=doc_type, category_code=category_code,
                title=filename_title(path.name, label, document_number(code)),
            ))
    per_code: dict[tuple[str, str], int] = defaultdict(int)
    for item in items:
        per_code[(item.folder, item.code)] += 1
    for item in items:
        sidecars = records.get((item.folder, item.code), [])
        if len(sidecars) != 1:
            continue
        if per_code[(item.folder, item.code)] != 1:
            item.warnings.append("METADATA_RECORD_AMBIGUOUS")
            continue
        record = read_record(sidecars[0])
        if record.get("TRÍCH YẾU"):
            item.title = record["TRÍCH YẾU"][:500]
            item.from_record = True
        item.issuing_body = record.get("CƠ QUAN BAN HÀNH", "")[:300] or None
        item.publication_date = parse_date(record.get("NGÀY BAN HÀNH"))
        link = record.get("LINK TRA CỨU")
        if link:
            try:
                item.official_url = validate_source_url(link)[0]
            except ValueError:
                item.warnings.append("OFFICIAL_URL_INVALID")
    items.sort(key=lambda i: (i.folder, i.path.name))
    if limit:
        items = items[:limit]
    return items, notes


async def ensure_categories(
    pool: Any, actor: UUID, remote_allowed: bool, codes: set[str], names: dict[str, str]
) -> tuple[dict[str, UUID], list[str]]:
    created: list[str] = []
    ids: dict[str, UUID] = {}
    for code in sorted(codes):
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT id, deleted_at FROM categories WHERE code = $1", code)
        if row is None:
            made = await create_category(
                pool, actor_id=actor, code=code, name=names[code],
                remote_processing_allowed=remote_allowed,
            )
            ids[code] = UUID(made["id"])
            created.append(code)
        elif row["deleted_at"] is not None:
            # An administrator deleted it on purpose; do not bring it back silently.
            raise RuntimeError(f"CATEGORY_DELETED_BY_ADMIN:{code}")
        else:
            ids[code] = row["id"]
    return ids, created


async def grant_access(pool: Any, actor: UUID, username: str, categories: list[UUID]) -> int:
    async with pool.acquire() as conn, conn.transaction():
        user_id = await conn.fetchval(
            "SELECT id FROM users WHERE lower(username) = lower($1) AND disabled_at IS NULL",
            username,
        )
        if user_id is None:
            return 0
        added = 0
        for category in categories:
            result = await conn.execute(
                """INSERT INTO category_acl (category_id, user_id, can_query, granted_by)
                   VALUES ($1, $2, TRUE, $3) ON CONFLICT DO NOTHING""",
                category, user_id, actor,
            )
            added += int(result.endswith(" 1"))
        if added:
            await append_audit(
                conn, principal_id=actor, action="admin.grant_category_acl",
                target_type="user", target_id=str(user_id),
                metadata={"categories": added, "via": "import_official_corpus"},
            )
        return added


async def run(args: argparse.Namespace) -> dict[str, Any]:
    source = Path(args.source_dir).resolve()
    if not source.is_dir():
        raise SystemExit(f"Source directory not found: {source}")
    items, _ = discover(source, set(args.only or []), args.limit)
    store_value = os.environ.get("EVIDENCE_DOCUMENT_STORE_ROOT")
    store_root = Path(store_value) if args.apply and store_value else None
    if args.apply:
        if not os.environ.get("DATABASE_URL") or store_root is None or not store_root.is_absolute():
            raise SystemExit(
                "--apply needs DATABASE_URL and an absolute EVIDENCE_DOCUMENT_STORE_ROOT"
            )
        store_root.mkdir(parents=True, exist_ok=True)

    pool = await create_pool(os.environ["DATABASE_URL"]) if args.apply else None
    summary: dict[str, Any] = {"mode": "apply" if args.apply else "dry-run"}
    try:
        category_ids: dict[str, UUID] = {}
        curator: UUID | None = None
        reviewer: UUID | None = None
        if pool is not None:
            async with pool.acquire() as conn:
                await apply_migrations(conn)
                admin_id = await conn.fetchval(
                    "SELECT u.id FROM users u JOIN user_roles r ON r.user_id=u.id "
                    "WHERE r.role_code='SYS_ADMIN' AND u.disabled_at IS NULL ORDER BY u.id LIMIT 1"
                )
                curator = await conn.fetchval(
                    "SELECT u.id FROM users u JOIN user_roles r ON r.user_id=u.id "
                    "WHERE r.role_code='CURATOR' AND u.disabled_at IS NULL ORDER BY u.id LIMIT 1"
                )
                reviewer = await conn.fetchval(
                    "SELECT u.id FROM users u JOIN user_roles r ON r.user_id=u.id "
                    "WHERE r.role_code='REVIEWER' AND u.disabled_at IS NULL "
                    "AND u.id IS DISTINCT FROM $1 ORDER BY u.id LIMIT 1", curator,
                )
            if curator is None or (args.approve and reviewer is None):
                raise SystemExit("Need an active CURATOR (and a different REVIEWER for --approve)")
            names = {code: name for code, name, _ in FOLDERS.values()}
            codes = {i.category_code for i in items} | {code for code, _, _ in FOLDERS.values()}
            for code in codes:
                names.setdefault(code, code)
            category_ids, created = await ensure_categories(
                pool, admin_id or uuid4(), not args.no_remote, codes, names,
            )
            summary["categories_created"] = created
            if args.grant_user:
                summary["acl_granted"] = await grant_access(
                    pool, admin_id or uuid4(), args.grant_user, list(category_ids.values()),
                )

        started = time.time()
        for index, item in enumerate(items, 1):
            begun = time.time()
            try:
                upload = item.path.read_bytes()
                converted = await asyncio.to_thread(
                    convert_to_pdf, upload, item.path.name, max_pages=args.max_pages,
                )
                item.warnings.extend(converted.warnings)
                digest = sha256_bytes(converted.pdf)
                if pool is not None:
                    async with pool.acquire() as conn:
                        known = await conn.fetchval(
                            "SELECT id FROM document_versions WHERE original_file_sha256=$1", digest,
                        )
                    if known:
                        item.status, item.version_id = "already_imported", str(known)
                        continue
                prepared = await asyncio.to_thread(
                    prepare_draft, converted.pdf, max_pages=args.max_pages,
                    temporary_root=store_root, isolate=True, timeout_seconds=args.timeout,
                )
                item.pages, item.nodes = len(prepared.pages), len(prepared.nodes)
                if prepared.pages:
                    better = content_title(prepared.pages[0].text)
                    if better and not item.from_record:
                        item.title = better[:500]
                if pool is None:
                    item.status = "would_import"
                    continue
                assert curator is not None and store_root is not None
                created_draft = await persist_draft(
                    prepared, pool=pool, store_root=store_root, title=item.title,
                    doc_type=item.doc_type, original_filename=item.path.name,
                    document_number=item.number, issuing_body=item.issuing_body,
                    publication_date=item.publication_date, official_url=item.official_url,
                    submitted_by=curator,
                    converted=converted if converted.source_format != "pdf" else None,
                )
                item.version_id = str(created_draft.document_version_id)
                item.status = "draft"
                if args.approve:
                    assert reviewer is not None
                    version = created_draft.document_version_id
                    await submit_draft_for_review(pool, version_id=version, curator_id=curator)
                    await approve_document_version(
                        pool, store_root=store_root, max_bytes=args.max_bytes,
                        version_id=version, reviewer_id=reviewer,
                        category_ids=[category_ids[item.category_code]],
                        review_note="Dữ liệu thử nghiệm: duyệt hàng loạt theo quyết định của chủ sở hữu.",
                        resolve_all_tasks=True,
                    )
                    item.status = "approved"
            except Exception as exc:  # report and continue with the next file
                code = str(exc) or type(exc).__name__
                item.status, item.detail = "failed", code[:200]
                if args.approve and item.version_id:
                    item.status = "draft_not_approved"
            finally:
                item.seconds = round(time.time() - begun, 2)
                print(f"[{index}/{len(items)}] {item.status:16} {item.folder}/{item.path.name[:70]}"
                      f" {item.detail}", flush=True)
        summary["seconds"] = round(time.time() - started, 1)
        counts: dict[str, int] = defaultdict(int)
        for item in items:
            counts[item.status] += 1
        summary["files"] = len(items)
        summary["by_status"] = dict(counts)
        summary["by_category"] = {
            code: sum(1 for i in items if i.category_code == code)
            for code in sorted({i.category_code for i in items})
        }
        if args.report:
            Path(args.report).write_text(
                json.dumps({"summary": summary,
                            "items": [{**asdict(i), "path": str(i.path),
                                       "publication_date": str(i.publication_date or "")}
                                      for i in items]}, ensure_ascii=False, indent=1),
                encoding="utf-8",
            )
        return summary
    finally:
        if pool is not None:
            await pool.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--source-dir", default=str(PROJECT_ROOT / "test-data" / "van-ban"))
    parser.add_argument("--apply", action="store_true", help="write to the database and store")
    parser.add_argument("--approve", action="store_true",
                        help="test corpora only: submit and approve as a different REVIEWER")
    parser.add_argument("--grant-user", default="chuyenvien",
                        help="username that receives query access to the categories ('' = none)")
    parser.add_argument("--no-remote", action="store_true",
                        help="create categories with remote AI processing disallowed")
    parser.add_argument("--only", nargs="*", help="limit to these folder names")
    parser.add_argument("--limit", type=int, help="process only the first N files (pilot)")
    # A trusted operator loads books the 200-page upload limit of the web form would refuse.
    parser.add_argument("--max-pages", type=int, default=1000)
    parser.add_argument("--max-bytes", type=int, default=int(
        os.environ.get("EVIDENCE_MAX_UPLOAD_BYTES", str(32 * 1024 * 1024))))
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--report", help="write a JSON report of every file")
    args = parser.parse_args()
    if args.approve and not args.apply:
        parser.error("--approve requires --apply")
    print(json.dumps(asyncio.run(run(args)), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
