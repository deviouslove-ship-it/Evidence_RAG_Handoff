"""Ephemeral RAM session, turn, and memory service.

This implementation is the POC profile.  It deliberately has no database path:
incognito sessions disappear on restart, expiry, logout, or explicit deletion.
A retained implementation requires an approved retention policy and opt-in.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import RLock
from uuid import UUID, uuid4

from ..schemas import Fact, MemoryItem, PreferencesRequest, Scope, TurnRequest


@dataclass(frozen=True)
class StoredEvent:
    """One replayable SSE event."""

    event: str
    data: dict[str, object]
    lookup_revision: int | None = None


@dataclass(frozen=True)
class StoredMessage:
    id: UUID
    content: str
    created_at: datetime


@dataclass(frozen=True)
class MemoryContext:
    """Bounded context that may help understand a follow-up turn.

    The context contains user/session state only.  Callers must still retrieve
    and validate evidence for every turn; these values are never citations.
    """

    messages: tuple[StoredMessage, ...]
    facts: tuple[Fact, ...]
    facts_revision: str
    memory_revision: str


@dataclass
class TurnState:
    turn_id: str
    query_id: str
    run_id: str
    status: str
    request: TurnRequest
    request_hash: str
    created_at: datetime
    events: list[StoredEvent] = field(default_factory=list)
    facts_snapshot: tuple[Fact, ...] = ()
    messages_snapshot: tuple[StoredMessage, ...] = ()
    context_facts_revision: str = "factrev_1"
    context_memory_revision: str = "memoryrev_1"
    event_bytes: int = 0


class IdempotencyConflictError(ValueError):
    """The same idempotency key was reused with a different request body."""


class MemoryCapacityError(RuntimeError):
    """The bounded in-memory replay store cannot accept another live turn."""


@dataclass
class _Session:
    id: UUID
    principal_id: str
    incognito: bool
    created_at: datetime
    last_seen_at: datetime
    facts_revision: str = "factrev_1"
    memory_revision: str = "memoryrev_1"
    scope: Scope | None = None
    facts: list[Fact] = field(default_factory=list)
    messages: list[StoredMessage] = field(default_factory=list)
    events: list[StoredEvent] = field(default_factory=list)
    turns: dict[str, TurnState] = field(default_factory=dict)
    idempotency: dict[str, str] = field(default_factory=dict)
    preferences: PreferencesRequest | None = None
    preferences_item_id: UUID | None = None


class EphemeralMemoryService:
    _MAX_SESSIONS = 64
    _MAX_PRINCIPAL_SESSIONS = 8
    _MAX_TURN_BYTES = 1024 * 1024
    _MAX_SESSION_EVENT_BYTES = 4 * 1024 * 1024
    _MAX_SESSION_MESSAGES = 100
    _MAX_SESSION_FACTS = 100
    _MAX_SESSION_TURNS = 100
    _MAX_SESSION_EVENTS = 500
    _MAX_TURN_EVENTS = 100
    _MAX_IDEMPOTENCY_KEYS = 200
    _MAX_CONTEXT_MESSAGES = 20
    _MAX_CONTEXT_FACTS = 32

    def __init__(self, ttl_seconds: int = 1800) -> None:
        self.ttl_seconds = ttl_seconds
        self._sessions: dict[UUID, _Session] = {}
        self._lock = RLock()

    def _now(self) -> datetime:
        return datetime.now(UTC)

    def purge_expired(self) -> int:
        """Release expired session data, including turns and replay buffers."""
        with self._lock:
            now = self._now()
            expired = [
                key
                for key, session in self._sessions.items()
                if session.last_seen_at + timedelta(seconds=self.ttl_seconds) <= now
            ]
            for key in expired:
                self._invalidate_turns(self._sessions[key])
                self._sessions[key].messages.clear()
                self._sessions[key].preferences = None
                del self._sessions[key]
            return len(expired)

    def _get_live(self, session_id: UUID, principal_id: str) -> _Session:
        with self._lock:
            self.purge_expired()
            session = self._sessions.get(session_id)
            now = self._now()
            if (
                session is None
                or session.principal_id != principal_id
                or session.last_seen_at + timedelta(seconds=self.ttl_seconds) <= now
            ):
                raise KeyError("SESSION_EXPIRED")
            session.last_seen_at = now
            return session

    def create_session(
        self,
        principal_id: str,
        *,
        incognito: bool = True,
        scope: Scope | None = None,
        retention_approved: bool = False,
    ) -> _Session:
        if not incognito:
            raise PermissionError(
                "RETENTION_UNAVAILABLE" if retention_approved else "RETENTION_NOT_APPROVED"
            )
        self.purge_expired()
        now = self._now()
        session = _Session(
            id=uuid4(),
            principal_id=principal_id,
            incognito=incognito,
            created_at=now,
            last_seen_at=now,
            scope=scope,
        )
        with self._lock:
            if len(self._sessions) >= self._MAX_SESSIONS or sum(
                item.principal_id == principal_id for item in self._sessions.values()
            ) >= self._MAX_PRINCIPAL_SESSIONS:
                raise MemoryCapacityError("SESSION_CAPACITY_EXCEEDED")
            self._sessions[session.id] = session
        return session

    def get_session(self, session_id: UUID, principal_id: str) -> _Session:
        return self._get_live(session_id, principal_id)

    def delete_session(self, session_id: UUID, principal_id: str) -> None:
        with self._lock:
            session = self._get_live(session_id, principal_id)
            self._invalidate_turns(session)
            session.messages.clear()
            session.preferences = None
            del self._sessions[session_id]

    def delete_principal(self, principal_id: str) -> int:
        """Delete every ephemeral session owned by a principal."""

        with self._lock:
            session_ids = [
                session_id
                for session_id, session in self._sessions.items()
                if session.principal_id == principal_id
            ]
            for session_id in session_ids:
                session = self._sessions[session_id]
                self._invalidate_turns(session)
                session.messages.clear()
                session.preferences = None
                del self._sessions[session_id]
            return len(session_ids)

    def append_message(self, session_id: UUID, principal_id: str, message: str) -> UUID:
        with self._lock:
            session = self._get_live(session_id, principal_id)
            item_id = uuid4()
            session.messages.append(
                StoredMessage(id=item_id, content=message, created_at=self._now())
            )
            if len(session.messages) > self._MAX_SESSION_MESSAGES:
                del session.messages[: len(session.messages) - self._MAX_SESSION_MESSAGES]
            session.memory_revision = f"memoryrev_{uuid4().hex[:12]}"
            return item_id

    def list_memory(self, session_id: UUID, principal_id: str) -> list[MemoryItem]:
        with self._lock:
            session = self._get_live(session_id, principal_id)
            items = [
                MemoryItem(
                    id=message.id,
                    kind="message",
                    content=message.content,
                    created_at=message.created_at.isoformat(),
                    expires_at=(
                        session.last_seen_at + timedelta(seconds=self.ttl_seconds)
                    ).isoformat(),
                )
                for message in session.messages
            ]
            if (
                session.preferences
                and session.preferences.enabled
                and session.preferences_item_id
            ):
                items.append(
                    MemoryItem(
                        id=session.preferences_item_id,
                        kind="preferences",
                        content="Sở thích tra cứu đang được bật",
                        created_at=session.created_at.isoformat(),
                        expires_at=None,
                    )
                )
            return items

    def get_context(
        self,
        session_id: UUID,
        principal_id: str,
        *,
        max_messages: int | None = None,
        max_facts: int | None = None,
    ) -> MemoryContext:
        """Return bounded session context for a follow-up turn.

        Context is advisory state only.  It does not authorize retrieval and
        must never be turned into evidence by a caller.
        """

        with self._lock:
            session = self._get_live(session_id, principal_id)
            message_limit = self._context_limit(max_messages, self._MAX_CONTEXT_MESSAGES)
            fact_limit = self._context_limit(max_facts, self._MAX_CONTEXT_FACTS)
            return self._make_context(
                messages=session.messages[-message_limit:] if message_limit else (),
                facts=session.facts[-fact_limit:] if fact_limit else (),
                facts_revision=session.facts_revision,
                memory_revision=session.memory_revision,
            )

    def query_context(
        self,
        session_id: UUID,
        principal_id: str,
        *,
        turn_id: str | None = None,
    ) -> MemoryContext:
        """Return current context or a stable snapshot for one turn."""

        if turn_id is not None:
            return self.get_turn_context(session_id, principal_id, turn_id)
        return self.get_context(session_id, principal_id)

    def get_turn_context(
        self,
        session_id: UUID,
        principal_id: str,
        turn_id: str,
    ) -> MemoryContext:
        """Return the context snapshot captured when a turn was created."""

        with self._lock:
            session = self._get_live(session_id, principal_id)
            turn = session.turns.get(turn_id)
            if turn is None:
                raise KeyError("TURN_NOT_FOUND")
            return self._make_context(
                messages=turn.messages_snapshot,
                facts=turn.facts_snapshot,
                facts_revision=turn.context_facts_revision,
                memory_revision=turn.context_memory_revision,
            )

    def delete_memory_item(self, session_id: UUID, principal_id: str, item_id: UUID) -> None:
        with self._lock:
            session = self._get_live(session_id, principal_id)
            before = len(session.messages)
            session.messages = [
                message for message in session.messages if message.id != item_id
            ]
            if len(session.messages) == before:
                if session.preferences_item_id != item_id:
                    raise KeyError("MEMORY_ITEM_NOT_FOUND")
                session.preferences = None
                session.preferences_item_id = None
            # Subsequent turns may depend on the deleted context. Keep only opaque
            # idempotency tombstones so a delayed duplicate cannot recreate it.
            self._invalidate_turns(session)
            session.memory_revision = f"memoryrev_{uuid4().hex[:12]}"

    def delete_fact(self, session_id: UUID, principal_id: str, key: str) -> bool:
        """Forget a fact and invalidate results that could have depended on it."""
        with self._lock:
            session = self._get_live(session_id, principal_id)
            remaining = [fact for fact in session.facts if fact.key.casefold() != key.casefold()]
            if len(remaining) == len(session.facts):
                return False
            self._invalidate_turns(session)
            session.facts = remaining
            session.memory_revision = f"memoryrev_{uuid4().hex[:12]}"
            return True

    @staticmethod
    def _invalidate_turns(session: _Session) -> None:
        for turn in session.turns.values():
            turn.status = "cancelled"
            turn.events.clear()
            turn.event_bytes = 0
        session.turns.clear()
        session.events.clear()
        session.facts.clear()
        session.facts_revision = f"factrev_{uuid4().hex[:12]}"

    @staticmethod
    def _context_limit(value: int | None, default: int) -> int:
        if value is None:
            return default
        return max(0, min(value, default))

    @staticmethod
    def _make_context(
        *,
        messages: Sequence[StoredMessage],
        facts: Sequence[Fact],
        facts_revision: str,
        memory_revision: str,
    ) -> MemoryContext:
        return MemoryContext(
            messages=tuple(messages),
            facts=tuple(fact.model_copy(deep=True) for fact in facts),
            facts_revision=facts_revision,
            memory_revision=memory_revision,
        )

    def _remember_facts(self, session: _Session, facts: Sequence[Fact]) -> None:
        changed = False
        for fact in facts:
            session.facts = [existing for existing in session.facts if existing.key != fact.key]
            session.facts.append(fact.model_copy(deep=True))
            changed = True
        if changed:
            if len(session.facts) > self._MAX_SESSION_FACTS:
                del session.facts[: len(session.facts) - self._MAX_SESSION_FACTS]
            session.facts_revision = f"factrev_{uuid4().hex[:12]}"

    def _trim_idempotency(self, session: _Session) -> None:
        while len(session.idempotency) > self._MAX_IDEMPOTENCY_KEYS:
            oldest_key = next(iter(session.idempotency))
            del session.idempotency[oldest_key]

    def _trim_turns(self, session: _Session) -> None:
        retained_bytes = sum(turn.event_bytes for turn in session.turns.values())
        if (
            len(session.turns) <= self._MAX_SESSION_TURNS
            and retained_bytes <= self._MAX_SESSION_EVENT_BYTES
        ):
            return
        candidates = sorted(
            session.turns.values(),
            key=lambda turn: turn.created_at,
        )
        for turn in candidates:
            if (
                len(session.turns) <= self._MAX_SESSION_TURNS
                and retained_bytes <= self._MAX_SESSION_EVENT_BYTES
            ):
                break
            if turn.status == "running":
                continue
            session.turns.pop(turn.turn_id, None)
            retained_bytes -= turn.event_bytes
        session.events = [
            event for turn in session.turns.values() for event in turn.events
        ][-self._MAX_SESSION_EVENTS :]
        if len(session.turns) > self._MAX_SESSION_TURNS:
            raise MemoryCapacityError("TURN_CAPACITY_EXCEEDED")

    def create_turn(
        self,
        session_id: UUID,
        principal_id: str,
        *,
        idempotency_key: str,
        request: TurnRequest,
        query_id: str,
        run_id: str,
    ) -> tuple[TurnState, bool]:
        """Create a turn or return the existing turn for an identical request."""

        request_hash = self._request_hash(request)
        with self._lock:
            session = self._get_live(session_id, principal_id)
            scoped_key = f"{principal_id}:{session_id}:{idempotency_key}"
            existing_id = session.idempotency.get(scoped_key)
            if existing_id:
                existing = session.turns.get(existing_id)
                if existing is None:
                    raise IdempotencyConflictError("TURN_INVALIDATED")
                if existing:
                    if existing.request_hash != request_hash:
                        raise IdempotencyConflictError("IDEMPOTENCY_KEY_REUSED")
                    return existing, False
            turn = TurnState(
                turn_id=f"turn_{uuid4().hex}",
                query_id=query_id,
                run_id=run_id,
                status="running",
                request=request,
                request_hash=request_hash,
                created_at=self._now(),
            )
            session.turns[turn.turn_id] = turn
            try:
                self._trim_turns(session)
            except MemoryCapacityError:
                session.turns.pop(turn.turn_id, None)
                raise
            session.idempotency[scoped_key] = turn.turn_id
            self._trim_idempotency(session)
            self._remember_facts(session, request.facts)
            turn.facts_snapshot = tuple(
                fact.model_copy(deep=True)
                for fact in session.facts[-self._MAX_CONTEXT_FACTS :]
            )
            turn.messages_snapshot = tuple(session.messages[-self._MAX_CONTEXT_MESSAGES :])
            turn.context_facts_revision = session.facts_revision
            turn.context_memory_revision = session.memory_revision
            return turn, True

    def append_turn_message(
        self,
        session_id: UUID,
        principal_id: str,
        turn_id: str,
        message: str,
    ) -> None:
        with self._lock:
            session = self._get_live(session_id, principal_id)
            turn = session.turns.get(turn_id)
            if turn is None:
                raise KeyError("TURN_NOT_FOUND")
            if turn.status != "running":
                return
            item_id = uuid4()
            session.messages.append(
                StoredMessage(id=item_id, content=message, created_at=self._now())
            )
            if len(session.messages) > self._MAX_SESSION_MESSAGES:
                del session.messages[: len(session.messages) - self._MAX_SESSION_MESSAGES]
            session.memory_revision = f"memoryrev_{uuid4().hex[:12]}"

    def fail_turn(self, session_id: UUID, principal_id: str, turn_id: str) -> None:
        with self._lock:
            session = self._get_live(session_id, principal_id)
            turn = session.turns.get(turn_id)
            if turn is None:
                raise KeyError("TURN_NOT_FOUND")
            if turn.status == "running":
                turn.status = "failed"

    def finish_turn(
        self,
        session_id: UUID,
        principal_id: str,
        turn_id: str,
        events: list[StoredEvent],
    ) -> None:
        with self._lock:
            session = self._get_live(session_id, principal_id)
            turn = session.turns.get(turn_id)
            if turn is None:
                raise KeyError("TURN_NOT_FOUND")
            if turn.status == "cancelled":
                return
            bounded_events = list(events)[-self._MAX_TURN_EVENTS :]
            event_bytes = len(json.dumps(
                [{"event": event.event, "data": event.data} for event in bounded_events],
                ensure_ascii=False,
            ).encode("utf-8"))
            if event_bytes > self._MAX_TURN_BYTES:
                raise MemoryCapacityError("TURN_PAYLOAD_TOO_LARGE")
            turn.status = "completed"
            turn.events = bounded_events
            turn.event_bytes = event_bytes
            session.events.extend(turn.events)
            if len(session.events) > self._MAX_SESSION_EVENTS:
                del session.events[: len(session.events) - self._MAX_SESSION_EVENTS]
            self._trim_turns(session)

    def get_turn(
        self,
        session_id: UUID,
        principal_id: str,
        turn_id: str,
    ) -> TurnState:
        with self._lock:
            session = self._get_live(session_id, principal_id)
            turn = session.turns.get(turn_id)
            if turn is None:
                raise KeyError("TURN_NOT_FOUND")
            return turn

    def cancel_turn(self, session_id: UUID, principal_id: str, turn_id: str) -> None:
        with self._lock:
            session = self._get_live(session_id, principal_id)
            turn = session.turns.get(turn_id)
            if turn is None:
                raise KeyError("TURN_NOT_FOUND")
            if turn.status == "running":
                turn.status = "cancelled"
                turn.events.clear()

    def get_preferences(
        self, session_id: UUID, principal_id: str
    ) -> PreferencesRequest | None:
        with self._lock:
            session = self._get_live(session_id, principal_id)
            if session.preferences is None:
                return None
            return session.preferences.model_copy(deep=True)

    def set_preferences(
        self,
        session_id: UUID,
        principal_id: str,
        preferences: PreferencesRequest,
    ) -> None:
        with self._lock:
            session = self._get_live(session_id, principal_id)
            session.preferences = preferences
            session.preferences_item_id = uuid4() if preferences.enabled else None
            session.memory_revision = f"memoryrev_{uuid4().hex[:12]}"

    @staticmethod
    def _request_hash(request: TurnRequest) -> str:
        canonical = json.dumps(
            request.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()
