"""Measure installed component footprints without claiming package size."""

from __future__ import annotations

import json
from pathlib import Path
import sys


def directory_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            total += item.stat().st_size
    return total


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: measure_footprint.py path [path...]", file=sys.stderr)
        return 2
    components = []
    for raw in sys.argv[1:]:
        path = Path(raw)
        components.append(
            {
                "path": str(path),
                "exists": path.exists(),
                "bytes": directory_size(path) if path.is_dir() else (path.stat().st_size if path.is_file() else 0),
            }
        )
    print(json.dumps({"components": components}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
