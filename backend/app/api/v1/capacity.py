"""Admission control: reject overload instead of queuing unlimited CPU work."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from .errors import api_error


@asynccontextmanager
async def operation_slot(slots: asyncio.Semaphore, error_code: str) -> AsyncIterator[None]:
    try:
        await asyncio.wait_for(slots.acquire(), timeout=0.1)
    except TimeoutError as exc:
        raise api_error(429, error_code) from exc
    try:
        yield
    finally:
        slots.release()
