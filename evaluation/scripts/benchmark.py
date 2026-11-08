"""Evaluation helpers.

The current script validates the case schema and split grouping.  It does not
claim retrieval quality until reviewed Gold cases and a locked corpus exist.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys


REQUIRED = {
    "case_id",
    "scenario_group_id",
    "question",
    "source_hash",
    "review_status",
    "split",
}


def validate(path: Path) -> int:
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    seen_ids: set[str] = set()
    group_splits: dict[str, str] = {}
    for case in cases:
        missing = REQUIRED - case.keys()
        if missing:
            raise ValueError(f"case {case.get('case_id')} missing {sorted(missing)}")
        case_id = str(case["case_id"])
        if case_id in seen_ids:
            raise ValueError(f"duplicate case_id: {case_id}")
        seen_ids.add(case_id)
        group = str(case["scenario_group_id"])
        split = str(case["split"])
        if group in group_splits and group_splits[group] != split:
            raise ValueError(f"scenario group crosses split: {group}")
        group_splits[group] = split
    return len(cases)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: benchmark.py cases.jsonl", file=sys.stderr)
        return 2
    count = validate(Path(sys.argv[1]))
    print(json.dumps({"schema_valid": True, "case_count": count}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
