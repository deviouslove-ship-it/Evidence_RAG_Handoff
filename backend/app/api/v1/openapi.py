"""OpenAPI contract extension for the fixed query and agent APIs."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from ...schemas import ApiError


def configure_openapi(app: FastAPI) -> None:
    def custom_openapi() -> dict[str, object]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        schema["components"] = schema.get("components", {})
        schema["components"]["securitySchemes"] = {
            "bearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
            }
        }
        schema["security"] = [{"bearerAuth": []}]
        schema["components"].setdefault("schemas", {})["ApiError"] = ApiError.model_json_schema()
        error = {
            "description": "Lỗi có mã và trace_id; không trả dữ liệu nội bộ.",
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ApiError"}}},
        }
        for path, operations in schema["paths"].items():
            for method, operation in operations.items():
                if method not in {"get", "post", "put", "patch", "delete", "options", "head"}:
                    continue
                responses = operation.setdefault("responses", {})
                responses["default"] = error
                if "422" in responses:
                    responses["422"] = error
                if path in {"/health", "/api/v1/system/mode", "/api/v1/auth/login"}:
                    operation["security"] = []
                if path.endswith("/turns") or path.endswith("/events"):
                    responses["200"] = {
                        "description": "Luồng SSE có định danh query/run và event_sequence.",
                        "content": {"text/event-stream": {"schema": {"type": "string"}}},
                    }
        schema["x-contract"] = {
            "scope_modes": ["SELECTED", "ALL_AUTHORIZED"],
            "sse_identity": [
                "query_id",
                "run_id",
                "facts_revision",
                "snapshot_revision",
                "event_sequence",
            ],
            "llm_attempt_budget": 2,
            "errors": [
                "REMOTE_AI_DENIED",
                "RETENTION_NOT_APPROVED",
                "SESSION_EXPIRED",
                "MODEL_NOT_CONFIGURED",
            ],
        }
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
