"""Unit tests for the emission-agnostic audited-execution cores (Task 5.4).

These prove each core (a) returns the structured result an emission layer needs
(ids / status / receipt ids / native step results / payload) and (b) actually
PERSISTS its receipts -- asserted by reading them back from the store. The
controlled environments mirror the golden routing tests:

* the provider core reuses the ``CRAIK_FIXTURE=1`` deterministic provider run;
* the claude core reuses the deterministic claude-marker subprocess monkeypatch.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from craik.runtime.auth.profile import AuthProfile, CredentialKind
from craik.runtime.auth.store import AuthProfileStore
from craik.runtime.backend.adapters.audited_core import (
    ClaudeCoreResult,
    ProviderCoreResult,
    run_claude_code_core,
    run_provider_core,
)
from craik.runtime.backend.events import BackendEvent
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
                '{"type":"result","result":"from typed stream"}\n',
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


def test_run_provider_core_returns_structured_result_and_persists_receipts(
    tmp_path: Path, monkeypatch
) -> None:
    _repo(tmp_path, monkeypatch)
    env = {**_env(tmp_path), "CRAIK_FIXTURE": "1"}

    core = run_provider_core(prompt="Upgrade Craik Docs", env=env, source="tui")
    try:
        assert isinstance(core, ProviderCoreResult)
        # Structured identity fields the emission layer derives events from.
        assert core.task_id == "task_upgrade_craik_docs"
        assert core.run_id == core.result.run.id
        assert core.payload["run"]["id"] == core.run_id
        assert core.payload["task"]["id"] == "task_upgrade_craik_docs"
        assert core.provider_id == "provider_openai"
        assert core.provider_family == "openai"
        assert core.display_name == "OpenAI Provider"
        assert core.status in {"completed", "blocked", "failed", "interrupted"}
        # Native step results are carried for the caller to map.
        assert core.result.provider_results
        # Receipt ids are string-only and match the payload's.
        assert core.receipt_ids == [
            receipt_id for receipt_id in core.payload["receipt_ids"] if isinstance(receipt_id, str)
        ]
        # Persistence: every reported receipt id is readable from the SAME store.
        for receipt_id in core.receipt_ids:
            assert core.store.get_receipt(receipt_id) is not None
        # The audited run is persisted too.
        assert core.store.get_task_run(core.run_id) is not None
    finally:
        core.store.close()

    # Persistence survives the store the core used: a fresh store sees the run.
    reopened = LocalStore.from_env(env)
    try:
        reopened.initialize()
        assert reopened.get_task_run(core.run_id) is not None
        for receipt_id in core.receipt_ids:
            assert reopened.get_receipt(receipt_id) is not None
    finally:
        reopened.close()


def test_run_provider_core_emits_no_events_via_a_sink() -> None:
    # The core takes no sink at all -- proven structurally by its signature. This
    # test documents the contract: there is no ``stream``/``emit`` parameter.
    import inspect

    params = inspect.signature(run_provider_core).parameters
    assert "emit" not in params
    assert "stream" not in params


def _claude_cli_marker_profile() -> AuthProfile:
    from datetime import UTC, datetime

    return AuthProfile(
        id="anthropic:default",
        kind=CredentialKind.MARKER,
        provider_family="anthropic",
        metadata={"external_runtime": "claude-cli", "credential_mode": "claude-cli"},
        created_at=datetime(2026, 5, 22, 12, 0, tzinfo=UTC),
        last_status="ok",
    )


def test_run_claude_code_core_returns_structured_result_and_streams_natively(
    tmp_path: Path, monkeypatch
) -> None:
    _repo(tmp_path, monkeypatch)
    env = _env(tmp_path)
    AuthProfileStore.from_env(env).put(_claude_cli_marker_profile())
    dispatch_slash_command("/model set anthropic/claude-sonnet-4-20250514", env=env)
    _install_claude_marker_subprocess(monkeypatch)

    streamed: list[BackendEvent] = []
    core = run_claude_code_core(
        prompt="Upgrade Craik Docs",
        env=env,
        require_operator_approval=False,
        stream=streamed.append,
    )

    assert isinstance(core, ClaudeCoreResult)
    assert core.payload["backend"] == "claude-code"
    # The native per-line claude events were delivered to the injected sink
    # DURING the run (the core itself emits no framing events).
    assert streamed, "claude core must stream native events to the injected sink"
    assert any(event.type == "tool.used" for event in streamed)
    # Receipt ids are string-only and match the payload's, and persist if present.
    assert core.receipt_ids == [
        receipt_id
        for receipt_id in (core.payload.get("receipt_ids") or [])
        if isinstance(receipt_id, str)
    ]
    if core.run_id is not None:
        reopened = LocalStore.from_env(env)
        try:
            reopened.initialize()
            for receipt_id in core.receipt_ids:
                assert reopened.get_receipt(receipt_id) is not None
        finally:
            reopened.close()
