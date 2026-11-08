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
    r"(?P<path>(?:(?:điểm\s+[a-zđ]\s+)?(?:khoản\s+\d+\s+)?)Điều\s+\d+[a-z]?)"
    rf"(?:\s+của\s+(?:{_TYPE_ALT})\s+này)?\s+có\s+hiệu\s+lực(?:\s+thi\s+hành)?"
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
# Cited parts right before "của <document>": "Khoản 1 Điều 2; Điều 4; Mẫu TK7 của".
_PATH_BEFORE = re.compile(
    r"((?:(?:Điều|[Kk]hoản|[Đđ]iểm|Mẫu|Phụ lục|Chương|Mục)\s+[0-9A-Za-zđ][^\s,;]*"
    r"(?:\s*(?:,|;|và)\s*|\s+))+)(?:của|tại)\s*$"
)
# A subject position: sentence start, list number, "và", comma or semicolon.
_SUBJECT_BEFORE = re.compile(r"(?:^|\d+\.|\bvà|,|;)\s*$")
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
    if "bãi bỏ một phần" in head:
        return "repeal_partial"
    if "bãi bỏ toàn bộ" in head or re.search(r"bãi\s+bỏ[^.]{0,200}sau\s+đây", head):
        return "repeal"
    if re.search(r"hết\s+hiệu\s+lực[^.]{0,120}sau\s+đây", head):
        return "repeal"
    if re.search(r"ngưng\s+hiệu\s+lực[^.]{0,200}sau\s+đây", head):
        return "suspend"
    return None


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
    if re.search(r"(?:thay\s+thế|thay\s+cho)\s*(?:cho\s+)?$", before.rstrip(" :,")):
        return "replace", None
    if re.search(r"\b(?:bị|được)\s+thay\s+thế", after[:200]):
        return "replace", None
    path_match = _PATH_BEFORE.search(raw_before)
    path = path_match.group(1).strip(" ,;") if path_match else None
    if re.search(r"bãi\s+bỏ", before):
        return ("repeal_partial", path) if path else ("repeal", None)
    # "<document> [và <document>] ... hết hiệu lực [kể từ ngày X này có hiệu lực]".
    subject = _SUBJECT_BEFORE.search(path_match.string[:path_match.start()] if path_match
                                     else raw_before)
    if re.search(r"hết\s+hiệu\s+lực", after) and (subject or path):
        if path:
            return "repeal_partial", path
        return ("replace" if _OWN_EFFECTIVE.search(after) else "repeal"), None
    if re.search(r"ngưng\s+hiệu\s+lực", before):
        return "suspend", None
    # The amending verb must belong to this document ("Sửa đổi ... của <ref>" at the
    # start of a heading, item or sentence; "X này sửa đổi"), not to a cited title.
    if re.search(
        r"(?:^|[.:;]\s+|\d+\.\s+|này\s+|ban\s+hành\s+\w+(?:\s+\w+)?\s+)"
        r"(?:sửa\s+đổi|bổ\s+sung)[^.;]{0,200}$",
        before,
    ):
        return "modify", None
    return None, None


def extract_relations(
    nodes: Sequence[NodeText],
    *,
    own_number_key: str | None,
    title: str,
    document_number: str | None,
    effective_from: date | None,
) -> Extraction:
    """Document-level relations and references read from the source document."""

    result = Extraction()
    if not nodes:
        return result
    consolidated = is_consolidated(document_number, title)
    repeal_list = is_repeal_list(title, nodes[0].text)
    partial_list = repeal_list and "một phần" in f"{title} {nodes[0].text[:600]}".lower()
    articles = {node.node_id: node for node in nodes if node.node_type == "article"}
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
        article = articles.get(node.parent_id or "") if node.node_type != "article" else None
        context = _context_verb(_clean(article.text)) if article is not None else None
        if context and node.node_type in {"clause", "point"}:
            # A list item under "Bãi bỏ ... sau đây:": the first document is the
            # target; later ones belong to its title ("... sửa đổi Thông tư Y").
            ref = refs[0]
            if ref.start < 40:
                _add_relation(
                    result, seen, node, context, ref, None, effective_from,
                    effective_from is not None, None, text[:1200], 0.9,
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
                if verdict is None:
                    if _RELATION_WORDS.search(sentence):
                        result.ai_candidates.append((node.node_id, sentence[:1200]))
                    continue
                if verdict.startswith("ref:"):
                    _add_reference(result, seen, node, verdict[4:], ref, sentence)
                    continue
                explicit = _explicit_date(sentence, ref)
                own = explicit is None and effective_from is not None
                condition = sentence[:600] if _CONDITION.search(sentence) else None
                _add_relation(
                    result, seen, node, verdict, ref, path,
                    explicit or (effective_from if own else None), own, condition,
                    sentence[:1200], 0.9 if verdict in {"repeal", "replace"} else 0.8,
                )
    return result


def _explicit_date(sentence: str, ref: DocRef) -> date | None:
    """A "từ ngày D" in the sentence that is not the referenced document's own date."""

    match: re.Match[str] | None = None
    for found in re.finditer(r"(?:kể\s+)?từ\s+ngày\s+(?:" + _DATE_WORDS + r")", sentence, re.I):
        if found.start() >= ref.end or found.end() <= ref.start:
            match = found
            break
    return _date_from(match) if match else None


def _add_relation(
    result: Extraction, seen: set[str], node: NodeText, action: str,
    ref: DocRef, path: str | None, valid_from: date | None, own: bool,
    condition: str | None, quote: str, confidence: float,
) -> None:
    key = f"{action}|{ref.number_key}|{(path or '').lower()}"
    if key in seen:
        return
    seen.add(key)
    result.relations.append(RelationProposal(
        source_node_id=node.node_id, action=action, scope="document", target=ref,
        target_path=path, valid_from=valid_from, from_own_effective=own,
        condition=condition, quote=quote, page=node.page, confidence=confidence, key=key,
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
    "thay thế từ": "modify", "thay thế cụm từ": "modify", "thay thế": "modify",
    "đình chỉ": "suspend", "ngưng hiệu lực": "suspend",
}
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
    cut = re.search(r"\bnhư\s+sau\b", head, re.IGNORECASE)
    if cut:
        head = head[: cut.start()]
    head = _QUOTE_BLOCK.sub(" ", head)
    head = head.split("“", 1)[0]
    verbs = list(_ITEM_VERB.finditer(head))
    if not verbs or verbs[0].start() > 3:
        return []
    found: list[tuple[str, str]] = []
    for index, verb in enumerate(verbs):
        end = verbs[index + 1].start() if index + 1 < len(verbs) else len(head)
        segment = head[verb.end():end]
        if not re.search(r"\bđiều\s+\d", segment, re.IGNORECASE):
            # "Sửa đổi khoản 3 và bổ sung khoản 4 vào Điều 9": the article named
            # later in the item also owns the clauses of this segment.
            later = re.search(r"\bĐiều\s+\d+[a-z]?\b", head[end:])
            if later is not None:
                segment = f"{segment} {later.group(0)}"
        action = _ITEM_ACTIONS.get(re.sub(r"\s+", " ", verb.group(1).lower()), "modify")
        if action == "add":
            into = re.search(r"\bvào\b", segment, re.IGNORECASE)
            if into is None:
                continue
            segment = segment[into.end():]
            # "vào sau khoản 5 Điều 6": the new clause belongs to Điều 6.
            after = re.match(r"\s*sau\s+(điểm\s+[a-zđ]|khoản\s+\d+|điều\s+\d+[a-z]?)\b",
                             segment, re.IGNORECASE)
            if after is not None:
                if after.group(1).lower().startswith("điều"):
                    continue
                segment = segment[after.end():]
        found += [(action, path) for path in _paths(segment)]
    return list(dict.fromkeys(found))


def node_amendment_items(
    nodes: Sequence[NodeText], *, own_number_key: str | None,
) -> list[tuple[NodeText, DocRef, str, str]]:
    """(source item, amended document, action, target path) for every amending item.

    The amended document is the one cited in the item's article heading ("Điều 1.
    Sửa đổi, bổ sung một số điều của Thông tư số 55/2021/TT-BCA").
    """

    articles = {node.node_id: node for node in nodes if node.node_type == "article"}
    found: list[tuple[NodeText, DocRef, str, str]] = []
    for node in nodes:
        if node.node_type not in {"clause", "point"} or node.parent_id not in articles:
            continue
        heading = _clean(articles[node.parent_id].text)[:600]
        if not re.search(r"sửa\s+đổi|bổ\s+sung|bãi\s+bỏ", heading, re.IGNORECASE):
            continue
        refs = [ref for ref in find_doc_refs(heading) if ref.number_key != own_number_key]
        if not refs:
            continue
        for action, path in parse_amend_item(node.text):
            found.append((node, refs[0], action, path))
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
            found.append((node.node_id, match.group("path"), when,
                          _window(text, match.start(), match.end()), node.page))
    return found
