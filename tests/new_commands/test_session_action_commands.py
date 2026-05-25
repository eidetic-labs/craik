"""Coverage for v0.12.8 session-action slash commands."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from craik.cli import app
from craik.contracts.models import AgentSessionEvent
from craik.runtime.contract.auto_registry import AutoSlashRegistry
from craik.runtime.shell.commands import attach_result, fork_result, note_result, redo_result
from craik.runtime.shell.session_settings import active_session_id
from craik.runtime.shell.slash_commands import dispatch_slash_command
from craik.runtime.store import LocalStore

SNAPSHOT_ROOT = Path(__file__).resolve().parents[1] / "snapshots" / "slash"


@pytest.mark.parametrize(
    ("command", "snapshot_name"),
    [
        ("/note Follow up on release checklist", "note"),
        ("/fork", "fork"),
        ("/redo", "redo"),
    ],
)
def test_session_action_slash_command_snapshots(
    tmp_path: Path,
    command: str,
    snapshot_name: str,
) -> None:
    result = dispatch_slash_command(command, env={"CRAIK_HOME": str(tmp_path)})

    snapshot = SNAPSHOT_ROOT / snapshot_name / "width-80.txt"

    assert result.text + "\n" == snapshot.read_text(encoding="utf-8")


def test_attach_slash_command_snapshot(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text("hello\n", encoding="utf-8")

    result = dispatch_slash_command("/attach notes.md", env={"CRAIK_HOME": str(tmp_path)})

    snapshot = SNAPSHOT_ROOT / "attach" / "width-80.txt"

    assert result.exit_code == 0
    assert result.text + "\n" == snapshot.read_text(encoding="utf-8")


def test_note_result_persists_operator_note_event(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path)}

    result = note_result("Remember the release checklist.", env)

    event = _only_event(tmp_path)
    assert result.payload["event_id"] == event.id
    assert event.event_type == "operator.note"
    assert event.session_id == "shell"
    assert event.metadata["text"] == "Remember the release checklist."


def test_fork_result_creates_active_session_state(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path)}

    result = fork_result(env)

    store = LocalStore.from_env(env)
    try:
        store.initialize()
        state = store.get_agent_session_state("shell_fork")
    finally:
        store.close()
    assert state is not None
    assert result.payload["fork_session"] == "shell_fork"
    assert active_session_id(env) == "shell_fork"
    assert state.recovery_metadata["forked_from"] == "shell"


def test_attach_result_persists_file_reference_without_file_contents(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path)}
    path = tmp_path / "context.txt"
    path.write_text("context material\n", encoding="utf-8")

    result = attach_result("context.txt", env)

    event = _only_event(tmp_path)
    assert result.payload["name"] == "context.txt"
    assert event.event_type == "context.attachment"
    assert event.metadata["name"] == "context.txt"
    assert event.metadata["size_bytes"] == len("context material\n")
    assert "context material" not in str(event.metadata)


def test_attach_result_rejects_paths_outside_craik_home(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-context.txt"
    outside.write_text("outside\n", encoding="utf-8")

    with pytest.raises(ValueError, match="within CRAIK_HOME"):
        attach_result(str(outside), {"CRAIK_HOME": str(tmp_path)})


def test_redo_result_records_request_for_replayable_event(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path)}
    _put_event(
        tmp_path,
        AgentSessionEvent(
            id="event_turn",
            session_id="shell",
            event_type="agent.turn",
            operator_subject="operator:test",
            metadata={"prompt": "summarize"},
            created_at=datetime.now(UTC),
        ),
    )

    result = redo_result(env)

    assert result.exit_code == 0
    assert result.payload["redo_supported"] is True
    assert result.payload["replay_event_id"] == "event_turn"
    assert len(_events(tmp_path)) == 2


def test_redo_without_replayable_turn_returns_actionable_empty_state(tmp_path: Path) -> None:
    result = redo_result({"CRAIK_HOME": str(tmp_path)})

    assert result.exit_code == 2
    assert result.payload["redo_supported"] is False
    assert "No replayable agent turn found" in (result.text or "")


def test_session_action_commands_are_registered_as_derived_slash_commands() -> None:
    registry = AutoSlashRegistry.from_typer(app)

    for command in ("/note", "/fork", "/attach", "/redo"):
        assert registry.spec_by_name(command) is not None


def _only_event(home: Path) -> AgentSessionEvent:
    events = _events(home)
    assert len(events) == 1
    return events[0]


def _events(home: Path) -> list[AgentSessionEvent]:
    store = LocalStore.from_env({"CRAIK_HOME": str(home)})
    try:
        store.initialize()
        return store.list_agent_session_events()
    finally:
        store.close()


def _put_event(home: Path, event: AgentSessionEvent) -> None:
    store = LocalStore.from_env({"CRAIK_HOME": str(home)})
    try:
        store.initialize()
        store.put_agent_session_event(event)
    finally:
        store.close()
