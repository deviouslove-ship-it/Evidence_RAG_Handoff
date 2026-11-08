"""Code checks for every point an AI writes (design §7).

``check_point`` (facts layer):

* every cited evidence id belongs to the evidence given to the model;
* every number, date, document number and Điều/Khoản/Điểm reference written outside
  quotation marks appears in the cited evidence;
* no business conclusion ("phải xử lý", "đủ điều kiện", "quyết định", ...) outside a
  quotation.

A point that cites unknown evidence or concludes is dropped; a point whose facts are not
all found is kept but marked "chưa kiểm chứng".

``verify_claim`` adds the layers a valid evidence id cannot prove on its own:

* quoted text must be a verbatim slice of the cited evidence;
* support: the claim's own words must come from the cited text (a claim about fire
  safety citing an alcohol-test clause has almost no words in common with it);
* relevance: a claim that names neither the question's subject nor its aspect must be
  well supported by evidence that was selected for the question;
* aspect: a claim that states a penalty, deadline, authority, condition or effectivity
  needs a clause that regulates that aspect;
* polarity: negation, exceptions, conditions and obligation/permission in the closest
  source sentence must not be lost or reversed;
* effectivity: "còn/hết hiệu lực" needs a verified status or the source's own words;
* duplicates of an earlier point are dropped.

These are lexical checks.  They catch unsupported, off-topic and reversed statements;
they do not prove that a paraphrase is legally exact, so a kept point is shown as
"đã đối chiếu với căn cứ", never as "đúng", and the verbatim quote stays next to it.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ..vietnamese_nlp.unicode_norm import fold_text, normalize_text

_QUOTED = re.compile(r"[\"“][^\"”]*[\"”]")
_DOC_NUMBER = re.compile(r"\b\d{1,5}/(?:\d{4}/)?[A-ZĐa-zđ][A-ZĐa-zđ0-9\-&]*")
_DATE_SLASH = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b")
_DATE_WORDS = re.compile(r"\bngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})", re.I)
_PART = re.compile(r"\b(điều|khoản|điểm)\s+(\d+[a-z]?|[a-zđ])\b", re.I)
_NUMBER = re.compile(r"(?<![\w/])\d+(?:[.,]\d+)*(?![\w/])")
_CONCLUSIONS = (
    re.compile(r"\bphải\s+xử\s+lý\b", re.I),
    re.compile(r"\b(?:không\s+)?đủ\s+điều\s+kiện\b", re.I),
    re.compile(r"\bkết\s+luận\b", re.I),
    re.compile(r"\bquyết\s+định\b(?!\s+(?:số|này|của|\d))", re.I),
)


@dataclass(frozen=True)
class PointCheck:
    keep: bool
    status: str  # verified | unverified
    reasons: tuple[str, ...]


def _dates(text: str) -> set[tuple[int, int, int]]:
    found = {(int(d), int(m), int(y)) for d, m, y in _DATE_SLASH.findall(text)}
    found |= {(int(d), int(m), int(y)) for d, m, y in _DATE_WORDS.findall(text)}
    return found


def _facts(text: str) -> tuple[set[str], set[tuple[int, int, int]], set[tuple[str, str]], set[str]]:
    numbers = {fold_text(item) for item in _DOC_NUMBER.findall(text)}
    dates = _dates(text)
    parts = {(kind.lower(), value.lower()) for kind, value in _PART.findall(text)}
    stripped = _DATE_WORDS.sub(" ", _DATE_SLASH.sub(" ", _DOC_NUMBER.sub(" ", text)))
    # "05 ngày" and "5 ngày" are the same number; thousands dots are kept as written.
    plain = {item.replace(",", ".").lstrip("0") or "0" for item in _NUMBER.findall(stripped)}
    return numbers, dates, parts, plain


def check_point(
    text: str, evidence_ids: Sequence[str], evidence: Mapping[str, str],
) -> PointCheck:
    """``evidence`` maps evidence id -> text the model was given (label, number, quote)."""

    if not text.strip() or not evidence_ids:
        return PointCheck(False, "unverified", ("NO_EVIDENCE",))
    if any(item not in evidence for item in evidence_ids) or len(set(evidence_ids)) != len(
        evidence_ids
    ):
        return PointCheck(False, "unverified", ("UNKNOWN_EVIDENCE_ID",))
    outside = _QUOTED.sub(" ", text)
    cited = "\n".join(evidence[item] for item in evidence_ids)
    folded_source = " ".join(fold_text(cited).split())
    for pattern in _CONCLUSIONS:
        # Restating the source's own words ("quyết định xử phạt", "giấy chứng nhận đủ
        # điều kiện") is not a conclusion; the model's own verdict is.
        found = pattern.search(outside)
        if found and " ".join(fold_text(found.group(0)).split()) not in folded_source:
            return PointCheck(False, "unverified", ("BUSINESS_CONCLUSION",))
    numbers, dates, parts, plain = _facts(outside)
    c_numbers, c_dates, c_parts, c_plain = _facts(cited)
    folded_cited = fold_text(cited)
    reasons: list[str] = []
    if any(number not in c_numbers and number not in folded_cited for number in numbers):
        reasons.append("DOCUMENT_NUMBER_NOT_IN_EVIDENCE")
    if dates - c_dates:
        reasons.append("DATE_NOT_IN_EVIDENCE")
    if parts - c_parts:
        reasons.append("REFERENCE_NOT_IN_EVIDENCE")
    if plain - c_plain:
        reasons.append("NUMBER_NOT_IN_EVIDENCE")
    return PointCheck(True, "unverified" if reasons else "verified", tuple(reasons))


# ------------------------------------------------------------------ claim layers
_WORD = re.compile(r"[0-9a-zđ]+")
# Words that carry no content of their own (function words, question words, generic
# legal glue).  A claim is judged on the rest.
_STOP = frozenset(fold_text(word) for word in (
    "và", "hoặc", "của", "các", "những", "là", "có", "được", "cho", "theo", "về", "trong",
    "với", "tại", "khi", "nếu", "thì", "do", "bởi", "từ", "đến", "này", "đó", "một", "mỗi",
    "để", "vào", "ra", "như", "sau", "trước", "bao", "gồm", "việc", "phải", "cần", "nên",
    "đã", "sẽ", "đang", "cũng", "còn", "mà", "nhưng", "hay", "ở", "trên", "dưới", "nào",
    "gì", "căn", "cứ", "quy", "định", "nêu", "rõ", "cụ", "thể", "văn", "bản", "điều",
    "khoản", "điểm", "số", "theo", "đây", "hiện", "nay", "đối", "với", "ai", "người",
))
SUPPORT_DROP = 0.35
SUPPORT_REVIEW = 0.55
DUPLICATE_SIMILARITY = 0.7
MAX_POINT_CHARS = 600
COPY_RUN_TOKENS = 30

_NEGATION = ("không", "chưa", "cấm", "nghiêm cấm", "không được", "không phải")
_EXCEPTION = ("trừ trường hợp", "ngoại trừ", "trừ khi", "trừ các trường hợp", "không áp dụng")
_CONDITION = ("trong trường hợp", "trường hợp", "nếu", "chỉ được", "chỉ khi", "với điều kiện")
_OBLIGATION = ("phải", "có trách nhiệm", "bắt buộc")
_PERMISSION = ("có thể", "được phép", "có quyền")
_EFFECTIVITY = ("còn hiệu lực", "hết hiệu lực", "có hiệu lực", "bị bãi bỏ", "bị thay thế",
                "đã bãi bỏ", "đã thay thế")

REASON_TEXT = {
    "QUOTE_NOT_IN_EVIDENCE": "đoạn trong ngoặc kép không có nguyên văn trong căn cứ",
    "NOT_SUPPORTED_BY_EVIDENCE": "nội dung không có trong căn cứ được dẫn",
    "WEAK_SUPPORT": "chỉ một phần nội dung có trong căn cứ",
    "OFF_TOPIC": "không thuộc vấn đề được hỏi",
    "ASPECT_NOT_IN_EVIDENCE": "căn cứ được dẫn không quy định nội dung này",
    "NEGATION_REVERSED": "ngược nghĩa phủ định so với căn cứ",
    "NEGATION_OMITTED": "căn cứ có phủ định/cấm mà ý này không nêu",
    "EXCEPTION_OMITTED": "căn cứ có ngoại lệ chưa được nêu",
    "CONDITION_OMITTED": "căn cứ có điều kiện áp dụng chưa được nêu",
    "MODALITY_MISMATCH": "khác căn cứ về bắt buộc/được phép",
    "EFFECTIVITY_NOT_VERIFIED": "hiệu lực chưa được xác minh trong kho",
    "DUPLICATE": "trùng ý đã trình bày",
    "TOO_LONG": "quá dài",
    "COPIED_VERBATIM": "chép nguyên văn căn cứ, không diễn giải",
    "DOCUMENT_NUMBER_NOT_IN_EVIDENCE": "số hiệu không có trong căn cứ",
    "DATE_NOT_IN_EVIDENCE": "ngày tháng không có trong căn cứ",
    "REFERENCE_NOT_IN_EVIDENCE": "Điều/Khoản/Điểm không có trong căn cứ",
    "NUMBER_NOT_IN_EVIDENCE": "con số không có trong căn cứ",
    "BUSINESS_CONCLUSION": "kết luận nghiệp vụ",
    "UNKNOWN_EVIDENCE_ID": "dẫn căn cứ không được cung cấp",
    "NO_EVIDENCE": "không gắn căn cứ",
}


@dataclass(frozen=True)
class ClaimEvidence:
    """What the model saw for one evidence id."""

    given: str  # number + label + quote cut, exactly as sent
    quote: str  # the verbatim cut alone
    effectivity_verified: bool = False
    aspects: frozenset[str] = frozenset()  # aspect codes the clause regulates


@dataclass(frozen=True)
class ClaimCheck:
    keep: bool
    status: str  # verified | needs_review
    reasons: tuple[str, ...]
    support: float

    @property
    def notes(self) -> list[str]:
        return [REASON_TEXT.get(item, item) for item in self.reasons]


def _fold_words(text: str) -> list[str]:
    return _WORD.findall(fold_text(normalize_text(text)))


def _content(words: Sequence[str]) -> list[str]:
    return [word for word in words if word not in _STOP and not word.isdigit()]


def _bigrams(words: Sequence[str]) -> set[tuple[str, str]]:
    return {(words[i], words[i + 1]) for i in range(len(words) - 1)}


def support_score(claim: str, source: str) -> float:
    """Share of the claim's content words (and adjacent pairs) found in ``source``."""

    claim_words = _fold_words(_QUOTED.sub(" ", claim))
    content = _content(claim_words)
    if not content:
        return 1.0
    source_words = _fold_words(source)
    source_set = set(source_words)
    unigram = sum(1 for word in content if word in source_set) / len(content)
    pairs = _bigrams(content)
    if not pairs:
        return unigram
    source_pairs = _bigrams(_content(source_words)) | _bigrams(source_words)
    bigram = sum(1 for pair in pairs if pair in source_pairs) / len(pairs)
    return round(0.4 * unigram + 0.6 * bigram, 4)


def similarity(left: str, right: str) -> float:
    """Overlap of two claims; numbers count ("đến 15.000.000 đồng" ≠ "đến 30.000.000 đồng")."""

    def words(text: str) -> list[str]:
        return [word for word in _fold_words(text) if word not in _STOP]

    if {item for item in _fold_words(left) if item.isdigit()} != {
            item for item in _fold_words(right) if item.isdigit()}:
        return 0.0  # same wording, different figures: different facts
    a, b = _bigrams(words(left)), _bigrams(words(right))
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _has_accented(text: str, cues: Sequence[str]) -> bool:
    words = re.findall(r"[0-9a-zà-ỹđ]+", normalize_text(text).casefold())
    padded = f" {' '.join(words)} "
    return any(f" {' '.join(re.findall(r'[0-9a-zà-ỹđ]+', cue))} " in padded for cue in cues)


def _sentences(text: str) -> list[str]:
    return [part for part in re.split(r"(?<=[.;:!?])\s+|\n+", text) if part.strip()]


def _closest_sentence(claim: str, source: str) -> str:
    best, best_score = "", -1.0
    for sentence in _sentences(source):
        score = support_score(claim, sentence)
        if score > best_score:
            best, best_score = sentence, score
    return best


def _quote_ok(claim: str, source: str) -> bool:
    folded_source = " ".join(_fold_words(source))
    for match in _QUOTED.finditer(claim):
        inner = " ".join(_fold_words(match.group(0)))
        if inner and inner not in folded_source:
            return False
    return True


def _longest_copy(claim: str, source: str) -> int:
    a, b = _fold_words(claim), _fold_words(source)
    if not a or not b:
        return 0
    positions: dict[str, list[int]] = {}
    for index, word in enumerate(b):
        positions.setdefault(word, []).append(index)
    best = 0
    for start in range(len(a)):
        for offset in positions.get(a[start], []):
            length = 0
            while (start + length < len(a) and offset + length < len(b)
                   and a[start + length] == b[offset + length]):
                length += 1
            best = max(best, length)
    return best


def verify_claim(
    text: str, evidence_ids: Sequence[str], evidence: Mapping[str, ClaimEvidence], *,
    focus: object | None = None, previous: Sequence[str] = (),
) -> ClaimCheck:
    """All layers for one AI point.  ``focus`` is a ``synthesis.focus.QuestionFocus``."""

    from .focus import ASPECTS, QuestionFocus, mentions_focus

    given = {key: value.given for key, value in evidence.items()}
    base = check_point(text, evidence_ids, given)
    if not base.keep or base.reasons:
        # A number, date, document number or Điều/Khoản/Điểm the cited clauses do not
        # contain is never shown, not even with a warning.
        return ClaimCheck(False, "needs_review", base.reasons, 0.0)
    reasons: list[str] = []
    cited = [evidence[item] for item in evidence_ids]
    quote = "\n".join(item.quote for item in cited)
    if len(text) > MAX_POINT_CHARS:
        return ClaimCheck(False, "needs_review", ("TOO_LONG",), 0.0)
    if not _quote_ok(text, quote):
        return ClaimCheck(False, "needs_review", ("QUOTE_NOT_IN_EVIDENCE",), 0.0)
    support = support_score(text, quote)
    if support < SUPPORT_DROP:
        return ClaimCheck(False, "needs_review", ("NOT_SUPPORTED_BY_EVIDENCE",), support)
    on_topic = True
    if isinstance(focus, QuestionFocus) and (focus.subject or focus.aspects):
        on_topic = mentions_focus(focus, text)
        if not on_topic and support < SUPPORT_REVIEW:
            return ClaimCheck(False, "needs_review", ("OFF_TOPIC",), support)
    # A claim that states an aspect (a penalty, a deadline, ...) needs a clause that
    # regulates it: an inspection procedure never supports a penalty.
    regulated = set().union(*(item.aspects for item in cited)) if cited else set()
    for aspect in ASPECTS:
        if not aspect.strict or aspect.code in regulated:
            continue
        if _has_accented(text, aspect.question_cues) and not _has_accented(
                quote, aspect.evidence_cues):
            return ClaimCheck(False, "needs_review", ("ASPECT_NOT_IN_EVIDENCE",), support)
    if _has_accented(text, _EFFECTIVITY) and not (
            any(item.effectivity_verified for item in cited)
            or _has_accented(quote, _EFFECTIVITY)):
        return ClaimCheck(False, "needs_review", ("EFFECTIVITY_NOT_VERIFIED",), support)
    sentence = _closest_sentence(text, quote)
    claim_negated = _has_accented(_QUOTED.sub(" ", text), _NEGATION)
    if claim_negated and not _has_accented(quote, _NEGATION):
        return ClaimCheck(False, "needs_review", ("NEGATION_REVERSED",), support)
    if _has_accented(sentence, _NEGATION) and not claim_negated:
        reasons.append("NEGATION_OMITTED")
    if _has_accented(sentence, _EXCEPTION) and not _has_accented(
            text, ("trừ", "ngoại trừ", "không áp dụng", "ngoại lệ")):
        reasons.append("EXCEPTION_OMITTED")
    if _has_accented(sentence, _CONDITION) and not _has_accented(
            text, ("trường hợp", "nếu", "khi", "chỉ", "điều kiện", "đối với")):
        reasons.append("CONDITION_OMITTED")
    if (_has_accented(sentence, _OBLIGATION) and _has_accented(text, ("có thể",))
            and not _has_accented(sentence, ("có thể",))) or (
            _has_accented(sentence, _PERMISSION) and _has_accented(text, ("bắt buộc", "phải"))
            and not _has_accented(sentence, _OBLIGATION)):
        reasons.append("MODALITY_MISMATCH")
    if any(similarity(text, item) >= DUPLICATE_SIMILARITY for item in previous):
        return ClaimCheck(False, "needs_review", ("DUPLICATE",), support)
    words = len(_fold_words(text))
    if words >= COPY_RUN_TOKENS and _longest_copy(text, quote) >= max(COPY_RUN_TOKENS,
                                                                        int(words * 0.85)):
        return ClaimCheck(False, "needs_review", ("COPIED_VERBATIM",), support)
    if support < SUPPORT_REVIEW:
        reasons.append("WEAK_SUPPORT")
    if not on_topic:
        reasons.append("OFF_TOPIC")
    status = "verified" if not reasons else "needs_review"
    return ClaimCheck(True, status, tuple(dict.fromkeys(reasons)), support)


# ------------------------------------------------------------------ text hygiene
_ID_MENTION = re.compile(r"\s*[\[(]\s*e\d+(?:\s*[,;]\s*e\d+)*\s*[\])]|\b(?:căn cứ\s+)?e\d+\b:?",
                         re.I)
_MARKDOWN = re.compile(r"[*_#`>]+")


def clean_text(text: str) -> str:
    """NFC, no markdown or evidence-id mentions, sentence case, final punctuation."""

    value = unicodedata.normalize("NFC", str(text))
    value = _ID_MENTION.sub("", value)
    value = _MARKDOWN.sub("", value)
    value = re.sub(r"^\s*(?:[-•–]|\d+[.)])\s+", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    # What is left of "Căn cứ: e1, e2." once the ids are gone.
    value = re.sub(r"(?:\(|\b)(?:theo\s+)?(?:căn cứ|nguồn)\s*[:：]?\s*[,;.\s]*\)?\s*$", "",
                   value, flags=re.I).strip()
    value = re.sub(r"\s*([,;])(?:\s*[,;])+", r"\1", value)
    value = re.sub(r"[,;]\s*\.", ".", value)
    value = re.sub(r"\s+([,.;:!?])", r"\1", value)
    value = re.sub(r"([,;:])(?=[^\W\d_])", r"\1 ", value)
    value = re.sub(r"\(\s*\)", "", value).strip(" ,;")
    if not value:
        return ""
    value = value[0].upper() + value[1:]
    if value[-1] not in ".!?…”\"":
        value += "."
    return value
