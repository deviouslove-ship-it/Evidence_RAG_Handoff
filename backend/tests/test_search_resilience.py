"""Search deadlines apply to acquisition, counts and audit lock contention."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

from app.storage.search import SearchQueryError, SearchService


class WaitingPool:
    @asynccontextmanager
    async def acquire(self):
        await asyncio.Event().wait()
        yield None


@pytest.mark.parametrize("method", ["search_documents", "search_approximate"])
async def test_pool_exhaustion_has_a_search_deadline(method: str) -> None:
    service = SearchService(WaitingPool(), statement_timeout_ms=100, audit_enabled=False)
    with pytest.raises(SearchQueryError) as raised:
        await asyncio.wait_for(
            getattr(service, method)(principal_id=uuid4(), raw_query="báo cáo"),
            timeout=0.5,
        )
    assert raised.value.code == "SEARCH_TIMEOUT"
    assert service._search_slots._value == 4


async def test_overload_is_rejected_instead_of_queuing_unbounded_searches() -> None:
    service = SearchService(WaitingPool(), audit_enabled=False)
    for _ in range(4):
        await service._search_slots.acquire()
    with pytest.raises(SearchQueryError) as raised:
        await service.search_documents(principal_id=uuid4(), raw_query="báo cáo")
    assert raised.value.code == "SEARCH_BUSY"
    assert raised.value.status_code == 429


async def test_cancelled_pool_wait_releases_its_search_slot() -> None:
    service = SearchService(WaitingPool(), audit_enabled=False)
    pending = asyncio.create_task(service.search_documents(
        principal_id=uuid4(), raw_query="báo cáo",
    ))
    await asyncio.sleep(0.02)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert service._search_slots._value == 4
