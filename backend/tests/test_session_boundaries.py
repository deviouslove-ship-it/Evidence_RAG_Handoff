import asyncio
import json
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app

HEADERS = {"X-Principal-Id": "00000000-0000-0000-0000-000000000001", "X-Roles": "USER"}


def _start_turn(client: TestClient) -> tuple[str, str, dict[str, object]]:
    session = client.post("/api/v1/agent/sessions", headers=HEADERS, json={}).json()
    response = client.post(
        f"/api/v1/agent/sessions/{session['session_id']}/turns",
        headers={**HEADERS, "Idempotency-Key": "boundary-test"},
        json={
            "question": "Fixture kiểm tra luồng sự kiện",
            "scope": {"scope_mode": "ALL_AUTHORIZED", "as_of_date": "2026-10-22"},
        },
    )
    assert response.status_code == 200
    first_event = next(line[6:] for line in response.text.splitlines() if line.startswith("data: "))
    return session["session_id"], response.headers["X-Turn-Id"], json.loads(first_event)


@pytest.mark.parametrize("changed", ["query_id", "run_id"])
def test_replay_rejects_last_event_from_another_run(changed: str) -> None:
    with TestClient(create_app()) as client:
        session_id, turn_id, event = _start_turn(client)
        event[changed] = "unrelated_identity"
        response = client.get(
            f"/api/v1/agent/sessions/{session_id}/turns/{turn_id}/events",
            headers={
                **HEADERS,
                "Last-Event-ID": f"{event['query_id']}:{event['run_id']}:1",
            },
        )
    assert response.status_code == 409
    assert response.json()["code"] == "RUN_MISMATCH"


@pytest.mark.parametrize("event_id", ["1", "run:1", "query:run:-1", "query:run:bad"])
def test_replay_rejects_malformed_event_ids(event_id: str) -> None:
    with TestClient(create_app()) as client:
        session_id, turn_id, _ = _start_turn(client)
        response = client.get(
            f"/api/v1/agent/sessions/{session_id}/turns/{turn_id}/events",
            headers={**HEADERS, "Last-Event-ID": event_id},
        )
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_LAST_EVENT_ID"


@pytest.mark.parametrize("action", ["events", "cancel", "retry"])
def test_missing_turn_returns_not_found_in_live_session(action: str) -> None:
    with TestClient(create_app()) as client:
        session_id = client.post("/api/v1/agent/sessions", headers=HEADERS, json={}).json()[
            "session_id"
        ]
        path = f"/api/v1/agent/sessions/{session_id}/turns/missing/{action}"
        response = client.get(path, headers=HEADERS) if action == "events" else client.post(
            path, headers=HEADERS
        )
    assert response.status_code == 404
    assert response.json()["code"] == "TURN_NOT_FOUND"


def test_missing_memory_item_returns_not_found_in_live_session() -> None:
    with TestClient(create_app()) as client:
        session_id = client.post("/api/v1/agent/sessions", headers=HEADERS, json={}).json()[
            "session_id"
        ]
        response = client.delete(
            f"/api/v1/memory/{uuid4()}", headers=HEADERS, params={"session_id": session_id}
        )
    assert response.status_code == 404
    assert response.json()["code"] == "MEMORY_ITEM_NOT_FOUND"


def test_deleting_message_invalidates_derived_replay_and_retry() -> None:
    app = create_app()
    with TestClient(app) as client:
        session_id, turn_id, _ = _start_turn(client)
        item_id = client.get(
            "/api/v1/memory", headers=HEADERS, params={"session_id": session_id}
        ).json()["items"][0]["id"]
        assert client.delete(
            f"/api/v1/memory/{item_id}", headers=HEADERS, params={"session_id": session_id}
        ).status_code == 204
        for action in ("events", "retry"):
            path = f"/api/v1/agent/sessions/{session_id}/turns/{turn_id}/{action}"
            response = client.get(path, headers=HEADERS) if action == "events" else client.post(
                path, headers={**HEADERS, "Idempotency-Key": "retry-deleted"}
            )
            assert response.status_code == 404
        session = app.state.memory.get_session(UUID(session_id), HEADERS["X-Principal-Id"])
        assert session.events == []
        assert session.facts == []


def test_retry_requires_a_key_and_deduplicates_the_same_key() -> None:
    with TestClient(create_app()) as client:
        session_id, turn_id, original = _start_turn(client)
        path = f"/api/v1/agent/sessions/{session_id}/turns/{turn_id}/retry"
        assert client.post(path, headers=HEADERS).status_code == 400
        first = client.post(path, headers={**HEADERS, "Idempotency-Key": "one-retry"})
        repeated = client.post(path, headers={**HEADERS, "Idempotency-Key": "one-retry"})
        assert first.status_code == repeated.status_code == 200
        assert first.json()["run_id"] == repeated.json()["run_id"]
        assert first.json()["run_id"] != original["run_id"]


@pytest.mark.parametrize("action", ["cancel", "delete_session", "delete_item"])
async def test_inflight_turn_cannot_publish_after_cancel_or_delete(action: str) -> None:
    app = create_app()
    async with app.router.lifespan_context(app):
        entered, release = asyncio.Event(), asyncio.Event()
        execute = app.state.pipeline.execute

        async def paused_execute(*args: object, **kwargs: object) -> object:
            entered.set()
            await release.wait()
            return await execute(*args, **kwargs)

        app.state.pipeline.execute = paused_execute
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            session_id = (await client.post(
                "/api/v1/agent/sessions", headers=HEADERS, json={}
            )).json()["session_id"]
            path = f"/api/v1/agent/sessions/{session_id}/turns"
            payload = {
                "question": "Fixture riêng tư đang xử lý",
                "scope": {"scope_mode": "ALL_AUTHORIZED", "as_of_date": "2026-10-22"},
            }
            headers = {**HEADERS, "Idempotency-Key": "inflight"}
            pending = asyncio.create_task(client.post(path, headers=headers, json=payload))
            try:
                await asyncio.wait_for(entered.wait(), timeout=2)
                duplicate = await client.post(path, headers=headers, json=payload)
                turn_id = duplicate.headers["X-Turn-Id"]
                if action == "cancel":
                    stopped = await client.post(f"{path}/{turn_id}/cancel", headers=HEADERS)
                elif action == "delete_session":
                    stopped = await client.delete(
                        f"/api/v1/agent/sessions/{session_id}", headers=HEADERS
                    )
                else:
                    memory = (await client.get(
                        "/api/v1/memory", headers=HEADERS, params={"session_id": session_id}
                    )).json()
                    stopped = await client.delete(
                        f"/api/v1/memory/{memory['items'][0]['id']}",
                        headers=HEADERS, params={"session_id": session_id},
                    )
                assert stopped.status_code in {200, 204}
            finally:
                release.set()
            response = await asyncio.wait_for(pending, timeout=2)
            assert "event: answer_complete" not in response.text
            assert "Fixture riêng tư" not in response.text
            if action == "cancel":
                assert "event: turn_cancelled" in response.text
