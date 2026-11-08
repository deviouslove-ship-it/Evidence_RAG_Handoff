from datetime import date

from app.documents.node_effectivity import AmendmentEdge, resolve_amendment_chain


def test_resolves_chain_beyond_context_hop_limit() -> None:
    edges = {
        "A": (AmendmentEdge("A", "B", "modify", date(2020, 1, 1)),),
        "B": (AmendmentEdge("B", "C", "modify", date(2021, 1, 1)),),
        "C": (AmendmentEdge("C", "D", "modify", date(2022, 1, 1)),),
    }
    result = resolve_amendment_chain("A", edges, date(2023, 1, 1))
    assert result.status == "modified"
    assert result.chain == ("A", "B", "C", "D")


def test_cycle_fails_closed() -> None:
    edges = {
        "A": (AmendmentEdge("A", "B", "modify", date(2020, 1, 1)),),
        "B": (AmendmentEdge("B", "A", "modify", date(2021, 1, 1)),),
    }
    result = resolve_amendment_chain("A", edges, date(2023, 1, 1))
    assert result.status == "unknown"
    assert "cycle_detected" in result.reasons
