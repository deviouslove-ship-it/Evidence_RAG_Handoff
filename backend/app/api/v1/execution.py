"""Bound query concurrency and cancel work on timeout, disconnect or explicit stop."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any, TypeVar
from uuid import uuid4

from fastapi import Request

from .capacity import operation_slot
from .errors import api_error

_Result = TypeVar("_Result")


class QueryExecution:
    def __init__(self) -> None:
        self._slots = asyncio.Semaphore(8)
        self._active: dict[tuple[str, str, str], asyncio.Future[Any]] = {}

    async def run(
        self, request: Request, operation: Callable[[], Awaitable[_Result]], *,
        principal_id: str, timeout: float, session_id: str = "", turn_id: str = "",
        watch_disconnect: bool = True,
        cancelled: Callable[[], bool] | None = None,
    ) -> _Result:
        key = (principal_id, session_id, turn_id or uuid4().hex)
        async with operation_slot(self._slots, "QUERY_BUSY"):
            if cancelled is not None and cancelled():
                raise api_error(409, "TURN_CANCELLED")
            if key in self._active:
                raise api_error(409, "TURN_IN_PROGRESS")
            task = asyncio.ensure_future(operation())
            self._active[key] = task
            disconnected = asyncio.create_task(
                self._watch_disconnect(request) if watch_disconnect else asyncio.Event().wait()
            )
            try:
                done, _ = await asyncio.wait(
                    {task, disconnected}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
                )
                if task in done:
                    return await task
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
                if disconnected in done:
                    raise api_error(408, "REQUEST_CANCELLED")
                raise api_error(504, "QUERY_TIMEOUT")
            except asyncio.CancelledError as exc:
                current = asyncio.current_task()
                if current is not None and current.cancelling():
                    raise
                raise api_error(409, "TURN_CANCELLED") from exc
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await task
                disconnected.cancel()
                with suppress(asyncio.CancelledError):
                    await disconnected
                self._active.pop(key, None)

    @staticmethod
    async def _watch_disconnect(request: Request) -> None:
        # Routes call this after consuming the JSON body.  A blocking receive
        # is cancellable; is_disconnected() opens an AnyIO cancel scope which
        # can swallow cancellation and leave response cleanup waiting forever.
        while True:
            message = await request.receive()
            if message["type"] == "http.disconnect":
                return

    def cancel_turn(self, principal_id: str, session_id: str, turn_id: str) -> None:
        task = self._active.get((principal_id, session_id, turn_id))
        if task is not None:
            task.cancel()

    def cancel_session(self, principal_id: str, session_id: str) -> None:
        for (owner, session, _), task in list(self._active.items()):
            if owner == principal_id and session == session_id:
                task.cancel()

    def cancel_principal(self, principal_id: str) -> None:
        for (owner, _, _), task in list(self._active.items()):
            if owner == principal_id:
                task.cancel()

    async def close(self) -> None:
        tasks = list(self._active.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
