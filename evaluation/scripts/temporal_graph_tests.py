"""Exercise the amendment graph on a synthetic graph, not legal data."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.documents.node_effectivity import AmendmentEdge, resolve_amendment_chain  # noqa: E402


def main() -> int:
    edges = {
        "A": (AmendmentEdge("A", "B", "modify", date(2020, 1, 1)),),
        "B": (AmendmentEdge("B", "C", "modify", date(2021, 1, 1)),),
        "C": (AmendmentEdge("C", "D", "modify", date(2022, 1, 1)),),
    }
    result = resolve_amendment_chain("A", edges, date(2023, 1, 1))
    ok = result.status == "modified" and result.chain == ("A", "B", "C", "D")
    print({"full_chain_resolved": ok, "status": result.status, "chain": list(result.chain)})
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
