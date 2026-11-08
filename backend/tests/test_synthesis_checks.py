"""G4 code checks on AI-written points (design §7) and G3 item reading.  HƯ CẤU text."""

from __future__ import annotations

from app.effectivity.extract import parse_amend_item
from app.synthesis.checks import check_point

EVIDENCE = {
    "n1": "99/2030/TT-BCA\nKhoản 2 Điều 5\nHồ sơ gồm 02 bản sao, nộp trong thời hạn 10 ngày "
          "làm việc kể từ ngày 01/7/2030.",
    "n2": "99/2030/TT-BCA\nĐiều 6\nCơ quan tiếp nhận kiểm tra hồ sơ.",
}


def test_point_must_cite_given_evidence() -> None:
    assert not check_point("Hồ sơ gồm 02 bản sao.", [], EVIDENCE).keep
    assert not check_point("Hồ sơ gồm 02 bản sao.", ["n9"], EVIDENCE).keep


def test_numbers_dates_and_parts_must_be_in_cited_evidence() -> None:
    ok = check_point("Theo khoản 2 Điều 5, hồ sơ nộp trong 10 ngày làm việc từ 01/7/2030.",
                     ["n1"], EVIDENCE)
    assert (ok.keep, ok.status) == (True, "verified")
    wrong_number = check_point("Hồ sơ nộp trong 15 ngày làm việc.", ["n1"], EVIDENCE)
    assert (wrong_number.keep, wrong_number.status) == (True, "unverified")
    wrong_part = check_point("Điều 7 quy định việc kiểm tra hồ sơ.", ["n2"], EVIDENCE)
    assert wrong_part.status == "unverified"
    wrong_source = check_point("Hồ sơ nộp trong 10 ngày làm việc.", ["n2"], EVIDENCE)
    assert wrong_source.status == "unverified"


def test_business_conclusions_are_dropped_outside_quotes() -> None:
    assert not check_point("Trường hợp này đủ điều kiện được cấp.", ["n1"], EVIDENCE).keep
    assert not check_point("Cơ quan phải xử lý ngay hồ sơ.", ["n2"], EVIDENCE).keep
    quoted = check_point("Căn cứ ghi “phải xử lý” trong khoản 2 Điều 5.", ["n1"], EVIDENCE)
    assert quoted.keep


def test_amending_items_map_to_clause_targets() -> None:
    assert parse_amend_item("2. Sửa đổi khoản 2 Điều 4 như sau: “2. ...”") == [
        ("modify", "khoản 2 Điều 4")]
    assert parse_amend_item(
        "5. Sửa đổi khoản 3 và bổ sung khoản 4, khoản 5 vào Điều 9 như sau:") == [
        ("modify", "khoản 3 Điều 9"), ("add", "Điều 9")]
    assert parse_amend_item("4. Bổ sung khoản 6 vào sau khoản 5 Điều 6 như sau:") == [
        ("add", "Điều 6")]
    assert parse_amend_item("14. Bãi bỏ Điều 12 quy định về việc HƯ CẤU.") == [
        ("repeal", "Điều 12")]
    assert parse_amend_item(
        "13. Thay thế cụm từ “A” bằng cụm từ “B” tại điểm c khoản 1 Điều 15 và điểm c "
        "khoản 1 Điều 16.") == [("modify", "điểm c khoản 1 Điều 15"),
                                ("modify", "điểm c khoản 1 Điều 16")]
    assert parse_amend_item("1. Thông tư này quy định HƯ CẤU.") == []
