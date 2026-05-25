"""Tests for the contract slash dispatcher."""

from __future__ import annotations

from typing import Any

import typer
from rich.console import Console

from craik.runtime.contract import CommandResult, craik_command
from craik.runtime.contract.auto_registry import AutoSlashRegistry
from craik.runtime.contract.dispatch import dispatch_slash_command, invoke_slash_command


def _capture(renderable: Any) -> str:
    console = Console(color_system=None, force_terminal=False, record=True, width=80)
    console.print(renderable)
    return console.export_text()


def _build_app() -> typer.Typer:
    app = typer.Typer()

    @app.command("status")
    @craik_command(payload_shape="kv")
    def status() -> CommandResult:
        return CommandResult(payload={"state": "ready"}, shape="kv")

    @app.command("echo")
    @craik_command(payload_shape="kv")
    def echo(value: str) -> CommandResult:
        return CommandResult(payload={"value": value}, shape="kv")

    @app.command("raw")
    @craik_command()
    def raw() -> dict[str, str]:
        return {"wrapped": "true"}

    return app


def test_invoke_slash_command_resolves_callback() -> None:
    registry = AutoSlashRegistry.from_typer(_build_app())

    result = invoke_slash_command("/status", registry=registry)

    assert result.payload == {"state": "ready"}
    assert result.shape == "kv"


def test_invoke_slash_command_passes_positional_args() -> None:
    registry = AutoSlashRegistry.from_typer(_build_app())

    result = invoke_slash_command('/echo "hello world"', registry=registry)

    assert result.payload == {"value": "hello world"}


def test_dispatch_slash_command_returns_tui_renderable() -> None:
    registry = AutoSlashRegistry.from_typer(_build_app())

    output = _capture(dispatch_slash_command("/status", registry=registry))

    assert "state" in output
    assert "ready" in output


def test_invoke_slash_command_unknown_command() -> None:
    registry = AutoSlashRegistry.from_typer(_build_app())

    result = invoke_slash_command("/missing", registry=registry)

    assert result.exit_code == 2
    assert result.payload == {"error": "unknown slash command: /missing"}


def test_invoke_slash_command_rejects_non_slash_text() -> None:
    registry = AutoSlashRegistry.from_typer(_build_app())

    result = invoke_slash_command("status", registry=registry)

    assert result.exit_code == 2
    assert result.payload == {"error": "slash commands must start with /"}


def test_invoke_slash_command_empty_registry() -> None:
    registry = AutoSlashRegistry.from_typer(typer.Typer())

    result = invoke_slash_command("/status", registry=registry)

    assert result.exit_code == 2
    assert result.payload == {"error": "unknown slash command: /status"}


def test_invoke_slash_command_wraps_non_command_result() -> None:
    registry = AutoSlashRegistry.from_typer(_build_app())

    result = invoke_slash_command("/raw", registry=registry)

    assert result.payload == {"wrapped": "true"}
