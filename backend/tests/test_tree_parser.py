from app.documents.native_pdf import ExtractedPage
from app.documents.tree_parser import parse_legal_tree


def test_does_not_invent_article_for_unstructured_document() -> None:
    pages = [ExtractedPage(1, 595, 842, 0, "Hướng dẫn thực hiện\nNội dung hướng dẫn.", ())]
    nodes = parse_legal_tree(pages)
    assert {node.node_type for node in nodes} == {"paragraph"}
    assert all(node.node_type != "article" for node in nodes)


def test_parses_explicit_article_and_clause() -> None:
    pages = [ExtractedPage(1, 595, 842, 0, "Điều 5. Quy định chung\n1. Nội dung áp dụng.", ())]
    nodes = parse_legal_tree(pages)
    assert {node.node_type for node in nodes} == {"article", "clause"}


def test_continuation_stays_with_point_and_page_number_is_ignored() -> None:
    pages = [
        ExtractedPage(
            1,
            595,
            842,
            0,
            "Điều 2. Quy định\n1. Khoản một\na) Điểm a\nNội dung tiếp của điểm a",
            (),
        ),
        ExtractedPage(2, 595, 842, 0, "2\nNội dung qua trang\nb) Điểm b\n2. Khoản hai", ()),
    ]
    nodes = parse_legal_tree(pages)
    assert [node.node_type for node in nodes] == ["article", "clause", "point", "point", "clause"]
    assert nodes[2].text_original == "a) Điểm a\nNội dung tiếp của điểm a\nNội dung qua trang"
    assert nodes[3].text_original == "b) Điểm b"
    assert nodes[4].text_original == "2. Khoản hai"


def test_ocr_nodes_keep_low_parse_confidence_for_review() -> None:
    pages = [
        ExtractedPage(
            1,
            595,
            842,
            0,
            "Điều 1. Phạm vi\n1. Nội dung OCR",
            (),
            extraction_method="local_ocr",
            text_quality="needs_review",
        )
    ]
    nodes = parse_legal_tree(pages)
    assert [node.node_type for node in nodes] == ["article", "clause"]
    assert all(node.parse_confidence <= 0.5 for node in nodes)


def test_words_chuong_trinh_and_muc_tieu_are_not_section_headings() -> None:
    pages = [ExtractedPage(
        1, 595, 842, 0,
        "Điều 1. Phạm vi\n1. Nội dung\na) Quy định\n"
        "Chương trình áp dụng\nMục tiêu thực hiện\nb) Quy định khác", (),
    )]
    nodes = parse_legal_tree(pages)
    assert [node.node_type for node in nodes] == ["article", "clause", "point", "point"]
    assert "Chương trình áp dụng" in nodes[2].text_original
    assert "Mục tiêu thực hiện" in nodes[2].text_original


def test_explicit_numbered_sections_remain_headings() -> None:
    pages = [ExtractedPage(
        1, 595, 842, 0, "Chương II. Quy định\nMục 1. Nguyên tắc\nĐiều 3. Nội dung", (),
    )]
    assert [node.node_type for node in parse_legal_tree(pages)] == ["heading", "heading", "article"]
