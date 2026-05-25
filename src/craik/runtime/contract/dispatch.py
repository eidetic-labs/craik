"""Unified slash dispatcher for @craik_command callbacks."""

from __future__ import annotations

import io
import shlex
from contextlib import redirect_stdout

from craik.runtime.contract.auto_registry import AutoSlashRegistry, CommandInventoryEntry
from craik.runtime.contract.command_result import CommandResult
from craik.runtime.contract.format import format_command_result
from craik.runtime.contract.output_context import slash_dispatch_context


def invoke_slash_command(text: str, *, registry: AutoSlashRegistry) -> CommandResult:
    """Resolve slash text through a registry and invoke the decorated callback."""
    tokens = shlex.split(text.strip())
    if not tokens or not tokens[0].startswith("/"):
        return _error_result("slash commands must start with /")

    command_name = tokens[0]
    entry = _entry_for_name(registry, command_name)
    if entry is None or entry.callback is None:
        return _error_result(f"unknown slash command: {command_name}")

    with slash_dispatch_context(), redirect_stdout(io.StringIO()):
        result = entry.callback(*tokens[1:])
    if isinstance(result, CommandResult):
        return result
    return CommandResult(payload=result)


def dispatch_slash_command(text: str, *, registry: AutoSlashRegistry) -> object:
    """Invoke slash text and return the TUI renderer output."""
    result = invoke_slash_command(text, registry=registry)
    return format_command_result(result, kind="tui")


def _entry_for_name(
    registry: AutoSlashRegistry,
    slash_name: str,
) -> CommandInventoryEntry | None:
    normalized = slash_name if slash_name.startswith("/") else f"/{slash_name}"
    for entry in registry.all_commands_including_exempt():
        if entry.is_slash and entry.slash_name == normalized:
            return entry
    return None


def _error_result(message: str) -> CommandResult:
    return CommandResult(
        payload={"error": message},
        shape="kv",
        text=message,
        exit_code=2,
    )
