"""Legal conflict detection and deterministic precedence evaluation (Phase 2)."""

from .precedence import (
    AMENDMENT_PRECEDENCE_ACTIONS,
    IN_FORCE_STATUSES,
    INACTIVE_STATUSES,
    LEX_SPECIALIS_CAVEAT,
    REFERENCE_NOTICE,
    UNKNOWN_STATUS_CAVEAT,
    AmendmentBetweenPair,
    AuthorityRule,
    DocumentAuthorityMeta,
    PrecedenceAssessment,
    PrecedenceResult,
    ResolvedAuthorityTier,
    evaluate_precedence,
    normalize_issuing_authority,
    resolve_authority_tier,
    same_issuing_authority,
)

__all__ = [
    "AMENDMENT_PRECEDENCE_ACTIONS",
    "AmendmentBetweenPair",
    "AuthorityRule",
    "DocumentAuthorityMeta",
    "INACTIVE_STATUSES",
    "IN_FORCE_STATUSES",
    "LEX_SPECIALIS_CAVEAT",
    "PrecedenceAssessment",
    "PrecedenceResult",
    "REFERENCE_NOTICE",
    "ResolvedAuthorityTier",
    "UNKNOWN_STATUS_CAVEAT",
    "evaluate_precedence",
    "normalize_issuing_authority",
    "resolve_authority_tier",
    "same_issuing_authority",
]
