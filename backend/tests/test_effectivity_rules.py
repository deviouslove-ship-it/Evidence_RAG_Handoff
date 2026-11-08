"""G1/G3 hard effectivity rules (design §4).  Fixture texts are HƯ CẤU."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import pytest

from app.effectivity.extract import NodeText, detect_dates, extract_relations, number_key
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
