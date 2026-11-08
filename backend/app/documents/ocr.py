"""Optional, local OCR adapter for PDF pages without a usable text layer.

The scan itself is never changed: OCR text is derived data, stored next to the page and
kept out of evidence until a reviewer confirms the page against the scan.  Besides the
text, every page gets diagnostics the reviewer sees:

* word confidences from Tesseract (mean, share below ``LOW_CONFIDENCE``, the weakest
  words) so misread syllables ("bồ sung", "B6", "1Š") are easy to find;
* tokens that cannot be Vietnamese (letters outside the Vietnamese alphabet, a digit
  glued to a letter, lowercase words without a vowel);
* how much of the page is ink compared with the words read, which reveals a page where
  OCR missed content (a table, a stamp, a faint scan);
* orientation: when a page reads badly, Tesseract's orientation detection is asked and a
  rotated page is read again; the better reading is kept and the rotation is recorded.

Nothing here corrects the text.  Executable, languages and data folder come from the
deployment configuration (``EVIDENCE_OCR_EXECUTABLE``, ``EVIDENCE_OCR_LANGUAGES``,
``EVIDENCE_OCR_TESSDATA``); OCR is off when no executable is configured.
"""

from __future__ import annotations

import io
import os
import re
import subprocess
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

LOW_CONFIDENCE = 60.0
LOW_MEAN_CONFIDENCE = 80.0
LOW_SHARE = 0.10
RETRY_MEAN_CONFIDENCE = 70.0
MIN_WORDS = 30
INK_PAGE_SHARE = 0.03
_VIETNAMESE_LETTERS = frozenset(
    "abcdefghijklmnopqrstuvwxyzđ"
    "àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵ"
)
_VOWELS = frozenset("aeiouyàáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵ")
_TOKEN = re.compile(r"[^\s.,;:!?()\[\]{}\"“”'‘’/\\|…–—\-+*=<>%]+")
# "QH15", "NĐ", "BCA" are abbreviations; one letter glued to a digit ("B6") is usually a
# misread syllable ("Bổ") and is shown to the reviewer.
_ABBREVIATION = re.compile(r"^(?:[A-ZĐ]{2,6}\d{0,3}|[A-ZĐ])$")
# Symbols that do not occur in Vietnamese legal text but are typical OCR misreads
# (§ for "g"/"8", „ for "“", ⁄ for "/").
_GARBAGE = frozenset("§„¤¦¨©®°±¶¸¹²³¼½¾×÷⁄‰†‡¬")
_POINT_LINE = re.compile(r"^\s*([a-zđ])\)\s")
_DIGIT_POINT_LINE = re.compile(r"^\s*([0-9])\)\s")


class OcrEngine(Protocol):
    def recognize_png(self, image: bytes) -> str: ...


class OcrError(RuntimeError):
    """A coded OCR failure; caller must keep the page out of verified evidence."""


@dataclass(frozen=True)
class OcrResult:
    text: str
    diagnostics: dict[str, Any] = field(default_factory=dict)


def suspect_tokens(text: str, limit: int = 20) -> list[str]:
    """Tokens that cannot be Vietnamese words as written (shown to the reviewer)."""

    found: list[str] = []
    for raw in _TOKEN.findall(unicodedata.normalize("NFC", text)):
        token = raw.strip("_")
        if not token or token.isdigit() or _ABBREVIATION.match(token):
            continue
        lower = token.casefold()
        letters = [char for char in lower if char.isalpha()]
        has_digit = any(char.isdigit() for char in token)
        foreign = any(char not in _VIETNAMESE_LETTERS for char in letters)
        mixed = has_digit and bool(letters) and not re.fullmatch(r"\d+[a-zđ]?", lower)
        voiceless = (token == lower and len(letters) >= 2 and not has_digit
                     and not any(char in _VOWELS for char in letters))
        garbage = any(char in _GARBAGE for char in token)
        if (foreign or mixed or voiceless or garbage) and token not in found:
            found.append(token)
            if len(found) >= limit:
                break
    return found


def marker_anomalies(text: str, limit: int = 10) -> list[str]:
    """Lines whose point marker looks misread: "1)" inside an "a) b) ... k)" list is
    usually "l)", "0)" is "o)".  The parser would otherwise make them a new Khoản."""

    found: list[str] = []
    in_points = False
    for line in text.splitlines():
        if _POINT_LINE.match(line):
            in_points = True
            continue
        digit = _DIGIT_POINT_LINE.match(line)
        if digit and in_points:
            found.append(line.strip()[:60])
            if len(found) >= limit:
                break
        elif re.match(r"^\s*\d+\.\s", line) or re.match(r"^\s*Điều\s+\d+", line):
            in_points = False
    return found


def diagnose(text: str, words: list[tuple[str, float]], *, ink_share: float | None,
             rotation: int = 0) -> dict[str, Any]:
    confidences = [conf for _, conf in words if conf >= 0]
    mean = round(sum(confidences) / len(confidences), 1) if confidences else 0.0
    low = [(word, conf) for word, conf in words if 0 <= conf < LOW_CONFIDENCE]
    share = round(len(low) / len(confidences), 3) if confidences else 0.0
    suspects = suspect_tokens(text)
    markers = marker_anomalies(text)
    flags: list[str] = []
    if not text.strip():
        flags.append("NO_TEXT")
    if confidences and (mean < LOW_MEAN_CONFIDENCE or share > LOW_SHARE):
        flags.append("LOW_CONFIDENCE")
    if ink_share is not None and ink_share >= INK_PAGE_SHARE and len(confidences) < MIN_WORDS:
        flags.append("LITTLE_TEXT_FOR_INK")
    if suspects:
        flags.append("SUSPECT_CHARACTERS")
    if markers:
        flags.append("SUSPECT_POINT_MARKERS")
    if rotation:
        flags.append("ROTATED")
    return {
        "engine": "tesseract", "words": len(confidences), "mean_confidence": mean,
        "low_confidence_share": share,
        "low_confidence_words": [word for word, _ in sorted(low, key=lambda item: item[1])][:15],
        "suspect_tokens": suspects, "suspect_markers": markers,
        "ink_share": ink_share, "rotation": rotation,
        "flags": flags,
    }


def ink_share(image: bytes) -> float | None:
    """Share of dark pixels of a grayscale page (None when Pillow is unavailable)."""

    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - Pillow ships with the OCR option
        return None
    with Image.open(io.BytesIO(image)) as picture:
        gray = picture.convert("L")
        gray.thumbnail((800, 800))
        histogram = gray.histogram()
    total = sum(histogram) or 1
    # Ink is what is clearly darker than the page's own background (faded scans have a
    # grey background and grey text, so a fixed threshold would see no ink at all).
    running, background = 0, 255
    for level in range(255, -1, -1):
        running += histogram[level]
        if running >= total * 0.5:
            background = level
            break
    threshold = max(0, background - 25)
    return float(round(sum(histogram[:threshold]) / total, 4))


def parse_tsv(tsv: str) -> tuple[str, list[tuple[str, float]]]:
    """Text in reading order (one line per Tesseract line) and word confidences."""

    lines: dict[tuple[int, int, int, int], list[str]] = {}
    order: list[tuple[int, int, int, int]] = []
    words: list[tuple[str, float]] = []
    for row in tsv.splitlines()[1:]:
        parts = row.split("\t")
        if len(parts) != 12 or parts[0] != "5":
            continue
        word = parts[11].strip()
        if not word:
            continue
        key = (int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4]))
        if key not in lines:
            lines[key] = []
            order.append(key)
        lines[key].append(word)
        try:
            words.append((word, float(parts[10])))
        except ValueError:
            words.append((word, -1.0))
    text_lines: list[str] = []
    previous: tuple[int, int, int, int] | None = None
    for key in order:
        if previous is not None and key[:3] != previous[:3] and text_lines:
            text_lines.append("")  # paragraph break, as Tesseract's text output does
        text_lines.append(" ".join(lines[key]))
        previous = key
    text = unicodedata.normalize("NFC", "\n".join(text_lines)).strip()
    return text, words


@dataclass(frozen=True)
class TesseractOcr:
    executable: Path
    languages: str = "vie+eng"
    timeout_seconds: int = 60
    tessdata: Path | None = None

    def _run(self, image: bytes, *arguments: str) -> str:
        if not self.executable.is_absolute() or not self.executable.is_file():
            raise OcrError("OCR_RUNTIME_NOT_CONFIGURED")
        command = [str(self.executable), "stdin", "stdout"]
        if self.tessdata is not None:
            command += ["--tessdata-dir", str(self.tessdata)]
        try:
            result = subprocess.run(
                [*command, *arguments], input=image, capture_output=True, check=False,
                timeout=self.timeout_seconds,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except subprocess.TimeoutExpired as exc:
            raise OcrError("OCR_TIMEOUT") from exc
        except OSError as exc:
            raise OcrError("OCR_EXECUTION_FAILED") from exc
        if result.returncode != 0:
            raise OcrError("OCR_EXECUTION_FAILED")
        return result.stdout.decode("utf-8", errors="replace")

    def _read(self, image: bytes) -> tuple[str, list[tuple[str, float]]]:
        return parse_tsv(self._run(image, "-l", self.languages, "--psm", "3", "tsv"))

    def _orientation(self, image: bytes) -> int:
        try:
            output = self._run(image, "--psm", "0")
        except OcrError:
            return 0  # orientation data missing: keep the page as it is
        rotate = re.search(r"Rotate:\s*(\d+)", output)
        confidence = re.search(r"Orientation confidence:\s*([\d.]+)", output)
        if not rotate or not confidence or float(confidence.group(1)) < 2.0:
            return 0
        value = int(rotate.group(1)) % 360
        return value if value in (90, 180, 270) else 0

    def recognize(self, image: bytes) -> OcrResult:
        text, words = self._read(image)
        rotation = 0
        mean = _mean(words)
        if len(words) < MIN_WORDS or mean < RETRY_MEAN_CONFIDENCE:
            angle = self._orientation(image)
            if angle:
                rotated = _rotate(image, angle)
                if rotated is not None:
                    text_r, words_r = self._read(rotated)
                    if _mean(words_r) > mean and len(words_r) >= len(words) * 0.8:
                        text, words, rotation = text_r, words_r, angle
        return OcrResult(text, diagnose(text, words, ink_share=ink_share(image),
                                        rotation=rotation)
                         | {"languages": self.languages})

    def recognize_png(self, image: bytes) -> str:
        return self.recognize(image).text


def _mean(words: list[tuple[str, float]]) -> float:
    values = [conf for _, conf in words if conf >= 0]
    return sum(values) / len(values) if values else 0.0


def _rotate(image: bytes, angle: int) -> bytes | None:
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover
        return None
    with Image.open(io.BytesIO(image)) as picture:
        # Tesseract reports the clockwise rotation that makes the page upright.
        upright = picture.rotate(-angle, expand=True)
        output = io.BytesIO()
        upright.save(output, format="PNG")
    return output.getvalue()


def configured_ocr_engine() -> TesseractOcr | None:
    """Enable OCR only when its external executable is configured explicitly."""
    executable = os.getenv("EVIDENCE_OCR_EXECUTABLE")
    if not executable:
        return None
    tessdata = os.getenv("EVIDENCE_OCR_TESSDATA")
    try:
        timeout = int(os.getenv("EVIDENCE_OCR_PAGE_TIMEOUT_SECONDS", "60"))
    except ValueError:
        timeout = 60
    return TesseractOcr(
        executable=Path(executable),
        languages=os.getenv("EVIDENCE_OCR_LANGUAGES", "vie+eng"),
        timeout_seconds=min(max(timeout, 5), 300),
        tessdata=Path(tessdata) if tessdata else None,
    )
