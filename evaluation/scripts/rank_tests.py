"""Validate locked split metadata for an evaluation run."""

from __future__ import annotations

import json
from pathlib import Path
import sys


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: rank_tests.py run.json", file=sys.stderr)
        return 2
    run = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    required = {"corpus_hash", "split_revision", "candidate_revision", "model_revision", "tokenizer_revision"}
    missing = required - run.keys()
    if missing:
        print(json.dumps({"valid": False, "missing": sorted(missing)}))
        return 1
    print(json.dumps({"valid": True, "locked_metadata": sorted(required)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
