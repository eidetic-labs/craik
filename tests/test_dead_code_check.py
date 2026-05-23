import os
import subprocess
import sys
import textwrap
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_dead_code.py"


def _write_fixture(tmp_path: Path, source: str) -> None:
    package = tmp_path / "src" / "craik"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "example.py").write_text(textwrap.dedent(source), encoding="utf-8")
    (tmp_path / "vulture-whitelist.py").write_text("", encoding="utf-8")


def _run_dead_code_check(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "CRAIK_DEAD_CODE_ROOT": str(tmp_path)}
    return subprocess.run(
        [sys.executable, str(_SCRIPT)],
        check=False,
        env=env,
        text=True,
        capture_output=True,
    )


def test_dead_code_check_passes_known_clean_tree(tmp_path: Path) -> None:
    _write_fixture(
        tmp_path,
        """
        def public_value(_input: int) -> int:
            return 1

        public_value(1)
        """,
    )

    result = _run_dead_code_check(tmp_path)

    assert result.returncode == 0, result.stderr


def test_dead_code_check_fails_known_dirty_tree(tmp_path: Path) -> None:
    _write_fixture(
        tmp_path,
        """
        def used(format: str) -> int:
            return 1

        used("json")
        """,
    )

    result = _run_dead_code_check(tmp_path)

    assert result.returncode == 1
    assert "unused variable 'format'" in result.stdout


def test_vulture_whitelist_is_bounded_and_documented() -> None:
    whitelist = Path(__file__).resolve().parents[1] / "vulture-whitelist.py"
    lines = [
        line
        for line in whitelist.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith('"""')
    ]

    assert len(lines) <= 20
    for line in lines:
        assert "# reason:" in line
