"""Migration coverage for provider command contract surfaces."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console
from typer.testing import CliRunner

from craik.cli import app
from craik.runtime.contract import CommandResult
from craik.runtime.contract.auto_registry import AutoSlashRegistry
from craik.runtime.providers.commands import (
    provider_list_result,
    provider_local_presets_result,
    provider_show_result,
)
from craik.runtime.shell.slash_commands import dispatch_slash_command
from craik.runtime.shell.textual_widgets.slash_renderers import render_slash_payload

runner = CliRunner()


def _capture(renderable: Any, *, width: int = 100) -> str:
    console = Console(color_system=None, force_terminal=False, record=True, width=width)
    console.print(renderable)
    return console.export_text()


def _rstrip_lines(value: str) -> str:
    return "\n".join(line.rstrip() for line in value.splitlines())


def _stable_provider_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: value for key, value in row.items() if key != "created_at"} for row in rows]


def test_provider_cli_and_slash_share_payload() -> None:
    cli = runner.invoke(app, ["provider", "list"])
    slash = runner.invoke(app, ["slash", "/provider"])

    assert cli.exit_code == 0, cli.output
    assert slash.exit_code == 0, slash.output
    assert _stable_provider_rows(json.loads(cli.stdout)) == _stable_provider_rows(
        json.loads(slash.stdout)
    )


def test_provider_commands_return_command_result_contracts() -> None:
    listing = provider_list_result()
    detail = provider_show_result("provider_openai")
    local = provider_local_presets_result()

    assert isinstance(listing, CommandResult)
    assert listing.shape == "card_list"
    assert detail.shape == "card"
    assert detail.payload["id"] == "provider_openai"
    assert local.shape == "card_list"


def test_provider_commands_are_registered_as_derived_slash_commands() -> None:
    registry = AutoSlashRegistry.from_typer(app)

    assert registry.spec_by_name("/provider") is not None
    assert registry.spec_by_name("/provider-show") is not None
    assert registry.spec_by_name("/provider-select") is not None
    assert registry.spec_by_name("/provider-local-presets") is not None
    assert registry.spec_by_name("/provider-local-health") is not None
    assert registry.spec_by_name("/provider-certification") is not None


@pytest.mark.parametrize("width", [80, 100])
def test_provider_tui_snapshot(width: int) -> None:
    result = dispatch_slash_command("/provider")
    assert result.payload is not None
    assert result.payload_shape is not None
    output = _capture(render_slash_payload(result.payload, shape=result.payload_shape), width=width)

    snapshot = (
        Path(__file__).resolve().parents[1]
        / "snapshots"
        / "slash"
        / "provider"
        / f"width-{width}.txt"
    )
    assert _rstrip_lines(output) == _rstrip_lines(snapshot.read_text(encoding="utf-8"))
