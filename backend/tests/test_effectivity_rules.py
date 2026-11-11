"""G1/G3 hard effectivity rules (design §4).  Fixture texts are HƯ CẤU."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import pytest

from app.effectivity.extract import (
    NodeText,
    detect_dates,
    extract_relations,
    item_valid_from,
    number_key,
    parse_amend_item,
)
from app.effectivity.resolver import (
    NOTE_PENDING,
    Attestation,
    Relation,
    at_date,
    cap_verification,
    resolve_intervals,
)

D0 = date(2024, 1, 1)


def _status(intervals: list, day: date) -> tuple[str, str]:
    found = at_date(intervals, day)
    assert found is not None
    return found.status, found.verification


def test_rule1_active_verified_only_from_attestation() -> None:
    # No relation, no attestation: never "active + verified".
    intervals = resolve_intervals(effective_from=D0, relations=[])
    assert all(not (i.status == "active" and i.verification == "verified") for i in intervals)
    attested = resolve_intervals(
        effective_from=D0, relations=[],
        attestations=[Attestation("a1", "active", date(2024, 1, 1), date(2024, 6, 30), "valid",
                                  "reviewer", "2024-06-30T00:00:00", "Đối chiếu Công báo")],
    )
    assert _status(attested, date(2024, 3, 1)) == ("active", "verified")
    # Outside the attested period: not verified, with the earlier verification noted.
    status, verification = _status(attested, date(2024, 9, 1))
    assert (status, verification) == ("unknown", "unverified")
    assert any("Đã xác minh" in note for note in at_date(attested, date(2024, 9, 1)).notes)
    # Query-time guard: an "active + verified" that is not from an attestation is capped.
    assert cap_verification("active", "verified", "relation", as_of=D0, data_date=None)[0] == (
        "unverified"
    )
    # After the store's data date nothing is verified.
    assert cap_verification(
        "active", "verified", "attestation", as_of=date(2025, 1, 2), data_date=date(2025, 1, 1)
    )[0] == "unverified"


def test_rule2_no_termination_is_unknown_not_found() -> None:
    intervals = resolve_intervals(effective_from=D0, relations=[])
    assert _status(intervals, date(2023, 6, 1)) == ("not_yet_effective", "unverified")
    status, verification = _status(intervals, date(2025, 1, 1))
    assert (status, verification) == ("unknown", "not_found")
    assert any("Có hiệu lực từ 01/01/2024" in note for note in
               at_date(intervals, date(2025, 1, 1)).notes)


def test_rule3_unapproved_proposal_does_not_change_axis_a() -> None:
    proposal = Relation("r1", "repeal", date(2024, 5, 1), approved=False, source_label="X")
    intervals = resolve_intervals(effective_from=D0, relations=[proposal])
    found = at_date(intervals, date(2024, 6, 1))
    assert (found.status, found.verification) == ("unknown", "not_found")
    assert NOTE_PENDING in found.notes
    approved = Relation("r1", "repeal", date(2024, 5, 1), approved=True, source_label="X",
                        reviewed_by="u1", reviewed_at="2024-05-02T00:00:00")
    intervals = resolve_intervals(effective_from=D0, relations=[approved])
    assert _status(intervals, date(2024, 4, 30))[0] == "unknown"
    assert _status(intervals, date(2024, 6, 1)) == ("repealed", "verified")


def test_rule4_conditional_relation_is_not_computed() -> None:
    conditional = Relation("r2", "replace", date(2024, 5, 1), approved=True,
                           condition="trừ trường hợp hồ sơ đã nộp trước ngày này",
                           source_label="Y")
    found = at_date(resolve_intervals(effective_from=D0, relations=[conditional]),
                    date(2024, 6, 1))
    assert (found.status, found.verification) == ("unknown", "unverified")
    assert any("trừ trường hợp" in note for note in found.notes)


def test_rule5_stale_attestation_no_longer_verifies() -> None:
    stale = Attestation("a2", "active", D0, date(2024, 6, 30), "needs_reverify", "reviewer",
                        "2024-06-30T00:00:00", "Đối chiếu")
    found = at_date(resolve_intervals(effective_from=D0, relations=[], attestations=[stale]),
                    date(2024, 3, 1))
    assert found.verification != "verified"
    assert any("cần xác minh lại" in note for note in found.notes)


def test_status_is_computed_per_date_not_copied_from_today() -> None:
    replaced = Relation("r3", "replace", date(2026, 7, 1), approved=True, source_label="Z",
                        reviewed_by="u", reviewed_at="2026-05-20T00:00:00")
    intervals = resolve_intervals(effective_from=date(2017, 10, 1), relations=[replaced])
    assert _status(intervals, date(2020, 1, 1))[0] == "unknown"
    assert _status(intervals, date(2026, 7, 1)) == ("replaced", "verified")


def _nodes(*texts: str) -> list[NodeText]:
    return [NodeText(f"n{i}", "article" if t.startswith("Điều") else "paragraph", f"{i:06d}", t)
            for i, t in enumerate(texts)]


def test_rules_read_dates_replace_repeal_and_amend() -> None:
    nodes = _nodes(
        "BỘ CÔNG AN Số: 9/2030/TT-BCA Hà Nội, ngày 15 tháng 5 năm 2030 THÔNG TƯ HƯ CẤU",
        "Điều 1. Sửa đổi, bổ sung một số điều của Thông tư số 1/2029/TT-BCA ngày 01 tháng 2 "
        "năm 2029 của Bộ trưởng",
        "Điều 2. Hiệu lực thi hành 1. Thông tư này có hiệu lực thi hành kể từ ngày 01 tháng 7 "
        "năm 2030. 2. Thông tư số 2/2020/TT-BCA ngày 19/09/2020 của Bộ trưởng hết hiệu lực "
        "kể từ ngày Thông tư này có hiệu lực thi hành. 3. Bãi bỏ Điều 4; khoản 2 Điều 5 của "
        "Thông tư số 3/2021/TT-BCA ngày 01/02/2021.",
    )
    dates = detect_dates(nodes, doc_type="circular", consolidated=False)
    assert dates.issue_date == date(2030, 5, 15)
    assert dates.effective_from == date(2030, 7, 1)
    found = extract_relations(nodes, own_number_key=number_key("9/2030/TT-BCA"),
                              title="Thông tư hư cấu", document_number="9/2030/TT-BCA",
                              effective_from=dates.effective_from)
    actions = {(r.action, r.target.number if r.target else None) for r in found.relations}
    assert ("modify", "1/2029/TT-BCA") in actions
    assert ("replace", "2/2020/TT-BCA") in actions
    assert ("repeal_partial", "3/2021/TT-BCA") in actions
    assert all(r.valid_from == date(2030, 7, 1) for r in found.relations)


def test_clause_and_article_replace_vs_modify_and_scope() -> None:
    from app.effectivity.extract import node_amendment_items, parse_amend_item
    from app.effectivity.node_paths import node_exception_intervals

    nodes = [
        NodeText("n_hdr", "paragraph", "000001",
                 "BỘ CÔNG AN Số: 09/2026/TT-BCA Hà Nội, ngày 01 tháng 4 năm 2026 THÔNG TƯ"),
        NodeText("n_dieu1", "article", "000002:dieu:1",
                 "Điều 1. Sửa đổi, bổ sung một số điều của Thông tư số 55/2021/TT-BCA"),
        NodeText("n_k1", "clause", "000002:dieu:1/000001:khoan:1",
                 "1. Thay thế khoản 3 Điều 8 như sau:", parent_id="n_dieu1"),
        NodeText("n_k2", "clause", "000002:dieu:1/000002:khoan:2",
                 "2. Sửa đổi, bổ sung khoản 1 Điều 6 như sau:", parent_id="n_dieu1"),
        NodeText("n_dieu4", "article", "000003:dieu:4",
                 "Điều 4. Thủ tục đăng ký mới."),
        NodeText(
            "n_dieu10", "article", "000004:dieu:10",
            "Điều 10. Hiệu lực thi hành. "
            "1. Thông tư này có hiệu lực thi hành kể từ ngày 15 tháng 5 năm 2026. "
            "2. Điều 4 của Thông tư này thay thế Điều 8 của Thông tư số 55/2021/TT-BCA. "
            "3. Thay thế khoản 3 Điều 9 của Thông tư số 56/2021/TT-BCA và khoản 2 Điều 6 "
            "của Thông tư số 57/2021/TT-BCA kể từ ngày 01/07/2026. "
            "4. Điều 5 của Thông tư số 58/2021/TT-BCA được thay thế bởi Điều 4 của Thông tư này.",
        ),
    ]
    eff = date(2026, 5, 15)
    found = extract_relations(
        nodes, own_number_key=number_key("09/2026/TT-BCA"),
        title="Thông tư sửa đổi", document_number="09/2026/TT-BCA", effective_from=eff,
    )
    by_target = {
        (r.target.number if r.target else "", r.target_path): r for r in found.relations
    }
    # 1. "Điều 4 của Thông tư này thay thế Điều 8 của Thông tư số 55/2021/TT-BCA"
    r55 = by_target[("55/2021/TT-BCA", "Điều 8")]
    assert r55.action == "replace"
    assert r55.scope == "node"
    assert r55.source_node_id == "n_dieu4"
    assert r55.quote_node_id == "n_dieu10"
    assert r55.source_path == "Điều 4"
    assert r55.valid_from == eff

    # 2. Multi-object "Thay thế khoản 3 Điều 9 của 56/2021/TT-BCA và khoản 2 Điều 6 của 57/2021"
    r56 = by_target[("56/2021/TT-BCA", "khoản 3 Điều 9")]
    assert r56.action == "replace"
    assert r56.scope == "node"
    assert r56.valid_from == date(2026, 7, 1)

    r57 = by_target[("57/2021/TT-BCA", "khoản 2 Điều 6")]
    assert r57.action == "replace"
    assert r57.scope == "node"
    assert r57.valid_from == date(2026, 7, 1)

    # 3. Passive "Điều 5 của Thông tư số 58/2021/TT-BCA được thay thế bởi Điều 4 của Thông tư này"
    r58 = by_target[("58/2021/TT-BCA", "Điều 5")]
    assert r58.action == "replace"
    assert r58.scope == "node"
    assert r58.source_node_id == "n_dieu4"
    assert r58.quote_node_id == "n_dieu10"
    assert r58.source_path == "Điều 4"
    assert r58.valid_from == eff

    # 4. parse_amend_item & node_amendment_items distinguish replace vs modify
    assert parse_amend_item("1. Thay thế khoản 3 Điều 8 như sau:") == [
        ("replace", "khoản 3 Điều 8")
    ]
    assert parse_amend_item("2. Điều 4 thay thế Điều 8 của Thông tư số 55/2021/TT-BCA") == [
        ("replace", "Điều 8")
    ]
    assert parse_amend_item("3. Sửa đổi, bổ sung khoản 1 Điều 6 như sau:") == [
        ("modify", "khoản 1 Điều 6")
    ]
    amend_items = [
        (node.node_id, ref.number, action, path)
        for node, ref, action, path in node_amendment_items(
            nodes, own_number_key=number_key("09/2026/TT-BCA")
        )
    ]
    assert ("n_k1", "55/2021/TT-BCA", "replace", "khoản 3 Điều 8") in amend_items
    assert ("n_k2", "55/2021/TT-BCA", "modify", "khoản 1 Điều 6") in amend_items

    # 5. Resolver: node-scoped replace does NOT mark the whole document as replaced
    node_rel = Relation(
        id="rel-node-replace", action="replace", valid_from=eff, approved=True,
        source_label="09/2026/TT-BCA", scope="node", target_path="Điều 8",
    )
    doc_intervals = resolve_intervals(effective_from=date(2021, 7, 1), relations=[node_rel])
    after_doc = at_date(doc_intervals, date(2026, 6, 1))
    assert after_doc is not None
    assert after_doc.status == "modified"
    assert any("Được thay thế một phần từ 15/05/2026" in note for note in after_doc.notes)

    node_exc = node_exception_intervals([node_rel])
    assert len(node_exc) == 1
    # The replaced node itself is superseded ("replaced"), like a repealed node; only the
    # *document* stays "modified" because the rest of it is untouched.
    assert node_exc[0].status == "replaced"
    assert node_exc[0].verification == "verified"
    assert any("Được thay thế nội dung từ 15/05/2026" in note for note in node_exc[0].notes)

    # ``modify`` on the same node stays "modified" and unverified (text changed, not superseded).
    modify_rel = Relation(
        id="rel-node-modify", action="modify", valid_from=eff, approved=True,
        source_label="09/2026/TT-BCA", scope="node", target_path="Điều 8",
    )
    modify_exc = node_exception_intervals([modify_rel])
    assert modify_exc[0].status == "modified"
    assert modify_exc[0].verification == "unverified"


DSN = os.environ.get("EVIDENCE_TEST_DATABASE_URL")


@pytest.mark.skipif(not DSN, reason="No disposable PostgreSQL test database configured")
async def test_postgres_trigger_snapshot_and_review_scope() -> None:
    from app.effectivity.service import EffectivityError, create_attestation, review_proposals
    from app.effectivity.store import load_effectivity, publish_snapshot

    assert DSN
    schema = "test_eff_" + uuid4().hex
    connection = await asyncpg.connect(DSN)
    pool = None
    try:
        await connection.execute(f'CREATE SCHEMA "{schema}"')
        await connection.execute(f'SET search_path TO "{schema}", public')
        migrations = Path(__file__).resolve().parents[1] / "app" / "migrations"
        for path in sorted(migrations.glob("*.sql")):
            if not path.name.endswith(".down.sql"):
                await connection.execute(path.read_text(encoding="utf-8"))
        reviewer, outsider, category = uuid4(), uuid4(), uuid4()
        for user, name in ((reviewer, "rv"), (outsider, "out")):
            await connection.execute(
                "INSERT INTO users (id, username, display_name) VALUES ($1, $2, $2)", user, name
            )
        await connection.execute(
            "INSERT INTO categories (id, name, code) VALUES ($1, 'HƯ CẤU', 'hc')", category
        )
        await connection.execute(
            "INSERT INTO category_acl (category_id, user_id, can_query, can_review)"
            " VALUES ($1, $2, TRUE, TRUE)", category, reviewer,
        )
        docs: dict[str, UUID] = {}
        nodes: dict[str, UUID] = {}
        for number in ("1/2029/TT-BCA", "9/2030/TT-BCA"):
            doc, version = uuid4(), uuid4()
            docs[number] = doc
            await connection.execute(
                "INSERT INTO documents (id, doc_type, title, document_number)"
                " VALUES ($1, 'circular', 'Thông tư HƯ CẤU', $2)", doc, number,
            )
            await connection.execute(
                "INSERT INTO document_categories VALUES ($1, $2)", doc, category
            )
            await connection.execute(
                """INSERT INTO document_versions (id, document_id, version_number,
                     original_file_path, original_file_sha256, original_filename,
                     review_status, effective_from)
                   VALUES ($1, $2, 1, 'x.pdf', $3, 'x.pdf', 'approved', '2020-03-01')""",
                version, doc, uuid4().hex + uuid4().hex,
            )
            nodes[number] = await connection.fetchval(
                """INSERT INTO document_nodes (document_id, document_version_id, node_type,
                     path, text_original, text_indexed, text_normalized, text_folded,
                     parse_confidence, review_status)
                   VALUES ($1, $2, 'article', '000001:dieu:1', 'Điều 1. HƯ CẤU', '', '', '',
                           0.9, 'approved') RETURNING id""",
                doc, version,
            )
        pool = await asyncpg.create_pool(
            DSN, min_size=1, max_size=2, server_settings={"search_path": f"{schema},public"}
        )
        target, source = docs["1/2029/TT-BCA"], docs["9/2030/TT-BCA"]
        # Rule 1 at the API boundary: "active" is only stated up to the verification day.
        with pytest.raises(EffectivityError, match="ATTESTATION_FUTURE_DATE"):
            await create_attestation(
                pool, reviewer_id=reviewer, document_id=target, result="active",
                valid_for_from=date(2020, 3, 1), valid_for_to=date(2999, 1, 1),
                source_note="x",
            )
        await create_attestation(
            pool, reviewer_id=reviewer, document_id=target, result="active",
            valid_for_from=date(2020, 3, 1), valid_for_to=date(2021, 1, 1),
            source_note="Đối chiếu bản gốc HƯ CẤU",
        )
        async with pool.acquire() as conn:
            views, _, _ = await load_effectivity(conn, document_ids=[target],
                                                 as_of=date(2020, 6, 1))
        assert views[str(target)].status.value == "active"
        assert views[str(target)].verification.value == "verified"
        # A new relation touching the target marks the attestation (rule 5).
        relation = await connection.fetchval(
            """INSERT INTO node_amendments (source_node_id, source_document_id,
                 target_document_id, scope, action, valid_from, evidence_source, proposed_by)
               VALUES ($1, $2, $3, 'document', 'replace', '2022-07-01', 'rule', 'rule')
               RETURNING id""",
            nodes["9/2030/TT-BCA"], source, target,
        )
        assert await connection.fetchval(
            "SELECT status FROM effectivity_attestations WHERE target_document_id = $1", target
        ) == "needs_reverify"
        # The proposal changes nothing on axis A until a reviewer approves it (rule 3).
        async with pool.acquire() as conn, conn.transaction():
            await publish_snapshot(conn, actor_id=None)
            views, _, _ = await load_effectivity(conn, document_ids=[target],
                                                 as_of=date(2023, 1, 1))
        assert views[str(target)].status.value == "unknown"
        assert views[str(target)].pending_proposals == 1
        # Review scope (D10): a user without can_review on the category is refused.
        with pytest.raises(EffectivityError, match="REVIEW_SCOPE_REQUIRED"):
            await review_proposals(pool, reviewer_id=outsider, note="x", decisions=[
                {"relation_id": relation, "decision": "approve"}])
        result = await review_proposals(pool, reviewer_id=reviewer, note="Duyệt lô HƯ CẤU",
                                        decisions=[{"relation_id": relation,
                                                    "decision": "approve"}])
        assert result["results"][0]["decision"] == "approve"
        assert await connection.fetchval(
            "SELECT count(*) FROM audit_events WHERE action = 'effectivity.review_relation'"
            " AND metadata->>'batch_id' = $1", result["batch_id"],
        ) == 1
        async with pool.acquire() as conn:
            before, _, _ = await load_effectivity(conn, document_ids=[target],
                                                  as_of=date(2022, 6, 30))
            after, _, _ = await load_effectivity(conn, document_ids=[target],
                                                 as_of=date(2022, 7, 1))
        assert before[str(target)].status.value == "unknown"
        assert after[str(target)].status.value == "replaced"
        assert after[str(target)].verification.value in {"verified", "unverified"}
    finally:
        if pool is not None:
            await pool.close()
        await connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await connection.close()


_OWN = "99/2026/TT-BCA"


def _article(text: str, node_id: str = "a1") -> NodeText:
    return NodeText(node_id, "article", f"000001:{node_id}", text)


def _relations(*nodes: NodeText, effective_from: date = date(2026, 7, 1)):
    return extract_relations(
        list(nodes), own_number_key=number_key(_OWN), title="Thông tư",
        document_number=_OWN, effective_from=effective_from,
    ).relations


def test_stated_date_survives_when_sentence_is_not_first_in_node() -> None:
    """Regression: the date was lost when the sentence offset shifted the reference span."""

    body = (
        "Điều 5 của Thông tư này thay thế Điều 3 của Thông tư số 12/2020/TT-BCA "
        "kể từ ngày 01 tháng 10 năm 2026."
    )
    for prefix in ("", "Điều 5. ", "Điều 5. Hiệu lực thi hành\n"):
        (rel,) = _relations(_article(prefix + body))
        assert rel.action == "replace" and rel.scope == "node"
        assert rel.source_path == "Điều 5" and rel.target_path == "Điều 3"
        assert rel.valid_from == date(2026, 10, 1), prefix
        assert rel.from_own_effective is False, prefix


def test_replace_keeps_scope_source_target_and_is_not_downgraded_to_modify() -> None:
    cases = {
        "Điều 5 của Thông tư này thay thế Điều 3 của Thông tư số 12/2020/TT-BCA.":
            ("node", "Điều 5", "Điều 3"),
        "Thay thế khoản 2 Điều 4 của Thông tư số 12/2020/TT-BCA như sau: nội dung mới.":
            ("node", "Điều 2", "khoản 2 Điều 4"),
        "Điều 3 của Thông tư số 12/2020/TT-BCA được thay thế bởi Điều 5 của Thông tư này.":
            ("node", "Điều 5", "Điều 3"),
        "Thông tư này thay thế Thông tư số 12/2020/TT-BCA.":
            ("document", None, None),
    }
    for text, (scope, source, target) in cases.items():
        (rel,) = _relations(_article("Điều 2. " + text))
        assert rel.action == "replace", text
        assert rel.scope == scope, text
        assert rel.target_path == target, text
        if source is not None:
            assert rel.source_path == source, text


def test_cum_tu_replacement_is_modify_not_replace() -> None:
    (item,) = parse_amend_item("3. Thay thế cụm từ “A” bằng cụm từ “B” tại khoản 5 Điều 4")
    assert item == ("modify", "khoản 5 Điều 4")


def test_partial_replace_without_unit_is_a_node_draft_with_empty_target() -> None:
    """Never ``modify`` and never the whole document: the reviewer must pick the Điều."""

    for text in (
        "Điều 1. Thay thế một số điều của Thông tư số 12/2020/TT-BCA như sau.",
        "Điều 1. Thông tư này thay thế một phần Thông tư số 12/2020/TT-BCA.",
        "Điều 1. Một số điều của Thông tư số 12/2020/TT-BCA được thay thế bởi Thông tư này.",
    ):
        (rel,) = _relations(_article(text))
        assert rel.action == "replace" and rel.scope == "node", text
        assert rel.target_path is None, text
        assert rel.target is not None and rel.target.number_key == number_key("12/2020/TT-BCA")
        assert rel.key.endswith("|partial"), text
    # A whole-document replacement keeps its document scope and its old key.
    (whole,) = _relations(_article("Điều 1. Thông tư này thay thế Thông tư số 12/2020/TT-BCA."))
    assert (whole.scope, whole.key) == ("document", "replace|12/2020/tt-bca|")


def test_partial_replace_heading_is_not_duplicated_when_items_name_the_units() -> None:
    heading = _article("Điều 1. Thay thế một số điều của Thông tư số 12/2020/TT-BCA như sau:")
    item = NodeText(
        "c1", "clause", "000001:a1:c1", "1. Thay thế khoản 2 Điều 4 như sau: nội dung mới.",
        parent_id="a1",
    )
    assert _relations(heading, item) == []


def test_replace_of_several_units_gives_one_relation_per_target() -> None:
    tt = "Thông tư số 12/2020/TT-BCA"
    cases = {
        f"Điều 5 và Điều 6 của Thông tư này thay thế Điều 3 và Điều 4 của {tt}.":
            ("Điều 5 và Điều 6", ["Điều 3", "Điều 4"]),
        f"Điều 3 và Điều 4 của {tt} được thay thế bởi Điều 5 và Điều 6 của Thông tư này.":
            ("Điều 5 và Điều 6", ["Điều 3", "Điều 4"]),
        f"Điều 5 của Thông tư này thay thế khoản 1 và khoản 2 Điều 4 của {tt}.":
            ("Điều 5", ["khoản 1 Điều 4", "khoản 2 Điều 4"]),
    }
    for text, (source, targets) in cases.items():
        relations = _relations(_article("Điều 2. " + text))
        assert [r.target_path for r in relations] == targets, text
        assert {(r.action, r.scope, r.source_path) for r in relations} == {
            ("replace", "node", source)
        }, text
        assert len({r.key for r in relations}) == len(targets), text


def test_same_target_replaced_by_two_source_units_keeps_both() -> None:
    first = _article(
        "Điều 5. Điều 5 của Thông tư này thay thế Điều 3 của Thông tư số 12/2020/TT-BCA "
        "kể từ ngày 01 tháng 10 năm 2026.", "a1",
    )
    second = _article(
        "Điều 6. Điều 6 của Thông tư này thay thế Điều 3 của Thông tư số 12/2020/TT-BCA "
        "kể từ ngày 01 tháng 01 năm 2027.", "a2",
    )
    relations = _relations(first, second)
    assert [(r.source_path, r.valid_from) for r in relations] == [
        ("Điều 5", date(2026, 10, 1)), ("Điều 6", date(2027, 1, 1)),
    ]
    assert relations[0].key == "replace|12/2020/tt-bca|điều 3"  # old key format unchanged
    assert len({r.key for r in relations}) == 2


def test_same_statement_repeated_is_still_deduplicated() -> None:
    text = "Điều 5 của Thông tư này thay thế Điều 3 của Thông tư số 12/2020/TT-BCA."
    relations = _relations(_article("Điều 5. " + text, "a1"), _article("Điều 9. " + text, "a2"))
    assert len(relations) == 1


def test_quy_dinh_tai_wording_keeps_replace_source_and_target() -> None:
    tt = "Thông tư số 12/2020/TT-BCA"
    cases = {
        f"Quy định tại Điều 5 của Thông tư này thay thế quy định tại Điều 3 của {tt}.":
            ("Điều 5", "Điều 3"),
        f"Điều 3 của {tt} được thay thế bởi quy định tại Điều 5 của Thông tư này.":
            ("Điều 5", "Điều 3"),
    }
    for text, (source, target) in cases.items():
        (rel,) = _relations(_article("Điều 2. " + text))
        assert rel.action == "replace" and rel.scope == "node", text
        assert (rel.source_path, rel.target_path) == (source, target), text


_HEAD = "Điều 1. Sửa đổi, bổ sung một số điều của Thông tư số 12/2020/TT-BCA như sau:"


def test_item_own_date_wins_over_document_date() -> None:
    doc = date(2026, 7, 1)
    own = "2. Thay thế khoản 2 Điều 4 kể từ ngày 01 tháng 01 năm 2027 như sau: nội dung mới."
    assert item_valid_from(own, doc) == date(2027, 1, 1)
    assert item_valid_from("2. Thay thế khoản 2 Điều 4 từ ngày 01/01/2027.", doc) == (
        date(2027, 1, 1))
    assert item_valid_from("2. Thay thế khoản 2 Điều 4 như sau: nội dung mới.", doc) == doc
    # Dates in the quoted new text, after "như sau" or of the cited document are not the item's.
    assert item_valid_from(
        "2. Thay thế khoản 2 Điều 4 như sau: “áp dụng kể từ ngày 05/05/2030”.", doc) == doc
    assert item_valid_from(
        "2. Sửa đổi Điều 4 của Thông tư số 12/2020/TT-BCA ngày 01/10/2020 như sau:", doc) == doc
    assert item_valid_from("2. Thay thế “kể từ ngày 05/05/2030” tại khoản 2 Điều 4", doc) == doc
    # Several different dates: unclear which applies to which target -> reviewer enters it.
    assert item_valid_from(
        "2. Sửa đổi khoản 2 từ ngày 01/01/2027 và khoản 3 từ ngày 01/07/2027 Điều 4", doc) is None
    assert item_valid_from("2. Sửa đổi Điều 4 từ ngày 01/01/2027 (từ ngày 01/01/2027)", doc) == (
        date(2027, 1, 1))
    assert item_valid_from("2. Sửa đổi Điều 4", None) is None


async def test_stored_amendment_items_use_their_own_date_and_fall_back_to_the_document() -> None:
    from app.effectivity.store import _store_node_amendments

    class Connection:
        def __init__(self) -> None:
            self.inserts: list[tuple] = []

        async def fetch(self, sql: str, *args: object) -> list:
            return []

        async def fetchval(self, sql: str, *args: object) -> UUID | None:
            if "INSERT INTO node_amendments" in sql:
                self.inserts.append(args)
                return uuid4()
            return None

    ids = [str(uuid4()) for _ in range(4)]
    nodes = [
        NodeText(ids[0], "article", "000001:a1", _HEAD),
        NodeText(ids[1], "clause", "000001:a1:c1",
                 "1. Thay thế khoản 2 Điều 4 kể từ ngày 01 tháng 01 năm 2027 như sau: mới.",
                 parent_id=ids[0]),
        NodeText(ids[2], "clause", "000001:a1:c2",
                 "2. Sửa đổi khoản 3 Điều 4 như sau: mới.", parent_id=ids[0]),
        NodeText(ids[3], "clause", "000001:a1:c3",
                 "3. Sửa đổi khoản 4 từ ngày 01/01/2027 và khoản 5 từ ngày 01/07/2027 Điều 4.",
                 parent_id=ids[0]),
    ]
    connection = Connection()
    meta = {"id": uuid4(), "effective_from": date(2026, 7, 1)}
    await _store_node_amendments(connection, meta, nodes, number_key(_OWN))
    stored = {(str(args[0]), args[9]): args[5] for args in connection.inserts}
    assert stored[(ids[1], "khoản 2 Điều 4")] == date(2027, 1, 1)
    assert stored[(ids[2], "khoản 3 Điều 4")] == date(2026, 7, 1)
    assert stored[(ids[3], "khoản 4 Điều 4")] is None
    assert stored[(ids[3], "khoản 5 Điều 4")] is None


def test_list_item_under_repeal_heading_keeps_its_own_date() -> None:
    heading = _article("Điều 3. Bãi bỏ các văn bản sau đây:", "a1")
    items = [
        NodeText("c1", "clause", "000001:a1:c1",
                 "1. Thông tư số 12/2020/TT-BCA kể từ ngày 01 tháng 01 năm 2027.",
                 parent_id="a1"),
        NodeText("c2", "clause", "000001:a1:c2", "2. Thông tư số 15/2021/TT-BCA.",
                 parent_id="a1"),
    ]
    first, second = _relations(heading, *items)
    assert (first.valid_from, first.from_own_effective) == (date(2027, 1, 1), False)
    assert (second.valid_from, second.from_own_effective) == (date(2026, 7, 1), True)


def test_modify_and_repeal_partial_with_named_unit_are_node_scoped() -> None:
    tt = "Thông tư số 12/2020/TT-BCA"
    cases = {
        f"Sửa đổi khoản 2 Điều 4 của {tt}.": ("modify", "khoản 2 Điều 4"),
        f"Bãi bỏ Điều 3 của {tt}.": ("repeal_partial", "Điều 3"),
        f"Bãi bỏ Điều 3 và Điều 4 của {tt}.": ("repeal_partial", "Điều 3"),
    }
    for text, (action, target) in cases.items():
        relations = _relations(_article("Điều 2. " + text))
        assert relations[0].action == action, text
        assert relations[0].target_path == target, text
        assert all(r.scope == "node" and r.action == action for r in relations), text
    # No unit named: still a document-level relation with the generic note.
    for text, action in (
        (f"Sửa đổi, bổ sung một số điều của {tt}.", "modify"),
        (f"Bãi bỏ một số điều của {tt}.", "repeal_partial"),
    ):
        (rel,) = _relations(_article("Điều 2. " + text))
        assert (rel.action, rel.scope, rel.target_path) == (action, "document", None), text
    # Whole-document repeal stays document-level.
    (rel,) = _relations(_article(f"Điều 2. Bãi bỏ {tt}."))
    assert (rel.action, rel.scope) == ("repeal", "document")


def test_node_scoped_modify_and_repeal_partial_resolve_on_the_amended_node() -> None:
    from datetime import UTC, datetime

    from app.effectivity.node_paths import node_exception_intervals

    now = datetime(2026, 7, 1, tzinfo=UTC).isoformat()
    modify = Relation("m", "modify", date(2026, 7, 1), True, scope="node",
                      target_path="khoản 2 Điều 4", source_label="TT mới", reviewed_at=now)
    repeal = Relation("r", "repeal_partial", date(2026, 7, 1), True, scope="node",
                      target_path="Điều 3", source_label="TT mới", reviewed_at=now)
    (changed,) = node_exception_intervals([modify])
    assert changed.status == "modified"
    (gone,) = node_exception_intervals([repeal])
    assert (gone.status, gone.verification) == ("repealed", "verified")
    # Approved node-scoped partial relations still mark the document as partly modified.
    intervals = resolve_intervals(effective_from=D0, relations=[modify, repeal])
    assert _status(intervals, date(2026, 8, 1))[0] == "modified"


def test_annex_and_form_replacement_items_reach_the_reviewer() -> None:
    assert parse_amend_item("5. Thay thế Phụ lục I ban hành kèm theo Thông tư") == [
        ("replace", "Phụ lục I")
    ]
    assert parse_amend_item("6. Thay thế Mẫu số 01 như sau:") == [("replace", "Mẫu số 01")]
    # ``modify`` stays ``modify`` for a phrase replacement even when it names an annex.
    assert parse_amend_item("7. Thay thế cụm từ “A” bằng cụm từ “B” tại Mẫu số 01") == [
        ("modify", "Mẫu số 01")
    ]
