import asyncio
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request

from app.api.v1.execution import QueryExecution
from app.main import _session_query, _validate_replay_evidence, create_app
from app.memory.service import EphemeralMemoryService, MemoryCapacityError, StoredEvent
from app.schemas import EvidenceRef, Fact, Scope, TurnRequest


def _request() -> Request:
    async def receive() -> dict[str, str]:
        await asyncio.Event().wait()
        return {"type": "http.disconnect"}

    return Request({"type": "http", "method": "POST", "path": "/"}, receive)


async def test_completed_query_does_not_hang_waiting_for_disconnect() -> None:
    execution = QueryExecution()

    async def operation() -> str:
        return "done"

    assert await asyncio.wait_for(
        execution.run(_request(), operation, principal_id="one", timeout=1), timeout=2
    ) == "done"
    assert not execution._active


async def test_query_timeout_cancels_work_and_frees_slot() -> None:
    execution = QueryExecution()
    stopped = asyncio.Event()

    async def operation() -> None:
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    with pytest.raises(HTTPException) as raised:
        await execution.run(_request(), operation, principal_id="one", timeout=0.02)
    assert raised.value.detail == "QUERY_TIMEOUT"
    assert stopped.is_set()
    assert not execution._active
    assert execution._slots._value == 8


async def test_explicit_cancel_stops_the_actual_query() -> None:
    execution = QueryExecution()
    started = asyncio.Event()

    async def operation() -> None:
        started.set()
        await asyncio.Event().wait()

    pending = asyncio.create_task(execution.run(
        _request(), operation, principal_id="one", session_id="session", turn_id="turn",
        timeout=10,
    ))
    await started.wait()
    execution.cancel_turn("one", "session", "turn")
    with pytest.raises(HTTPException) as raised:
        await asyncio.wait_for(pending, timeout=1)
    assert raised.value.detail == "TURN_CANCELLED"
    assert not execution._active


async def test_cancel_before_registration_never_sends_the_query() -> None:
    execution = QueryExecution()

    async def must_not_start() -> None:
        raise AssertionError("A cancelled turn must not start model or retrieval work")

    with pytest.raises(HTTPException) as raised:
        await execution.run(
            _request(), must_not_start, principal_id="one", timeout=1, cancelled=lambda: True,
        )
    assert raised.value.detail == "TURN_CANCELLED"
    assert not execution._active


async def test_query_overload_is_rejected_and_logout_cancels_every_task() -> None:
    execution = QueryExecution()
    entered = 0
    all_entered = asyncio.Event()

    async def operation() -> None:
        nonlocal entered
        entered += 1
        if entered == 8:
            all_entered.set()
        await asyncio.Event().wait()

    pending = [asyncio.create_task(execution.run(
        _request(), operation, principal_id="one", timeout=5,
    )) for _ in range(8)]
    await asyncio.wait_for(all_entered.wait(), timeout=1)
    try:
        with pytest.raises(HTTPException) as raised:
            await execution.run(_request(), operation, principal_id="two", timeout=5)
        assert raised.value.status_code == 429
        execution.cancel_principal("one")
        results = await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), 1)
        assert all(isinstance(result, HTTPException) for result in results)
        assert not execution._active
    finally:
        await execution.close()


def test_session_request_keeps_current_facts() -> None:
    request = TurnRequest(
        question="Còn trường hợp này?",
        scope=Scope(scope_mode="ALL_AUTHORIZED", as_of_date=date(2026, 10, 26)),
        facts=[Fact(key="document_number", value="1/2026/NĐ-CP")],
    )
    assert _session_query(request).facts == request.facts


async def test_replay_rechecks_current_acl(monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app()
    app.state.db_pool = object()
    app.state.settings = SimpleNamespace(dev_allow_in_memory_store=False)
    evidence = EvidenceRef(
        evidence_id=f"ev_{uuid4()}", document_id=uuid4(), document_version_id=uuid4(),
        node_id=uuid4(), title="Nguồn", label="Điều 1", quote_exact="Nội dung gốc",
        page=1, source_hash="a" * 64, as_of_date=date(2026, 10, 26),
        viewer_url="/api/v1/citations/example/pdf",
    )

    async def revoked(*args: object, **kwargs: object) -> dict[str, object]:
        return {}

    monkeypatch.setattr("app.main.get_authorized_citations", revoked)
    with pytest.raises(HTTPException) as raised:
        await _validate_replay_evidence(app, str(uuid4()), [StoredEvent(
            "evidence_verified", {"evidence": [evidence.model_dump(mode="json")]}
        )])
    assert raised.value.detail == "CITATION_INVALID"


def test_session_count_and_replay_bytes_are_bounded() -> None:
    memory = EphemeralMemoryService()
    memory._MAX_PRINCIPAL_SESSIONS = 1
    session = memory.create_session("one")
    with pytest.raises(MemoryCapacityError):
        memory.create_session("one")
    turn, _ = memory.create_turn(
        session.id, "one", idempotency_key="one",
        request=TurnRequest(question="Hỏi?", scope=Scope(
            scope_mode="ALL_AUTHORIZED", as_of_date=date(2026, 10, 26),
        )), query_id="query", run_id="run",
    )
    memory._MAX_TURN_BYTES = 100
    with pytest.raises(MemoryCapacityError):
        memory.finish_turn(session.id, "one", turn.turn_id, [StoredEvent(
            "evidence_verified", {"evidence": "x" * 101},
        )])
    assert turn.status == "running"
    assert turn.events == []
