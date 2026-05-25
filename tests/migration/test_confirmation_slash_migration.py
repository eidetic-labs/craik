"""Migration coverage for confirmation-only slash commands."""

from __future__ import annotations

import pytest

from craik.runtime.contract import CommandResult
from craik.runtime.shell.commands import confirmation_result
from craik.runtime.shell.slash_commands import dispatch_slash_command


@pytest.mark.parametrize(
    ("command", "action"),
    [
        ("/clear", "clear"),
        ("/policy reset", "policy.reset"),
        ("/migrate apply", "migrate.apply"),
        ("/agent delete agent_123", "agent.delete"),
        ("/session delete session_123", "session.delete"),
    ],
)
def test_confirmation_slash_commands_use_shared_results(command: str, action: str) -> None:
    result = dispatch_slash_command(command, env={})
    expected = confirmation_result(action)

    assert result.text == expected.text
    assert "`/" not in result.text
    assert "registered but has no inline handler" not in result.text


def test_confirmation_helper_returns_command_result() -> None:
    result = confirmation_result("agent.delete", target_id="agent_123")

    assert isinstance(result, CommandResult)
    assert result.payload["action"] == "agent.delete"
    assert result.payload["target_id"] == "agent_123"
    assert result.payload["requires_confirmation"] is True


def test_confirmation_unknown_action_fails_precisely() -> None:
    with pytest.raises(ValueError, match="unknown confirmation action"):
        confirmation_result("unknown")
