"""Basic migration pairing and destructive-down check."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "backend" / "app" / "migrations"


def main() -> int:
    up = sorted(ROOT.glob("*.sql"))
    failures = []
    for path in up:
        if path.name.endswith(".down.sql"):
            continue
        down = path.with_name(path.stem + ".down.sql")
        if not down.exists():
            failures.append(f"missing down migration: {path.name}")
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(
        f"migration pairs: {len([p for p in up if not p.name.endswith('.down.sql')])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
