"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from starlette.concurrency import run_in_threadpool
from starlette.staticfiles import StaticFiles

from .admin_services import list_authorized_categories
from .api.v1.admin import router as admin_router
from .api.v1.auth import router as auth_router
from .api.v1.comprehensive import router as comprehensive_router
from .api.v1.effectivity import router as effectivity_router
from .api.v1.errors import api_error, api_error_handler
from .api.v1.execution import QueryExecution
from .api.v1.openapi import configure_openapi
from .api.v1.synthesis import router as synthesis_router
from .api.v1.user import require_user
from .api.v1.user import router as user_router
from .auth_acl.policy import Principal
from .config import Settings
from .documents.provenance import (
    read_immutable_pdf,
    read_immutable_source,
    verify_immutable_pdf,
)
from .memory.service import (
    EphemeralMemoryService,
    IdempotencyConflictError,
    MemoryCapacityError,
    StoredEvent,
)
from .migrations.runner import apply_migrations
from .model_registry.profiles import OperatingMode
from .model_registry.runtime import EndpointPolicy, RegistryRuntime
from .schemas import (
    AnalyzeRequest,
    CitationResponse,
    EvidenceRef,
    MemoryListResponse,
    PreferencesRequest,
    ScopeMode,
    SessionCreateRequest,
    SessionResponse,
    TurnRequest,
)
from .storage.chat_retrieval import ChatRetrieval
from .storage.citations import (
    AuthorizedCitation,
    get_authorized_citation,
    get_authorized_citations,
)
from .storage.comprehensive import ComprehensiveSearch
from .storage.cross_encoder import CrossEncoderClient
from .storage.embedding_jobs import EmbeddingWorker
from .storage.normalization import normalization_status
from .storage.postgres import create_pool
from .storage.search import SearchService, SlidingWindowRateLimiter
from .synthesis.service import SynthesisService
from .workflow.ai_selection import ConfiguredSelection
from .workflow.fixed_pipeline import FixedPipeline, PipelineDependencies

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings.from_env()
    settings.validate_runtime()
    app.state.settings = settings
    ai_policy = EndpointPolicy.from_env()
    app.state.memory = EphemeralMemoryService(settings.session_ttl_seconds)
    app.state.search_authorized_nodes = await _build_search(app, settings)
    app.state.ai_runtime = RegistryRuntime(
        getattr(app.state, "db_pool", None), mode=OperatingMode(settings.operating_mode),
        attempt_limit=settings.llm_attempt_budget, policy=ai_policy,
    )
    app.state.comprehensive_search = (
        ComprehensiveSearch(
            app.state.search_service, app.state.ai_runtime,
            semantic_top_n=settings.semantic_top_n,
            semantic_relative_threshold=settings.semantic_relative_threshold,
            rerank_top_n=settings.rerank_top_n, rerank_batch_size=settings.rerank_batch_size,
            result_set_ttl_seconds=settings.result_set_ttl_seconds,
            concept_min_terms=settings.concept_min_terms,
            statement_timeout_ms=settings.search_statement_timeout_ms,
            cross_encoder=(
                CrossEncoderClient(
                    settings.cross_encoder_url or "",
                    timeout_seconds=settings.cross_encoder_timeout_seconds,
                    instruction=settings.cross_encoder_instruction,
                )
                if settings.rerank_backend == "cross_encoder" else None
            ),
        )
        if getattr(app.state, "search_service", None) is not None
        else None
    )
    pool = getattr(app.state, "db_pool", None)
    chat_retrieval = (
        ChatRetrieval(app.state.comprehensive_search)
        if app.state.comprehensive_search is not None else None
    )
    app.state.synthesis = (
        SynthesisService(pool, app.state.ai_runtime, retrieval=chat_retrieval)
        if pool is not None else None
    )
    app.state.pipeline = FixedPipeline(
        dependencies=PipelineDependencies(
            search_authorized_nodes=app.state.search_authorized_nodes,
            select_evidence=ConfiguredSelection(
                app.state.ai_runtime,
                timeout_seconds=settings.query_timeout_seconds * 0.7,
            ),
            chat_retrieval=chat_retrieval,
        ),
        operating_mode=settings.operating_mode,
        llm_attempt_budget=settings.llm_attempt_budget,
    )
    app.state.embedding_worker = None
    if pool is not None and settings.embedding_worker_enabled:
        # Embedding rebuilds queued from the Admin Portal run here, independent of any
        # browser session; jobs left running by a stopped process resume on restart.
        app.state.embedding_worker = EmbeddingWorker(pool, app.state.ai_runtime)
        app.state.embedding_worker.start()
    cleanup = asyncio.create_task(_expire_sessions(app.state.memory, settings.session_ttl_seconds))
    try:
        yield
    finally:
        if app.state.embedding_worker is not None:
            await app.state.embedding_worker.stop()
        await app.state.execution.close()
        cleanup.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup
        if hasattr(app.state, "db_pool"):
            await app.state.db_pool.close()


async def _expire_sessions(memory: EphemeralMemoryService, ttl_seconds: int) -> None:
    while True:
        await asyncio.sleep(max(1, min(ttl_seconds, 60)))
        memory.purge_expired()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Vietnamese Evidence RAG Agent",
        version="0.1.0",
        description="Read-only evidence retrieval with source-first citations.",
        lifespan=lifespan,
    )
    app.add_exception_handler(Exception, api_error_handler)
    app.add_exception_handler(HTTPException, api_error_handler)
    app.add_exception_handler(RequestValidationError, api_error_handler)
    app.include_router(auth_router)
    app.include_router(user_router)
    app.include_router(admin_router)
    app.include_router(effectivity_router)
    app.include_router(comprehensive_router)
    app.include_router(synthesis_router)
    configure_openapi(app)
    cors_settings = Settings.from_env()
    cors_headers = [
        "Authorization",
        "Content-Type",
        "Idempotency-Key",
        "If-Match",
        "Last-Event-ID",
        "X-Turn-Id",
    ]
    if cors_settings.dev_allow_in_memory_store:
        # Identity headers exist only for the explicit in-memory development profile.
        cors_headers += ["X-Principal-Id", "X-Roles"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cors_settings.allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=cors_headers,
        expose_headers=["X-Turn-Id"],
    )
    app.state.settings = cors_settings
    app.state.pdf_slots = asyncio.Semaphore(2)
    app.state.auth_slots = asyncio.Semaphore(4)
    app.state.execution = QueryExecution()
    app.state.search_rate = SlidingWindowRateLimiter(
        limit=cors_settings.search_rate_limit_per_minute
    )
    app.state.search_service = None

    @app.get("/health")
    async def health() -> dict[str, str]:
        pool = getattr(app.state, "db_pool", None)
        if pool is not None:
            try:
                async with asyncio.timeout(2), pool.acquire() as connection:
                    await connection.fetchval("SELECT 1")
            except Exception as exc:
                raise api_error(503, "DATABASE_UNAVAILABLE") from exc
        return {"status": "ok", "service": "evidence-rag"}

    @app.get("/api/v1/system/mode")
    async def system_mode() -> dict[str, object]:
        return {
            "effective_mode": app.state.settings.operating_mode,
            "query_timeout_seconds": app.state.settings.query_timeout_seconds,
            "pdf_timeout_seconds": app.state.settings.pdf_timeout_seconds,
            "search_normalization_status": (
                "unavailable"
                if getattr(app.state, "search_normalization", None) is None
                else (
                    "stale"
                    if app.state.search_normalization["stale_nodes"]
                    else "current"
                )
            ),
            "search_normalization_revision": (
                app.state.search_normalization["current_revision"]
                if getattr(app.state, "search_normalization", None)
                else None
            ),
            "search_normalization_stale_nodes": (
                app.state.search_normalization["stale_nodes"]
                if getattr(app.state, "search_normalization", None)
                else 0
            ),
        }

    @app.post(
        "/api/v1/agent/sessions",
        response_model=SessionResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_session(
        request: SessionCreateRequest,
        principal: Annotated[Principal, Depends(require_user)],
    ) -> SessionResponse:
        principal_id = _principal_id(principal.id)
        try:
            session = app.state.memory.create_session(
                str(principal_id),
                incognito=request.incognito,
                scope=request.scope,
                retention_approved=app.state.settings.retention_approved,
            )
        except PermissionError as exc:
            code = (
                "RETENTION_UNAVAILABLE"
                if str(exc) == "RETENTION_UNAVAILABLE"
                else "RETENTION_NOT_APPROVED"
            )
            raise api_error(409, code) from exc
        except MemoryCapacityError as exc:
            raise api_error(429, "MEMORY_CAPACITY_EXCEEDED") from exc
        return SessionResponse(
            session_id=session.id,
            persistence_state="ephemeral",
            expires_at=(
                session.last_seen_at
                + timedelta(seconds=app.state.settings.session_ttl_seconds)
            ).isoformat(),
            facts_revision=session.facts_revision,
            memory_revision=session.memory_revision,
        )

    @app.get("/api/v1/agent/sessions/{session_id}", response_model=SessionResponse)
    async def get_session(
        session_id: UUID,
        principal: Annotated[Principal, Depends(require_user)],
    ) -> SessionResponse:
        try:
            session = app.state.memory.get_session(session_id, principal.id)
        except KeyError as exc:
            raise api_error(410, "SESSION_EXPIRED") from exc
        return SessionResponse(
            session_id=session.id,
            persistence_state="ephemeral",
            expires_at=(
                session.last_seen_at
                + timedelta(seconds=app.state.settings.session_ttl_seconds)
            ).isoformat(),
            facts_revision=session.facts_revision,
            memory_revision=session.memory_revision,
        )

    @app.delete("/api/v1/agent/sessions/{session_id}/facts", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_session_fact(
        session_id: UUID,
        principal: Annotated[Principal, Depends(require_user)],
        key: Annotated[str, Query(min_length=1, max_length=80)],
    ) -> Response:
        try:
            changed = app.state.memory.delete_fact(session_id, principal.id, key)
            if changed:
                app.state.execution.cancel_session(principal.id, str(session_id))
        except KeyError as exc:
            raise api_error(410, "SESSION_EXPIRED") from exc
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post("/api/v1/agent/sessions/{session_id}/turns")
    async def create_turn(
        session_id: UUID,
        request: TurnRequest,
        http_request: Request,
        principal: Annotated[Principal, Depends(require_user)],
        idempotency_key: str | None = Header(default=None),
    ) -> StreamingResponse:
        if not idempotency_key:
            raise api_error(400, "IDEMPOTENCY_KEY_REQUIRED")
        principal_id = _principal_id(principal.id)
        try:
            context = app.state.memory.query_context(session_id, principal.id)
            request = _with_preferences(
                request, app.state.memory.get_preferences(session_id, principal.id)
            )
            query = _session_query(request)
            preliminary = await app.state.pipeline.analyze(query, memory_context=context)
            turn, created = app.state.memory.create_turn(
                session_id, principal.id, idempotency_key=f"turn:{idempotency_key}",
                request=request, query_id=preliminary.query_id, run_id=preliminary.run_id,
            )
        except MemoryCapacityError as exc:
            raise api_error(429, "MEMORY_CAPACITY_EXCEEDED") from exc
        except IdempotencyConflictError as exc:
            raise api_error(409, "IDEMPOTENCY_KEY_REUSED") from exc
        except KeyError as exc:
            raise api_error(410, "SESSION_EXPIRED") from exc
        if not created:
            if turn.status == "running":
                raise api_error(409, "TURN_IN_PROGRESS", headers={"X-Turn-Id": turn.turn_id})
            if turn.status != "completed":
                raise api_error(409, "TURN_CANCELLED")
            await _validate_replay_evidence(app, principal.id, turn.events)

            async def replay_events() -> AsyncIterator[str]:
                for event in turn.events:
                    yield _sse(event.event, event.data)

            return StreamingResponse(
                replay_events(), media_type="text/event-stream",
                headers={"Cache-Control": "no-store", "X-Turn-Id": turn.turn_id},
            )
        app.state.memory.append_turn_message(
            session_id, principal.id, turn.turn_id, request.question
        )
        context = app.state.memory.get_turn_context(session_id, principal.id, turn.turn_id)
        base = {"query_id": turn.query_id, "run_id": turn.run_id,
                "facts_revision": context.facts_revision, "snapshot_revision": None}

        async def events() -> AsyncIterator[str]:
            yield _sse("retrieval_started", {**base, "event_sequence": 1})
            try:
                result = await app.state.execution.run(
                    http_request,
                    lambda: app.state.pipeline.execute(
                        query, principal_id=principal_id, query_id=turn.query_id,
                        run_id=turn.run_id, memory_context=context,
                        facts_revision=context.facts_revision,
                    ),
                    principal_id=principal.id, session_id=str(session_id), turn_id=turn.turn_id,
                    timeout=app.state.settings.query_timeout_seconds, watch_disconnect=False,
                    cancelled=lambda: turn.status != "running",
                )
                stored_events = _build_turn_events(result)
                await _validate_replay_evidence(app, principal.id, stored_events)
                active = app.state.memory.get_turn(session_id, principal.id, turn.turn_id)
                if active.status == "cancelled":
                    yield _sse("turn_cancelled", {**base, "event_sequence": 2})
                    return
                app.state.memory.finish_turn(session_id, principal.id, turn.turn_id, stored_events)
                for event in stored_events[1:]:
                    yield _sse(event.event, event.data)
            except KeyError:
                # Session or turn disappeared (expiry, memory deletion): tell the client
                # instead of ending the stream without a terminal event.
                yield _sse("turn_error", {**base, "event_sequence": 2, "code": "SESSION_EXPIRED"})
                return
            except MemoryCapacityError:
                with suppress(KeyError):
                    app.state.memory.fail_turn(session_id, principal.id, turn.turn_id)
                yield _sse("turn_error", {
                    **base, "event_sequence": 2, "code": "MEMORY_CAPACITY_EXCEEDED",
                })
            except HTTPException as exc:
                with suppress(KeyError):
                    app.state.memory.fail_turn(session_id, principal.id, turn.turn_id)
                cancelled = exc.detail in {"TURN_CANCELLED", "REQUEST_CANCELLED"}
                yield _sse("turn_cancelled" if cancelled else "turn_error", {
                    **base, "event_sequence": 2, "code": exc.detail,
                })
            except TimeoutError:
                # Evidence retrieval hit its database budget; tell the user to retry
                # instead of reporting a generic failure.
                with suppress(KeyError):
                    app.state.memory.fail_turn(session_id, principal.id, turn.turn_id)
                yield _sse("turn_error", {**base, "event_sequence": 2, "code": "QUERY_TIMEOUT"})
            except Exception:
                with suppress(KeyError):
                    app.state.memory.fail_turn(session_id, principal.id, turn.turn_id)
                yield _sse("turn_error", {**base, "event_sequence": 2, "code": "QUERY_FAILED"})
            finally:
                app.state.execution.cancel_turn(principal.id, str(session_id), turn.turn_id)
                with suppress(KeyError):
                    active = app.state.memory.get_turn(session_id, principal.id, turn.turn_id)
                    if active.status == "running":
                        app.state.memory.fail_turn(session_id, principal.id, turn.turn_id)

        return StreamingResponse(
            events(), media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no",
                     "X-Turn-Id": turn.turn_id},
        )

    @app.post("/api/v1/agent/sessions/{session_id}/turns/{turn_id}/cancel")
    async def cancel_turn(
        session_id: UUID,
        turn_id: str,
        principal: Annotated[Principal, Depends(require_user)],
    ) -> dict[str, str]:
        try:
            app.state.memory.cancel_turn(session_id, principal.id, turn_id)
            app.state.execution.cancel_turn(principal.id, str(session_id), turn_id)
        except KeyError as exc:
            code = "TURN_NOT_FOUND" if exc.args == ("TURN_NOT_FOUND",) else "SESSION_EXPIRED"
            raise api_error(404 if code == "TURN_NOT_FOUND" else 410, code) from exc
        return {"status": "cancelled", "turn_id": turn_id}

    @app.post("/api/v1/agent/sessions/{session_id}/turns/{turn_id}/retry")
    async def retry_turn(
        session_id: UUID,
        turn_id: str,
        http_request: Request,
        principal: Annotated[Principal, Depends(require_user)],
        idempotency_key: str | None = Header(default=None),
    ) -> dict[str, str]:
        try:
            original = app.state.memory.get_turn(session_id, principal.id, turn_id)
        except KeyError as exc:
            code = "TURN_NOT_FOUND" if exc.args == ("TURN_NOT_FOUND",) else "SESSION_EXPIRED"
            raise api_error(404 if code == "TURN_NOT_FOUND" else 410, code) from exc
        if not idempotency_key:
            raise api_error(400, "IDEMPOTENCY_KEY_REQUIRED")
        if original.status == "running":
            raise api_error(409, "TURN_IN_PROGRESS")
        query = _session_query(original.request)
        context = app.state.memory.get_turn_context(session_id, principal.id, turn_id)
        preliminary = await app.state.pipeline.analyze(query, memory_context=context)
        try:
            retry_turn_state, created = app.state.memory.create_turn(
                session_id,
                principal.id,
                idempotency_key=f"retry:{turn_id}:{idempotency_key}",
                request=original.request,
                query_id=preliminary.query_id,
                run_id=preliminary.run_id,
            )
        except MemoryCapacityError as exc:
            raise api_error(429, "MEMORY_CAPACITY_EXCEEDED") from exc
        except IdempotencyConflictError as exc:
            raise api_error(409, "IDEMPOTENCY_KEY_REUSED") from exc
        except KeyError as exc:
            raise api_error(410, "SESSION_EXPIRED") from exc
        if not created:
            if retry_turn_state.status == "running":
                raise api_error(409, "TURN_IN_PROGRESS")
            if retry_turn_state.status != "completed":
                raise api_error(409, "TURN_CANCELLED")
            await _validate_replay_evidence(app, principal.id, retry_turn_state.events)
            return {
                "status": "retry_ready",
                "turn_id": retry_turn_state.turn_id,
                "run_id": retry_turn_state.run_id,
            }
        try:
            result = await app.state.execution.run(
                http_request,
                lambda: app.state.pipeline.execute(
                    query, principal_id=_principal_id(principal.id),
                    query_id=retry_turn_state.query_id, run_id=retry_turn_state.run_id,
                    memory_context=context, facts_revision=context.facts_revision,
                ),
                principal_id=principal.id, session_id=str(session_id),
                turn_id=retry_turn_state.turn_id,
                timeout=app.state.settings.query_timeout_seconds,
                cancelled=lambda: retry_turn_state.status != "running",
            )
            events = _build_turn_events(result)
            await _validate_replay_evidence(app, principal.id, events)
        except TimeoutError as exc:
            # Evidence retrieval hit its database budget.
            with suppress(KeyError):
                app.state.memory.fail_turn(session_id, principal.id, retry_turn_state.turn_id)
            raise api_error(504, "QUERY_TIMEOUT") from exc
        except Exception:
            with suppress(KeyError):
                app.state.memory.fail_turn(session_id, principal.id, retry_turn_state.turn_id)
            raise
        try:
            if retry_turn_state.status == "cancelled":
                raise api_error(409, "TURN_CANCELLED")
            app.state.memory.finish_turn(
                session_id, principal.id, retry_turn_state.turn_id, events
            )
        except MemoryCapacityError as exc:
            app.state.memory.fail_turn(session_id, principal.id, retry_turn_state.turn_id)
            raise api_error(429, "MEMORY_CAPACITY_EXCEEDED") from exc
        except KeyError as exc:
            raise api_error(410, "SESSION_EXPIRED") from exc
        return {
            "status": "retry_ready",
            "turn_id": retry_turn_state.turn_id,
            "run_id": retry_turn_state.run_id,
        }

    @app.get("/api/v1/agent/sessions/{session_id}/turns/{turn_id}/events")
    async def turn_events(
        session_id: UUID,
        turn_id: str,
        principal: Annotated[Principal, Depends(require_user)],
        last_event_id: str | None = Header(default=None),
        run_id: str | None = Query(default=None),
    ) -> StreamingResponse:
        try:
            turn = app.state.memory.get_turn(session_id, principal.id, turn_id)
        except KeyError as exc:
            code = "TURN_NOT_FOUND" if exc.args == ("TURN_NOT_FOUND",) else "SESSION_EXPIRED"
            raise api_error(404 if code == "TURN_NOT_FOUND" else 410, code) from exc
        if run_id and run_id != turn.run_id:
            raise api_error(409, "RUN_MISMATCH")
        if turn.status == "running":
            raise api_error(409, "TURN_IN_PROGRESS")
        if turn.status != "completed":
            raise api_error(409, "TURN_CANCELLED")
        await _validate_replay_evidence(app, principal.id, turn.events)
        after = _parse_last_event_sequence(
            last_event_id, query_id=turn.query_id, run_id=turn.run_id
        )

        async def replay() -> AsyncIterator[str]:
            for event in turn.events:
                if after is not None and _event_sequence(event.data) <= after:
                    continue
                yield _sse(event.event, event.data)

        return StreamingResponse(
            replay(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-store",
                "X-Accel-Buffering": "no",
                "X-Turn-Id": turn.turn_id,
            },
        )

    @app.delete("/api/v1/agent/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_session(
        session_id: UUID,
        principal: Annotated[Principal, Depends(require_user)],
    ) -> Response:
        try:
            app.state.memory.delete_session(session_id, principal.id)
            app.state.execution.cancel_session(principal.id, str(session_id))
        except KeyError as exc:
            raise api_error(410, "SESSION_EXPIRED") from exc

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/api/v1/memory", response_model=MemoryListResponse)
    async def list_memory(
        session_id: UUID,
        principal: Annotated[Principal, Depends(require_user)],
    ) -> MemoryListResponse:
        try:
            session = app.state.memory.get_session(session_id, principal.id)
            items = app.state.memory.list_memory(session_id, principal.id)
        except KeyError as exc:
            raise api_error(410, "SESSION_EXPIRED") from exc
        return MemoryListResponse(
            items=items,
            persistence_state="ephemeral",
            memory_revision=session.memory_revision,
        )

    @app.delete("/api/v1/memory/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_memory_item(
        item_id: UUID,
        session_id: UUID,
        principal: Annotated[Principal, Depends(require_user)],
    ) -> Response:
        try:
            app.state.memory.delete_memory_item(session_id, principal.id, item_id)
            app.state.execution.cancel_session(principal.id, str(session_id))
        except KeyError as exc:
            code = (
                "MEMORY_ITEM_NOT_FOUND"
                if exc.args == ("MEMORY_ITEM_NOT_FOUND",)
                else "SESSION_EXPIRED"
            )
            raise api_error(404 if code == "MEMORY_ITEM_NOT_FOUND" else 410, code) from exc

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.delete("/api/v1/memory", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_memory(
        session_id: UUID,
        principal: Annotated[Principal, Depends(require_user)],
    ) -> Response:
        try:
            app.state.memory.delete_session(session_id, principal.id)
            app.state.execution.cancel_session(principal.id, str(session_id))
        except KeyError as exc:
            raise api_error(410, "SESSION_EXPIRED") from exc

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.put("/api/v1/memory/preferences")
    async def set_preferences(
        session_id: UUID,
        request: PreferencesRequest,
        principal: Annotated[Principal, Depends(require_user)],
    ) -> dict[str, str]:
        if request.default_as_of_date is not None:
            raise api_error(422, "PREFERENCE_DATE_UNAVAILABLE")
        if request.enabled and not request.default_category_ids:
            raise api_error(422, "CATEGORY_REQUIRED")
        try:
            app.state.memory.set_preferences(session_id, principal.id, request)
        except KeyError as exc:
            raise api_error(410, "SESSION_EXPIRED") from exc
        return {"status": "updated"}
    @app.get("/api/v1/memory/preferences")
    async def get_preferences(
        session_id: UUID,
        principal: Annotated[Principal, Depends(require_user)],
    ) -> dict[str, object]:
        try:
            preferences = cast(
                PreferencesRequest | None,
                app.state.memory.get_preferences(session_id, principal.id),
            )
        except KeyError as exc:
            raise api_error(410, "SESSION_EXPIRED") from exc
        if preferences is None or not preferences.enabled:
            return {"enabled": False, "default_category_ids": [], "default_as_of_date": None}
        return preferences.model_dump(mode="json")

    async def _open_citation(
        citation_id: str, principal: Principal, as_of_date: date | None
    ) -> AuthorizedCitation:
        pool = getattr(app.state, "db_pool", None)
        if pool is None:
            # In-memory POC has no verified source store: fail closed.
            raise api_error(404, "CITATION_INVALID")
        found = await get_authorized_citation(
            pool,
            principal_id=_principal_id(principal.id),
            citation_id=citation_id,
            as_of_date=as_of_date or date.today(),
        )
        if found is None:
            raise api_error(404, "CITATION_INVALID")
        return found

    @app.get("/api/v1/citations/{citation_id}", response_model=CitationResponse)
    async def citation(
        citation_id: str,
        principal: Annotated[Principal, Depends(require_user)],
        as_of_date: date | None = None,
    ) -> CitationResponse:
        return (await _open_citation(citation_id, principal, as_of_date)).response

    @app.get("/api/v1/citations/{citation_id}/pdf")
    async def citation_pdf(
        citation_id: str,
        principal: Annotated[Principal, Depends(require_user)],
        as_of_date: date | None = None,
    ) -> Response:
        found = await _open_citation(citation_id, principal, as_of_date)
        settings = app.state.settings
        if not settings.document_store_root:
            raise api_error(503, "DOCUMENT_STORE_NOT_CONFIGURED")
        try:
            content = await run_in_threadpool(
                read_immutable_pdf,
                Path(settings.document_store_root),
                found.original_file_path,
                found.source_hash,
                max_bytes=settings.max_upload_bytes,
            )
        except ValueError as exc:
            raise api_error(503, "CITATION_SOURCE_UNAVAILABLE") from exc
        return Response(
            content=content,
            media_type="application/pdf",
            headers={
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Content-Disposition": 'inline; filename="document.pdf"',
            },
        )

    @app.get("/api/v1/citations/{citation_id}/original")
    async def citation_original(
        citation_id: str,
        principal: Annotated[Principal, Depends(require_user)],
        as_of_date: date | None = None,
    ) -> Response:
        """The file exactly as the curator uploaded it (ACL, version and SHA-256 re-checked).

        A PDF (scans included) is the stored original itself.  For Word/TXT the uploaded
        file is served, never the PDF rendered from it; OCR/text layers are not files.
        """

        found = await _open_citation(citation_id, principal, as_of_date)
        settings = app.state.settings
        if not settings.document_store_root:
            raise api_error(503, "DOCUMENT_STORE_NOT_CONFIGURED")
        root = Path(settings.document_store_root)
        try:
            if found.source_format == "pdf":
                content = await run_in_threadpool(
                    read_immutable_pdf, root, found.original_file_path, found.source_hash,
                    max_bytes=settings.max_upload_bytes,
                )
                digest = found.source_hash
            else:
                content = await run_in_threadpool(
                    read_immutable_source, root, found.source_format,
                    found.source_file_sha256, max_bytes=settings.max_upload_bytes,
                )
                digest = found.source_file_sha256 or ""
        except ValueError as exc:
            raise api_error(503, "CITATION_SOURCE_UNAVAILABLE") from exc
        media_type, disposition = _SOURCE_MEDIA.get(
            found.source_format, ("application/octet-stream", "attachment")
        )
        return Response(
            content=content,
            media_type=media_type,
            headers={
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Content-Disposition": _content_disposition(
                    disposition, found.original_filename, found.source_format
                ),
                "X-Source-Format": found.source_format,
                "X-Source-SHA256": digest,
            },
        )

    @app.get("/api/v1/categories")
    async def categories(
        principal: Annotated[Principal, Depends(require_user)],
    ) -> list[dict[str, object]]:
        pool = getattr(app.state, "db_pool", None)
        if pool is None:
            raise api_error(503, "DATABASE_NOT_CONFIGURED")
        return await list_authorized_categories(pool, principal_id=_principal_id(principal.id))

    # Registered last so every API route above takes precedence over static files.
    if cors_settings.web_root and (Path(cors_settings.web_root) / "index.html").is_file():
        app.mount("/", _WebFiles(directory=cors_settings.web_root, html=True), name="web")
    return app


class _WebFiles(StaticFiles):
    """Built web app: hashed assets are cached for a year, everything else revalidates."""

    def file_response(self, full_path: Any, stat_result: Any, scope: Any,
                      status_code: int = 200) -> Response:
        response = super().file_response(full_path, stat_result, scope, status_code)
        hashed = Path(str(full_path)).parent.name == "assets"
        response.headers["Cache-Control"] = (
            "public, max-age=31536000, immutable" if hashed else "no-cache"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response


_SOURCE_MEDIA = {
    "pdf": ("application/pdf", "inline"),
    "docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "attachment",
    ),
    "doc": ("application/msword", "attachment"),
    "txt": ("text/plain", "attachment"),
}


def _content_disposition(disposition: str, filename: str, source_format: str) -> str:
    """RFC 6266 header with an ASCII fallback and the original (UTF-8) file name."""

    import re
    from urllib.parse import quote

    name = Path(filename.replace("\\", "/")).name.strip() or f"document.{source_format}"
    name = re.sub(r"[\x00-\x1f\x7f\"]", "_", name)
    if not name.lower().endswith(f".{source_format}"):
        name = f"{name}.{source_format}"
    ascii_name = re.sub(r"[^A-Za-z0-9._\-]+", "_", name).strip("_") or f"document.{source_format}"
    return f"{disposition}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"


def _principal_id(value: str) -> UUID:
    try:
        return UUID(value)
    except (TypeError, ValueError) as exc:
        raise api_error(401, "INVALID_PRINCIPAL") from exc


def _with_preferences(
    request: TurnRequest, preferences: PreferencesRequest | None
) -> TurnRequest:
    """Apply the user's opt-in default categories to an unscoped (all authorized) turn."""

    if (
        preferences is None
        or not preferences.enabled
        or not preferences.default_category_ids
        or request.scope.scope_mode != ScopeMode.ALL_AUTHORIZED
        or request.scope.category_ids
    ):
        return request
    scope = request.scope.model_copy(
        update={
            "scope_mode": ScopeMode.SELECTED,
            "category_ids": list(preferences.default_category_ids),
        }
    )
    return request.model_copy(update={"scope": scope})


def _session_query(request: TurnRequest) -> AnalyzeRequest:
    return AnalyzeRequest(
        question=request.question,
        scope=request.scope,
        facts=request.facts,
        deep_analysis=request.deep_analysis,
    )


async def _validate_replay_evidence(
    app: FastAPI, principal_id: str, events: list[StoredEvent]
) -> None:
    pool = getattr(app.state, "db_pool", None)
    if pool is None:
        if not app.state.settings.dev_allow_in_memory_store:
            raise api_error(503, "DATABASE_UNAVAILABLE")
        return
    checked_files: set[str] = set()
    try:
        async with asyncio.timeout(5):
            for event in events:
                if event.event != "evidence_verified":
                    continue
                raw_evidence = event.data.get("evidence", [])
                if not isinstance(raw_evidence, list):
                    raise ValueError("INVALID_REPLAY")
                items = [EvidenceRef.model_validate(raw) for raw in raw_evidence]
                # One principal-scoped query per as_of_date instead of one per item.
                by_date: dict[date, list[str]] = {}
                for evidence in items:
                    by_date.setdefault(evidence.as_of_date, []).append(evidence.evidence_id)
                current_by_date = {
                    as_of: await get_authorized_citations(
                        pool, principal_id=_principal_id(principal_id),
                        citation_ids=ids, as_of_date=as_of,
                    )
                    for as_of, ids in by_date.items()
                }
                for evidence in items:
                    current = current_by_date[evidence.as_of_date].get(evidence.evidence_id)
                    if current is None:
                        raise ValueError("CITATION_INVALID")
                    source = current.response.evidence
                    if any(
                        getattr(source, field) != getattr(evidence, field)
                        for field in (
                            "document_id", "document_version_id", "node_id",
                            "source_hash", "quote_exact", "page", "document_number", "title",
                        )
                    ):
                        raise ValueError("CITATION_INVALID")
                    if current.source_hash not in checked_files:
                        store_root = app.state.settings.document_store_root
                        if not store_root:
                            raise ValueError("PDF_STORAGE_CONFLICT")
                        await asyncio.to_thread(
                            verify_immutable_pdf, Path(store_root),
                            current.original_file_path, current.source_hash,
                            max_bytes=app.state.settings.max_upload_bytes,
                        )
                        checked_files.add(current.source_hash)
    except ValueError as exc:
        raise api_error(403, "CITATION_INVALID") from exc
    except TimeoutError as exc:
        # A slow disk or database is not evidence that a citation is invalid.
        raise api_error(504, "QUERY_TIMEOUT") from exc


async def _build_search(app: FastAPI, settings: Settings) -> Any:
    if settings.dev_allow_in_memory_store:
        app.state.search_service = None
        return _development_search
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required")
    pool = await create_pool(settings.database_url)
    try:
        async with pool.acquire() as connection:
            await apply_migrations(connection)
    except BaseException:
        await pool.close()
        raise
    app.state.db_pool = pool
    try:
        app.state.search_normalization = await normalization_status(pool)
        if app.state.search_normalization["stale_nodes"]:
            logger.warning(
                "search normalization is stale: %s node(s) at %s",
                app.state.search_normalization["stale_nodes"],
                app.state.search_normalization["current_revision"],
            )
    except Exception:  # a status probe must not block startup
        app.state.search_normalization = None
        logger.warning("search normalization status unavailable", exc_info=True)
    service = SearchService(
        pool,
        statement_timeout_ms=settings.search_statement_timeout_ms,
        max_page_depth=settings.search_max_page_depth,
        count_cap=settings.search_count_cap,
    )
    app.state.search_service = service
    return service.search_clauses


async def _development_search(
    *,
    principal_id: UUID,
    scope: object,
    query: str,
    limit: int = 12,
) -> list[EvidenceRef]:
    """Return no evidence by default; tests inject their ACL-controlled store."""

    return []


def _sse(event: str, data: dict[str, object]) -> str:
    import json

    sequence = data.get("event_sequence", 0)
    query_id = data.get("query_id", "")
    run_id = data.get("run_id", "")
    event_id = f"{query_id}:{run_id}:{sequence}"
    return f"id: {event_id}\nevent: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _build_turn_events(result: Any) -> list[StoredEvent]:
    base = {
        "query_id": result.query_id,
        "run_id": result.run_id,
        "facts_revision": result.facts_revision,
        "snapshot_revision": result.snapshot_revision,
    }
    events: list[StoredEvent] = [
        StoredEvent("retrieval_started", {**base, "event_sequence": 1}),
        StoredEvent(
            "evidence_verified",
            {
                **base,
                "event_sequence": 2,
                "evidence": [item.model_dump(mode="json") for item in result.evidence],
            },
        ),
        StoredEvent(
            "evidence_complete",
            {**base, "event_sequence": 3, "evidence_count": len(result.evidence)},
        ),
    ]
    events.append(
        StoredEvent(
            "analysis_ready",
            {
                **base,
                "event_sequence": 4,
                **result.model_dump(
                    mode="json",
                    include={
                        "effective_mode", "status", "source_scope", "evidence_groups",
                        "claims", "missing_information", "suggestions", "coverage_checks",
                        "answer_generated", "ai_selection_applied", "external_ai_used",
                        "ai_limited", "explanation_unavailable",
                        "disclaimer", "documents", "answer",
                    },
                ),
            },
        )
    )
    sequence = 5
    if result.explanation_unavailable:
        events.append(
            StoredEvent(
                "explanation_unavailable",
                {
                    **base,
                    "event_sequence": sequence,
                    "message": (
                        "Giải thích tạm thời không khả dụng. "
                        "Các căn cứ đã được kiểm tra nguồn."
                    ),
                },
            )
        )
        sequence += 1
    events.append(
        StoredEvent(
            "answer_complete",
            {**base, "event_sequence": sequence, "status": result.status.value},
        )
    )
    return events


def _event_sequence(data: dict[str, object]) -> int:
    value = data.get("event_sequence", 0)
    return value if isinstance(value, int) else 0


def _parse_last_event_sequence(
    value: str | None, *, query_id: str, run_id: str
) -> int | None:
    if value is None:
        return None
    parts = value.split(":")
    if len(parts) != 3:
        raise api_error(400, "INVALID_LAST_EVENT_ID")
    try:
        sequence = int(parts[2])
    except ValueError as exc:
        raise api_error(400, "INVALID_LAST_EVENT_ID") from exc
    if sequence < 0:
        raise api_error(400, "INVALID_LAST_EVENT_ID")
    if parts[:2] != [query_id, run_id]:
        raise api_error(409, "RUN_MISMATCH")
    return sequence


app = create_app()
