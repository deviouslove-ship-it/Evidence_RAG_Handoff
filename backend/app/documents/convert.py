"""Convert TXT, DOCX and legacy DOC uploads into the one source format the app cites: PDF.

The evidence pipeline (text-box extraction, page locators, hash-checked PDF viewer) is
built around immutable PDFs.  Instead of creating a second citation path, a text-bearing
source is rendered into a deterministic PDF with a real text layer.  Same input bytes
always give the same PDF bytes, so duplicate detection by SHA-256 keeps working.  The
original file is kept next to it and its own SHA-256 is recorded.

Everything here is pure Python (no Office, no external converter) so it behaves the same
on a developer machine and on a clean server.
"""

from __future__ import annotations

import hashlib
import io
import re
import struct
import unicodedata
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal

from defusedxml import ElementTree as SafeElementTree

SourceFormat = Literal["pdf", "docx", "doc", "txt"]

PDF_MAGIC: Final = b"%PDF-"
_ZIP_MAGIC: Final = b"PK\x03\x04"
_OLE_MAGIC: Final = bytes.fromhex("D0CF11E0A1B11AE1")
_FONT_DIR: Final = Path(__file__).resolve().parent / "fonts"
_MAX_TEXT_CHARACTERS: Final = 5_000_000
_MAX_XML_BYTES: Final = 96 * 1024 * 1024
_W: Final = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_MC_FALLBACK: Final = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"
_FIXED_DATE: Final = datetime(2000, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class Paragraph:
    text: str
    align: Literal["L", "C", "R"] = "L"
    bold: bool = False


@dataclass(frozen=True)
class ConvertedSource:
    """A PDF ready for the existing intake, plus where it came from."""

    pdf: bytes
    source_format: SourceFormat
    source_sha256: str
    source_bytes: bytes | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)


def detect_format(content: bytes, filename: str | None) -> SourceFormat:
    """Decide the format from the bytes; the extension only breaks ties for plain text."""
    if content.startswith(PDF_MAGIC):
        return "pdf"
    if content.startswith(_ZIP_MAGIC):
        return "docx"
    if content.startswith(_OLE_MAGIC):
        return "doc"
    extension = Path(filename or "").suffix.lower()
    if extension == ".txt":
        return "txt"
    if extension in {"", ".pdf"}:
        raise ValueError("INVALID_PDF_MAGIC")
    raise ValueError("UNSUPPORTED_FILE_TYPE")


def convert_to_pdf(
    content: bytes, filename: str | None, *, max_pages: int
) -> ConvertedSource:
    """Return a PDF for any supported upload.  PDFs pass through untouched."""
    source_format = detect_format(content, filename)
    digest = hashlib.sha256(content).hexdigest()
    if source_format == "pdf":
        return ConvertedSource(content, "pdf", digest)
    warnings: list[str] = []
    try:
        if source_format == "txt":
            paragraphs = text_paragraphs(decode_text(content))
        elif source_format == "docx":
            paragraphs = docx_paragraphs(content, warnings)
        else:
            paragraphs = doc_paragraphs(content)
    except ValueError:
        raise
    except Exception as exc:  # malformed input must become a clean 422, never a 500
        raise ValueError("DOCUMENT_CONVERT_FAILED") from exc
    paragraphs = _clean(paragraphs)
    if sum(len(item.text) for item in paragraphs) > _MAX_TEXT_CHARACTERS:
        raise ValueError("PDF_RESOURCE_LIMIT_EXCEEDED")
    if not any(any(char.isalnum() for char in item.text) for item in paragraphs):
        raise ValueError("DOCUMENT_TEXT_EMPTY")
    pdf = render_pdf(paragraphs, max_pages=max_pages)
    return ConvertedSource(pdf, source_format, digest, content, tuple(warnings))


# --------------------------------------------------------------------------- TXT


def decode_text(content: bytes) -> str:
    if b"\x00" in content and not content.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise ValueError("TXT_ENCODING_UNSUPPORTED")
    if content.startswith((b"\xff\xfe", b"\xfe\xff")):
        return content.decode("utf-16")
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    try:  # Vietnamese Windows code page, the usual non-Unicode fallback
        return content.decode("cp1258")
    except UnicodeDecodeError as exc:
        raise ValueError("TXT_ENCODING_UNSUPPORTED") from exc


def text_paragraphs(text: str) -> list[Paragraph]:
    return [Paragraph(line) for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]


# -------------------------------------------------------------------------- DOCX


def docx_paragraphs(content: bytes, warnings: list[str]) -> list[Paragraph]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise ValueError("UNSUPPORTED_FILE_TYPE") from exc
    with archive:
        try:
            info = archive.getinfo("word/document.xml")
        except KeyError as exc:
            raise ValueError("UNSUPPORTED_FILE_TYPE") from exc
        if info.flag_bits & 0x1:
            raise ValueError("DOCUMENT_ENCRYPTED")
        if info.file_size > _MAX_XML_BYTES:
            raise ValueError("PDF_RESOURCE_LIMIT_EXCEEDED")
        data = archive.read(info)
        if any(name.startswith("word/media/") for name in archive.namelist()):
            warnings.append("DOCX_IMAGES_NOT_RENDERED")
    root = SafeElementTree.fromstring(data)
    body = root.find(f"{_W}body")
    if body is None:
        raise ValueError("DOCUMENT_CONVERT_FAILED")
    return list(_walk_blocks(body))


def _walk_blocks(parent: object) -> list[Paragraph]:
    result: list[Paragraph] = []
    for child in parent:  # type: ignore[attr-defined]
        tag = child.tag
        if tag == f"{_W}p":
            result.extend(_paragraph(child))
        elif tag == f"{_W}tbl":
            for row in child.findall(f"{_W}tr"):
                for cell in row.findall(f"{_W}tc"):
                    result.extend(_walk_blocks(cell))
        elif tag in {f"{_W}sdt", f"{_W}sdtContent", f"{_W}customXml"}:
            result.extend(_walk_blocks(child))
    return result


def _paragraph(element: object) -> list[Paragraph]:
    pieces: list[str] = []
    extra: list[Paragraph] = []
    bold_runs: list[bool] = []
    _collect_runs(element, pieces, extra, bold_runs)
    properties = element.find(f"{_W}pPr")  # type: ignore[attr-defined]
    align: Literal["L", "C", "R"] = "L"
    if properties is not None:
        justification = properties.find(f"{_W}jc")
        value = justification.get(f"{_W}val") if justification is not None else None
        if value == "center":
            align = "C"
        elif value in {"right", "end"}:
            align = "R"
    text = "".join(pieces)
    host = [Paragraph(line, align, bool(bold_runs) and all(bold_runs))
            for line in text.split("\n")]
    return host + extra


def _collect_runs(
    element: object, pieces: list[str], extra: list[Paragraph], bold_runs: list[bool]
) -> None:
    for child in element:  # type: ignore[attr-defined]
        tag = child.tag
        if tag == _MC_FALLBACK:
            continue  # the same content already appears in mc:Choice
        if tag == f"{_W}txbxContent":
            extra.extend(_walk_blocks(child))
            continue
        if tag == f"{_W}t":
            pieces.append(child.text or "")
        elif tag == f"{_W}tab":
            pieces.append("\t")
        elif tag in {f"{_W}br", f"{_W}cr"}:
            pieces.append("\n")
        elif tag == f"{_W}noBreakHyphen":
            pieces.append("-")
        elif tag == f"{_W}r":
            run_properties = child.find(f"{_W}rPr")
            has_text = any(
                item.tag in {f"{_W}t", f"{_W}tab"} and (item.text or item.tag == f"{_W}tab")
                for item in child
            )
            if has_text:
                bold_runs.append(_is_bold(run_properties))
        if tag != f"{_W}pPr":
            _collect_runs(child, pieces, extra, bold_runs)


def _is_bold(run_properties: object) -> bool:
    if run_properties is None:
        return False
    bold = run_properties.find(f"{_W}b")  # type: ignore[attr-defined]
    if bold is None:
        return False
    return bold.get(f"{_W}val") not in {"0", "false", "off"}


# --------------------------------------------------------------------------- DOC


def doc_paragraphs(content: bytes) -> list[Paragraph]:
    """Read the main-story text of a Word 97-2003 file through its piece table."""
    import olefile

    try:
        ole = olefile.OleFileIO(io.BytesIO(content))
    except OSError as exc:
        raise ValueError("UNSUPPORTED_FILE_TYPE") from exc
    with ole:
        if ole.exists("EncryptedPackage"):
            raise ValueError("DOCUMENT_ENCRYPTED")
        if not ole.exists("WordDocument"):
            raise ValueError("UNSUPPORTED_FILE_TYPE")
        word = ole.openstream("WordDocument").read()
        if len(word) < 0x1A6 or struct.unpack_from("<H", word, 0)[0] != 0xA5EC:
            raise ValueError("UNSUPPORTED_FILE_TYPE")
        flags = struct.unpack_from("<H", word, 0x0A)[0]
        if flags & 0x0100:
            raise ValueError("DOCUMENT_ENCRYPTED")
        table_name = "1Table" if flags & 0x0200 else "0Table"
        if not ole.exists(table_name):
            raise ValueError("DOCUMENT_CONVERT_FAILED")
        table = ole.openstream(table_name).read()
    csw = struct.unpack_from("<H", word, 32)[0]
    position = 34 + csw * 2
    cslw = struct.unpack_from("<H", word, position)[0]
    long_start = position + 2
    characters = struct.unpack_from("<I", word, long_start + 12)[0]
    pair_count_at = long_start + cslw * 4
    pair_count = struct.unpack_from("<H", word, pair_count_at)[0]
    if pair_count < 34:
        raise ValueError("UNSUPPORTED_FILE_TYPE")
    clx_offset, clx_length = struct.unpack_from("<II", word, pair_count_at + 2 + 33 * 8)
    if characters > _MAX_TEXT_CHARACTERS * 4:
        raise ValueError("PDF_RESOURCE_LIMIT_EXCEEDED")
    raw = _piece_table_text(word, table[clx_offset:clx_offset + clx_length], characters)
    return [Paragraph(line) for line in _doc_clean(raw).split("\n")]


def _piece_table_text(word: bytes, clx: bytes, limit: int) -> str:
    index = 0
    while index < len(clx):
        kind = clx[index]
        if kind == 1:
            index += 3 + struct.unpack_from("<H", clx, index + 1)[0]
        elif kind == 2:
            length = struct.unpack_from("<I", clx, index + 1)[0]
            plc = clx[index + 5:index + 5 + length]
            break
        else:
            raise ValueError("DOCUMENT_CONVERT_FAILED")
    else:
        raise ValueError("DOCUMENT_CONVERT_FAILED")
    pieces = (len(plc) - 4) // 12
    positions = struct.unpack_from(f"<{pieces + 1}I", plc, 0)
    parts: list[str] = []
    taken = 0
    for piece in range(pieces):
        raw_offset = struct.unpack_from("<I", plc, 4 * (pieces + 1) + 8 * piece + 2)[0]
        count = min(positions[piece + 1] - positions[piece], limit - taken)
        if count <= 0:
            break
        if raw_offset & 0x40000000:  # 8-bit text stored as Windows-1252
            start = (raw_offset & 0x3FFFFFFF) // 2
            parts.append(word[start:start + count].decode("cp1252", errors="replace"))
        else:
            start = raw_offset & 0x3FFFFFFF
            parts.append(word[start:start + 2 * count].decode("utf-16-le", errors="replace"))
        taken += count
    return "".join(parts)


def _doc_clean(raw: str) -> str:
    out: list[str] = []
    in_instruction: list[bool] = []
    for char in raw:
        if char == "\x13":  # field begin: the code part is not document text
            in_instruction.append(True)
        elif char == "\x14":
            if in_instruction:
                in_instruction[-1] = False
        elif char == "\x15":
            if in_instruction:
                in_instruction.pop()
        elif not any(in_instruction):
            out.append(char)
    text = "".join(out)
    translate = {"\r": "\n", "\x07": "\n", "\x0b": "\n", "\x0c": "\n", "\x1e": "-",
                 "\x1f": "", "\xa0": " "}
    return "".join(translate.get(char, char) for char in text)


# ------------------------------------------------------------------------ common


def _clean(paragraphs: list[Paragraph]) -> list[Paragraph]:
    cleaned: list[Paragraph] = []
    blank = 0
    for item in paragraphs:
        text = unicodedata.normalize("NFC", item.text)
        text = text.replace("\t", "    ").replace("\xa0", " ")
        text = "".join(
            char for char in text
            if char == " " or unicodedata.category(char) not in {"Cc", "Cf", "Cs", "Co", "Cn"}
        ).rstrip()
        if not text.strip():
            blank += 1
            if blank == 1 and cleaned:
                cleaned.append(Paragraph("", item.align))
            continue
        blank = 0
        cleaned.append(Paragraph(text, item.align, item.bold))
    while cleaned and not cleaned[-1].text:
        cleaned.pop()
    return cleaned


_MARGIN_MM: Final = 20.0
_LINE_MM: Final = 6.0
_PARAGRAPH_GAP_MM: Final = 1.5


def render_pdf(paragraphs: list[Paragraph], *, max_pages: int) -> bytes:
    """Deterministic A4 PDF.  Every paragraph starts on a new line so the legal tree
    parser sees Điều/Khoản/điểm headings exactly where the author put them."""
    import logging

    from fpdf import FPDF

    for noisy in ("fontTools", "fpdf"):  # per-glyph subset chatter on every conversion
        logging.getLogger(noisy).setLevel(logging.ERROR)
    pdf = FPDF(format="A4", unit="mm")
    pdf.set_creation_date(_FIXED_DATE)
    pdf.set_producer("evidence-rag-converter")
    pdf.set_margins(_MARGIN_MM, _MARGIN_MM, _MARGIN_MM)
    pdf.set_auto_page_break(auto=True, margin=_MARGIN_MM)
    pdf.add_font("Tinos", "", str(_FONT_DIR / "Tinos-Regular.ttf"))
    pdf.add_font("Tinos", "B", str(_FONT_DIR / "Tinos-Bold.ttf"))
    pdf.add_page()
    for item in paragraphs:
        if not item.text:
            pdf.ln(_LINE_MM / 2)
            continue
        pdf.set_font("Tinos", "B" if item.bold else "", 12)
        pdf.multi_cell(0, _LINE_MM, item.text, align=item.align,
                       new_x="LMARGIN", new_y="NEXT")
        pdf.ln(_PARAGRAPH_GAP_MM)
        if pdf.page > max_pages:
            raise ValueError("PDF_PAGE_LIMIT_EXCEEDED")
    return bytes(pdf.output())


_SAFE_NAME = re.compile(r"[^0-9A-Za-z._-]+")


def source_file_name(source_sha256: str, source_format: SourceFormat) -> str:
    return f"{source_sha256}.{_SAFE_NAME.sub('', source_format)}"
