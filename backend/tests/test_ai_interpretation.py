"""Diễn giải AI: question focus, evidence selection and every claim check layer.

All legal text here is HƯ CẤU (invented for the test); no real document is quoted.
"""

from __future__ import annotations

import json
from datetime import date
from uuid import uuid4

from app.storage.relevance import analyze_terms, word_plan
from app.synthesis import focused
from app.synthesis.checks import ClaimEvidence, clean_text, verify_claim
from app.synthesis.focus import analyze_question, aspects_in, mentions_focus

ALCOHOL_TEST = ("d) Sử dụng thiết bị kỹ thuật nghiệp vụ để kiểm tra nồng độ cồn đối với người "
                "điều khiển phương tiện liên quan đến vụ tai nạn giao thông tại hiện trường;")
FIRE_LIST = ("c) Các cơ sở kinh doanh không phải nộp tài liệu về phòng cháy và chữa cháy, gồm: "
             "kinh doanh dịch vụ đặt cược; kinh doanh thiết bị kiểm tra nồng độ cồn;")
PENALTY = ("1. Phạt tiền từ 2.000.000 đồng đến 3.000.000 đồng đối với hành vi điều khiển xe "
           "trên đường mà trong máu có nồng độ cồn vượt quá mức quy định.")


def evidence(text: str, *aspects: str, verified: bool = False) -> ClaimEvidence:
    return ClaimEvidence(given=f"99/2030/TT-BCA\nKhoản 1 Điều 5\n{text}", quote=text,
                         effectivity_verified=verified, aspects=frozenset(aspects))


# ------------------------------------------------------------------ focus
def test_question_aspect_and_subject_are_separated() -> None:
    alcohol = analyze_question("Xử phạt về nồng độ cồn")
    assert [item.code for item in alcohol.aspects] == ["xu_phat"]
    assert alcohol.subject == ("nồng độ cồn",) and alcohol.strict
    amount = analyze_question("Mức phạt khi không đội mũ bảo hiểm")
    assert [item.code for item in amount.aspects] == ["muc_phat"]  # hides the general one
    appoint = analyze_question("Thủ tục bổ nhiệm, miễn nhiệm trong Công an nhân dân")
    assert [item.code for item in appoint.aspects] == ["thu_tuc"] and not appoint.strict
    assert appoint.subject == ("bổ nhiệm", "miễn nhiệm", "công an nhân dân")
    both = analyze_question("Thẩm quyền xử phạt vi phạm hành chính trong lĩnh vực thống kê")
    assert {item.code for item in both.aspects} == {"xu_phat", "tham_quyen"}
    deadline = analyze_question("Thời hạn thụ lý khiếu nại là bao lâu?")
    assert [item.code for item in deadline.aspects] == ["thoi_han"]
    assert deadline.subject == ("thụ lý khiếu nại",)
    effect = analyze_question("Thông tư quy định quy tắc ứng xử còn hiệu lực không")
    assert [item.code for item in effect.aspects] == ["hieu_luc"]
    plain = analyze_question("chế độ báo cáo định kỳ")
    assert plain.aspects == () and plain.subject == ("chế độ báo cáo định kỳ",)
    # "đồ vật cấm" names a thing; nobody asks about prohibited behaviour here.
    assert analyze_question("đồ vật cấm đưa vào buồng tạm giữ").aspects == ()


def test_inspection_clause_does_not_regulate_a_penalty() -> None:
    focus = analyze_question("Xử phạt về nồng độ cồn")
    assert aspects_in(focus, [ALCOHOL_TEST]) == set()
    assert aspects_in(focus, [FIRE_LIST]) == set()
    assert aspects_in(focus, [PENALTY]) == {"xu_phat"}


# ------------------------------------------------------------------ selection
def _view(node: str, document: str, text: str, *, tier: str = "direct",
          listing: bool = False, title: str = "Quy định HƯ CẤU",
          label: str = "Khoản 1 Điều 5") -> dict:
    return {
        "node_id": node, "document_id": document, "document_version_id": str(uuid4()),
        "document_number": f"{document[:2]}/2030/TT-BCA", "title": title, "doc_type": "circular",
        "issuing_body": None, "publication_date": None, "source_format": "pdf",
        "original_filename": "x.pdf", "label": label, "heading": None,
        "node_type": "clause", "path": "", "page": 1, "page_end": 1, "quote_exact": text,
        "excerpt": {"start": 0, "end": len(text), "text": text, "truncated_before": False,
                    "truncated_after": False, "highlights": []},
        "viewer_url": "/v", "original_url": "/o", "source_hash": "h", "effectivity": None,
        "tier": tier, "match": "phrase", "matched_terms": [], "listing": listing,
        "relevance": 1.0, "extraction_method": "native_text",
    }


def _plan(question: str, views: list[dict]) -> focused.FocusPlan:
    focus = analyze_question(question)
    terms = analyze_terms(focus.subject_text)
    weights = {unit.tokens: 1.0 for unit in terms.units}
    classified = focused.classify(focus, [(view, {"exact": 1}) for view in views], terms,
                                  word_plan(terms, weights))
    return focused.build_plan(focus, classified, rules=[], relations={}, as_of=date(2030, 1, 1),
                              max_per_batch=focused.BATCH_CLAUSES)


def test_no_penalty_clause_means_not_found_and_no_model_batch() -> None:
    plan = _plan("Xử phạt về nồng độ cồn", [
        _view(str(uuid4()), str(uuid4()), ALCOHOL_TEST),
        _view(str(uuid4()), str(uuid4()), FIRE_LIST),
        _view(str(uuid4()), str(uuid4()), "Danh mục 1/2020/TT-BCA; 2/2021/TT-BCA; 3/2022/TT-BCA;"
              " 4/2023/TT-BCA nồng độ cồn", listing=True),
    ])
    assert plan.status == "not_found" and plan.batches == []
    assert plan.counts["other_aspect"] == 2 and plan.counts["mentioned"] == 1
    assert len(plan.other_documents) == 2
    state = focused.FocusState(plan=plan)
    answer = focused.response(state, result_set_id="rs", disclaimer="d")["answer"]
    assert answer["status"] == "not_found"
    assert answer["lead"]["text"].startswith("Chưa tìm thấy trong kho điều khoản quy định xử phạt")
    assert answer["points"] == [] and answer["documents"] == []


def test_penalty_clause_is_the_only_interpreted_evidence() -> None:
    penalty_node = str(uuid4())
    plan = _plan("Xử phạt về nồng độ cồn", [
        _view(str(uuid4()), str(uuid4()), ALCOHOL_TEST),
        _view(penalty_node, str(uuid4()), PENALTY),
    ])
    assert plan.status == "ready"
    assert list(plan.claim_evidence) == [f"ev_{penalty_node}"]
    messages, keys = focused.messages_for(plan, plan.batch_evidence(0), [], want_summary=True)
    payload = json.loads(messages[1]["content"])
    assert payload["question"] == "Xử phạt về nồng độ cồn"
    assert payload["asked"] == {"aspect": "xử phạt", "subject": "nồng độ cồn"}
    assert list(payload["evidence"]) == ["e1"] and keys == {"e1": f"ev_{penalty_node}"}


def test_partial_subject_is_used_only_when_nothing_has_all_of_it() -> None:
    whole, part = str(uuid4()), str(uuid4())
    plan = _plan("Phụ cấp công vụ đối với công chức cấp xã", [
        _view(whole, str(uuid4()), "1. Phụ cấp công vụ đối với công chức cấp xã bằng 25%."),
        _view(part, str(uuid4()), "2. Phụ cấp ưu đãi nghề đối với nhân viên y tế.",
              tier="related"),
    ])
    assert list(plan.claim_evidence) == [f"ev_{whole}"] and not plan.subject_partial


def test_continue_interprets_next_documents_without_repeating() -> None:
    first, second = str(uuid4()), str(uuid4())
    views = [_view(f"{i:08d}-0000-0000-0000-000000000000", doc, f"{i}. Báo cáo định kỳ hằng "
                   f"tháng gửi đơn vị số {i} HƯ CẤU.", label=f"Khoản 1 Điều {i}") for i, doc in
             [(1, first), (2, first), (3, first), (4, first), (5, second)]]
    plan = _plan("chế độ báo cáo định kỳ", views)
    assert len(plan.batches) == 2  # 4 clauses per call, the next document waits
    state = focused.FocusState(plan=plan)
    for index, text in ((0, "Báo cáo định kỳ hằng tháng gửi đơn vị số 1."),
                        (1, "Báo cáo định kỳ hằng tháng gửi đơn vị số 5.")):
        ids = plan.batch_evidence(index)
        previous = [point["text"] for point in state.points]
        _, keys = focused.messages_for(plan, ids, previous, want_summary=index == 0)
        canonical = json.dumps({"summary": None, "points": [
            {"text": text, "evidence_ids": ["e1"]},
            # The model repeats the first point in the second call: dropped.
            {"text": "Báo cáo định kỳ hằng tháng gửi đơn vị số 1.", "evidence_ids": ["e1"]},
        ], "missing": ""})
        _, points, _, _ = focused.check_claims(plan, canonical, keys, previous)
        state.points.extend({**point, "batch": index + 1} for point in points)
        state.position = index + 1
        state.model_answers += 1
        body = focused.response(state, result_set_id="rs", disclaimer="d")
        assert body["can_continue"] is (index == 0)
    assert [point["text"] for point in state.points] == [
        "Báo cáo định kỳ hằng tháng gửi đơn vị số 1.",
        "Báo cáo định kỳ hằng tháng gửi đơn vị số 5."]


# ------------------------------------------------------------------ claim layers
def test_valid_evidence_id_does_not_make_an_off_topic_claim_pass() -> None:
    focus = analyze_question("Xử phạt về nồng độ cồn")
    given = {"a": evidence(ALCOHOL_TEST)}
    fire = verify_claim("Cơ sở kinh doanh phải bảo đảm an toàn phòng cháy và chữa cháy cho kho.",
                        ["a"], given, focus=focus)
    assert not fire.keep and fire.reasons in {("NOT_SUPPORTED_BY_EVIDENCE",), ("OFF_TOPIC",)}
    # Well supported by the words of the clause, but it states a penalty the clause lacks.
    inferred = verify_claim("Người điều khiển phương tiện liên quan đến vụ tai nạn giao thông bị "
                            "xử phạt khi kiểm tra nồng độ cồn tại hiện trường.",
                            ["a"], given, focus=focus)
    assert not inferred.keep and inferred.reasons == ("ASPECT_NOT_IN_EVIDENCE",)
    ok = verify_claim("Thiết bị kỹ thuật nghiệp vụ được dùng để kiểm tra nồng độ cồn của người "
                      "điều khiển phương tiện tại hiện trường vụ tai nạn.", ["a"], given,
                      focus=focus)
    assert ok.keep and ok.status == "verified"


def test_facts_not_in_cited_clause_are_dropped_not_flagged() -> None:
    given = {"p": evidence(PENALTY, "xu_phat")}
    focus = analyze_question("Xử phạt về nồng độ cồn")
    assert not verify_claim("Phạt tiền từ 5.000.000 đồng đối với người có nồng độ cồn.", ["p"],
                            given, focus=focus).keep
    assert not verify_claim("Theo Điều 9, người có nồng độ cồn bị phạt tiền.", ["p"], given,
                            focus=focus).keep
    assert not verify_claim("Nghị định 1/2031/NĐ-CP phạt tiền người có nồng độ cồn.", ["p"],
                            given, focus=focus).keep
    kept = verify_claim("Phạt tiền từ 2.000.000 đồng đến 3.000.000 đồng khi trong máu có nồng độ "
                        "cồn vượt quá mức quy định.", ["p"], given, focus=focus)
    assert kept.keep and kept.status == "verified"


def test_quotes_negation_exceptions_conditions_and_modality() -> None:
    focus = analyze_question("điều kiện cấp giấy phép HƯ CẤU")
    rule = evidence("Cơ quan cấp giấy phép khi hồ sơ đầy đủ, trừ trường hợp người đề nghị đang bị "
                    "xử lý kỷ luật.", "dieu_kien")
    given = {"r": rule}
    quote = verify_claim("Căn cứ ghi “cấp giấy phép trong mọi trường hợp”.", ["r"], given,
                         focus=focus)
    assert not quote.keep and quote.reasons == ("QUOTE_NOT_IN_EVIDENCE",)
    reversed_ = verify_claim("Cơ quan không cấp giấy phép khi hồ sơ đầy đủ.", ["r"], given,
                             focus=focus)
    assert not reversed_.keep and reversed_.reasons == ("NEGATION_REVERSED",)
    omitted = verify_claim("Cơ quan cấp giấy phép khi hồ sơ đầy đủ.", ["r"], given, focus=focus)
    assert omitted.keep and omitted.status == "needs_review"
    assert "EXCEPTION_OMITTED" in omitted.reasons
    full = verify_claim("Cơ quan cấp giấy phép khi hồ sơ đầy đủ, trừ trường hợp người đề nghị "
                        "đang bị xử lý kỷ luật.", ["r"], given, focus=focus)
    assert full.keep and full.status == "verified"
    must = {"m": evidence("Cơ quan phải trả lời bằng văn bản cho người đề nghị cấp giấy phép.")}
    may = verify_claim("Cơ quan có thể trả lời bằng văn bản cho người đề nghị cấp giấy phép.",
                       ["m"], must, focus=focus)
    assert may.keep and "MODALITY_MISMATCH" in may.reasons


def test_effectivity_needs_verification_or_the_source_words() -> None:
    focus = analyze_question("quy tắc ứng xử HƯ CẤU còn hiệu lực không")
    plain = {"x": evidence("Quy tắc ứng xử HƯ CẤU áp dụng cho cán bộ.")}
    unverified = verify_claim("Quy tắc ứng xử HƯ CẤU còn hiệu lực.", ["x"], plain, focus=focus)
    assert not unverified.keep
    assert unverified.reasons[0] in {"EFFECTIVITY_NOT_VERIFIED", "ASPECT_NOT_IN_EVIDENCE"}
    # Without a question about effectivity the dedicated layer is what drops it.
    other = verify_claim("Quy tắc ứng xử HƯ CẤU còn hiệu lực.", ["x"], plain,
                         focus=analyze_question("quy tắc ứng xử HƯ CẤU"))
    assert other.reasons == ("ASPECT_NOT_IN_EVIDENCE",) or other.reasons == (
        "EFFECTIVITY_NOT_VERIFIED",)
    marked = verify_claim("Quy tắc ứng xử HƯ CẤU còn hiệu lực.", ["v"],
                          {"v": evidence("Quy tắc ứng xử HƯ CẤU áp dụng cho cán bộ.", "hieu_luc",
                                         verified=True)}, focus=focus)
    assert marked.keep
    source = {"y": evidence("Thông tư này có hiệu lực thi hành kể từ ngày 06 tháng 10 năm 2030.",
                            "hieu_luc")}
    stated = verify_claim("Thông tư có hiệu lực thi hành kể từ ngày 06 tháng 10 năm 2030.", ["y"],
                          source, focus=focus)
    assert stated.keep and stated.status == "verified"


def test_duplicates_copies_and_restated_decisions() -> None:
    focus = analyze_question("thời hạn thi hành biện pháp HƯ CẤU")
    text = ("Thời hạn thi hành biện pháp khắc phục là 10 ngày làm việc kể từ ngày nhận được "
            "quyết định xử phạt vi phạm hành chính.")
    given = {"t": evidence(text, "thoi_han")}
    restated_text = ("Thời hạn thi hành biện pháp khắc phục là 10 ngày làm việc kể từ ngày nhận "
                     "quyết định xử phạt.")
    restated = verify_claim(restated_text, ["t"], given, focus=focus)
    assert restated.keep  # "quyết định xử phạt" is the source's noun, not a verdict
    again = verify_claim(restated_text, ["t"], given, focus=focus, previous=[restated_text])
    assert not again.keep and again.reasons == ("DUPLICATE",)
    long_source = " ".join(["Cơ quan HƯ CẤU tiếp nhận hồ sơ đề nghị và kiểm tra thành phần"] * 4)
    copied = verify_claim(long_source, ["c"], {"c": evidence(long_source)}, focus=focus)
    assert not copied.keep and copied.reasons == ("COPIED_VERBATIM",)
    assert mentions_focus(focus, "Biện pháp HƯ CẤU được thi hành")


def test_clean_text_fixes_form_never_content() -> None:
    assert clean_text("  - thời hạn là 10 ngày (e1). Căn cứ: e1, e2.") == "Thời hạn là 10 ngày."
    assert clean_text("**Hồ sơ** gồm 02 bộ [e3]") == "Hồ sơ gồm 02 bộ."
    decomposed = "Thu\u0309 tu\u0323c"  # NFD input from a model
    assert clean_text(decomposed) == "Thủ tục."
