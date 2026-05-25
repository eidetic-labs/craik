"""Migration coverage for doctor command contract surfaces."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from rich.console import Console
from typer.testing import CliRunner

from craik.cli import app
from craik.runtime.contract import CommandResult
from craik.runtime.contract.auto_registry import AutoSlashRegistry
from craik.runtime.contract.format import format_command_result
from craik.runtime.diagnostics.commands import doctor_result
from craik.runtime.shell.slash_commands import dispatch_slash_command

runner = CliRunner()


def _env(tmp_path: Path) -> dict[str, str]:
    return {"CRAIK_HOME": str(tmp_path / "craik-home")}


def _capture(renderable: Any, *, width: int = 80) -> str:
    console = Console(color_system=None, force_terminal=False, record=True, width=width)
    console.print(renderable)
    return console.export_text()


def _rstrip_lines(value: str) -> str:
    return "\n".join(line.rstrip() for line in value.splitlines())


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


def test_doctor_tui_snapshot(tmp_path: Path) -> None:
    env = _env(tmp_path)
    result = doctor_result(env=env)
    result = replace(result, payload=_normalized_paths(result.payload, env["CRAIK_HOME"]))

    output = _capture(format_command_result(result, kind="tui"), width=80)

    snapshot = (
        Path(__file__).resolve().parents[1]
        / "snapshots"
        / "slash"
        / "doctor"
        / "width-80.txt"
    )
    assert _rstrip_lines(output) == _rstrip_lines(snapshot.read_text(encoding="utf-8"))


def _normalized_paths(value: Any, path: str) -> Any:
    replacements = {path, str(Path(path).resolve())}
    if isinstance(value, dict):
        return {key: _normalized_paths(item, path) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalized_paths(item, path) for item in value]
    if isinstance(value, str):
        for replacement in sorted(replacements, key=len, reverse=True):
            value = value.replace(replacement, "<craik-home>")
    return value
