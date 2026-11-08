"""Compute abstention metrics for reviewed evaluation cases."""

from __future__ import annotations

import json
from pathlib import Path
import sys


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: abstention.py results.jsonl", file=sys.stderr)
        return 2
    rows = [json.loads(line) for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines() if line.strip()]
    reviewed = [row for row in rows if row.get("review_status") == "approved"]
    if not reviewed:
        print(json.dumps({"reviewed_cases": 0, "status": "not_evaluated"}))
        return 0
    correct = sum(bool(row.get("abstained")) == bool(row.get("expected_abstention")) for row in reviewed)
    print(json.dumps({"reviewed_cases": len(reviewed), "abstention_accuracy": correct / len(reviewed)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
