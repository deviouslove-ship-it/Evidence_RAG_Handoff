"""Pick a fixed, reproducible subset of the test corpus for the reranker benchmark.

    python evaluation/coverage/select_subset.py --dest <staging-folder> [--size 100]

* Every document file whose number appears in ``topics.json`` (required citations) is kept.
* The rest of the subset is filled with other document files in the order of
  SHA-256(``Folder/filename``), so the choice does not depend on file order or on this
  benchmark's results.
* The metadata record (``.txt``) that belongs to a chosen document is copied with it; those
  records are not counted as documents.
* ``--exclude`` skips files that are known not to import (one ``Folder/filename`` per line).

The staging folder keeps the layout ``scripts/import_official_corpus.py`` expects and gets a
``subset-manifest.json`` listing every file with its role and SHA-256.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from import_official_corpus import _NAME, canonical_code, discover  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--source-dir", default=str(PROJECT_ROOT / "test-data" / "van-ban"))
    parser.add_argument("--dest", required=True)
    parser.add_argument("--size", type=int, default=100)
    parser.add_argument("--exclude", help="text file with Folder/filename lines to skip")
    args = parser.parse_args()
    source, dest = Path(args.source_dir).resolve(), Path(args.dest).resolve()
    if dest.exists() and any(dest.iterdir()):
        raise SystemExit(f"Destination is not empty: {dest}")
    topics = json.loads((HERE / "topics.json").read_text(encoding="utf-8"))["topics"]
    required = {need["document_number"] for topic in topics for need in topic["required"]}
    skipped = set()
    if args.exclude:
        skipped = {line.strip() for line in Path(args.exclude).read_text(
            encoding="utf-8-sig").splitlines() if line.strip()}

    items, _ = discover(source, set(), None)
    key = lambda item: f"{item.folder}/{item.path.name}"  # noqa: E731
    items = [item for item in items if key(item) not in skipped]
    mandatory = [item for item in items if item.number in required]
    missing = required - {item.number for item in mandatory}
    if missing:
        raise SystemExit(f"Required documents not found in the corpus: {sorted(missing)}")
    rest = sorted((item for item in items if item.number not in required),
                  key=lambda item: hashlib.sha256(key(item).encode("utf-8")).hexdigest())
    chosen = [(item, "required") for item in mandatory]
    chosen += [(item, "filler") for item in rest[: max(0, args.size - len(mandatory))]]
    if len(chosen) != args.size:
        raise SystemExit(f"Only {len(chosen)} documents available for size {args.size}")

    manifest: list[dict[str, str]] = []
    records_copied = 0
    for item, role in chosen:
        target = dest / item.folder
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item.path, target / item.path.name)
        manifest.append({"path": key(item), "number": item.number, "role": role,
                         "sha256": hashlib.sha256(item.path.read_bytes()).hexdigest()})
    # Metadata records: same folder and code, copied once.
    for folder in sorted({item.folder for item, _ in chosen}):
        codes = {item.code for item, _ in chosen if item.folder == folder}
        for path in sorted((source / folder).glob("*.txt")):
            match = _NAME.match(path.name)
            code = canonical_code(match["code"] if match else path.stem)
            if code in codes:
                shutil.copy2(path, dest / folder / path.name)
                records_copied += 1
    (dest / "subset-manifest.json").write_text(json.dumps({
        "documents": len(chosen), "metadata_records": records_copied,
        "required_numbers": sorted(required), "files": manifest,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"documents": len(chosen), "required": len(mandatory),
                      "filler": len(chosen) - len(mandatory), "metadata_records": records_copied,
                      "dest": str(dest)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
