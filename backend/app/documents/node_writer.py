"""Write a parsed legal tree: page-by-page source spans, parent links, citation labels.

A node whose text continues on the next page gets one source span per page, in
reading order (``node_source_spans``).  Its ``text_original`` is the exact page
slices joined by "\\n", so the stored quote is still byte-for-byte what the PDF says.
``document_nodes.source_span_id`` keeps pointing at the first span for the queries
that only need the first page.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from ..vietnamese_nlp.unicode_norm import NORMALIZER_REVISION, fold_text, normalize_text
from .spans import PageTextLocator
from .tree_parser import ParsedNode


@dataclass(frozen=True)
class Anchor:
    page_number: int
    offset: int
    text: str


def anchor_nodes(
    page_texts: dict[int, str], nodes: list[ParsedNode]
) -> list[tuple[Anchor, ...] | None]:
    """Locate every node on its page(s); None when any part cannot be found exactly."""
    locators: dict[int, PageTextLocator] = {}
    cursors: dict[int, int] = {}
    result: list[tuple[Anchor, ...] | None] = []
    for node in nodes:
        anchors: list[Anchor] = []
        for page_number, text in node.segments():
            page_text = page_texts.get(page_number)
            if not page_text:
                anchors = []
                break
            locator = locators.get(page_number)
            if locator is None:
                locator = locators[page_number] = PageTextLocator(page_text)
            found = locator.find_from(text, cursors.get(page_number, 0))
            if found is None:
                found = locator.find_unique(text)
            if found is None:
                anchors = []
                break
            offset, exact, end = found
            cursors[page_number] = max(cursors.get(page_number, 0), end)
            anchors.append(Anchor(page_number, offset, exact))
        result.append(tuple(anchors) if anchors else None)
    return result


async def write_nodes(
    connection: Any,
    *,
    document_id: UUID,
    version_id: UUID,
    title: str,
    document_number: str | None,
    page_ids: dict[int, UUID],
    page_texts: dict[int, str],
    nodes: list[ParsedNode],
) -> tuple[int, int]:
    """Insert nodes and their spans; returns (anchored, unanchored)."""
    anchors_by_node = anchor_nodes(page_texts, nodes)
    node_ids = [uuid4() for _ in nodes]
    anchored = unanchored = 0
    for index, (node, anchors) in enumerate(zip(nodes, anchors_by_node, strict=True)):
        span_ids: list[UUID] = []
        if anchors is not None and all(a.page_number in page_ids for a in anchors):
            for anchor in anchors:
                span_id = uuid4()
                span_ids.append(span_id)
                await connection.execute(
                    """INSERT INTO source_spans
                       (id, page_id, original_offset, original_length, text_original)
                       VALUES ($1, $2, $3, $4, $5)""",
                    span_id, page_ids[anchor.page_number], anchor.offset,
                    len(anchor.text), anchor.text,
                )
            exact_text = "\n".join(anchor.text for anchor in anchors)
            page_start, page_end = anchors[0].page_number, anchors[-1].page_number
            anchored += 1
        else:
            exact_text = node.text_original
            page_start, page_end = node.page_start, node.page_end
            unanchored += 1
        indexed = " ".join(
            part for part in (title, document_number, node.label_original, exact_text) if part
        )
        parent_id = node_ids[node.parent_index] if node.parent_index is not None else None
        await connection.execute(
            """INSERT INTO document_nodes
               (id, document_id, document_version_id, parent_id, node_type, label_original,
                path, citation_label, text_original, text_indexed, text_normalized,
                text_folded, page_start, page_end, source_span_id, parse_confidence,
                review_status, normalization_revision)
               VALUES ($1, $2, $3, $4, $5::node_type, $6, $7, $8, $9, $10, $11, $12,
                       $13, $14, $15, $16, 'draft', $17)""",
            node_ids[index], document_id, version_id, parent_id, node.node_type,
            node.label_original or None,
            f"{index + 1:06d}:{node.path_key}" if node.path_key else f"{index + 1:06d}",
            node.citation_label, exact_text, indexed, normalize_text(exact_text),
            fold_text(exact_text), page_start, page_end,
            span_ids[0] if span_ids else None, node.parse_confidence, NORMALIZER_REVISION,
        )
        for ordinal, span_id in enumerate(span_ids, start=1):
            await connection.execute(
                """INSERT INTO node_source_spans (node_id, ordinal, source_span_id)
                   VALUES ($1, $2, $3)""",
                node_ids[index], ordinal, span_id,
            )
    return anchored, unanchored


async def delete_version_nodes(connection: Any, version_id: UUID) -> None:
    """Remove a draft version's nodes and the node spans that only they used.

    Whole-page spans (written once per page at intake) are not node spans and stay.
    """
    rows = await connection.fetch(
        """SELECT nss.source_span_id AS id FROM node_source_spans nss
           JOIN document_nodes n ON n.id = nss.node_id
           WHERE n.document_version_id = $1
           UNION
           SELECT source_span_id FROM document_nodes
           WHERE document_version_id = $1 AND source_span_id IS NOT NULL""",
        version_id,
    )
    await connection.execute(
        "DELETE FROM document_nodes WHERE document_version_id = $1", version_id
    )
    if rows:
        await connection.execute(
            """DELETE FROM source_spans ss WHERE ss.id = ANY($1::uuid[])
               AND NOT EXISTS (SELECT 1 FROM document_nodes n WHERE n.source_span_id = ss.id)
               AND NOT EXISTS (SELECT 1 FROM node_source_spans x
                               WHERE x.source_span_id = ss.id)""",
            [row["id"] for row in rows],
        )


_VIETNAMESE_MARKS = frozenset(
    "ăâêôơưđáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ"
)


def suspect_text_layer(text: str) -> bool:
    """True for a long page whose text layer has almost no Vietnamese diacritics.

    Typical of a scanner's built-in OCR ("CONG HOA XA HOI ...").  Such a page is
    still stored and searchable, but the reviewer is asked to check it.
    """
    letters = [char for char in unicodedata.normalize("NFC", text).casefold() if char.isalpha()]
    if len(letters) < 400:
        return False
    marked = sum(char in _VIETNAMESE_MARKS for char in letters)
    return marked / len(letters) < 0.02
