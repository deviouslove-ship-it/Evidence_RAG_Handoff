from app.vietnamese_nlp.unicode_norm import canonical_document_number, fold_text, normalize_text


def test_tone_mapping_is_bidirectional() -> None:
    assert normalize_text("hòa") == normalize_text("hoà") == "hòa"
    assert normalize_text("thúy") == normalize_text("thuý") == "thúy"


def test_fold_text_handles_dong_banh() -> None:
    assert fold_text("Đặng") == "dang"


def test_canonical_document_number_preserves_source_and_creates_key() -> None:
    assert canonical_document_number("NĐ  12/2024/NĐ-CP") == "nd12/2024/nd-cp"
