"""What a question asks about: its aspect (xử phạt, thủ tục, thẩm quyền, ...) and its subject.

"Xử phạt về nồng độ cồn" asks for *penalties* (aspect) about *nồng độ cồn* (subject).  A
clause on how to test alcohol levels shares the subject but not the aspect; it must not
be used to infer a penalty.  This module finds both parts without any model:

* aspects come from a fixed table of legal question types.  Each aspect lists the cue
  phrases that ask for it in a question and the cue phrases that show a clause actually
  regulates it.  The table names kinds of legal content, never a document, a number or
  a particular question;
* the subject is the question's own phrase segments (``storage/relevance.py``) with the
  aspect cue words removed.

A *strict* aspect is one where reading a clause about another aspect would invite a
made-up answer (a penalty, an amount, a deadline, an authority, a condition, an
effectivity status).  When no clause of the result set regulates a strict aspect, the
interpretation says so and does not ask a model to fill the gap.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from ..storage.relevance import analyze_terms, find_sequence, phrase_tokens, tokenize


@dataclass(frozen=True)
class Aspect:
    code: str
    label: str
    question_cues: tuple[str, ...]
    evidence_cues: tuple[str, ...]
    strict: bool

    def evidence_sequences(self) -> tuple[tuple[str, ...], ...]:
        return tuple(phrase_tokens(item) for item in self.evidence_cues)


ASPECTS: tuple[Aspect, ...] = (
    Aspect("muc_phat", "mức phạt",
           ("mức phạt", "phạt bao nhiêu", "bị phạt bao nhiêu", "mức xử phạt", "phạt tiền bao nhiêu",
            "số tiền phạt"),
           ("phạt tiền", "mức phạt", "mức xử phạt", "số tiền phạt", "đồng đến"), strict=True),
    Aspect("xu_phat", "xử phạt",
           ("xử phạt", "bị phạt", "phạt tiền", "chế tài", "hình thức xử phạt",
            "xử lý vi phạm hành chính"),
           ("xử phạt", "phạt tiền", "phạt cảnh cáo", "mức phạt", "hình thức xử phạt",
            "tước quyền sử dụng", "tịch thu", "biện pháp khắc phục hậu quả", "đình chỉ hoạt động"),
           strict=True),
    Aspect("vi_pham", "hành vi vi phạm, bị cấm",
           # A lone "cấm" is not asked here: in "đồ vật cấm" it names the subject.
           ("hành vi vi phạm", "hành vi bị cấm", "hành vi bị nghiêm cấm", "nghiêm cấm", "bị cấm"),
           ("nghiêm cấm", "bị cấm", "cấm", "không được", "hành vi", "vi phạm"), strict=True),
    Aspect("tham_quyen", "thẩm quyền, trách nhiệm",
           ("thẩm quyền", "cơ quan nào", "ai có quyền", "người có thẩm quyền", "ai quyết định",
            "trách nhiệm"),
           ("thẩm quyền", "có quyền", "quyết định", "trách nhiệm", "chủ trì", "giao"), strict=True),
    Aspect("thoi_han", "thời hạn",
           ("thời hạn", "bao lâu", "trong vòng", "thời gian", "hạn chót", "chậm nhất", "mấy ngày",
            "bao nhiêu ngày"),
           ("thời hạn", "ngày làm việc", "ngày kể từ", "chậm nhất", "trong vòng", "tháng kể từ",
            "trước ngày", "thời gian"), strict=True),
    Aspect("dieu_kien", "điều kiện, tiêu chuẩn",
           ("điều kiện", "tiêu chuẩn", "yêu cầu"),
           ("điều kiện", "tiêu chuẩn", "phải có", "đáp ứng", "yêu cầu"), strict=True),
    Aspect("hieu_luc", "hiệu lực",
           ("hiệu lực", "còn hiệu lực", "hết hiệu lực", "bãi bỏ", "thay thế", "áp dụng từ"),
           ("hiệu lực", "bãi bỏ", "thay thế", "thi hành kể từ"), strict=True),
    Aspect("thu_tuc", "trình tự, thủ tục",
           ("thủ tục", "trình tự", "quy trình", "các bước", "cách thức", "thực hiện như thế nào"),
           ("thủ tục", "trình tự", "quy trình", "hồ sơ", "đề nghị", "thẩm định", "xem xét",
            "tiếp nhận", "bước", "lấy ý kiến", "quyết định"), strict=False),
    Aspect("ho_so", "hồ sơ, giấy tờ",
           ("hồ sơ", "giấy tờ", "thành phần hồ sơ", "biểu mẫu"),
           ("hồ sơ", "giấy tờ", "bản sao", "đơn", "biểu mẫu", "mẫu số"), strict=False),
    Aspect("doi_tuong", "đối tượng, phạm vi áp dụng",
           ("đối tượng", "áp dụng cho", "áp dụng đối với", "phạm vi"),
           ("đối tượng", "áp dụng đối với", "phạm vi điều chỉnh", "áp dụng cho"), strict=False),
    Aspect("dinh_nghia", "khái niệm",
           ("là gì", "khái niệm", "được hiểu", "định nghĩa"),
           ("được hiểu", "giải thích từ ngữ", "là việc", "là hoạt động", "là người", "là cơ quan",
            "là tổ chức"), strict=False),
    Aspect("quyen_nghia_vu", "quyền, nghĩa vụ, nhiệm vụ",
           ("quyền và nghĩa vụ", "nghĩa vụ", "quyền hạn", "nhiệm vụ"),
           ("quyền", "nghĩa vụ", "nhiệm vụ", "trách nhiệm"), strict=False),
)
# "mức phạt" implies "xử phạt": the more specific aspect hides the general one.
_IMPLIES = {"muc_phat": "xu_phat"}


@dataclass(frozen=True)
class QuestionFocus:
    question: str
    aspects: tuple[Aspect, ...]
    subject: tuple[str, ...]  # phrase segments of the question without aspect cues
    accented: bool
    cue_tokens: frozenset[str] = field(default_factory=frozenset)

    @property
    def strict(self) -> bool:
        return any(item.strict for item in self.aspects)

    @property
    def aspect_label(self) -> str:
        return ", ".join(item.label for item in self.aspects)

    @property
    def subject_text(self) -> str:
        return ", ".join(self.subject)


def analyze_question(question: str) -> QuestionFocus:
    tokens = tokenize(question)
    terms = analyze_terms(question)
    found: list[Aspect] = []
    cue_spans: list[tuple[str, ...]] = []
    for aspect in ASPECTS:
        hits = [phrase_tokens(cue) for cue in aspect.question_cues
                if find_sequence(tokens, phrase_tokens(cue), folded=not terms.accented)]
        if hits:
            found.append(aspect)
            cue_spans.extend(hits)
    codes = {item.code for item in found}
    found = [item for item in found
             if not any(_IMPLIES.get(other) == item.code for other in codes)]
    subject: list[str] = []
    for segment in terms.segments:
        for part in _remove_cues(list(segment), cue_spans, folded=not terms.accented):
            text = " ".join(part)
            if text and text not in subject:
                subject.append(text)
    return QuestionFocus(
        question=question.strip(), aspects=tuple(found), subject=tuple(subject),
        accented=terms.accented,
        cue_tokens=frozenset(token for span in cue_spans for token in span),
    )


def _remove_cues(
    segment: list[str], cues: Sequence[tuple[str, ...]], *, folded: bool,
) -> list[list[str]]:
    from ..storage.relevance import fold_token

    def same(left: Sequence[str], right: Sequence[str]) -> bool:
        if folded:
            return [fold_token(item) for item in left] == [fold_token(item) for item in right]
        return list(left) == list(right)

    parts: list[list[str]] = []
    current: list[str] = []
    index = 0
    ordered = sorted(cues, key=len, reverse=True)
    while index < len(segment):
        cue = next((item for item in ordered
                    if same(segment[index:index + len(item)], item)), None)
        if cue is not None:
            if current:
                parts.append(current)
            current = []
            index += len(cue)
            continue
        current.append(segment[index])
        index += 1
    if current:
        parts.append(current)
    return parts


def aspects_in(focus: QuestionFocus, texts: Iterable[str]) -> set[str]:
    """Codes of the question's aspects that one of ``texts`` (clause, Điều title) regulates."""

    if not focus.aspects:
        return set()
    token_sets = [tokenize(text) for text in texts if text]
    matched: set[str] = set()
    for aspect in focus.aspects:
        for sequence in aspect.evidence_sequences():
            if any(find_sequence(item, sequence) for item in token_sets):
                matched.add(aspect.code)
                break
    return matched


def mentions_focus(focus: QuestionFocus, text: str) -> bool:
    """The text names part of the subject or an aspect of the question (accent-insensitive)."""

    tokens = tokenize(text)
    for phrase in focus.subject:
        words = phrase_tokens(phrase)
        pairs = [words[i:i + 2] for i in range(len(words) - 1)] or [words]
        if any(find_sequence(tokens, pair, folded=True) for pair in pairs):
            return True
    for aspect in focus.aspects:
        for cue in (*aspect.question_cues, *aspect.evidence_cues):
            sequence = phrase_tokens(cue)
            if len(sequence) >= 2 or len(focus.subject) == 0:
                if find_sequence(tokens, sequence, folded=True):
                    return True
    return False
