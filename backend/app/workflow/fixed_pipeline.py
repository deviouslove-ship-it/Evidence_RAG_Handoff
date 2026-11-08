"""Fixed Analyze → Retrieve → Validate → Explain pipeline.

The orchestration is deterministic.  There is no free-form agent loop, and the
workflow does not call a model to write quotes or citation identifiers.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID, uuid4

from ..evidence.validators import validate_claim
from ..memory.service import MemoryContext
from ..model_registry.stages import MAX_STAGE_ATTEMPTS
from ..schemas import (
    AmendmentStatus,
    AnalyzeRequest,
    AnalyzeResponse,
    Claim,
    CoverageChecks,
    CoverageState,
    EvidenceGroup,
    EvidenceRef,
    Fact,
    FactStatus,
    QueryResponse,
    ResultStatus,
    Scope,
)
from ..vietnamese_nlp.legal_citation_parser import (
    ParsedReferences,
    parse_legal_references,
    reference_document_number,
)
from ..vietnamese_nlp.unicode_norm import canonical_document_number
from .ai_selection import SelectionResult
from .analyze import analyze_request

if TYPE_CHECKING:
    from ..storage.chat_retrieval import ChatRetrievalResult

_LOG = logging.getLogger(__name__)


class SearchAuthorizedNodes(Protocol):
    async def __call__(
        self,
        *,
        principal_id: UUID,
        scope: Scope,
        query: str,
        limit: int = 12,
    ) -> list[EvidenceRef]: ...


class SelectEvidence(Protocol):
    async def __call__(
        self, question: str, evidence: list[EvidenceRef], *, principal_id: UUID,
        deep_analysis: bool = False,
    ) -> SelectionResult: ...


class ChatRetrievalPort(Protocol):
    async def run(
        self, *, principal_id: UUID, scope: Scope, question: str,
    ) -> ChatRetrievalResult: ...

    async def for_evidence(
        self, *, principal_id: UUID, question: str, evidence: list[EvidenceRef],
        direct_nodes: set[str], as_of: Any,
    ) -> ChatRetrievalResult: ...


@dataclass(frozen=True)
class PipelineDependencies:
    search_authorized_nodes: SearchAuthorizedNodes
    select_evidence: SelectEvidence | None = None
    # G2-based retrieval composed into documents and a structured answer.  None keeps
    # the extractive behaviour (in-memory development profile, unit tests).
    chat_retrieval: ChatRetrievalPort | None = None


@dataclass
class FixedPipeline:
    dependencies: PipelineDependencies
    operating_mode: str = "LOCAL"
    llm_attempt_budget: int = 2

    _MAX_FACTS_IN_QUERY = 32
    _MAX_EFFECTIVE_QUERY_LENGTH = 12_000
    # Only explicit back-references make a turn a follow-up; a new question that merely
    # contains "còn" ("còn hiệu lực") or "này" must not inherit facts of an earlier turn.
    _FOLLOW_UP_RE = re.compile(
        r"(?:\bthì\s+sao\b|\bnhư\s+(?:trên|vậy)\b|\btrường\s+hợp\s+(?:này|đó|trên)\b|"
        r"\b(?:văn\s+bản|thông\s+tư|nghị\s+định|quyết\s+định|điều|khoản|điểm|"
        r"quy\s+định)\s+(?:này|đó|trên|nói\s+trên)\b)",
        re.IGNORECASE,
    )

    def __post_init__(self) -> None:
        if self.llm_attempt_budget < 1 or self.llm_attempt_budget > MAX_STAGE_ATTEMPTS:
            raise ValueError(f"LLM attempt budget must be at most {MAX_STAGE_ATTEMPTS}")

    async def analyze(
        self,
        request: AnalyzeRequest,
        *,
        memory_context: MemoryContext | None = None,
    ) -> AnalyzeResponse:
        request = self._request_with_memory_context(request, memory_context)
        analysis = analyze_request(request)
        query_id = f"qry_{uuid4().hex}"
        run_id = f"run_{uuid4().hex}"
        return AnalyzeResponse(
            request_id=f"req_{uuid4().hex}",
            query_id=query_id,
            run_id=run_id,
            facts_revision=(
                memory_context.facts_revision
                if memory_context is not None
                else f"factrev_{uuid4().hex[:12]}"
            ),
            understood_as=analysis.understood_as,
            facts=list(analysis.facts),
            missing_information=list(analysis.missing_information),
            aspects=list(analysis.aspects),
            query_rewrites=list(analysis.query_rewrites),
        )

    async def execute(
        self,
        request: AnalyzeRequest,
        *,
        principal_id: UUID,
        query_id: str | None = None,
        run_id: str | None = None,
        facts_revision: str | None = None,
        memory_context: MemoryContext | None = None,
    ) -> QueryResponse:
        request = self._request_with_memory_context(request, memory_context)
        analysis = analyze_request(request)
        query_id = query_id or f"qry_{uuid4().hex}"
        run_id = run_id or f"run_{uuid4().hex}"
        facts_revision = (
            facts_revision
            or (memory_context.facts_revision if memory_context is not None else None)
            or f"factrev_{uuid4().hex[:12]}"
        )
        effective_query = self._merge_question_with_facts(request)
        if self.dependencies.chat_retrieval is not None:
            composed = await self._compose(request, effective_query, principal_id)
            if composed is not None:
                return self._composed_response(
                    composed, request, query_id=query_id, run_id=run_id,
                    facts_revision=facts_revision,
                )
        evidence = self._rank_evidence(
            list(
                await self.dependencies.search_authorized_nodes(
                    principal_id=principal_id,
                    scope=request.scope,
                    query=effective_query,
                )
            ),
            effective_query,
        )
        if not evidence:
            return QueryResponse(
                request_id=f"req_{uuid4().hex}",
                query_id=query_id,
                run_id=run_id,
                effective_mode=self.operating_mode,
                status=ResultStatus.INSUFFICIENT,
                source_scope=request.scope,
                missing_information=list(analysis.missing_information),
                facts_revision=facts_revision,
                coverage_checks=CoverageChecks(source_verified=CoverageState.UNKNOWN),
                explanation_unavailable=True,
            )
        parsed_references = parse_legal_references(effective_query)
        claim_evidence = evidence
        if parsed_references.is_unique_local_reference:
            claim_evidence = [
                item
                for item in evidence
                if self._matches_legal_reference(item, parsed_references)
            ]
        effective_checked = self._effectivity_coverage(evidence)
        claim_evidence, effectivity_notes = self._exclude_blocked_evidence(
            claim_evidence, parsed_references
        )
        selection_applied = False
        selection = SelectionResult()
        # Evidence eligible for claims/suggestions before the optional AI narrowing.
        suggestion_pool = claim_evidence
        # The model runs only when there is source-checked evidence to choose from;
        # no evidence means no call and no API escalation (D5, D8).
        if claim_evidence and self.dependencies.select_evidence is not None:
            selection = await self.dependencies.select_evidence(
                effective_query, claim_evidence, principal_id=principal_id,
                deep_analysis=request.deep_analysis,
            )
            selected = selection.evidence_ids
            if selected is not None:
                by_id = {item.evidence_id: item for item in claim_evidence}
                # Model output may only select existing approved evidence.
                # It cannot supply a quote, claim or citation identifier.
                if len(selected) == len(set(selected)) and all(key in by_id for key in selected):
                    claim_evidence = [by_id[key] for key in selected]
                    selection_applied = True
        evidence_by_id = {item.evidence_id: item.quote_exact for item in evidence}
        groups = self._group_evidence(evidence)
        claims = self._extractive_claims(claim_evidence)
        for claim in claims:
            validation = validate_claim(
                claim.text,
                claim.evidence_ids,
                evidence_by_id,
                memory_evidence_ids=(),
            )
            claim.status = validation.status
            if effective_checked != CoverageState.PASSED and claim.status == "supported":
                claim.status = "conditional"
        suggestions = self._build_suggestions(
            self._unclaimed_for_suggestions(claim_evidence, suggestion_pool)
        )
        if not claims or any(claim.status == "blocked" for claim in claims):
            status = ResultStatus.INSUFFICIENT
        elif any(claim.status != "supported" for claim in claims):
            status = ResultStatus.CONDITIONAL
        else:
            status = ResultStatus.EVIDENCE_FOUND
        if not claims:
            claim_supported = CoverageState.UNKNOWN
        elif any(claim.status == "blocked" for claim in claims):
            claim_supported = CoverageState.FAILED
        elif any(claim.status != "supported" for claim in claims):
            claim_supported = CoverageState.UNKNOWN
        else:
            claim_supported = CoverageState.PASSED
        return QueryResponse(
            request_id=f"req_{uuid4().hex}",
            query_id=query_id,
            run_id=run_id,
            effective_mode=self.operating_mode,
            status=status,
            source_scope=request.scope,
            evidence=evidence,
            evidence_groups=groups,
            claims=claims,
            missing_information=[
                *analysis.missing_information, *effectivity_notes,
                *self._verification_notes(evidence),
            ],
            suggestions=suggestions,
            coverage_checks=CoverageChecks(
                source_verified=CoverageState.PASSED,
                effective_checked=effective_checked,
                applicability_checked=CoverageState.UNKNOWN,
                claim_supported=claim_supported,
                transition_checked=CoverageState.UNKNOWN,
                required_facts_complete=CoverageState.UNKNOWN,
                scope_expansion=CoverageState.PASSED,
            ),
            facts_revision=facts_revision,
            answer_generated=False,
            explanation_unavailable=True,
            ai_selection_applied=selection_applied,
            external_ai_used=selection.external_api_used,
            ai_limited=selection.ai_limited,
        )

    async def _compose(
        self, request: AnalyzeRequest, effective_query: str, principal_id: UUID,
    ) -> ChatRetrievalResult | None:
        """Retrieve and compose; None = fall back to the extractive path (search busy)."""

        from ..storage.authorized_search import query_document_number_key
        from ..storage.search import SearchQueryError

        chat = self.dependencies.chat_retrieval
        assert chat is not None
        # Only what the user typed decides whether this is a reference lookup.
        parsed = parse_legal_references(request.question)
        number_key = query_document_number_key(request.question)
        try:
            if parsed.is_unique_local_reference or number_key:
                evidence = self._rank_evidence(list(
                    await self.dependencies.search_authorized_nodes(
                        principal_id=principal_id, scope=request.scope, query=effective_query,
                    )
                ), effective_query)
                direct: set[str] = set()
                for item in evidence:
                    if parsed.is_unique_local_reference:
                        if self._matches_legal_reference(item, parsed):
                            direct.add(str(item.node_id))
                    elif item.document_number and canonical_document_number(
                        reference_document_number(item.document_number) or item.document_number
                    ) == number_key:
                        direct.add(str(item.node_id))
                return await chat.for_evidence(
                    principal_id=principal_id, question=request.question, evidence=evidence,
                    direct_nodes=direct, as_of=request.scope.as_of_date,
                )
            return await chat.run(
                principal_id=principal_id, scope=request.scope, question=effective_query,
            )
        except SearchQueryError as exc:
            _LOG.warning("chat retrieval unavailable (%s); extractive fallback", exc.code)
            return None

    def _composed_response(
        self, composed: ChatRetrievalResult, request: AnalyzeRequest, *, query_id: str,
        run_id: str, facts_revision: str,
    ) -> QueryResponse:
        composition = composed.composition
        evidence = composition.evidence
        documents = composition.documents
        answer = composition.answer
        quotes = {item.evidence_id: item.quote_exact for item in evidence}
        claims: list[Claim] = []
        for document in documents:
            if document.role != "direct":
                continue
            for clause in document.clauses:
                if clause.tier != "direct" or clause.same_as or len(claims) >= 6:
                    continue
                validation = validate_claim(
                    clause.excerpt.text, [clause.evidence_id], quotes, memory_evidence_ids=(),
                )
                claims.append(Claim(
                    text=clause.excerpt.text, evidence_ids=[clause.evidence_id],
                    status="conditional" if validation.status == "supported"
                    else validation.status,
                ))
        effective_checked = self._effectivity_coverage(evidence)
        if not evidence or answer is None or answer.outcome == "not_found":
            status = ResultStatus.INSUFFICIENT
        elif effective_checked == CoverageState.PASSED and answer.outcome == "direct" and all(
            item.effectivity is not None and item.effectivity.verification == "verified"
            for item in evidence
        ):
            status = ResultStatus.EVIDENCE_FOUND
        else:
            status = ResultStatus.CONDITIONAL
        groups = [
            EvidenceGroup(
                group_id=f"document_{document.document_id.hex}", purpose=document.role,
                evidence_ids=[clause.evidence_id for clause in document.clauses],
                roles=[document.role],
            )
            for document in documents
        ]
        return QueryResponse(
            request_id=f"req_{uuid4().hex}", query_id=query_id, run_id=run_id,
            effective_mode=self.operating_mode, status=status, source_scope=request.scope,
            evidence=evidence, evidence_groups=groups, claims=claims,
            missing_information=[], suggestions=[],
            coverage_checks=CoverageChecks(
                source_verified=CoverageState.PASSED if evidence else CoverageState.UNKNOWN,
                effective_checked=effective_checked,
                applicability_checked=CoverageState.UNKNOWN,
                claim_supported=CoverageState.UNKNOWN,
                transition_checked=CoverageState.UNKNOWN,
                required_facts_complete=CoverageState.UNKNOWN,
                scope_expansion=CoverageState.PASSED,
            ),
            facts_revision=facts_revision, answer_generated=False,
            explanation_unavailable=False, documents=documents, answer=answer,
        )

    @classmethod
    def _request_with_memory_context(
        cls,
        request: AnalyzeRequest,
        memory_context: MemoryContext | None,
    ) -> AnalyzeRequest:
        """Resolve a follow-up with stable, explicitly confirmed session facts.

        Session messages are intentionally ignored here.  They are conversational
        history, not evidence.  A context fact is copied only when the current
        question contains a follow-up marker, has no conflicting key in the
        request, and has one unambiguous confirmed value in the snapshot.
        """

        if memory_context is None or not cls._FOLLOW_UP_RE.search(request.question):
            return request

        request_keys = {fact.key.casefold().strip() for fact in request.facts}
        confirmed: dict[str, Fact] = {}
        ambiguous: set[str] = set()
        for fact in memory_context.facts:
            if fact.status != FactStatus.USER_CONFIRMED:
                continue
            key = fact.key.casefold().strip()
            value = fact.value.strip()
            if not key or not value or key in request_keys or key in ambiguous:
                continue
            previous = confirmed.get(key)
            if previous is not None and previous.value.strip() != value:
                confirmed.pop(key, None)
                ambiguous.add(key)
                continue
            confirmed[key] = fact

        if not confirmed:
            return request
        return request.model_copy(
            update={
                "facts": [
                    *request.facts,
                    *(fact.model_copy(deep=True) for fact in confirmed.values()),
                ]
            }
        )

    @staticmethod
    def _merge_question_with_facts(request: AnalyzeRequest) -> str:
        base = request.question.strip()
        if not request.facts:
            return base
        lowered = base.casefold()
        has_explicit_article = bool(re.search(r"\bđiều\s+\d+\b", base, re.I))
        has_explicit_doc = bool(re.search(r"\b\d{1,4}/\d{4}/[A-ZĐa-zđ0-9\-]+\b", base))
        extra_parts: list[str] = []
        for fact in request.facts[: FixedPipeline._MAX_FACTS_IN_QUERY]:
            if fact.status != FactStatus.USER_CONFIRMED:
                continue
            key_cf = fact.key.casefold()
            val = fact.value.strip()
            if not val or key_cf == "question":
                continue
            if ("điều" in key_cf or key_cf == "legal_reference") and has_explicit_article:
                continue
            if ("số hiệu" in key_cf or key_cf == "document_number") and has_explicit_doc:
                continue
            if val.casefold() not in lowered:
                candidate = " ".join((*extra_parts, val))
                if len(base) + len(candidate) + 3 > FixedPipeline._MAX_EFFECTIVE_QUERY_LENGTH:
                    break
                extra_parts.append(val)
        if not extra_parts:
            return base
        return f"{base} ({' '.join(extra_parts)})"

    @staticmethod
    def _rank_evidence(evidence: list[EvidenceRef], question: str) -> list[EvidenceRef]:
        """Prefer an exact legal reference within the already authorized pool.

        This only reorders candidates. Uniqueness, temporal validity and citation
        verification still belong to their separate gates.
        """

        parsed = parse_legal_references(question)
        if not parsed.is_unique_local_reference:
            return evidence
        reference = parsed.references[0]
        article = reference.article
        if article is None:
            return evidence
        article_pattern = re.compile(
            r"\b" + re.escape(article).replace(r"\ ", r"\s+") + r"(?:\.(?!\d)|\s|$)",
            re.I,
        )
        reference_number = (
            reference_document_number(parsed.document_numbers[0])
            if len(parsed.document_numbers) == 1
            else None
        )
        document_number = (
            canonical_document_number(reference_number) if reference_number else None
        )

        def score(item: EvidenceRef) -> tuple[bool, bool, bool]:
            article_match = bool(article_pattern.search(item.label))
            document_match = bool(
                document_number
                and item.document_number
                and canonical_document_number(
                    reference_document_number(item.document_number) or item.document_number
                )
                == document_number
            )
            return (article_match and document_match, article_match, document_match)

        return sorted(evidence, key=score, reverse=True)

    @staticmethod
    def _matches_legal_reference(item: EvidenceRef, parsed: ParsedReferences) -> bool:
        if not parsed.is_unique_local_reference:
            return True
        reference = parsed.references[0]
        if reference.article is None:
            return False
        article_pattern = re.compile(
            r"\b" + re.escape(reference.article).replace(r"\ ", r"\s+") + r"(?:\.(?!\d)|\s|$)",
            re.I,
        )
        if not article_pattern.search(item.label):
            return False
        if len(parsed.document_numbers) > 1:
            return False
        if not parsed.document_numbers:
            return True
        expected = canonical_document_number(
            reference_document_number(parsed.document_numbers[0])
            or parsed.document_numbers[0]
        )
        actual = canonical_document_number(
            reference_document_number(item.document_number or "") or item.document_number or ""
        )
        return bool(actual) and actual == expected

    _BLOCKED_STATES = {
        AmendmentStatus.REPEALED: "đã bị bãi bỏ",
        AmendmentStatus.REPLACED: "đã bị thay thế",
        AmendmentStatus.SUSPENDED: "đang bị tạm đình chỉ",
        AmendmentStatus.NOT_YET_EFFECTIVE: "chưa có hiệu lực",
    }

    @classmethod
    def _exclude_blocked_evidence(
        cls, claim_evidence: list[EvidenceRef], parsed: ParsedReferences
    ) -> tuple[list[EvidenceRef], list[str]]:
        """Keep repealed/suspended/not-yet-effective clauses out of every claim.

        The whole conclusion is withheld when the blocked clause is what the user
        asked for: the top-ranked candidate, or a clause matching an explicitly
        cited article *and* document number.  Otherwise only the blocked clauses
        are dropped; they stay visible as evidence cards with their status, and
        the remaining claims are at most conditional (``effective_checked`` is
        ``failed`` for the evidence set).
        """

        blocked = [item for item in claim_evidence if item.amendment_state in cls._BLOCKED_STATES]
        if not blocked:
            return claim_evidence, []
        lead = claim_evidence[0]
        cited_document = parsed.is_unique_local_reference and len(parsed.document_numbers) == 1
        if lead.amendment_state in cls._BLOCKED_STATES or cited_document:
            target = lead if lead.amendment_state in cls._BLOCKED_STATES else blocked[0]
            return [], [
                f"{cls._describe(target)} {cls._BLOCKED_STATES[target.amendment_state]} "
                f"tại ngày {target.as_of_date:%d/%m/%Y} nên không đưa ra kết luận. "
                "Hãy kiểm tra văn bản sửa đổi, thay thế hoặc ngày hiệu lực."
            ]
        kept = [item for item in claim_evidence if item.amendment_state not in cls._BLOCKED_STATES]
        listed = "; ".join(
            f"{cls._describe(item)} ({cls._BLOCKED_STATES[item.amendment_state]})"
            for item in blocked[:3]
        )
        more = f" và {len(blocked) - 3} căn cứ khác" if len(blocked) > 3 else ""
        return kept, [
            f"Đã loại {len(blocked)} căn cứ không áp dụng được tại ngày "
            f"{blocked[0].as_of_date:%d/%m/%Y} khỏi kết luận: {listed}{more}."
        ]

    @staticmethod
    def _verification_notes(evidence: list[EvidenceRef]) -> list[str]:
        """D12: unverified effectivity never blocks the answer; it is stated instead."""

        unverified = [
            item for item in evidence
            if item.effectivity is None or item.effectivity.verification != "verified"
        ]
        if not unverified:
            return []
        return [
            f"{len(unverified)}/{len(evidence)} căn cứ chưa được xác minh hiệu lực tại ngày "
            f"{unverified[0].as_of_date:%d/%m/%Y}; nội dung đã kiểm nguồn nhưng cần đối chiếu "
            "hiệu lực trước khi sử dụng."
        ]

    @staticmethod
    def _describe(item: EvidenceRef) -> str:
        label = " ".join(item.label.split()).rstrip(" .")
        if len(label) > 60:
            label = label[:59].rstrip() + "…"
        return f"{label} ({item.document_number or item.title})"

    @staticmethod
    def _effectivity_coverage(evidence: list[EvidenceRef]) -> CoverageState:
        if not evidence:
            return CoverageState.UNKNOWN
        blocked = {
            AmendmentStatus.REPEALED,
            AmendmentStatus.REPLACED,
            AmendmentStatus.SUSPENDED,
            AmendmentStatus.NOT_YET_EFFECTIVE,
        }
        if any(item.amendment_state in blocked for item in evidence):
            return CoverageState.FAILED
        if any(item.amendment_state == AmendmentStatus.UNKNOWN for item in evidence):
            return CoverageState.UNKNOWN
        if all(
            item.amendment_state in {AmendmentStatus.ACTIVE, AmendmentStatus.MODIFIED}
            for item in evidence
        ):
            return CoverageState.PASSED
        return CoverageState.UNKNOWN

    @staticmethod
    def _group_evidence(evidence: list[EvidenceRef]) -> list[EvidenceGroup]:
        groups: dict[tuple[UUID, str], list[EvidenceRef]] = {}
        for item in evidence:
            role = item.label.split(" ")[0] or "other"
            groups.setdefault((item.document_version_id, role), []).append(item)
        return [
            EvidenceGroup(
                group_id=f"group_{version_id.hex}_{role}",
                purpose=role,
                evidence_ids=[item.evidence_id for item in members],
                roles=[role],
            )
            for (version_id, role), members in groups.items()
        ]

    @staticmethod
    def _extractive_claims(evidence: list[EvidenceRef]) -> list[Claim]:
        return [
            Claim(
                text=item.quote_exact,
                evidence_ids=[item.evidence_id],
                status="conditional",
            )
            for item in evidence[:8]
            if item.quote_exact.strip()
        ]

    @staticmethod
    def _unclaimed_for_suggestions(
        claim_evidence: list[EvidenceRef], evidence: list[EvidenceRef]
    ) -> list[EvidenceRef]:
        """Keep the lead claim, then offer only evidence not already shown as a claim.

        Suggestions are cross-check pointers; repeating an evidence item that is
        already rendered as a claim adds noise and no new source.
        """

        if not claim_evidence:
            return []
        shown = {item.evidence_id for item in claim_evidence[:8]}
        return [claim_evidence[0], *(item for item in evidence if item.evidence_id not in shown)]

    @staticmethod
    def _build_suggestions(evidence: list[EvidenceRef]) -> list[Claim]:
        if len(evidence) <= 1:
            return []
        suggestions: list[Claim] = []
        for related in evidence[1:4]:
            doc_label = related.document_number or related.title
            page_label = f", trang {related.page}" if related.page else ""
            raw_snippet = " ".join(related.quote_exact.split())
            snippet = (
                raw_snippet[:110].rstrip() + "…"
                if len(raw_snippet) > 110
                else raw_snippet
            )
            fallback_text = (
                f"Đối chiếu thêm {related.label} ({doc_label}{page_label}) "
                "để xem xét đầy đủ các quy định có liên quan."
            )
            text = (
                f"Đối chiếu thêm {related.label} ({doc_label}{page_label}) — “{snippet}”"
                if snippet
                else fallback_text
            )
            suggestions.append(
                Claim(
                    text=text,
                    evidence_ids=[related.evidence_id],
                    status="needs_review",
                )
            )
        return suggestions
