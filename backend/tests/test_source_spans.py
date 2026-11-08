from app.documents.spans import PageTextLocator


def test_maps_whitespace_changes_back_to_original_page_text() -> None:
    page = "Mở đầu\r\n  Điều 1. Quy định\r\n   Nội dung\ncuối"
    result = PageTextLocator(page).find("Điều 1. Quy định\nNội dung")
    assert result is not None
    offset, exact = result
    assert exact == "Điều 1. Quy định\r\n   Nội dung"
    assert page[offset:offset + len(exact)] == exact


def test_refuses_ambiguous_or_cross_page_text() -> None:
    locator = PageTextLocator("Điều 1.\nNội dung\nĐiều 1.\nNội dung")
    assert locator.find("Điều 1.\nNội dung") is None
    assert locator.find("Điều 1.\nNội dung ở trang sau") is None
    assert locator.find("   ") is None
