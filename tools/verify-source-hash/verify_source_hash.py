"""Verify SHA-256 for a PDF against a manifest entry."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--file", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if args.file:
        expected = manifest.get("sha256")
        actual = sha256(args.file)
        ok = expected == actual
        print(json.dumps({"expected": expected, "actual": actual, "match": ok}))
        return 0 if ok else 1
    if not isinstance(manifest.get("files"), list):
        print("manifest must contain a files list", file=sys.stderr)
        return 2
    failures = []
    for item in manifest["files"]:
        path = Path(item["path"])
        if not path.is_file() or sha256(path) != item["sha256"]:
            failures.append(item["path"])
    print(json.dumps({"checked": len(manifest["files"]), "failures": failures}))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
