"""Phrase-aware relevance of retrieved clauses (SRS §5.2 L2 syllable bigrams, §5.3 P0-lite gate).

Retrieval channels find candidates; this module decides how each candidate relates to
what the user actually typed, so a clause is never shown as evidence because of one
shared syllable ("nhiệm", "báo", "định").

* The question is cut into **phrase segments** at punctuation and function words
  ("trong", "của", "và", "như thế nào", ...).  "Thủ tục bổ nhiệm, miễn nhiệm trong Công
  an nhân dân" -> ``thủ tục bổ nhiệm`` | ``miễn nhiệm`` | ``công an nhân dân``.
* Inside a segment the units are the adjacent syllable pairs (bigrams).  A bigram is
  matched only as a contiguous pair of whole syllables, so "báo cáo" never matches a
  clause that has "báo" and "cáo" in different places.  A one-syllable segment is a
  single unit.
* Every unit is weighted by how rare it is among the clauses the user may read
  (inverse document frequency, counted in PostgreSQL).  Common context such as "công an
  nhân dân" weighs little; "miễn nhiệm" weighs a lot.  Nothing in the code knows any
  particular word.
* A clause is scored on its own text and its headings (Điều title, Chương/Mục); the
  document title counts half.  Tiers: ``direct`` (the question's phrases are in the
  clause), ``related`` (it shares the rarest phrases, or was found by meaning and shares
  some), ``weak`` (only scattered or common words).  Weak results stay in the full result
  list; they are never presented as evidence.
* A clause that lists many other documents (a catalogue of legal documents) is a
  ``listing``: shown as "chỉ nhắc đến", never as direct evidence.

The excerpt is a verbatim slice of ``text_original`` around the best phrase matches;
highlights are offsets in that text.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from ..vietnamese_nlp.unicode_norm import _normalize_tone_spelling, normalize_text

# Letters/digits plus combining marks (a decomposed text keeps its syllables whole).
_TOKEN_RE = re.compile(r"[0-9A-Za-zÀ-ỹĐđ\u0300-\u036f]+")
_SPLIT_RE = re.compile(r"[,;:.!?()\[\]{}\"“”'‘’«»/\\|…–—\-]+|\s-\s")
_DOC_NUMBER_RE = re.compile(
    r"\b\d{1,5}/(?:\d{4}/)?[A-ZĐ][A-ZĐa-zđ0-9]*(?:-[A-ZĐa-zđ0-9]+)*", re.UNICODE
)
_REFERENCE_RE = re.compile(
    r"\b(?:điều|khoản|điểm|chương|mục)\s+(?:\d+[a-z]?|[a-zđ]|[ivxlc]+)\b", re.IGNORECASE
)
_NUMBER_BODY_RE = re.compile(
    r"\b\d{1,5}/\d{4}(?:/[0-9A-Za-zÀ-ỹĐđ]+(?:-[0-9A-Za-zÀ-ỹĐđ]+)*)?"
)
_LISTING_TITLE_RE = re.compile(r"\bdanh muc\b.*\b(?:van ban|vbqppl)\b|\bhe thong hoa\b")

# Function words and question words: they separate phrases and never count as evidence.
_SPLIT_PHRASES = tuple(sorted((
    ("như", "thế", "nào"), ("thế", "nào"), ("ra", "sao"), ("là", "gì"), ("bao", "nhiêu"),
    ("đối", "với"), ("liên", "quan", "đến"), ("liên", "quan", "tới"), ("quy", "định"),
    ("văn", "bản", "nào"), ("hay", "không"), ("được", "không"), ("những", "gì"),
    ("gồm", "những"), ("bao", "gồm"), ("có", "phải"), ("như", "vậy"), ("cho", "biết"),
    ("hiện", "nay"), ("hiện", "hành"), ("theo", "đó"), ("vấn", "đề"), ("thế", "nào", "là"),
    ("có", "những"), ("những", "nội", "dung", "gì"), ("cụ", "thể"),
), key=len, reverse=True))
_SPLIT_WORDS = frozenset({
    "gì", "nào", "sao", "ai", "đâu", "những", "các", "là", "có", "không", "được", "của",
    "về", "trong", "theo", "với", "và", "hoặc", "hay", "cho", "tại", "khi", "nếu", "thì",
    "do", "bởi", "từ", "đến", "tới", "này", "đó", "ấy", "kia", "hỏi", "tôi", "xin", "cần",
    "bị", "đã", "sẽ", "đang", "mọi", "mỗi", "một", "ở", "vào", "để", "nên", "vậy", "thế",
    "nhé", "ạ", "ơi", "như", "thuộc", "mà", "gồm", "rằng", "nhưng", "cũng", "còn", "phải",
})

# Tier thresholds on the weighted unit coverage (0..1).  Not tuned to any question.
DIRECT_OWN = 0.5          # with every core segment present
DIRECT_ALONE = 0.85       # almost every word of the question, close together
RELATED_CLOSE = 0.3
SEMANTIC_OWN = 0.15
SEMANTIC_STRONG_RANK = 5
CORE_SEGMENT_COVERAGE = 0.5
WINDOW_TOKENS = 30
SCATTERED_CREDIT = 0.3
TITLE_CREDIT = 0.5
FOLDED_CREDIT = 0.8
HEADING_CREDIT = 0.9
LISTING_MIN_NUMBERS = 4
EXCERPT_TARGET = 360
EXCERPT_MAX = 520
TIER_ORDER = {"direct": 0, "related": 1, "weak": 2, "unscored": 3}


def _fold_table() -> dict[int, str]:
    table: dict[int, str] = {}
    for code in range(0xC0, 0x1EFA):
        char = chr(code)
        base = "".join(part for part in unicodedata.normalize("NFD", char)
                       if unicodedata.category(part) != "Mn")
        if len(base) == 1 and base != char:
            table[code] = base
    table[ord("đ")] = "d"
    table[ord("Đ")] = "D"
    return table


_FOLD = _fold_table()


def fold_token(token: str) -> str:
    """Accent-free form of an already normalized, lower-cased syllable (same length)."""

    return token.translate(_FOLD)


def _norm_token(token: str) -> str:
    return normalize_text(token).casefold()


@dataclass(frozen=True)
class Unit:
    tokens: tuple[str, ...]
    folded: tuple[str, ...]
    segment: int

    @property
    def text(self) -> str:
        return " ".join(self.tokens)

    @property
    def folded_text(self) -> str:
        return " ".join(self.folded)


@dataclass(frozen=True)
class QueryTerms:
    original: str
    segments: tuple[tuple[str, ...], ...]
    units: tuple[Unit, ...]
    accented: bool

    @property
    def phrases(self) -> list[str]:
        return [" ".join(segment) for segment in self.segments]

    @property
    def empty(self) -> bool:
        return not self.units


def _split_segment(tokens: list[str]) -> list[list[str]]:
    segments: list[list[str]] = []
    current: list[str] = []
    index = 0
    while index < len(tokens):
        matched = next((phrase for phrase in _SPLIT_PHRASES
                        if tuple(tokens[index:index + len(phrase)]) == phrase), None)
        if matched is not None:
            if current:
                segments.append(current)
            current = []
            index += len(matched)
            continue
        if tokens[index] in _SPLIT_WORDS:
            if current:
                segments.append(current)
            current = []
        else:
            current.append(tokens[index])
        index += 1
    if current:
        segments.append(current)
    return segments


def analyze_terms(question: str) -> QueryTerms:
    """Phrase segments and bigram units of the question (references removed)."""

    text = normalize_text(question)
    text = _NUMBER_BODY_RE.sub(" | ", _REFERENCE_RE.sub(" | ", text))
    segments: list[tuple[str, ...]] = []
    all_tokens: list[str] = []
    for chunk in _SPLIT_RE.split(text):
        tokens = [_norm_token(token) for token in _TOKEN_RE.findall(chunk)]
        all_tokens += tokens
        for words in _split_segment(tokens):
            key = tuple(words)
            if key and key not in segments:
                segments.append(key)
    if not segments and all_tokens:
        # Only function words: keep what the user typed rather than nothing.
        segments = [tuple(dict.fromkeys(all_tokens))]
    units: list[Unit] = []
    seen: set[tuple[str, ...]] = set()
    for position, segment in enumerate(segments):
        pairs: list[tuple[str, ...]] = (
            [tuple(segment[i:i + 2]) for i in range(len(segment) - 1)]
            if len(segment) > 1 else [tuple(segment)]
        )
        for pair in pairs:
            if pair in seen:
                continue
            seen.add(pair)
            units.append(Unit(tuple(pair), tuple(fold_token(t) for t in pair), position))
    accented = any(fold_token(token) != token for segment in segments for token in segment)
    return QueryTerms(question.strip(), tuple(segments), tuple(units), accented)


# ------------------------------------------------------------------ weights
_DF_SQL = """
SELECT u.ordinality::int AS position,
       (SELECT count(*) FROM (
            SELECT 1 FROM document_nodes n
            WHERE n.document_version_id = ANY($1::uuid[]) AND n.review_status = 'approved'
              AND to_tsvector('simple'::regconfig, n.text_folded)
                  @@ phraseto_tsquery('simple'::regconfig, u.phrase)
            LIMIT $3) found) AS df
FROM unnest($2::text[]) WITH ORDINALITY AS u(phrase, ordinality)
"""
_TOTAL_SQL = """
SELECT count(*) FROM document_nodes n
WHERE n.document_version_id = ANY($1::uuid[]) AND n.review_status = 'approved'
"""
DF_CAP = 20_000


async def unit_weights(
    connection: Any, versions: Sequence[UUID], terms: QueryTerms,
) -> dict[tuple[str, ...], float]:
    """Inverse document frequency of every unit among the clauses the user may read.

    A unit that no readable clause contains gets weight 0: it cannot be matched, so it
    must not lower every score alike.
    """

    if terms.empty or not versions:
        return {}
    total = int(await connection.fetchval(_TOTAL_SQL, list(versions)) or 0)
    rows = await connection.fetch(
        _DF_SQL, list(versions), [unit.folded_text for unit in terms.units], DF_CAP,
    )
    df = {int(row["position"]): int(row["df"]) for row in rows}
    weights: dict[tuple[str, ...], float] = {}
    for position, unit in enumerate(terms.units, start=1):
        count = df.get(position, 0)
        weights[unit.tokens] = (
            0.0 if count == 0 else math.log((total + 1) / (count + 0.5)) + 0.1
        )
    return weights


# ------------------------------------------------------------------ texts
@dataclass
class _Tokens:
    norms: list[str]
    folds: list[str]
    spans: list[tuple[int, int]]
    index: dict[str, list[int]]
    folded_index: dict[str, list[int]]


def _tokens(text: str) -> _Tokens:
    # Same-length normalization keeps offsets valid in ``text`` itself.
    source = _normalize_tone_spelling(text) if unicodedata.is_normalized("NFC", text) else None
    norms: list[str] = []
    spans: list[tuple[int, int]] = []
    for match in _TOKEN_RE.finditer(source if source is not None else text):
        raw = match.group(0)
        norms.append(raw.casefold() if source is not None else _norm_token(raw))
        spans.append((match.start(), match.end()))
    folds = [fold_token(token) for token in norms]
    index: dict[str, list[int]] = {}
    folded_index: dict[str, list[int]] = {}
    for position, (norm, fold) in enumerate(zip(norms, folds, strict=True)):
        index.setdefault(norm, []).append(position)
        folded_index.setdefault(fold, []).append(position)
    return _Tokens(norms, folds, spans, index, folded_index)


def tokenize(text: str) -> _Tokens:
    """Normalized and accent-folded syllables of ``text`` with their offsets."""

    return _tokens(text)


def phrase_tokens(phrase: str) -> tuple[str, ...]:
    return tuple(_norm_token(token) for token in _TOKEN_RE.findall(normalize_text(phrase)))


def find_sequence(tokens: _Tokens, sequence: Sequence[str], *, folded: bool = False) -> list[int]:
    """Start positions where ``sequence`` (normalized syllables) occurs contiguously."""

    if not sequence:
        return []
    key = tuple(fold_token(item) for item in sequence) if folded else tuple(sequence)
    return _occurrences(tokens, Unit(tuple(sequence), key, 0), folded=folded)


def _occurrences(tokens: _Tokens, unit: Unit, *, folded: bool) -> list[int]:
    sequence = unit.folded if folded else unit.tokens
    values = tokens.folds if folded else tokens.norms
    starts = (tokens.folded_index if folded else tokens.index).get(sequence[0], [])
    size = len(sequence)
    return [start for start in starts
            if tuple(values[start:start + size]) == sequence]


@dataclass
class Assessment:
    tier: str = "unscored"
    match: str = "none"  # phrase | terms | partial | semantic | concept | relation | none
    score: float = 0.0
    context_score: float = 0.0
    matched: list[str] = field(default_factory=list)
    phrases: list[str] = field(default_factory=list)
    listing: bool = False
    excerpt_start: int = 0
    excerpt_end: int = 0
    highlights: list[tuple[int, int]] = field(default_factory=list)


def _credit(tokens: _Tokens, unit: Unit, accented: bool) -> tuple[float, list[int]]:
    exact = _occurrences(tokens, unit, folded=False)
    if exact:
        return 1.0, exact
    folded = _occurrences(tokens, unit, folded=True)
    if folded:
        return (1.0 if not accented else FOLDED_CREDIT), folded
    return 0.0, []


def distinct_document_numbers(text: str) -> int:
    return len({re.sub(r"\s+", "", item).casefold() for item in _DOC_NUMBER_RE.findall(text)})


def is_listing(text: str, title: str) -> bool:
    numbers = distinct_document_numbers(text)
    if numbers >= LISTING_MIN_NUMBERS:
        return True
    folded_title = " ".join(re.sub(r"[^0-9a-z]+", " ", fold_token(title.casefold())).split())
    return numbers >= 2 and bool(_LISTING_TITLE_RE.search(folded_title))


@dataclass(frozen=True)
class WordPlan:
    """Which unit "owns" each syllable of the question, and its weight.

    Without a word list, a syllable belongs to the most frequent pair that contains it:
    real words ("bổ nhiệm") occur far more often than pairs straddling two words
    ("tục bổ" in "thủ tục bổ nhiệm").  Only owning units give credit, so a pair that
    straddles two words never makes a clause relevant on its own.
    """

    owners: tuple[tuple[Unit, int], ...]  # (unit, number of syllables it owns)
    weights: dict[tuple[str, ...], float]
    total: float
    rare: frozenset[tuple[str, ...]]
    # Segments holding a rare unit: the ones a direct answer must contain.
    core_segments: frozenset[int] = frozenset()


def word_plan(terms: QueryTerms, weights: dict[tuple[str, ...], float]) -> WordPlan:
    owned: dict[tuple[str, ...], int] = {}
    by_tokens = {unit.tokens: unit for unit in terms.units}
    for position, segment in enumerate(terms.segments):
        candidates = [unit for unit in terms.units if unit.segment == position]
        for index in range(len(segment)):
            holders = [
                unit for unit in candidates
                if weights.get(unit.tokens, 0.0) > 0 and (
                    (len(unit.tokens) == 1 and index == 0)
                    or (len(unit.tokens) == 2 and segment[index:index + 2] == unit.tokens)
                    or (len(unit.tokens) == 2 and index > 0
                        and segment[index - 1:index + 1] == unit.tokens))
            ]
            if not holders:
                continue
            owner = min(holders, key=lambda unit: weights[unit.tokens])
            owned[owner.tokens] = owned.get(owner.tokens, 0) + 1
    owners = tuple((by_tokens[tokens], count) for tokens, count in owned.items())
    total = sum(weights[unit.tokens] * count for unit, count in owners)
    ranked = sorted(owners, key=lambda pair: -weights[pair[0].tokens])
    rare: list[tuple[str, ...]] = []
    running = 0.0
    core: set[int] = set()
    for unit, count in ranked:
        rare.append(unit.tokens)
        core.add(unit.segment)
        running += weights[unit.tokens] * count
        if running >= total * 0.5:
            break
    return WordPlan(owners, weights, total, frozenset(rare), frozenset(core))


def _best_window(
    hits: dict[tuple[str, ...], list[int]], weights: dict[tuple[str, ...], float],
) -> set[tuple[str, ...]]:
    """Units that occur together inside the densest window of ``WINDOW_TOKENS`` tokens.

    Long paragraphs contain most words somewhere; only words written close together
    (about one sentence) express the question's idea, so scattered ones count less.
    """

    events = sorted((position, unit) for unit, positions in hits.items() for position in positions)
    best: set[tuple[str, ...]] = set()
    best_weight = -1.0
    left = 0
    inside: dict[tuple[str, ...], int] = {}
    for right in range(len(events)):
        position, unit = events[right]
        inside[unit] = inside.get(unit, 0) + 1
        while position - events[left][0] > WINDOW_TOKENS:
            gone = events[left][1]
            inside[gone] -= 1
            if not inside[gone]:
                del inside[gone]
            left += 1
        weight = sum(weights.get(item, 0.0) for item in inside)
        if weight > best_weight + 1e-9:
            best_weight, best = weight, set(inside)
    return best


def assess(
    terms: QueryTerms, plan: WordPlan, *, text: str,
    headings: Iterable[str], title: str, ranks: dict[str, int] | None = None,
    approved_concept: bool = False,
) -> Assessment:
    """Tier, match kind, matched phrases and a verbatim excerpt of one clause.

    ``ranks`` are the clause's ranks per retrieval channel (exact, semantic, ...).
    """

    result = Assessment()
    channel_ranks = dict(ranks or {})
    channel_set = set(channel_ranks)
    result.listing = is_listing(text, title)
    own = _tokens(text)
    heading_tokens = [_tokens(item) for item in headings if item]
    title_tokens = _tokens(title)
    occurrences: list[tuple[int, int, float, str]] = []  # start, end, weight, unit key
    found: dict[tuple[str, ...], tuple[float, list[int]]] = {
        unit.tokens: _credit(own, unit, terms.accented) for unit, _ in plan.owners
    }
    together = _best_window({key: starts for key, (_, starts) in found.items() if starts},
                            {unit.tokens: plan.weights[unit.tokens] * count
                             for unit, count in plan.owners})
    own_sum = context_sum = close_sum = 0.0
    matched: list[str] = []
    has_rare = False
    rare_close = False
    close_units = 0
    segment_hit: dict[int, float] = {}
    segment_total: dict[int, float] = {}
    for unit, count in plan.owners:
        weight = plan.weights[unit.tokens] * count
        segment_total[unit.segment] = segment_total.get(unit.segment, 0.0) + weight
        credit, starts = found[unit.tokens]
        if credit and unit.tokens not in together:
            credit *= SCATTERED_CREDIT
        heading_credit = max((_credit(item, unit, terms.accented)[0] for item in heading_tokens),
                             default=0.0) * HEADING_CREDIT
        title_credit = _credit(title_tokens, unit, terms.accented)[0] * TITLE_CREDIT
        best_own = max(credit, heading_credit)
        if best_own > 0:
            matched.append(unit.text)
            has_rare = has_rare or unit.tokens in plan.rare
        # A segment is present only through words written together (or in a heading).
        close = max(found[unit.tokens][0] if unit.tokens in together else 0.0, heading_credit)
        if close > 0:
            segment_hit[unit.segment] = segment_hit.get(unit.segment, 0.0) + weight * close
            close_sum += weight * close
            close_units += 1
            rare_close = rare_close or unit.tokens in plan.rare
        own_sum += weight * best_own
        context_sum += weight * max(best_own, title_credit)
        for start in starts:
            end = own.spans[start + len(unit.tokens) - 1][1]
            occurrences.append((own.spans[start][0], end, weight, unit.text))
    # Every segment carrying a real share of the question must be present: "bổ nhiệm"
    # alone does not answer "bổ nhiệm, miễn nhiệm"; light context ("công an nhân dân")
    # may be missing.
    core_covered = bool(plan.core_segments) and all(
        segment_hit.get(segment, 0.0) >= segment_total.get(segment, 0.0) * CORE_SEGMENT_COVERAGE
        for segment in plan.core_segments
    )
    # A whole multi-word segment written contiguously is a phrase match; its pairs that
    # straddle words are only used here, to detect that the phrase is intact.
    for position, segment in enumerate(terms.segments):
        if len(segment) < 2:
            continue
        probe = Unit(segment, tuple(fold_token(token) for token in segment), position)
        spots = _occurrences(own, probe, folded=False) or (
            _occurrences(own, probe, folded=True) if not terms.accented else [])
        if spots:
            result.phrases.append(" ".join(segment))
            for start in spots:
                end = own.spans[start + len(segment) - 1][1]
                occurrences.append((own.spans[start][0], end, 0.0, f"phrase:{position}"))
    result.matched = matched
    if plan.total > 0:
        result.score = round(own_sum / plan.total, 4)
        result.context_score = round(context_sum / plan.total, 4)
    lexical = "exact" in channel_set or not channel_set
    direct = (core_covered and result.score >= DIRECT_OWN) or result.score >= DIRECT_ALONE
    semantic_rank = channel_ranks.get("semantic")
    close_score = close_sum / plan.total if plan.total else 0.0
    if direct:
        result.tier = "direct"
    elif rare_close and close_score >= RELATED_CLOSE and (
            close_units >= 2 or len(plan.owners) == 1):
        # One word of a several-word question is never enough on its own.
        # A rare phrase of the question with other words of it in the same sentence.
        result.tier = "related"
    elif semantic_rank is not None and semantic_rank <= SEMANTIC_STRONG_RANK and \
            has_rare and result.score >= SEMANTIC_OWN:
        # Among the very nearest by meaning and holding a distinctive word of the
        # question: a paraphrase.  Nearness alone (common words only) is not enough.
        result.tier = "related"
    elif "concept" in channel_set and approved_concept and result.score >= SEMANTIC_OWN:
        result.tier = "related"
    else:
        result.tier = "weak"
    if result.listing and result.tier == "direct":
        result.tier = "related"
    if result.phrases and direct:
        result.match = "phrase"
    elif direct:
        result.match = "terms"
    elif not has_rare and "semantic" in channel_set and (
            result.tier == "related" or not lexical):
        # Found by meaning, without the question's distinctive phrases: labelled so,
        # never presented as a keyword match.
        result.match = "semantic"
    elif result.tier == "related" and not has_rare and "concept" in channel_set:
        result.match = "concept"
    elif result.tier == "related" and not has_rare and "relation" in channel_set:
        result.match = "relation"
    elif matched:
        result.match = "partial"
    # Mark the question's distinctive phrases, not light context ("công an nhân dân").
    keys = ({unit.text for unit, _ in plan.owners if unit.segment in plan.core_segments}
            | {f"phrase:{segment}" for segment in plan.core_segments}) \
        if plan.core_segments else None
    result.excerpt_start, result.excerpt_end, result.highlights = excerpt(
        text, occurrences, keys)
    return result


# ------------------------------------------------------------------ excerpt
def _boundary_before(text: str, position: int, limit: int) -> int:
    floor = max(0, position - limit)
    for marker in ("\n", ". ", "; ", ": "):
        found = text.rfind(marker, floor, position)
        if found >= 0:
            return found + len(marker)
    if floor == 0:
        return 0
    space = text.rfind(" ", floor, position)
    return space + 1 if space >= 0 else floor


def _boundary_after(text: str, position: int, ceiling: int) -> int:
    ceiling = min(len(text), ceiling)
    if ceiling >= len(text):
        return len(text)
    best = -1
    for marker in ("\n", ". ", "; "):
        found = text.find(marker, position, ceiling)
        if found >= 0 and (best < 0 or found < best):
            best = found + 1
    if best > 0:
        return best
    space = text.rfind(" ", position, ceiling)
    return space if space > position else ceiling


def excerpt(
    text: str, occurrences: Sequence[tuple[int, int, float, str]],
    highlight_keys: set[str] | None = None,
) -> tuple[int, int, list[tuple[int, int]]]:
    """Verbatim window around the densest phrase matches; highlights in text offsets."""

    length = len(text)
    if not occurrences:
        if length <= EXCERPT_MAX:
            return 0, length, []
        return 0, _boundary_after(text, EXCERPT_TARGET, EXCERPT_MAX), []
    phrase_spans = [(start, end) for start, end, _, _ in occurrences]
    if length <= EXCERPT_MAX:
        start, end = 0, length
    else:
        best: tuple[float, int] | None = None
        for anchor, _, _, _ in occurrences:
            window_end = anchor + EXCERPT_TARGET
            seen: set[str] = set()
            score = 0.0
            for start, end, weight, key in occurrences:
                if anchor <= start and end <= window_end and key not in seen:
                    seen.add(key)
                    score += weight
            if best is None or score > best[0] + 1e-9:
                best = (score, anchor)
        anchor = best[1] if best else occurrences[0][0]
        start = _boundary_before(text, anchor, 160)
        last = max((end for begin, end in phrase_spans
                    if begin >= anchor and end <= anchor + EXCERPT_TARGET), default=anchor)
        end = _boundary_after(text, max(last, start + 200), start + EXCERPT_MAX)
        if end <= start:
            end = min(length, start + EXCERPT_MAX)
    marked = [(s, e) for s, e, _, key in occurrences
              if highlight_keys is None or key in highlight_keys]
    highlights = _merge([(s, e) for s, e in marked if s >= start and e <= end])
    return start, end, highlights


def _merge(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged
