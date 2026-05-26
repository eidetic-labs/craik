"""Compatibility surface for slash-command dispatch.

The v0.12.9 TUI cutover routes dispatch through
``craik.runtime.contract.dispatch`` and the Typer-derived registry. This
module remains as a thin import-stability shim for older tests and callers.
"""

from __future__ import annotations

from dataclasses import dataclass

from rich.markup import escape

from craik.runtime.contract.dispatch import invoke_slash_command
from craik.runtime.shell.contract_runtime.registry_provider import get_tui_registry
from craik.runtime.shell.contract_runtime.result_adapter import to_slash_command_result
from craik.runtime.shell.slash_command_schema import ReadinessRequirement, slash_command_specs
from craik.runtime.shell.slash_command_schema.results import SlashCommandResult

__all__ = [
    "SlashCommand",
    "SlashCommandResult",
    "command_names",
    "dispatch_slash_command",
    "list_slash_commands",
    "slash_command_is_mutating",
    "suggest_close_command",
]

SUBCOMMAND_LISTINGS: dict[str, tuple[str, ...]] = {
    "agent": ("list", "launch", "rename", "delete"),
    "session": ("list", "rename", "delete"),
    "receipts": ("list", "detail", "verify"),
}


@dataclass(frozen=True)
class SlashCommand:
    """Declarative slash-command metadata."""

    name: str
    summary: str
    usage: str
    examples: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    readiness: ReadinessRequirement = "none"
    mutating: bool = False


def list_slash_commands() -> list[SlashCommand]:
    """Return stable operator-facing slash commands from schema metadata."""
    return [
            SlashCommand(
                spec.command_name,
                spec.summary,
                spec.usage,
                spec.examples,
                aliases=spec.aliases,
                readiness=spec.readiness,
                mutating=spec.mutating,
            )
            for spec in slash_command_specs()
    ]


def command_names() -> list[str]:
    """Return command names and aliases without slash prefixes."""
    values: list[str] = []
    for command in list_slash_commands():
        values.append(command.name)
        values.extend(command.aliases)
    return values


def slash_command_is_mutating(text: str) -> bool:
    """Return whether a slash command family may change local runtime state."""
    tokens = text.strip().split()
    if not tokens or not tokens[0].startswith("/"):
        return False
    name = tokens[0].removeprefix("/")
    if name == "auth" and len(tokens) > 1 and tokens[1] == "status":
        return False
    for command in list_slash_commands():
        if command.name == name or name in command.aliases:
            return command.mutating
    return False


def dispatch_slash_command(text: str, *, env: dict[str, str] | None = None) -> SlashCommandResult:
    """Dispatch one slash command through the contract layer."""
    result = invoke_slash_command(text, registry=get_tui_registry(), env=env)
    return to_slash_command_result(result)


def suggest_close_command(tokens: list[str]) -> str | None:
    """Suggest a close slash command for an unknown token sequence."""
    import difflib

    if not tokens:
        return None
    name = tokens[0].removeprefix("/")
    matches = difflib.get_close_matches(name, command_names(), n=1, cutoff=0.65)
    if not matches:
        return None
    tail = " ".join(tokens[1:])
    return f"/{matches[0]} {tail}".strip()


def _subcommand_listing_response(command_name: str, tokens: list[str]) -> str | None:
    subcommands = SUBCOMMAND_LISTINGS.get(command_name)
    if subcommands is None or len(tokens) > 1:
        return None
    escaped_command = escape(command_name)
    rendered = ", ".join(f"`/{escaped_command} {subcommand}`" for subcommand in subcommands)
    return (
        f"`/{escaped_command}` requires a subcommand: {rendered}. "
        f"See `/help {escaped_command}` for details."
    )
