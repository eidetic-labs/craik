"""Migration coverage for model command contract surfaces."""

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
from craik.runtime.model_commands import model_list_result, model_set_result

runner = CliRunner()


def _capture(renderable: Any, *, width: int = 80) -> str:
    console = Console(color_system=None, force_terminal=False, record=True, width=width)
    console.print(renderable)
    return console.export_text()


def _rstrip_lines(value: str) -> str:
    return "\n".join(line.rstrip() for line in value.splitlines())


def test_model_set_cli_and_slash_share_active_model(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "craik-home")}

    cli = runner.invoke(app, ["model", "set", "openai/gpt-5.2"], env=env)
    slash = runner.invoke(app, ["slash", "/model set openai/gpt-4o-mini"], env=env)
    status = runner.invoke(app, ["model", "list"], env=env)

    assert cli.exit_code == 0, cli.output
    assert slash.exit_code == 0, slash.output
    assert json.loads(cli.stdout)["active_model"] == "openai/gpt-5.2"
    assert "Active model set" in slash.stdout
    assert json.loads(status.stdout)["active_model"] == "openai/gpt-4o-mini"


def test_model_commands_return_command_result_contract(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CRAIK_HOME", str(tmp_path / "craik-home"))

    updated = model_set_result("openai/gpt-5.2")
    listing = model_list_result()

    assert isinstance(updated, CommandResult)
    assert updated.shape == "kv"
    assert listing.payload["active_model"] == "openai/gpt-5.2"


def test_model_commands_are_registered_as_derived_slash_commands() -> None:
    registry = AutoSlashRegistry.from_typer(app)

    assert registry.spec_by_name("/model") is not None
    assert registry.spec_by_name("/model-list") is not None
    assert registry.spec_by_name("/model-set") is not None
    assert registry.spec_by_name("/model-probe") is not None
    assert registry.spec_by_name("/model-alias") is not None
    assert registry.spec_by_name("/model-fallback") is not None


def test_model_tui_snapshot(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CRAIK_HOME", str(tmp_path / "craik-home"))
    result = model_set_result("openai/gpt-5.2")

    output = _capture(format_command_result(result, kind="tui"), width=80)

    snapshot = (
        Path(__file__).resolve().parents[1]
        / "snapshots"
        / "slash"
        / "model"
        / "width-80.txt"
    )
    assert _rstrip_lines(output) == _rstrip_lines(snapshot.read_text(encoding="utf-8"))
