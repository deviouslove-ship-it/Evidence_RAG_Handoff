"""C1: shared normative signals + deterministic alignment/diff engine.  HƯ CẤU text.

Pure unit tests: inputs are constructed directly, no PostgreSQL, no LLM, no network.
"""

from __future__ import annotations

import unicodedata
from datetime import date
from uuid import UUID, uuid4

from app.analysis.signals import (
    DeadlineSpan,
    LogicalNode,
    NodeRecord,
    QuantitySpan,
    extract_normative_signals,
    normalize_structural_key,
    stitch_logical_nodes,
)
from app.comparison.align import AlignedPair, AmendmentLink, align_nodes
from app.comparison.diff import DiffSegment, compute_token_diff, diff_pair
from app.vietnamese_nlp.unicode_norm import fold_text


def _node(
    key: str,
    text: str,
    *,
    ordinal: int,
    node_type: str = "clause",
    node_id: UUID | None = None,
    embedding: tuple[float, ...] | None = None,
    page_start: int | None = 1,
    page_end: int | None = 1,
) -> LogicalNode:
    nid = node_id if node_id is not None else uuid4()
    return LogicalNode(
        primary_node_id=nid,
        member_node_ids=(nid,),
        node_type=node_type,
        structural_key=key,
        raw_path=f"{ordinal + 1:06d}:{key}" if key else f"{ordinal + 1:06d}",
        citation_label=None,
        label_original=None,
        text_original=text,
        text_folded=fold_text(text),
        page_start=page_start,
        page_end=page_end,
        ordinal=ordinal,
        embedding=embedding,
    )


def _record(
    path: str,
    text: str,
    *,
    node_type: str = "clause",
    node_id: UUID | None = None,
    page_start: int | None = None,
    page_end: int | None = None,
) -> NodeRecord:
    return NodeRecord(
        node_id=node_id if node_id is not None else uuid4(),
        node_type=node_type,
        path=path,
        text_original=text,
        page_start=page_start,
        page_end=page_end,
    )


# --------------------------------------------------------------- structural key


def test_normalize_structural_key_extracts_dieu_family() -> None:
    assert normalize_structural_key("000001:chuong:I/dieu:5/khoan:2/diem:a") == (
        "dieu:5/khoan:2/diem:a"
    )
    assert normalize_structural_key("000001:dieu:5/khoan:2/diem:A") == (
        "dieu:5/khoan:2/diem:a"
    )
    assert normalize_structural_key("dieu:5/khoan:2/diem:Đ") == (
        "dieu:5/khoan:2/diem:đ"
    )
    assert normalize_structural_key("000003:dieu:2/khoan:1") == "dieu:2/khoan:1"
    assert normalize_structural_key("000004:dieu:2/khoan:1/tiep:2") == "dieu:2/khoan:1"
    assert normalize_structural_key("dieu:5/khoan:2") == "dieu:5/khoan:2"
    assert normalize_structural_key("000001:dieu:05/khoan:02") == "dieu:5/khoan:2"


def test_normalize_structural_key_keeps_non_dieu_remainder() -> None:
    assert normalize_structural_key("000010:chuong:I") == "chuong:I"
    assert normalize_structural_key("000011:muc:2") == "muc:2"
    assert normalize_structural_key("000012:phuluc:1") == "phuluc:1"
    assert normalize_structural_key("000013:doan") == "doan"
    assert normalize_structural_key("000014:doan/tiep:3") == "doan"


def test_normalize_structural_key_edges() -> None:
    assert normalize_structural_key(None) == ""
    assert normalize_structural_key("") == ""
    # node_writer writes a BARE ordinal when the parsed node has no path_key.
    assert normalize_structural_key("000007") == ""


# --------------------------------------------------------------- stitch tiep:N


def test_stitch_merges_continuation_segments() -> None:
    owner_id, part_id = uuid4(), uuid4()
    records = [
        _record("000003:dieu:2/khoan:1", "Nội dung khoản 2.", node_type="clause",
                node_id=owner_id, page_start=1, page_end=1),
        _record("000004:dieu:2/khoan:1/tiep:2", "Phần tiếp theo của khoản 2.",
                node_type="paragraph", node_id=part_id, page_start=2, page_end=2),
    ]
    stitched = stitch_logical_nodes(records)
    assert len(stitched) == 1
    node = stitched[0]
    assert node.primary_node_id == owner_id
    assert node.member_node_ids == (owner_id, part_id)
    assert node.node_type == "clause"
    assert node.structural_key == "dieu:2/khoan:1"
    assert node.text_original == "Nội dung khoản 2.\nPhần tiếp theo của khoản 2."
    assert (node.page_start, node.page_end) == (1, 2)


def test_stitch_three_segments_join_with_single_newlines() -> None:
    ids = [uuid4(), uuid4(), uuid4()]
    records = [
        _record("000003:dieu:2/khoan:1", "A", node_id=ids[0], page_start=1, page_end=1),
        _record("000004:dieu:2/khoan:1/tiep:2", "B", node_type="paragraph",
                node_id=ids[1], page_start=2, page_end=2),
        _record("000005:dieu:2/khoan:1/tiep:3", "C", node_type="paragraph",
                node_id=ids[2], page_start=3, page_end=3),
    ]
    node = stitch_logical_nodes(records)[0]
    assert node.member_node_ids == tuple(ids)
    assert node.text_original == "A\nB\nC"
    assert (node.page_start, node.page_end) == (1, 3)


def test_stitch_short_v2_does_not_create_phantom_add_remove() -> None:
    v1 = stitch_logical_nodes([
        _record("000003:dieu:2/khoan:1", "Nội dung dài.", page_start=1, page_end=1),
        _record("000004:dieu:2/khoan:1/tiep:2", "Phần tiếp.", node_type="paragraph",
                page_start=2, page_end=2),
    ])
    v2 = stitch_logical_nodes([
        _record("000003:dieu:2/khoan:1", "Nội dung dài. Phần tiếp.", page_start=1, page_end=1),
    ])
    pairs = align_nodes(v1, v2, mode="versions")
    assert len(pairs) == 1
    assert pairs[0].left is not None and pairs[0].right is not None
    assert pairs[0].alignment_method == "structural_key"
    assert diff_pair(pairs[0]).change_kind == "unchanged"


def test_stitch_keeps_distinct_doan_paragraphs_apart() -> None:
    a1, a2, b1, b2 = uuid4(), uuid4(), uuid4(), uuid4()
    records = [
        _record("000001:doan", "Đoạn một.", node_type="paragraph", node_id=a1),
        _record("000002:doan/tiep:2", "Tiếp đoạn một.", node_type="paragraph", node_id=a2),
        _record("000003:doan", "Đoạn hai.", node_type="paragraph", node_id=b1),
        _record("000004:doan/tiep:2", "Tiếp đoạn hai.", node_type="paragraph", node_id=b2),
    ]
    stitched = stitch_logical_nodes(records)
    assert len(stitched) == 2
    assert stitched[0].member_node_ids == (a1, a2)
    assert stitched[1].member_node_ids == (b1, b2)
    assert stitched[0].text_original == "Đoạn một.\nTiếp đoạn một."
    assert stitched[1].text_original == "Đoạn hai.\nTiếp đoạn hai."


def test_stitch_none_pages_stay_none() -> None:
    node = stitch_logical_nodes([_record("000001:doan", "X", node_type="paragraph")])[0]
    assert node.page_start is None and node.page_end is None


# --------------------------------------------------------------- signals


def test_deadlines_and_dates() -> None:
    signals = extract_normative_signals(
        "Hồ sơ nộp trong thời hạn 10 ngày làm việc kể từ ngày 01/7/2030."
    )
    assert DeadlineSpan(10.0, "ngay_lam_viec", "10 ngày làm việc") in signals.deadlines
    assert (1, 7, 2030) in signals.dates
    # "01 tháng 7" inside a date is not a deadline of one month.
    assert all(span.unit_normalized != "thang" for span in signals.deadlines)
    plain = extract_normative_signals("Thời hạn 15 ngày.").plain_numbers
    assert "15" in plain


def test_amounts_percents_and_counts() -> None:
    signals = extract_normative_signals(
        "Phạt tiền 15.000.000 đồng, tối đa 1,5 triệu đồng, tỷ lệ 20%, hồ sơ gồm 02 bản sao."
    )
    assert QuantitySpan(15000000.0, "dong", "15.000.000 đồng") in signals.amounts_and_percents
    assert QuantitySpan(1.5, "trieu_dong", "1,5 triệu đồng") in signals.amounts_and_percents
    assert QuantitySpan(20.0, "percent", "20%") in signals.amounts_and_percents
    assert QuantitySpan(2.0, "ban", "02 bản") in signals.amounts_and_percents


def test_deontic_polarities_distinguish_prohibition_permission_obligation() -> None:
    assert extract_normative_signals("Tổ chức được phép khai thác.").deontic_polarities == (
        frozenset({"permission"})
    )
    assert extract_normative_signals("Tổ chức có quyền khai thác.").deontic_polarities == (
        frozenset({"permission"})
    )
    assert extract_normative_signals("Nghiêm cấm khai thác.").deontic_polarities == (
        frozenset({"prohibition"})
    )
    assert extract_normative_signals("Không được khai thác.").deontic_polarities == (
        frozenset({"prohibition"})
    )
    assert extract_normative_signals("Tổ chức phải khai thác.").deontic_polarities == (
        frozenset({"obligation"})
    )
    assert extract_normative_signals("Hồ sơ chưa đầy đủ.").deontic_polarities == (
        frozenset({"negation"})
    )
    both = extract_normative_signals(
        "Trước đây được phép khai thác, nay nghiêm cấm khai thác."
    ).deontic_polarities
    assert both == frozenset({"permission", "prohibition"})


def test_exception_condition_and_subject_tokens() -> None:
    signals = extract_normative_signals(
        "Cơ quan phải kiểm tra hồ sơ, trừ trường hợp khẩn cấp, nếu có yêu cầu."
    )
    assert signals.has_exception
    assert "trừ trường hợp" in signals.exception_phrases
    assert signals.has_condition
    # "hồ" -> "ho", "tra" -> "tra"; "phải" is a stopword.  ("sơ" folds to "so", which the
    # shared checks._STOP table lists for "số" — a known collision of the reused table.)
    assert "ho" in signals.subject_tokens and "tra" in signals.subject_tokens
    assert "phai" not in signals.subject_tokens  # stopword removed


def test_signals_empty_text() -> None:
    signals = extract_normative_signals("")
    assert signals.deadlines == ()
    assert signals.amounts_and_percents == ()
    assert signals.dates == frozenset()
    assert signals.plain_numbers == frozenset()
    assert signals.deontic_polarities == frozenset()
    assert not signals.has_exception and not signals.has_condition
    assert signals.subject_tokens == frozenset()


def test_number_parser_total_for_regex_accepted_forms() -> None:
    # Review fix 1: US-format thousands commas must parse, not crash (probe input 1).
    signals = extract_normative_signals("Phạt 1,234,567 đồng.")
    assert QuantitySpan(1234567.0, "dong", "1,234,567 đồng") in signals.amounts_and_percents
    # Mangled OCR groups (probe input 2): documented best effort, never an exception.
    mangled = extract_normative_signals("Phạt 1.23.45 đồng.")
    assert mangled.amounts_and_percents[0].value_num == 123.45
    # Mixed conventions: the last separator is the decimal one.
    vi = extract_normative_signals("Phạt 1.234,56 đồng.")
    assert vi.amounts_and_percents[0].value_num == 1234.56
    us = extract_normative_signals("Phạt 1,234.56 đồng.")
    assert us.amounts_and_percents[0].value_num == 1234.56
    # Single ",NNN" group with decimal comma is a decimal, never thousands.
    dec_pct = extract_normative_signals("Lãi suất 0,125% mỗi năm.")
    assert QuantitySpan(0.125, "percent", "0,125%") in dec_pct.amounts_and_percents
    dec_money = extract_normative_signals("Hạn mức 1,125 tỷ đồng.")
    assert QuantitySpan(1.125, "ty_dong", "1,125 tỷ đồng") in dec_money.amounts_and_percents


def test_single_group_comma_decimal_differs_from_thousands_in_diff() -> None:
    pct_left = _node("dieu:1/khoan:1", "Áp dụng mức 0,125%.", ordinal=0)
    pct_right = _node("dieu:1/khoan:1", "Áp dụng mức 0,5%.", ordinal=0)
    pct_diff = diff_pair(
        AlignedPair(left=pct_left, right=pct_right, alignment_method="structural_key")
    )
    assert pct_diff.change_kind == "modified"
    assert pct_diff.signals.amounts_changed
    assert pct_diff.signals.impact_level == "high"

    amt_left = _node("dieu:1/khoan:2", "Hạn mức 1,125 tỷ đồng.", ordinal=1)
    amt_right = _node("dieu:1/khoan:2", "Hạn mức 1125 tỷ đồng.", ordinal=1)
    amt_diff = diff_pair(
        AlignedPair(left=amt_left, right=amt_right, alignment_method="structural_key")
    )
    assert amt_diff.change_kind == "modified"
    assert [s.value_num for s in amt_diff.signals.amounts_changed] == [1.125, 1125.0]
    assert amt_diff.signals.impact_level == "high"


def test_us_format_amount_does_not_abort_comparison() -> None:
    left = _node("dieu:1/khoan:1", "Phạt 1,234,567 đồng.", ordinal=0)
    right = _node("dieu:1/khoan:1", "Phạt 2,000,000 đồng.", ordinal=0)
    pairs = align_nodes([left], [right], mode="cross_document")
    assert len(pairs) == 1
    result = diff_pair(pairs[0])
    assert result.change_kind == "modified"
    assert result.signals.amounts_changed
    assert result.signals.impact_level == "high"


def test_partial_dates_do_not_become_deadlines() -> None:
    # Review fix 2: month-year and day-month dates are dates, not durations.
    assert extract_normative_signals("Hiệu lực từ tháng 7 năm 2030.").deadlines == ()
    assert extract_normative_signals("Từ ngày 01 tháng 7.").deadlines == ()
    assert extract_normative_signals("Từ ngày 01 tháng 7 năm 2030.").deadlines == ()
    # Genuine durations must survive the partial-date pre-strip.
    assert DeadlineSpan(7.0, "nam", "7 năm") in extract_normative_signals(
        "trong 7 năm"
    ).deadlines
    assert DeadlineSpan(1.0, "thang", "01 tháng") in extract_normative_signals(
        "gia hạn 01 tháng"
    ).deadlines
    assert DeadlineSpan(10.0, "ngay", "10 ngày") in extract_normative_signals(
        "trong 10 ngày kể từ ngày 01 tháng 7"
    ).deadlines


def test_month_only_date_change_stays_medium() -> None:
    left = _node("dieu:1/khoan:1", "Hiệu lực từ tháng 7 năm 2030.", ordinal=0)
    right = _node("dieu:1/khoan:1", "Hiệu lực từ tháng 8 năm 2030.", ordinal=0)
    pair = AlignedPair(left=left, right=right, alignment_method="structural_key")
    result = diff_pair(pair)
    assert result.change_kind == "modified"
    assert not result.signals.deadlines_changed
    assert result.signals.impact_level == "medium"


# --------------------------------------------------------------- align scenarios


def test_align_scenario_1_deadline_and_modality_change() -> None:
    left = [
        _node("dieu:1/khoan:1", "Quy định chung về phạm vi điều chỉnh.", ordinal=0),
        _node("dieu:2/khoan:1",
              "Tổ chức, cá nhân được phép nộp hồ sơ trong thời hạn 10 ngày "
              "kể từ ngày nhận được thông báo.", ordinal=1),
        _node("dieu:3/khoan:1", "Điều khoản thi hành và hiệu lực.", ordinal=2),
    ]
    right = [
        _node("dieu:1/khoan:1", "Quy định chung về phạm vi điều chỉnh.", ordinal=0),
        _node("dieu:2/khoan:1",
              "Tổ chức, cá nhân nghiêm cấm nộp hồ sơ trong thời hạn 15 ngày "
              "kể từ ngày nhận được thông báo.", ordinal=1),
        _node("dieu:3/khoan:1", "Điều khoản thi hành và hiệu lực.", ordinal=2),
    ]
    pairs = align_nodes(left, right, mode="versions")
    assert len(pairs) == 3
    changed = next(p for p in pairs if p.left and p.left.structural_key == "dieu:2/khoan:1")
    assert changed.alignment_method == "structural_key"
    result = diff_pair(changed)
    assert result.change_kind == "modified"
    assert result.signals.impact_level == "high"
    assert result.signals.deadlines_changed
    assert result.signals.modality_shifted
    assert {s.value_num for s in result.signals.deadlines_changed} == {10.0, 15.0}
    others = [p for p in pairs if p is not changed]
    assert all(diff_pair(p).change_kind == "unchanged" for p in others)


def test_align_scenario_2_inserted_article_renumbering() -> None:
    # Clause-level nodes: the clause text itself does not repeat the article number, so a
    # renumbered clause keeps identical content while its structural key shifts.
    old_d2 = "Huấn luyện an toàn lao động cho người lao động trong doanh nghiệp."
    old_d3 = "Khai thác khoáng sản và bảo vệ môi trường mỏ."
    new_d2 = "Quản lý thu chi ngân sách và kiểm soát kinh phí công đoàn."
    left = [
        _node("dieu:1/khoan:1", "Quy định chung về phạm vi điều chỉnh.", ordinal=0),
        _node("dieu:2/khoan:1", old_d2, ordinal=1),
        _node("dieu:3/khoan:1", old_d3, ordinal=2),
    ]
    right = [
        _node("dieu:1/khoan:1", "Quy định chung về phạm vi điều chỉnh.", ordinal=0),
        _node("dieu:2/khoan:1", new_d2, ordinal=1),
        _node("dieu:3/khoan:1", old_d2, ordinal=2),
        _node("dieu:4/khoan:1", old_d3, ordinal=3),
    ]
    pairs = align_nodes(left, right, mode="versions")
    # Old Điều 2 must NOT be reported as removed + new Điều 3 as added.
    removed_keys = [p.left.structural_key for p in pairs if p.right is None and p.left]
    added_keys = [p.right.structural_key for p in pairs if p.left is None and p.right]
    assert removed_keys == []
    assert added_keys == ["dieu:2/khoan:1"]
    moved = [p for p in pairs if p.left and p.right
             and p.left.structural_key != p.right.structural_key]
    assert {(p.left.structural_key, p.right.structural_key) for p in moved} == (
        {("dieu:2/khoan:1", "dieu:3/khoan:1"), ("dieu:3/khoan:1", "dieu:4/khoan:1")}
    )
    for pair in moved:
        assert pair.alignment_method == "semantic_lexical"
        result = diff_pair(pair)
        assert result.change_kind == "moved_or_renumbered"
        assert not result.content_also_modified


def test_align_scenario_2_reading_order_inserts_added_in_place() -> None:
    left = [
        _node("dieu:1", "Điều 1. Phạm vi điều chỉnh.", ordinal=0, node_type="article"),
        _node("dieu:3", "Điều 3. Kiểm định thiết bị an toàn.", ordinal=1, node_type="article"),
    ]
    right = [
        _node("dieu:1", "Điều 1. Phạm vi điều chỉnh.", ordinal=0, node_type="article"),
        _node("dieu:2", "Điều 2. Quản lý thu chi ngân sách công đoàn.", ordinal=1,
              node_type="article"),
        _node("dieu:3", "Điều 3. Kiểm định thiết bị an toàn.", ordinal=2, node_type="article"),
    ]
    pairs = align_nodes(left, right, mode="versions")
    order = [(p.left.structural_key if p.left else None,
              p.right.structural_key if p.right else None) for p in pairs]
    assert order == [("dieu:1", "dieu:1"), (None, "dieu:2"), ("dieu:3", "dieu:3")]


def test_align_scenario_3_administrative_text_without_dieu() -> None:
    left = [
        _node("", "I. Mục đích và phạm vi của kế hoạch.", ordinal=0, node_type="heading"),
        _node("doan", "Kế hoạch nhằm nâng cao chất lượng dịch vụ công trực tuyến.",
              ordinal=1, node_type="paragraph"),
        _node("", "II. Nhiệm vụ và giải pháp thực hiện.", ordinal=2, node_type="heading"),
        _node("doan", "Các đơn vị triển khai đào tạo cán bộ và kiểm tra định kỳ.",
              ordinal=3, node_type="paragraph"),
    ]
    right = [
        _node("", "I. Mục đích và phạm vi của kế hoạch.", ordinal=0, node_type="heading"),
        _node("doan", "Kế hoạch nhằm nâng cao chất lượng dịch vụ công trực tuyến mức độ bốn.",
              ordinal=1, node_type="paragraph"),
        _node("", "II. Nhiệm vụ và giải pháp thực hiện.", ordinal=2, node_type="heading"),
        _node("doan", "Các đơn vị triển khai đào tạo cán bộ và kiểm tra đột xuất.",
              ordinal=3, node_type="paragraph"),
    ]
    pairs = align_nodes(left, right, mode="versions")
    assert len(pairs) == 4
    assert all(p.left is not None and p.right is not None for p in pairs)
    assert all(p.alignment_method == "semantic_lexical" for p in pairs)
    # Correct heading + lexical alignment: each left node pairs with its counterpart.
    for index, pair in enumerate(pairs):
        assert pair.left is left[index]
        assert pair.right is right[index]
    kinds = [diff_pair(p).change_kind for p in pairs]
    assert kinds == ["unchanged", "modified", "unchanged", "modified"]


def test_align_scenario_4_explicit_amendment_link_wins() -> None:
    left_id, right_id = uuid4(), uuid4()
    left = [_node("dieu:5/khoan:2", "Nội dung cũ của khoản 2 Điều 5.", ordinal=0,
                  node_id=left_id)]
    right = [_node("dieu:5/khoan:2", "Nội dung mới thay thế khoản 2 Điều 5.", ordinal=0,
                   node_id=right_id)]
    link = AmendmentLink(
        source_node_id=left_id,
        target_path="dieu:5/khoan:2",
        action="replace",
        valid_from=date(2030, 1, 1),
        source_quote="Thay thế khoản 2 Điều 5 như sau:",
    )
    pairs = align_nodes(left, right, [link], mode="amendment_pair")
    assert len(pairs) == 1
    pair = pairs[0]
    assert pair.alignment_method == "explicit_amendment"
    assert pair.amendment_action == "replace"
    assert pair.valid_from == date(2030, 1, 1)
    assert pair.source_quote == "Thay thế khoản 2 Điều 5 như sau:"
    assert diff_pair(pair).change_kind == "modified"


def test_align_explicit_link_by_target_node_id_and_member_id() -> None:
    owner_id, part_id, right_id = uuid4(), uuid4(), uuid4()
    left = stitch_logical_nodes([
        _record("000003:dieu:2/khoan:1", "A", node_id=owner_id),
        _record("000004:dieu:2/khoan:1/tiep:2", "B", node_type="paragraph", node_id=part_id),
    ])
    right = [_node("dieu:2/khoan:1", "Nội dung sửa đổi.", ordinal=0, node_id=right_id)]
    link = AmendmentLink(source_node_id=part_id, target_node_id=right_id, action="modify")
    pairs = align_nodes(left, right, [link], mode="amendment_pair")
    assert len(pairs) == 1
    assert pairs[0].alignment_method == "explicit_amendment"
    assert pairs[0].amendment_action == "modify"


def test_align_explicit_link_right_to_left_by_target_node_id_and_target_path() -> None:
    left_id, left_part_id, right_id = uuid4(), uuid4(), uuid4()
    left = stitch_logical_nodes([
        _record("000005:dieu:5/khoan:2", "Quy định gốc.", node_id=left_id),
        _record("000006:dieu:5/khoan:2/tiep:2", "Phần tiếp theo.", node_type="paragraph",
                node_id=left_part_id),
    ])
    right = [_node("dieu:1/khoan:1", "Sửa đổi khoản 2 Điều 5.", ordinal=0, node_id=right_id)]

    by_id = AmendmentLink(
        source_node_id=right_id,
        target_node_id=left_part_id,
        action="modify",
        valid_from=date(2030, 5, 1),
        source_quote="Sửa đổi khoản 2 Điều 5:",
        direction="right_to_left",
    )
    pairs_id = align_nodes(left, right, [by_id], mode="amendment_pair")
    assert len(pairs_id) == 1
    assert pairs_id[0].alignment_method == "explicit_amendment"
    assert pairs_id[0].left is left[0]
    assert pairs_id[0].right is right[0]
    assert pairs_id[0].amendment_action == "modify"
    assert pairs_id[0].valid_from == date(2030, 5, 1)

    by_path = AmendmentLink(
        source_node_id=right_id,
        target_path="000005:dieu:05/khoan:02",
        action="replace",
        direction="right_to_left",
    )
    pairs_path = align_nodes(left, right, [by_path], mode="amendment_pair")
    assert len(pairs_path) == 1
    assert pairs_path[0].alignment_method == "explicit_amendment"
    assert pairs_path[0].left is left[0]
    assert pairs_path[0].right is right[0]
    assert pairs_path[0].amendment_action == "replace"


def test_align_explicit_link_blank_or_bare_ordinal_target_path_skips_unkeyed() -> None:
    src_a, src_b = uuid4(), uuid4()
    left = [
        _node("000001:doan", "Sửa đổi đoạn mở đầu về chế độ báo cáo.", ordinal=0, node_id=src_a),
        _node("000002:doan", "Bổ sung đoạn quy định xử lý vi phạm.", ordinal=1, node_id=src_b),
    ]
    unkeyed = stitch_logical_nodes([
        _record("000001", "Nội dung đoạn văn chưa gắn số hiệu điều khoản.", node_type="paragraph"),
    ])
    assert unkeyed[0].structural_key == ""
    links = [
        AmendmentLink(source_node_id=src_a, target_path="000001", action="modify"),
        AmendmentLink(source_node_id=src_b, target_path="   ", action="replace"),
    ]
    pairs = align_nodes(left, unkeyed, links, mode="amendment_pair")
    assert all(p.alignment_method != "explicit_amendment" for p in pairs)


def test_align_empty_inputs() -> None:
    assert align_nodes([], [], mode="versions") == []
    node = _node("dieu:1", "Điều 1. Nội dung.", ordinal=0, node_type="article")
    only_left = align_nodes([node], [], mode="versions")
    assert len(only_left) == 1 and only_left[0].right is None
    assert diff_pair(only_left[0]).change_kind == "removed"
    only_right = align_nodes([], [node], mode="versions")
    assert len(only_right) == 1 and only_right[0].left is None
    assert diff_pair(only_right[0]).change_kind == "added"


def test_align_tier3_uses_embeddings_when_present() -> None:
    left = [_node("dieu:2", "Điều 2. Huấn luyện an toàn lao động.", ordinal=0,
                  node_type="article", embedding=(1.0, 0.0))]
    right = [
        _node("dieu:3", "Điều 3. Huấn luyện an toàn lao động.", ordinal=0,
              node_type="article", embedding=(1.0, 0.0)),
        _node("dieu:9", "Điều 9. Quản lý thu chi ngân sách.", ordinal=1,
              node_type="article", embedding=(0.0, 1.0)),
    ]
    pairs = align_nodes(left, right, mode="versions")
    matched = [p for p in pairs if p.left and p.right]
    assert len(matched) == 1
    assert matched[0].right.structural_key == "dieu:3"
    assert matched[0].score is not None and matched[0].score >= 0.42


# --------------------------------------------------------------- token diff


def test_token_diff_keeps_nfc_diacritics_and_whole_words() -> None:
    segments = compute_token_diff("được phép nộp 10 ngày", "nghiêm cấm nộp 15 ngày")
    assert all(unicodedata.is_normalized("NFC", seg.text) for seg in segments)
    delete_words = [w for seg in segments if seg.op == "delete" for w in seg.text.split()]
    insert_words = [w for seg in segments if seg.op == "insert" for w in seg.text.split()]
    equal_text = "".join(seg.text for seg in segments if seg.op == "equal")
    assert {"được", "phép", "10"} <= set(delete_words)
    assert {"nghiêm", "cấm", "15"} <= set(insert_words)
    # Shared words stay in equal segments; no syllable is ever cut in half.
    assert "nộp" in equal_text and "ngày" in equal_text
    assert "ngà" not in delete_words + insert_words
    assert all(seg.op in {"equal", "delete", "insert"} for seg in segments)


def test_token_diff_merges_adjacent_same_op_segments() -> None:
    segments = compute_token_diff("a b c d", "a x c y")
    assert all(prev.op != curr.op for prev, curr in zip(segments, segments[1:]))
    assert "".join(seg.text for seg in segments if seg.op in {"equal", "delete"}) == "a b c d"
    assert "".join(seg.text for seg in segments if seg.op in {"equal", "insert"}) == "a x c y"


def test_token_diff_identical_and_empty() -> None:
    same = compute_token_diff("một hai ba", "một hai ba")
    assert same == [DiffSegment(op="equal", text="một hai ba")]
    assert compute_token_diff("", "") == []
    inserted = compute_token_diff("", "mới")
    assert inserted == [DiffSegment(op="insert", text="mới")]
    deleted = compute_token_diff("cũ", "")
    assert deleted == [DiffSegment(op="delete", text="cũ")]


def test_whitespace_noise_is_unchanged() -> None:
    left = _node("dieu:1/khoan:1", "Nội   dung\tkhoản  1.", ordinal=0)
    right = _node("dieu:1/khoan:1", "Nội dung khoản 1.", ordinal=0)
    pair = AlignedPair(left=left, right=right, alignment_method="structural_key")
    result = diff_pair(pair)
    assert result.change_kind == "unchanged"
    assert result.signals.impact_level == "low"
    assert not result.signals.deadlines_changed
    # Newline noise (OCR line breaks) is not a content change either.
    left_nl = _node("dieu:1/khoan:1", "Nội dung\nkhoản 1.", ordinal=0)
    pair_nl = AlignedPair(left=left_nl, right=right, alignment_method="structural_key")
    assert diff_pair(pair_nl).change_kind == "unchanged"


def test_diff_moved_with_content_change_flags_content_also_modified() -> None:
    left = _node("dieu:2", "Điều 2. Huấn luyện an toàn lao động.", ordinal=0,
                 node_type="article")
    right = _node("dieu:3", "Điều 3. Huấn luyện an toàn lao động bắt buộc.", ordinal=0,
                  node_type="article")
    pair = AlignedPair(left=left, right=right, alignment_method="semantic_lexical")
    result = diff_pair(pair)
    assert result.change_kind == "moved_or_renumbered"
    assert result.content_also_modified
    assert result.signals.modality_shifted  # "bắt buộc" adds obligation
    assert result.signals.impact_level == "high"


def test_diff_date_only_change_is_not_high_impact() -> None:
    left = _node("dieu:1/khoan:1", "Báo cáo nộp trước ngày 01/7/2030.", ordinal=0)
    right = _node("dieu:1/khoan:1", "Báo cáo nộp trước ngày 01/8/2030.", ordinal=0)
    pair = AlignedPair(left=left, right=right, alignment_method="structural_key")
    result = diff_pair(pair)
    assert result.change_kind == "modified"
    assert result.signals.dates_changed == ((1, 7, 2030), (1, 8, 2030))
    assert result.signals.impact_level == "medium"


def test_diff_minor_wording_change_is_low_impact() -> None:
    left = _node("dieu:1/khoan:1", "Cơ quan tiếp nhận hồ sơ trực tiếp.", ordinal=0)
    right = _node("dieu:1/khoan:1", "Cơ quan tiếp nhận hồ sơ trực tuyến.", ordinal=0)
    pair = AlignedPair(left=left, right=right, alignment_method="structural_key")
    result = diff_pair(pair)
    assert result.change_kind == "modified"
    assert result.signals.impact_level == "low"
    assert not result.signals.modality_shifted
