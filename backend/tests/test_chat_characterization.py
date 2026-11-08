"""SR-0: characterization (golden) tests for the existing chat behaviour.

These tests pin the observable behaviour of the fixed pipeline **before** the
Search v1 refactor.  They use the deterministic in-memory search double so the
assertions do not depend on PostgreSQL state.  Any change to evidence order,
claim count, suggestion count or SSE event names must be explicit in the ADR
and update this file.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

import pytest

from app.evidence.mapper import to_evidence_ref
from app.main import _build_turn_events
from app.schemas import (
    AmendmentStatus,
    AnalyzeRequest,
    Scope,
    ScopeMode,
)
from app.storage.authorized_search import (
    AuthorizedNode,
    InMemoryAuthorizedNodeSearch,
)
from app.workflow.fixed_pipeline import FixedPipeline, PipelineDependencies

PRINCIPAL = UUID("00000000-0000-0000-0000-000000000001")
CATEGORY = UUID("00000000-0000-0000-0000-0000000000aa")
AS_OF = date(2026, 10, 31)


def _node(index: int) -> AuthorizedNode:
    return AuthorizedNode(
        evidence_id=f"ev_{index:032d}",
        document_id=UUID(int=index),
        document_version_id=UUID(int=index + 1000),
        node_id=UUID(int=index),
        document_number=f"100/2026/ND-CP-{index}",
        title="Nghị định hư cấu về chế độ báo cáo",
        label=f"Điều {index}",
        quote_exact=f"Điều {index}. Cơ quan định kỳ báo cáo tình hình thực hiện.",
        page=index,
        source_hash="a" * 64,
        as_of_date=AS_OF,
        amendment_state=AmendmentStatus.ACTIVE,
        category_ids=(CATEGORY,),
    )


def _search() -> InMemoryAuthorizedNodeSearch:
    nodes = [_node(index) for index in range(1, 16)]
    return InMemoryAuthorizedNodeSearch(nodes, {PRINCIPAL: {CATEGORY}})


def _request(question: str = "báo cáo định kỳ") -> AnalyzeRequest:
    return AnalyzeRequest(
        question=question,
        scope=Scope(scope_mode=ScopeMode.ALL_AUTHORIZED, as_of_date=AS_OF),
        facts=[],
    )


async def _run(question: str = "báo cáo định kỳ"):
    pipeline = FixedPipeline(
        dependencies=PipelineDependencies(
            search_authorized_nodes=_search().search, select_evidence=None
        ),
        operating_mode="LOCAL",
    )
    return await pipeline.execute(_request(question), principal_id=PRINCIPAL)


@pytest.mark.asyncio
async def test_chat_returns_twelve_evidence_items_in_stable_order() -> None:
    result = await _run()

    assert len(result.evidence) == 12
    expected_ids = sorted(f"ev_{index:032d}" for index in range(1, 16))[:12]
    assert [item.evidence_id for item in result.evidence] == expected_ids
    assert result.evidence[0].quote_exact.startswith("Điều 1.")
    assert all("định kỳ báo cáo" in item.quote_exact for item in result.evidence)


@pytest.mark.asyncio
async def test_chat_claims_suggestions_and_status_are_golden() -> None:
    result = await _run()

    assert len(result.claims) == 8
    assert [claim.text for claim in result.claims] == [
        item.quote_exact for item in result.evidence[:8]
    ]
    assert all(claim.status == "supported" for claim in result.claims)
    assert len(result.suggestions) == 3
    assert result.status.value == "evidence_found"
    assert result.answer_generated is False
    assert result.explanation_unavailable is True
    assert result.ai_selection_applied is False
    assert result.coverage_checks.source_verified.value == "passed"
    assert result.coverage_checks.effective_checked.value == "passed"
    assert len(result.evidence_groups) == len(result.evidence)


@pytest.mark.asyncio
async def test_chat_sse_event_sequence_is_golden() -> None:
    result = await _run()
    events = _build_turn_events(result)

    assert [event.event for event in events] == [
        "retrieval_started",
        "evidence_verified",
        "evidence_complete",
        "analysis_ready",
        "explanation_unavailable",
        "answer_complete",
    ]
    assert [event.data["event_sequence"] for event in events] == [1, 2, 3, 4, 5, 6]
    assert events[1].data["evidence"][0]["evidence_id"] == result.evidence[0].evidence_id
    assert events[3].data["answer_generated"] is False


@pytest.mark.asyncio
async def test_empty_chat_result_is_insufficient_and_has_no_claims() -> None:
    pipeline = FixedPipeline(
        dependencies=PipelineDependencies(
            search_authorized_nodes=InMemoryAuthorizedNodeSearch([], {}).search,
            select_evidence=None,
        ),
        operating_mode="LOCAL",
    )
    result = await pipeline.execute(_request(), principal_id=PRINCIPAL)

    assert result.evidence == []
    assert result.claims == []
    assert result.status.value == "insufficient"
    assert result.explanation_unavailable is True


def test_conversion_of_node_to_evidence_ref_is_stable() -> None:
    node = _node(1)
    ref = to_evidence_ref(node)
    assert ref.evidence_id == node.evidence_id
    assert ref.quote_exact == node.quote_exact
    assert ref.viewer_url.endswith(
        f"/api/v1/citations/{node.evidence_id}/pdf?as_of_date=2026-10-31"
    )
