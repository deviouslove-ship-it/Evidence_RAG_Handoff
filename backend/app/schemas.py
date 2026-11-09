"""API and domain schemas shared by the REST and SSE contracts."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from .ai_limits import MAX_AI_OUTPUT_TOKENS


class ScopeMode(StrEnum):
    SELECTED = "SELECTED"
    ALL_AUTHORIZED = "ALL_AUTHORIZED"


class FactStatus(StrEnum):
    USER_CONFIRMED = "user_confirmed"
    EXTRACTED_UNCONFIRMED = "extracted_unconfirmed"
    INFERRED_UNCERTAIN = "inferred_uncertain"


class AmendmentStatus(StrEnum):
    """Axis A (effective status) at the requested date."""

    ACTIVE = "active"
    MODIFIED = "modified"
    REPEALED = "repealed"
    REPLACED = "replaced"
    SUSPENDED = "suspended"
    NOT_YET_EFFECTIVE = "not_yet_effective"
    UNKNOWN = "unknown"


class VerificationState(StrEnum):
    """Axis B: Đã xác minh · Chưa xác minh · Không tìm thấy thông tin trong kho."""

    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    NOT_FOUND = "not_found"


class EffectivityView(BaseModel):
    """Both axes of one document or clause at ``as_of_date`` (design §4)."""

    model_config = ConfigDict(extra="forbid")

    status: AmendmentStatus = AmendmentStatus.UNKNOWN
    verification: VerificationState = VerificationState.NOT_FOUND
    level: Literal["document", "node"] = "document"
    as_of_date: date | None = None
    notes: list[str] = Field(default_factory=list)
    verification_source: str | None = None
    verified_by: str | None = None
    verified_at: str | None = None
    pending_proposals: int = 0
    clause_level_reviewed: bool = False
    data_date: date | None = None


class ResultStatus(StrEnum):
    EVIDENCE_FOUND = "evidence_found"
    CONDITIONAL = "conditional"
    INSUFFICIENT = "insufficient"
    CONFLICTING = "conflicting"


class CoverageState(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    UNKNOWN = "unknown"


class Fact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=2000)
    status: FactStatus = FactStatus.EXTRACTED_UNCONFIRMED
    source: str | None = Field(default=None, max_length=2000)


class Scope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope_mode: ScopeMode
    category_ids: list[UUID] = Field(default_factory=list, max_length=100)
    document_types: list[str] = Field(default_factory=list, max_length=30)
    as_of_date: date


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=10000)
    scope: Scope
    facts: list[Fact] = Field(default_factory=list, max_length=32)
    base_query_id: UUID | None = None
    base_facts_revision: str | None = None
    # "Phân tích sâu": in API mode (Hybrid Auto) try the escalation profile first.
    deep_analysis: bool = False


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    document_id: UUID
    document_version_id: UUID
    node_id: UUID
    document_number: str | None = None
    title: str
    label: str
    quote_exact: str
    page: int | None = None
    source_hash: str
    as_of_date: date
    amendment_state: AmendmentStatus = AmendmentStatus.UNKNOWN
    viewer_url: str
    outside_scope: bool = False
    effectivity: EffectivityView | None = None
    # The uploaded file (PDF itself, or the Word/TXT original), never a derived copy.
    original_url: str | None = None


class EvidenceGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_id: str
    purpose: str
    evidence_ids: list[str]
    roles: list[str]


class TextSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: int = Field(ge=0)
    end: int = Field(ge=0)


class Excerpt(BaseModel):
    """A verbatim slice of the clause's ``quote_exact`` (offsets into it)."""

    model_config = ConfigDict(extra="forbid")

    start: int = Field(ge=0)
    end: int = Field(ge=0)
    text: str
    truncated_before: bool = False
    truncated_after: bool = False
    highlights: list[TextSpan] = Field(default_factory=list)


class AnswerClause(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    node_id: UUID
    label: str
    heading: str | None = None
    page: int | None = None
    page_end: int | None = None
    # direct: the question's phrases are in the clause; related: shares the rarest
    # phrases or was found by meaning; reference: a list naming other documents.
    tier: Literal["direct", "related", "reference"]
    # phrase | terms | semantic | concept | relation | number | article | partial
    match: str
    matched_terms: list[str] = Field(default_factory=list)
    excerpt: Excerpt
    topics: list[str] = Field(default_factory=list)
    same_as: list[str] = Field(default_factory=list)
    # Other matching clauses of the same Điều (labels only, e.g. "Khoản 3 Điều 5").
    also_matched: list[str] = Field(default_factory=list)
    effectivity: EffectivityView | None = None
    # The quote is OCR text of a scanned page that a reviewer confirmed against the scan.
    ocr: bool = False


class DocumentRelation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    label: str
    target_number: str | None = None
    verified: bool = False
    source: str


class AnswerDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: UUID
    document_version_id: UUID
    doc_type: str
    doc_type_label: str
    document_number: str | None = None
    title: str
    issuing_body: str | None = None
    publication_date: date | None = None
    source_format: str = "pdf"
    original_filename: str | None = None
    original_url: str
    viewer_url: str
    # direct | related | reference (only lists/mentions other documents)
    role: Literal["direct", "related", "reference"]
    kind_label: str | None = None
    relations: list[DocumentRelation] = Field(default_factory=list)
    effectivity: EffectivityView | None = None
    clauses: list[AnswerClause] = Field(default_factory=list)
    more_clauses: int = 0


class AnswerTopic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    references: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class ChatAnswer(BaseModel):
    """Structured answer written from retrieved metadata and labels only (no model)."""

    model_config = ConfigDict(extra="forbid")

    outcome: Literal["direct", "related_only", "not_found"]
    understood_phrases: list[str] = Field(default_factory=list)
    summary: str
    points: list[str] = Field(default_factory=list)
    topics: list[AnswerTopic] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    result_set_id: str | None = None


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    evidence_ids: list[str] = Field(default_factory=list)
    status: str = "conditional"


class CoverageChecks(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_verified: CoverageState = CoverageState.UNKNOWN
    effective_checked: CoverageState = CoverageState.UNKNOWN
    applicability_checked: CoverageState = CoverageState.UNKNOWN
    claim_supported: CoverageState = CoverageState.UNKNOWN
    transition_checked: CoverageState = CoverageState.UNKNOWN
    required_facts_complete: CoverageState = CoverageState.UNKNOWN
    scope_expansion: CoverageState = CoverageState.UNKNOWN


class AnalyzeResponse(BaseModel):
    request_id: str
    query_id: str
    run_id: str
    facts_revision: str
    understood_as: str
    facts: list[Fact]
    missing_information: list[str] = Field(default_factory=list)
    aspects: list[str] = Field(default_factory=list)
    query_rewrites: list[str] = Field(default_factory=list)


class QueryResponse(BaseModel):
    request_id: str
    query_id: str
    run_id: str
    effective_mode: str
    status: ResultStatus
    source_scope: Scope
    evidence: list[EvidenceRef] = Field(default_factory=list)
    evidence_groups: list[EvidenceGroup] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    suggestions: list[Claim] = Field(default_factory=list)
    coverage_checks: CoverageChecks = Field(default_factory=CoverageChecks)
    facts_revision: str
    snapshot_revision: str | None = None
    answer_generated: bool = False
    ai_selection_applied: bool = False
    # Evidence-derived content was sent to a public (external) model in this turn.
    external_ai_used: bool = False
    # A cost cap kept a configured model from running; the result is model-free.
    ai_limited: bool = False
    explanation_unavailable: bool = False
    disclaimer: str = (
        "Kết quả chỉ hỗ trợ tra cứu và tham mưu, không thay thế quyết định "
        "của người có thẩm quyền."
    )
    # One entry per document, its relevant clauses inside; and the structured answer.
    documents: list[AnswerDocument] = Field(default_factory=list)
    answer: ChatAnswer | None = None


class SessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incognito: bool = True
    scope: Scope | None = None


class SessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    persistence_state: str
    expires_at: str
    facts_revision: str
    memory_revision: str


class TurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=10000)
    scope: Scope
    facts: list[Fact] = Field(default_factory=list, max_length=32)
    deep_analysis: bool = False


class MemoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    kind: str
    content: str
    created_at: str
    expires_at: str | None = None


class MemoryListResponse(BaseModel):
    items: list[MemoryItem]
    persistence_state: str
    memory_revision: str


class PreferencesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_category_ids: list[UUID] = Field(default_factory=list)
    default_as_of_date: date | None = None
    enabled: bool = False


class CitationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence: EvidenceRef
    quote_exact: str
    amendment_state: AmendmentStatus
    as_of_date: date


class PdfPagePreview(BaseModel):
    page_number: int
    extraction_method: str
    text_quality: str
    text_characters: int
    extraction_error: str | None = None


class PdfPreviewResponse(BaseModel):
    status: str = "preview_only"
    sha256: str
    size_bytes: int
    page_count: int
    node_count: int
    review_required_pages: int
    pages: list[PdfPagePreview]


class PotentialDuplicate(BaseModel):
    document_version_id: UUID
    title: str
    document_number: str | None
    status: str


class PdfContentDuplicates(BaseModel):
    content_check_available: bool
    potential_duplicates: list[PotentialDuplicate]


class PdfDraftResponse(BaseModel):
    status: str = "draft"
    document_id: UUID
    document_version_id: UUID
    sha256: str
    page_count: int
    node_count: int
    review_required_pages: int
    content_check_available: bool = False
    potential_duplicates: list[PotentialDuplicate] = Field(default_factory=list)


class PdfDraftListItem(BaseModel):
    document_id: UUID
    document_version_id: UUID
    title: str
    doc_type: str
    document_number: str | None
    status: str
    sha256: str
    page_count: int
    open_review_tasks: int
    source_review_revision: int | None = None
    # G1: dates read by rule, confirmed by the reviewer together with the source.
    detected_issue_date: date | None = None
    detected_effective_from: date | None = None
    detected_effective_quote: str | None = None


class PdfReextractResponse(BaseModel):
    status: str
    pages_restored: int
    nodes_anchored: int
    nodes_unresolved: int
    possible_duplicates: int


class ModelParams(BaseModel):
    """Bounded generation settings an admin may store on a profile."""

    model_config = ConfigDict(extra="forbid")

    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, gt=0, le=1)
    max_tokens: int | None = Field(default=None, ge=1, le=MAX_AI_OUTPUT_TOKENS)
    json_mode: bool = False
    # Thinking models (Gemini 2.5+/3.x, GPT-5.x, Qwen3, Gemma 4) spend part of the token
    # budget on reasoning.  Choosing a low effort keeps the short JSON answer inside it.
    reasoning_effort: Literal["none", "minimal", "low", "medium", "high"] | None = None
    # GPT-5.x and o-series reject "max_tokens" and expect "max_completion_tokens".
    token_limit_field: Literal["max_tokens", "max_completion_tokens"] = "max_tokens"
    # Embedding profiles only: requested vector size for models that can shorten their
    # output ("dimensions" in the OpenAI-compatible API).  None = the model's own size.
    embedding_dimensions: int | None = Field(default=None, ge=1, le=4000)

    def to_stored(self) -> dict[str, Any]:
        stored: dict[str, Any] = {}
        if self.temperature is not None:
            stored["temperature"] = self.temperature
        if self.top_p is not None:
            stored["top_p"] = self.top_p
        if self.max_tokens is not None:
            stored["max_tokens"] = self.max_tokens
        if self.json_mode:
            stored["response_format"] = {"type": "json_object"}
        if self.reasoning_effort is not None:
            stored["reasoning_effort"] = self.reasoning_effort
        if self.token_limit_field != "max_tokens":
            stored["token_limit_field"] = self.token_limit_field
        if self.embedding_dimensions is not None:
            stored["dimensions"] = self.embedding_dimensions
        return stored


class ModelProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str = Field(min_length=1, max_length=100)
    adapter: str = Field(min_length=1, max_length=50)
    endpoint: str = Field(min_length=1, max_length=1000)
    model_id: str = Field(min_length=1, max_length=300)
    # One role (as before) or several text-generation roles; "embedding" stands alone.
    capabilities: list[str] = Field(min_length=1, max_length=8)
    privacy_zone: str = Field(min_length=1, max_length=80)
    revision: str = Field(min_length=1, max_length=100)
    # env:NAME (key in the server environment) or secret:NAME (key in the server key store).
    secret_ref: str | None = Field(
        default=None, max_length=132,
        pattern=r"^(?:env:[A-Za-z_][A-Za-z0-9_]{0,127}|secret:[A-Za-z0-9][A-Za-z0-9_.-]{0,99})$",
    )
    # A key typed in the Admin Portal.  Written once to the key store (replacing
    # ``secret_ref`` with a ``secret:`` reference), never stored in the database, never
    # returned, never logged.
    api_key: SecretStr | None = Field(default=None, min_length=1, max_length=4096)
    fallback: list[str] = Field(default_factory=list, max_length=1)
    provider_approved: bool = False
    params: ModelParams | None = None
    # Prices per million tokens and spending caps (G1.0).  Omitted = not set.
    input_price_per_mtok: float | None = Field(default=None, ge=0, le=1_000_000)
    output_price_per_mtok: float | None = Field(default=None, ge=0, le=1_000_000)
    daily_cost_limit: float | None = Field(default=None, ge=0, le=1_000_000_000)
    monthly_cost_limit: float | None = Field(default=None, ge=0, le=1_000_000_000)


class StagePolicyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str = Field(min_length=1, max_length=16)
    stage: str = Field(min_length=1, max_length=80)
    max_attempts: int = Field(ge=1, le=10)
    max_output_tokens: int | None = Field(default=None, ge=1, le=16_384)
    timeout_seconds: float | None = Field(default=None, gt=0, le=30)
    max_concurrency: int | None = Field(default=None, ge=1, le=64)


class ApiError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    trace_id: str
    details: dict[str, Any] = Field(default_factory=dict)

class SearchMatchType(StrEnum):
    EXACT_PHRASE = "exact_phrase"
    PHRASE_FOLDED = "phrase_folded"
    ALL_TERMS = "all_terms"
    ANY_TERM = "any_term"


class SearchEmptyReason(StrEnum):
    NO_AUTHORIZED_DOCUMENTS = "NO_AUTHORIZED_DOCUMENTS"
    NO_RESULTS = "NO_RESULTS"
    PHRASE_NOT_FOUND = "PHRASE_NOT_FOUND"


class SearchQueryInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original: str
    phrase: str | None = None
    mode: str
    normalization_revision: str


class SearchHighlight(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: int = Field(ge=0)
    end: int = Field(ge=0)


class SearchClause(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    label: str
    page: int | None = None
    match_type: SearchMatchType
    amendment_state: AmendmentStatus = AmendmentStatus.UNKNOWN
    amendment_as_of: date
    quote_exact: str
    snippet: str
    snippet_start: int = 0
    highlights: list[SearchHighlight] = Field(default_factory=list)
    viewer_url: str
    source_hash: str
    effectivity: EffectivityView | None = None


class SearchDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    document_version_id: str
    document_number: str | None = None
    title: str
    doc_type: str
    issuing_body: str | None = None
    official_url: str | None = None
    matched_clause_count: int = 0
    clause_page: int = 1
    clause_page_size: int = 5
    has_more_clauses: bool = False
    clauses: list[SearchClause] = Field(default_factory=list)
    effectivity: EffectivityView | None = None


class SearchTotals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    documents: int = 0
    clauses: int = 0
    approximate_matches_hidden: int = 0
    # True when more than ``count_cap`` clauses matched: ``clauses`` is then
    # ``count_cap`` and documents/ranking cover only the first clauses examined.
    capped: bool = False
    count_cap: int | None = None


class SearchApproximate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collapsed: bool = True
    total_clauses: int = 0
    capped: bool = False


class SearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: SearchQueryInfo
    phrase_found: bool = False
    totals: SearchTotals = Field(default_factory=SearchTotals)
    page: int = 1
    page_size: int = 20
    has_more: bool = False
    effectivity_snapshot_status: str = "stale"
    results: list[SearchDocument] = Field(default_factory=list)
    approximate: SearchApproximate = Field(default_factory=SearchApproximate)
    empty_reason: SearchEmptyReason | None = None
    # Fixed banner until clause-level effectivity is reviewed (design §4, G3).
    clause_level_warning: str | None = None
    data_date: date | None = None