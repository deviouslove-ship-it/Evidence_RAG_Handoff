from app.vietnamese_nlp.legal_citation_parser import (
    parse_legal_references,
    reference_document_number,
)


def test_parses_article_clause_and_point() -> None:
    parsed = parse_legal_references("Theo Điều 5 khoản 2 điểm a của Nghị định 12/2024/NĐ-CP")
    assert parsed.is_unique_local_reference
    reference = parsed.references[0]
    assert reference.article == "điều 5"
    assert reference.clause == "khoản 2"
    assert reference.point == "điểm a"
    assert parsed.document_numbers == ("Nghị định 12/2024/NĐ-CP",)


def test_ambiguous_references_do_not_bypass_analysis() -> None:
    parsed = parse_legal_references("Điều 5 và Điều 6")
    assert not parsed.is_unique_local_reference


def test_reference_document_number_removes_type_prefix_only() -> None:
    assert reference_document_number("Nghị định 381/2026/NĐ-CP") == "381/2026/NĐ-CP"
