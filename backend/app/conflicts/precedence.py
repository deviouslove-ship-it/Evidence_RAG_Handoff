"""Deterministic legal precedence & effectivity assessment (Phase 2, D2).

Pure-Python evaluation of legal authority hierarchy and effectivity precedence
between two documents, consuming ``legal_authority_rules`` rows and approved
``node_amendments`` / effectivity statuses without database or network I/O.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from app.schemas import AmendmentStatus
from app.vietnamese_nlp.unicode_norm import fold_text

PrecedenceResult = Literal[
    "higher_authority_a",
    "higher_authority_b",
    "same_tier_newer_a",
    "same_tier_newer_b",
    "superseded_by_amendment",
    "undetermined_requires_review",
]

IN_FORCE_STATUSES: frozenset[str] = frozenset(
    {AmendmentStatus.ACTIVE.value, AmendmentStatus.MODIFIED.value}
)
INACTIVE_STATUSES: frozenset[str] = frozenset(
    {
        AmendmentStatus.REPEALED.value,
        AmendmentStatus.REPLACED.value,
        AmendmentStatus.SUSPENDED.value,
        AmendmentStatus.NOT_YET_EFFECTIVE.value,
    }
)
AMENDMENT_PRECEDENCE_ACTIONS: frozenset[str] = frozenset(
    {"replace", "repeal", "repeal_partial", "modify", "suspend"}
)

UNKNOWN_STATUS_CAVEAT = (
    "Trạng thái hiệu lực tại ngày đối chiếu chưa được xác minh (unknown) "
    "— kết quả thứ bậc chỉ mang tính tham khảo cấu trúc."
)
LEX_SPECIALIS_CAVEAT = (
    "Kiểm tra nguyên tắc văn bản chuyên ngành (lex specialis): nếu văn bản ban hành trước "
    "là quy định chuyên ngành cụ thể, văn bản sau không tự động thay thế nếu không có điều "
    "khoản bãi bỏ/sửa đổi."
)
AMBIGUOUS_ISSUER_REASON = "Loại văn bản cần xác định rõ cơ quan ban hành"
REFERENCE_NOTICE = "Gợi ý tự động — cần chuyên viên thẩm định trước khi áp dụng"

_PUNCTUATION_RE = re.compile(r"[.,;:/()\-–—]+")
_WHITESPACE_RE = re.compile(r"\s+")
_AGENCY_PREFIX_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bubnd\b"), "uy ban nhan dan"),
    (re.compile(r"\bhdnd\b"), "hoi dong nhan dan"),
    (re.compile(r"\bubtvqh\b"), "uy ban thuong vu quoc hoi"),
    (re.compile(r"\btp\b"), "thanh pho"),
    (re.compile(r"\bbo truong\s+(?=bo\s)"), ""),
)
_PARTIAL_AMENDMENT_ACTIONS = frozenset({"modify", "repeal_partial"})


@dataclass(frozen=True)
class AuthorityRule:
    """One row from ``legal_authority_rules``."""

    rule_code: str
    doc_type: str
    issuing_body_pattern: str | None
    authority_rank: int
    authority_tier_label: str
    is_ambiguous_without_issuer: bool = False
    match_priority: int = 100
    is_active: bool = True
    note: str | None = None


@dataclass(frozen=True)
class DocumentAuthorityMeta:
    """Authority and effectivity metadata for one document in a comparison pair."""

    document_id: str
    doc_type: str
    issuing_body: str | None = None
    document_number: str | None = None
    effective_from: date | None = None
    publication_date: date | None = None
    effective_status_at_date: AmendmentStatus | str = AmendmentStatus.UNKNOWN


@dataclass(frozen=True)
class AmendmentBetweenPair:
    """Approved ``node_amendments`` relation directly linking two documents."""

    source_document_id: str
    target_document_id: str
    action: str
    amendment_id: str | None = None
    effective_from: date | None = None
    description: str | None = None
    approved: bool = True


@dataclass(frozen=True)
class ResolvedAuthorityTier:
    """Result of matching a document against ``legal_authority_rules``."""

    tier: AuthorityRule | None
    reason: str | None = None
    fallback_rule: AuthorityRule | None = None

    @property
    def rule_code(self) -> str | None:
        return self.tier.rule_code if self.tier is not None else None

    @property
    def authority_rank(self) -> int | None:
        return self.tier.authority_rank if self.tier is not None else None

    @property
    def authority_tier_label(self) -> str | None:
        return self.tier.authority_tier_label if self.tier is not None else None


@dataclass(frozen=True)
class PrecedenceAssessment:
    """Structured legal precedence assessment for a document pair."""

    precedence_result: PrecedenceResult
    basis: str
    caveats: tuple[str, ...] = ()
    tier_a: AuthorityRule | None = None
    tier_b: AuthorityRule | None = None
    status_a: str = AmendmentStatus.UNKNOWN.value
    status_b: str = AmendmentStatus.UNKNOWN.value
    preferred_document_id: str | None = None
    as_of_date: date | None = None
    reference_notice: str = REFERENCE_NOTICE

    def to_basis_json(self) -> dict[str, Any]:
        """Serialize rationale for ``conflict_findings.precedence_basis_json``."""

        return {
            "precedence_result": self.precedence_result,
            "preferred_document_id": self.preferred_document_id,
            "basis": self.basis,
            "caveats": list(self.caveats),
            "status_a": self.status_a,
            "status_b": self.status_b,
            "as_of_date": self.as_of_date.isoformat() if self.as_of_date else None,
            "tier_a": _tier_to_dict(self.tier_a),
            "tier_b": _tier_to_dict(self.tier_b),
            "reference_notice": self.reference_notice,
        }


def _tier_to_dict(tier: AuthorityRule | None) -> dict[str, Any] | None:
    if tier is None:
        return None
    return {
        "rule_code": tier.rule_code,
        "doc_type": tier.doc_type,
        "authority_rank": tier.authority_rank,
        "authority_tier_label": tier.authority_tier_label,
    }


def _fold_collapse_issuer(issuing_body: str | None) -> str:
    if not issuing_body:
        return ""
    value = fold_text(issuing_body)
    value = _PUNCTUATION_RE.sub(" ", value)
    return _WHITESPACE_RE.sub(" ", value).strip()


def normalize_issuing_authority(issuing_body: str | None) -> str:
    """Fold accents, punctuation, whitespace, and unambiguous agency prefixes."""

    value = _fold_collapse_issuer(issuing_body)
    if not value:
        return ""
    for pattern, replacement in _AGENCY_PREFIX_REPLACEMENTS:
        value = pattern.sub(replacement, value)
    return _WHITESPACE_RE.sub(" ", value).strip()


def same_issuing_authority(issuer_a: str | None, issuer_b: str | None) -> bool:
    """Return True only when both issuing bodies normalize to the same non-empty agency."""

    norm_a = normalize_issuing_authority(issuer_a)
    norm_b = normalize_issuing_authority(issuer_b)
    return bool(norm_a and norm_b and norm_a == norm_b)


def _fold_pattern_non_ascii(pattern: str) -> str:
    """Fold non-ASCII Vietnamese letters in a regex pattern while preserving regex tokens."""

    return "".join(fold_text(ch) if ord(ch) > 127 else ch for ch in pattern)


def _pattern_matches(
    pattern: str, normalized_issuer: str, raw_folded_issuer: str = ""
) -> bool:
    candidates = tuple(c for c in (normalized_issuer, raw_folded_issuer) if c)
    if not candidates:
        return False
    folded_pattern = _fold_pattern_non_ascii(pattern)
    try:
        compiled = re.compile(folded_pattern, re.IGNORECASE)
        return any(compiled.search(candidate) is not None for candidate in candidates)
    except re.error:
        folded_literal = fold_text(pattern)
        return any(folded_literal in candidate for candidate in candidates)


def resolve_authority_tier(
    doc_type: str,
    issuing_body: str | None,
    rules: Sequence[AuthorityRule],
) -> ResolvedAuthorityTier:
    """Match ``doc_type`` and folded ``issuing_body`` against ``legal_authority_rules``."""

    normalized_doc_type = doc_type.strip().lower()
    matching_rules = sorted(
        (
            rule
            for rule in rules
            if rule.is_active and rule.doc_type.strip().lower() == normalized_doc_type
        ),
        key=lambda r: (0 if r.issuing_body_pattern else 1, r.match_priority, r.rule_code),
    )
    if not matching_rules:
        return ResolvedAuthorityTier(
            tier=None,
            reason="Không có quy tắc thứ bậc phù hợp cho loại văn bản này",
        )

    raw_folded_issuer = _fold_collapse_issuer(issuing_body)
    normalized_issuer = normalize_issuing_authority(issuing_body)
    fallback_rules: list[AuthorityRule] = []
    for rule in matching_rules:
        if rule.issuing_body_pattern:
            if _pattern_matches(rule.issuing_body_pattern, normalized_issuer, raw_folded_issuer):
                return ResolvedAuthorityTier(tier=rule)
        else:
            fallback_rules.append(rule)

    if fallback_rules:
        fallback = fallback_rules[0]
        if fallback.is_ambiguous_without_issuer:
            return ResolvedAuthorityTier(
                tier=None,
                reason=AMBIGUOUS_ISSUER_REASON,
                fallback_rule=fallback,
            )
        return ResolvedAuthorityTier(tier=fallback)

    return ResolvedAuthorityTier(
        tier=None,
        reason=AMBIGUOUS_ISSUER_REASON,
    )


def _normalize_status(status: AmendmentStatus | str | None) -> str:
    if status is None:
        return AmendmentStatus.UNKNOWN.value
    raw = status.value if isinstance(status, AmendmentStatus) else str(status)
    cleaned = raw.strip().lower()
    if (
        cleaned in IN_FORCE_STATUSES
        or cleaned in INACTIVE_STATUSES
        or cleaned == AmendmentStatus.UNKNOWN.value
    ):
        return cleaned
    return AmendmentStatus.UNKNOWN.value


def _doc_label(doc: DocumentAuthorityMeta) -> str:
    if doc.document_number:
        return f"{doc.document_id} ({doc.document_number})"
    return doc.document_id


def _effective_date_with_source(doc: DocumentAuthorityMeta) -> tuple[date | None, str]:
    if doc.effective_from is not None:
        return doc.effective_from, "ngày có hiệu lực"
    if doc.publication_date is not None:
        return doc.publication_date, "ngày ban hành/công bố"
    return None, "chưa rõ ngày"


def _active_amendments_between(
    doc_a: DocumentAuthorityMeta,
    doc_b: DocumentAuthorityMeta,
    approved_amendments: Sequence[AmendmentBetweenPair],
    as_of_date: date | None,
) -> tuple[list[AmendmentBetweenPair], list[AmendmentBetweenPair]]:
    """Return ``(b_amends_a, a_amends_b)`` for approved active relations at ``as_of_date``."""

    if doc_a.document_id == doc_b.document_id:
        return [], []
    b_amends_a: list[AmendmentBetweenPair] = []
    a_amends_b: list[AmendmentBetweenPair] = []
    for amendment in approved_amendments:
        if not amendment.approved:
            continue
        if amendment.action.strip().lower() not in AMENDMENT_PRECEDENCE_ACTIONS:
            continue
        if (
            as_of_date is not None
            and amendment.effective_from is not None
            and amendment.effective_from > as_of_date
        ):
            continue
        if (
            amendment.source_document_id == doc_b.document_id
            and amendment.target_document_id == doc_a.document_id
        ):
            b_amends_a.append(amendment)
        elif (
            amendment.source_document_id == doc_a.document_id
            and amendment.target_document_id == doc_b.document_id
        ):
            a_amends_b.append(amendment)
    return b_amends_a, a_amends_b


def _format_tier_summary(label: str, tier: AuthorityRule) -> str:
    return (
        f"{label}: {tier.authority_tier_label} "
        f"[rule_code={tier.rule_code}, rank={tier.authority_rank}]"
    )


def _evaluate_amendment_step(
    doc_a: DocumentAuthorityMeta,
    doc_b: DocumentAuthorityMeta,
    tier_a: ResolvedAuthorityTier,
    tier_b: ResolvedAuthorityTier,
    status_a: str,
    status_b: str,
    approved_amendments: Sequence[AmendmentBetweenPair],
    as_of_date: date | None,
) -> PrecedenceAssessment | None:
    b_amends_a, a_amends_b = _active_amendments_between(
        doc_a, doc_b, approved_amendments, as_of_date
    )
    if b_amends_a and a_amends_b:
        return PrecedenceAssessment(
            precedence_result="undetermined_requires_review",
            basis=(
                f"Cả hai văn bản {_doc_label(doc_a)} và {_doc_label(doc_b)} đều có quan hệ "
                "sửa đổi/thay thế chéo đã được duyệt tại ngày đối chiếu — cần chuyên viên rà soát."
            ),
            tier_a=tier_a.tier,
            tier_b=tier_b.tier,
            status_a=status_a,
            status_b=status_b,
            preferred_document_id=None,
            as_of_date=as_of_date,
        )
    if b_amends_a or a_amends_b:
        amending_doc, amending_status, target_doc, target_status, relations = (
            (doc_b, status_b, doc_a, status_a, b_amends_a)
            if b_amends_a
            else (doc_a, status_a, doc_b, status_b, a_amends_b)
        )
        actions = sorted({rel.action.strip().lower() for rel in relations})
        actions_text = ", ".join(actions)
        if amending_status in INACTIVE_STATUSES:
            inactive_caveats: tuple[str, ...] = (
                (UNKNOWN_STATUS_CAVEAT,)
                if target_status == AmendmentStatus.UNKNOWN.value
                else ()
            )
            return PrecedenceAssessment(
                precedence_result="undetermined_requires_review",
                basis=(
                    f"Văn bản {_doc_label(amending_doc)} có quan hệ sửa đổi/thay thế đã duyệt "
                    f"({actions_text}) lên {_doc_label(target_doc)}, nhưng bản thân "
                    f"{_doc_label(amending_doc)} đang ở trạng thái không còn/chưa có hiệu lực "
                    f"({amending_status}) tại ngày đối chiếu — cần chuyên viên thẩm định."
                ),
                caveats=inactive_caveats,
                tier_a=tier_a.tier,
                tier_b=tier_b.tier,
                status_a=status_a,
                status_b=status_b,
                preferred_document_id=None,
                as_of_date=as_of_date,
            )
        caveats: tuple[str, ...] = ()
        if all(action in _PARTIAL_AMENDMENT_ACTIONS for action in actions):
            caveats = (
                "Quan hệ là sửa đổi/bãi bỏ một phần — chỉ ưu tiên văn bản sửa đổi đối với "
                "phần nội dung bị tác động.",
            )
        return PrecedenceAssessment(
            precedence_result="superseded_by_amendment",
            basis=(
                f"Văn bản {_doc_label(amending_doc)} đã có quan hệ được duyệt ({actions_text}) "
                f"tác động trực tiếp lên {_doc_label(target_doc)}; ưu tiên văn bản đang "
                f"sửa đổi/thay thế {_doc_label(amending_doc)}."
            ),
            caveats=caveats,
            tier_a=tier_a.tier,
            tier_b=tier_b.tier,
            status_a=status_a,
            status_b=status_b,
            preferred_document_id=amending_doc.document_id,
            as_of_date=as_of_date,
        )

    a_in_force = status_a in IN_FORCE_STATUSES
    b_in_force = status_b in IN_FORCE_STATUSES
    a_inactive = status_a in INACTIVE_STATUSES
    b_inactive = status_b in INACTIVE_STATUSES

    if (a_in_force and b_inactive) or (b_in_force and a_inactive):
        in_force_doc, in_force_st, inactive_doc, inactive_st = (
            (doc_a, status_a, doc_b, status_b)
            if a_in_force
            else (doc_b, status_b, doc_a, status_a)
        )
        return PrecedenceAssessment(
            precedence_result="superseded_by_amendment",
            basis=(
                f"Văn bản {_doc_label(in_force_doc)} đang có hiệu lực ({in_force_st}) trong khi "
                f"{_doc_label(inactive_doc)} ở trạng thái không còn/chưa có hiệu lực "
                f"({inactive_st}); ưu tiên văn bản {_doc_label(in_force_doc)}."
            ),
            tier_a=tier_a.tier,
            tier_b=tier_b.tier,
            status_a=status_a,
            status_b=status_b,
            preferred_document_id=in_force_doc.document_id,
            as_of_date=as_of_date,
        )
    if a_inactive and b_inactive:
        return PrecedenceAssessment(
            precedence_result="undetermined_requires_review",
            basis=(
                f"Cả hai văn bản đều không ở trạng thái đang có hiệu lực "
                f"({_doc_label(doc_a)}: {status_a}; {_doc_label(doc_b)}: {status_b}) "
                "— cần chuyên viên thẩm định."
            ),
            tier_a=tier_a.tier,
            tier_b=tier_b.tier,
            status_a=status_a,
            status_b=status_b,
            preferred_document_id=None,
            as_of_date=as_of_date,
        )
    if (a_inactive and status_b == AmendmentStatus.UNKNOWN.value) or (
        b_inactive and status_a == AmendmentStatus.UNKNOWN.value
    ):
        return PrecedenceAssessment(
            precedence_result="undetermined_requires_review",
            basis=(
                f"Một văn bản không còn/chưa có hiệu lực ({_doc_label(doc_a)}: {status_a}; "
                f"{_doc_label(doc_b)}: {status_b}) trong khi văn bản còn lại chưa rõ trạng thái "
                "hiệu lực — cần chuyên viên thẩm định."
            ),
            caveats=(UNKNOWN_STATUS_CAVEAT,),
            tier_a=tier_a.tier,
            tier_b=tier_b.tier,
            status_a=status_a,
            status_b=status_b,
            preferred_document_id=None,
            as_of_date=as_of_date,
        )
    return None


def evaluate_precedence(
    doc_a: DocumentAuthorityMeta,
    doc_b: DocumentAuthorityMeta,
    rules: Sequence[AuthorityRule],
    approved_amendments: Sequence[AmendmentBetweenPair] = (),
    *,
    as_of_date: date | None = None,
) -> PrecedenceAssessment:
    """Evaluate deterministic legal precedence between ``doc_a`` and ``doc_b``.

    Follows the 5-step algorithm:
    1. Approved amendment links & in-force vs inactive status checks.
    2. Authority tier resolution via ``legal_authority_rules``.
    3. Cross-rank comparison (smaller ``authority_rank`` = higher legal authority).
    4. Same-rank comparison (same issuing authority + effective date -> *lex posterior*
       with mandatory *lex specialis* caveat; different agencies -> review required).
    5. Missing basis / ambiguous tier -> ``undetermined_requires_review`` (fail-closed).
    """

    status_a = _normalize_status(doc_a.effective_status_at_date)
    status_b = _normalize_status(doc_b.effective_status_at_date)
    tier_a = resolve_authority_tier(doc_a.doc_type, doc_a.issuing_body, rules)
    tier_b = resolve_authority_tier(doc_b.doc_type, doc_b.issuing_body, rules)

    # Step 1: Effectivity & approved amendments
    step1 = _evaluate_amendment_step(
        doc_a, doc_b, tier_a, tier_b, status_a, status_b, approved_amendments, as_of_date
    )
    if step1 is not None:
        return step1

    base_caveats: list[str] = []
    if AmendmentStatus.UNKNOWN.value in (status_a, status_b):
        base_caveats.append(UNKNOWN_STATUS_CAVEAT)

    # Step 2 & 5: Missing or ambiguous authority tier -> fail-closed
    if tier_a.tier is None or tier_b.tier is None:
        reasons: list[str] = []
        if tier_a.tier is None:
            reasons.append(f"{_doc_label(doc_a)}: {tier_a.reason or AMBIGUOUS_ISSUER_REASON}")
        if tier_b.tier is None:
            reasons.append(f"{_doc_label(doc_b)}: {tier_b.reason or AMBIGUOUS_ISSUER_REASON}")
        return PrecedenceAssessment(
            precedence_result="undetermined_requires_review",
            basis=(
                "Chưa đủ căn cứ xác định thứ bậc hiệu lực ("
                + "; ".join(reasons)
                + ") — cần chuyên viên thẩm định."
            ),
            caveats=tuple(base_caveats),
            tier_a=tier_a.tier,
            tier_b=tier_b.tier,
            status_a=status_a,
            status_b=status_b,
            preferred_document_id=None,
            as_of_date=as_of_date,
        )

    resolved_a = tier_a.tier
    resolved_b = tier_b.tier
    tier_summary = (
        f"{_format_tier_summary(_doc_label(doc_a), resolved_a)}; "
        f"{_format_tier_summary(_doc_label(doc_b), resolved_b)}"
    )

    # Step 3: Different authority ranks (lower rank number = higher authority)
    if resolved_a.authority_rank != resolved_b.authority_rank:
        a_higher = resolved_a.authority_rank < resolved_b.authority_rank
        higher_doc = doc_a if a_higher else doc_b
        result_code: PrecedenceResult = "higher_authority_a" if a_higher else "higher_authority_b"
        return PrecedenceAssessment(
            precedence_result=result_code,
            basis=(
                f"Văn bản {_doc_label(higher_doc)} có bậc hiệu lực pháp lý cao hơn "
                f"({tier_summary}). Cần kiểm tra tính hợp hiến, hợp pháp và thẩm quyền "
                "ban hành của văn bản cấp dưới."
            ),
            caveats=tuple(base_caveats),
            tier_a=resolved_a,
            tier_b=resolved_b,
            status_a=status_a,
            status_b=status_b,
            preferred_document_id=higher_doc.document_id,
            as_of_date=as_of_date,
        )

    # Step 4: Same authority rank
    if not same_issuing_authority(doc_a.issuing_body, doc_b.issuing_body):
        issuer_a = doc_a.issuing_body or "chưa rõ"
        issuer_b = doc_b.issuing_body or "chưa rõ"
        return PrecedenceAssessment(
            precedence_result="undetermined_requires_review",
            basis=(
                "Hai văn bản ngang bậc từ hai cơ quan khác nhau — cần chuyên viên/cơ quan có "
                f"thẩm quyền đối chiếu phạm vi quản lý ({tier_summary}; cơ quan: "
                f"{issuer_a} vs {issuer_b})."
            ),
            caveats=tuple(base_caveats),
            tier_a=resolved_a,
            tier_b=resolved_b,
            status_a=status_a,
            status_b=status_b,
            preferred_document_id=None,
            as_of_date=as_of_date,
        )

    date_a, date_a_src = _effective_date_with_source(doc_a)
    date_b, date_b_src = _effective_date_with_source(doc_b)
    if date_a is None or date_b is None:
        return PrecedenceAssessment(
            precedence_result="undetermined_requires_review",
            basis=(
                f"Hai văn bản cùng bậc và cùng cơ quan ban hành ({tier_summary}), nhưng thiếu "
                "ngày hiệu lực/ban hành để áp dụng nguyên tắc văn bản ban hành sau."
            ),
            caveats=tuple(base_caveats),
            tier_a=resolved_a,
            tier_b=resolved_b,
            status_a=status_a,
            status_b=status_b,
            preferred_document_id=None,
            as_of_date=as_of_date,
        )

    if date_a == date_b:
        return PrecedenceAssessment(
            precedence_result="undetermined_requires_review",
            basis=(
                f"Hai văn bản cùng bậc, cùng cơ quan ban hành và cùng mốc thời gian "
                f"{date_a.isoformat()} ({tier_summary}) — không thể tự động phân định văn bản sau."
            ),
            caveats=tuple(base_caveats),
            tier_a=resolved_a,
            tier_b=resolved_b,
            status_a=status_a,
            status_b=status_b,
            preferred_document_id=None,
            as_of_date=as_of_date,
        )

    a_newer = date_a > date_b
    newer_doc = doc_a if a_newer else doc_b
    same_tier_result: PrecedenceResult = (
        "same_tier_newer_a" if a_newer else "same_tier_newer_b"
    )
    caveats = (*base_caveats, LEX_SPECIALIS_CAVEAT)
    return PrecedenceAssessment(
        precedence_result=same_tier_result,
        basis=(
            f"Hai văn bản cùng bậc và cùng cơ quan ban hành ({tier_summary}); theo nguyên tắc "
            f"văn bản ban hành sau (lex posterior), {_doc_label(newer_doc)} có mốc mới hơn "
            f"({_doc_label(doc_a)}: {date_a.isoformat()} [{date_a_src}] vs "
            f"{_doc_label(doc_b)}: {date_b.isoformat()} [{date_b_src}])."
        ),
        caveats=caveats,
        tier_a=resolved_a,
        tier_b=resolved_b,
        status_a=status_a,
        status_b=status_b,
        preferred_document_id=newer_doc.document_id,
        as_of_date=as_of_date,
    )
