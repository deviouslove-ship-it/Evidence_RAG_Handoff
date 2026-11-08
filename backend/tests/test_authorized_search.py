from datetime import date
from uuid import uuid4

from app.schemas import AmendmentStatus, Scope, ScopeMode
from app.storage.authorized_search import AuthorizedNode, InMemoryAuthorizedNodeSearch


async def test_selected_scope_cannot_expand_beyond_acl() -> None:
    principal = uuid4()
    allowed = uuid4()
    forbidden = uuid4()
    node = AuthorizedNode(
        evidence_id="e1",
        document_id=uuid4(),
        document_version_id=uuid4(),
        node_id=uuid4(),
        document_number="NĐ 1/2026",
        title="Tài liệu",
        label="Điều 1",
        quote_exact="Nội dung điều kiện",
        page=1,
        source_hash="a" * 64,
        as_of_date=date(2026, 1, 1),
        amendment_state=AmendmentStatus.ACTIVE,
        category_ids=(allowed,),
    )
    search = InMemoryAuthorizedNodeSearch([node], {principal: {allowed}})
    result = await search.search(
        principal_id=principal,
        scope=Scope(
            scope_mode=ScopeMode.SELECTED, category_ids=[forbidden], as_of_date=date(2026, 1, 1)
        ),
        query="điều kiện",
    )
    assert result == []


async def test_authorized_node_is_mapped_to_public_evidence_contract() -> None:
    principal = uuid4()
    category = uuid4()
    node = AuthorizedNode(
        evidence_id="e2",
        document_id=uuid4(),
        document_version_id=uuid4(),
        node_id=uuid4(),
        document_number="NĐ 1/2026",
        title="Tài liệu",
        label="Điều 1",
        quote_exact="Nội dung điều kiện",
        page=1,
        source_hash="b" * 64,
        as_of_date=date(2026, 1, 1),
        amendment_state=AmendmentStatus.ACTIVE,
        category_ids=(category,),
    )
    result = await InMemoryAuthorizedNodeSearch([node], {principal: {category}}).search(
        principal_id=principal,
        scope=Scope(scope_mode=ScopeMode.ALL_AUTHORIZED, as_of_date=date(2026, 1, 1)),
        query="điều kiện",
    )
    assert len(result) == 1
    assert result[0].evidence_id == "e2"
    assert result[0].viewer_url == "/api/v1/citations/e2/pdf?as_of_date=2026-01-01"


async def test_authorized_search_finds_document_number_and_title_without_quote_match() -> None:
    principal = uuid4()
    category = uuid4()
    node = AuthorizedNode(
        evidence_id="e3",
        document_id=uuid4(),
        document_version_id=uuid4(),
        node_id=uuid4(),
        document_number="381/2026/NĐ-CP",
        title="Quy định phụ cấp công vụ",
        label="Điều 1. Phạm vi điều chỉnh",
        quote_exact="Nội dung không chứa số hiệu hay tên văn bản.",
        page=1,
        source_hash="c" * 64,
        as_of_date=date(2026, 10, 22),
        amendment_state=AmendmentStatus.UNKNOWN,
        category_ids=(category,),
    )
    search = InMemoryAuthorizedNodeSearch([node], {principal: {category}})
    scope = Scope(scope_mode=ScopeMode.ALL_AUTHORIZED, as_of_date=date(2026, 10, 22))
    by_number = await search.search(principal_id=principal, scope=scope, query="381/2026/NĐ-CP")
    by_title = await search.search(principal_id=principal, scope=scope, query="phụ cấp công vụ")
    assert [item.evidence_id for item in by_number] == ["e3"]
    assert [item.evidence_id for item in by_title] == ["e3"]
