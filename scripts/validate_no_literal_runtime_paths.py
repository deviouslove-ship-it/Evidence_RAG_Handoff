"""Static check for forbidden hardcoded runtime/provider literals."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRS = (
    "backend",
    "frontend",
    "src-tauri",
    "tools",
    "evaluation",
    "configs",
    "deploy",
    "scripts",
)
SKIP_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "target",
    "dist",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".vite",
    "gen",
}
SOURCE_SUFFIXES = {
    ".py",
    ".pyi",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".rs",
    ".ps1",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".sql",
    ".css",
    ".html",
    ".ini",
    ".cfg",
    ".sh",
}
FORBIDDEN_PROVIDER = re.compile(
    r"(?i)(sk-[a-z0-9]{16,}|api[_-]?key\s*[:=]\s*['\"][^'\"]+|bearer\s+[a-z0-9._-]{16,})"
)
FORBIDDEN_PATH = re.compile(
    r"(?i)(?<![\w])(?:[a-z]:[\\/]|\\{2,}[\w.-]+\\)"
    r"|['\"]/(?:home|Users|usr|opt|tmp|var|Applications)(?:/|['\"])"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    root = parser.parse_args().root.resolve()
    failures: list[str] = []
    for directory in SOURCE_DIRS:
        for parent, directories, files in os.walk(root / directory, followlinks=False):
            directories[:] = [
                name
                for name in directories
                if name not in SKIP_DIRS and not name.endswith(".egg-info")
            ]
            for name in files:
                path = Path(parent) / name
                if path.suffix not in SOURCE_SUFFIXES or ".local." in name:
                    continue
                try:
                    content = path.read_text(encoding="utf-8")
                except (OSError, UnicodeError):
                    failures.append(
                        f"unreadable UTF-8 source: {path.relative_to(root)}"
                    )
                    continue
                if FORBIDDEN_PROVIDER.search(content):
                    failures.append(f"secret-like literal: {path.relative_to(root)}")
                if FORBIDDEN_PATH.search(content):
                    failures.append(
                        f"absolute filesystem literal: {path.relative_to(root)}"
                    )
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print("no forbidden secret/filesystem literal found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
