import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "validate_no_literal_runtime_paths.py"


@pytest.mark.parametrize("kind", ["filesystem", "credential"])
def test_source_policy_detects_literals_without_printing_their_values(
    tmp_path: Path, kind: str
) -> None:
    source = tmp_path / "backend"
    source.mkdir()
    literal = (
        str(tmp_path / "private" / "runtime.exe") if kind == "filesystem" else "sk-" + "x" * 20
    )
    (source / "bad.py").write_text(f"value = {literal!r}\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "bad.py" in result.stderr
    assert literal not in result.stderr


def test_source_policy_skips_installed_dependencies(tmp_path: Path) -> None:
    dependency = tmp_path / "frontend" / "node_modules"
    dependency.mkdir(parents=True)
    (dependency / "generated.js").write_text("token = 'sk-" + "x" * 20 + "';", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
