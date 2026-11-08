"""Compose a chat answer from retrieved clauses: one entry per document, a short summary.

Everything written here comes from stored metadata (type, number, title, Điều headings),
the relevance tiers of ``storage/relevance.py`` and the content-group rules kept in the
database.  No model is called, no legal fact, number, date or effectivity is invented:
unknown values stay unknown.  Quotes are verbatim slices of ``text_original``.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal
from uuid import UUID

from ..schemas import (
    AmendmentStatus,
    AnswerClause,
    AnswerDocument,
    AnswerTopic,
    ChatAnswer,
    DocumentRelation,
    EffectivityView,
    EvidenceRef,
    Excerpt,
    TextSpan,
)
from ..vietnamese_nlp.unicode_norm import fold_text

DOC_TYPE_LABELS = {
    "law": "Luật", "code": "Bộ luật", "ordinance": "Pháp lệnh", "resolution": "Nghị quyết",
    "decree": "Nghị định", "circular": "Thông tư", "joint_circular": "Thông tư liên tịch",
    "decision": "Quyết định", "directive": "Chỉ thị", "consolidated": "Văn bản hợp nhất",
    "other": "Văn bản khác",
}
# Leading words of a stored title that only repeat the document type ("Thông Tư Quy định…").
_TITLE_KIND_WORDS = (
    "thong tu lien tich", "van ban hop nhat", "thong tu", "nghi dinh", "quyet dinh",
    "chi thi", "nghi quyet", "phap lenh", "bo luat", "luat", "ke hoach",
)
_TITLE_KEEP_WORDS = frozenset({"ke hoach"})
_ARTICLE_LABEL = re.compile(r"^\s*(Điều\s+\d+[a-zđ]?)\s*[.:]?\s*(.*)$", re.IGNORECASE | re.S)
_PART_SUFFIX = re.compile(r"\s*\((phần\s+\d+)\)\s*$", re.IGNORECASE)
_ARTICLE_IN_LABEL = re.compile(r"\bĐiều\s+(\d+[a-zđ]?)\b", re.IGNORECASE)
_FORM_RE = re.compile(r"\bMẫu\s+số\b.{0,80}?\(?\s*Ban\s+hành\s+kèm\s+theo", re.IGNORECASE | re.S)
_TITLE_RELATION = re.compile(
    r"\b(sửa đổi, bổ sung|sửa đổi|bổ sung|bãi bỏ|thay thế|hướng dẫn thi hành|hướng dẫn)\b"
    r"[^.;]{0,80}?\b((?:Thông tư liên tịch|Thông tư|Nghị định|Quyết định|Luật|Chỉ thị)"
    r"\s+số\s+(\d{1,4}/\d{4}/[0-9A-Za-zĐđ\-]+))",
    re.IGNORECASE,
)
_CONSOLIDATED_BASE = re.compile(
    r"\b((?:Thông tư liên tịch|Thông tư|Nghị định|Quyết định|Luật)\s+số\s+"
    r"(\d{1,4}/\d{4}/[0-9A-Za-zĐđ\-]+))",
    re.IGNORECASE,
)
_STATUS_TEXT = {
    AmendmentStatus.REPEALED: "đã bị bãi bỏ", AmendmentStatus.REPLACED: "đã bị thay thế",
    AmendmentStatus.SUSPENDED: "đang bị tạm ngưng hiệu lực",
    AmendmentStatus.NOT_YET_EFFECTIVE: "chưa có hiệu lực",
}


def _folded_words(text: str) -> str:
    return " ".join(re.sub(r"[^0-9a-z]+", " ", fold_text(text)).split())


def display_title(title: str) -> str:
    """Trích yếu without a leading, title-cased copy of the document type."""

    clean = " ".join((title or "").split())
    folded = _folded_words(clean)
    for kind in _TITLE_KIND_WORDS:
        if folded.startswith(kind + " "):
            words = len(kind.split())
            parts = clean.split(" ")
            rest = " ".join(parts[words:])
            # "Kế hoạch" is part of the title itself (a plan), not a copy of the type.
            if rest and rest[0].isupper() and kind not in _TITLE_KEEP_WORDS:
                return rest
            # Keep the type word but write it in sentence case ("Kế Hoạch" -> "Kế hoạch").
            head = " ".join(parts[:words])
            return head[:1].upper() + head[1:].lower() + (" " + rest if rest else "")
    return clean


def kind_label(document_number: str | None, title: str) -> str | None:
    if document_number and "vbhn" in fold_text(document_number):
        return "Văn bản hợp nhất"
    folded = _folded_words(display_title(title))
    if folded.startswith(("sua doi", "bo sung")):
        return "Văn bản sửa đổi, bổ sung"
    if folded.startswith("bai bo"):
        return "Văn bản bãi bỏ"
    return None


def title_relations(document_number: str | None, title: str) -> list[DocumentRelation]:
    """Relations the title itself states; shown as such, never as a verified relation."""

    found: list[DocumentRelation] = []
    clean = " ".join((title or "").split())
    if kind_label(document_number, clean) == "Văn bản hợp nhất":
        match = _CONSOLIDATED_BASE.search(clean)
        if match:
            found.append(DocumentRelation(
                kind="consolidates", label=f"Hợp nhất {match.group(1)}",
                target_number=match.group(2), verified=False, source="Theo trích yếu"))
        return found
    for match in _TITLE_RELATION.finditer(clean):
        verb = match.group(1).lower()
        found.append(DocumentRelation(
            kind="title", label=f"{verb[:1].upper()}{verb[1:]} {match.group(2)}",
            target_number=match.group(3), verified=False, source="Theo trích yếu"))
    return found[:3]


def split_label(label: str, heading: str | None, node_type: str | None,
                path: str | None) -> tuple[str, str | None]:
    """Short citation label and the Điều title it belongs to."""

    text = " ".join((label or "").split())
    part = _PART_SUFFIX.search(text)
    suffix = f" ({part.group(1)})" if part else ""
    if part:
        text = text[: part.start()]
    if node_type == "paragraph" or text in {"paragraph", ""}:
        first = (path or "").startswith("000001:")
        return ("Phần mở đầu" if first else "Đoạn không đánh số") + suffix, heading
    article = _ARTICLE_LABEL.match(text)
    if article and node_type in {"article", None}:
        title = article.group(2).strip()
        return article.group(1) + suffix, title or heading
    return text + suffix, heading


@dataclass(frozen=True)
class Rule:
    name: str
    sort_order: int
    phrase: str
    scope: str
    code: str = ""


# Content groups (migration 0013) that frame a document rather than regulate the matter:
# scope, definitions, entry into force.  Their articles are listed after substantive ones.
FRAMEWORK_GROUPS = frozenset({"pham_vi_doi_tuong", "giai_thich_tu_ngu", "hieu_luc_chuyen_tiep"})


def topics_of(rules: Sequence[Rule], heading: str | None, text: str) -> list[tuple[str, str]]:
    """(name, code) of the content groups whose phrase rules match, in group order."""

    folded_heading = f" {_folded_words((heading or '')[:200])} "
    folded_text = f" {_folded_words(text)} "
    names: dict[str, tuple[int, str]] = {}
    for rule in rules:
        needle = _folded_words(rule.phrase)
        haystack = folded_heading if rule.scope == "heading" else folded_text
        if needle and f" {needle} " in haystack:
            names[rule.name] = (rule.sort_order, rule.code)
    return [(name, code) for name, (_, code) in sorted(names.items(), key=lambda pair: pair[1])]


@dataclass
class Composition:
    documents: list[AnswerDocument] = field(default_factory=list)
    evidence: list[EvidenceRef] = field(default_factory=list)
    answer: ChatAnswer | None = None


def _effectivity(value: Any) -> EffectivityView | None:
    if value is None:
        return None
    return value if isinstance(value, EffectivityView) else EffectivityView.model_validate(value)


def _norm_key(text: str) -> str:
    body = re.sub(r"^\s*(?:\d+[.)]|[a-zđ][)])\s*", "", text or "")
    return " ".join(_folded_words(body).split())


def _short(text: str, limit: int) -> str:
    clean = " ".join(text.split())
    if len(clean) <= limit:
        return clean
    cut = clean.rfind(" ", 0, limit)
    return clean[: cut if cut > limit * 0.6 else limit].rstrip(" ,;:") + "…"


def _date(value: Any) -> date | None:
    if value is None or isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def compose(
    *, question: str, phrases: Sequence[str], items: Sequence[dict[str, Any]],
    rules: Sequence[Rule], as_of: date, result_set_id: str | None = None,
    verified_relations: dict[str, list[DocumentRelation]] | None = None,
    max_documents: int = 8, max_clauses: int = 4, max_reference_documents: int = 3,
    weak_count: int = 0, documents_in_scope: int | None = None,
    document_counts: dict[str, int] | None = None,
) -> Composition:
    """``items`` are hydrated result items (``ComprehensiveSearch.item_view``) in rank order."""

    by_document: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for item in items:
        if item.get("tier") not in ("direct", "related"):
            continue
        by_document.setdefault(item["document_id"], []).append(item)

    def role(members: list[dict[str, Any]]) -> str:
        if all(member.get("listing") for member in members):
            return "reference"
        if any(member["tier"] == "direct" and not member.get("listing") for member in members):
            return "direct"
        return "related"

    roles = {document: role(members) for document, members in by_document.items()}
    ordered = ([d for d in by_document if roles[d] == "direct"]
               + [d for d in by_document if roles[d] == "related"])
    chosen = ordered[:max_documents]
    references = [d for d in by_document if roles[d] == "reference"][:max_reference_documents]

    composition = Composition()
    seen_text: dict[str, tuple[str, str]] = {}
    topic_refs: OrderedDict[str, list[tuple[str, str]]] = OrderedDict()
    # What the question asks (penalty, deadline, ...): a document whose clauses only share
    # the subject must not be announced as regulating it (synthesis/focus.py).
    from ..synthesis.focus import analyze_question, aspects_in

    focus = analyze_question(question)
    strict = {aspect.code for aspect in focus.aspects if aspect.strict}
    aspect_documents = 0
    for document_id in [*chosen, *references]:
        members = by_document[document_id]
        document_role = roles[document_id]
        limit = 1 if document_role == "reference" else max_clauses
        picked, also = _pick_clauses(members, rules, limit,
                                     keep_listing=document_role == "reference")
        if strict and document_role != "reference" and any(
                strict <= aspects_in(focus, [item["quote_exact"], item.get("heading") or ""])
                for item in members if not item.get("listing")):
            aspect_documents += 1
        first = picked[0]
        clauses: list[AnswerClause] = []
        for item in picked:
            evidence_id = f"ev_{item['node_id']}"
            short_label, heading = split_label(item["label"], item.get("heading"),
                                               item.get("node_type"), item.get("path"))
            key = _norm_key(item["quote_exact"])
            same_as: list[str] = []
            if len(key) >= 60:
                if key in seen_text and seen_text[key][0] != evidence_id:
                    same_as = [seen_text[key][0]]
                else:
                    seen_text.setdefault(key, (evidence_id, document_id))
            excerpt = item["excerpt"]
            tier: Literal["direct", "related", "reference"] = (
                "reference" if document_role == "reference" or item.get("listing")
                else "direct" if item["tier"] == "direct" else "related")
            topics = [] if tier == "reference" else [name for name, _ in topics_of(
                rules, _topic_heading(item), item["quote_exact"])]
            clause = AnswerClause(
                evidence_id=evidence_id, node_id=UUID(item["node_id"]), label=short_label,
                heading=heading, page=item.get("page"), page_end=item.get("page_end"),
                tier=tier, match=item.get("match") or "partial",
                matched_terms=list(item.get("matched_terms") or []),
                excerpt=Excerpt(
                    start=excerpt["start"], end=excerpt["end"], text=excerpt["text"],
                    truncated_before=excerpt["truncated_before"],
                    truncated_after=excerpt["truncated_after"],
                    highlights=[TextSpan(start=span["start"], end=span["end"])
                                for span in excerpt["highlights"]],
                ),
                topics=topics, same_as=same_as, also_matched=also.get(item["node_id"], []),
                effectivity=_effectivity(item.get("effectivity")),
                ocr=item.get("extraction_method") == "local_ocr",
            )
            clauses.append(clause)
            for topic in topics:
                topic_refs.setdefault(topic, []).append(
                    (f"{short_label}, {item['document_number'] or display_title(item['title'])}",
                     evidence_id))
            view = clause.effectivity
            composition.evidence.append(EvidenceRef(
                evidence_id=evidence_id, document_id=UUID(item["document_id"]),
                document_version_id=UUID(item["document_version_id"]),
                node_id=UUID(item["node_id"]), document_number=item["document_number"],
                title=item["title"], label=item["label"], quote_exact=item["quote_exact"],
                page=item.get("page"), source_hash=item["source_hash"], as_of_date=as_of,
                amendment_state=view.status if view else AmendmentStatus.UNKNOWN,
                viewer_url=item["viewer_url"], effectivity=view,
                original_url=item.get("original_url"),
            ))
        relations = list((verified_relations or {}).get(document_id, []))
        relations += title_relations(first["document_number"], first["title"])
        composition.documents.append(AnswerDocument(
            document_id=UUID(document_id), document_version_id=UUID(first["document_version_id"]),
            doc_type=first.get("doc_type") or "other",
            doc_type_label=DOC_TYPE_LABELS.get(first.get("doc_type") or "", "Văn bản"),
            document_number=first["document_number"], title=display_title(first["title"]),
            issuing_body=first.get("issuing_body"),
            publication_date=_date(first.get("publication_date")),
            source_format=first.get("source_format") or "pdf",
            original_filename=first.get("original_filename"),
            original_url=first.get("original_url") or "",
            viewer_url=first["viewer_url"], role=document_role,  # type: ignore[arg-type]
            kind_label=("Danh mục, liệt kê văn bản" if document_role == "reference"
                        else kind_label(first["document_number"], first["title"])),
            relations=relations,
            effectivity=_effectivity(first.get("effectivity")),
            clauses=clauses,
            more_clauses=max(0, (document_counts or {}).get(document_id, len(members))
                             - len(clauses) - sum(len(value) for value in also.values())),
        ))
    composition.answer = _answer(
        question=question, phrases=phrases, documents=composition.documents,
        topics=topic_refs, as_of=as_of, result_set_id=result_set_id,
        extra_documents=max(0, len(ordered) - len(chosen)), weak_count=weak_count,
        documents_in_scope=documents_in_scope,
        missing_aspect=(focus.aspect_label, focus.subject_text)
        if strict and not aspect_documents else None,
    )
    return composition


def _topic_heading(item: dict[str, Any]) -> str | None:
    if item.get("node_type") == "article":
        return str(item["label"])
    return item.get("heading")


def _article_key(item: dict[str, Any]) -> str:
    match = _ARTICLE_IN_LABEL.search(item.get("label") or "")
    return f"dieu:{match.group(1).lower()}" if match else f"node:{item['node_id']}"


def _pick_clauses(
    members: list[dict[str, Any]], rules: Sequence[Rule], limit: int, *, keep_listing: bool,
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    """At most ``limit`` clauses, one per Điều: the best one represents its article.

    Order: direct before related, substantive articles before scope/definition/entry
    into force articles, then relevance and rank.  The other matching clauses of the
    same Điều are returned as labels so nothing relevant is silently dropped.
    """

    usable = [item for item in members if keep_listing or not item.get("listing")] or members

    def framework(item: dict[str, Any]) -> bool:
        codes = {code for _, code in topics_of(rules, _topic_heading(item), "")}
        # Sample forms appended to a document ("Mẫu số …, ban hành kèm theo …") restate
        # the subject in their own title; the articles that regulate it come first.
        form = bool(_FORM_RE.search(item.get("quote_exact") or ""))
        return bool(codes & FRAMEWORK_GROUPS) or form

    def order(item: dict[str, Any]) -> tuple[bool, bool, float, int]:
        return (item.get("tier") != "direct", framework(item),
                -float(item.get("relevance") or 0.0), int(item.get("rank") or 0))

    def heading_only(item: dict[str, Any]) -> bool:
        # An article whose own text is little more than its title: its clauses say more.
        return item.get("node_type") == "article" and len(item.get("quote_exact") or "") < 260

    by_article: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for item in sorted(usable, key=order):
        by_article.setdefault(_article_key(item), []).append(item)
    groups = list(by_article.values())
    picked: list[dict[str, Any]] = []
    also: dict[str, list[str]] = {}
    representative: dict[str, dict[str, Any]] = {}
    for group in groups:
        ordered = sorted(group, key=lambda item: (heading_only(item) and len(group) > 1,
                                                  order(item)))
        group[:] = ordered
    # First one clause per Điều, then a second clause of the same Điều if room is left.
    for round_index in (0, 1):
        for group in groups:
            if len(picked) >= limit:
                break
            if round_index < len(group) and (round_index == 0 or group[round_index]["tier"]
                                             == "direct"):
                picked.append(group[round_index])
                representative.setdefault(_article_key(group[0]), group[round_index])
    chosen = {item["node_id"] for item in picked}
    for group in groups:
        head = representative.get(_article_key(group[0]))
        if head is None:
            continue
        others = [split_label(item["label"], None, item.get("node_type"), item.get("path"))[0]
                  for item in group if item["node_id"] not in chosen]
        if others:
            also[head["node_id"]] = others[:8]
    picked.sort(key=lambda item: groups.index(next(g for g in groups if item in g)))
    return picked, also


def _article_list(document: AnswerDocument) -> str:
    seen: OrderedDict[str, str | None] = OrderedDict()
    for clause in document.clauses:
        match = _ARTICLE_IN_LABEL.search(clause.label)
        key = f"Điều {match.group(1)}" if match else clause.label
        heading = clause.heading
        if heading:
            article = _ARTICLE_LABEL.match(heading)
            heading = article.group(2).strip() if article else heading
        seen.setdefault(key, heading)
    parts = [f"{key} ({_short(heading, 90)})" if heading else key for key, heading in seen.items()]
    return "; ".join(parts)


def _document_name(document: AnswerDocument) -> str:
    kind = document.doc_type_label
    if document.kind_label == "Văn bản hợp nhất":
        kind = "Văn bản hợp nhất"
    number = document.document_number or "chưa có số hiệu"
    return f"{kind} {number}"


def _answer(
    *, question: str, phrases: Sequence[str], documents: Sequence[AnswerDocument],
    topics: OrderedDict[str, list[tuple[str, str]]], as_of: date, result_set_id: str | None,
    extra_documents: int, weak_count: int, documents_in_scope: int | None,
    missing_aspect: tuple[str, str] | None = None,
) -> ChatAnswer:
    direct = [item for item in documents if item.role == "direct"]
    related = [item for item in documents if item.role == "related"]
    references = [item for item in documents if item.role == "reference"]
    subject = f"“{_short(question, 160)}”"
    points: list[str] = []
    notes: list[str] = []
    outcome: Literal["direct", "related_only", "not_found"]
    if missing_aspect is not None and (direct or related):
        # The question asks for e.g. a penalty; the clauses found only share its subject.
        aspect, about = missing_aspect
        about_text = f"“{about}”" if about else "nội dung này"
        outcome = "related_only"
        summary = (f"Chưa tìm thấy điều khoản quy định {aspect} về {about_text}. Có "
                   f"{len(direct) + len(related)} văn bản nêu {about_text} ở nội dung khác; "
                   "các văn bản này không dùng để suy ra " + aspect + ".")
    elif direct:
        outcome = "direct"
        summary = (f"Tìm thấy {len(direct)} văn bản có điều khoản nêu trực tiếp nội dung "
                   f"{subject}"
                   + (f" và {len(related)} văn bản có nội dung liên quan" if related else "")
                   + ". Điều, khoản cụ thể và trích dẫn nguyên văn ở danh sách bên dưới.")
    elif related:
        outcome = "related_only"
        summary = (f"Chưa thấy điều khoản nêu trực tiếp nội dung {subject}. Có "
                   f"{len(related)} văn bản có nội dung liên quan, cần đọc để đối chiếu.")
    else:
        outcome = "not_found"
        scope = f" ({documents_in_scope} văn bản)" if documents_in_scope else ""
        summary = (f"Chưa tìm thấy trong kho văn bản quy định nội dung {subject} trong phạm vi "
                   f"được phép tra cứu{scope}.")
        if weak_count:
            notes.append(f"Có {weak_count} đoạn chỉ khớp một phần từ ngữ; có thể rà soát ở "
                         "trang Tìm kiếm văn bản.")
    for document in [*direct, *related]:
        name = _document_name(document)
        articles = _article_list(document)
        points.append(f"{name}: {_short(document.title, 120)}"
                      + (f" — {articles}" if articles else "") + ".")
    if extra_documents:
        notes.append(f"Còn {extra_documents} văn bản liên quan khác; xem đầy đủ ở trang Tìm kiếm "
                     "văn bản.")
    if references:
        names = ", ".join(item.document_number or item.title for item in references)
        notes.append(f"{len(references)} văn bản chỉ liệt kê hoặc nhắc đến nội dung này trong "
                     f"danh mục ({names}); không dùng làm căn cứ trực tiếp.")
    shown = [*direct, *related]
    if any(item.kind_label == "Văn bản hợp nhất" for item in shown):
        notes.append("Văn bản hợp nhất dùng để tra cứu, đối chiếu; khi viện dẫn cần dẫn văn bản "
                     "được hợp nhất và văn bản sửa đổi, bổ sung.")
    terminated = [item for item in shown
                  if item.effectivity and item.effectivity.status in _STATUS_TEXT]
    for item in terminated[:3]:
        assert item.effectivity is not None
        notes.append(f"{_document_name(item)} {_STATUS_TEXT[item.effectivity.status]} tại ngày "
                     f"{as_of:%d/%m/%Y}.")
    unverified = [item for item in shown
                  if item.effectivity is None or item.effectivity.verification != "verified"]
    if unverified:
        notes.append(
            (f"Hiệu lực của {len(unverified)}/{len(shown)} văn bản" if len(unverified) < len(shown)
             else "Hiệu lực của các văn bản này")
            + f" chưa được xác minh trong kho tại ngày {as_of:%d/%m/%Y}; cần đối chiếu trước "
              "khi áp dụng.")
    topic_items = [
        AnswerTopic(name=name, references=list(dict.fromkeys(ref for ref, _ in refs))[:6],
                    evidence_ids=list(dict.fromkeys(ev for _, ev in refs)))
        for name, refs in topics.items()
    ]
    return ChatAnswer(
        outcome=outcome, understood_phrases=list(phrases), summary=summary, points=points,
        topics=topic_items if len(topic_items) >= 2 else [], notes=notes,
        counts={"direct": len(direct), "related": len(related), "reference": len(references),
                "more": extra_documents, "weak": weak_count},
        result_set_id=result_set_id,
    )
