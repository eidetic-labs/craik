"""Migration coverage for control and auth-adjacent slash commands."""

from __future__ import annotations

from pathlib import Path

import pytest

from craik.runtime.auth.commands import (
    auth_logout_confirmation_result,
    operator_login_guidance_result,
)
from craik.runtime.shell.slash_commands import dispatch_slash_command

SNAPSHOT_ROOT = Path(__file__).resolve().parents[1] / "snapshots" / "slash"


@pytest.mark.parametrize(
    ("command", "snapshot_name"),
    [
        ("/help", "help"),
        ("/login", "login"),
        ("/logout", "logout"),
        ("/mcp", "mcp"),
        ("/exit", "exit"),
    ],
)
def test_control_slash_command_snapshots(
    tmp_path: Path,
    command: str,
    snapshot_name: str,
) -> None:
    env = {"CRAIK_HOME": str(tmp_path)}
    result = dispatch_slash_command(command, env=env)

    snapshot = SNAPSHOT_ROOT / snapshot_name / "width-80.txt"

    assert result.text + "\n" == snapshot.read_text(encoding="utf-8")


def test_login_slash_preserves_shared_payload() -> None:
    result = dispatch_slash_command("/login", env={})
    expected = operator_login_guidance_result()

    assert result.text == expected.text
    assert result.payload == expected.payload
    assert result.payload_shape == expected.shape


def test_logout_slash_preserves_shared_payload() -> None:
    result = dispatch_slash_command("/logout provider:default", env={})
    expected = auth_logout_confirmation_result("provider:default", env={})

    assert result.text == expected.text
    assert result.payload == expected.payload
    assert result.payload_shape == expected.shape


def test_exit_slash_marks_shell_exit() -> None:
    result = dispatch_slash_command("/exit", env={})

    assert result.exit_shell is True
    assert result.exit_code == 0
