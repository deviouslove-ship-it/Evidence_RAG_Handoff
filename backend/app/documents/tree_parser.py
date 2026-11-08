"""Conservative legal document tree parser.

The parser only recognizes explicit headings.  It never creates an Article or
Clause when the source does not contain one.

Besides the flat node list it records, for every node, the lines it took from each
page (so a clause that continues on the next page can be anchored page by page), its
parent (Chương → Mục → Điều → Khoản → Điểm) and a citation label such as
"Điểm a khoản 2 Điều 5".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

from .native_pdf import ExtractedPage

# "Điều 3. Tên điều" starts an article; a wrapped line of running text such as
# "Điều 3 của Nghị định này, ..." (PDF/OCR line breaks) does not: there the number is
# followed by a lowercase word or a comma.
# (Case-sensitive on purpose: the lookahead must see lowercase letters only.)
_ARTICLE_RE = re.compile(r"^\s*(?:Điều|ĐIỀU|điều)\s+(\d+)\b(?!\s*[,;]|\s+[a-zà-ỹđ])")
_CLAUSE_RE = re.compile(r"^\s*(\d+)[.)]\s+")
_POINT_RE = re.compile(r"^\s*([a-zà-ỹ])\)\s+", re.IGNORECASE)
_HEADING_RE = re.compile(
    r"^\s*(?:(?:Chương|Mục)\s+(?:\d+|[IVXLCDM]+)(?!\w)"
    r"|Phụ\s+lục(?:\s+(?:\d+|[IVXLCDM]+)(?!\w))?(?=\s*(?:[.:–—-]|$)))",
    re.IGNORECASE,
)
# Longer nodes continue in "(phần N)" parts.  About 1% of the clauses in the test
# corpus exceed it; a few whole annexes reach 200,000 characters.
MAX_NODE_CHARACTERS = 4000
_HEADING_PARTS_RE = re.compile(
    r"^\s*(Chương|Mục|Phụ\s+lục)(?:\s+(\d+|[IVXLCDM]+)(?!\w))?", re.IGNORECASE
)


@dataclass(frozen=True)
class ParsedNode:
    node_type: str
    label_original: str
    text_original: str
    page_start: int
    parse_confidence: float
    # (page_number, line) in reading order; text_original is these lines joined by "\n".
    lines: tuple[tuple[int, str], ...] = field(default=(), compare=False)
    parent_index: int | None = None
    path_key: str = ""
    citation_label: str | None = None

    @property
    def page_end(self) -> int:
        return self.lines[-1][0] if self.lines else self.page_start

    def segments(self) -> tuple[tuple[int, str], ...]:
        """The node text split per page, in order: ((page, text), ...)."""
        if not self.lines:
            return ((self.page_start, self.text_original),)
        grouped: list[tuple[int, list[str]]] = []
        for page_number, line in self.lines:
            if grouped and grouped[-1][0] == page_number:
                grouped[-1][1].append(line)
            else:
                grouped.append((page_number, [line]))
        return tuple((page_number, "\n".join(parts)) for page_number, parts in grouped)


def _heading_key(line: str) -> tuple[str, str]:
    match = _HEADING_PARTS_RE.match(line)
    if match is None:
        return "heading", ""
    kind = match.group(1).casefold().replace(" ", "")
    number = (match.group(2) or "").upper()
    return {"chương": "chuong", "mục": "muc", "phụlục": "phuluc"}.get(kind, "heading"), number


def parse_legal_tree(pages: list[ExtractedPage]) -> list[ParsedNode]:
    nodes: list[ParsedNode] = []
    current_index: int | None = None
    current_article_index: int | None = None
    current_clause_index: int | None = None
    current_chapter_index: int | None = None
    current_section_index: int | None = None
    article_number: str | None = None
    clause_number: str | None = None
    part_counts: dict[int | None, int] = {}

    def path_of(index: int | None) -> str:
        return nodes[index].path_key if index is not None else ""

    def joined(parent: str, own: str) -> str:
        return f"{parent}/{own}" if parent else own

    for page in pages:
        confidence_cap = 0.5 if page.text_quality == "needs_review" else 1.0
        first_line = True
        for raw_line in page.text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if first_line and line == str(page.page_number) and page.page_number > 1:
                first_line = False
                continue
            first_line = False
            entry = ((page.page_number, line),)
            heading = _HEADING_RE.match(line)
            article = _ARTICLE_RE.match(line)
            clause = _CLAUSE_RE.match(line)
            point = _POINT_RE.match(line)
            if heading:
                current_article_index = None
                current_clause_index = None
                article_number = clause_number = None
                kind, number = _heading_key(line)
                parent = current_chapter_index if kind == "muc" else None
                nodes.append(
                    ParsedNode(
                        node_type="heading",
                        label_original=line,
                        text_original=line,
                        page_start=page.page_number,
                        parse_confidence=min(0.8, confidence_cap),
                        lines=entry,
                        parent_index=parent,
                        path_key=joined(path_of(parent), f"{kind}:{number}"),
                    )
                )
                current_index = len(nodes) - 1
                if kind == "muc":
                    current_section_index = current_index
                else:
                    current_chapter_index = current_index
                    current_section_index = None
            elif article:
                article_number = article.group(1)
                clause_number = None
                parent = (
                    current_section_index if current_section_index is not None
                    else current_chapter_index
                )
                nodes.append(
                    ParsedNode(
                        node_type="article",
                        label_original=line,
                        text_original=line,
                        page_start=page.page_number,
                        parse_confidence=min(0.95, confidence_cap),
                        lines=entry,
                        parent_index=parent,
                        path_key=joined(path_of(parent), f"dieu:{article_number}"),
                    )
                )
                current_index = len(nodes) - 1
                current_article_index = current_index
                current_clause_index = None
            elif clause and current_article_index is not None:
                clause_number = clause.group(1)
                nodes.append(
                    ParsedNode(
                        node_type="clause",
                        label_original=line,
                        text_original=line,
                        page_start=page.page_number,
                        parse_confidence=min(0.8, confidence_cap),
                        lines=entry,
                        parent_index=current_article_index,
                        path_key=joined(
                            path_of(current_article_index), f"khoan:{clause_number}"
                        ),
                        citation_label=f"Khoản {clause_number} Điều {article_number}",
                    )
                )
                current_index = len(nodes) - 1
                current_clause_index = current_index
            elif point and current_clause_index is not None:
                letter = point.group(1).casefold()
                nodes.append(
                    ParsedNode(
                        node_type="point",
                        label_original=line,
                        text_original=line,
                        page_start=page.page_number,
                        parse_confidence=min(0.75, confidence_cap),
                        lines=entry,
                        parent_index=current_clause_index,
                        path_key=joined(path_of(current_clause_index), f"diem:{letter}"),
                        citation_label=(
                            f"Điểm {letter} khoản {clause_number} Điều {article_number}"
                        ),
                    )
                )
                current_index = len(nodes) - 1
            elif current_index is not None and (
                len(nodes[current_index].text_original) + len(line) + 1 > MAX_NODE_CHARACTERS
            ):
                # A very long Điều/Khoản (tables, annexes, whole unstructured parts) is
                # split into "(tiếp theo)" parts so one quote stays readable and a chat
                # turn stays bounded.  Each part is still anchored to its own pages.
                current = nodes[current_index]
                owner_index = current_index if not current.path_key.split("/")[-1].startswith(
                    "tiep:") else current.parent_index
                owner = nodes[owner_index] if owner_index is not None else current
                part = part_counts[owner_index] = part_counts.get(owner_index, 1) + 1
                base_label = owner.citation_label or owner.label_original[:120] or None
                nodes.append(
                    ParsedNode(
                        node_type="paragraph",
                        label_original="",
                        text_original=line,
                        page_start=page.page_number,
                        parse_confidence=min(owner.parse_confidence, 0.75, confidence_cap),
                        lines=entry,
                        parent_index=owner_index,
                        path_key=joined(owner.path_key, f"tiep:{part}"),
                        citation_label=f"{base_label} (phần {part})" if base_label else None,
                    )
                )
                current_index = len(nodes) - 1
            elif current_index is not None:
                current = nodes[current_index]
                nodes[current_index] = replace(
                    current,
                    text_original=f"{current.text_original}\n{line}",
                    parse_confidence=min(current.parse_confidence, 0.75, confidence_cap),
                    lines=current.lines + entry,
                )
            else:
                nodes.append(
                    ParsedNode(
                        node_type="paragraph",
                        label_original="",
                        text_original=line,
                        page_start=page.page_number,
                        parse_confidence=min(0.6, confidence_cap),
                        lines=entry,
                        path_key="doan",
                    )
                )
                current_index = len(nodes) - 1
    return nodes
