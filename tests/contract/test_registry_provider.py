"""Tests for the TUI registry provider."""

from __future__ import annotations

from craik.runtime.contract.auto_registry import AutoSlashRegistry
from craik.runtime.shell.contract_runtime.registry_provider import get_tui_registry


def test_returns_auto_slash_registry() -> None:
    registry = get_tui_registry()
    assert isinstance(registry, AutoSlashRegistry)


def test_cached_returns_same_instance() -> None:
    assert get_tui_registry() is get_tui_registry()


def test_includes_contract_and_shell_builtin_commands() -> None:
    registry = get_tui_registry()
    names = {spec.name for spec in registry.slash_specs}
    for command in (
        "/help",
        "/clear",
        "/exit",
        "/who",
        "/cost",
        "/quota",
        "/note",
        "/fork",
        "/attach",
        "/redo",
        "/compact",
        "/share",
    ):
        assert command in names
