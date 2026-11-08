"""Phrase-aware relevance tiers: one shared syllable is never evidence (storage/relevance.py)."""

from app.storage.relevance import (
    QueryTerms,
    WordPlan,
    analyze_terms,
    assess,
    is_listing,
    word_plan,
)


def _plan(terms: QueryTerms, document_frequency: dict[str, int], total: int = 7000) -> WordPlan:
    import math

    weights = {}
    for unit in terms.units:
        count = document_frequency.get(unit.text, 0)
        weights[unit.tokens] = 0.0 if count == 0 else math.log((total + 1) / (count + 0.5)) + 0.1
    return word_plan(terms, weights)


APPOINT_DF = {"thủ tục": 300, "tục bổ": 20, "bổ nhiệm": 60, "miễn nhiệm": 45,
              "công an": 1500, "an nhân": 900, "nhân dân": 1100}


def test_question_is_cut_into_phrases_not_syllables() -> None:
    terms = analyze_terms("Thủ tục bổ nhiệm, miễn nhiệm trong Công an nhân dân")
    assert terms.phrases == ["thủ tục bổ nhiệm", "miễn nhiệm", "công an nhân dân"]
    assert "nhiệm" not in [unit.text for unit in terms.units]
    assert analyze_terms("chế độ báo cáo định kỳ").phrases == ["chế độ báo cáo định kỳ"]
    # References are matched by their own channel and never become words to look for.
    assert analyze_terms("Điều 5 Thông tư 55/2021/TT-BCA quy định gì?").phrases == ["thông tư"]
    assert analyze_terms("Chỉ thị về phổ biến giáo dục pháp luật").phrases[0] == "chỉ thị"


def test_straddling_pairs_do_not_own_syllables() -> None:
    terms = analyze_terms("Thủ tục bổ nhiệm, miễn nhiệm trong Công an nhân dân")
    plan = _plan(terms, APPOINT_DF)
    owners = {unit.text for unit, _ in plan.owners}
    assert "tục bổ" not in owners and "an nhân" not in owners
    assert {"bổ nhiệm", "miễn nhiệm"} <= {" ".join(tokens) for tokens in plan.rare}


def test_clause_with_both_phrases_is_direct_and_excerpt_is_verbatim() -> None:
    terms = analyze_terms("Thủ tục bổ nhiệm, miễn nhiệm trong Công an nhân dân")
    plan = _plan(terms, APPOINT_DF)
    text = ("4. Trong thời hạn 10 ngày làm việc, kể từ ngày bổ nhiệm, miễn nhiệm giám định "
            "viên kỹ thuật hình sự, Bộ Công an, Ủy ban nhân dân cấp tỉnh có trách nhiệm lập "
            "danh sách.")
    found = assess(terms, plan, text=text,
                   headings=["Điều 5. Thẩm quyền, trình tự, thủ tục bổ nhiệm, miễn nhiệm"],
                   title="Thông tư quy định", ranks={"exact": 1})
    assert found.tier == "direct"
    excerpt = text[found.excerpt_start:found.excerpt_end]
    assert excerpt and excerpt in text
    marked = [text[start:end] for start, end in found.highlights]
    assert "bổ nhiệm" in marked and "miễn nhiệm" in marked


def test_shared_syllables_or_context_words_are_weak() -> None:
    terms = analyze_terms("Thủ tục bổ nhiệm, miễn nhiệm trong Công an nhân dân")
    plan = _plan(terms, APPOINT_DF)
    found = assess(terms, plan,
                   text="Cán bộ Công an nhân dân có trách nhiệm thực hiện nhiệm vụ được giao.",
                   headings=[], title="Thông tư", ranks={"exact": 3, "semantic": 40})
    assert found.tier == "weak"
    assert found.match in {"semantic", "partial"}


def test_one_of_two_coordinated_phrases_is_not_direct() -> None:
    terms = analyze_terms("Thủ tục bổ nhiệm, miễn nhiệm trong Công an nhân dân")
    plan = _plan(terms, APPOINT_DF)
    found = assess(terms, plan,
                   text="Tại thôn đã bổ nhiệm Đội trưởng, Công an cấp xã và Ủy ban nhân dân.",
                   headings=["Điều 4. Trình tự, thủ tục thành lập Tổ bảo vệ"],
                   title="Thông tư", ranks={"exact": 2})
    assert found.tier == "related"


def test_scattered_words_in_a_long_paragraph_are_not_a_phrase_match() -> None:
    terms = analyze_terms("chế độ báo cáo định kỳ")
    plan = _plan(terms, {"chế độ": 250, "độ báo": 20, "báo cáo": 700, "cáo định": 10,
                         "định kỳ": 150})
    filler = " ".join(["nội dung công tác"] * 30)
    scattered = f"Chế độ công tác. {filler} việc báo cáo chưa đầy đủ. {filler} kiểm tra định kỳ."
    together = "2. Báo cáo định kỳ hàng tháng về tố cáo gửi Thanh tra Bộ."
    assert assess(terms, plan, text=scattered, headings=[], title="",
                  ranks={"exact": 1}).tier != "direct"
    assert assess(terms, plan, text=together, headings=["Điều 18. Báo cáo công tác"],
                  title="", ranks={"exact": 1}).tier == "direct"


def test_lists_of_documents_are_never_direct_evidence() -> None:
    text = ("Thông tư số 33/2014/TT-BCA quy định chi tiết tiêu chuẩn, trình tự, thủ tục bổ "
            "nhiệm, miễn nhiệm giám định viên; Thông tư số 77/2019/TT-BCA; Thông tư số "
            "32/2022/TT-BCA; Nghị định số 85/2013/NĐ-CP thay thế.")
    assert is_listing(text, "Quyết định công bố danh mục")
    terms = analyze_terms("Thủ tục bổ nhiệm, miễn nhiệm trong Công an nhân dân")
    found = assess(terms, _plan(terms, APPOINT_DF), text=text, headings=[],
                   title="Quyết định về việc công bố Danh mục văn bản",
                   ranks={"exact": 1})
    assert found.listing and found.tier != "direct"


def test_unaccented_query_matches_accented_text() -> None:
    terms = analyze_terms("bo nhiem mien nhiem giam dinh vien")
    plan = _plan(terms, {"bo nhiem": 60, "nhiem mien": 30, "mien nhiem": 45,
                         "nhiem giam": 10, "giam dinh": 80, "dinh vien": 90})
    found = assess(terms, plan, text="Bổ nhiệm, miễn nhiệm giám định viên kỹ thuật hình sự.",
                   headings=[], title="", ranks={"exact": 1})
    assert found.tier == "direct"
