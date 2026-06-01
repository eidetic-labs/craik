"""Tests for the typed ``run()`` composing the audited cores (Task 5.5a).

These prove the live-today adapter ``run()``s produce the NEW typed event
sequence by COMPOSING the Task-5.4 cores -- they do NOT re-run the legacy
emission path:

* ``AnthropicCLI.run`` composes ``run_claude_code_core`` (the core spawns the
  claude subprocess); ``run()`` re-shapes EMISSION only, yielding the coalesced
  ``assistant_text`` + ``tool.used`` (during the stream) and the framing
  (``run.started`` / ``receipt.created`` source=anthropic-cli execution=
  delegated-observed / ``run.completed``) after.
* the API adapters' ``run`` compose ``run_provider_core`` (via
  ``run_provider_typed``) and yield typed events (source=<vendor>-api,
  execution=craik receipts) derived from the ``ProviderCoreResult``, closing the
  core's store exactly once.

The controlled environments mirror the audited-core unit tests: the claude path
reuses the deterministic claude-marker subprocess; the provider path reuses the
``CRAIK_FIXTURE=1`` deterministic provider run.
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from craik.runtime.auth.profile import AuthProfile, CredentialKind
from craik.runtime.auth.store import AuthProfileStore
from craik.runtime.backend.adapters.anthropic_api import AnthropicAPI
from craik.runtime.backend.adapters.anthropic_cli import AnthropicCLI
from craik.runtime.backend.adapters.base import RunContext
from craik.runtime.backend.adapters.openai_api import OpenAIAPI
from craik.runtime.shell.slash_commands import dispatch_slash_command
from craik.runtime.store import LocalStore


def _env(tmp_path: Path) -> dict[str, str]:
    return {"CRAIK_HOME": str(tmp_path / ".craik")}


def _repo(tmp_path: Path, monkeypatch) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Repo\n", encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    monkeypatch.chdir(repo)
    return repo


def _ctx(prompt: str) -> RunContext:
    return RunContext(
        prompt=prompt,
        env={},
        emit=lambda event: None,
        decide=lambda request: "allow",
        require_operator_approval=False,
    )


# --- claude CLI path: compose the claude core -------------------------------


def _install_claude_marker_subprocess(monkeypatch) -> None:
    original_popen = subprocess.Popen

    monkeypatch.setattr(
        "craik.runtime.backend.claude_code.shutil.which",
        lambda command: "/usr/local/bin/claude" if command == "claude" else None,
    )

    class _Process:
        stdout = iter(
            [
                (
                    '{"type":"assistant","message":{"content":[{"type":"tool_use",'
                    '"name":"Read","input":{"file_path":"README.md"}}]}}\n'
                ),
                (
                    '{"type":"assistant","message":{"content":[{"type":"text",'
                    '"text":"Reviewing the plan now."}]}}\n'
                ),
                '{"type":"result","result":"done from typed run"}\n',
            ]
        )

        def poll(self):
            return None

        def wait(self, timeout=None):
            return 0

    def _popen(args, **kwargs):
        if Path(args[0]).name != "claude":
            return original_popen(args, **kwargs)
        return _Process()

    monkeypatch.setattr(
        "craik.runtime.sandbox.local_process_backend.subprocess.Popen",
        _popen,
    )


def _claude_cli_marker_profile() -> AuthProfile:
    return AuthProfile(
        id="anthropic:default",
        kind=CredentialKind.MARKER,
        provider_family="anthropic",
        metadata={"external_runtime": "claude-cli", "credential_mode": "claude-cli"},
        created_at=datetime(2026, 5, 22, 12, 0, tzinfo=UTC),
        last_status="ok",
    )


def test_anthropic_cli_run_composes_claude_core_typed_sequence(tmp_path: Path, monkeypatch) -> None:
    _repo(tmp_path, monkeypatch)
    env = _env(tmp_path)
    AuthProfileStore.from_env(env).put(_claude_cli_marker_profile())
    dispatch_slash_command("/model set anthropic/claude-sonnet-4-20250514", env=env)
    _install_claude_marker_subprocess(monkeypatch)

    adapter = AnthropicCLI(original_env=env)
    events = list(adapter.run(_ctx("Upgrade Craik Docs")))
    types = [event.type for event in events]

    # Native typed events streamed during the run.
    assert "tool.used" in types
    # Exactly one coalesced assistant_text (snapshots supersede; never concat).
    assert types.count("assistant_text") == 1
    # Framing derived from the core after it returns.
    assert "run.started" in types
    assert "run.completed" in types
    # Every event is sourced to this adapter.
    assert all(event.source == "anthropic-cli" for event in events)


def test_anthropic_cli_run_emits_delegated_observed_receipts(tmp_path: Path, monkeypatch) -> None:
    _repo(tmp_path, monkeypatch)
    env = _env(tmp_path)
    AuthProfileStore.from_env(env).put(_claude_cli_marker_profile())
    dispatch_slash_command("/model set anthropic/claude-sonnet-4-20250514", env=env)
    _install_claude_marker_subprocess(monkeypatch)

    adapter = AnthropicCLI(original_env=env)
    events = list(adapter.run(_ctx("Upgrade Craik Docs")))

    receipts = [e for e in events if e.type == "receipt.created"]
    assert receipts, "expected receipt.created events"
    # Every CLI receipt event carries the delegated-observed posture + vendor.
    for receipt in receipts:
        assert receipt.source == "anthropic-cli"
        assert receipt.data["execution"] == "delegated-observed"
    # The FRAMING receipts (derived from the core's persisted receipt ids) are
    # readable from a fresh store; the stream-mapped ``result`` receipt is an
    # emission-only stub (matching the Phase-4 fixture mapping) and is not
    # persisted. Assert at least one emitted receipt id is readable from the
    # store -- i.e. the framing receipts came from the core's persisted ids.
    reopened = LocalStore.from_env(env)
    try:
        reopened.initialize()
        persisted = [r for r in receipts if reopened.get_receipt(r.data["receipt_id"]) is not None]
        assert persisted, "expected at least one framing receipt persisted via the core"
    finally:
        reopened.close()


def test_anthropic_cli_run_strips_contract_envelopes(tmp_path: Path, monkeypatch) -> None:
    _repo(tmp_path, monkeypatch)
    env = _env(tmp_path)
    AuthProfileStore.from_env(env).put(_claude_cli_marker_profile())
    dispatch_slash_command("/model set anthropic/claude-sonnet-4-20250514", env=env)
    _install_claude_marker_subprocess(monkeypatch)

    adapter = AnthropicCLI(original_env=env)
    events = list(adapter.run(_ctx("Upgrade Craik Docs")))
    blob = "\n".join(str(event.as_dict()) for event in events)

    assert "craik.runner_step_result" not in blob
    assert "craik.handoff" not in blob


def _install_claude_env_capturing_subprocess(monkeypatch) -> dict[str, dict[str, str]]:
    """Claude marker subprocess that records the ``env`` passed to ``Popen``."""
    captured: dict[str, dict[str, str]] = {}
    original_popen = subprocess.Popen

    monkeypatch.setattr(
        "craik.runtime.backend.claude_code.shutil.which",
        lambda command: "/usr/local/bin/claude" if command == "claude" else None,
    )

    class _Process:
        stdout = iter(['{"type":"result","result":"done"}\n'])

        def poll(self):
            return None

        def wait(self, timeout=None):
            return 0

    def _popen(args, **kwargs):
        if Path(args[0]).name != "claude":
            return original_popen(args, **kwargs)
        captured["env"] = dict(kwargs.get("env") or {})
        return _Process()

    monkeypatch.setattr(
        "craik.runtime.sandbox.local_process_backend.subprocess.Popen",
        _popen,
    )
    return captured


def test_anthropic_cli_run_merges_hook_env_into_claude_subprocess(
    tmp_path: Path, monkeypatch
) -> None:
    _repo(tmp_path, monkeypatch)
    env = _env(tmp_path)
    AuthProfileStore.from_env(env).put(_claude_cli_marker_profile())
    dispatch_slash_command("/model set anthropic/claude-sonnet-4-20250514", env=env)
    captured = _install_claude_env_capturing_subprocess(monkeypatch)

    adapter = AnthropicCLI(original_env=env)
    adapter.hook_env = {
        "CRAIK_HOOK_SOCKET": "/run/craik/a.sock",
        "CRAIK_HOOK_VENDOR": "anthropic",
    }
    list(adapter.run(_ctx("Upgrade Craik Docs")))

    # The claude subprocess env (built from os.environ + the threaded env)
    # carries the merged hook overlay for the PreToolUse craik-hook client.
    assert captured["env"]["CRAIK_HOOK_SOCKET"] == "/run/craik/a.sock"
    assert captured["env"]["CRAIK_HOOK_VENDOR"] == "anthropic"


def test_anthropic_cli_run_without_hook_env_passes_no_bridge_env(
    tmp_path: Path, monkeypatch
) -> None:
    _repo(tmp_path, monkeypatch)
    env = _env(tmp_path)
    AuthProfileStore.from_env(env).put(_claude_cli_marker_profile())
    dispatch_slash_command("/model set anthropic/claude-sonnet-4-20250514", env=env)
    captured = _install_claude_env_capturing_subprocess(monkeypatch)

    adapter = AnthropicCLI(original_env=env)
    # hook_env defaults to None pre-cutover: no bridge env reaches the subprocess.
    assert adapter.hook_env is None
    list(adapter.run(_ctx("Upgrade Craik Docs")))
    assert "CRAIK_HOOK_SOCKET" not in captured["env"]


# --- provider API path: compose the provider core ---------------------------


def _provider_env(tmp_path: Path) -> dict[str, str]:
    return {**_env(tmp_path), "CRAIK_FIXTURE": "1"}


def test_openai_api_run_composes_provider_core_typed_sequence(tmp_path: Path, monkeypatch) -> None:
    _repo(tmp_path, monkeypatch)
    env = _provider_env(tmp_path)

    adapter = OpenAIAPI(original_env=env)
    events = list(adapter.run(_ctx("Upgrade Craik Docs")))
    types = [event.type for event in events]

    assert "run.started" in types
    assert "run.output" in types
    assert "run.completed" in types
    # Receipts carry the craik-executed posture and the vendor token.
    receipts = [e for e in events if e.type == "receipt.created"]
    assert receipts, "expected receipt.created events derived from the core receipt ids"
    for receipt in receipts:
        assert receipt.source == "openai-api"
        assert receipt.data["execution"] == "craik"
    # Every event is sourced to this adapter's vendor token.
    assert all(event.source == "openai-api" for event in events)
    # run.started / receipt.created / run.completed carry the audited run id.
    framed = [e for e in events if e.type in {"run.started", "run.completed", "run.output"}]
    assert all(e.run_id for e in framed)


def test_provider_api_run_persists_and_closes_the_store(tmp_path: Path, monkeypatch) -> None:
    _repo(tmp_path, monkeypatch)
    env = _provider_env(tmp_path)

    adapter = OpenAIAPI(original_env=env)
    events = list(adapter.run(_ctx("Upgrade Craik Docs")))

    # The audited run + receipts persist: a fresh store sees them after run()
    # closed the core's store (no leak, single close).
    completed = next(e for e in events if e.type == "run.completed")
    run_id = completed.run_id
    assert run_id is not None
    reopened = LocalStore.from_env(env)
    try:
        reopened.initialize()
        assert reopened.get_task_run(run_id) is not None
        for receipt in (e for e in events if e.type == "receipt.created"):
            assert reopened.get_receipt(receipt.data["receipt_id"]) is not None
    finally:
        reopened.close()


def test_anthropic_api_run_refuses_wrong_vendor_and_closes_store(
    tmp_path: Path, monkeypatch
) -> None:
    # Vendor/provider_family alignment is now GUARDED: the CRAIK_FIXTURE provider
    # resolves to the openai family, so driving the AnthropicAPI adapter (vendor
    # ``anthropic``) over it is a mismatch. The typed path must REFUSE to emit a
    # wrong-vendor audit record -- ``run()`` raises the mismatch ValueError -- and
    # the audited core's store must STILL be closed exactly once (no leak), since
    # the raise happens after the core ran.
    import craik.runtime.backend.adapters.audited_core as audited_core

    _repo(tmp_path, monkeypatch)
    env = _provider_env(tmp_path)

    closes: list[int] = []
    real_run_provider_core = audited_core.run_provider_core

    def _capturing_run_provider_core(**kwargs):
        core = real_run_provider_core(**kwargs)
        original_close = core.store.close

        def _counted_close() -> None:
            closes.append(1)
            original_close()

        monkeypatch.setattr(core.store, "close", _counted_close)
        return core

    monkeypatch.setattr(audited_core, "run_provider_core", _capturing_run_provider_core)

    adapter = AnthropicAPI(original_env=env)
    with pytest.raises(ValueError, match="refusing to emit wrong-vendor receipts"):
        list(adapter.run(_ctx("Upgrade Craik Docs")))

    # The core's store was closed exactly once on the mismatch-raise path.
    assert closes == [1]
