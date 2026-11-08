"""Run deterministic polarity and numeric regression cases."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.evidence.validators import validate_claim  # noqa: E402


CASES = [
    ("Không quá 15 ngày.", "Không quá 15 ngày.", "supported"),
    ("Không quá 15 ngày.", "Ít nhất 15 ngày.", "conditional"),
    ("Có thể nộp.", "Phải nộp.", "conditional"),
    ("Mọi trường hợp, trừ trường hợp tại Điều 5.", "Mọi trường hợp.", "conditional"),
]


def main() -> int:
    failures = []
    for quote, claim, expected in CASES:
        result = validate_claim(claim, ["e1"], {"e1": quote})
        if result.status != expected:
            failures.append({"quote": quote, "claim": claim, "expected": expected, "actual": result.status})
    print({"cases": len(CASES), "failures": failures})
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
