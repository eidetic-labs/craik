"""Shared registry provider for TUI slash-command dispatch."""

from __future__ import annotations

from functools import lru_cache

from craik.runtime.contract.auto_registry import AutoSlashRegistry
from craik.runtime.shell.slash_command_schema import SlashCommandSpec
from craik.runtime.shell.slash_command_schema.lookup import find_slash_command_spec


@lru_cache(maxsize=1)
def get_tui_registry() -> AutoSlashRegistry:
    """Return the live Typer-derived slash registry plus shell-only built-ins."""
    from craik.cli import app as cli_app
    from craik.runtime.shell.contract_runtime.builtin_slash_registry import (
        extend_registry_with_shell_builtins,
    )

    return extend_registry_with_shell_builtins(AutoSlashRegistry.from_typer(cli_app))


def get_tui_slash_specs() -> tuple[SlashCommandSpec, ...]:
    """Return registry-derived slash specs for TUI surfaces."""
    return get_tui_registry().slash_specs


def get_tui_slash_spec(name: str) -> SlashCommandSpec | None:
    """Return one registry-derived slash spec by bare or slash-prefixed name."""
    return find_slash_command_spec(get_tui_slash_specs(), name)
