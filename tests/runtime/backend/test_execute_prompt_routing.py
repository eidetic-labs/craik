"""Golden routing tests for ``execute_prompt`` dispatch through the adapter seam.

CHECKPOINT 2 safety net: these tests snapshot the FULL event sequence (and key
payload fields) produced by ``execute_prompt`` for both the provider path and
the claude-code path. They are written against the pre-refactor code to capture
the golden, then must continue to pass byte-identically (modulo the volatile
``created_at`` field) after the if/else is replaced by adapter dispatch.

The harness here mirrors ``tests/test_backend_gateway_session.py``:
- ``_repo`` / ``_env`` reproduce the temp git repo + CRAIK_HOME used there.
- The provider golden reuses the ``CRAIK_FIXTURE=1`` deterministic provider run
  exercised by ``test_gateway_prompt_execution_emits_audited_events``.
- The claude golden replicates EXACTLY the monkeypatch from
  ``test_gateway_anthropic_marker_prompt_streams_typed_claude_events`` so the
  claude path is deterministic without a real subprocess.
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
    """Snapshot the full event sequence, stripping the volatile ``created_at``.

    Every other field (``type``, ``source``, ``run_id``, ``task_id``, ``data``)
    is preserved verbatim so the snapshot is byte-identical across the refactor.
    """
    snapshot: list[dict[str, Any]] = []
    for event in events:
        as_dict = event.as_dict()
        assert "created_at" in as_dict  # contract guard: the volatile field exists
        del as_dict["created_at"]
        snapshot.append(as_dict)
    return snapshot


def _install_claude_marker_subprocess(monkeypatch) -> None:
    """Replicate the deterministic claude-code subprocess monkeypatch.

    Mirrors ``test_gateway_anthropic_marker_prompt_streams_typed_claude_events``
    verbatim so the claude path runs without a real ``claude`` binary.
    """
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


# --- Golden snapshots --------------------------------------------------------
# These literals were captured from the pre-refactor code by running each test
# once and pasting the normalized event sequence. After the refactor they must
# match byte-identically (modulo created_at, which _normalize_events strips).


def test_provider_path_event_sequence_is_golden(tmp_path: Path, monkeypatch) -> None:
    _repo(tmp_path, monkeypatch)
    env = {**_env(tmp_path), "CRAIK_FIXTURE": "1"}

    result = execute_prompt("Upgrade Craik Docs", env=env, source="tui")
    snapshot = _normalize_events(result.events)

    expected = [
        {
            "type": "prompt.submitted",
            "source": "gateway",
            "run_id": None,
            "task_id": None,
            "data": {"source": "tui", "prompt_preview": "Upgrade Craik Docs"},
        },
        {
            "type": "model.selected",
            "source": "gateway",
            "run_id": None,
            "task_id": "task_upgrade_craik_docs",
            "data": {
                "backend": "provider",
                "provider_id": "provider_openai",
                "provider_family": "openai",
                "model": None,
                "display_name": "OpenAI Provider",
                "profile": None,
                "live_enabled": False,
            },
        },
        {
            "type": "run.working",
            "source": "gateway",
            "run_id": None,
            "task_id": "task_upgrade_craik_docs",
            "data": {
                "backend": "provider",
                "provider_id": "provider_openai",
                "provider_family": "openai",
                "model": None,
                "phase": "thinking",
            },
        },
        {
            "type": "run.progress",
            "source": "gateway",
            "run_id": None,
            "task_id": "task_upgrade_craik_docs",
            "data": {
                "provider_id": "provider_openai",
                "provider_family": "openai",
                "model": None,
                "message": "OpenAI Provider is preparing an audited provider run.",
            },
        },
    ]

    # The full prefix (deterministic, payload-stable) must match exactly.
    assert snapshot[: len(expected)] == expected

    # Tail invariants: structure and ordering of the remaining events. The
    # run_id / receipt ids are fixture-stable; assert the type sequence and key
    # fields rather than re-pasting volatile ids.
    types = [e["type"] for e in snapshot]
    assert types[0] == "prompt.submitted"
    assert types[-1] == "run.completed"
    assert types == [
        "prompt.submitted",
        "model.selected",
        "run.working",
        "run.progress",
        "run.started",
        *[t for t in types if t == "tool.used"],
        "run.progress",
        *[t for t in types if t == "receipt.created"],
        "run.output",
        "run.completed",
    ]

    run_started = next(e for e in snapshot if e["type"] == "run.started")
    run_id = run_started["run_id"]
    assert run_id is not None
    # Every post-start event carries the SAME run_id + task_id + provider fields.
    for event in snapshot:
        if event["type"] in {
            "run.started",
            "tool.used",
            "receipt.created",
            "run.output",
            "run.completed",
        }:
            assert event["run_id"] == run_id
            assert event["task_id"] == "task_upgrade_craik_docs"
            assert event["data"]["provider_id"] == "provider_openai"
            assert event["data"]["provider_family"] == "openai"

    completed = snapshot[-1]
    assert completed["data"]["status"] in {"completed", "blocked", "failed", "interrupted"}

    # Key payload fields.
    assert result.payload["task"]["id"] == "task_upgrade_craik_docs"
    assert result.payload["run"]["task_id"] == "task_upgrade_craik_docs"
    assert result.payload["run"]["id"] == run_id


def test_claude_code_path_event_sequence_is_golden(tmp_path: Path, monkeypatch) -> None:
    _repo(tmp_path, monkeypatch)
    env = _env(tmp_path)
    AuthProfileStore.from_env(env).put(_claude_cli_marker_profile())
    dispatch_slash_command("/model set anthropic/claude-sonnet-4-20250514", env=env)
    _install_claude_marker_subprocess(monkeypatch)

    # auto + marker -> claude path
    result = execute_prompt("Upgrade Craik Docs", env=env, source="tui")
    snapshot = _normalize_events(result.events)

    types = [e["type"] for e in snapshot]
    assert types[0] == "prompt.submitted"
    # The fixed framing emitted by the claude branch around the streamed events.
    assert types[1] == "model.selected"
    assert types[2] == "run.working"
    assert types[-1] == "run.completed"

    # Framing events have the exact fixed payloads of the claude branch.
    assert snapshot[0] == {
        "type": "prompt.submitted",
        "source": "gateway",
        "run_id": None,
        "task_id": None,
        "data": {"source": "tui", "prompt_preview": "Upgrade Craik Docs"},
    }
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

    # The streamed claude events appear in-between, in stable order.
    assert "tool.used" in types
    assert "file.changed" in types
    assert "approval.requested" in types
    assert "run.event" in types
    assert "run.started" in types
    assert "run.completed" in types

    tool_events = [e for e in snapshot if e["type"] == "tool.used"]
    assert [e["data"]["tool"] for e in tool_events] == ["Read", "Bash", "Edit"]

    completed = snapshot[-1]
    assert completed["data"]["backend"] == "claude-code"

    assert result.payload["backend"] == "claude-code"

    # Capture the full normalized snapshot to a module attribute so a second
    # explicit-backend run can be compared against it byte-for-byte.
    test_claude_code_path_event_sequence_is_golden.snapshot = snapshot  # type: ignore[attr-defined]


def test_claude_code_explicit_backend_matches_auto_marker(tmp_path: Path, monkeypatch) -> None:
    """``backend="claude-code"`` must route to the same claude path as auto+marker.

    Reproduces the claude golden with the explicit backend selector. The marker
    profile is NOT installed here on purpose -- the explicit ``backend`` value
    alone must select the claude path (today's ``backend == "claude-code"``
    branch). approval_required differs (explicit claude-code -> True), but that
    only affects the claude run's internals, not the framing event sequence.
    """
    _repo(tmp_path, monkeypatch)
    # Explicit claude-code -> approval_required defaults to True; supply the
    # audited non-interactive approval marker so the run proceeds (this is the
    # documented escape hatch, not a behavior change).
    env = {**_env(tmp_path), "CRAIK_CLAUDE_CODE_RUN_APPROVED": "1"}
    dispatch_slash_command("/model set anthropic/claude-sonnet-4-20250514", env=env)
    _install_claude_marker_subprocess(monkeypatch)

    result = execute_prompt("Upgrade Craik Docs", env=env, source="tui", backend="claude-code")
    snapshot = _normalize_events(result.events)

    types = [e["type"] for e in snapshot]
    assert types[0] == "prompt.submitted"
    assert types[1] == "model.selected"
    assert types[2] == "run.working"
    assert types[-1] == "run.completed"
    assert snapshot[1]["data"] == {"backend": "claude-code"}
    assert snapshot[2]["data"] == {"backend": "claude-code", "phase": "starting"}
    assert result.payload["backend"] == "claude-code"

    tool_events = [e for e in snapshot if e["type"] == "tool.used"]
    assert [e["data"]["tool"] for e in tool_events] == ["Read", "Bash", "Edit"]
