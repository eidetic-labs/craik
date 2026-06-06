"""Wire-T3: the GATED real-gemini spawn registers craik's BeforeTool hook.

Unlike claude (``--settings <file>``), the ``gemini`` CLI has NO per-run
settings-path flag, so craik MUST fall back to MERGING its BeforeTool hook into
the project ``.gemini/settings.json`` and RESTORING the operator's original
bytes on teardown (``registered_hook_settings``). For a GATED run -- indicated
by the bridge socket env (``CRAIK_HOOK_SOCKET``) being present in the adapter's
``hook_env`` overlay -- the spawn must:

* merge craik's BeforeTool ``craik-hook`` entry into ``.gemini/settings.json``
  (additively, never clobbering the operator's own hooks), and
* spawn with ``GEMINI_CLI_TRUST_WORKSPACE=true`` (the load-bearing precondition;
  the hook silently does NOT fire in an untrusted workspace).

After the run the operator's ORIGINAL ``.gemini/settings.json`` is restored (or
removed if it did not exist). A NON-gated run (no ``hook_env``) registers
NOTHING: ``.gemini/settings.json`` is untouched (delegate-observe). The
AUTHORITATIVE gemini ``--approval-mode`` that makes the BeforeTool hook the gate
is PENDING the operator smoke (``scripts/smoke_gemini_hook.sh``); this task wires
the mode-INDEPENDENT mechanisms (hook registration + workspace trust) and does
NOT force a gate mode.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from craik.runtime.backend.adapters.base import RunContext
from craik.runtime.backend.adapters.google_cli import GoogleCLI
from craik.runtime.backend.adapters.hook_bridge import SOCKET_ENV, VENDOR_ENV

_FIXTURE_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "adapters"
_GEMINI_FIXTURE = _FIXTURE_DIR / "gemini_cli_stream_raw.jsonl"


def _env(tmp_path: Path) -> dict[str, str]:
    return {"CRAIK_HOME": str(tmp_path / ".craik")}


def _repo(tmp_path: Path, monkeypatch) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Repo\n", encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    monkeypatch.chdir(repo)
    return repo


class _FakeProcess:
    """Minimal Popen stand-in yielding recorded lines then a clean exit."""

    def __init__(self, lines: list[str]) -> None:
        self.stdout = iter(line if line.endswith("\n") else line + "\n" for line in lines)
        self.returncode = 0

    def poll(self):
        return None

    def wait(self, timeout=None):
        return 0

    def terminate(self) -> None:  # pragma: no cover - not exercised on clean exit
        pass

    def kill(self) -> None:  # pragma: no cover - not exercised on clean exit
        pass


def _install_spawn_probe(monkeypatch, repo: Path) -> dict[str, object]:
    """Fake the gemini subprocess; capture env + the LIVE ``.gemini/settings.json``.

    The settings file is read back AT SPAWN TIME (while the run is 'live', before
    the merge-and-restore context manager tears down) so the post-run restore
    cannot hide what was registered during the run.
    """
    captured: dict[str, object] = {}
    original_popen = subprocess.Popen
    lines = _GEMINI_FIXTURE.read_text(encoding="utf-8").splitlines()

    def _popen(args, **kwargs):
        if Path(args[0]).name != "gemini":
            return original_popen(args, **kwargs)
        captured["env"] = dict(kwargs.get("env") or {})
        settings = repo / ".gemini" / "settings.json"
        captured["settings_existed_during_run"] = settings.exists()
        if settings.exists():
            captured["settings_body"] = json.loads(settings.read_text(encoding="utf-8"))
        return _FakeProcess(lines)

    monkeypatch.setattr("craik.runtime.sandbox.local_process_backend.subprocess.Popen", _popen)
    return captured


def _ctx(env: dict[str, str]) -> RunContext:
    return RunContext(
        prompt="Review the implementation plan",
        env=env,
        emit=lambda event: None,
        decide=lambda request: "allow",
        require_operator_approval=False,
    )


def _registers_craik_hook(body: object) -> bool:
    """True when a settings dict registers a BeforeTool hook invoking craik-hook."""
    if not isinstance(body, dict):
        return False
    entries = body.get("hooks", {}).get("BeforeTool", [])
    for entry in entries:
        for inner in entry.get("hooks", []):
            if inner.get("command") == "craik-hook":
                return True
    return False


def test_gated_run_registers_before_tool_hook_and_trusts_workspace(
    tmp_path: Path, monkeypatch
) -> None:
    """GATED (hook_env present): merge BeforeTool craik-hook + trust the workspace."""
    repo = _repo(tmp_path, monkeypatch)
    env = _env(tmp_path)
    captured = _install_spawn_probe(monkeypatch, repo)

    adapter = GoogleCLI(original_env=env)
    adapter.hook_env = {SOCKET_ENV: str(tmp_path / "bridge.sock"), VENDOR_ENV: "google"}
    list(adapter.run(_ctx(env)))

    # The craik BeforeTool hook was registered in .gemini/settings.json DURING
    # the live run...
    assert captured["settings_existed_during_run"] is True
    assert _registers_craik_hook(captured["settings_body"])
    # ...the workspace-trust flag (load-bearing precondition) reached the spawn...
    assert captured["env"]["GEMINI_CLI_TRUST_WORKSPACE"] == "true"
    # ...alongside the bridge socket overlay.
    assert captured["env"][SOCKET_ENV] == str(tmp_path / "bridge.sock")
    assert captured["env"][VENDOR_ENV] == "google"


def test_gated_run_restores_operator_settings_after_run(tmp_path: Path, monkeypatch) -> None:
    """The operator's pre-existing .gemini/settings.json is RESTORED, not clobbered."""
    repo = _repo(tmp_path, monkeypatch)
    gemini_dir = repo / ".gemini"
    gemini_dir.mkdir()
    original = {
        "theme": "operator-theme",
        "hooks": {"BeforeTool": [{"matcher": "*", "hooks": [{"command": "operator-own-hook"}]}]},
    }
    settings = gemini_dir / "settings.json"
    settings.write_text(json.dumps(original, indent=2) + "\n", encoding="utf-8")
    original_bytes = settings.read_bytes()

    env = _env(tmp_path)
    captured = _install_spawn_probe(monkeypatch, repo)

    adapter = GoogleCLI(original_env=env)
    adapter.hook_env = {SOCKET_ENV: str(tmp_path / "bridge.sock"), VENDOR_ENV: "google"}
    list(adapter.run(_ctx(env)))

    # DURING the run craik's hook was additively merged alongside the operator's.
    body = captured["settings_body"]
    assert _registers_craik_hook(body)
    before_tool = body["hooks"]["BeforeTool"]
    assert any(
        h.get("command") == "operator-own-hook"
        for entry in before_tool
        for h in entry.get("hooks", [])
    ), "operator's own BeforeTool hook must be preserved during the run"

    # AFTER the run the operator's original bytes are restored verbatim.
    assert settings.read_bytes() == original_bytes


def test_ungated_run_does_not_touch_gemini_settings(tmp_path: Path, monkeypatch) -> None:
    """NON-gated (no hook_env): NOTHING is written to .gemini/settings.json."""
    repo = _repo(tmp_path, monkeypatch)
    env = _env(tmp_path)
    captured = _install_spawn_probe(monkeypatch, repo)

    adapter = GoogleCLI(original_env=env)
    # No hook_env -> ungated observe-only run.
    list(adapter.run(_ctx(env)))

    # No craik hook registered, and no .gemini/settings.json created.
    assert captured["settings_existed_during_run"] is False
    assert not (repo / ".gemini" / "settings.json").exists()


def test_ungated_run_leaves_operator_settings_untouched(tmp_path: Path, monkeypatch) -> None:
    """NON-gated + operator has settings: file is byte-for-byte unchanged."""
    repo = _repo(tmp_path, monkeypatch)
    gemini_dir = repo / ".gemini"
    gemini_dir.mkdir()
    settings = gemini_dir / "settings.json"
    settings.write_text('{"theme": "operator-theme"}\n', encoding="utf-8")
    original_bytes = settings.read_bytes()

    env = _env(tmp_path)
    _install_spawn_probe(monkeypatch, repo)

    adapter = GoogleCLI(original_env=env)
    list(adapter.run(_ctx(env)))

    assert settings.read_bytes() == original_bytes
