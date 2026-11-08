"""Chat answer composition: one entry per document, verbatim excerpts, no invented facts."""

from datetime import date
from uuid import uuid4

from app.workflow.chat_answer import (
    Rule,
    compose,
    display_title,
    kind_label,
    split_label,
    title_relations,
)

AS_OF = date(2026, 11, 8)


def _item(document: str, label: str, text: str, *, tier: str = "direct", rank: int = 1,
          number: str = "01/VBHN-BCA", title: str = "Thông Tư Quy định chi tiết thủ tục",
          listing: bool = False, node_type: str = "clause", heading: str | None = None,
          relevance: float = 0.9) -> dict:
    node = str(uuid4())
    end = min(len(text), 120)
    return {
        "rank": rank, "node_id": node, "document_id": document,
        "document_version_id": str(uuid4()), "document_number": number, "title": title,
        "doc_type": "circular", "issuing_body": None, "publication_date": None,
        "source_format": "doc", "original_filename": "x.doc", "label": label,
        "heading": heading, "node_type": node_type, "path": "000002:dieu:5",
        "page": 3, "page_end": 3, "quote_exact": text, "source_hash": "a" * 64,
        "viewer_url": f"/api/v1/citations/ev_{node}/pdf?as_of_date=2026-11-08",
        "original_url": f"/api/v1/citations/ev_{node}/original?as_of_date=2026-11-08",
        "effectivity": None, "tier": tier, "match": "phrase", "matched_terms": ["bổ nhiệm"],
        "listing": listing, "relevance": relevance,
        "excerpt": {"start": 0, "end": end, "text": text[:end], "truncated_before": False,
                    "truncated_after": end < len(text), "highlights": [{"start": 0, "end": 4}]},
    }


RULES = [Rule("Trình tự, thủ tục", 60, "thu tuc", "heading", "trinh_tu_thu_tuc"),
         Rule("Phạm vi điều chỉnh, đối tượng áp dụng", 10, "pham vi dieu chinh", "heading",
              "pham_vi_doi_tuong")]


def test_titles_and_kinds_come_from_stored_metadata_only() -> None:
    assert display_title("Thông Tư Quy định chi tiết tiêu chuẩn") == "Quy định chi tiết tiêu chuẩn"
    assert display_title("Kế Hoạch Công tác phổ biến") == "Kế hoạch Công tác phổ biến"
    assert display_title("Thông tư số 33/2026/TT-BCA") == "Thông tư số 33/2026/TT-BCA"
    assert kind_label("01/VBHN-BCA", "Thông Tư Quy định") == "Văn bản hợp nhất"
    assert kind_label("77/2019/TT-BCA", "Thông Tư Sửa đổi, bổ sung một số điều") == (
        "Văn bản sửa đổi, bổ sung")
    relations = title_relations(
        "77/2019/TT-BCA", "Thông Tư Sửa đổi, bổ sung một số điều Thông tư số 33/2014/TT-BCA")
    assert relations and relations[0].target_number == "33/2014/TT-BCA"
    assert not relations[0].verified  # stated by the title, not a verified relation
    assert split_label("Điều 5. Thẩm quyền, trình tự", None, "article", "x") == (
        "Điều 5", "Thẩm quyền, trình tự")
    assert split_label("paragraph", None, "paragraph", "000001:doan")[0] == "Phần mở đầu"


def test_documents_are_grouped_deduplicated_and_lists_kept_apart() -> None:
    consolidated, amending, catalogue = str(uuid4()), str(uuid4()), str(uuid4())
    shared = "Trong thời hạn 10 ngày làm việc, kể từ ngày bổ nhiệm, miễn nhiệm giám định viên."
    items = [
        _item(amending, "Khoản 4 Điều 1", "4. " + shared, number="77/2019/TT-BCA",
              title="Thông Tư Sửa đổi, bổ sung một số điều Thông tư số 33/2014/TT-BCA"),
        _item(consolidated, "Khoản 4 Điều 5", "4. " + shared, rank=2,
              heading="Điều 5. Thẩm quyền, trình tự, thủ tục bổ nhiệm"),
        _item(consolidated, "Điều 1. Phạm vi điều chỉnh", "Điều 1. Phạm vi điều chỉnh ...",
              rank=3, node_type="article"),
        _item(catalogue, "paragraph", "Thông tư số 33/2014/TT-BCA; 77/2019/TT-BCA; ...",
              rank=4, number="540/QD-BCA", listing=True, node_type="paragraph"),
        _item(str(uuid4()), "Khoản 1 Điều 2", "Nhiệm vụ của cán bộ.", tier="weak", rank=5),
    ]
    composed = compose(question="Thủ tục bổ nhiệm, miễn nhiệm", phrases=["thủ tục bổ nhiệm"],
                       items=items, rules=RULES, as_of=AS_OF, result_set_id="rs_x")
    roles = [(document.document_number, document.role) for document in composed.documents]
    assert roles == [("77/2019/TT-BCA", "direct"), ("01/VBHN-BCA", "direct"),
                     ("540/QD-BCA", "reference")]
    vbhn = composed.documents[1]
    assert vbhn.kind_label == "Văn bản hợp nhất"
    # The scope article is listed after the article that regulates the matter.
    assert [clause.label for clause in vbhn.clauses] == ["Khoản 4 Điều 5", "Điều 1"]
    assert vbhn.clauses[0].same_as == [composed.documents[0].clauses[0].evidence_id]
    assert all(item.quote_exact in {i["quote_exact"] for i in items} for item in composed.evidence)
    answer = composed.answer
    assert answer is not None and answer.outcome == "direct"
    assert answer.counts["direct"] == 2 and answer.counts["reference"] == 1
    assert any("chưa được xác minh" in note for note in answer.notes)
    assert any("danh mục" in note for note in answer.notes)
    assert answer.result_set_id == "rs_x"


def test_nothing_relevant_says_so_without_inventing_documents() -> None:
    composed = compose(question="Câu hỏi không có trong kho", phrases=["câu hỏi"],
                       items=[_item(str(uuid4()), "Điều 1", "x", tier="weak")], rules=RULES,
                       as_of=AS_OF, weak_count=1, documents_in_scope=100)
    assert composed.documents == [] and composed.evidence == []
    assert composed.answer is not None and composed.answer.outcome == "not_found"
    assert "100 văn bản" in composed.answer.summary
