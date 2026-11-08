"""Rules-first question analysis."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..schemas import AnalyzeRequest, Fact, FactStatus

_ASPECT_RULES = {
    "eligibility": ("đủ điều kiện", "điều kiện", "đối tượng", "hưởng", "được hưởng", "áp dụng"),
    "procedure": ("quy trình", "thủ tục", "hồ sơ", "thực hiện", "trình tự"),
    "exceptions": ("trừ trường hợp", "ngoại lệ", "không áp dụng", "miễn"),
    "transition": ("chuyển tiếp", "trước ngày", "từ ngày", "hiệu lực"),
    "authority": (
        "thẩm quyền",
        "cơ quan",
        "người có thẩm quyền",
        "trách nhiệm",
        "chức năng",
        "nhiệm vụ",
    ),
}
_DATE_RE = re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b")
_ARTICLE_RE = re.compile(r"\bđiều\s+\d+\b", re.IGNORECASE)
_DOC_NUM_RE = re.compile(r"\b\d{1,4}/\d{4}/[A-ZĐa-zđ0-9\-]+\b")


@dataclass(frozen=True)
class Analysis:
    understood_as: str
    facts: tuple[Fact, ...]
    missing_information: tuple[str, ...]
    aspects: tuple[str, ...]
    query_rewrites: tuple[str, ...]


def analyze_request(request: AnalyzeRequest) -> Analysis:
    text = request.question.strip()
    facts = list(request.facts)
    if not any(fact.key == "question" for fact in facts):
        facts.insert(0, Fact(key="question", value=text, status=FactStatus.USER_CONFIRMED))
    date_match = _DATE_RE.search(text)
    if date_match and not any(fact.key == "event_date" for fact in facts):
        facts.append(
            Fact(
                key="event_date",
                value=date_match.group(0),
                status=FactStatus.EXTRACTED_UNCONFIRMED,
                source="question",
            )
        )
    article_match = _ARTICLE_RE.search(text)
    if article_match and not any(fact.key == "legal_reference" for fact in facts):
        facts.append(
            Fact(
                key="legal_reference",
                value=article_match.group(0),
                status=FactStatus.EXTRACTED_UNCONFIRMED,
                source="question",
            )
        )
    doc_match = _DOC_NUM_RE.search(text)
    if doc_match and not any(fact.key == "document_number" for fact in facts):
        facts.append(
            Fact(
                key="document_number",
                value=doc_match.group(0),
                status=FactStatus.EXTRACTED_UNCONFIRMED,
                source="question",
            )
        )
    lowered = text.casefold()
    aspects = tuple(
        name for name, markers in _ASPECT_RULES.items() if any(m in lowered for m in markers)
    )
    if not aspects:
        aspects = ("general",)
    missing: list[str] = []
    if not date_match:
        missing.append("Thời điểm áp dụng hoặc thời điểm phát sinh sự kiện pháp lý")
    if "eligibility" not in aspects and "authority" not in aspects:
        missing.append("Đối tượng hoặc cơ quan áp dụng cụ thể trong tình huống")
    doc_num = doc_match.group(0) if doc_match else None
    if doc_num:
        rewrites = tuple(
            dict.fromkeys(
                (
                    text,
                    f"Phạm vi điều chỉnh và đối tượng áp dụng của Nghị định {doc_num}?",
                    f"Trách nhiệm thi hành và hiệu lực của Nghị định {doc_num}?",
                )
            )
        )
    else:
        rewrites = tuple(
            dict.fromkeys(
                (
                    text,
                    f"{text} — phạm vi và đối tượng áp dụng",
                    f"{text} — trường hợp ngoại lệ và điều khoản thi hành",
                )
            )
        )
    return Analysis(
        understood_as=text,
        facts=tuple(facts),
        missing_information=tuple(missing),
        aspects=aspects,
        query_rewrites=rewrites,
    )
