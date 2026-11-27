"""Unit tests for candidate pairer & deterministic conflict signal detector (Phase 2, D3).

Pure unit tests: no PostgreSQL, no LLM, no network. Uses fictional legal texts (HƯ CẤU).
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.analysis.signals import NodeRecord
from app.conflicts.detector import (
    ApprovedNodeAmendment,
    ApprovedNodeReference,
    CandidatePair,
    DocumentNodesInput,
    ScopedLogicalNode,
    classify_candidate_pair,
    detect_conflict_candidates,
    fetch_pgvector_candidate_similarities,
    filter_normative_nodes,
    generate_candidate_pairs,
)
from app.schemas import AmendmentStatus


def _doc_input(
    records: list[NodeRecord],
    *,
    document_id: UUID | None = None,
    status: AmendmentStatus | str = AmendmentStatus.ACTIVE,
    document_number: str | None = None,
) -> DocumentNodesInput:
    return DocumentNodesInput(
        document_id=document_id or uuid4(),
        records=records,
        effective_status_at_date=status,
        document_number=document_number,
    )


def _record(
    path: str,
    text: str,
    *,
    node_type: str = "clause",
    node_id: UUID | None = None,
    embedding: tuple[float, ...] | None = None,
    taxonomy_codes: tuple[str, ...] = (),
) -> NodeRecord:
    return NodeRecord(
        node_id=node_id or uuid4(),
        node_type=node_type,
        path=path,
        text_original=text,
        embedding=embedding,
        taxonomy_codes=taxonomy_codes,
    )


def _single_scoped(
    text: str,
    *,
    doc_id: UUID | None = None,
    node_id: UUID | None = None,
    path: str = "000001:dieu:1/khoan:1",
    node_type: str = "clause",
    status: AmendmentStatus | str = AmendmentStatus.ACTIVE,
    document_number: str | None = None,
    embedding: tuple[float, ...] | None = None,
    taxonomy_codes: tuple[str, ...] = (),
) -> ScopedLogicalNode:
    filtered = filter_normative_nodes(
        [
            _doc_input(
                [
                    _record(
                        path,
                        text,
                        node_type=node_type,
                        node_id=node_id,
                        embedding=embedding,
                        taxonomy_codes=taxonomy_codes,
                    )
                ],
                document_id=doc_id,
                status=status,
                document_number=document_number,
            )
        ],
        include_expired=True,
    )
    assert len(filtered) == 1
    return filtered[0]


# ------------------------------------------------------------------ Scenario 1..6


def test_scenario_1_deadline_divergence_contradiction_high() -> None:
    """Scenario 1: 5 ngày làm việc vs 15 ngày làm việc -> contradiction, high."""
    node_a = _single_scoped(
        "Thời hạn giải quyết cấp giấy phép kinh doanh là 5 ngày làm việc "
        "kể từ ngày nhận đủ hồ sơ hợp lệ.",
        taxonomy_codes=("thoi_han", "trinh_tu_thu_tuc"),
    )
    node_b = _single_scoped(
        "Cơ quan có thẩm quyền thực hiện cấp giấy phép kinh doanh trong thời hạn "
        "15 ngày làm việc kể từ ngày nhận đủ hồ sơ.",
        taxonomy_codes=("thoi_han",),
    )

    pairs = generate_candidate_pairs([node_a, node_b])
    assert len(pairs) == 1
    finding = classify_candidate_pair(pairs[0])
    assert finding is not None
    assert finding.finding_type == "contradiction"
    assert finding.severity == "high"
    assert "deadline_divergence" in finding.signals_json["signals"]


def test_scenario_2_deontic_polarity_conflict_contradiction_high() -> None:
    """Scenario 2: nghiêm cấm ủy quyền vs được phép ủy quyền -> contradiction, high."""
    node_a = _single_scoped(
        "Nghiêm cấm ủy quyền giải quyết thủ tục hành chính cấp giấy phép xây dựng.",
        taxonomy_codes=("vi_pham_xu_ly",),
    )
    node_b = _single_scoped(
        "Thủ trưởng cơ quan được phép ủy quyền cho cấp phó giải quyết thủ tục hành chính "
        "cấp giấy phép xây dựng.",
        taxonomy_codes=("vi_pham_xu_ly", "tham_quyen_trach_nhiem"),
    )

    pairs = generate_candidate_pairs([node_a, node_b])
    assert len(pairs) == 1
    finding = classify_candidate_pair(pairs[0])
    assert finding is not None
    assert finding.finding_type == "contradiction"
    assert finding.severity == "high"
    assert "deontic_polarity_conflict" in finding.signals_json["signals"]


def test_scenario_3_exception_qualification_low_not_contradiction() -> None:
    """Scenario 3: Divergence with explicit exception phrase -> exception_refinement, low (R3)."""
    node_a = _single_scoped(
        "Nghiêm cấm ủy quyền giải quyết thủ tục hành chính cấp giấy phép xây dựng.",
        taxonomy_codes=("vi_pham_xu_ly",),
    )
    node_b = _single_scoped(
        "Thủ trưởng cơ quan được phép ủy quyền giải quyết thủ tục hành chính "
        "cấp giấy phép xây dựng, trừ trường hợp đặc biệt theo quy định của Bộ chuyên ngành.",
        taxonomy_codes=("vi_pham_xu_ly",),
    )

    pairs = generate_candidate_pairs([node_a, node_b])
    assert len(pairs) == 1
    finding = classify_candidate_pair(pairs[0])
    assert finding is not None
    assert finding.finding_type == "exception_refinement"
    assert finding.severity == "low"
    assert "exception_qualification" in finding.signals_json["signals"]


def test_scenario_4_unlinked_parallel_overlap_medium() -> None:
    """Scenario 4: Independent co-effective docs repeating same obligation -> overlap, medium."""
    node_a = _single_scoped(
        "Doanh nghiệp phải lưu giữ hồ sơ kiểm định an toàn thiết bị nâng "
        "trong thời hạn 05 năm tại trụ sở chính.",
        status=AmendmentStatus.ACTIVE,
        taxonomy_codes=("quyen_nghia_vu",),
    )
    node_b = _single_scoped(
        "Doanh nghiệp có trách nhiệm lưu giữ hồ sơ kiểm định an toàn thiết bị nâng "
        "trong thời hạn 05 năm tại trụ sở.",
        status=AmendmentStatus.MODIFIED,
        taxonomy_codes=("quyen_nghia_vu",),
    )

    pairs = generate_candidate_pairs([node_a, node_b])
    assert len(pairs) == 1
    finding = classify_candidate_pair(pairs[0])
    assert finding is not None
    assert finding.finding_type == "overlap"
    assert finding.severity == "medium"
    assert "scope_overlap_without_link" in finding.signals_json["signals"]


def test_scenario_5_unrelated_topics_with_same_number_filtered_out() -> None:
    """Scenario 5: PCCC vs kế toán tài chính with '10 ngày' -> low subject_overlap, dropped."""
    node_a = _single_scoped(
        "Chủ cơ sở thuộc diện quản lý về phòng cháy chữa cháy phải gửi thông báo "
        "kết quả kiểm tra an toàn cháy nổ trong thời hạn 10 ngày.",
        taxonomy_codes=("thoi_han",),
    )
    node_b = _single_scoped(
        "Đơn vị kế toán tài chính phải lập bảng cân đối phát sinh và nộp tờ khai "
        "quyết toán thuế trong thời hạn 10 ngày.",
        taxonomy_codes=("thoi_han",),
    )

    pairs = generate_candidate_pairs([node_a, node_b])
    assert pairs == []
    # Even if forced into classify_candidate_pair directly, subject_overlap guard drops it
    forced = CandidatePair(
        node_a=node_a,
        node_b=node_b,
        shared_labels=("thoi_han",),
        subject_overlap=0.10,
        lexical_bigram=0.05,
        similarity_score=None,
        channels=("taxonomy",),
        priority_score=0.10,
    )
    assert classify_candidate_pair(forced) is None


def test_scenario_6_approved_amendment_superseded_already_low() -> None:
    """Scenario 6: Pair with approved node_amendments -> superseded_already, low (R3)."""
    doc_a = uuid4()
    doc_b = uuid4()
    id_a = uuid4()
    id_b = uuid4()
    node_a = _single_scoped(
        "Thời hạn giải quyết cấp giấy phép kinh doanh là 5 ngày làm việc "
        "kể từ ngày nhận đủ hồ sơ hợp lệ.",
        doc_id=doc_a,
        node_id=id_a,
        taxonomy_codes=("thoi_han",),
    )
    node_b = _single_scoped(
        "Thời hạn giải quyết cấp giấy phép kinh doanh là 15 ngày làm việc "
        "kể từ ngày nhận đủ hồ sơ hợp lệ.",
        doc_id=doc_b,
        node_id=id_b,
        taxonomy_codes=("thoi_han",),
    )

    amendment = ApprovedNodeAmendment(
        source_document_id=doc_b,
        target_document_id=doc_a,
        source_node_id=id_b,
        target_node_id=id_a,
        action="modify",
        valid_from=date(2025, 1, 1),
        approved=True,
    )
    findings = detect_conflict_candidates(
        [node_a, node_b],
        approved_amendments=[amendment],
    )
    assert len(findings) == 1
    assert findings[0].finding_type == "superseded_already"
    assert findings[0].severity == "low"


# ------------------------------------------------------------------ Filtering & stitching


def test_filter_normative_nodes_stitches_tiep_and_skips_short_headings() -> None:
    doc_id = uuid4()
    heading_short = _record("000001:chuong:I", "Chương I. QUY ĐỊNH CHUNG", node_type="chapter")
    heading_long = _record(
        "000002:muc:1",
        "Mục 1. Quy định chi tiết về trình tự thủ tục cấp giấy phép đầu tư kinh doanh có điều kiện",
        node_type="section",
    )
    clause_short = _record(
        "000003:dieu:1/khoan:1",
        "Nghiêm cấm hành vi gian lận.",
        node_type="clause",
    )
    parent = _record(
        "000004:dieu:2/khoan:1",
        "Hồ sơ đề nghị cấp phép gồm đơn đề nghị theo mẫu quy định.",
        node_type="clause",
    )
    cont = _record(
        "000005:dieu:2/khoan:1/tiep:1",
        "Bản sao giấy chứng nhận đăng ký doanh nghiệp còn hiệu lực.",
        node_type="paragraph",
    )

    stitched = filter_normative_nodes(
        [_doc_input([heading_short, heading_long, clause_short, parent, cont], document_id=doc_id)]
    )
    assert len(stitched) == 3
    assert stitched[0].node.primary_node_id == heading_long.node_id
    assert stitched[1].node.primary_node_id == clause_short.node_id
    assert stitched[2].node.primary_node_id == parent.node_id
    assert stitched[2].node.member_node_ids == (parent.node_id, cont.node_id)
    assert "đăng ký doanh nghiệp" in stitched[2].node.text_original


def test_filter_normative_nodes_respects_real_amendment_statuses() -> None:
    """Ruling P3: exclude repealed/replaced/not_yet_effective when include_expired=False."""
    docs = [
        _doc_input(
            [_record("000001:dieu:1", "Quy định đang có hiệu lực về hồ sơ đấu thầu.")],
            status=AmendmentStatus.ACTIVE,
        ),
        _doc_input(
            [_record("000001:dieu:1", "Quy định đã sửa đổi bổ sung về hồ sơ đấu thầu.")],
            status=AmendmentStatus.MODIFIED,
        ),
        _doc_input(
            [_record("000001:dieu:1", "Quy định tạm ngưng hiệu lực về hồ sơ đấu thầu.")],
            status=AmendmentStatus.SUSPENDED,
        ),
        _doc_input(
            [_record("000001:dieu:1", "Quy định chưa xác minh trạng thái hiệu lực về hồ sơ.")],
            status=AmendmentStatus.UNKNOWN,
        ),
        _doc_input(
            [_record("000001:dieu:1", "Quy định đã bị bãi bỏ về hồ sơ đấu thầu.")],
            status=AmendmentStatus.REPEALED,
        ),
        _doc_input(
            [_record("000001:dieu:1", "Quy định đã bị thay thế về hồ sơ đấu thầu.")],
            status=AmendmentStatus.REPLACED,
        ),
        _doc_input(
            [_record("000001:dieu:1", "Quy định chưa có hiệu lực thi hành về hồ sơ đấu thầu.")],
            status=AmendmentStatus.NOT_YET_EFFECTIVE,
        ),
    ]

    default_filtered = filter_normative_nodes(docs, include_expired=False)
    assert [item.effective_status_at_date for item in default_filtered] == [
        "active",
        "modified",
        "suspended",
        "unknown",
    ]

    with_expired = filter_normative_nodes(docs, include_expired=True)
    assert len(with_expired) == 7


# ------------------------------------------------------------------ Capping & dedup


def test_generate_candidate_pairs_caps_per_node_and_max_pairs_and_deduplicates() -> None:
    anchor_doc = uuid4()
    anchor_node = _single_scoped(
        "Cơ quan quản lý nhà nước cấp giấy phép kinh doanh vận tải hành khách theo quy định.",
        doc_id=anchor_doc,
        taxonomy_codes=("trinh_tu_thu_tuc",),
    )
    same_doc_node = _single_scoped(
        "Cơ quan quản lý nhà nước cấp giấy phép kinh doanh vận tải hành khách nội địa.",
        doc_id=anchor_doc,
        taxonomy_codes=("trinh_tu_thu_tuc",),
    )
    others = [
        _single_scoped(
            f"Cơ quan quản lý nhà nước cấp giấy phép kinh doanh vận tải hành khách tuyến số {i}.",
            taxonomy_codes=("trinh_tu_thu_tuc",),
        )
        for i in range(6)
    ]

    pairs = generate_candidate_pairs(
        [anchor_node, same_doc_node, *others],
        max_pairs=8,
        max_pairs_per_node=3,
    )
    assert len(pairs) <= 8
    # Same-document pair must never appear
    for pair in pairs:
        assert pair.node_a.document_id != pair.node_b.document_id
        assert pair.node_a.node.primary_node_id < pair.node_b.node.primary_node_id

    # Per-node degree cap <= 3
    counts: dict[UUID, int] = {}
    seen_keys: set[tuple[UUID, UUID]] = set()
    for pair in pairs:
        key = (pair.node_a.node.primary_node_id, pair.node_b.node.primary_node_id)
        assert key not in seen_keys
        seen_keys.add(key)
        counts[key[0]] = counts.get(key[0], 0) + 1
        counts[key[1]] = counts.get(key[1], 0) + 1
    assert counts[anchor_node.node.primary_node_id] <= 3
    assert all(count <= 3 for count in counts.values())
    # Sorted descending by priority_score
    scores = [p.priority_score for p in pairs]
    assert scores == sorted(scores, reverse=True)


# --------------------------------------------------------------- Numeric, authority, cross-ref


def test_numeric_threshold_divergence_and_unit_equivalence() -> None:
    node_a = _single_scoped(
        "Phạt tiền 5.000.000 đồng đối với hành vi chậm nộp báo cáo giám sát môi trường định kỳ.",
        taxonomy_codes=("vi_pham_xu_ly",),
    )
    node_b = _single_scoped(
        "Phạt tiền 15 triệu đồng đối với hành vi chậm nộp báo cáo giám sát môi trường định kỳ.",
        taxonomy_codes=("vi_pham_xu_ly",),
    )
    node_equiv = _single_scoped(
        "Phạt tiền 5 triệu đồng đối với hành vi chậm nộp báo cáo giám sát môi trường định kỳ.",
        taxonomy_codes=("vi_pham_xu_ly",),
    )

    pair_diff = generate_candidate_pairs([node_a, node_b])[0]
    finding_diff = classify_candidate_pair(pair_diff)
    assert finding_diff is not None
    assert finding_diff.finding_type == "contradiction"
    assert finding_diff.severity == "high"
    assert "numeric_threshold_divergence" in finding_diff.signals_json["signals"]

    # 5.000.000 đồng == 5 triệu đồng -> not a numeric divergence (overlap instead)
    pair_same = generate_candidate_pairs([node_a, node_equiv])[0]
    finding_same = classify_candidate_pair(pair_same)
    assert finding_same is not None
    assert "numeric_threshold_divergence" not in finding_same.signals_json["signals"]
    assert finding_same.finding_type == "overlap"


def test_deadline_convertible_equivalents_not_false_contradiction() -> None:
    node_a = _single_scoped(
        "Thời hạn thẩm định hồ sơ đăng ký kinh doanh là 1 tháng kể từ ngày nhận đủ hồ sơ.",
        taxonomy_codes=("thoi_han",),
    )
    node_b = _single_scoped(
        "Thời hạn thẩm định hồ sơ đăng ký kinh doanh là 30 ngày kể từ ngày nhận đủ hồ sơ.",
        taxonomy_codes=("thoi_han",),
    )
    pair = generate_candidate_pairs([node_a, node_b])[0]
    finding = classify_candidate_pair(pair)
    assert finding is not None
    assert "deadline_divergence" not in finding.signals_json["signals"]


def test_authority_divergence_medium() -> None:
    node_a = _single_scoped(
        "UBND tỉnh quyết định phê duyệt quy hoạch chi tiết khu công nghiệp trên địa bàn.",
        taxonomy_codes=("tham_quyen_trach_nhiem",),
    )
    node_b = _single_scoped(
        "Bộ Tài chính quyết định phê duyệt quy hoạch chi tiết khu công nghiệp trên địa bàn.",
        taxonomy_codes=("tham_quyen_trach_nhiem",),
    )

    pair = generate_candidate_pairs([node_a, node_b])[0]
    finding = classify_candidate_pair(pair)
    assert finding is not None
    assert finding.finding_type == "contradiction"
    assert finding.severity == "medium"
    assert "authority_divergence" in finding.signals_json["signals"]


def test_cross_reference_turns_divergence_into_exception_refinement() -> None:
    doc_a = uuid4()
    doc_b = uuid4()
    id_a = uuid4()
    id_b = uuid4()
    node_a = _single_scoped(
        "Thời hạn cấp giấy phép xuất khẩu là 5 ngày làm việc theo hồ sơ hợp lệ.",
        doc_id=doc_a,
        node_id=id_a,
        document_number="10/2023/NĐ-CP",
        taxonomy_codes=("thoi_han",),
    )
    node_b = _single_scoped(
        "Thời hạn cấp giấy phép xuất khẩu là 15 ngày làm việc đối với hồ sơ liên ngành.",
        doc_id=doc_b,
        node_id=id_b,
        document_number="22/2024/TT-BTC",
        taxonomy_codes=("thoi_han",),
    )

    ref = ApprovedNodeReference(
        source_node_id=id_b,
        target_node_id=id_a,
        target_document_id=doc_a,
        target_expression="10/2023/NĐ-CP",
        verified=True,
    )
    findings = detect_conflict_candidates([node_a, node_b], approved_references=[ref])
    assert len(findings) == 1
    assert findings[0].finding_type == "exception_refinement"
    assert findings[0].severity == "low"
    assert "exception_qualification" in findings[0].signals_json["signals"]

    # Also via explicit document_number citation in text without ApprovedNodeReference row
    node_c = _single_scoped(
        "Theo Nghị định số 10/2023/NĐ-CP, thời hạn cấp giấy phép xuất khẩu "
        "là 15 ngày làm việc đối với hồ sơ liên ngành.",
        doc_id=doc_b,
        node_id=id_b,
        document_number="22/2024/TT-BTC",
        taxonomy_codes=("thoi_han",),
    )
    findings_cited = detect_conflict_candidates([node_a, node_c])
    assert len(findings_cited) == 1
    assert findings_cited[0].finding_type == "exception_refinement"
    assert findings_cited[0].severity == "low"


def test_channel2_in_memory_cosine_similarity_pairs_and_detects_overlap() -> None:
    """Channel 2 works in-memory via LogicalNode.embedding without taxonomy labels or DB."""
    node_a = _single_scoped(
        "Doanh nghiệp thực hiện báo cáo định kỳ về an toàn lao động hàng năm.",
        embedding=(1.0, 0.0, 0.0),
        taxonomy_codes=(),
    )
    node_b = _single_scoped(
        "Đơn vị sử dụng lao động gửi thống kê tổng hợp về tai nạn nghề nghiệp định kỳ.",
        embedding=(0.95, 0.31, 0.0),  # cosine ~ 0.95 >= 0.84
        taxonomy_codes=(),
    )

    pairs = generate_candidate_pairs([node_a, node_b])
    assert len(pairs) == 1
    assert "vector" in pairs[0].channels
    assert pairs[0].similarity_score is not None and pairs[0].similarity_score >= 0.84

    finding = classify_candidate_pair(pairs[0])
    assert finding is not None
    assert finding.finding_type == "overlap"
    assert finding.severity == "medium"


@pytest.mark.asyncio
async def test_fetch_pgvector_candidate_similarities_uses_active_index_and_schema() -> None:
    """Ruling P7: verify SQL helper queries active_index and node_embeddings with exact columns."""
    id_a = UUID("00000000-0000-0000-0000-000000000001")
    id_b = UUID("00000000-0000-0000-0000-000000000002")
    idx_id = UUID("00000000-0000-0000-0000-000000000099")

    class FakeConn:
        def __init__(self, has_index: bool = True) -> None:
            self.has_index = has_index
            self.queries: list[tuple[str, tuple[Any, ...]]] = []

        async def fetchrow(self, sql: str, *args: Any) -> Any:
            self.queries.append((sql, args))
            if not self.has_index:
                return None
            return {
                "id": idx_id,
                "model_id": "test-model",
                "model_revision": "1",
                "dimensions": 768,
                "profile_key": "default",
                "node_count": 10,
                "completed_at": None,
            }

        async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
            self.queries.append((sql, args))
            return [{"node_a_id": id_b, "node_b_id": id_a, "similarity": 0.88123}]

    conn = FakeConn(has_index=True)
    result = await fetch_pgvector_candidate_similarities(conn, [id_a, id_b])
    assert result == {(id_a, id_b): pytest.approx(0.8812, abs=1e-4)}
    sql_executed = conn.queries[1][0]
    assert "document_node_id" in sql_executed
    assert "embedding_index_id" in sql_executed
    assert "vector(768)" in sql_executed
    assert "embedding_indices" in sql_executed
    assert "is_active" in sql_executed

    no_idx_conn = FakeConn(has_index=False)
    assert await fetch_pgvector_candidate_similarities(no_idx_conn, [id_a, id_b]) == {}
