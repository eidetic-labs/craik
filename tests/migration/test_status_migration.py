"""Migration coverage for the v0.12.8 status command contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console
from typer.testing import CliRunner

from craik.cli import app
from craik.runtime.contract import CommandResult
from craik.runtime.contract.auto_registry import AutoSlashRegistry
from craik.runtime.shell.slash_commands import dispatch_slash_command
from craik.runtime.shell.textual_widgets.slash_renderers import render_slash_payload
from craik.runtime.status import status_command_result, status_payload

runner = CliRunner()


def _capture(renderable: Any, *, width: int = 80) -> str:
    console = Console(color_system=None, force_terminal=False, record=True, width=width)
    console.print(renderable)
    return console.export_text()


def _rstrip_lines(value: str) -> str:
    return "\n".join(line.rstrip() for line in value.splitlines())


def test_status_cli_and_slash_share_payload(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "craik-home")}

    cli = runner.invoke(app, ["status"], env=env)
    slash = runner.invoke(app, ["slash", "/status"], env=env)

    assert cli.exit_code == 0, cli.output
    assert slash.exit_code == 0, slash.output
    assert json.loads(cli.stdout) == json.loads(slash.stdout)
    assert json.loads(cli.stdout) == status_payload(env)


def test_status_command_returns_command_result_contract(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "craik-home")}

    result = status_command_result(env)

    assert isinstance(result, CommandResult)
    assert result.shape == "kv"
    assert result.payload["state"] == "unconfigured"
    assert [action.command for action in result.next_actions] == [
        "/login",
        "/auth login",
        "/model set",
    ]


def test_status_command_is_registered_as_derived_slash_command() -> None:
    registry = AutoSlashRegistry.from_typer(app)
    spec = registry.spec_by_name("/status")

    assert spec is not None
    assert spec.payload_shape == "kv"
    assert "readiness" in spec.summary.lower()


def test_status_tui_snapshot(tmp_path: Path) -> None:
    home = tmp_path / "craik-home"
    result = dispatch_slash_command("/status", env={"CRAIK_HOME": str(home)})
    assert result.payload_shape is not None
    assert result.payload is not None
    result.payload["home"] = "<craik-home>"
    output = _capture(render_slash_payload(result.payload, shape=result.payload_shape), width=80)

    snapshot = (
        Path(__file__).resolve().parents[1]
        / "snapshots"
        / "slash"
        / "status"
        / "width-80.txt"
    )
    assert _rstrip_lines(output) == _rstrip_lines(snapshot.read_text(encoding="utf-8"))
