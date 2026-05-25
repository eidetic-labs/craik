"""Migration coverage for doctor command contract surfaces."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from craik.cli import app
from craik.runtime.contract import CommandResult
from craik.runtime.contract.auto_registry import AutoSlashRegistry
from craik.runtime.diagnostics.commands import doctor_result
from craik.runtime.shell.slash_commands import dispatch_slash_command

runner = CliRunner()


def _env(tmp_path: Path) -> dict[str, str]:
    return {"CRAIK_HOME": str(tmp_path / "craik-home")}


def test_doctor_cli_and_slash_share_payload(tmp_path: Path) -> None:
    cli_env = {"CRAIK_HOME": str(tmp_path / "cli-home")}
    slash_env = {"CRAIK_HOME": str(tmp_path / "slash-home")}

    cli = runner.invoke(app, ["doctor", "--json"], env=cli_env)
    slash = dispatch_slash_command("/doctor", env=slash_env)

    assert cli.exit_code == 0, cli.output
    assert json.loads(cli.stdout) == doctor_result(env=cli_env).payload
    assert json.loads(slash.text) == doctor_result(env=slash_env).payload


def test_doctor_helper_returns_command_result(tmp_path: Path) -> None:
    result = doctor_result(env=_env(tmp_path))

    assert isinstance(result, CommandResult)
    assert result.shape == "tree"
    assert "checks" in result.payload


def test_doctor_command_is_registered() -> None:
    registry = AutoSlashRegistry.from_typer(app)

    assert registry.spec_by_name("/doctor") is not None
