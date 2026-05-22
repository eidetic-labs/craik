"""Central slash-command registry for shell, TUI, and tests."""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass
from typing import Literal

from craik.runtime.shell.readiness import readiness_allows_action, resolve_readiness

ReadinessRequirement = Literal["none", "operator", "provider", "model", "ready"]


@dataclass(frozen=True)
class SlashCommand:
    """Declarative slash-command metadata."""

    name: str
    summary: str
    usage: str
    examples: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    readiness: ReadinessRequirement = "none"


@dataclass(frozen=True)
class SlashCommandResult:
    """Rendered slash-command dispatch result."""

    text: str
    exit_shell: bool = False
    exit_code: int = 0


COMMANDS: tuple[SlashCommand, ...] = (
    SlashCommand("help", "Show slash-command help.", "/help [command]", ("/help status",)),
    SlashCommand("setup", "Show progressive setup guidance.", "/setup"),
    SlashCommand("auth", "Manage operator and provider auth.", "/auth [login]", ("/auth login",)),
    SlashCommand(
        "provider",
        "Inspect or configure provider credentials.",
        "/provider [login <provider>]",
        ("/provider login openai", "/provider login local"),
    ),
    SlashCommand("model", "Inspect or select the active model.", "/model [set <provider/model>]"),
    SlashCommand("status", "Show readiness state.", "/status"),
    SlashCommand("doctor", "Run diagnostics from the CLI.", "/doctor", readiness="operator"),
    SlashCommand("sessions", "List persistent sessions.", "/sessions"),
    SlashCommand("resume", "Resume a persistent session.", "/resume <session-id>"),
    SlashCommand("approvals", "Inspect pending approvals.", "/approvals", readiness="operator"),
    SlashCommand("handoffs", "Inspect handoffs.", "/handoffs", readiness="operator"),
    SlashCommand("receipts", "Inspect receipts.", "/receipts", readiness="operator"),
    SlashCommand(
        "skills",
        "Inspect learning-loop skill controls.",
        "/skills",
        readiness="operator",
    ),
    SlashCommand("memory", "Inspect memory proposals and facts.", "/memory", readiness="operator"),
    SlashCommand("gateway", "Inspect gateway state.", "/gateway"),
    SlashCommand("exit", "Exit the shell.", "/exit", aliases=("quit",)),
)


def list_slash_commands() -> list[SlashCommand]:
    """Return registered slash commands in stable order."""
    return list(COMMANDS)


def command_names() -> list[str]:
    """Return command names and aliases without slash prefixes."""
    values: list[str] = []
    for command in COMMANDS:
        values.append(command.name)
        values.extend(command.aliases)
    return values


def dispatch_slash_command(text: str, *, env: dict[str, str] | None = None) -> SlashCommandResult:
    """Parse and dispatch one slash command."""
    tokens = text.strip().split()
    if not tokens or not tokens[0].startswith("/"):
        return SlashCommandResult("slash commands must start with /")
    name = tokens[0][1:]
    command = _command_for_name(name)
    if command is None:
        suggestion = _suggest(name)
        suffix = f" Did you mean /{suggestion}?" if suggestion else ""
        return SlashCommandResult(f"unknown slash command: /{name}.{suffix}")
    if command.name == "exit":
        return SlashCommandResult("Session ended.", exit_shell=True)
    if command.name == "help":
        return SlashCommandResult(_help_text(tokens[1:]))
    report = resolve_readiness(env)
    allowed, reason = readiness_allows_action(report, command.readiness)
    if not allowed:
        return SlashCommandResult(reason or "blocked")
    if command.name in {"status", "setup"}:
        return SlashCommandResult(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    if command.name == "auth":
        return SlashCommandResult(
            "Use `craik auth login [provider]` or `/provider login <provider>`."
        )
    if command.name == "provider" and len(tokens) >= 3 and tokens[1] == "login":
        return SlashCommandResult(f"Use `craik auth login {tokens[2]}` to configure this provider.")
    if command.name == "model":
        return SlashCommandResult(
            "Use `craik model list`, `craik model status`, or `craik model set`."
        )
    if command.name == "sessions":
        return SlashCommandResult(
            "Use `craik session list` or `craik session resume <session-id>`."
        )
    return SlashCommandResult(f"Use `craik {command.name}` for the full command surface.")


def _command_for_name(name: str) -> SlashCommand | None:
    for command in COMMANDS:
        if command.name == name or name in command.aliases:
            return command
    return None


def _help_text(args: list[str]) -> str:
    if args:
        command = _command_for_name(args[0].removeprefix("/"))
        if command is None:
            suggestion = _suggest(args[0].removeprefix("/"))
            return f"unknown slash command: /{args[0]}. Did you mean /{suggestion}?"
        examples = "\n".join(f"  {example}" for example in command.examples)
        example_block = f"\nExamples:\n{examples}" if examples else ""
        return (
            f"/{command.name}\n{command.summary}\nUsage: {command.usage}\n"
            f"Requires: {command.readiness}{example_block}"
        )
    rows = [f"/{command.name:<10} {command.summary}" for command in COMMANDS]
    return "Craik slash commands\n" + "\n".join(rows)


def _suggest(name: str) -> str | None:
    matches = difflib.get_close_matches(name, command_names(), n=1, cutoff=0.5)
    return matches[0] if matches else None
