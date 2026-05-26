"""Tests for the contract dispatch runtime-consumption guard."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_guard_passes_on_current_tree() -> None:
    result = subprocess.run(
        ["python3", str(ROOT / "scripts" / "check_contract_dispatch_consumed.py")],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
