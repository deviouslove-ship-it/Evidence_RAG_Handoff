from datetime import date
from uuid import UUID, uuid4

from app.schemas import (
    AmendmentStatus,
    AnalyzeRequest,
    CoverageState,
    EvidenceRef,
    Scope,
    ScopeMode,
)
from app.storage.authorized_search import AuthorizedNode, InMemoryAuthorizedNodeSearch
from app.workflow.fixed_pipeline import FixedPipeline, PipelineDependencies


async def test_authorized_evidence_produces_a_valid_conservative_response() -> None:
    principal, category = uuid4(), uuid4()
    node = AuthorizedNode(
        evidence_id="fixture_evidence",
        document_id=uuid4(),
        document_version_id=uuid4(),
        node_id=uuid4(),
        document_number=None,
        title="Fixture kỹ thuật, không phải văn bản nghiệp vụ",
        label="Đoạn thử nghiệm",
        quote_exact="Nội dung dùng để kiểm thử hợp đồng.",
        page=1,
        source_hash="a" * 64,
        as_of_date=date(2026, 10, 22),
        amendment_state=AmendmentStatus.UNKNOWN,
        category_ids=(category,),
    )
    search = InMemoryAuthorizedNodeSearch([node], {principal: {category}})
    pipeline = FixedPipeline(PipelineDependencies(search.search))
    response = await pipeline.execute(
        AnalyzeRequest(
            question="kiểm thử",
            scope=Scope(scope_mode=ScopeMode.ALL_AUTHORIZED, as_of_date=date(2026, 10, 22)),
        ),
        principal_id=principal,
    )
    assert [item.quote_exact for item in response.evidence] == [node.quote_exact]
    assert response.coverage_checks.effective_checked == CoverageState.UNKNOWN
    assert response.coverage_checks.claim_supported == CoverageState.UNKNOWN
    assert response.answer_generated is False
    assert response.explanation_unavailable is True


def _reference_evidence(
    label: str, version_id: UUID, *, document_number: str = "Nghị định 12/2024/NĐ-CP"
) -> EvidenceRef:
    node_id = uuid4()
    return EvidenceRef(
        evidence_id=f"ev_{node_id.hex}",
        document_id=uuid4(),
        document_version_id=version_id,
        node_id=node_id,
        document_number=document_number,
        title="Văn bản thử nghiệm",
        label=label,
        quote_exact=f"Nội dung thử nghiệm của {label}.",
        page=1,
        source_hash="b" * 64,
        as_of_date=date(2026, 10, 22),
        amendment_state=AmendmentStatus.UNKNOWN,
        viewer_url=f"/api/v1/citations/ev_{node_id.hex}/pdf",
    )


async def test_exact_reference_ranks_before_neighboring_article() -> None:
    version_id = uuid4()
    neighboring = _reference_evidence("Điều 50", version_id)
    exact = _reference_evidence("Điều 5", version_id)

    async def candidates(**_kwargs):
        return [neighboring, exact]

    response = await FixedPipeline(PipelineDependencies(candidates)).execute(
        AnalyzeRequest(
            question="Điều 5 Nghị định 12/2024/NĐ-CP quy định gì?",
            scope=Scope(scope_mode=ScopeMode.ALL_AUTHORIZED, as_of_date=date(2026, 10, 22)),
        ),
        principal_id=uuid4(),
    )
    assert [item.evidence_id for item in response.evidence] == [
        exact.evidence_id,
        neighboring.evidence_id,
    ]
    assert response.claims[0].evidence_ids == [exact.evidence_id]


def test_groups_do_not_mix_document_versions() -> None:
    older = _reference_evidence("Điều 5", uuid4())
    newer = _reference_evidence("Điều 5", uuid4())
    groups = FixedPipeline._group_evidence([older, newer])
    assert len(groups) == 2
    assert {tuple(group.evidence_ids) for group in groups} == {
        (older.evidence_id,),
        (newer.evidence_id,),
    }


def test_ambiguous_reference_keeps_authorized_candidate_order() -> None:
    version_id = uuid4()
    first = _reference_evidence("Điều 50", version_id)
    second = _reference_evidence("Điều 5", version_id)
    assert FixedPipeline._rank_evidence([first, second], "Đối chiếu Điều 5 và Điều 50") == [
        first,
        second,
    ]


def test_real_document_number_prefers_matching_article_over_other_document() -> None:
    other = _reference_evidence("Điều 3. Phạm vi", uuid4(), document_number="350/2026/NĐ-CP")
    expected = _reference_evidence("Điều 3. Phạm vi", uuid4(), document_number="381/2026/NĐ-CP")
    assert FixedPipeline._rank_evidence(
        [other, expected], "Điều 3 Nghị định 381/2026/NĐ-CP"
    )[0] == expected


def test_article_heading_with_period_beats_numbered_neighbor() -> None:
    neighbor = _reference_evidence("Điều 30. Nội dung", uuid4(), document_number="381/2026/NĐ-CP")
    exact = _reference_evidence("Điều 3. Nội dung", uuid4(), document_number="381/2026/NĐ-CP")
    assert FixedPipeline._rank_evidence(
        [neighbor, exact], "Điều 3 Nghị định 381/2026/NĐ-CP"
    )[0] == exact
