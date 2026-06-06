"""Wire-T2: the GATED real-claude spawn registers craik's PreToolUse hook.

Today the real ``claude`` spawn registers NO hook (delegate-observe). For a
GATED run -- indicated by the bridge socket env (``CRAIK_HOOK_SOCKET``) being
present -- the spawn must instead:

* run under a fail-safe gate mode (``dontAsk`` by default, the deny-by-default
  gate the craik-hook approves; ``bypassPermissions`` ONLY if the operator
  explicitly chose it -- respecting their escape hatch, the hook still enforces
  deny per the live smoke), and
* pass ``--settings <craik-owned file>`` whose content registers a PreToolUse
  hook invoking ``craik-hook``.

The craik-owned settings file must NOT live under the operator's cwd and must be
removed after the run (no files left in their workspace). The bridge socket env
must flow to the spawned subprocess.

A NON-gated run (no ``CRAIK_HOOK_SOCKET``) is UNCHANGED: no ``--settings``, the
existing ``--permission-mode`` passthrough, delegate-observe.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from craik.runtime.backend import claude_code
from craik.runtime.backend.adapters.hook_bridge import SOCKET_ENV
from craik.runtime.backend.claude_code_settings import CLAUDE_PERMISSION_MODE_ENV


class _FakeProcess:
    """Minimal Popen stand-in: one result line then a clean exit."""

    def __init__(self) -> None:
        self.stdout = iter(['{"type":"result","result":"done"}\n'])
        self.returncode = 0
        self.pid = 4321

    def poll(self):
        return 0

    def wait(self, timeout=None):
        return 0

    def terminate(self) -> None:  # pragma: no cover - not exercised
        pass

    def kill(self) -> None:  # pragma: no cover - not exercised
        pass


def _install_capturing_spawn(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Fake the claude spawn seam; capture argv/env/cwd + the settings file body.

    The settings file content is read back at spawn time (while the process is
    'running') so the post-run cleanup cannot hide what was registered.
    """
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        claude_code.shutil,
        "which",
        lambda command: "/usr/local/bin/claude" if command == "claude" else None,
    )

    def _fake_spawn(command, *, stdout, stderr, env, **kwargs):
        captured["command"] = [str(part) for part in command]
        captured["env"] = dict(env or {})
        captured["cwd"] = kwargs.get("cwd")
        # Read the --settings file while the run is live (before cleanup).
        argv = captured["command"]
        if "--settings" in argv:
            settings_path = Path(argv[argv.index("--settings") + 1])
            captured["settings_path"] = settings_path
            captured["settings_existed_during_run"] = settings_path.exists()
            if settings_path.exists():
                captured["settings_body"] = json.loads(
                    settings_path.read_text(encoding="utf-8")
                )
        return _FakeProcess()

    monkeypatch.setattr(claude_code, "start_reviewed_local_process", _fake_spawn)
    return captured


def _gated_env(tmp_path: Path) -> dict[str, str]:
    return {
        "CRAIK_HOME": str(tmp_path / ".craik"),
        SOCKET_ENV: str(tmp_path / "bridge.sock"),
    }


def _ungated_env(tmp_path: Path) -> dict[str, str]:
    return {"CRAIK_HOME": str(tmp_path / ".craik")}


def _registers_craik_hook(body: object) -> bool:
    """True when a settings dict registers a PreToolUse hook invoking craik-hook."""
    if not isinstance(body, dict):
        return False
    entries = body.get("hooks", {}).get("PreToolUse", [])
    for entry in entries:
        for inner in entry.get("hooks", []):
            if inner.get("command") == "craik-hook":
                return True
    return False


def test_gated_run_defaults_to_dontask_and_registers_hook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GATED + no explicit bypass: dontAsk gate + a craik-hook --settings file."""
    captured = _install_capturing_spawn(monkeypatch)
    env = _gated_env(tmp_path)

    claude_code._execute_claude_code_prompt("do the thing", env=env)

    argv = captured["command"]
    assert "--permission-mode" in argv
    assert argv[argv.index("--permission-mode") + 1] == "dontAsk"
    assert "--settings" in argv

    # The settings file registered the PreToolUse craik-hook and existed while
    # the run was live.
    assert captured["settings_existed_during_run"] is True
    assert _registers_craik_hook(captured["settings_body"])

    # The craik-owned settings file does NOT live under the operator's cwd...
    settings_path = captured["settings_path"]
    cwd = Path.cwd().resolve()
    assert cwd not in settings_path.resolve().parents
    # ...and is removed after the run (nothing left in the workspace).
    assert not settings_path.exists()

    # The bridge socket env flows to the spawned subprocess.
    assert captured["env"][SOCKET_ENV] == env[SOCKET_ENV]


def test_gated_run_overrides_other_operator_modes_with_dontask(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-bypass operator mode is OVERRIDDEN by the dontAsk gate (governance)."""
    captured = _install_capturing_spawn(monkeypatch)
    env = {**_gated_env(tmp_path), CLAUDE_PERMISSION_MODE_ENV: "acceptEdits"}

    claude_code._execute_claude_code_prompt("do the thing", env=env)

    argv = captured["command"]
    assert argv[argv.index("--permission-mode") + 1] == "dontAsk"
    assert "acceptEdits" not in argv
    assert "--settings" in argv


def test_gated_run_respects_operator_bypass_but_still_registers_hook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GATED + operator chose bypassPermissions: keep bypass, still register hook."""
    captured = _install_capturing_spawn(monkeypatch)
    env = {**_gated_env(tmp_path), CLAUDE_PERMISSION_MODE_ENV: "bypassPermissions"}

    claude_code._execute_claude_code_prompt("do the thing", env=env)

    argv = captured["command"]
    assert argv[argv.index("--permission-mode") + 1] == "bypassPermissions"
    assert "--settings" in argv
    assert _registers_craik_hook(captured["settings_body"])


def test_ungated_run_has_no_settings_and_passes_through_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NON-gated: no --settings, existing permission-mode passthrough, no forced dontAsk."""
    captured = _install_capturing_spawn(monkeypatch)
    env = {**_ungated_env(tmp_path), CLAUDE_PERMISSION_MODE_ENV: "acceptEdits"}

    claude_code._execute_claude_code_prompt("do the thing", env=env)

    argv = captured["command"]
    assert "--settings" not in argv
    assert argv[argv.index("--permission-mode") + 1] == "acceptEdits"
    assert "dontAsk" not in argv


def test_ungated_run_with_no_mode_has_no_permission_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NON-gated + no operator mode: argv has neither --settings nor a forced gate."""
    captured = _install_capturing_spawn(monkeypatch)
    env = _ungated_env(tmp_path)

    claude_code._execute_claude_code_prompt("do the thing", env=env)

    argv = captured["command"]
    assert "--settings" not in argv
    assert "--permission-mode" not in argv
