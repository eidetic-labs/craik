"""Shared registry provider for TUI slash-command dispatch."""

from __future__ import annotations

from functools import lru_cache

from craik.runtime.contract.auto_registry import AutoSlashRegistry
from craik.runtime.shell.contract_runtime.builtin_slash_commands import (
    extend_registry_with_shell_builtins,
)


@lru_cache(maxsize=1)
def get_tui_registry() -> AutoSlashRegistry:
    """Return the live Typer-derived slash registry plus shell-only built-ins."""
    from craik.cli import app as cli_app

    return extend_registry_with_shell_builtins(AutoSlashRegistry.from_typer(cli_app))
