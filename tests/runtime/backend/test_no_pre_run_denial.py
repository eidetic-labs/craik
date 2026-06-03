"""Approval Task 4: pin the invariant "no provider x surface pre-denies a run".

Craik governance is delegate-and-observe: every provider x surface STARTS the
run (the vendor governs its own tools via its permission mode; craik observes
the stream and writes receipts). NO surface may raise an up-front approval/denial
error that blocks a run before it begins when no operator-approval flag is set.

A prior investigation (verified) found the Claude path held the ONLY pre-run
denial (``_require_claude_code_run_approval``); it was removed so the run always
starts. These regression tests PIN that invariant so it cannot silently return:
per gatable surface they drive the REAL ``run()`` path to its execution/spawn
seam with a FAKE subprocess / fixture transport (no real CLI or network) and
assert the run PROCEEDS to completion rather than raising up-front.

Surfaces covered + how the execution boundary is stubbed:

* ``anthropic-cli`` (the surface we changed) -- the ``claude`` subprocess is
  faked at the ``local_process_backend`` ``Popen`` seam (the same seam the
  audited-core tests fake); ``run()`` reaches the spawn and completes.
* ``google-cli`` (representative gating CLI) -- the ``gemini`` subprocess is
  faked at the same seam, replaying a recorded ``stream-json`` fixture.
* ``openai-api`` (representative API surface) -- driven through the deterministic
  ``CRAIK_FIXTURE=1`` provider run (no real HTTP), the same controlled
  environment the audited-core provider tests use.

Codex (``openai-cli``) is observe-only: ``supports_live_gating()`` is False and
its run STARTS + is recorded as observed (``decided_by="bypass"``), never falsely
operator-approved. A live-gating REQUEST (``require_operator_approval=True``) is
refused before any spawn -- that refusal is honest routing, NOT a pre-run denial
of an ungated run.
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from craik.runtime.auth.profile import AuthProfile, CredentialKind
from craik.runtime.auth.store import AuthProfileStore
from craik.runtime.backend.adapters.anthropic_cli import AnthropicCLI
from craik.runtime.backend.adapters.base import RunContext
from craik.runtime.backend.adapters.google_cli import GoogleCLI
from craik.runtime.backend.adapters.openai_api import OpenAIAPI
from craik.runtime.backend.adapters.openai_cli import LiveGatingUnsupported, OpenAICLI
from craik.runtime.shell.slash_commands import dispatch_slash_command

# Recorded vendor-CLI stream fixtures, resolved at import time so the per-test
# ``chdir`` into the fixture repo does not break relative reads.
_FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "adapters"
_GEMINI_FIXTURE = _FIXTURE_DIR / "gemini_cli_stream_raw.jsonl"
_CODEX_FIXTURE = _FIXTURE_DIR / "codex_exec_stream_raw.jsonl"


def _env(tmp_path: Path) -> dict[str, str]:
    return {"CRAIK_HOME": str(tmp_path / ".craik")}


def _repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Repo\n", encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    monkeypatch.chdir(repo)
    return repo


def _ctx(env: dict[str, str], *, require_operator_approval: bool = False) -> RunContext:
    """A RunContext with NO operator-approval flag set (the ungated default)."""
    return RunContext(
        prompt="Review the implementation plan",
        env=env,
        emit=lambda event: None,
        decide=lambda request: "allow",
        require_operator_approval=require_operator_approval,
    )


class _FakeProcess:
    """Minimal Popen stand-in yielding recorded lines then a clean exit."""

    def __init__(self, lines: list[str], returncode: int = 0) -> None:
        self.stdout = iter(line if line.endswith("\n") else line + "\n" for line in lines)
        self._returncode = returncode
        self.returncode = returncode

    def poll(self):
        return None

    def wait(self, timeout=None):
        return self._returncode

    def terminate(self) -> None:  # pragma: no cover - not exercised on clean exit
        self.returncode = self._returncode

    def kill(self) -> None:  # pragma: no cover - not exercised on clean exit
        self.returncode = self._returncode


def _install_fake_subprocess(
    monkeypatch: pytest.MonkeyPatch, binary: str, fixture: Path
) -> list[list[str]]:
    """Fake the ``binary`` subprocess to replay ``fixture``; record spawned argvs."""
    spawned: list[list[str]] = []
    original_popen = subprocess.Popen
    lines = fixture.read_text(encoding="utf-8").splitlines()

    def _popen(args, **kwargs):
        if Path(args[0]).name != binary:
            return original_popen(args, **kwargs)
        spawned.append([str(a) for a in args])
        return _FakeProcess(lines)

    monkeypatch.setattr("craik.runtime.sandbox.local_process_backend.subprocess.Popen", _popen)
    return spawned


def _install_claude_marker_subprocess(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Fake the ``claude`` subprocess at the Popen seam; record spawned argvs."""
    spawned: list[list[str]] = []
    original_popen = subprocess.Popen

    monkeypatch.setattr(
        "craik.runtime.backend.claude_code.shutil.which",
        lambda command: "/usr/local/bin/claude" if command == "claude" else None,
    )

    def _popen(args, **kwargs):
        if Path(args[0]).name != "claude":
            return original_popen(args, **kwargs)
        spawned.append([str(a) for a in args])
        return _FakeProcess(['{"type":"result","result":"done from no-pre-deny test"}'])

    monkeypatch.setattr(
        "craik.runtime.sandbox.local_process_backend.subprocess.Popen", _popen
    )
    return spawned


def _claude_cli_marker_profile() -> AuthProfile:
    return AuthProfile(
        id="anthropic:default",
        kind=CredentialKind.MARKER,
        provider_family="anthropic",
        metadata={"external_runtime": "claude-cli", "credential_mode": "claude-cli"},
        created_at=datetime(2026, 5, 22, 12, 0, tzinfo=UTC),
        last_status="ok",
    )


# --- anthropic-cli: the surface we changed ----------------------------------


def test_anthropic_cli_run_starts_without_approval_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """anthropic-cli reaches the claude spawn + completes; never pre-denies."""
    _repo(tmp_path, monkeypatch)
    env = _env(tmp_path)
    AuthProfileStore.from_env(env).put(_claude_cli_marker_profile())
    dispatch_slash_command("/model set anthropic/claude-sonnet-4-20250514", env=env)
    spawned = _install_claude_marker_subprocess(monkeypatch)

    adapter = AnthropicCLI(original_env=env)
    # No approval flag, require_operator_approval=False: the run must PROCEED to
    # the spawn seam and complete, not raise an up-front approval/denial error.
    events = list(adapter.run(_ctx(env)))
    types = [event.type for event in events]

    assert spawned and Path(spawned[0][0]).name == "claude", "claude subprocess was reached"
    assert types[-1] == "run.completed", "run started and completed (not pre-denied)"
    # Honest delegate-observe attribution: no operator approved an ungated run.
    receipts = [e for e in events if e.type == "receipt.created"]
    assert receipts
    assert all(e.data["execution"] == "delegated-observed" for e in receipts)


# --- google-cli: representative gating CLI ----------------------------------


def test_google_cli_run_starts_without_approval_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """google-cli reaches the gemini spawn + completes; never pre-denies."""
    _repo(tmp_path, monkeypatch)
    env = _env(tmp_path)
    spawned = _install_fake_subprocess(monkeypatch, "gemini", _GEMINI_FIXTURE)

    adapter = GoogleCLI(original_env=env)
    events = list(adapter.run(_ctx(env)))
    types = [event.type for event in events]

    assert spawned and Path(spawned[0][0]).name == "gemini", "gemini subprocess was reached"
    assert types[-1] == "run.completed", "run started and completed (not pre-denied)"
    receipts = [e for e in events if e.type == "receipt.created"]
    assert receipts
    assert all(e.data["execution"] == "delegated-observed" for e in receipts)


# --- openai-api: representative API surface ---------------------------------


def test_openai_api_run_starts_without_approval_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """openai-api reaches the provider transport + completes; never pre-denies."""
    _repo(tmp_path, monkeypatch)
    # CRAIK_FIXTURE=1 drives the deterministic provider run (no real HTTP), the
    # same controlled environment the audited-core provider tests use.
    env = {**_env(tmp_path), "CRAIK_FIXTURE": "1"}

    adapter = OpenAIAPI(original_env=env)
    events = list(adapter.run(_ctx(env)))
    types = [event.type for event in events]

    assert "run.started" in types, "the provider run started (not pre-denied)"
    assert types[-1] == "run.completed", "the run reached completion"
    receipts = [e for e in events if e.type == "receipt.created"]
    assert receipts, "the run produced audited receipts"
    assert all(e.source == "openai-api" for e in events)


# --- openai-cli (Codex): observe-only honesty -------------------------------


def test_openai_cli_is_observe_only_not_live_gatable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Codex declares observe-only: supports_live_gating() is False (not a stub)."""
    adapter = OpenAICLI(original_env=_env(tmp_path))
    assert adapter.supports_live_gating() is False


def test_openai_cli_run_starts_and_records_observed_not_operator_approved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Codex run STARTS (not pre-denied) and is recorded observed, never operator-approved."""
    _repo(tmp_path, monkeypatch)
    env = _env(tmp_path)
    spawned = _install_fake_subprocess(monkeypatch, "codex", _CODEX_FIXTURE)

    adapter = OpenAICLI(original_env=env)
    # No approval flag: the observe-only run must START + complete.
    events = list(adapter.run(_ctx(env)))
    types = [event.type for event in events]

    assert spawned and Path(spawned[0][0]).name == "codex", "codex subprocess was reached"
    assert types[-1] == "run.completed", "observe-only run started and completed"
    receipts = [e for e in events if e.type == "receipt.created"]
    assert receipts
    # Honest observation: bypass (ungoverned audit flag), NEVER falsely operator.
    for receipt in receipts:
        assert receipt.data["decided_by"] == "bypass"
        assert receipt.data["decided_by"] != "operator"
        assert receipt.data["execution"] == "delegated-observed"


def test_openai_cli_refuses_live_gating_request_but_does_not_pre_deny_ungated_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The observe-only refusal is a live-gating REQUEST refusal, not an ungated pre-denial.

    A live-gating request (``require_operator_approval=True``) is refused before
    any spawn -- honest routing, since craik cannot enforce a veto on this surface
    (route live governance via openai-api). But the DEFAULT ungated run is NOT
    pre-denied: it starts and is observed.
    """
    _repo(tmp_path, monkeypatch)
    env = _env(tmp_path)
    spawned = _install_fake_subprocess(monkeypatch, "codex", _CODEX_FIXTURE)

    adapter = OpenAICLI(original_env=env)
    # A live-gating REQUEST is refused before any subprocess spawns.
    with pytest.raises(LiveGatingUnsupported):
        list(adapter.run(_ctx(env, require_operator_approval=True)))
    assert spawned == [], "no subprocess spawned when a live-gating request is refused"

    # The ungated run on the SAME adapter is not pre-denied -- it starts.
    events = list(adapter.run(_ctx(env)))
    assert spawned and Path(spawned[0][0]).name == "codex"
    assert [e.type for e in events][-1] == "run.completed"
