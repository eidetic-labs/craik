"""Migration coverage for the v0.12.8 setup command contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console
from typer.testing import CliRunner

from craik.cli import app, setup_command_result
from craik.runtime.contract import CommandResult
from craik.runtime.contract.auto_registry import AutoSlashRegistry
from craik.runtime.contract.format import format_command_result

runner = CliRunner()


def _capture(renderable: Any, *, width: int = 80) -> str:
    console = Console(color_system=None, force_terminal=False, record=True, width=width)
    console.print(renderable)
    return console.export_text()


def test_setup_cli_preserves_json_output(tmp_path: Path) -> None:
    home = tmp_path / "craik-home"

    result = runner.invoke(
        app,
        [
            "setup",
            "--project-id",
            "project_gateway",
            "--enable-gateway",
            "--policy-envelope-id",
            "policy_gateway",
        ],
        env={"CRAIK_HOME": str(home)},
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["secrets_written"] is False
    assert payload["gateway_config"]["project_id"] == "project_gateway"
    assert payload["gateway_config"]["enabled"] is True
    assert payload["gateway_config"]["policy_envelope_id"] == "policy_gateway"


def test_setup_command_returns_command_result_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CRAIK_HOME", str(tmp_path / "craik-home"))

    result = setup_command_result(
        project_id="project_gateway",
        gateway_enabled=True,
        policy_envelope_id="policy_gateway",
    )

    assert isinstance(result, CommandResult)
    assert result.shape == "kv"
    assert result.payload["gateway_config"]["project_id"] == "project_gateway"
    assert [action.command for action in result.next_actions] == ["/gateway", "/doctor"]


def test_setup_command_is_registered_as_derived_slash_command() -> None:
    registry = AutoSlashRegistry.from_typer(app)
    spec = registry.spec_by_name("/setup")

    assert spec is not None
    assert spec.payload_shape == "kv"
    assert "initialize local state" in spec.summary.lower()


def test_setup_tui_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CRAIK_HOME", str(tmp_path / "craik-home"))
    result = setup_command_result(project_id="project_gateway")

    output = _capture(format_command_result(result, kind="tui"), width=80)

    snapshot = (
        Path(__file__).resolve().parents[1]
        / "snapshots"
        / "slash"
        / "setup"
        / "width-80.txt"
    )
    assert output == snapshot.read_text(encoding="utf-8")
