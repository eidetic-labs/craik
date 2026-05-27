"""Result helpers for built-in slash commands."""

from __future__ import annotations

from rich.markup import escape

from craik.runtime.contract.auto_registry import AutoSlashRegistry, CommandInventoryEntry
from craik.runtime.contract.command_result import CommandResult


def unknown_command_result(text: str, registry: AutoSlashRegistry) -> CommandResult:
    """Return a friendly unknown-command result."""
    import difflib
    import shlex

    try:
        tokens = shlex.split(text.strip())
    except ValueError:
        tokens = text.strip().split()
    name = tokens[0].removeprefix("/") if tokens else ""
    names = [
        entry.slash_name.removeprefix("/")
        for entry in registry.all_commands_including_exempt()
        if entry.is_slash and entry.slash_name
    ]
    matches = difflib.get_close_matches(name, names, n=1, cutoff=0.65)
    suggestion = matches[0] if matches else None
    if suggestion == "auth" and len(tokens) > 1 and tokens[1] == "login":
        suggestion = "auth login"
    suffix = f". Did you mean `/{suggestion}`?" if suggestion else ""
    message = f"unknown slash command: /{name}{suffix}"
    return CommandResult(
        payload={"error": message},
        shape="kv",
        text=f"unknown slash command: /{escape(name)}{suffix}",
        exit_code=2,
    )

def _named_result(result: CommandResult, command_name: str) -> CommandResult:
    return CommandResult(
        payload=result.payload,
        shape=result.shape,
        text=result.text,
        exit_code=result.exit_code,
        exit_shell=result.exit_shell,
        command_name=command_name,
        next_actions=result.next_actions,
        empty_state_message=result.empty_state_message,
    )


def _summary(entry: CommandInventoryEntry) -> str:
    if entry.callback is None:
        return entry.command_name
    doc = getattr(entry.callback, "__doc__", None)
    if isinstance(doc, str) and doc.strip():
        return doc.strip().split("\n", 1)[0]
    return entry.command_name


def _subcommand_listing(command_name: str, subcommands: tuple[str, ...]) -> str:
    escaped_command = escape(command_name)
    rendered = ", ".join(f"`/{escaped_command} {subcommand}`" for subcommand in subcommands)
    return (
        f"`/{escaped_command}` requires a subcommand: {rendered}. "
        f"See `/help {escaped_command}` for details."
    )
