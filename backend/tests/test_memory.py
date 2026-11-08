from datetime import timedelta

import pytest

from app.memory.service import EphemeralMemoryService
from app.schemas import Fact, FactStatus, Scope, ScopeMode, TurnRequest


def scope() -> Scope:
    return Scope(scope_mode=ScopeMode.ALL_AUTHORIZED, as_of_date="2026-01-01")  # type: ignore[arg-type]


def test_retained_session_requires_policy() -> None:
    service = EphemeralMemoryService()
    with pytest.raises(PermissionError, match="RETENTION_NOT_APPROVED"):
        service.create_session("user-1", incognito=False)


def test_retained_session_is_rejected_when_persistence_is_not_implemented() -> None:
    service = EphemeralMemoryService()
    with pytest.raises(PermissionError, match="RETENTION_UNAVAILABLE"):
        service.create_session("user-1", incognito=False, retention_approved=True)


def test_session_is_owned_by_principal() -> None:
    service = EphemeralMemoryService()
    session = service.create_session("user-1", scope=scope())
    with pytest.raises(KeyError, match="SESSION_EXPIRED"):
        service.get_session(session.id, "user-2")


def test_delete_removes_messages_and_session() -> None:
    service = EphemeralMemoryService()
    session = service.create_session("user-1", scope=scope())
    item_id = service.append_message(session.id, "user-1", "câu hỏi")
    assert service.list_memory(session.id, "user-1")
    service.delete_memory_item(session.id, "user-1", item_id)
    assert service.list_memory(session.id, "user-1") == []
    service.delete_session(session.id, "user-1")
    with pytest.raises(KeyError, match="SESSION_EXPIRED"):
        service.get_session(session.id, "user-1")


def test_expired_session_is_removed_from_ram(monkeypatch: pytest.MonkeyPatch) -> None:
    service = EphemeralMemoryService(ttl_seconds=10)
    session = service.create_session("user-1")
    service.append_message(session.id, "user-1", "Dữ liệu cần hết hạn")
    expired_at = session.last_seen_at + timedelta(seconds=11)
    monkeypatch.setattr(service, "_now", lambda: expired_at)
    with pytest.raises(KeyError, match="SESSION_EXPIRED"):
        service.get_session(session.id, "user-1")
    assert session.id not in service._sessions


def test_cleanup_expires_idle_sessions_without_a_request(monkeypatch: pytest.MonkeyPatch) -> None:
    service = EphemeralMemoryService(ttl_seconds=10)
    expired = service.create_session("user-1")
    clock = expired.last_seen_at + timedelta(seconds=11)
    monkeypatch.setattr(service, "_now", lambda: clock)
    assert service.purge_expired() == 1
    assert expired.id not in service._sessions
    live = service.create_session("user-2")
    assert service.purge_expired() == 0
    assert service.get_session(live.id, "user-2").id == live.id


def test_deleting_one_fact_invalidates_dependent_turns_and_keeps_other_facts() -> None:
    service = EphemeralMemoryService()
    session = service.create_session("user-1", scope=scope())
    turn, _ = service.create_turn(
        session.id, "user-1", idempotency_key="one", query_id="q", run_id="r",
        request=TurnRequest(question="Còn trường hợp này?", scope=scope(), facts=[
            Fact(key="role", value="công chức", status=FactStatus.USER_CONFIRMED),
            Fact(key="location", value="Hà Nội", status=FactStatus.USER_CONFIRMED),
        ]),
    )
    before = service.get_context(session.id, "user-1").facts_revision
    service.delete_fact(session.id, "user-1", "role")
    context = service.get_context(session.id, "user-1")
    assert [fact.key for fact in context.facts] == ["location"]
    assert context.facts_revision != before
    with pytest.raises(KeyError, match="TURN_NOT_FOUND"):
        service.get_turn(session.id, "user-1", turn.turn_id)
    with pytest.raises(KeyError, match="SESSION_EXPIRED"):
        service.delete_fact(session.id, "user-2", "location")
    service.delete_fact(session.id, "user-1", "role")  # idempotent
