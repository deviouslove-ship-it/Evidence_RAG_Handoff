from datetime import date
from uuid import uuid4

import pytest

from app.evidence.validators import validate_claim
from app.memory.service import (
    EphemeralMemoryService,
    MemoryCapacityError,
    MemoryContext,
    StoredEvent,
)
from app.model_registry.adapters import AdapterBudget
from app.schemas import (
    AmendmentStatus,
    AnalyzeRequest,
    EvidenceRef,
    Fact,
    FactStatus,
    ResultStatus,
    Scope,
    ScopeMode,
    TurnRequest,
)
from app.vietnamese_nlp.legal_citation_parser import parse_legal_references
from app.workflow.fixed_pipeline import FixedPipeline, PipelineDependencies


def _scope() -> Scope:
    return Scope(scope_mode=ScopeMode.ALL_AUTHORIZED, as_of_date=date(2026, 10, 22))


def _turn_request(question: str, *, facts: list[Fact] | None = None) -> TurnRequest:
    return TurnRequest(question=question, scope=_scope(), facts=facts or [])


def test_memory_context_keeps_facts_and_bounds_replay_state() -> None:
    service = EphemeralMemoryService()
    session = service.create_session("user-1", scope=_scope())

    for index in range(service._MAX_SESSION_TURNS + 5):
        turn, created = service.create_turn(
            session.id,
            "user-1",
            idempotency_key=f"key-{index}",
            request=_turn_request(
                f"question-{index}",
                facts=[Fact(key=f"fact-{index}", value=f"value-{index}")],
            ),
            query_id=f"query-{index}",
            run_id=f"run-{index}",
        )
        assert created
        service.finish_turn(
            session.id,
            "user-1",
            turn.turn_id,
            [
                StoredEvent(event="event", data={"index": index})
                for _ in range(service._MAX_TURN_EVENTS + 5)
            ],
        )

    context = service.get_context(session.id, "user-1")
    assert len(session.turns) <= service._MAX_SESSION_TURNS
    assert len(session.idempotency) <= service._MAX_IDEMPOTENCY_KEYS
    assert len(session.events) <= service._MAX_SESSION_EVENTS
    assert all(len(turn.events) <= service._MAX_TURN_EVENTS for turn in session.turns.values())
    assert len(context.facts) <= service._MAX_SESSION_FACTS
    assert context.facts[-1].key == f"fact-{service._MAX_SESSION_TURNS + 4}"


def test_delete_principal_removes_all_sessions_and_replay_state() -> None:
    service = EphemeralMemoryService()
    first = service.create_session("user-1")
    second = service.create_session("user-1")
    service.create_session("user-2")

    assert service.delete_principal("user-1") == 2
    with pytest.raises(KeyError, match="SESSION_EXPIRED"):
        service.get_session(first.id, "user-1")
    with pytest.raises(KeyError, match="SESSION_EXPIRED"):
        service.get_session(second.id, "user-1")
    assert len(service._sessions) == 1


def test_running_turn_capacity_rolls_back_the_rejected_turn() -> None:
    service = EphemeralMemoryService()
    service._MAX_SESSION_TURNS = 1
    session = service.create_session("user-1")
    service.create_turn(
        session.id,
        "user-1",
        idempotency_key="first",
        request=_turn_request("first"),
        query_id="query-1",
        run_id="run-1",
    )

    with pytest.raises(MemoryCapacityError, match="TURN_CAPACITY_EXCEEDED"):
        service.create_turn(
            session.id,
            "user-1",
            idempotency_key="second",
            request=_turn_request("second"),
            query_id="query-2",
            run_id="run-2",
        )

    assert len(session.turns) == 1
    assert len(session.idempotency) == 1


def test_turn_context_snapshots_facts_before_a_later_turn_changes_them() -> None:
    service = EphemeralMemoryService()
    session = service.create_session("user-1")
    first, _ = service.create_turn(
        session.id,
        "user-1",
        idempotency_key="first",
        request=_turn_request("first", facts=[Fact(key="role", value="first")]),
        query_id="query-1",
        run_id="run-1",
    )
    service.append_turn_message(session.id, "user-1", first.turn_id, "first")
    second, _ = service.create_turn(
        session.id,
        "user-1",
        idempotency_key="second",
        request=_turn_request("second", facts=[Fact(key="role", value="second")]),
        query_id="query-2",
        run_id="run-2",
    )

    first_context = service.get_turn_context(session.id, "user-1", first.turn_id)
    second_context = service.get_turn_context(session.id, "user-1", second.turn_id)

    assert [(fact.key, fact.value) for fact in first_context.facts] == [("role", "first")]
    assert [(fact.key, fact.value) for fact in second_context.facts] == [("role", "second")]
    assert [message.content for message in second_context.messages] == ["first"]


def test_query_context_alias_returns_current_bounded_context() -> None:
    service = EphemeralMemoryService()
    session = service.create_session("user-1")
    assert service.query_context(session.id, "user-1").facts == ()


def test_follow_up_uses_only_unambiguous_confirmed_memory_facts() -> None:
    request = AnalyzeRequest(question="Còn thủ tục thì sao?", scope=_scope())
    context = MemoryContext(
        messages=(),
        facts=(
            Fact(
                key="document_number",
                value="12/2024/NĐ-CP",
                status=FactStatus.USER_CONFIRMED,
            ),
            Fact(
                key="role",
                value="nội dung suy đoán",
                status=FactStatus.INFERRED_UNCERTAIN,
            ),
        ),
        facts_revision="factrev_previous",
        memory_revision="memoryrev_previous",
    )

    merged = FixedPipeline._request_with_memory_context(request, context)
    assert [fact.key for fact in merged.facts] == ["document_number"]
    assert merged.facts[0].value == "12/2024/NĐ-CP"

    direct_request = AnalyzeRequest(question="Thủ tục hành chính?", scope=_scope())
    assert FixedPipeline._request_with_memory_context(direct_request, context).facts == []

    ambiguous = MemoryContext(
        messages=(),
        facts=(
            Fact(
                key="document_number",
                value="12/2024/NĐ-CP",
                status=FactStatus.USER_CONFIRMED,
            ),
            Fact(
                key="document_number",
                value="13/2024/NĐ-CP",
                status=FactStatus.USER_CONFIRMED,
            ),
        ),
        facts_revision=context.facts_revision,
        memory_revision=context.memory_revision,
    )
    assert FixedPipeline._request_with_memory_context(request, ambiguous).facts == []


@pytest.mark.asyncio
async def test_pipeline_uses_memory_facts_revision_for_follow_up_run() -> None:
    evidence = _evidence("Điều 5")

    async def candidates(**_kwargs):
        return [evidence]

    context = MemoryContext(
        messages=(),
        facts=(
            Fact(
                key="document_number",
                value="12/2024/NĐ-CP",
                status=FactStatus.USER_CONFIRMED,
            ),
        ),
        facts_revision="factrev_previous",
        memory_revision="memoryrev_previous",
    )
    response = await FixedPipeline(PipelineDependencies(candidates)).execute(
        AnalyzeRequest(question="Còn điều này thì sao?", scope=_scope()),
        principal_id=uuid4(),
        memory_context=context,
    )

    assert response.facts_revision == "factrev_previous"


def test_claim_cannot_add_or_remove_polarity() -> None:
    added_negation = validate_claim(
        "Hồ sơ không được nộp trực tuyến.",
        ["e"],
        {"e": "Hồ sơ được nộp trực tuyến."},
    )
    removed_negation = validate_claim(
        "Hồ sơ được nộp trực tuyến.",
        ["e"],
        {"e": "Hồ sơ không được nộp trực tuyến."},
    )

    assert added_negation.status == "conditional"
    assert "polarity_mismatch" in added_negation.reasons
    assert removed_negation.status == "conditional"
    assert "polarity_mismatch" in removed_negation.reasons


def test_claim_cannot_add_or_remove_general_negation() -> None:
    result = validate_claim(
        "Hồ sơ không chứa bản sao.",
        ["e"],
        {"e": "Hồ sơ chứa bản sao."},
    )
    assert result.status == "conditional"
    assert "polarity_mismatch" in result.reasons


def test_parser_accepts_document_number_with_so() -> None:
    parsed = parse_legal_references("Theo Điều 5 Nghị định số 12/2024/NĐ-CP")
    assert parsed.document_numbers == ("Nghị định số 12/2024/NĐ-CP",)


def test_query_merge_bounds_facts_and_ignores_uncertain_values() -> None:
    request = AnalyzeRequest(
        question="tìm quy định",
        scope=_scope(),
        facts=[
            Fact(
                key="inferred",
                value="inferred-" + "x" * 1900,
                status=FactStatus.INFERRED_UNCERTAIN,
            ),
            Fact(key="confirmed", value="công chức"),
        ],
    )

    merged = FixedPipeline._merge_question_with_facts(request)
    assert "inferred-" not in merged
    assert len(merged) <= FixedPipeline._MAX_EFFECTIVE_QUERY_LENGTH


def test_unconfirmed_session_facts_cannot_redirect_retrieval() -> None:
    request = AnalyzeRequest(question="Còn điều kiện áp dụng?", scope=_scope(), facts=[
        Fact(key="Số hiệu văn bản", value="999/2026/NĐ-CP"),
        Fact(key="Đối tượng", value="công chức", status=FactStatus.USER_CONFIRMED),
    ])
    merged = FixedPipeline._merge_question_with_facts(request)
    assert "999/2026/NĐ-CP" not in merged
    assert "công chức" in merged


def _evidence(
    label: str,
    *,
    document_number: str = "Nghị định 12/2024/NĐ-CP",
    amendment_state: AmendmentStatus = AmendmentStatus.ACTIVE,
    quote: str | None = None,
) -> EvidenceRef:
    node_id = uuid4()
    return EvidenceRef(
        evidence_id=f"e_{node_id.hex}",
        document_id=uuid4(),
        document_version_id=uuid4(),
        node_id=node_id,
        document_number=document_number,
        title="Văn bản thử nghiệm",
        label=label,
        quote_exact=quote if quote is not None else f"Nội dung {label}.",
        page=1,
        source_hash="a" * 64,
        as_of_date=date(2026, 10, 22),
        amendment_state=amendment_state,
        viewer_url=f"/citation/{node_id}",
    )


@pytest.mark.asyncio
async def test_exact_reference_without_matching_node_abstains() -> None:
    wrong = _evidence("Điều 6")

    async def candidates(**_kwargs):
        return [wrong]

    response = await FixedPipeline(PipelineDependencies(candidates)).execute(
        AnalyzeRequest(question="Điều 5 Nghị định 12/2024/NĐ-CP", scope=_scope()),
        principal_id=uuid4(),
    )

    assert response.status == ResultStatus.INSUFFICIENT
    assert response.claims == []


@pytest.mark.asyncio
async def test_repealed_evidence_cannot_be_claimed() -> None:
    repealed = _evidence("Điều 5", amendment_state=AmendmentStatus.REPEALED)

    async def candidates(**_kwargs):
        return [repealed]

    response = await FixedPipeline(PipelineDependencies(candidates)).execute(
        AnalyzeRequest(question="quy định", scope=_scope()),
        principal_id=uuid4(),
    )

    assert response.status == ResultStatus.INSUFFICIENT
    assert response.claims == []


@pytest.mark.asyncio
async def test_empty_quote_does_not_produce_evidence_found() -> None:
    empty = _evidence("Đoạn trống", quote="")

    async def candidates(**_kwargs):
        return [empty]

    response = await FixedPipeline(PipelineDependencies(candidates)).execute(
        AnalyzeRequest(question="quy định", scope=_scope()),
        principal_id=uuid4(),
    )

    assert response.status == ResultStatus.INSUFFICIENT


def test_suggestions_are_never_marked_supported_without_validation() -> None:
    suggestions = FixedPipeline._build_suggestions([_evidence("Điều 1"), _evidence("Điều 2")])
    assert suggestions
    assert all(item.status == "needs_review" for item in suggestions)


def test_adapter_budget_has_a_hard_cap() -> None:
    with pytest.raises(ValueError, match="at most 10"):
        AdapterBudget(limit=11)


def test_pipeline_budget_has_a_hard_cap() -> None:
    async def candidates(**_kwargs):
        return []

    with pytest.raises(ValueError, match="at most 10"):
        FixedPipeline(PipelineDependencies(candidates), llm_attempt_budget=11)

