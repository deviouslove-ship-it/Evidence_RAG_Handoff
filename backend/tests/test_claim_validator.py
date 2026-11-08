from app.evidence.validators import validate_claim


def test_numeric_mismatch_is_not_supported() -> None:
    result = validate_claim(
        "Thời hạn là 30 ngày.",
        ["e1"],
        {"e1": "Thời hạn không quá 15 ngày."},
    )
    assert result.status == "conditional"
    assert "numeric_or_date_mismatch" in result.reasons


def test_exception_must_be_preserved() -> None:
    result = validate_claim(
        "Mọi trường hợp đều áp dụng.",
        ["e1"],
        {"e1": "Áp dụng cho mọi trường hợp, trừ trường hợp quy định tại Điều 5."},
    )
    assert result.status == "conditional"
    assert "exception_not_preserved" in result.reasons


def test_memory_cannot_be_evidence() -> None:
    result = validate_claim(
        "Mọi trường hợp.", ["m1"], {"m1": "ghi nhớ"}, memory_evidence_ids=["m1"]
    )
    assert result.status == "blocked"
    assert "memory_is_not_evidence" in result.reasons


def test_every_cited_evidence_id_must_exist() -> None:
    result = validate_claim("Nội dung nguồn", ["e1", "missing"], {"e1": "Nội dung nguồn"})
    assert result.status == "blocked"
    assert "evidence_not_found" in result.reasons
