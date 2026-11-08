from app.documents.deduplication import content_fingerprint
from app.documents.native_pdf import ExtractedPage


def _page(
    number: int, text: str, *, method: str = "native_text", quality: str = "usable",
) -> ExtractedPage:
    return ExtractedPage(number, 595, 842, 0, text, (), method, quality)


def test_text_fingerprint_ignores_unicode_and_whitespace_layout_only() -> None:
    original = [_page(1, "Điều 1.  Quy định\r\náp dụng"), _page(2, "từ ngày 01.")]
    repackaged = [_page(1, "Điều 1. Quy định áp dụng từ ngày 01.")]
    original_hash = content_fingerprint(original)
    assert original_hash is not None
    assert original_hash == content_fingerprint(repackaged)
    assert original_hash != content_fingerprint([_page(1, "Điều 1. Quy định áp dụng từ ngày 02.")])
    assert original_hash != content_fingerprint([_page(1, "Điều 1. Quy định ap dụng từ ngày 01.")])


def test_text_fingerprint_is_unavailable_for_unreadable_or_ocr_pages() -> None:
    assert content_fingerprint([]) is None
    assert content_fingerprint([_page(1, "")]) is None
    assert content_fingerprint([_page(1, "text", quality="needs_review")]) is None
    assert content_fingerprint([_page(1, "text", method="local_ocr")]) is None
    assert content_fingerprint([_page(1, "text"), _page(2, "", quality="needs_ocr")]) is None
