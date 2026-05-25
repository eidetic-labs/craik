"""Migration coverage for agent and session slash command-family entry points."""

from __future__ import annotations

from pathlib import Path

import pytest

from craik.runtime.shell.slash_commands import dispatch_slash_command

SNAPSHOT_ROOT = Path(__file__).resolve().parents[1] / "snapshots" / "slash"


@pytest.mark.parametrize(
    ("command", "snapshot_name"),
    [
        ("/agent", "agent"),
        ("/session", "session-family"),
    ],
)
def test_agent_session_family_slash_snapshots(command: str, snapshot_name: str) -> None:
    result = dispatch_slash_command(command, env={})

    snapshot = SNAPSHOT_ROOT / snapshot_name / "width-80.txt"

    assert result.text + "\n" == snapshot.read_text(encoding="utf-8")
    assert "registered but has no inline handler" not in result.text
