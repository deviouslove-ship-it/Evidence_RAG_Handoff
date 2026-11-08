"""OCR adapter diagnostics, OCR-aware parsing and per-page reviewer confirmation.

Text is HƯ CẤU; the PostgreSQL test runs in a disposable schema.
"""

from __future__ import annotations

import os
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import pypdfium2 as pdfium
import pytest

from app.admin_services import create_category, create_or_update_user
from app.documents.draft import PreparedDraft, persist_draft
from app.documents.native_pdf import ExtractedPage
from app.documents.ocr import (
    TesseractOcr,
    diagnose,
    marker_anomalies,
    parse_tsv,
    suspect_tokens,
)
from app.documents.review import (
    ReviewError,
    approve_document_version,
    list_review_tasks,
    resolve_review_task,
    submit_draft_for_review,
)
from app.documents.tree_parser import parse_legal_tree
from app.migrations.runner import apply_migrations

TSV_HEADER = ("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight"
              "\tconf\ttext")


def _tsv(lines: list[list[tuple[str, float]]]) -> str:
    rows = [TSV_HEADER]
    for line_index, words in enumerate(lines, 1):
        for word_index, (word, conf) in enumerate(words, 1):
            rows.append(f"5\t1\t1\t1\t{line_index}\t{word_index}\t0\t0\t1\t1\t{conf}\t{word}")
    return "\n".join(rows)


def test_tsv_keeps_reading_order_and_confidences() -> None:
    text, words = parse_tsv(_tsv([[("Điều", 96), ("1.", 95), ("Phạm", 94), ("vi", 97)],
                                  [("1.", 90), ("Nội", 40), ("dung", 91)]]))
    assert text == "Điều 1. Phạm vi\n1. Nội dung"
    assert ("Nội", 40.0) in words


def test_suspect_tokens_and_point_markers_are_reported_not_fixed() -> None:
    page = "1. B6 sung khoản 3 ngày 1Š tháng 11;\nk) Buộc nộp;\n1) Buộc chấm dứt; bd sung § 5"
    assert {"B6", "1Š", "bd", "§"} <= set(suspect_tokens(page))
    assert "QH15" not in suspect_tokens("Luật số 63/2025/QH15 và NĐ-CP")
    assert marker_anomalies(page) == ["1) Buộc chấm dứt; bd sung § 5"]
    found = diagnose(page, [("B6", 30.0), ("sung", 95.0)], ink_share=0.05)
    assert {"SUSPECT_CHARACTERS", "SUSPECT_POINT_MARKERS", "LOW_CONFIDENCE"} <= set(found["flags"])
    assert "LITTLE_TEXT_FOR_INK" in found["flags"]  # inked page, 2 words read
    assert diagnose("", [], ink_share=0.0)["flags"] == ["NO_TEXT"]


def test_rotated_page_is_read_again_upright(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    from PIL import Image

    exe = tmp_path / "tesseract.exe"
    exe.write_bytes(b"")
    engine = TesseractOcr(exe)
    upright = _tsv([[("Điều", 96), ("1.", 96), ("Phạm", 95), ("vi", 95)]] * 10)
    sideways = _tsv([[("~~", 20), ("ii", 15)]])
    calls: list[tuple[str, ...]] = []

    def run(self: TesseractOcr, image: bytes, *arguments: str) -> str:
        calls.append(arguments)
        if arguments[-2:] == ("--psm", "0"):
            return "Rotate: 90\nOrientation confidence: 9.1\n"
        with Image.open(BytesIO(image)) as picture:  # the retry gets the turned image
            return upright if picture.size == (20, 10) else sideways

    monkeypatch.setattr(TesseractOcr, "_run", run)
    buffer = BytesIO()
    Image.new("L", (10, 20), 255).save(buffer, format="PNG")
    result = engine.recognize(buffer.getvalue())
    assert result.diagnostics["rotation"] == 90 and "ROTATED" in result.diagnostics["flags"]
    assert result.text.startswith("Điều 1. Phạm vi")
    assert ("--psm", "0") in calls


def test_wrapped_reference_line_is_not_a_new_article() -> None:
    text = ("Điều 1. Sửa đổi\n2. Thời hạn\nb) Đối với biện pháp quy định tại điểm b khoản 2\n"
            "Điều 3 của Nghị định này, thời hạn là 30 ngày.\nĐiều 2 Hiệu lực thi hành\n"
            "Nghị định này có hiệu lực.")
    nodes = parse_legal_tree([ExtractedPage(1, 595, 842, 0, text, (), "local_ocr",
                                            "needs_review")])
    articles = [node.label_original for node in nodes if node.node_type == "article"]
    assert articles == ["Điều 1. Sửa đổi", "Điều 2 Hiệu lực thi hành"]
    point = next(node for node in nodes if node.node_type == "point")
    assert "Điều 3 của Nghị định này" in point.text_original


# ------------------------------------------------------------------ PostgreSQL
@pytest.fixture
async def ocr_pool():
    dsn = os.getenv("EVIDENCE_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Disposable PostgreSQL not configured")
    schema = "test_ocr_" + uuid4().hex
    connection = await asyncpg.connect(dsn)
    pool = None
    try:
        await connection.execute(f'CREATE SCHEMA "{schema}"')
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=4,
                                         server_settings={"search_path": schema + ",public"})
        async with pool.acquire() as conn:
            await apply_migrations(conn)
        yield pool
    finally:
        if pool is not None:
            await pool.close()
        await connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await connection.close()


async def _user(pool, name: str, roles: list[str]) -> UUID:
    row = await create_or_update_user(
        pool, actor_id=uuid4(), username=name, display_name=name,
        password="OcrPassword!2026", roles=roles, category_ids=[],
        must_change_password=False,
    )
    return UUID(row["id"])


def _blank_pdf(pages: int) -> bytes:
    output = BytesIO()
    document = pdfium.PdfDocument.new()
    for _ in range(pages):
        document.new_page(595, 842).close()
    document.save(output)
    document.close()
    return output.getvalue()


async def test_ocr_pages_need_page_by_page_confirmation(ocr_pool, tmp_path: Path) -> None:
    curator = await _user(ocr_pool, "curator", ["CURATOR"])
    reviewer = await _user(ocr_pool, "reviewer", ["REVIEWER"])
    category = await create_category(ocr_pool, actor_id=curator, code="OCR", name="OCR")
    content = _blank_pdf(2)
    page_one = "Số: 7/2030/NĐ-CP\nĐiều 1. Phạm vi HƯ CẤU\n1. Nội dung khoản một."
    diagnostics = diagnose(page_one, [("Số:", 95.0)], ink_share=0.04)
    pages = [
        ExtractedPage(1, 595, 842, 0, page_one, (), "local_ocr", "needs_review",
                      ocr_diagnostics=diagnostics),
        # A seal/signature page the OCR could not read.
        ExtractedPage(2, 595, 842, 0, "", (), "native_text", "needs_ocr", "OCR_EMPTY",
                      ocr_diagnostics=diagnose("", [], ink_share=0.01)),
    ]
    prepared = PreparedDraft(content, sha256(content).hexdigest(), pages,
                             parse_legal_tree(pages))
    draft = await persist_draft(
        prepared, pool=ocr_pool, store_root=tmp_path, title="Nghị định HƯ CẤU",
        doc_type="decree", original_filename="scan.pdf", document_number="7/2030/NĐ-CP",
        submitted_by=curator,
    )
    await submit_draft_for_review(ocr_pool, version_id=draft.document_version_id,
                                  curator_id=curator)
    tasks = await list_review_tasks(ocr_pool, version_id=draft.document_version_id,
                                    status_filter="open")
    page_tasks = [task for task in tasks if task["page"]]
    assert sorted(task["page"]["page_number"] for task in page_tasks) == [1, 2]
    first = next(task for task in page_tasks if task["page"]["page_number"] == 1)
    assert first["page"]["extraction_method"] == "local_ocr"
    assert first["page"]["text"] == page_one and first["page"]["ocr_diagnostics"]["words"] == 1
    assert not any(task["reason"] == "document_number_not_in_ocr_text" for task in tasks)

    # A bulk approval never confirms OCR text: the page tasks stay open.
    with pytest.raises(ReviewError, match="OPEN_REVIEW_TASKS_REMAIN"):
        await approve_document_version(
            ocr_pool, store_root=tmp_path, max_bytes=len(content) + 1,
            version_id=draft.document_version_id, reviewer_id=reviewer,
            category_ids=[UUID(category["id"])], review_note="Bulk", resolve_all_tasks=True)
    async with ocr_pool.acquire() as conn:
        assert await conn.fetchval(
            "SELECT count(*) FROM source_pages WHERE document_version_id=$1 "
            "AND text_quality='usable'", draft.document_version_id) == 0
    for task in page_tasks:
        await resolve_review_task(ocr_pool, task_id=UUID(task["id"]), reviewer_id=reviewer,
                                  resolution_note="Đã đối chiếu trang với bản scan.")
    result = await approve_document_version(
        ocr_pool, store_root=tmp_path, max_bytes=len(content) + 1,
        version_id=draft.document_version_id, reviewer_id=reviewer,
        category_ids=[UUID(category["id"])], review_note="Checked", resolve_all_tasks=True)
    assert result["status"] == "approved"
    async with ocr_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT page_number, extraction_method, text_quality, reviewed_by FROM source_pages "
            "WHERE document_version_id=$1 ORDER BY page_number", draft.document_version_id)
        stored = await conn.fetchval(
            "SELECT original_file_sha256 FROM document_versions WHERE id=$1",
            draft.document_version_id)
        audits = await conn.fetchval(
            "SELECT count(*) FROM audit_events WHERE action='document.confirm_page_text'")
    assert [(row["extraction_method"], row["text_quality"]) for row in rows] == [
        ("local_ocr", "usable"), ("native_text", "usable")]
    assert all(row["reviewed_by"] == reviewer for row in rows)
    assert stored == sha256(content).hexdigest()  # the scan itself is the stored original
    assert audits == 2


async def test_declared_number_missing_from_ocr_text_opens_a_task(ocr_pool, tmp_path: Path) -> None:
    curator = await _user(ocr_pool, "curator2", ["CURATOR"])
    content = _blank_pdf(1)
    text = "Số: 25/2030/NĐ-CP\nĐiều 1. Phạm vi HƯ CẤU"  # OCR read 9 as 2
    pages = [ExtractedPage(1, 595, 842, 0, text, (), "local_ocr", "needs_review")]
    draft = await persist_draft(
        PreparedDraft(content, sha256(content).hexdigest(), pages, parse_legal_tree(pages)),
        pool=ocr_pool, store_root=tmp_path, title="HƯ CẤU", doc_type="decree",
        original_filename="scan.pdf", document_number="95/2030/NĐ-CP", submitted_by=curator)
    tasks = await list_review_tasks(ocr_pool, version_id=draft.document_version_id)
    assert any(task["reason"] == "document_number_not_in_ocr_text" and task["risk"] == "high"
               for task in tasks)
