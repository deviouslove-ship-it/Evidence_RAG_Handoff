from uuid import UUID

import pytest
from fastapi.testclient import TestClient


@pytest.mark.parametrize("target", ["session", "memory", "item"])
def test_delete_endpoints_have_no_response_body(target: str) -> None:
    from app.main import create_app

    app = create_app()
    headers = {"X-Principal-Id": "00000000-0000-0000-0000-000000000001", "X-Roles": "USER"}
    with TestClient(app) as client:
        session_id = client.post("/api/v1/agent/sessions", headers=headers, json={}).json()[
            "session_id"
        ]
        if target == "session":
            path = f"/api/v1/agent/sessions/{session_id}"
            params = {}
        else:
            path = "/api/v1/memory"
            params = {"session_id": session_id}
            if target == "item":
                item_id = app.state.memory.append_message(
                    UUID(session_id), headers["X-Principal-Id"], "Nội dung riêng tư"
                )
                path += f"/{item_id}"
        response = client.delete(path, headers=headers, params=params)
        assert response.status_code == 204
        assert response.content == b""
        openapi_path = {
            "session": "/api/v1/agent/sessions/{session_id}",
            "memory": "/api/v1/memory",
            "item": "/api/v1/memory/{item_id}",
        }[target]
        schema = client.get("/openapi.json").json()
        assert "content" not in schema["paths"][openapi_path]["delete"]["responses"]["204"]


def test_missing_authentication_has_a_user_message() -> None:
    from app.main import create_app

    with TestClient(create_app()) as client:
        response = client.post("/api/v1/agent/sessions", json={})
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"
    assert "đăng nhập" in response.json()["message"]


def test_invalid_query_uses_the_standard_error_contract() -> None:
    from app.main import create_app

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/query/evidence",
            headers={
                "X-Principal-Id": "00000000-0000-0000-0000-000000000001",
                "X-Roles": "USER",
            },
            json={"question": "Thiếu phạm vi"},
        )
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_REQUEST"
    assert response.json()["trace_id"].startswith("trace_")
    assert "detail" not in response.json()


def test_openapi_documents_actual_stream_and_error_contracts() -> None:
    from app.main import create_app

    schema = create_app().openapi()
    paths = schema["paths"]
    stream = paths["/api/v1/agent/sessions/{session_id}/turns"]["post"]
    assert "text/event-stream" in stream["responses"]["200"]["content"]
    invalid = paths["/api/v1/query/evidence"]["post"]["responses"]["422"]
    assert invalid["content"]["application/json"]["schema"]["$ref"].endswith("/ApiError")
    assert paths["/health"]["get"]["security"] == []
