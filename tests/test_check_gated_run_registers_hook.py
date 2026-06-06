"""Tests for the gated-run hook-registration structural guard.

Confirms the guard PASSES on the real wiring (Wire-T2/T3) and -- the load-bearing
part -- that it FAILS when a vendor's gated run does NOT register the craik-hook,
so the guard actually pins the "ungated-while-claiming-gated" regression class.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
_GUARD_PATH = _SCRIPTS / "check_gated_run_registers_hook.py"


def _load_guard():
    spec = importlib.util.spec_from_file_location("check_gated_run_registers_hook", _GUARD_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_guard_passes_on_real_wiring() -> None:
    result = subprocess.run(
        [sys.executable, str(_GUARD_PATH)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_guard_checks_pass_individually() -> None:
    guard = _load_guard()
    assert guard.check_claude() == []
    assert guard.check_gemini() == []


def test_event_has_craik_hook_detects_missing_registration() -> None:
    """The detector is real: it returns False when no craik-hook is registered."""
    guard = _load_guard()
    # An operator-only settings block (no craik-hook) -> NOT detected as registered.
    operator_only = {
        "hooks": {"PreToolUse": [{"hooks": [{"type": "command", "command": "something-else"}]}]}
    }
    assert guard._event_has_craik_hook(operator_only, "PreToolUse") is False
    # A craik-hook entry -> detected.
    with_craik = {
        "hooks": {"PreToolUse": [{"hooks": [{"type": "command", "command": guard.HOOK_COMMAND}]}]}
    }
    assert guard._event_has_craik_hook(with_craik, "PreToolUse") is True
    # Wrong event -> not detected (the gate fires on the SPECIFIC event).
    assert guard._event_has_craik_hook(with_craik, "BeforeTool") is False
