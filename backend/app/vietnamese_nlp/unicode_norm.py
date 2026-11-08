"""Versioned Vietnamese normalization.

`text_original` is never mutated by this module.  The functions return derived
texts and an explicit offset map for a future indexer.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

NORMALIZER_REVISION = "vietnamese-tone-v3"


@dataclass(frozen=True)
class NormalizedText:
    original: str
    unicode_nfc: str
    normalized: str
    folded: str
    offsets: tuple[int, ...]


# Deliberately small, reviewable table.  Extend it only with a tested pair.
# "kì/kỳ" is the variant required by the Search v1 acceptance criteria.
_TONE_MAP = {
    "hoà": "hòa",
    "thuý": "thúy",
    "kì": "kỳ",
}
_TONE_RE = re.compile(r"\b(?:" + "|".join(map(re.escape, _TONE_MAP)) + r")\b", re.I)


def unicode_nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def _normalize_tone_spelling(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        source = match.group(0)
        target = _TONE_MAP[source.lower()]
        if source.isupper():
            return target.upper()
        if source[0].isupper():
            target = target[0].upper() + target[1:]
        return target

    return _TONE_RE.sub(replace, text)


def normalize_text(text: str) -> str:
    normalized = _normalize_tone_spelling(unicode_nfc(text))
    return re.sub(r"[ \t]+", " ", normalized).strip()


def fold_text(text: str) -> str:
    """Remove accents while preserving the original character `đ` as `d`."""

    value = normalize_text(text)
    result: list[str] = []
    for char in value:
        if char in "đĐ":
            result.append("d" if char == "đ" else "D")
            continue
        decomposed = unicodedata.normalize("NFD", char)
        result.append("".join(part for part in decomposed if unicodedata.category(part) != "Mn"))
    return "".join(result).casefold()


def canonical_document_number(value: str) -> str:
    """Return a search key without destroying the source number."""

    raw = fold_text(value)
    raw = raw.replace("–", "-").replace("—", "-")
    raw = re.sub(r"\s+", "", raw)
    raw = re.sub(r"-{2,}", "-", raw)
    return raw.strip(".-/")


def normalize_with_offsets(text: str) -> NormalizedText:
    """Return a conservative offset map for derived text.

    The map currently maps each derived character to the nearest original index;
    it is deliberately explicit so a future syllable/word tokenizer cannot
    silently claim an invalid highlight.
    """

    original = text
    normalized = normalize_text(text)
    folded = fold_text(text)
    offsets = tuple(min(i, len(original)) for i in range(len(normalized)))
    return NormalizedText(original, unicode_nfc(text), normalized, folded, offsets)
