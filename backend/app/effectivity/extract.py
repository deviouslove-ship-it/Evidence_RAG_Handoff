"""Rule-based reading of dates and effectivity relations from approved node text.

Rules only propose: every relation found here is stored as a draft that a
reviewer must approve (design §9).  Sentences that mention a relation in a way the
rules cannot read are returned as candidates for the optional AI stage
``relation``; they are never turned into relations by code.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

from ..vietnamese_nlp.unicode_norm import canonical_document_number, unicode_nfc

TYPE_WORDS: dict[str, str] = {
    "bộ luật": "law", "luật": "law", "pháp lệnh": "ordinance", "nghị quyết": "resolution",
    "nghị định": "decree", "thông tư liên tịch": "joint_circular", "thông tư": "circular",
    "quyết định": "decision", "chỉ thị": "directive", "văn bản hợp nhất": "consolidated",
}
_TYPE_ALT = "|".join(
    sorted((re.escape(word) for word in TYPE_WORDS), key=len, reverse=True)
)
_NUMBER = r"\d{1,5}[a-z]?/(?:\d{4}/)?[A-ZĐÐ][0-9A-Za-zĐđÐ&\-]*(?:\([0-9A-Za-zĐđ]+\))?"
_DATE_WORDS = (
    r"(?P<d>\d{1,2})\s*tháng\s*(?P<m>\d{1,2})\s*năm\s*(?P<y>\d{4})"
    r"|(?P<d2>\d{1,2})[/.\-](?P<m2>\d{1,2})[/.\-](?P<y2>\d{4})"
)
DOC_REF = re.compile(
    rf"(?P<type>{_TYPE_ALT})\s+(?:(?P<so>số)\s+)?(?P<number>{_NUMBER})"
    rf"(?:\s+(?P<ngay>ngày\s+)?(?:{_DATE_WORDS}))?",
    re.IGNORECASE,
)
_DATE = re.compile(_DATE_WORDS, re.IGNORECASE)
_EFFECTIVE = re.compile(
    rf"(?P<subj>{_TYPE_ALT}|quy chế|quy định|nội quy)\s+này\s+có\s+hiệu\s+lực"
    r"(?:\s+thi\s+hành)?(?:\s+(?:kể\s+)?từ\s+ngày\s+(?:(?P<sign>ký)|"
    + _DATE_WORDS + r"))",
    re.IGNORECASE,
)
_NODE_EFFECTIVE = re.compile(
    r"(?P<path>(?:(?:(?:điểm|khoản|điều)\s+[0-9a-zđ]+(?:\s*(?:,|;|và)\s*|\s+))*?"
    r"(?:điểm\s+[a-zđ]\s+)?(?:khoản\s+\d+\s+)?Điều\s+\d+[a-z]?))"
    r"(?:\s+(?:của|tại)\s+[^.;]{0,180}?)?\s+có\s+hiệu\s+lực(?:\s+thi\s+hành)?"
    r"\s+(?:kể\s+)?từ\s+ngày\s+(?:" + _DATE_WORDS + r")",
    re.IGNORECASE,
)
_ISSUE = re.compile(
    r",\s*ngày\s+(?P<d>\d{1,2})\s*tháng\s*(?P<m>\d{1,2})\s*năm\s*(?P<y>\d{4})", re.IGNORECASE
)
_BODY = re.compile(
    r"^\s*(BỘ\s+[A-ZÀ-Ỹ][A-ZÀ-Ỹ ,]{2,60}?|CHÍNH PHỦ|THỦ TƯỚNG CHÍNH PHỦ|QUỐC HỘI"
    r"|ỦY BAN THƯỜNG VỤ QUỐC HỘI)(?=\s+(?:Số|CỘNG|-|$))",
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.:])\s+(?=[\"“A-ZĐÀ-Ỹ0-9])")
# Cited parts right before "[của|tại] <document>": "Khoản 1 Điều 2; Điều 4; Mẫu TK7 của".
_UNIT_ID = (
    r"(?:(?:Điều|[Kk]hoản)\s+\d+[a-z]?\b|[Đđ]iểm\s+[a-zđ]\b"
    r"|(?:Mẫu|Phụ lục|Chương|Mục)\s+(?:số\s+)?[0-9A-ZĐ][0-9A-Za-zđ\-]*\b)"
)
_PATH_BEFORE = re.compile(
    rf"((?:{_UNIT_ID}(?:\s*(?:,|;|và)\s*(?:\d+[a-z]?\b|[a-zđ]\b)?\s*|\s+))+)"
    r"(?:(?:của|tại|ban\s+hành\s+kèm\s+theo)\s*)?$"
)
# A subject position: sentence start, list number, "và", comma or semicolon (with optional "Các").
_SUBJECT_BEFORE = re.compile(r"(?:^|\d+[a-z]?\.|\bvà|,|;)\s*(?:các\s+)?$", re.IGNORECASE)
_CONDITION = re.compile(
    r"trừ\s+trường\s+hợp|cho\s+đến\s+khi|đến\s+hết\s+ngày|chuyển\s+tiếp"
    r"|tiếp\s+tục\s+(?:được\s+)?(?:áp\s+dụng|thực\s+hiện|sử\s+dụng)|trong\s+thời\s+hạn",
    re.IGNORECASE,
)
_RELATION_WORDS = re.compile(
    r"bãi\s+bỏ|thay\s+thế|hết\s+hiệu\s+lực|sửa\s+đổi|bổ\s+sung|ngưng\s+hiệu\s+lực",
    re.IGNORECASE,
)
_OWN_EFFECTIVE = re.compile(
    rf"kể\s+từ\s+ngày\s+(?:{_TYPE_ALT})\s+này\s+có\s+hiệu\s+lực", re.IGNORECASE
)
# "thay thế một phần / một số điều của <văn bản>": the replaced Điều is not named.
_PARTIAL_REPLACE_BEFORE = re.compile(
    r"(?:thay\s+thế|thay\s+cho)\s+(?:cho\s+)?"
    r"(?:một\s+phần|một\s+số\s+(?:điều|khoản|điểm|nội\s+dung|quy\s+định))"
    r"(?:\s+(?:các\s+)?(?:điều|khoản|điểm|nội\s+dung|quy\s+định))?(?:\s+(?:của|tại))?$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class NodeText:
    node_id: str
    node_type: str
    path: str
    text: str
    page: int | None = None
    parent_id: str | None = None


@dataclass(frozen=True)
class DocRef:
    type_word: str
    doc_type: str
    number: str
    number_key: str
    issue_date: date | None
    start: int
    end: int
    strict_row: bool = False


@dataclass(frozen=True)
class RelationProposal:
    source_node_id: str
    action: str
    scope: str
    target: DocRef | None
    target_path: str | None
    valid_from: date | None
    from_own_effective: bool
    condition: str | None
    quote: str
    page: int | None
    confidence: float
    key: str
    source_path: str | None = None
    quote_node_id: str | None = None


@dataclass(frozen=True)
class ReferenceProposal:
    source_node_id: str
    kind: str
    target: DocRef
    quote: str
    key: str


@dataclass(frozen=True)
class DatesDetected:
    issue_date: date | None = None
    issue_quote: str | None = None
    effective_from: date | None = None
    effective_quote: str | None = None
    effective_on_signing: bool = False
    issuing_body: str | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "issue_date": self.issue_date.isoformat() if self.issue_date else None,
            "issue_quote": self.issue_quote,
            "effective_from": self.effective_from.isoformat() if self.effective_from else None,
            "effective_quote": self.effective_quote,
            "effective_on_signing": self.effective_on_signing,
            "issuing_body": self.issuing_body,
        }


@dataclass
class Extraction:
    relations: list[RelationProposal] = field(default_factory=list)
    references: list[ReferenceProposal] = field(default_factory=list)
    ai_candidates: list[tuple[str, str]] = field(default_factory=list)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", unicode_nfc(text)).strip()


def _date_from(match: re.Match[str]) -> date | None:
    groups = match.groupdict()
    day, month, year = (
        (groups.get("d"), groups.get("m"), groups.get("y"))
        if groups.get("d") else (groups.get("d2"), groups.get("m2"), groups.get("y2"))
    )
    if not day or not month or not year:
        return None
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


def number_key(number: str) -> str:
    return canonical_document_number(number.replace("Ð", "Đ"))


def find_doc_refs(text: str) -> list[DocRef]:
    refs: list[DocRef] = []
    for match in DOC_REF.finditer(text):
        word = match.group("type").lower()
        number = match.group("number").rstrip("-")
        doc_type = TYPE_WORDS.get(word, "other")
        if "VBHN" in number.upper():
            doc_type = "consolidated"
        has_date = bool(match.group("d") or match.group("d2"))
        refs.append(DocRef(
            type_word=match.group("type"), doc_type=doc_type, number=number,
            number_key=number_key(number), issue_date=_date_from(match),
            start=match.start(), end=match.end(),
            strict_row=has_date and not match.group("so") and not match.group("ngay"),
        ))
    return refs


def is_consolidated(document_number: str | None, title: str) -> bool:
    return "VBHN" in (document_number or "").upper() or title.lower().startswith(
        "văn bản hợp nhất"
    )


def is_repeal_list(title: str, first_text: str) -> bool:
    head = f"{title} {first_text[:600]}".lower()
    return "danh mục" in head and "hết hiệu lực" in head


def detect_dates(nodes: Sequence[NodeText], *, doc_type: str, consolidated: bool) -> DatesDetected:
    """Issue date and issuing body from the header; effective date from "X này có hiệu lực"."""

    if not nodes:
        return DatesDetected()
    header = _clean(nodes[0].text)[:700]
    issue = _ISSUE.search(header)
    issue_date = _date_from(issue) if issue else None
    body = _BODY.match(header)
    issuing_body = body.group(1).strip().title() if body else None
    if consolidated:
        return DatesDetected(
            issue_date=None, issue_quote=None, issuing_body=issuing_body,
        )
    own_word = next((word for word, code in TYPE_WORDS.items() if code == doc_type), None)
    fallback: tuple[re.Match[str], str] | None = None
    for node in nodes:
        text = _clean(node.text)
        for match in _EFFECTIVE.finditer(text):
            subject = match.group("subj").lower()
            if own_word is None or subject == own_word:
                return _effective_result(match, text, issue_date, issue, header, issuing_body)
            if fallback is None:
                fallback = (match, text)
    if fallback is not None:
        return _effective_result(
            fallback[0], fallback[1], issue_date, issue, header, issuing_body
        )
    return DatesDetected(
        issue_date=issue_date, issue_quote=issue.group(0).strip(", ") if issue else None,
        issuing_body=issuing_body,
    )


def _effective_result(
    match: re.Match[str], text: str, issue_date: date | None, issue: re.Match[str] | None,
    header: str, issuing_body: str | None,
) -> DatesDetected:
    on_signing = bool(match.group("sign"))
    effective = issue_date if on_signing else _date_from(match)
    return DatesDetected(
        issue_date=issue_date,
        issue_quote=issue.group(0).strip(", ") if issue else None,
        effective_from=effective,
        effective_quote=_window(text, match.start(), match.end()),
        effective_on_signing=on_signing,
        issuing_body=issuing_body,
    )


def _window(text: str, start: int, end: int, size: int = 160) -> str:
    return text[max(0, start - size):min(len(text), end + size)].strip()


def _sentences(text: str) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    offset = 0
    for part in _SENTENCE_SPLIT.split(text):
        index = text.find(part, offset)
        result.append((index, part))
        offset = index + len(part)
    return result


def _context_verb(article_text: str) -> str | None:
    head = article_text[:500].lower()
    if "bãi bỏ một phần" in head or "bãi bỏ một số" in head:
        return "repeal_partial"
    if (
        "bãi bỏ toàn bộ" in head
        or re.search(r"bãi\s+bỏ[^.]{0,200}sau\s+đây", head)
        or re.search(r"sau\s+đây[^.]{0,160}(?:bị\s+)?bãi\s+bỏ", head)
    ):
        return "repeal"
    if (
        re.search(r"hết\s+hiệu\s+lực[^.]{0,160}sau\s+đây", head)
        or re.search(r"sau\s+đây[^.]{0,160}hết\s+hiệu\s+lực", head)
    ):
        return "repeal"
    if (
        re.search(r"ngưng\s+hiệu\s+lực[^.]{0,200}sau\s+đây", head)
        or re.search(r"sau\s+đây[^.]{0,160}ngưng\s+hiệu\s+lực", head)
    ):
        return "suspend"
    return None


_SOURCE_PATH_ACTIVE = re.compile(
    rf"(?P<src>(?:{_UNIT_ID}(?:\s*(?:,|;|và)\s*(?:\d+[a-z]?\b|[a-zđ]\b)?\s*|\s+))+)"
    rf"(?:(?:của|tại)\s+(?:{_TYPE_ALT}|quy chế|quy định)\s+này\s+|(?:{_TYPE_ALT})\s+này\s+)?"
    r"(?:thay\s+thế|thay\s+cho|sửa\s+đổi(?:,\s*bổ\s+sung)?|bổ\s+sung)\s*(?:cho\s+)?"
    r"(?:(?:các\s+)?(?:quy\s+định|nội\s+dung)\s*(?:tại|của)?\s*)?$",
    re.IGNORECASE,
)
_SOURCE_PATH_PASSIVE = re.compile(
    r"\b(?:bị|được)\s+(?:thay\s+thế|sửa\s+đổi(?:,\s*bổ\s+sung)?|bổ\s+sung)"
    r"\s+(?:bởi|bằng)\s+(?:(?:các\s+)?(?:quy\s+định|nội\s+dung)\s+(?:tại|của)\s+)?"
    rf"(?P<src>(?:{_UNIT_ID}(?:\s*(?:,|;|và)\s*(?:\d+[a-z]?\b|[a-zđ]\b)?\s*|\s+))+)"
    rf"(?!\s*(?:của|tại)\s+(?:{_TYPE_ALT})\s+(?:số\s+)?{_NUMBER})",
    re.IGNORECASE,
)


def _strip_doc_refs_and_conjunctions(text: str) -> str:
    """Remove earlier document references, their target paths, and conjunctions."""
    stripped = text
    while True:
        match = DOC_REF.search(stripped)
        if not match:
            break
        cut_start = match.start()
        prefix = stripped[:cut_start]
        prior_path = _PATH_BEFORE.search(prefix)
        if prior_path is not None:
            cut_start = prior_path.start()
        tail = stripped[match.end():]
        conj = re.search(r"(?:\s*(?:,|;|và)\s*)", tail, re.IGNORECASE)
        if conj:
            stripped = stripped[:cut_start] + tail[conj.end():]
        else:
            stripped = stripped[:cut_start] + " " + tail
    return stripped


def _extract_explicit_source_path(sentence: str, ref_start: int, ref_end: int) -> str | None:
    """Extract 'Điều A' / 'Khoản X Điều Y' when stated as the replacing/amending source unit."""
    raw_before = sentence[max(0, ref_start - 300):ref_start]
    clean_before = re.sub(r"\([^()]*\)", " ", raw_before)
    path_match = _PATH_BEFORE.search(clean_before)
    prefix_before_path = (
        clean_before[:path_match.start()] if path_match is not None else clean_before
    )
    collapsed = _strip_doc_refs_and_conjunctions(prefix_before_path).rstrip(" :,")
    active = _SOURCE_PATH_ACTIVE.search(collapsed)
    if active is not None:
        return active.group("src").strip(" ,;")
    after = sentence[ref_end:ref_end + 220]
    passive = _SOURCE_PATH_PASSIVE.search(after)
    if passive is not None:
        return passive.group("src").strip(" ,;")
    return None


def _infer_node_source_path(node: NodeText, by_id: dict[str, NodeText]) -> str | None:
    """Infer human-readable source path (e.g. 'khoản 1 Điều 2' or 'Điều 4') from node hierarchy."""
    text = _clean(node.text)
    if node.node_type == "article":
        m = re.match(r"^(Điều\s+\d+[a-z]?)\b", text, re.IGNORECASE)
        return m.group(1) if m else None
    if node.node_type in {"clause", "point"}:
        parent = by_id.get(node.parent_id or "")
        article = parent if (parent and parent.node_type == "article") else (
            by_id.get(parent.parent_id or "") if parent else None
        )
        art_match = (
            re.match(r"^(Điều\s+\d+[a-z]?)\b", _clean(article.text), re.IGNORECASE)
            if article else None
        )
        art_label = art_match.group(1) if art_match else None
        cl_match = re.match(r"^(\d+[a-z]?)\.\s+", text)
        if cl_match and art_label:
            return f"khoản {cl_match.group(1)} {art_label}"
        return art_label
    return None


def _resolve_source_node_in_tree(
    source_path: str | None, fallback_node: NodeText, all_nodes: Sequence[NodeText],
) -> NodeText:
    """Resolve explicit source_path (e.g. 'Điều 4') to its NodeText in all_nodes if present."""
    if not source_path:
        return fallback_node
    expanded = _paths(source_path) or [source_path]
    target = expanded[0]
    m = re.search(
        r"(?:điểm\s+(?P<point>[a-zđ])\s+)?(?:khoản\s+(?P<clause>\d+[a-z]?)\s+)?"
        r"Điều\s+(?P<article>\d+[a-z]?)\b",
        target,
        re.IGNORECASE,
    )
    if m is None:
        return fallback_node
    art_num = m.group("article").lower()
    clause_num = m.group("clause").lower() if m.group("clause") else None
    point_let = m.group("point").lower() if m.group("point") else None
    segments = [f"dieu:{art_num}"]
    if clause_num:
        segments.append(f"khoan:{clause_num}")
    if point_let:
        segments.append(f"diem:{point_let}")
    suffix = "/".join(segments)
    pattern = re.compile(rf"(?:^|[:/]){re.escape(suffix)}$", re.IGNORECASE)
    for cand in all_nodes:
        if pattern.search(cand.path):
            return cand
    if not clause_num and not point_let:
        art_prefix = re.compile(rf"^Điều\s+{re.escape(art_num)}\b", re.IGNORECASE)
        for cand in all_nodes:
            if cand.node_type == "article" and art_prefix.search(_clean(cand.text)):
                return cand
    return fallback_node


def _classify(sentence: str, ref_start: int, ref_end: int) -> tuple[str | None, str | None]:
    """(action or reference kind, target path) for one reference inside one sentence."""

    raw_before = sentence[max(0, ref_start - 300):ref_start]
    before = raw_before.lower()
    after = sentence[ref_end:].lower()
    if sentence.lstrip().lower().startswith("căn cứ"):
        return "ref:basis", None
    if re.search(r"này\s+(?:quy\s+định\s+chi\s+tiết|hướng\s+dẫn)", before):
        return "ref:guidance", None
    if re.search(r"thay\s+thế\s+(?:cụm\s+)?từ", sentence.lower()):
        return None, None
    # Ignore references inside parenthetical amendment notes: "(đã được sửa đổi tại Thông tư B)"
    if raw_before.count("(") > raw_before.count(")"):
        return None, None
    # Ignore historical amendment chains: "... đã được sửa đổi, bổ sung tại/theo Thông tư B"
    if re.search(
        r"(?:đã\s+)?được\s+(?:sửa\s+đổi|bổ\s+sung)[^.;()]{0,140}(?:tại|theo|bởi|bằng)\s+[^.;()]{0,160}$",
        before,
    ):
        return None, None
    # Ignore the actor after "bởi"/"bằng" in passive constructions:
    # "Thông tư A được thay thế bởi Thông tư B"
    if re.search(
        r"\b(?:bị|được)\s+(?:thay\s+thế|sửa\s+đổi|bổ\s+sung|bãi\s+bỏ|ngưng\s+hiệu\s+lực)"
        r"[^.;]{0,80}\b(?:bởi|bằng)\s+[^.;]{0,100}$",
        before,
    ):
        return None, None

    clean_before = re.sub(r"\([^()]*\)", " ", raw_before)
    clean_before_lower = clean_before.lower()
    path_match = _PATH_BEFORE.search(clean_before)
    path = path_match.group(1).strip(" ,;") if path_match else None
    prefix_before_path = (
        clean_before[:path_match.start()] if path_match is not None else clean_before
    )
    collapsed_before = _strip_doc_refs_and_conjunctions(prefix_before_path).lower()

    # No Điều is named, so the target node is left for the reviewer to choose: this is
    # neither "modify" nor a replacement of the whole document.
    if not path and _PARTIAL_REPLACE_BEFORE.search(clean_before_lower.rstrip(" :,")):
        return "replace_partial", None
    if re.search(
        r"(?:thay\s+thế|thay\s+cho)\s*(?:cho\s+)?"
        r"(?:(?:các\s+)?(?:quy\s+định|nội\s+dung)\s*(?:tại|của)?\s*)?$",
        collapsed_before.rstrip(" :,"),
    ):
        return "replace", path
    if re.search(r"\b(?:bị|được)\s+thay\s+thế", after[:200]):
        if not path and re.search(
            r"(?:một\s+phần|một\s+số\s+(?:điều|khoản|điểm|nội\s+dung|quy\s+định))",
            clean_before_lower,
        ):
            return "replace_partial", None
        return "replace", path
    if re.search(r"bãi\s+bỏ", clean_before_lower):
        if path or re.search(
            r"bãi\s+bỏ\s+(?:một\s+số|một\s+phần|nội\s+dung|quy\s+định\s+tại|(?:cụm\s+)?từ)",
            clean_before_lower,
        ):
            return "repeal_partial", path
        return "repeal", None
    # "<document> [và <document>] ... hết hiệu lực [kể từ ngày X này có hiệu lực]".
    subject = _SUBJECT_BEFORE.search(collapsed_before)
    if re.search(r"hết\s+hiệu\s+lực", after) and (subject or path):
        if path or re.search(
            r"(?:một\s+số|một\s+phần)\s+(?:điều|khoản|điểm|nội\s+dung|quy\s+định)",
            clean_before_lower,
        ):
            return "repeal_partial", path
        return ("replace" if _OWN_EFFECTIVE.search(after) else "repeal"), None
    if re.search(r"ngưng\s+hiệu\s+lực", clean_before_lower):
        return "suspend", path
    # The amending verb must belong to this document ("Sửa đổi ... của <ref>" at the
    # start of a heading, item or sentence; "X này sửa đổi"), not to a cited title.
    if re.search(
        r"(?:^|[.:;]\s+|\d+[a-z]?\.\s+|[a-zđ]\)\s+|này\s+|ban\s+hành\s+\w+(?:\s+\w+)?\s+)"
        r"(?:sửa\s+đổi|bổ\s+sung|thay\s+thế\s+(?:cụm\s+)?từ)[^.;]{0,240}$",
        clean_before_lower,
    ):
        return "modify", path
    return None, None


def extract_relations(
    nodes: Sequence[NodeText],
    *,
    own_number_key: str | None,
    title: str,
    document_number: str | None,
    effective_from: date | None,
) -> Extraction:
    """Document-level and node-targeted relations and references read from the source document."""

    result = Extraction()
    if not nodes:
        return result
    consolidated = is_consolidated(document_number, title)
    repeal_list = is_repeal_list(title, nodes[0].text)
    partial_list = repeal_list and "một phần" in f"{title} {nodes[0].text[:600]}".lower()
    by_id = {node.node_id: node for node in nodes}
    amendment_items = node_amendment_items(nodes, own_number_key=own_number_key)
    node_item_keys = {
        (item_node.node_id, ref.number_key) for item_node, ref, _, _ in amendment_items
    }
    # A heading such as "Thay thế một số điều của Thông tư X như sau" whose items name
    # the Điều is already covered by those item proposals.
    covered_by_items = {
        (ancestor, ref.number_key)
        for item_node, ref, _, _ in amendment_items
        for ancestor in _ancestor_ids(item_node, by_id)
    }
    seen: set[str] = set()
    first_article_seen = False
    # The articles state relations with their dates; the preamble repeats them, so
    # it is read last and only adds what the articles did not say.
    if not consolidated:
        nodes = [
            *(node for node in nodes if node.node_type != "paragraph"),
            *(node for node in nodes if node.node_type == "paragraph"),
        ]
    for node in nodes:
        text = _clean(node.text)
        if node.node_type == "article":
            first_article_seen = True
        refs = [ref for ref in find_doc_refs(text) if ref.number_key != own_number_key]
        if not refs:
            continue
        if consolidated:
            # Văn bản hợp nhất: the header lists the base and amending documents.
            if not first_article_seen:
                for ref in refs:
                    _add_reference(result, seen, node, "consolidation", ref, text)
            continue
        if repeal_list:
            for ref in refs:
                if not ref.strict_row:
                    continue
                _add_relation(
                    result, seen, node, "repeal_partial" if partial_list else "repeal",
                    ref, None, None, False, None, _window(text, ref.start, ref.end), 0.5,
                )
            continue
        context: str | None = None
        if node.node_type != "article":
            parent = by_id.get(node.parent_id or "")
            while parent is not None and context is None:
                context = _context_verb(_clean(parent.text))
                parent = by_id.get(parent.parent_id or "")
        if context and node.node_type in {"clause", "point"}:
            # A list item under "Bãi bỏ ... sau đây:": the first document is the
            # target; later ones belong to its title ("... sửa đổi Thông tư Y").
            ref = refs[0]
            if ref.start < 40:
                stated = bool(item_dates(text))
                _add_relation(
                    result, seen, node, context, ref, None,
                    item_valid_from(text, effective_from),
                    effective_from is not None and not stated, None, text[:1200], 0.9,
                )
                continue
        for sentence_start, sentence in _sentences(text):
            sentence_refs = [
                ref for ref in refs
                if sentence_start <= ref.start < sentence_start + len(sentence)
            ]
            for ref in sentence_refs:
                start = ref.start - sentence_start
                end = ref.end - sentence_start
                verdict, path = _classify(sentence, start, end)
                partial_replace = verdict == "replace_partial"
                if partial_replace:
                    if (node.node_id, ref.number_key) in covered_by_items:
                        continue
                    verdict = "replace"
                if verdict is None:
                    if _RELATION_WORDS.search(sentence):
                        result.ai_candidates.append((node.node_id, sentence[:1200]))
                    continue
                if verdict.startswith("ref:"):
                    _add_reference(result, seen, node, verdict[4:], ref, sentence)
                    continue
                # Avoid creating a duplicate proposal on a clause/point node when the
                # parent article already registered the document-level relation and
                # node_amendment_items extracts the clause-level item.
                if (
                    node.node_type in {"clause", "point"}
                    and (node.node_id, ref.number_key) in node_item_keys
                    and f"modify|{ref.number_key}|" in seen
                    and verdict in {"modify", "add", "repeal_partial", "suspend", "replace"}
                ):
                    continue
                explicit_src = _extract_explicit_source_path(sentence, start, end)
                src_node = _resolve_source_node_in_tree(explicit_src, node, nodes)
                src_path = explicit_src or _infer_node_source_path(src_node, by_id)
                explicit = _explicit_date(sentence, ref, span=(start, end))
                own = explicit is None and effective_from is not None
                condition = sentence[:600] if _CONDITION.search(sentence) else None
                confidence = (
                    0.7 if partial_replace else 0.9 if verdict in {"repeal", "replace"} else 0.8
                )
                # "Điều 3 và Điều 4": one relation per target unit (the source stays the
                # group; its units are not paired with the targets).
                for target_path in _split_target_paths(path):
                    _add_relation(
                        result, seen, src_node, verdict, ref, target_path,
                        explicit or (effective_from if own else None), own, condition,
                        sentence[:1200], confidence,
                        source_path=src_path, quote_node_id=node.node_id,
                        quote_page=node.page, partial=partial_replace,
                    )
    return result


def _explicit_date(
    sentence: str, ref: DocRef, *, span: tuple[int, int] | None = None,
) -> date | None:
    """A "từ ngày D" in the sentence that is not the referenced document's own date.

    ``span`` is the reference's (start, end) *inside* ``sentence``.  ``ref.start`` and
    ``ref.end`` are offsets in the whole node text, so they must not be compared with
    offsets in the sentence (a sentence that is not first in its node shifted them and
    made the date look like it belonged to the reference, losing the stated date).
    """

    ref_start, ref_end = span if span is not None else (ref.start, ref.end)
    match: re.Match[str] | None = None
    for found in re.finditer(r"(?:kể\s+)?từ\s+ngày\s+(?:" + _DATE_WORDS + r")", sentence, re.I):
        if found.start() >= ref_end or found.end() <= ref_start:
            match = found
            break
    return _date_from(match) if match else None


def _same_statement(
    prior: RelationProposal, source_path: str | None, valid_from: date | None, own: bool,
) -> bool:
    """True when ``prior`` is the same statement (same source unit and stated date)."""

    if (
        prior.source_path and source_path
        and prior.source_path.lower() != source_path.lower()
    ):
        return False
    return not (
        not own and not prior.from_own_effective
        and prior.valid_from is not None and valid_from is not None
        and prior.valid_from != valid_from
    )


# Actions that, with a named Điều/Khoản/Điểm, apply to that node rather than the document.
_NODE_SCOPE_ACTIONS = frozenset({"replace", "suspend", "modify", "repeal_partial"})


def _ancestor_ids(node: NodeText, by_id: dict[str, NodeText]) -> list[str]:
    ids: list[str] = []
    parent = by_id.get(node.parent_id or "")
    while parent is not None and parent.node_id not in ids:
        ids.append(parent.node_id)
        parent = by_id.get(parent.parent_id or "")
    return ids


def _split_target_paths(path: str | None) -> list[str | None]:
    """"Điều 3 và Điều 4" -> ["Điều 3", "Điều 4"]; a single unit or an annex is kept as is."""

    if not path or _ANNEX_UNIT.search(path):
        return [path]
    expanded = _paths(path)
    return list(expanded) if len(expanded) > 1 else [path]


def _add_relation(
    result: Extraction, seen: set[str], node: NodeText, action: str,
    ref: DocRef, path: str | None, valid_from: date | None, own: bool,
    condition: str | None, quote: str, confidence: float,
    *,
    source_path: str | None = None,
    quote_node_id: str | None = None,
    quote_page: int | None = None,
    partial: bool = False,
) -> None:
    base_key = f"{action}|{ref.number_key}|{(path or '').lower()}"
    if partial:
        # Target unit not named: never the same statement as a whole-document relation.
        base_key += "|partial"
    key = base_key
    if base_key in seen:
        priors = [
            item for item in result.relations if item.key.split("|src=", 1)[0] == base_key
        ]
        if any(_same_statement(item, source_path, valid_from, own) for item in priors):
            return
        # A different source unit or a different stated date is a different relation:
        # keep it under a distinct key (the plain key stays unchanged for old rows).
        key = (
            f"{base_key}|src={(source_path or node.node_id).lower()}"
            f"|from={valid_from.isoformat() if valid_from else ''}"
        )
        if key in seen:
            return
    seen.add(base_key)
    seen.add(key)
    scope = "node" if (partial or (path and action in _NODE_SCOPE_ACTIONS)) else "document"
    result.relations.append(RelationProposal(
        source_node_id=node.node_id, action=action, scope=scope, target=ref,
        target_path=path, valid_from=valid_from, from_own_effective=own,
        condition=condition, quote=quote,
        page=quote_page if quote_page is not None else node.page,
        confidence=confidence, key=key,
        source_path=source_path, quote_node_id=quote_node_id or node.node_id,
    ))


def _add_reference(
    result: Extraction, seen: set[str], node: NodeText, kind: str, ref: DocRef,
    quote: str,
) -> None:
    key = f"ref:{kind}|{ref.number_key}"
    if key in seen:
        return
    seen.add(key)
    result.references.append(ReferenceProposal(
        source_node_id=node.node_id, kind=kind, target=ref,
        quote=_window(quote, ref.start, ref.end) if len(quote) > 600 else quote, key=key,
    ))


_ITEM_VERB = re.compile(
    r"(sửa\s+đổi,\s*bổ\s+sung|sửa\s+đổi|bổ\s+sung|bãi\s+bỏ|thay\s+thế\s+(?:cụm\s+)?từ|"
    r"thay\s+thế|đình\s+chỉ|ngưng\s+hiệu\s+lực)",
    re.IGNORECASE,
)
_ITEM_ACTIONS = {
    "sửa đổi, bổ sung": "modify", "sửa đổi": "modify", "bổ sung": "add", "bãi bỏ": "repeal",
    "thay thế từ": "modify", "thay thế cụm từ": "modify", "thay thế": "replace",
    "đình chỉ": "suspend", "ngưng hiệu lực": "suspend",
}
_ANNEX_UNIT = re.compile(
    r"\b(?:Phụ\s+lục|Mẫu|Chương|Mục)\s+(?:số\s+)?[0-9IVXLC][0-9A-Za-zđ\-]*", re.IGNORECASE
)
_PART_TOKEN = re.compile(r"\b(điểm|khoản|điều)\s+(\d+[a-z]?|[a-zđ])\b", re.IGNORECASE)
_QUOTE_BLOCK = re.compile(r"“[^”]*”|\"[^\"]*\"")


def _paths(segment: str) -> list[str]:
    """'khoản 1, khoản 2 và khoản 3 Điều 7' -> ['khoản 1 Điều 7', 'khoản 2 Điều 7', ...]."""

    paths: list[str] = []
    points: list[str] = []
    clauses: list[tuple[str, list[str]]] = []
    for kind, value in _PART_TOKEN.findall(segment):
        kind = kind.lower()
        if kind == "điểm":
            points.append(value.lower())
        elif kind == "khoản":
            clauses.append((value, points))
            points = []
        else:
            if clauses:
                for clause, clause_points in clauses:
                    if clause_points:
                        paths += [f"điểm {p} khoản {clause} Điều {value}" for p in clause_points]
                    else:
                        paths.append(f"khoản {clause} Điều {value}")
            elif points:
                paths += [f"điểm {p} Điều {value}" for p in points]
            else:
                paths.append(f"Điều {value}")
            clauses, points = [], []
    return list(dict.fromkeys(paths))


def parse_amend_item(text: str) -> list[tuple[str, str]]:
    """Read one amending item ("2. Sửa đổi khoản 2 Điều 4 như sau: ...").

    Returns (action, target path) pairs.  For "Bổ sung X vào Y" the target is the
    container Y (the new parts do not exist in the amended document yet).
    """

    head = _clean(text)
    head = re.sub(r"^\d+[a-z]?\.\s*", "", head)
    head = re.sub(r"^[a-zđ]\)\s*", "", head)
    head = re.sub(r"^Điều\s+\d+[a-z]?[.:]\s*", "", head, flags=re.IGNORECASE)
    cut = re.search(r"\bnhư\s+sau\b", head, re.IGNORECASE)
    if cut:
        head = head[: cut.start()]
    head = _QUOTE_BLOCK.sub(" ", head)
    head = head.split("“", 1)[0]
    # Trim any trailing document reference ("... của Thông tư số 55/2021/TT-BCA ...")
    doc_ref_match = DOC_REF.search(head)
    if doc_ref_match is not None:
        head = head[:doc_ref_match.start()]
    # Strip leading source unit in active voice: "Điều A [của Thông tư này] thay thế Điều B"
    head = re.sub(
        rf"^(?:{_UNIT_ID}(?:\s*(?:,|;|và)\s*(?:\d+[a-z]?\b|[a-zđ]\b)?\s*|\s+))+"
        rf"(?:(?:của|tại)\s+(?:{_TYPE_ALT}|quy chế|quy định)\s+này\s+|(?:{_TYPE_ALT})\s+này\s+)?"
        r"(?=(?:thay\s+thế|sửa\s+đổi|bổ\s+sung|bãi\s+bỏ|đình\s+chỉ|ngưng\s+hiệu\s+lực)\b)",
        "",
        head,
        flags=re.IGNORECASE,
    )
    verbs = list(_ITEM_VERB.finditer(head))
    if not verbs or verbs[0].start() > 3:
        return []
    found: list[tuple[str, str]] = []
    for index, verb in enumerate(verbs):
        end = verbs[index + 1].start() if index + 1 < len(verbs) else len(head)
        segment = head[verb.end():end]
        action = _ITEM_ACTIONS.get(re.sub(r"\s+", " ", verb.group(1).lower()), "modify")
        if action == "replace" and re.match(r"^\s*(?:cụm\s+từ|từ)\b", segment, re.IGNORECASE):
            action = "modify"
        else:
            by_cut = re.search(r"\b(?:bởi|bằng)\b", segment, re.IGNORECASE)
            if by_cut is not None and _paths(segment[:by_cut.start()]):
                segment = segment[:by_cut.start()]
        if not re.search(r"\bđiều\s+\d", segment, re.IGNORECASE):
            # "Sửa đổi khoản 3 và bổ sung khoản 4 vào Điều 9": the article named
            # later in the item also owns the clauses of this segment.
            later = re.search(r"\bĐiều\s+\d+[a-z]?\b", head[end:])
            if later is not None:
                segment = f"{segment} {later.group(0)}"
        if action == "add":
            into = re.search(r"\bvào\b", segment, re.IGNORECASE)
            if into is None:
                continue
            segment = segment[into.end():]
            # "vào sau khoản 5 Điều 6": the new clause belongs to Điều 6.
            # "vào sau Điều 3": anchor to Điều 3 so the addition is not dropped.
            after = re.match(r"\s*(?:trước|sau)\s+(điểm\s+[a-zđ]|khoản\s+\d+|điều\s+\d+[a-z]?)\b",
                             segment, re.IGNORECASE)
            if after is not None:
                if after.group(1).lower().startswith("điều"):
                    segment = after.group(1)
                else:
                    segment = segment[after.end():]
        paths = _paths(segment)
        if not paths and action != "add":
            # "Thay thế Phụ lục I", "Thay thế Mẫu số 01": not part of the Điều/Khoản/Điểm tree,
            # so the target cannot be matched automatically, but the proposal must still
            # reach a reviewer instead of disappearing.
            annex = _ANNEX_UNIT.search(segment)
            if annex is not None:
                paths = [re.sub(r"\s+", " ", annex.group(0)).strip()]
        found += [(action, path) for path in paths]
    return list(dict.fromkeys(found))


_FROM_DATE = re.compile(r"(?:kể\s+)?từ\s+ngày\s+(?:" + _DATE_WORDS + r")", re.IGNORECASE)


def item_dates(text: str) -> list[date]:
    """Distinct "từ ngày D" dates in an amending item's own wording.

    Quoted replacement text and anything after "như sau" belong to the amended
    document, not to the item, so they are ignored.
    """

    head = _QUOTE_BLOCK.sub(" ", _clean(text))
    cut = re.search(r"\bnhư\s+sau\b", head, re.IGNORECASE)
    if cut:
        head = head[: cut.start()]
    return sorted({
        found for match in _FROM_DATE.finditer(head) if (found := _date_from(match)) is not None
    })


def item_valid_from(text: str, fallback: date | None) -> date | None:
    """Date an amending item takes effect: its own "từ ngày D", else ``fallback``.

    ``fallback`` is the effective date of the whole document.  When the item states
    several different dates the right one per target is unclear, so no date is
    returned and the reviewer must enter it; silently using the document date could
    end a unit too early.
    """

    dates = item_dates(text)
    if not dates:
        return fallback
    return dates[0] if len(dates) == 1 else None


def node_amendment_items(
    nodes: Sequence[NodeText], *, own_number_key: str | None,
) -> list[tuple[NodeText, DocRef, str, str]]:
    """(source item, amended document, action, target path) for every amending item.

    The amended document is the one cited in the item's article heading ("Điều 1.
    Sửa đổi, bổ sung một số điều của Thông tư số 55/2021/TT-BCA") or directly in
    the item text when the heading does not name a single document.
    """

    by_id = {node.node_id: node for node in nodes}
    found: list[tuple[NodeText, DocRef, str, str]] = []
    seen_items: set[tuple[str, str, str, str]] = set()
    for node in nodes:
        if node.node_type not in {"clause", "point"}:
            continue
        parent = by_id.get(node.parent_id or "")
        article = parent if (parent and parent.node_type == "article") else (
            by_id.get(parent.parent_id or "") if parent else None
        )
        heading_refs: list[DocRef] = []
        if article is not None:
            heading = _clean(article.text)[:600]
            if re.search(
                r"sửa\s+đổi|bổ\s+sung|bãi\s+bỏ|thay\s+thế|hiệu\s+lực",
                heading,
                re.IGNORECASE,
            ):
                heading_refs = [
                    ref for ref in find_doc_refs(heading)
                    if ref.number_key != own_number_key
                ]
        inline_refs = [
            ref for ref in find_doc_refs(_clean(node.text)[:500])
            if ref.number_key != own_number_key
        ]
        target_refs = heading_refs or inline_refs
        if not target_refs:
            continue
        for action, path in parse_amend_item(node.text):
            key = (node.node_id, target_refs[0].number_key, action, path.lower())
            if key in seen_items:
                continue
            seen_items.add(key)
            found.append((node, target_refs[0], action, path))
    return found


def node_effective_dates(nodes: Sequence[NodeText]) -> list[tuple[str, str, date, str, int | None]]:
    """"Điều 2 của Thông tư này có hiệu lực từ D" -> (source node, path, date, quote, page)."""

    found: list[tuple[str, str, date, str, int | None]] = []
    for node in nodes:
        text = _clean(node.text)
        for match in _NODE_EFFECTIVE.finditer(text):
            when = _date_from(match)
            if when is None:
                continue
            raw_path = match.group("path")
            expanded = _paths(raw_path) or [raw_path]
            for path in expanded:
                found.append((node.node_id, path, when,
                              _window(text, match.start(), match.end()), node.page))
    return found
