import pytest

from app.vietnamese_nlp.unicode_norm import normalize_text


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("sự kiện của nhà sư", "sự kiện của nhà sư"),
        ("Hoàng và hoàng hôn", "Hoàng và hoàng hôn"),
        ("HOÀ", "HÒA"),
        ("hoà thuý lí", "hòa thúy lí"),
    ],
)
def test_normalization_preserves_words_and_uses_stable_spelling(source: str, expected: str) -> None:
    assert normalize_text(source) == expected
    assert normalize_text(expected) == expected
