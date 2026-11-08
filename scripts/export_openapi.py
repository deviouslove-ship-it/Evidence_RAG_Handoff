"""Export the implemented API only; --check rejects a stale committed schema."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.main import create_app  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "openapi.json")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = (
        json.dumps(create_app().openapi(), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    )
    if args.check:
        if (
            not args.output.is_file()
            or args.output.read_text(encoding="utf-8") != rendered
        ):
            print(
                "OpenAPI is missing or stale; run scripts/export_openapi.py",
                file=sys.stderr,
            )
            return 1
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print("OpenAPI contract checked" if args.check else "OpenAPI contract exported")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
