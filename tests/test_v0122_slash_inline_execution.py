from __future__ import annotations

import json
from pathlib import Path

import pytest

from craik.runtime.shell.slash_commands import dispatch_slash_command


def _env(tmp_path: Path) -> dict[str, str]:
    return {"CRAIK_HOME": str(tmp_path / ".craik")}


@pytest.mark.parametrize(
    "command",
    [
        "/auth",
        "/auth login openai",
        "/auth logout default",
        "/provider",
        "/provider login openai",
        "/model",
        "/model list",
        "/sessions",
        "/approvals",
        "/approvals decide approval_1",
        "/handoffs",
        "/receipts",
        "/skills",
        "/memory",
        "/gateway",
        "/doctor",
    ],
)
def test_slash_commands_do_not_route_back_to_cli(tmp_path: Path, command: str) -> None:
    result = dispatch_slash_command(command, env=_env(tmp_path))

    assert "Use `craik " not in result.text
    assert "run `craik " not in result.text


def test_model_set_persists_active_model(tmp_path: Path) -> None:
    env = _env(tmp_path)

    result = dispatch_slash_command("/model set openai/gpt-4o-mini", env=env)
    status = dispatch_slash_command("/model", env=env)

    assert result.text == "Active model set to `openai/gpt-4o-mini`."
    assert json.loads(status.text)["active_model"] == "openai/gpt-4o-mini"


def test_resume_persists_active_session_without_argument_loss(tmp_path: Path) -> None:
    env = _env(tmp_path)

    result = dispatch_slash_command("/resume session_alpha", env=env)
    sessions = dispatch_slash_command("/sessions", env=env)

    assert result.text == "Active session set to `session_alpha`."
    assert json.loads(sessions.text)["active_session"] == "session_alpha"


def test_craik_prefix_gets_specific_recovery() -> None:
    result = dispatch_slash_command("/craik auth login openai", env={})

    assert (
        result.text
        == "Drop the `craik` prefix — try `/auth login openai` instead. "
        "`/help` lists all slash commands."
    )


def test_unknown_command_suggests_close_candidate() -> None:
    result = dispatch_slash_command("/auht login", env={})

    assert result.text == "unknown slash command: /auht. Did you mean `/auth login`?"
