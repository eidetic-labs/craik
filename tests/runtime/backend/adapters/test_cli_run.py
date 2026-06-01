"""Tests for the live GoogleCLI / OpenAICLI ``run()`` + the audited CLI core (5.5b).

These drive the REAL ``run()`` path with a FAKE subprocess: the
``gemini_cli_stream_raw.jsonl`` / ``codex_exec_stream_raw.jsonl`` recorded lines
are fed through a monkeypatched ``subprocess.Popen`` at the SAME
``local_process_backend`` seam the claude core tests fake, so no real CLI is
required. They assert the typed event sequence, audited persistence (run +
receipts read back from the store), the OpenAICLI gate-refusal-before-spawn, and
graceful completed-with-error handling of a failed subprocess.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from craik.runtime.backend.adapters.base import RunContext
from craik.runtime.backend.adapters.google_cli import GoogleCLI
from craik.runtime.backend.adapters.openai_cli import LiveGatingUnsupported, OpenAICLI
from craik.runtime.backend.cli.cli_audited import run_cli_core
from craik.runtime.store import LocalStore

# Resolve to absolute paths at import time so the per-test ``chdir`` into the
# fixture repo does not break relative fixture reads.
_FIXTURE_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "adapters"
_GEMINI_FIXTURE = _FIXTURE_DIR / "gemini_cli_stream_raw.jsonl"
_CODEX_FIXTURE = _FIXTURE_DIR / "codex_exec_stream_raw.jsonl"


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
    monkeypatch, binary: str, fixture: Path, returncode: int = 0
) -> list[list[str]]:
    """Fake the ``binary`` subprocess to replay ``fixture``; record spawned argvs."""
    spawned: list[list[str]] = []
    original_popen = subprocess.Popen
    lines = fixture.read_text(encoding="utf-8").splitlines()

    def _popen(args, **kwargs):
        if Path(args[0]).name != binary:
            return original_popen(args, **kwargs)
        spawned.append([str(a) for a in args])
        return _FakeProcess(lines, returncode=returncode)

    monkeypatch.setattr("craik.runtime.sandbox.local_process_backend.subprocess.Popen", _popen)
    return spawned


def _ctx(env: dict[str, str], *, require_operator_approval: bool = False) -> RunContext:
    return RunContext(
        prompt="Review the implementation plan",
        env=env,
        emit=lambda event: None,
        decide=lambda request: "allow",
        require_operator_approval=require_operator_approval,
    )


# --- GoogleCLI.run() ---------------------------------------------------------


def test_google_cli_run_yields_typed_sequence_and_persists(tmp_path: Path, monkeypatch) -> None:
    _repo(tmp_path, monkeypatch)
    env = _env(tmp_path)
    spawned = _install_fake_subprocess(monkeypatch, "gemini", _GEMINI_FIXTURE)

    adapter = GoogleCLI(original_env=env)
    events = list(adapter.run(_ctx(env)))
    types = [event.type for event in events]

    # A real gemini argv was spawned (stream-json), and the typed sequence
    # carries the coalesced text, tool.used, the delegated-observed receipt, and
    # ends in run.completed.
    assert spawned and Path(spawned[0][0]).name == "gemini"
    assert "stream-json" in spawned[0]
    assert types.count("assistant_text") == 1
    assert "tool.used" in types
    assert types[-1] == "run.completed"
    receipts = [e for e in events if e.type == "receipt.created"]
    assert receipts
    assert all(e.source == "google-cli" for e in events)
    assert receipts[0].data["execution"] == "delegated-observed"

    # Audited persistence: the run + its receipts are readable from a fresh store.
    run_completed = events[-1]
    store = LocalStore.from_env(env)
    try:
        store.initialize()
        assert store.get_task_run(run_completed.run_id) is not None
        run = store.get_task_run(run_completed.run_id)
        assert run is not None
        for receipt_id in run.receipt_ids:
            assert store.get_receipt(receipt_id) is not None
    finally:
        store.close()


# --- OpenAICLI.run() ---------------------------------------------------------


def test_openai_cli_run_yields_observe_sequence(tmp_path: Path, monkeypatch) -> None:
    _repo(tmp_path, monkeypatch)
    env = _env(tmp_path)
    spawned = _install_fake_subprocess(monkeypatch, "codex", _CODEX_FIXTURE)

    adapter = OpenAICLI(original_env=env)
    events = list(adapter.run(_ctx(env)))
    types = [event.type for event in events]

    assert spawned and Path(spawned[0][0]).name == "codex"
    assert "exec" in spawned[0] and "--json" in spawned[0]
    assert types.count("assistant_text") == 1
    assert "tool.used" in types
    assert types[-1] == "run.completed"
    receipts = [e for e in events if e.type == "receipt.created"]
    assert receipts
    assert all(e.source == "openai-cli" for e in events)
    # Observe-only attribution: the receipt is decided_by="bypass", never operator.
    assert receipts[0].data["decided_by"] == "bypass"
    assert receipts[0].data["execution"] == "delegated-observed"


def test_openai_cli_run_refuses_to_gate_before_spawn(tmp_path: Path, monkeypatch) -> None:
    _repo(tmp_path, monkeypatch)
    env = _env(tmp_path)
    spawned = _install_fake_subprocess(monkeypatch, "codex", _CODEX_FIXTURE)

    adapter = OpenAICLI(original_env=env)
    # require_operator_approval=True asks for live gating, which observe-only must
    # refuse BEFORE spawning any subprocess.
    with pytest.raises(LiveGatingUnsupported):
        list(adapter.run(_ctx(env, require_operator_approval=True)))

    assert spawned == [], "no subprocess may be spawned when gating is refused"


# --- Subprocess failure -> graceful completed-with-error ---------------------


def test_cli_core_handles_nonzero_exit_as_completed_with_error(tmp_path: Path, monkeypatch) -> None:
    _repo(tmp_path, monkeypatch)
    env = _env(tmp_path)
    # Nonzero exit AND no usable output: a failed subprocess must NOT hang/crash.
    _install_fake_subprocess(monkeypatch, "gemini", _GEMINI_FIXTURE, returncode=2)

    streamed: list[str] = []
    core = run_cli_core(
        prompt="Review the implementation plan",
        env=env,
        argv=["gemini", "-p", "x", "--output-format", "stream-json"],
        spawn_env=dict(env),
        vendor="google",
        stream=streamed.append,
    )

    assert core.status == "failed"
    assert core.run_id is not None
    # The failed run is still persisted as a completed-with-error audited record.
    store = LocalStore.from_env(env)
    try:
        store.initialize()
        run = store.get_task_run(core.run_id)
        assert run is not None
        assert run.status == "failed"
        for receipt_id in core.receipt_ids:
            assert store.get_receipt(receipt_id) is not None
    finally:
        store.close()


def test_cli_core_handles_start_error_without_hanging(tmp_path: Path, monkeypatch) -> None:
    _repo(tmp_path, monkeypatch)
    env = _env(tmp_path)

    original_popen = subprocess.Popen

    def _raise(args, **kwargs):
        if Path(args[0]).name == "gemini":
            raise OSError("boom")
        return original_popen(args, **kwargs)

    monkeypatch.setattr("craik.runtime.sandbox.local_process_backend.subprocess.Popen", _raise)

    core = run_cli_core(
        prompt="Review the implementation plan",
        env=env,
        argv=["gemini", "-p", "x"],
        spawn_env=dict(env),
        vendor="google",
        stream=lambda line: None,
    )

    assert core.status == "failed"
    assert core.run_id is not None
