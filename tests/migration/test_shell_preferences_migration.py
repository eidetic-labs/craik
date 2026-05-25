"""Migration coverage for shell preference slash commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console
from typer.testing import CliRunner

from craik.cli import app
from craik.runtime.contract import CommandResult
from craik.runtime.contract.auto_registry import AutoSlashRegistry
from craik.runtime.contract.format import format_command_result
from craik.runtime.shell_preferences import rename_shell_session_result, theme_result

runner = CliRunner()


def _capture(renderable: Any, *, width: int = 80) -> str:
    console = Console(color_system=None, force_terminal=False, record=True, width=width)
    console.print(renderable)
    return console.export_text()


def _rstrip_lines(value: str) -> str:
    return "\n".join(line.rstrip() for line in value.splitlines())


def test_theme_cli_and_slash_share_payload(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "craik-home")}

    cli = runner.invoke(app, ["theme"], env=env)
    slash = runner.invoke(app, ["slash", "/theme"], env=env)

    assert cli.exit_code == 0, cli.output
    assert slash.exit_code == 0, slash.output
    assert json.loads(cli.stdout) == json.loads(slash.stdout)


def test_preference_commands_return_command_result_contract(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "craik-home")}

    theme = theme_result("monochrome", env=env)
    renamed = rename_shell_session_result("Desk review", env=env)

    assert isinstance(theme, CommandResult)
    assert theme.payload == {"theme": "monochrome"}
    assert renamed.payload == {"session_name": "Desk review"}


def test_preference_commands_are_registered_as_derived_slash_commands() -> None:
    registry = AutoSlashRegistry.from_typer(app)

    assert registry.spec_by_name("/theme") is not None
    assert registry.spec_by_name("/rename") is not None


def test_theme_tui_snapshot() -> None:
    output = _capture(format_command_result(theme_result(None, env={}), kind="tui"), width=80)

    snapshot = (
        Path(__file__).resolve().parents[1]
        / "snapshots"
        / "slash"
        / "theme"
        / "width-80.txt"
    )
    assert _rstrip_lines(output) == _rstrip_lines(snapshot.read_text(encoding="utf-8"))
