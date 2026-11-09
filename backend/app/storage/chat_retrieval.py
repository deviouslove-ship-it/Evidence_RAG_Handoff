"""Chat retrieval on top of G2 comprehensive search, composed into documents and an answer.

* A question without an explicit legal reference runs the four G2 channels (exact,
  semantic, concept, relation; RRF; no rerank) as one fixed result set, the same set
  the "Tìm kiếm văn bản" page shows.  Only clauses in the ``direct``/``related`` tiers
  (storage/relevance.py) become evidence; weak matches are counted, never cited.
* A question that names a document number or an Điều keeps the deterministic legal
  reference lookup (SRS §5.1 step 2) and is composed the same way.
* Every evidence item is a hydrated, ACL-checked row; quotes are ``text_original``.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from ..schemas import DocumentRelation, EvidenceRef, Scope, ScopeMode
from ..workflow.chat_answer import Composition, Rule, compose
from .authorized_search import ALLOWED_DOCUMENTS_SQL
from .comprehensive import _HYDRATE_SQL, ComprehensiveRequest, ComprehensiveSearch, heading_of
from .relevance import analyze_terms, assess, unit_weights, word_plan
from .search import MAX_QUERY_CHARS, MAX_TERMS

_TOKEN_RE = re.compile(r"[0-9A-Za-zÀ-ỹĐđ]+")
_RULES_TTL_SECONDS = 300.0
_ACTION_LABELS = {
    "modify": "Sửa đổi, bổ sung", "add": "Bổ sung", "repeal": "Bãi bỏ",
    "repeal_partial": "Bãi bỏ một phần", "replace": "Thay thế", "suspend": "Tạm ngưng",
}


@dataclass
class ChatRetrievalResult:
    composition: Composition
    result_set_id: str | None
    phrases: list[str]

    @property
    def evidence(self) -> list[EvidenceRef]:
        return self.composition.evidence


def keyword_query(question: str) -> str:
    """Bounded keyword form of a question for the exact channel (≤ 20 terms, 500 chars)."""

    terms = analyze_terms(question)
    words: list[str] = []
    for segment in terms.segments:
        for token in segment:
            if token not in words:
                words.append(token)
    if not words:
        words = list(dict.fromkeys(token.casefold() for token in _TOKEN_RE.findall(question)))
    return " ".join(words[:MAX_TERMS])[:MAX_QUERY_CHARS].strip()


class ChatRetrieval:
    def __init__(
        self, comprehensive: ComprehensiveSearch, *, max_documents: int = 8,
        max_clauses: int = 4,
    ) -> None:
        self.comprehensive = comprehensive
        self.max_documents = max_documents
        self.max_clauses = max_clauses
        self._rules: tuple[float, list[Rule]] | None = None

    @property
    def _pool(self) -> Any:
        return self.comprehensive.search._pool

    async def run(
        self, *, principal_id: UUID, scope: Scope, question: str,
    ) -> ChatRetrievalResult:
        query = question.strip()
        if len(query) > MAX_QUERY_CHARS or len(_TOKEN_RE.findall(query)) > MAX_TERMS:
            query = keyword_query(question)
        result = await self.comprehensive.run(principal_id, ComprehensiveRequest(
            query=query or question[:MAX_QUERY_CHARS],
            category_ids=(list(scope.category_ids) or None)
            if scope.scope_mode == ScopeMode.SELECTED else None,
            doc_types=list(scope.document_types) or None,
            as_of_date=scope.as_of_date, display="default", rerank=False,
            semantic_query=question, terms_query=question,
        ))
        relevant = self.comprehensive.filtered(result, tiers=("direct", "related"))
        weak = sum(1 for item in result.candidates if item.tier == "weak")
        counts: dict[str, int] = {}
        for item in relevant:
            counts[item.document_id] = counts.get(item.document_id, 0) + 1
        selected = self._select(relevant)
        rows = await self.comprehensive.hydrate(principal_id, result, selected)
        items = [self.comprehensive.item_view(result, item, rows[item.node_id], position)
                 for position, item in enumerate(selected, start=1) if item.node_id in rows]
        composition = compose(
            question=question, phrases=result.summary.get("understood", {}).get("phrases", []),
            items=items, rules=await self.rules(), as_of=result.as_of,
            result_set_id=result.id,
            verified_relations=await self.relations(
                principal_id, {item["document_id"] for item in items}),
            max_documents=self.max_documents, max_clauses=self.max_clauses,
            weak_count=weak,
            documents_in_scope=result.summary.get("scope", {}).get("documents_in_scope"),
            document_counts=counts,
        )
        return ChatRetrievalResult(composition, result.id, list(
            result.summary.get("understood", {}).get("phrases", [])))

    def _select(self, relevant: list[Any]) -> list[Any]:
        """Enough clauses for ``max_documents`` documents, in result-set order."""

        per_document: dict[str, int] = {}
        chosen: list[Any] = []
        for item in relevant:
            count = per_document.get(item.document_id, 0)
            if count == 0 and len(per_document) >= self.max_documents * 2:
                continue
            if count >= self.max_clauses * 4:
                continue
            per_document[item.document_id] = count + 1
            chosen.append(item)
        return chosen

    async def for_evidence(
        self, *, principal_id: UUID, question: str, evidence: list[EvidenceRef],
        direct_nodes: set[str], as_of: Any,
    ) -> ChatRetrievalResult:
        """Compose evidence found by the legal-reference lookup (number / Điều)."""

        terms = analyze_terms(question)
        versions = list(dict.fromkeys(item.document_version_id for item in evidence))
        async with self._pool.acquire() as connection, connection.transaction():
            await connection.execute(
                "SELECT set_config('app.user_id', $1, true)", str(principal_id))
            rows = {row["node_id"]: row for row in await connection.fetch(
                _HYDRATE_SQL, [item.node_id for item in evidence], versions)}
            weights = await unit_weights(connection, versions, terms) if not terms.empty else {}
        plan = word_plan(terms, weights)
        items: list[dict[str, Any]] = []
        for position, ref in enumerate(evidence, start=1):
            row = rows.get(str(ref.node_id))
            if row is None:
                continue
            headings = [value for value in (row["parent1"], row["parent2"]) if value]
            found = assess(terms, plan, text=row["text_original"], headings=headings,
                           title=row["title"] or "", ranks={"exact": position})
            tier = found.tier
            match = found.match
            if str(ref.node_id) in direct_nodes:
                tier, match = "direct", "article"
            elif plan.total <= 0:
                tier = "related"
            text = row["text_original"]
            start, end = found.excerpt_start, found.excerpt_end
            if not (0 <= start < end <= len(text)):
                start, end = 0, min(len(text), 520)
            items.append({
                "rank": position, "node_id": str(ref.node_id),
                "document_id": str(ref.document_id),
                "document_version_id": str(ref.document_version_id),
                "document_number": row["document_number"], "title": row["title"],
                "doc_type": row["doc_type"], "issuing_body": row["issuing_body"],
                "publication_date": row["publication_date"],
                "source_format": row["source_format"],
                "original_filename": row["original_filename"],
                "extraction_method": row.get("extraction_method"),
                "label": row["label"], "heading": heading_of(row),
                "node_type": row["node_type"], "path": row["path"],
                "page": row["page_number"], "page_end": row["page_end"],
                "quote_exact": text, "source_hash": row["source_hash"],
                "viewer_url": ref.viewer_url,
                "original_url": (f"/api/v1/citations/{ref.evidence_id}/original"
                                 f"?as_of_date={ref.as_of_date.isoformat()}"),
                "effectivity": ref.effectivity,
                "tier": tier, "match": match, "matched_terms": found.matched,
                "listing": found.listing, "relevance": found.score,
                "excerpt": {
                    "start": start, "end": end, "text": text[start:end],
                    "truncated_before": start > 0, "truncated_after": end < len(text),
                    "highlights": [{"start": s - start, "end": e - start}
                                   for s, e in found.highlights if start <= s and e <= end],
                },
            })
        composition = compose(
            question=question, phrases=terms.phrases, items=items, rules=await self.rules(),
            as_of=as_of, verified_relations=await self.relations(
                principal_id, {item["document_id"] for item in items}),
            max_documents=self.max_documents, max_clauses=self.max_clauses,
        )
        return ChatRetrievalResult(composition, None, terms.phrases)

    async def rules(self) -> list[Rule]:
        """Content-group phrase rules (G4), read from the database and cached briefly."""

        now = time.monotonic()
        if self._rules is not None and now - self._rules[0] < _RULES_TTL_SECONDS:
            return self._rules[1]
        try:
            async with self._pool.acquire() as connection:
                rows = await connection.fetch(
                    """SELECT t.code, t.name, t.sort_order, r.phrase_folded, r.scope
                       FROM labeling_rules r JOIN content_taxonomy t ON t.id = r.taxonomy_id
                       WHERE r.active AND t.active ORDER BY t.sort_order, r.id""")
        except Exception:  # grouping is optional; never fail an answer for it
            return []
        rules = [Rule(row["name"], int(row["sort_order"]), row["phrase_folded"], row["scope"],
                      row["code"]) for row in rows]
        self._rules = (now, rules)
        return rules

    async def relations(
        self, principal_id: UUID, document_ids: set[str],
    ) -> dict[str, list[DocumentRelation]]:
        """Approved (reviewed) document-level relations only; proposals are not shown."""

        if not document_ids:
            return {}
        try:
            async with self._pool.acquire() as connection, connection.transaction():
                await connection.execute(
                    "SELECT set_config('app.user_id', $1, true)", str(principal_id))
                rows = await connection.fetch(
                    "WITH allowed AS (" + ALLOWED_DOCUMENTS_SQL + """)
                       SELECT a.source_document_id::text AS source, a.target_document_id::text
                              AS target, a.action, a.target_number,
                              sd.document_number AS source_number,
                              td.document_number AS target_doc_number
                       FROM node_amendments a
                       JOIN authorized_nodes n ON n.id = a.source_node_id
                       JOIN documents sd ON sd.id = a.source_document_id
                       JOIN allowed td_allowed ON td_allowed.document_id = a.target_document_id
                       JOIN documents td ON td.id = td_allowed.document_id
                       WHERE a.review_status = 'approved' AND a.superseded_by IS NULL
                         AND (a.source_document_id = ANY($1::uuid[])
                              OR a.target_document_id = ANY($1::uuid[]))
                       LIMIT 200""",
                    [UUID(item) for item in document_ids],
                )
        except Exception:
            return {}
        found: dict[str, list[DocumentRelation]] = {}
        for row in rows:
            label = _ACTION_LABELS.get(row["action"], row["action"])
            if row["source"] in document_ids:
                number = row["target_doc_number"] or row["target_number"]
                found.setdefault(row["source"], []).append(DocumentRelation(
                    kind=row["action"], label=f"{label} {number or 'văn bản khác'}",
                    target_number=number, verified=True, source="Đã xác minh"))
            if row["target"] in document_ids and row["source_number"]:
                found.setdefault(row["target"], []).append(DocumentRelation(
                    kind=f"{row['action']}_by",
                    label=f"Bị {label.lower()} bởi {row['source_number']}",
                    target_number=row["source_number"], verified=True, source="Đã xác minh"))
        for key, values in found.items():
            unique: dict[str, DocumentRelation] = {}
            for value in values:
                unique.setdefault(value.label, value)
            found[key] = list(unique.values())[:6]
        return found
