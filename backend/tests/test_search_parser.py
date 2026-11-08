"""Pure unit tests for Search v1 query parsing, verification and snippets."""

from __future__ import annotations

from datetime import date

from app.schemas import SearchMatchType
from app.storage.search import (
    SearchHit,
    SearchQueryError,
    SearchService,
    _build_snippet,
    _find_phrase_span,
    _normalize_content,
    _verify_phrase,
    parse_search_query,
)


def _codes(raw: str, mode: str = "keywords") -> str:
    try:
        parse_search_query(raw, mode)
    except SearchQueryError as exc:
        return exc.code
    raise AssertionError("expected SearchQueryError")


def test_quoted_phrase_is_detected_in_auto_mode() -> None:
    parsed = parse_search_query('Tìm "báo cáo định kỳ và thường xuyên" giúp tôi')
    assert parsed.mode == "phrase"
    assert parsed.phrase == "báo cáo định kỳ và thường xuyên"
    assert parsed.phrase_normalized == "báo cáo định kỳ và thường xuyên"


def test_keywords_outside_the_quoted_phrase_are_preserved() -> None:
    parsed = parse_search_query('"báo cáo" tổng hợp')
    assert parsed.terms == ("báo", "cáo", "tổng", "hợp")


def test_plain_keywords_mode_ignores_quotes() -> None:
    parsed = parse_search_query('"báo cáo định kỳ"', mode="keywords")
    assert parsed.mode == "keywords"
    assert parsed.phrase is None
    assert parsed.terms == ("báo", "cáo", "định", "kỳ")


def test_phrase_mode_without_quotes_uses_whole_query() -> None:
    parsed = parse_search_query("báo cáo định kỳ", mode="phrase")
    assert parsed.mode == "phrase"
    assert parsed.phrase == "báo cáo định kỳ"


def test_empty_and_long_queries_are_rejected() -> None:
    assert _codes("   ") == "QUERY_EMPTY"
    assert _codes("a" * 501) == "QUERY_TOO_LONG"
    assert _codes(" ".join(f"từ{i}" for i in range(21))) == "TOO_MANY_TERMS"


def test_auto_mode_rejects_an_overlong_quoted_phrase() -> None:
    assert _codes('"' + "a" * 201 + '"', mode="auto") == "QUERY_TOO_LONG"


def test_special_characters_are_treated_as_separators() -> None:
    parsed = parse_search_query('- | & :* <-> % _ " báo cáo')
    assert parsed.terms == ("báo", "cáo")


def test_legal_document_number_is_detected() -> None:
    parsed = parse_search_query("385/2026/NĐ-CP")
    assert parsed.document_number == "385/2026/nd-cp"
    assert parse_search_query("Nghị định 400/2026/NĐ-CP").document_number == "400/2026/nd-cp"


def test_tone_spelling_variants_normalize_together() -> None:
    assert _normalize_content("hoà Thuý") == _normalize_content("hòa Thúy")
    assert _normalize_content("định kì") == _normalize_content("định kỳ")


def test_phrase_verification_requires_whole_tokens() -> None:
    assert _verify_phrase("các bộ báo cáo định kỳ và thường xuyên", "báo cáo định kỳ")
    assert _verify_phrase("báo cáo viên", "báo cáo")
    assert _verify_phrase("báo cáo, định kỳ", "báo cáo định kỳ")
    assert not _verify_phrase("báo cáo được lập định kỳ", "báo cáo định kỳ")


def test_phrase_span_and_snippet_offsets_are_absolute() -> None:
    original = "Mở đầu. Các bộ thực hiện báo cáo định kỳ và thường xuyên theo quy định."
    span = _find_phrase_span(original, "báo cáo định kỳ và thường xuyên")
    assert span is not None
    snippet, start, highlights = _build_snippet(original, [span])
    assert snippet == original[start:]
    assert highlights
    for highlight in highlights:
        assert original[highlight.start : highlight.end].startswith("báo cáo")
        assert 0 <= highlight.start < highlight.end <= len(original)


def test_phrase_span_is_not_found_when_words_are_separated() -> None:
    assert _find_phrase_span("Báo cáo được lập định kỳ.", "báo cáo định kỳ") is None


def test_service_validates_length_and_page_depth_without_database() -> None:
    service = SearchService(None)
    try:
        service_valid_length = True
        import asyncio

        async def _run() -> None:
            await service.search_documents(
                principal_id=__import__("uuid").uuid4(),
                raw_query="a" * 501,
            )

        asyncio.run(_run())
        service_valid_length = False
    except SearchQueryError as exc:
        assert exc.code == "QUERY_TOO_LONG"
    assert service_valid_length is True

    async def _deep() -> None:
        await service.search_documents(
            principal_id=__import__("uuid").uuid4(),
            raw_query="báo cáo",
            page=1000,
            page_size=50,
        )

    try:
        import asyncio

        asyncio.run(_deep())
        raise AssertionError("expected PAGE_TOO_DEEP")
    except SearchQueryError as exc:
        assert exc.code == "PAGE_TOO_DEEP"
def test_clause_window_pagination_is_applied_per_document() -> None:
    def hit(index: int) -> SearchHit:
        return SearchHit(
            node_id=f"00000000-0000-0000-0000-{index:012d}",
            document_id="00000000-0000-0000-0000-000000000100",
            document_version_id="00000000-0000-0000-0000-000000000101",
            document_number="HU-CAU/2026/ND-CP",
            title="Văn bản HƯ CẤU",
            doc_type="decree",
            issuing_body="Cơ quan HƯ CẤU",
            official_url=None,
            source_hash="a" * 64,
            label=f"Khoản {index}",
            page=index,
            quote_exact=f"báo cáo định kỳ lần {index}",
            text_normalized=f"báo cáo định kỳ lần {index}",
            text_folded=f"bao cao dinh ky lan {index}",
            amendment_state="active",
            score=1.0,
            tier=1,
            match_type=SearchMatchType.EXACT_PHRASE,
        )

    service = SearchService(None)
    parsed = parse_search_query("báo cáo")
    hits = [hit(index) for index in range(1, 7)]
    first, _, _ = service._group_hits(
        hits,
        parsed=parsed,
        page=1,
        page_size=10,
        as_of=date(2026, 10, 31),
        clause_page=2,
        clause_page_size=2,
    )
    assert len(first) == 1
    assert first[0].matched_clause_count == 6
    assert first[0].clause_page == 2
    assert first[0].clause_page_size == 2
    assert first[0].has_more_clauses is True
    assert len(first[0].clauses) == 2

    last, _, _ = service._group_hits(
        hits,
        parsed=parsed,
        page=1,
        page_size=10,
        as_of=date(2026, 10, 31),
        clause_page=3,
        clause_page_size=2,
    )
    assert last[0].has_more_clauses is False
    assert len(last[0].clauses) == 2
