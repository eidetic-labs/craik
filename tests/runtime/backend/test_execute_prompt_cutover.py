"""Task 5.7 cutover tests: ``execute_prompt`` routes through typed ``run()``.

These pin the BEHAVIOR-CHANGING cutover: by default ``execute_prompt`` consumes
the adapter's typed ``run()`` (typed events, no legacy framing) and still returns
a :class:`BackendPromptResult` carrying the audited payload. The
``CRAIK_BACKEND_LEGACY_RUN=1`` flag restores the legacy ``_legacy_run`` path
(asserted in ``test_execute_prompt_routing.py``). The id-exposure cases prove the
six canonical ids route directly while ``auto`` / ``provider`` / ``claude-code``
back-compat still holds.
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

from craik.runtime.auth.profile import AuthProfile, CredentialKind
from craik.runtime.auth.store import AuthProfileStore
from craik.runtime.backend.session import execute_prompt
from craik.runtime.shell.slash_commands import dispatch_slash_command


def _env(tmp_path: Path) -> dict[str, str]:
    return {"CRAIK_HOME": str(tmp_path / ".craik")}


def _repo(tmp_path: Path, monkeypatch) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Repo\n", encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    monkeypatch.chdir(repo)
    return repo


def _claude_cli_marker_profile() -> AuthProfile:
    return AuthProfile(
        id="anthropic:default",
        kind=CredentialKind.MARKER,
        provider_family="anthropic",
        metadata={"external_runtime": "claude-cli", "credential_mode": "claude-cli"},
        created_at=datetime(2026, 5, 22, 12, 0, tzinfo=UTC),
        last_status="ok",
    )


def test_provider_default_routes_through_typed_run(tmp_path: Path, monkeypatch) -> None:
    """Default provider path emits the TYPED sequence and returns the payload.

    The typed run() drops the legacy ``model.selected`` / ``run.working`` framing
    and stamps the vendor source token; ``execute_prompt`` must still return a
    payload with the audited task id derived from the core.
    """
    _repo(tmp_path, monkeypatch)
    env = {**_env(tmp_path), "CRAIK_FIXTURE": "1"}

    result = execute_prompt("Upgrade Craik Docs", env=env, source="tui")

    types = [event.type for event in result.events]
    # prompt.submitted is still emitted by execute_prompt itself (session-level).
    assert types[0] == "prompt.submitted"
    assert types[-1] == "run.completed"
    # Legacy framing is GONE under the typed run().
    assert "model.selected" not in types
    assert "run.working" not in types
    # Typed sequence hallmarks present.
    assert "run.started" in types
    assert "receipt.created" in types
    assert "run.output" in types
    # The post-submit events carry the vendor source token, not "gateway".
    non_session = [event for event in result.events if event.type != "prompt.submitted"]
    assert non_session, "typed run produced events"
    assert all(event.source == "openai-api" for event in non_session)
    # Receipts carry the differentiated governance fields.
    receipts = [event for event in result.events if event.type == "receipt.created"]
    assert receipts
    for receipt in receipts:
        assert receipt.data["execution"] == "craik"
        assert receipt.data["decided_by"] == "operator"
        assert receipt.data["decision"] == "allow"
    # The payload contract still holds.
    assert result.payload["task"]["id"] == "task_upgrade_craik_docs"
    assert result.payload["run"]["task_id"] == "task_upgrade_craik_docs"


def test_provider_backcompat_routes_like_auto(tmp_path: Path, monkeypatch) -> None:
    """``backend="provider"`` routes to the active-family typed adapter (openai)."""
    _repo(tmp_path, monkeypatch)
    env = {**_env(tmp_path), "CRAIK_FIXTURE": "1"}

    result = execute_prompt("Upgrade Craik Docs", env=env, source="tui", backend="provider")

    non_session = [event for event in result.events if event.type != "prompt.submitted"]
    assert non_session
    assert all(event.source == "openai-api" for event in non_session)
    assert result.payload["task"]["id"] == "task_upgrade_craik_docs"


def test_canonical_id_exposed_directly(tmp_path: Path, monkeypatch) -> None:
    """A canonical ``<vendor>-api`` id passed as ``backend`` routes directly.

    Set the active model to anthropic so the openai-api run()'s vendor guard
    would mismatch -- but ``backend="anthropic-api"`` selects the anthropic
    adapter, whose vendor agrees with the resolved family, proving the id is
    honored (not silently remapped to a provider-preference default).
    """
    _repo(tmp_path, monkeypatch)
    env = {**_env(tmp_path), "CRAIK_FIXTURE": "1"}
    dispatch_slash_command("/model set anthropic/claude-sonnet-4-20250514", env=env)

    result = execute_prompt("Upgrade Craik Docs", env=env, source="tui", backend="anthropic-api")

    non_session = [event for event in result.events if event.type != "prompt.submitted"]
    assert non_session
    assert all(event.source == "anthropic-api" for event in non_session)
    assert result.payload["task"]["id"] == "task_upgrade_craik_docs"


def test_auto_marker_routes_to_typed_claude_cli(tmp_path: Path, monkeypatch) -> None:
    """``auto`` + the anthropic marker routes to the typed AnthropicCLI run()."""
    _repo(tmp_path, monkeypatch)
    env = _env(tmp_path)
    AuthProfileStore.from_env(env).put(_claude_cli_marker_profile())
    dispatch_slash_command("/model set anthropic/claude-sonnet-4-20250514", env=env)

    original_popen = __import__("subprocess").Popen
    monkeypatch.setattr(
        "craik.runtime.backend.claude_code.shutil.which",
        lambda command: "/usr/local/bin/claude" if command == "claude" else None,
    )

    class _Process:
        stdout = iter(['{"type":"result","result":"ok"}\n'])

        def poll(self):
            return None

        def wait(self, timeout=None):
            return 0

    def _popen(args, **kwargs):
        if Path(args[0]).name != "claude":
            return original_popen(args, **kwargs)
        return _Process()

    monkeypatch.setattr("craik.runtime.sandbox.local_process_backend.subprocess.Popen", _popen)

    result = execute_prompt("Upgrade Craik Docs", env=env, source="tui", backend="auto")

    assert result.payload["backend"] == "claude-code"
    non_session = [event for event in result.events if event.type != "prompt.submitted"]
    assert all(event.source == "anthropic-cli" for event in non_session)
