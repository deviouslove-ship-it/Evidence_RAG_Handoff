import json
from dataclasses import replace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

PRINCIPAL = "00000000-0000-0000-0000-000000000001"


@pytest.mark.parametrize("path,role", [
    ("/api/v1/categories", "USER"), ("/api/v1/admin/categories", "SYS_ADMIN"),
    ("/api/v1/admin/users", "SYS_ADMIN"),
])
def test_unconfigured_lists_report_configuration_error(path: str, role: str) -> None:
    with TestClient(create_app()) as client:
        response = client.get(path, headers={"X-Principal-Id": PRINCIPAL, "X-Roles": role})
    assert response.status_code == 503
    assert response.json()["code"] == "DATABASE_NOT_CONFIGURED"


def test_query_contract_returns_insufficient_without_evidence() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/query/evidence",
            headers={"X-Principal-Id": PRINCIPAL, "X-Roles": "USER"},
            json={
                "question": "Điều kiện áp dụng là gì?",
                "scope": {
                    "scope_mode": "ALL_AUTHORIZED",
                    "category_ids": [],
                    "document_types": [],
                    "as_of_date": "2026-01-01",
                },
                "facts": [],
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "insufficient"
    assert body["answer_generated"] is False
    assert body["explanation_unavailable"] is True
    assert body["evidence"] == []


def test_user_route_rejects_admin_without_query_permission() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/query/evidence",
            headers={"X-Principal-Id": PRINCIPAL, "X-Roles": "SYS_ADMIN"},
            json={
                "question": "Điều kiện áp dụng là gì?",
                "scope": {
                    "scope_mode": "ALL_AUTHORIZED",
                    "category_ids": [],
                    "document_types": [],
                    "as_of_date": "2026-01-01",
                },
                "facts": [],
            },
        )
    assert response.status_code == 403
    error = response.json()
    assert error["code"] == "QUERY_REQUIRED"
    assert error["trace_id"].startswith("trace_")


def test_admin_route_requires_admin_role() -> None:
    app = create_app()
    with TestClient(app) as client:
        denied = client.get(
            "/api/v1/admin/model-registry",
            headers={"X-Principal-Id": PRINCIPAL, "X-Roles": "USER"},
        )
        allowed = client.get(
            "/api/v1/admin/model-registry",
            headers={"X-Principal-Id": PRINCIPAL, "X-Roles": "SYS_ADMIN"},
        )
    assert denied.status_code == 403
    assert denied.json()["code"] == "ADMIN_REQUIRED"
    assert allowed.status_code == 503
    assert allowed.json()["code"] == "DATABASE_NOT_CONFIGURED"


def test_deleting_a_session_fact_is_owner_scoped_and_invalidates_replay() -> None:
    app = create_app()
    headers = {"X-Principal-Id": PRINCIPAL, "X-Roles": "USER"}
    with TestClient(app) as client:
        session = client.post("/api/v1/agent/sessions", headers=headers, json={}).json()
        session_id = session["session_id"]
        turn = client.post(
            f"/api/v1/agent/sessions/{session_id}/turns",
            headers={**headers, "Idempotency-Key": "fact-delete"},
            json={
                "question": "Trường hợp này thế nào?",
                "scope": {"scope_mode": "ALL_AUTHORIZED", "as_of_date": "2026-10-27"},
                "facts": [{"key": "role", "value": "công chức", "status": "user_confirmed"}],
            },
        )
        assert turn.status_code == 200
        turn_id = turn.headers["X-Turn-Id"]
        other = client.delete(
            f"/api/v1/agent/sessions/{session_id}/facts", params={"key": "role"},
            headers={"X-Principal-Id": "00000000-0000-0000-0000-000000000002", "X-Roles": "USER"},
        )
        assert other.status_code == 410
        deleted = client.delete(
            f"/api/v1/agent/sessions/{session_id}/facts", params={"key": "role"}, headers=headers,
        )
        assert deleted.status_code == 204
        assert not app.state.memory.get_context(UUID(session_id), PRINCIPAL).facts
        replay = client.get(
            f"/api/v1/agent/sessions/{session_id}/turns/{turn_id}/events", headers=headers,
        )
        assert replay.status_code == 404


def test_empty_default_category_preference_is_not_reported_as_enabled() -> None:
    app = create_app()
    headers = {"X-Principal-Id": PRINCIPAL, "X-Roles": "USER"}
    with TestClient(app) as client:
        session = client.post("/api/v1/agent/sessions", headers=headers, json={}).json()
        session_id = session["session_id"]
        response = client.put(
            "/api/v1/memory/preferences", params={"session_id": session_id}, headers=headers,
            json={"enabled": True, "default_category_ids": [], "default_as_of_date": None},
        )
        assert response.status_code == 422
        assert response.json()["code"] == "CATEGORY_REQUIRED"


def test_unused_default_date_preference_is_rejected() -> None:
    app = create_app()
    headers = {"X-Principal-Id": PRINCIPAL, "X-Roles": "USER"}
    with TestClient(app) as client:
        session = client.post("/api/v1/agent/sessions", headers=headers, json={}).json()
        session_id = session["session_id"]
        date_preference = client.put(
            "/api/v1/memory/preferences", params={"session_id": session_id}, headers=headers,
            json={"enabled": False, "default_category_ids": [], "default_as_of_date": "2026-01-01"},
        )
        assert date_preference.status_code == 422
        assert date_preference.json()["code"] == "PREFERENCE_DATE_UNAVAILABLE"


def test_retention_policy_approval_does_not_pretend_persistence_exists() -> None:
    app = create_app()
    with TestClient(app) as client:
        app.state.settings = replace(app.state.settings, retention_approved=True)
        response = client.post(
            "/api/v1/agent/sessions",
            headers={"X-Principal-Id": PRINCIPAL, "X-Roles": "USER"},
            json={"incognito": False},
        )
    assert response.status_code == 409
    assert response.json()["code"] == "RETENTION_UNAVAILABLE"


def test_session_is_incognito_by_default_and_sse_has_run_identity() -> None:
    app = create_app()
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/agent/sessions",
            headers={"X-Principal-Id": PRINCIPAL, "X-Roles": "USER"},
            json={"incognito": True},
        )
        assert created.status_code == 201
        session = created.json()
        assert session["persistence_state"] == "ephemeral"
        fetched = client.get(
            f"/api/v1/agent/sessions/{session['session_id']}",
            headers={"X-Principal-Id": PRINCIPAL, "X-Roles": "USER"},
        )
        assert fetched.status_code == 200
        assert fetched.json()["memory_revision"] == session["memory_revision"]
        response = client.post(
            f"/api/v1/agent/sessions/{session['session_id']}/turns",
            headers={
                "X-Principal-Id": PRINCIPAL,
                "X-Roles": "USER",
                "Idempotency-Key": "test-key",
            },
            json={
                "question": "Tình huống cần tra cứu?",
                "scope": {
                    "scope_mode": "ALL_AUTHORIZED",
                    "category_ids": [],
                    "document_types": [],
                    "as_of_date": "2026-01-01",
                },
                "facts": [],
            },
        )
    assert response.status_code == 200
    assert "run_id" in response.text
    assert "query_id" in response.text
    assert "event: evidence_verified" in response.text
    assert "Cache-Control" in response.headers
    assert "no-store" in response.headers["Cache-Control"]
    assert "trace_id" not in response.text


def test_turn_idempotency_replays_same_run_and_does_not_duplicate_message() -> None:
    app = create_app()
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/agent/sessions",
            headers={"X-Principal-Id": PRINCIPAL, "X-Roles": "USER"},
            json={"incognito": True},
        )
        session_id = created.json()["session_id"]
        payload = {
            "question": "Câu hỏi idempotent",
            "scope": {
                "scope_mode": "ALL_AUTHORIZED",
                "category_ids": [],
                "document_types": [],
                "as_of_date": "2026-01-01",
            },
            "facts": [],
        }
        headers = {
            "X-Principal-Id": PRINCIPAL,
            "X-Roles": "USER",
            "Idempotency-Key": "same-turn",
        }
        first = client.post(
            f"/api/v1/agent/sessions/{session_id}/turns",
            headers=headers,
            json=payload,
        )
        second = client.post(
            f"/api/v1/agent/sessions/{session_id}/turns",
            headers=headers,
            json=payload,
        )
        memory = client.get(
            "/api/v1/memory",
            params={"session_id": session_id},
            headers={"X-Principal-Id": PRINCIPAL, "X-Roles": "USER"},
        )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.text == second.text
    assert first.headers["X-Turn-Id"] == second.headers["X-Turn-Id"]
    assert len(memory.json()["items"]) == 1


def test_turn_idempotency_rejects_changed_request() -> None:
    app = create_app()
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/agent/sessions",
            headers={"X-Principal-Id": PRINCIPAL, "X-Roles": "USER"},
            json={"incognito": True},
        )
        session_id = created.json()["session_id"]
        headers = {
            "X-Principal-Id": PRINCIPAL,
            "X-Roles": "USER",
            "Idempotency-Key": "conflicting-turn",
        }
        base_payload = {
            "question": "Câu hỏi ban đầu",
            "scope": {
                "scope_mode": "ALL_AUTHORIZED",
                "category_ids": [],
                "document_types": [],
                "as_of_date": "2026-01-01",
            },
            "facts": [],
        }
        first = client.post(
            f"/api/v1/agent/sessions/{session_id}/turns",
            headers=headers,
            json=base_payload,
        )
        changed = client.post(
            f"/api/v1/agent/sessions/{session_id}/turns",
            headers=headers,
            json={**base_payload, "question": "Câu hỏi đã đổi"},
        )
    assert first.status_code == 200
    assert changed.status_code == 409
    assert changed.json()["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_memory_item_delete_is_owner_scoped() -> None:
    app = create_app()
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/agent/sessions",
            headers={"X-Principal-Id": PRINCIPAL, "X-Roles": "USER"},
            json={"incognito": True},
        )
        session_id = created.json()["session_id"]
        turn = client.post(
            f"/api/v1/agent/sessions/{session_id}/turns",
            headers={
                "X-Principal-Id": PRINCIPAL,
                "X-Roles": "USER",
                "Idempotency-Key": "memory-test",
            },
            json={
                "question": "Câu hỏi cần xóa khỏi bộ nhớ",
                "scope": {
                    "scope_mode": "ALL_AUTHORIZED",
                    "category_ids": [],
                    "document_types": [],
                    "as_of_date": "2026-01-01",
                },
                "facts": [],
            },
        )
        assert turn.status_code == 200
        memory = client.get(
            "/api/v1/memory",
            params={"session_id": session_id},
            headers={"X-Principal-Id": PRINCIPAL, "X-Roles": "USER"},
        )
        assert memory.status_code == 200
        item_id = memory.json()["items"][0]["id"]
        deleted = client.delete(
            f"/api/v1/memory/{item_id}",
            params={"session_id": session_id},
            headers={"X-Principal-Id": PRINCIPAL, "X-Roles": "USER"},
        )
        remaining = client.get(
            "/api/v1/memory",
            params={"session_id": session_id},
            headers={"X-Principal-Id": PRINCIPAL, "X-Roles": "USER"},
        )
    assert deleted.status_code == 204
    assert remaining.json()["items"] == []


def test_sse_reconnect_replays_only_events_after_last_event_id() -> None:
    app = create_app()
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/agent/sessions",
            headers={"X-Principal-Id": PRINCIPAL, "X-Roles": "USER"},
            json={"incognito": True},
        )
        session_id = created.json()["session_id"]
        turn = client.post(
            f"/api/v1/agent/sessions/{session_id}/turns",
            headers={
                "X-Principal-Id": PRINCIPAL,
                "X-Roles": "USER",
                "Idempotency-Key": "replay-turn",
            },
            json={
                "question": "Câu hỏi cần replay",
                "scope": {
                    "scope_mode": "ALL_AUTHORIZED",
                    "category_ids": [],
                    "document_types": [],
                    "as_of_date": "2026-01-01",
                },
                "facts": [],
            },
        )
        assert turn.status_code == 200
        turn_id = turn.headers["X-Turn-Id"]
        event = json.loads(
            next(line[6:] for line in turn.text.splitlines() if line.startswith("data: "))
        )
        run_id = event["run_id"]
        replay = client.get(
            f"/api/v1/agent/sessions/{session_id}/turns/{turn_id}/events",
            params={"run_id": run_id},
            headers={
                "X-Principal-Id": PRINCIPAL,
                "X-Roles": "USER",
                "Last-Event-ID": f"{event['query_id']}:{run_id}:1",
            },
        )
    assert replay.status_code == 200
    assert "event: retrieval_started" not in replay.text
    assert "event: evidence_verified" in replay.text
    replayed = [
        json.loads(line[6:]) for line in replay.text.splitlines() if line.startswith("data: ")
    ]
    assert [item["event_sequence"] for item in replayed] == [2, 3, 4, 5, 6]
