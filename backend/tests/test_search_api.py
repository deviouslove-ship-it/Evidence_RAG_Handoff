"""API contract tests for GET /api/v1/search using an injected service."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas import (
    SearchApproximate,
    SearchClause,
    SearchDocument,
    SearchEmptyReason,
    SearchMatchType,
    SearchQueryInfo,
    SearchResponse,
    SearchTotals,
)
from app.storage.search import SearchQueryError, SearchService, SlidingWindowRateLimiter

PRINCIPAL = "00000000-0000-0000-0000-000000000001"
HEADERS = {"X-Principal-Id": PRINCIPAL, "X-Roles": "USER"}
AS_OF = date(2026, 10, 31)


def _response(query: str = "báo cáo định kỳ") -> SearchResponse:
    clause = SearchClause(
        node_id="00000000-0000-0000-0000-000000000111",
        label="Khoản 1 Điều 5",
        page=12,
        match_type=SearchMatchType.EXACT_PHRASE,
        amendment_state="active",
        amendment_as_of=AS_OF,
        quote_exact="Các bộ báo cáo định kỳ và thường xuyên.",
        snippet="Các bộ báo cáo định kỳ và thường xuyên.",
        snippet_start=0,
        highlights=[{"start": 8, "end": 40}],
        viewer_url="/api/v1/citations/ev_x/pdf?as_of_date=2026-10-31",
        source_hash="a" * 64,
    )
    document = SearchDocument(
        document_id="00000000-0000-0000-0000-000000000222",
        document_version_id="00000000-0000-0000-0000-000000000333",
        document_number="385/2026/NĐ-CP",
        title="Nghị định hư cấu",
        doc_type="decree",
        issuing_body="Bộ Tư pháp",
        official_url="https://example.test/hu-cau",
        matched_clause_count=1,
        clauses=[clause],
    )
    return SearchResponse(
        query=SearchQueryInfo(
            original=query,
            phrase=query,
            mode="phrase",
            normalization_revision="vietnamese-tone-v2",
        ),
        phrase_found=True,
        totals=SearchTotals(documents=1, clauses=1, approximate_matches_hidden=2),
        page=1,
        page_size=20,
        has_more=False,
        effectivity_snapshot_status="stale",
        results=[document],
        approximate=SearchApproximate(collapsed=True, total_clauses=2),
        empty_reason=None,
    )


class FakeSearchService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def search_documents(self, **kwargs: object) -> SearchResponse:
        self.calls.append({"method": "documents", **kwargs})
        return _response(str(kwargs["raw_query"]))

    async def search_approximate(self, **kwargs: object) -> SearchResponse:
        self.calls.append({"method": "approximate", **kwargs})
        response = _response(str(kwargs["raw_query"]))
        response.phrase_found = False
        response.empty_reason = SearchEmptyReason.PHRASE_NOT_FOUND
        return response


class FailingSearchService:
    async def search_documents(self, **kwargs: object) -> SearchResponse:
        raise SearchQueryError("QUERY_TOO_LONG")

    async def search_approximate(self, **kwargs: object) -> SearchResponse:
        raise SearchQueryError("SEARCH_TIMEOUT", 504)


def test_search_returns_contract_and_passes_filters() -> None:
    app = create_app()
    fake = FakeSearchService()
    with TestClient(app) as client:
        app.state.search_service = fake
        response = client.get(
            "/api/v1/search",
            headers=HEADERS,
            params={
                "q": "báo cáo định kỳ",
                "mode": "phrase",
                "category_id": str(UUID(int=7)),
                "doc_type": ["decree", "circular"],
                "issuing_body": "Bộ Tư pháp",
                "as_of_date": "2026-10-31",
                "only_active": "true",
                "page": 2,
                "page_size": 10,
                "clause_page": 2,
                "clause_page_size": 3,
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["totals"]["documents"] == 1
    assert body["results"][0]["clauses"][0]["match_type"] == "exact_phrase"
    assert body["results"][0]["clauses"][0]["highlights"][0] == {"start": 8, "end": 40}
    call = fake.calls[0]
    assert call["raw_query"] == "báo cáo định kỳ"
    assert call["mode"] == "phrase"
    assert call["category_ids"] == [UUID(int=7)]
    assert call["doc_types"] == ["decree", "circular"]
    assert call["page"] == 2
    assert call["page_size"] == 10
    assert call["clause_page"] == 2
    assert call["clause_page_size"] == 3
    assert call["only_active"] is True


def test_search_requires_authentication_and_service() -> None:
    app = create_app()
    with TestClient(app) as client:
        assert client.get("/api/v1/search", params={"q": "x"}).status_code == 401
        response = client.get("/api/v1/search", headers=HEADERS, params={"q": "x"})
    assert response.status_code == 503
    assert response.json()["code"] == "DATABASE_NOT_CONFIGURED"


def test_search_maps_query_errors_and_timeouts() -> None:
    app = create_app()
    with TestClient(app) as client:
        app.state.search_service = FailingSearchService()
        too_long = client.get("/api/v1/search", headers=HEADERS, params={"q": "x"})
        timeout = client.get("/api/v1/search/approximate", headers=HEADERS, params={"q": "x"})
    assert too_long.status_code == 422
    assert too_long.json()["code"] == "QUERY_TOO_LONG"
    assert timeout.status_code == 504
    assert timeout.json()["code"] == "SEARCH_TIMEOUT"


def test_search_rate_limit_is_enforced() -> None:
    app = create_app()
    with TestClient(app) as client:
        app.state.search_service = FakeSearchService()
        app.state.search_rate = SlidingWindowRateLimiter(limit=1)
        first = client.get("/api/v1/search", headers=HEADERS, params={"q": "x"})
        second = client.get("/api/v1/search", headers=HEADERS, params={"q": "x"})
    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["code"] == "RATE_LIMITED"


def test_approximate_endpoint_uses_approximate_method() -> None:
    app = create_app()
    fake = FakeSearchService()
    with TestClient(app) as client:
        app.state.search_service = fake
        response = client.get(
            "/api/v1/search/approximate", headers=HEADERS, params={"q": "báo cáo"}
        )
    assert response.status_code == 200
    assert fake.calls[0]["method"] == "approximate"


def test_page_size_validation_rejects_more_than_fifty() -> None:
    app = create_app()
    with TestClient(app) as client:
        app.state.search_service = FakeSearchService()
        response = client.get(
            "/api/v1/search", headers=HEADERS, params={"q": "x", "page_size": 51}
        )
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_REQUEST"


def test_real_service_maps_query_limits_to_api_codes() -> None:
    app = create_app()
    with TestClient(app) as client:
        app.state.search_service = SearchService(None)
        too_long = client.get("/api/v1/search", headers=HEADERS, params={"q": "a" * 501})
        too_deep = client.get(
            "/api/v1/search",
            headers=HEADERS,
            params={"q": "báo cáo", "page": 1000, "page_size": 50},
        )
    assert too_long.status_code == 422
    assert too_long.json()["code"] == "QUERY_TOO_LONG"
    assert too_deep.status_code == 422
    assert too_deep.json()["code"] == "PAGE_TOO_DEEP"


def test_system_mode_reports_normalization_status() -> None:
    app = create_app()
    with TestClient(app) as client:
        app.state.search_normalization = {
            "current_revision": "vietnamese-tone-v3",
            "total_nodes": 10,
            "stale_nodes": 2,
            "revisions": {"vietnamese-tone-v2": 2, "vietnamese-tone-v3": 8},
        }
        body = client.get("/api/v1/system/mode").json()
    assert body["search_normalization_status"] == "stale"
    assert body["search_normalization_revision"] == "vietnamese-tone-v3"
    assert body["search_normalization_stale_nodes"] == 2