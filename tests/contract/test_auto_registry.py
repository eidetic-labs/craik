"""Tests for the auto-registry: Typer commands to SlashCommandSpec derivation."""

from __future__ import annotations

import typer

from craik.runtime.contract import CommandResult
from craik.runtime.contract.auto_registry import (
    AutoSlashRegistry,
    derive_slash_specs,
)
from craik.runtime.contract.craik_command import craik_command


def _build_test_app() -> typer.Typer:
    app = typer.Typer()

    @app.command("setup")
    @craik_command()
    def setup_cmd() -> CommandResult:
        """Run first-time setup."""
        return CommandResult(payload={"state": "ok"})

    @app.command("ingest-firehose")
    @craik_command(
        tui_eligible=False,
        tui_exempt_reason="streams unbounded stdin; only useful in pipe context",
    )
    def ingest_cmd() -> CommandResult:
        return CommandResult(payload={})

    @app.command("status")
    @craik_command(slash_alias="state", payload_shape="kv")
    def status_cmd() -> CommandResult:
        return CommandResult(payload={"x": 1}, shape="kv")

    return app


def test_derive_slash_specs_includes_tui_eligible() -> None:
    app = _build_test_app()
    specs = derive_slash_specs(app)
    names = {spec.name for spec in specs}

    assert "/setup" in names
    assert "/state" in names
    assert "/ingest-firehose" not in names


def test_derive_slash_specs_captures_help_text_and_shape() -> None:
    app = _build_test_app()
    specs = derive_slash_specs(app)

    setup_spec = next(spec for spec in specs if spec.name == "/setup")
    status_spec = next(spec for spec in specs if spec.name == "/state")
    assert "first-time setup" in setup_spec.summary.lower()
    assert setup_spec.payload_shape == "auto"
    assert status_spec.payload_shape == "kv"


def test_auto_registry_lookup() -> None:
    app = _build_test_app()
    registry = AutoSlashRegistry.from_typer(app)

    assert registry.spec_by_name("/setup") is not None
    assert registry.spec_by_name("/state") is not None
    assert registry.spec_by_name("/missing") is None


def test_auto_registry_includes_exempt_commands_in_inventory() -> None:
    app = _build_test_app()
    registry = AutoSlashRegistry.from_typer(app)
    inventory = registry.all_commands_including_exempt()
    names = {entry.command_name for entry in inventory}

    assert "ingest-firehose" in names
    exempt = next(entry for entry in inventory if entry.command_name == "ingest-firehose")
    assert exempt.is_slash is False
    assert "stdin" in (exempt.exempt_reason or "")


def test_auto_registry_rejects_undecorated_commands() -> None:
    app = typer.Typer()

    @app.command("legacy")
    def legacy() -> None:
        pass

    registry = AutoSlashRegistry.from_typer(app)

    assert "legacy" in registry.undecorated_command_names()


def test_auto_registry_walks_subcommands_with_slash_safe_name() -> None:
    app = typer.Typer()
    auth = typer.Typer()

    @auth.command("login")
    @craik_command()
    def login() -> CommandResult:
        return CommandResult(payload={"provider": "openai"})

    app.add_typer(auth, name="auth")
    registry = AutoSlashRegistry.from_typer(app)

    assert registry.spec_by_name("/auth-login") is not None
