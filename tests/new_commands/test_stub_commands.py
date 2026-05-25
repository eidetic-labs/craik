"""Coverage for v0.12.8 placeholder slash commands."""

from __future__ import annotations

from pathlib import Path

import pytest

from craik.cli import app
from craik.runtime.contract import CommandResult
from craik.runtime.contract.auto_registry import AutoSlashRegistry
from craik.runtime.shell.commands import compact_stub_result, share_stub_result
from craik.runtime.shell.slash_commands import dispatch_slash_command

SNAPSHOT_ROOT = Path(__file__).resolve().parents[1] / "snapshots" / "slash"


@pytest.mark.parametrize(
    ("command", "snapshot_name", "target"),
    [
        ("/compact", "compact", "v0.14.0 G1"),
        ("/share", "share", "v0.13.0 G8"),
    ],
)
def test_stub_slash_commands_render_snapshots(
    command: str,
    snapshot_name: str,
    target: str,
) -> None:
    result = dispatch_slash_command(command, env={})

    snapshot = SNAPSHOT_ROOT / snapshot_name / "width-80.txt"

    assert result.exit_code == 2
    assert result.payload["implementation_target"] == target
    assert result.text + "\n" == snapshot.read_text(encoding="utf-8")


def test_stub_helpers_return_command_results() -> None:
    compact = compact_stub_result()
    share = share_stub_result()

    assert isinstance(compact, CommandResult)
    assert isinstance(share, CommandResult)
    assert compact.shape == "kv"
    assert share.shape == "kv"
    assert compact.exit_code == 2
    assert share.exit_code == 2


def test_stub_commands_are_registered_as_derived_slash_commands() -> None:
    registry = AutoSlashRegistry.from_typer(app)

    assert registry.spec_by_name("/compact") is not None
    assert registry.spec_by_name("/share") is not None
