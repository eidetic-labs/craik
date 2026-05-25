"""Migration coverage for confirmation-only slash commands."""

from __future__ import annotations

from pathlib import Path

import pytest

from craik.runtime.contract import CommandResult
from craik.runtime.shell.commands import confirmation_result
from craik.runtime.shell.slash_commands import dispatch_slash_command

SNAPSHOT_ROOT = Path(__file__).resolve().parents[1] / "snapshots" / "slash"


@pytest.mark.parametrize(
    ("command", "action", "target_id"),
    [
        ("/clear", "clear", None),
        ("/policy reset", "policy.reset", None),
        ("/migrate apply", "migrate.apply", None),
        ("/agent delete agent_123", "agent.delete", "agent_123"),
        ("/session delete session_123", "session.delete", "session_123"),
    ],
)
def test_confirmation_slash_commands_use_shared_results(
    command: str,
    action: str,
    target_id: str | None,
) -> None:
    result = dispatch_slash_command(command, env={})
    expected = confirmation_result(action, target_id=target_id)

    assert result.text == expected.text
    assert result.payload == expected.payload
    assert result.payload_shape == expected.shape
    assert "`/" not in result.text
    assert "registered but has no inline handler" not in result.text


@pytest.mark.parametrize(
    ("command", "snapshot_name"),
    [
        ("/clear", "clear"),
        ("/policy reset", "policy"),
        ("/migrate apply", "migrate"),
        ("/agent delete agent_123", "agent-delete"),
        ("/session delete session_123", "session-delete"),
    ],
)
def test_confirmation_slash_command_snapshots(command: str, snapshot_name: str) -> None:
    result = dispatch_slash_command(command, env={})

    snapshot = SNAPSHOT_ROOT / snapshot_name / "width-80.txt"

    assert result.text + "\n" == snapshot.read_text(encoding="utf-8")


def test_confirmation_helper_returns_command_result() -> None:
    result = confirmation_result("agent.delete", target_id="agent_123")

    assert isinstance(result, CommandResult)
    assert result.payload["action"] == "agent.delete"
    assert result.payload["target_id"] == "agent_123"
    assert result.payload["requires_confirmation"] is True


def test_confirmation_unknown_action_fails_precisely() -> None:
    with pytest.raises(ValueError, match="unknown confirmation action"):
        confirmation_result("unknown")
