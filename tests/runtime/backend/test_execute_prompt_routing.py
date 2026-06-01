"""Golden routing tests for ``execute_prompt`` dispatch through the typed run().

CHECKPOINT-5 artifact (Task 5.7): ``execute_prompt`` now routes through each
adapter's typed ``run()`` by DEFAULT. These snapshots assert the NEW typed event
sequences (the legacy framing is gone; partials coalesce; receipts carry the
differentiated governance fields and the vendor source token). The
``CRAIK_BACKEND_LEGACY_RUN=1`` fallback test proves the OLD sequence is still
reachable through the retained legacy path.

The diff legacy->typed (the maintainer's review artifact) is summarized in the
Task 5.7 report.

The harness mirrors ``tests/test_backend_gateway_session.py``:
- ``_repo`` / ``_env`` reproduce the temp git repo + CRAIK_HOME used there.
- The provider golden reuses the ``CRAIK_FIXTURE=1`` deterministic provider run.
- The claude golden replicates the deterministic claude-marker subprocess
  monkeypatch so the claude path is deterministic without a real subprocess.
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from craik.runtime.auth.profile import AuthProfile, CredentialKind
from craik.runtime.auth.store import AuthProfileStore
from craik.runtime.backend.events import BackendEvent
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


def _normalize_events(events: list[BackendEvent]) -> list[dict[str, Any]]:
    """Snapshot the full event sequence, stripping the volatile ``created_at``."""
    snapshot: list[dict[str, Any]] = []
    for event in events:
        as_dict = event.as_dict()
        assert "created_at" in as_dict  # contract guard: the volatile field exists
        del as_dict["created_at"]
        snapshot.append(as_dict)
    return snapshot


def _install_claude_marker_subprocess(monkeypatch) -> None:
    """Replicate the deterministic claude-code subprocess monkeypatch."""
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
                    '{"type":"assistant","message":{"content":[{"type":"tool_use",'
                    '"name":"Bash","input":{"command":"uv run pytest '
                    'tests/test_backend_gateway_session.py"}}]}}\n'
                ),
                (
                    '{"type":"assistant","message":{"content":[{"type":"tool_use",'
                    '"name":"Edit","input":{"file_path":"README.md","old_string":"# Repo",'
                    '"new_string":"# Repo\\n\\nUpdated"}}]}}\n'
                ),
                (
                    '{"type":"approval_request","tool_name":"Edit",'
                    '"target":"README.md","reason":"write docs"}\n'
                ),
                '{"type":"user","message":{"content":"ignored lifecycle echo"}}\n',
                '{"type":"rate_limit_event","message":"rate limit metadata"}\n',
                '{"type":"system","subtype":"thinking_tokens"}\n',
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


# --- NEW typed golden snapshots (Task 5.7 cutover) ---------------------------


def test_provider_path_typed_event_sequence_is_golden(tmp_path: Path, monkeypatch) -> None:
    """The provider path emits the NEW typed sequence under the default run()."""
    _repo(tmp_path, monkeypatch)
    env = {**_env(tmp_path), "CRAIK_FIXTURE": "1"}

    result = execute_prompt("Upgrade Craik Docs", env=env, source="tui")
    snapshot = _normalize_events(result.events)
    types = [event["type"] for event in snapshot]

    # The session-level prompt.submitted is still emitted by execute_prompt
    # itself; everything after is the typed run() sequence.
    assert snapshot[0] == {
        "type": "prompt.submitted",
        "source": "gateway",
        "run_id": None,
        "task_id": None,
        "data": {"source": "tui", "prompt_preview": "Upgrade Craik Docs"},
    }
    # Legacy framing chatter is GONE.
    assert "model.selected" not in types
    assert "run.working" not in types
    # Typed sequence shape: optional assistant_text, tool.used*, run.started,
    # receipt.created*, run.output, run.completed.
    assert types[-1] == "run.completed"
    assert types == [
        "prompt.submitted",
        *[t for t in types if t == "assistant_text"],
        *[t for t in types if t == "tool.used"],
        "run.started",
        *[t for t in types if t == "receipt.created"],
        "run.output",
        "run.completed",
    ]
    # The default fixture env resolves the openai provider family -> openai-api.
    non_session = [e for e in snapshot if e["type"] != "prompt.submitted"]
    assert all(e["source"] == "openai-api" for e in non_session)
    # Receipts carry the differentiated governance fields (craik execution).
    receipts = [e for e in snapshot if e["type"] == "receipt.created"]
    assert receipts
    for receipt in receipts:
        assert receipt["data"]["execution"] == "craik"
        assert receipt["data"]["decided_by"] == "operator"
        assert receipt["data"]["decision"] == "allow"
        assert receipt["data"]["purpose"] == "execution"
    # Payload contract holds.
    run_started = next(e for e in snapshot if e["type"] == "run.started")
    run_id = run_started["run_id"]
    assert run_id is not None
    assert result.payload["task"]["id"] == "task_upgrade_craik_docs"
    assert result.payload["run"]["id"] == run_id
    completed = snapshot[-1]
    assert completed["data"]["status"] in {"completed", "blocked", "failed", "interrupted"}


def test_claude_code_path_typed_event_sequence_is_golden(tmp_path: Path, monkeypatch) -> None:
    """auto + marker routes to the typed AnthropicCLI run() (no legacy framing)."""
    _repo(tmp_path, monkeypatch)
    env = _env(tmp_path)
    AuthProfileStore.from_env(env).put(_claude_cli_marker_profile())
    dispatch_slash_command("/model set anthropic/claude-sonnet-4-20250514", env=env)
    _install_claude_marker_subprocess(monkeypatch)

    result = execute_prompt("Upgrade Craik Docs", env=env, source="tui")
    snapshot = _normalize_events(result.events)
    types = [event["type"] for event in snapshot]

    assert snapshot[0]["type"] == "prompt.submitted"
    # Legacy claude framing is GONE: no model.selected / run.working / run.event /
    # file.changed / approval.requested chatter.
    for legacy_type in ("model.selected", "run.working", "run.event", "file.changed"):
        assert legacy_type not in types
    # Typed claude sequence: tool.used*, then framing (run.started + receipts +
    # run.completed). The native result line maps to one delegated-observed
    # receipt; framing adds the per-id receipts.
    assert "tool.used" in types
    assert "run.started" in types
    assert types[-1] == "run.completed"
    tool_events = [e for e in snapshot if e["type"] == "tool.used"]
    assert [e["data"]["tool"] for e in tool_events] == ["Read", "Bash", "Edit"]
    assert all(e["source"] == "anthropic-cli" for e in tool_events)
    # auto + marker is UNgated (require_operator_approval defaults to False), so
    # the delegated-observed receipts attribute "bypass", never "operator"
    # (parity item C).
    receipts = [e for e in snapshot if e["type"] == "receipt.created"]
    assert receipts
    for receipt in receipts:
        assert receipt["data"]["execution"] == "delegated-observed"
        assert receipt["data"]["decided_by"] == "bypass"
    assert result.payload["backend"] == "claude-code"


def test_claude_code_explicit_backend_attributes_operator(tmp_path: Path, monkeypatch) -> None:
    """``backend="claude-code"`` is a GATED run -> operator-attributed receipts.

    The explicit selector defaults ``require_operator_approval`` to True (today's
    rule), so an operator decision occurs and the receipts honestly attribute
    ``operator`` -- contrast the ungated auto+marker case above.
    """
    _repo(tmp_path, monkeypatch)
    env = {**_env(tmp_path), "CRAIK_CLAUDE_CODE_RUN_APPROVED": "1"}
    dispatch_slash_command("/model set anthropic/claude-sonnet-4-20250514", env=env)
    _install_claude_marker_subprocess(monkeypatch)

    result = execute_prompt("Upgrade Craik Docs", env=env, source="tui", backend="claude-code")
    snapshot = _normalize_events(result.events)

    assert result.payload["backend"] == "claude-code"
    receipts = [e for e in snapshot if e["type"] == "receipt.created"]
    assert receipts
    for receipt in receipts:
        assert receipt["data"]["decided_by"] == "operator"
    tool_events = [e for e in snapshot if e["type"] == "tool.used"]
    assert [e["data"]["tool"] for e in tool_events] == ["Read", "Bash", "Edit"]


# --- Legacy fallback: the OLD sequence is still reachable --------------------


def test_legacy_run_flag_restores_old_provider_sequence(tmp_path: Path, monkeypatch) -> None:
    """``CRAIK_BACKEND_LEGACY_RUN=1`` routes back to the legacy provider path.

    Proves the retained legacy fallback: the OLD event sequence (with
    ``model.selected`` / ``run.working`` / ``run.progress`` framing and the
    ``gateway`` source) holds when the flag is set.
    """
    _repo(tmp_path, monkeypatch)
    env = {**_env(tmp_path), "CRAIK_FIXTURE": "1", "CRAIK_BACKEND_LEGACY_RUN": "1"}

    result = execute_prompt("Upgrade Craik Docs", env=env, source="tui")
    snapshot = _normalize_events(result.events)
    types = [event["type"] for event in snapshot]

    # The legacy framing chatter is BACK.
    assert types[:4] == ["prompt.submitted", "model.selected", "run.working", "run.progress"]
    assert types[-1] == "run.completed"
    # Legacy events stamp the "gateway" source (not the vendor token).
    assert all(event["source"] == "gateway" for event in snapshot)
    # Legacy provider receipts carry provider_id/provider_family, NOT the typed
    # differentiated governance fields.
    receipts = [e for e in snapshot if e["type"] == "receipt.created"]
    assert receipts
    for receipt in receipts:
        assert receipt["data"]["provider_id"] == "provider_openai"
        assert "execution" not in receipt["data"]
    assert result.payload["task"]["id"] == "task_upgrade_craik_docs"


def test_legacy_run_flag_restores_old_claude_sequence(tmp_path: Path, monkeypatch) -> None:
    """``CRAIK_BACKEND_LEGACY_RUN=1`` restores the legacy claude framing too."""
    _repo(tmp_path, monkeypatch)
    env = {**_env(tmp_path), "CRAIK_BACKEND_LEGACY_RUN": "1"}
    AuthProfileStore.from_env(env).put(_claude_cli_marker_profile())
    dispatch_slash_command("/model set anthropic/claude-sonnet-4-20250514", env=env)
    _install_claude_marker_subprocess(monkeypatch)

    result = execute_prompt("Upgrade Craik Docs", env=env, source="tui")
    snapshot = _normalize_events(result.events)
    types = [event["type"] for event in snapshot]

    assert snapshot[1] == {
        "type": "model.selected",
        "source": "gateway",
        "run_id": None,
        "task_id": None,
        "data": {"backend": "claude-code"},
    }
    assert snapshot[2] == {
        "type": "run.working",
        "source": "gateway",
        "run_id": None,
        "task_id": None,
        "data": {"backend": "claude-code", "phase": "starting"},
    }
    # Legacy claude stream surfaces the catch-all run.event + file.changed +
    # approval.requested events that the typed path drops.
    assert "run.event" in types
    assert "file.changed" in types
    assert "approval.requested" in types
    assert result.payload["backend"] == "claude-code"
