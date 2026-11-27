"""Tests for the deterministic legal precedence & effectivity engine (Phase 2, D2)."""

from __future__ import annotations

from datetime import date

import pytest

from app.conflicts.precedence import (
    LEX_SPECIALIS_CAVEAT,
    UNKNOWN_STATUS_CAVEAT,
    AmendmentBetweenPair,
    AuthorityRule,
    DocumentAuthorityMeta,
    evaluate_precedence,
    resolve_authority_tier,
    same_issuing_authority,
)
from app.schemas import AmendmentStatus

# Mirrors the 23 default rows seeded in migration 0018_legal_hierarchy_and_conflict_reviews.sql.
SEEDED_0018_RULES: tuple[AuthorityRule, ...] = (
    AuthorityRule("code_national_assembly", "code", None, 10, "Bộ luật (Quốc hội)", False, 100),
    AuthorityRule("law_national_assembly", "law", None, 10, "Luật (Quốc hội)", False, 100),
    AuthorityRule(
        "resolution_ubtvqh",
        "resolution",
        "(uy ban thuong vu quoc hoi|ubtvqh)",
        20,
        "Nghị quyết (Ủy ban Thường vụ Quốc hội)",
        False,
        10,
    ),
    AuthorityRule(
        "resolution_national_assembly",
        "resolution",
        "(^| )quoc hoi($| )",
        15,
        "Nghị quyết (Quốc hội)",
        False,
        20,
    ),
    AuthorityRule(
        "resolution_government",
        "resolution",
        "(^| )chinh phu($| )",
        30,
        "Nghị quyết (Chính phủ)",
        False,
        30,
    ),
    AuthorityRule(
        "resolution_hdnd_provincial",
        "resolution",
        "(hoi dong nhan dan|hdnd).*(tinh|thanh pho)",
        50,
        "Nghị quyết (HĐND cấp tỉnh)",
        False,
        50,
    ),
    AuthorityRule(
        "resolution_hdnd_local",
        "resolution",
        "(hoi dong nhan dan|hdnd)",
        60,
        "Nghị quyết (HĐND cấp huyện/xã/đơn vị)",
        False,
        60,
    ),
    AuthorityRule(
        "resolution_fallback_ambiguous",
        "resolution",
        None,
        50,
        "Nghị quyết (cần xác định cơ quan ban hành)",
        True,
        900,
    ),
    AuthorityRule(
        "ordinance_ubtvqh",
        "ordinance",
        None,
        20,
        "Pháp lệnh (Ủy ban Thường vụ Quốc hội)",
        False,
        100,
    ),
    AuthorityRule(
        "decision_president",
        "decision",
        "chu tich nuoc",
        25,
        "Quyết định (Chủ tịch nước)",
        False,
        10,
    ),
    AuthorityRule(
        "decision_prime_minister",
        "decision",
        "thu tuong",
        35,
        "Quyết định (Thủ tướng Chính phủ)",
        False,
        20,
    ),
    AuthorityRule(
        "decision_ministry_or_province",
        "decision",
        "(^bo |lien bo |bo truong|co quan ngang bo|"
        "uy ban nhan dan (tinh|thanh pho)|ubnd (tinh|thanh pho)|"
        "hoi dong nhan dan (tinh|thanh pho)|hdnd (tinh|thanh pho))",
        50,
        "Quyết định (Bộ / cơ quan ngang Bộ / UBND cấp tỉnh)",
        False,
        30,
    ),
    AuthorityRule(
        "decision_department_or_local",
        "decision",
        "(giam doc|^so |uy ban nhan dan|ubnd|hoi dong nhan dan|hdnd|"
        "cuc |chi cuc|don vi|vien truong|hieu truong|tong giam doc)",
        60,
        "Quyết định (Cấp Sở / Huyện / Đơn vị nội bộ)",
        False,
        40,
    ),
    AuthorityRule(
        "decision_fallback_ambiguous",
        "decision",
        None,
        50,
        "Quyết định (cần xác định cơ quan ban hành)",
        True,
        900,
    ),
    AuthorityRule("decree_government", "decree", None, 30, "Nghị định (Chính phủ)", False, 100),
    AuthorityRule(
        "joint_circular_ministries",
        "joint_circular",
        None,
        40,
        "Thông tư liên tịch",
        False,
        100,
    ),
    AuthorityRule(
        "circular_ministry",
        "circular",
        None,
        40,
        "Thông tư (Bộ / cơ quan ngang Bộ)",
        False,
        100,
    ),
    AuthorityRule(
        "directive_prime_minister",
        "directive",
        "thu tuong",
        35,
        "Chỉ thị (Thủ tướng Chính phủ)",
        False,
        20,
    ),
    AuthorityRule(
        "directive_ministry_or_province",
        "directive",
        "(^bo |lien bo |bo truong|co quan ngang bo|"
        "uy ban nhan dan (tinh|thanh pho)|ubnd (tinh|thanh pho)|"
        "hoi dong nhan dan (tinh|thanh pho)|hdnd (tinh|thanh pho))",
        50,
        "Chỉ thị (Bộ / cơ quan ngang Bộ / UBND cấp tỉnh)",
        False,
        30,
    ),
    AuthorityRule(
        "directive_department_or_local",
        "directive",
        "(giam doc|^so |uy ban nhan dan|ubnd|hoi dong nhan dan|hdnd|"
        "cuc |chi cuc|don vi|vien truong|hieu truong|tong giam doc)",
        60,
        "Chỉ thị (Cấp Sở / Huyện / Đơn vị nội bộ)",
        False,
        40,
    ),
    AuthorityRule(
        "directive_fallback_ambiguous",
        "directive",
        None,
        50,
        "Chỉ thị (cần xác định cơ quan ban hành)",
        True,
        900,
    ),
    AuthorityRule(
        "consolidated_fallback_ambiguous",
        "consolidated",
        None,
        100,
        "Văn bản hợp nhất (cần đối chiếu văn bản gốc)",
        True,
        900,
    ),
    AuthorityRule(
        "other_fallback_ambiguous",
        "other",
        None,
        500,
        "Văn bản khác (chưa xác định thứ bậc)",
        True,
        900,
    ),
)


def _doc(
    doc_id: str,
    doc_type: str,
    issuing_body: str | None = None,
    *,
    document_number: str | None = None,
    effective_from: date | None = None,
    publication_date: date | None = None,
    status: AmendmentStatus | str = AmendmentStatus.ACTIVE,
) -> DocumentAuthorityMeta:
    return DocumentAuthorityMeta(
        document_id=doc_id,
        doc_type=doc_type,
        issuing_body=issuing_body,
        document_number=document_number,
        effective_from=effective_from,
        publication_date=publication_date,
        effective_status_at_date=status,
    )


def test_scenario_1_law_vs_decree_higher_authority_a() -> None:
    doc_a = _doc("doc-law", "law", "Quốc hội", document_number="45/2019/QH14")
    doc_b = _doc("doc-decree", "decree", "Chính phủ", document_number="145/2020/NĐ-CP")

    result = evaluate_precedence(doc_a, doc_b, SEEDED_0018_RULES)

    assert result.precedence_result == "higher_authority_a"
    assert result.preferred_document_id == "doc-law"
    assert "law_national_assembly" in result.basis
    assert "decree_government" in result.basis
    assert "10" in result.basis and "30" in result.basis
    assert result.caveats == ()


def test_scenario_2_decree_vs_circular_higher_authority_a() -> None:
    doc_a = _doc("doc-decree", "decree", "Chính phủ", document_number="10/2023/NĐ-CP")
    doc_b = _doc("doc-circular", "circular", "Bộ Tài chính", document_number="20/2024/TT-BTC")

    result = evaluate_precedence(doc_a, doc_b, SEEDED_0018_RULES)

    assert result.precedence_result == "higher_authority_a"
    assert result.preferred_document_id == "doc-decree"
    assert result.tier_a is not None and result.tier_a.authority_rank == 30
    assert result.tier_b is not None and result.tier_b.authority_rank == 40


def test_scenario_3_resolution_national_assembly_vs_resolution_government() -> None:
    doc_a = _doc("doc-res-qh", "resolution", "Quốc hội", document_number="100/2023/QH15")
    doc_b = _doc("doc-res-cp", "resolution", "Chính phủ", document_number="88/NQ-CP")

    result = evaluate_precedence(doc_a, doc_b, SEEDED_0018_RULES)

    assert result.precedence_result == "higher_authority_a"
    assert result.preferred_document_id == "doc-res-qh"
    assert result.tier_a is not None and result.tier_a.rule_code == "resolution_national_assembly"
    assert result.tier_b is not None and result.tier_b.rule_code == "resolution_government"


def test_scenario_4_decision_prime_minister_vs_department_director() -> None:
    doc_a = _doc("doc-pm", "decision", "Thủ tướng Chính phủ", document_number="12/2024/QĐ-TTg")
    doc_b = _doc("doc-dir", "decision", "Giám đốc Sở Tài chính", document_number="05/QĐ-STC")

    result = evaluate_precedence(doc_a, doc_b, SEEDED_0018_RULES)

    assert result.precedence_result == "higher_authority_a"
    assert result.preferred_document_id == "doc-pm"
    assert result.tier_a is not None and result.tier_a.rule_code == "decision_prime_minister"
    assert result.tier_b is not None and result.tier_b.rule_code == "decision_department_or_local"


def test_scenario_5_resolution_missing_issuing_body_vs_decree_undetermined() -> None:
    doc_a = _doc("doc-res-no-issuer", "resolution", None, document_number="01/NQ")
    doc_b = _doc("doc-decree", "decree", "Chính phủ", document_number="15/2023/NĐ-CP")

    resolved = resolve_authority_tier("resolution", None, SEEDED_0018_RULES)
    assert resolved.tier is None
    assert resolved.reason == "Loại văn bản cần xác định rõ cơ quan ban hành"

    result = evaluate_precedence(doc_a, doc_b, SEEDED_0018_RULES)

    assert result.precedence_result == "undetermined_requires_review"
    assert result.preferred_document_id is None
    assert result.tier_a is None


def test_scenario_6_same_ministry_circulars_newer_wins_with_lex_specialis_caveat() -> None:
    doc_a = _doc(
        "doc-circ-2025",
        "circular",
        "Bộ Tài chính",
        document_number="02/2025/TT-BTC",
        effective_from=date(2025, 3, 1),
    )
    doc_b = _doc(
        "doc-circ-2022",
        "circular",
        "bo tai chinh",
        document_number="50/2022/TT-BTC",
        effective_from=date(2022, 9, 15),
    )

    result = evaluate_precedence(doc_a, doc_b, SEEDED_0018_RULES)

    assert result.precedence_result == "same_tier_newer_a"
    assert result.preferred_document_id == "doc-circ-2025"
    assert LEX_SPECIALIS_CAVEAT in result.caveats


def test_scenario_7_different_ministries_circulars_undetermined() -> None:
    doc_a = _doc(
        "doc-btc",
        "circular",
        "Bộ Tài chính",
        document_number="10/2024/TT-BTC",
        effective_from=date(2024, 5, 1),
    )
    doc_b = _doc(
        "doc-bct",
        "circular",
        "Bộ Công Thương",
        document_number="12/2023/TT-BCT",
        effective_from=date(2023, 6, 1),
    )

    result = evaluate_precedence(doc_a, doc_b, SEEDED_0018_RULES)

    assert result.precedence_result == "undetermined_requires_review"
    assert result.preferred_document_id is None
    assert "cơ quan khác nhau" in result.basis


def test_scenario_8_approved_amendment_replace_b_to_a_supersedes_regardless_of_date() -> None:
    doc_a = _doc(
        "doc-a",
        "law",
        "Quốc hội",
        effective_from=date(2025, 1, 1),
        status=AmendmentStatus.ACTIVE,
    )
    doc_b = _doc(
        "doc-b",
        "decree",
        "Chính phủ",
        effective_from=date(2020, 1, 1),
        status=AmendmentStatus.ACTIVE,
    )
    amendment = AmendmentBetweenPair(
        source_document_id="doc-b",
        target_document_id="doc-a",
        action="replace",
        amendment_id="amend-1",
        effective_from=date(2024, 7, 1),
    )

    result = evaluate_precedence(
        doc_a,
        doc_b,
        SEEDED_0018_RULES,
        approved_amendments=[amendment],
        as_of_date=date(2025, 6, 1),
    )

    assert result.precedence_result == "superseded_by_amendment"
    assert result.preferred_document_id == "doc-b"
    assert "doc-b" in result.basis
    assert "replace" in result.basis


def test_ubtvqh_resolution_matches_priority_10_before_national_assembly_pattern() -> None:
    doc_a = _doc("doc-ubtvqh", "resolution", "Ủy ban Thường vụ Quốc hội")
    doc_b = _doc("doc-qh", "resolution", "Quốc hội")

    result = evaluate_precedence(doc_a, doc_b, SEEDED_0018_RULES)

    assert result.precedence_result == "higher_authority_b"
    assert result.preferred_document_id == "doc-qh"
    assert result.tier_a is not None and result.tier_a.rule_code == "resolution_ubtvqh"
    assert result.tier_b is not None and result.tier_b.rule_code == "resolution_national_assembly"


def test_prime_minister_vs_minister_decision_ranks_35_vs_50() -> None:
    doc_a = _doc("doc-pm", "decision", "Thủ tướng Chính phủ")
    doc_b = _doc("doc-minister", "decision", "Bộ trưởng Bộ Tài chính")

    result = evaluate_precedence(doc_a, doc_b, SEEDED_0018_RULES)

    assert result.precedence_result == "higher_authority_a"
    assert result.tier_a is not None and result.tier_a.authority_rank == 35
    assert result.tier_b is not None and result.tier_b.authority_rank == 50


def test_unknown_statuses_still_compute_hierarchy_with_explicit_caveat() -> None:
    doc_a = _doc("doc-law", "law", "Quốc hội", status=AmendmentStatus.UNKNOWN)
    doc_b = _doc("doc-decree", "decree", "Chính phủ", status=AmendmentStatus.UNKNOWN)

    result = evaluate_precedence(doc_a, doc_b, SEEDED_0018_RULES)

    assert result.precedence_result == "higher_authority_a"
    assert result.preferred_document_id == "doc-law"
    assert UNKNOWN_STATUS_CAVEAT in result.caveats


def test_one_unknown_and_one_active_without_amendment_runs_hierarchy_with_caveat() -> None:
    doc_a = _doc("doc-decree", "decree", "Chính phủ", status=AmendmentStatus.UNKNOWN)
    doc_b = _doc("doc-law", "law", "Quốc hội", status=AmendmentStatus.ACTIVE)

    result = evaluate_precedence(doc_a, doc_b, SEEDED_0018_RULES)

    assert result.precedence_result == "higher_authority_b"
    assert result.preferred_document_id == "doc-law"
    assert UNKNOWN_STATUS_CAVEAT in result.caveats


@pytest.mark.parametrize(
    ("inactive_status", "in_force_status"),
    [
        (AmendmentStatus.REPEALED, AmendmentStatus.ACTIVE),
        (AmendmentStatus.REPLACED, AmendmentStatus.MODIFIED),
        (AmendmentStatus.SUSPENDED, AmendmentStatus.ACTIVE),
        (AmendmentStatus.NOT_YET_EFFECTIVE, AmendmentStatus.ACTIVE),
    ],
)
def test_inactive_vs_in_force_returns_superseded_by_amendment(
    inactive_status: AmendmentStatus,
    in_force_status: AmendmentStatus,
) -> None:
    doc_a = _doc("doc-a", "law", "Quốc hội", status=inactive_status)
    doc_b = _doc("doc-b", "circular", "Bộ Tài chính", status=in_force_status)

    result = evaluate_precedence(doc_a, doc_b, SEEDED_0018_RULES)

    assert result.precedence_result == "superseded_by_amendment"
    assert result.preferred_document_id == "doc-b"
    assert "doc-b" in result.basis


def test_both_inactive_or_inactive_with_unknown_returns_undetermined_requires_review() -> None:
    both_repealed = evaluate_precedence(
        _doc("doc-a", "law", "Quốc hội", status=AmendmentStatus.REPEALED),
        _doc("doc-b", "decree", "Chính phủ", status=AmendmentStatus.SUSPENDED),
        SEEDED_0018_RULES,
    )
    assert both_repealed.precedence_result == "undetermined_requires_review"
    assert both_repealed.preferred_document_id is None

    inactive_and_unknown = evaluate_precedence(
        _doc("doc-a", "law", "Quốc hội", status=AmendmentStatus.REPEALED),
        _doc("doc-b", "decree", "Chính phủ", status=AmendmentStatus.UNKNOWN),
        SEEDED_0018_RULES,
    )
    assert inactive_and_unknown.precedence_result == "undetermined_requires_review"
    assert inactive_and_unknown.preferred_document_id is None
    assert UNKNOWN_STATUS_CAVEAT in inactive_and_unknown.caveats


def test_same_tier_same_issuer_same_date_tie_requires_review() -> None:
    doc_a = _doc(
        "doc-a",
        "circular",
        "Bộ Tài chính",
        effective_from=date(2024, 1, 1),
    )
    doc_b = _doc(
        "doc-b",
        "circular",
        "Bộ Tài chính",
        effective_from=date(2024, 1, 1),
    )

    result = evaluate_precedence(doc_a, doc_b, SEEDED_0018_RULES)

    assert result.precedence_result == "undetermined_requires_review"
    assert result.preferred_document_id is None


def test_same_tier_same_issuer_publication_date_fallback_and_newer_b() -> None:
    doc_a = _doc(
        "doc-a",
        "circular",
        "Bộ Tài chính",
        publication_date=date(2021, 5, 1),
    )
    doc_b = _doc(
        "doc-b",
        "circular",
        "Bộ trưởng Bộ Tài chính",
        publication_date=date(2023, 8, 1),
    )

    result = evaluate_precedence(doc_a, doc_b, SEEDED_0018_RULES)

    assert result.precedence_result == "same_tier_newer_b"
    assert result.preferred_document_id == "doc-b"
    assert LEX_SPECIALIS_CAVEAT in result.caveats


def test_future_or_unapproved_amendments_are_ignored_at_as_of_date() -> None:
    doc_a = _doc("doc-a", "law", "Quốc hội", status=AmendmentStatus.ACTIVE)
    doc_b = _doc("doc-b", "decree", "Chính phủ", status=AmendmentStatus.ACTIVE)
    future_amendment = AmendmentBetweenPair(
        source_document_id="doc-b",
        target_document_id="doc-a",
        action="replace",
        effective_from=date(2026, 1, 1),
        approved=True,
    )
    unapproved_amendment = AmendmentBetweenPair(
        source_document_id="doc-b",
        target_document_id="doc-a",
        action="repeal",
        effective_from=date(2023, 1, 1),
        approved=False,
    )

    result = evaluate_precedence(
        doc_a,
        doc_b,
        SEEDED_0018_RULES,
        approved_amendments=[future_amendment, unapproved_amendment],
        as_of_date=date(2025, 1, 1),
    )

    assert result.precedence_result == "higher_authority_a"


def test_same_issuing_authority_normalization_and_distinct_agencies() -> None:
    assert same_issuing_authority("Bộ Tài chính", "  bo   tai chinh. ")
    assert same_issuing_authority("UBND Thành phố Hà Nội", "Ủy ban nhân dân TP. Hà Nội")
    assert same_issuing_authority("Bộ trưởng Bộ Tài chính", "Bộ Tài chính")

    assert not same_issuing_authority("Bộ Tài chính", "Bộ Công Thương")
    assert not same_issuing_authority("UBND Thành phố Hà Nội", "UBND Thành phố Hồ Chí Minh")
    assert not same_issuing_authority(None, "Bộ Tài chính")
    assert not same_issuing_authority("", "   ")


def test_to_basis_json_serializes_structured_audit_metadata() -> None:
    doc_a = _doc("doc-a", "law", "Quốc hội", status=AmendmentStatus.UNKNOWN)
    doc_b = _doc("doc-b", "decree", "Chính phủ", status=AmendmentStatus.UNKNOWN)

    result = evaluate_precedence(
        doc_a,
        doc_b,
        SEEDED_0018_RULES,
        as_of_date=date(2025, 11, 1),
    )
    payload = result.to_basis_json()

    assert payload["precedence_result"] == "higher_authority_a"
    assert payload["preferred_document_id"] == "doc-a"
    assert payload["as_of_date"] == "2025-11-01"
    assert payload["tier_a"]["rule_code"] == "law_national_assembly"
    assert payload["tier_b"]["rule_code"] == "decree_government"
    assert UNKNOWN_STATUS_CAVEAT in payload["caveats"]
    assert "cần chuyên viên thẩm định" in payload["reference_notice"]


def test_inactive_rules_are_ignored_and_unknown_doc_type_is_undetermined() -> None:
    inactive_rule = AuthorityRule(
        "other_override_inactive",
        "other",
        None,
        10,
        "Inactive",
        is_ambiguous_without_issuer=False,
        match_priority=1,
        is_active=False,
    )
    rules = (*SEEDED_0018_RULES, inactive_rule)

    res_other = resolve_authority_tier("other", "Cơ quan X", rules)
    assert res_other.tier is None

    res_unknown_type = resolve_authority_tier("custom_unknown_type", "Quốc hội", rules)
    assert res_unknown_type.tier is None

    assessment = evaluate_precedence(
        _doc("doc-other", "other", "Cơ quan X"),
        _doc("doc-decree", "decree", "Chính phủ"),
        rules,
    )
    assert assessment.precedence_result == "undetermined_requires_review"
    assert assessment.preferred_document_id is None


def test_ubnd_tp_abbreviation_resolves_provincial_decision_tier_50() -> None:
    doc_a = _doc("doc-hanoi", "decision", "UBND TP. Hà Nội", effective_from=date(2024, 6, 1))
    doc_b = _doc(
        "doc-hanoi-2",
        "decision",
        "Ủy ban nhân dân Thành phố Hà Nội",
        effective_from=date(2023, 1, 1),
    )

    result = evaluate_precedence(doc_a, doc_b, SEEDED_0018_RULES)

    assert result.tier_a is not None
    assert result.tier_a.rule_code == "decision_ministry_or_province"
    assert result.tier_a.authority_rank == 50
    assert result.precedence_result == "same_tier_newer_a"
    assert LEX_SPECIALIS_CAVEAT in result.caveats


@pytest.mark.parametrize(
    "amending_status",
    [
        AmendmentStatus.REPEALED,
        AmendmentStatus.REPLACED,
        AmendmentStatus.SUSPENDED,
        AmendmentStatus.NOT_YET_EFFECTIVE,
    ],
)
def test_unidirectional_amendment_fails_closed_when_amending_doc_is_inactive(
    amending_status: AmendmentStatus,
) -> None:
    doc_a = _doc("doc-a", "law", "Quốc hội", status=AmendmentStatus.ACTIVE)
    doc_b = _doc("doc-b", "decree", "Chính phủ", status=amending_status)
    amendment = AmendmentBetweenPair(
        source_document_id="doc-b",
        target_document_id="doc-a",
        action="replace",
        effective_from=None,
    )

    result = evaluate_precedence(
        doc_a,
        doc_b,
        SEEDED_0018_RULES,
        approved_amendments=[amendment],
    )

    assert result.precedence_result == "undetermined_requires_review"
    assert result.preferred_document_id is None
    assert "doc-b" in result.basis
    assert amending_status.value in result.basis


def test_inactive_amending_doc_with_unknown_target_preserves_unknown_caveat() -> None:
    doc_a = _doc("doc-a", "decree", "Chính phủ", status=AmendmentStatus.NOT_YET_EFFECTIVE)
    doc_b = _doc("doc-b", "circular", "Bộ Tài chính", status=AmendmentStatus.UNKNOWN)
    amendment = AmendmentBetweenPair(
        source_document_id="doc-a",
        target_document_id="doc-b",
        action="modify",
        effective_from=None,
    )

    result = evaluate_precedence(
        doc_a,
        doc_b,
        SEEDED_0018_RULES,
        approved_amendments=[amendment],
    )

    assert result.precedence_result == "undetermined_requires_review"
    assert result.preferred_document_id is None
    assert UNKNOWN_STATUS_CAVEAT in result.caveats


def test_bidirectional_approved_amendments_require_review() -> None:
    doc_a = _doc("doc-a", "decree", "Chính phủ", status=AmendmentStatus.ACTIVE)
    doc_b = _doc("doc-b", "decree", "Chính phủ", status=AmendmentStatus.ACTIVE)
    amend_ab = AmendmentBetweenPair(
        source_document_id="doc-a",
        target_document_id="doc-b",
        action="modify",
        effective_from=date(2024, 1, 1),
    )
    amend_ba = AmendmentBetweenPair(
        source_document_id="doc-b",
        target_document_id="doc-a",
        action="replace",
        effective_from=date(2024, 6, 1),
    )

    result = evaluate_precedence(
        doc_a,
        doc_b,
        SEEDED_0018_RULES,
        approved_amendments=[amend_ab, amend_ba],
        as_of_date=date(2025, 1, 1),
    )

    assert result.precedence_result == "undetermined_requires_review"
    assert result.preferred_document_id is None


def test_custom_rules_with_vietnamese_abbreviations_match_issuing_body() -> None:
    custom_rules = (
        AuthorityRule(
            "custom_ubnd_hn",
            "decision",
            r"ubnd.*ha noi",
            50,
            "Quyết định UBND Hà Nội",
            False,
            5,
        ),
        AuthorityRule(
            "custom_hdnd_tinh",
            "resolution",
            r"hdnd.*tinh",
            50,
            "Nghị quyết HĐND tỉnh",
            False,
            5,
        ),
        AuthorityRule(
            "custom_bo_truong_yte",
            "circular",
            r"bo truong.*y te",
            45,
            "Thông tư Bộ trưởng Bộ Y tế",
            False,
            5,
        ),
    )
    assert (
        resolve_authority_tier("decision", "UBND TP. Hà Nội", custom_rules).rule_code
        == "custom_ubnd_hn"
    )
    assert (
        resolve_authority_tier("resolution", "HĐND tỉnh Nghệ An", custom_rules).rule_code
        == "custom_hdnd_tinh"
    )
    assert (
        resolve_authority_tier("circular", "Bộ trưởng Bộ Y tế", custom_rules).rule_code
        == "custom_bo_truong_yte"
    )
