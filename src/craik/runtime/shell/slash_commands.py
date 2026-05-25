"""Central slash-command registry for shell, TUI, and tests."""

from __future__ import annotations

import difflib
from dataclasses import dataclass

from rich.markup import escape

from craik.runtime.auth.commands import (
    auth_logout_confirmation_result,
    auth_status_result,
    auth_summary_result,
    operator_login_guidance_result,
    provider_login_capture_result,
)
from craik.runtime.diagnostics.commands import doctor_result
from craik.runtime.i18n import text as localized_text
from craik.runtime.memory.commands import memory_overview_result
from craik.runtime.model_commands import (
    model_list_result,
    model_set_result,
    model_status_result,
)
from craik.runtime.providers.commands import provider_list_result
from craik.runtime.reviewing.approval_commands import approvals_list_result
from craik.runtime.sandbox.mcp_discovery import render_mcp_discovery
from craik.runtime.session_commands import (
    session_activate_result,
    session_shell_status_result,
)
from craik.runtime.shell.argument_validation import argument_validation_error
from craik.runtime.shell.commands import confirmation_result
from craik.runtime.shell.readiness import readiness_allows_action, resolve_readiness
from craik.runtime.shell.slash_command_adapters.system_command_results import (
    gateway_slash_result,
    receipts_slash_result,
)
from craik.runtime.shell.slash_command_schema import (
    ReadinessRequirement,
    slash_command_spec_by_name,
    slash_command_specs,
)
from craik.runtime.shell.slash_command_schema.detail_help import command_detail_help
from craik.runtime.shell.slash_command_schema.help import argument_help_markdown
from craik.runtime.shell.slash_command_schema.results import (
    SlashCommandResult as SlashCommandResult,
)
from craik.runtime.shell.slash_command_schema.results import (
    payload_result as _payload_result,
)
from craik.runtime.shell.textual_widgets.craik_input import MULTILINE_HELP_TEXT
from craik.runtime.shell_preferences import rename_shell_session_result, theme_result
from craik.runtime.skills.commands import skills_overview_result
from craik.runtime.status import status_command_result
from craik.runtime.work.commands.handoff_commands import handoff_list_result


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


COMMANDS: tuple[SlashCommand, ...] = tuple(
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
)

SUBCOMMAND_LISTINGS: dict[str, tuple[str, ...]] = {
    "agent": ("list", "launch", "rename", "delete"),
    "session": ("list", "rename", "delete"),
    "receipts": ("list", "detail", "verify"),
}


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


def slash_command_is_mutating(text: str) -> bool:
    """Return whether a slash command family may change local runtime state."""
    tokens = text.strip().split()
    if not tokens or not tokens[0].startswith("/"):
        return False
    if tokens[0] == "/auth" and len(tokens) > 1 and tokens[1] == "status":
        return False
    command = _command_for_name(tokens[0][1:])
    return command.mutating if command is not None else False


def dispatch_slash_command(text: str, *, env: dict[str, str] | None = None) -> SlashCommandResult:
    """Parse and dispatch one slash command."""
    tokens = text.strip().split()
    if not tokens or not tokens[0].startswith("/"):
        return SlashCommandResult("slash commands must start with /")
    name = tokens[0][1:]
    if name == "craik":
        return SlashCommandResult(_craik_prefix_recovery(tokens))
    command = _command_for_name(name)
    if command is None:
        suggestion = suggest_close_command(tokens)
        suffix = f" Did you mean `{suggestion}`?" if suggestion else ""
        return SlashCommandResult(f"unknown slash command: /{escape(name)}.{suffix}")
    if command.name == "exit":
        return SlashCommandResult("Session ended.", exit_shell=True)
    if command.name == "help":
        return _payload_result(command.name, _localized_help_text(tokens[1:], env=env))
    listing = _subcommand_listing_response(command.name, tokens)
    if listing is not None:
        return SlashCommandResult(listing)
    if command.name == "clear":
        return _confirmation_slash_result("clear")
    report = resolve_readiness(env)
    allowed, reason = readiness_allows_action(report, command.readiness)
    if not allowed:
        return SlashCommandResult(reason or "blocked")
    help_result = _argument_help_result(command, tokens[1:])
    if help_result is not None:
        return help_result
    validation_error = argument_validation_error(command, tokens[1:])
    if validation_error is not None:
        return SlashCommandResult(validation_error, exit_code=2)
    if command.name in {"status", "setup"}:
        return _payload_result(command.name, _status_payload(report, env))
    if command.name == "auth":
        if len(tokens) > 1 and tokens[1] == "logout":
            profile = tokens[2] if len(tokens) > 2 else report.active_profile
            result = auth_logout_confirmation_result(profile, env=env)
            return SlashCommandResult(result.text or "")
        if len(tokens) > 1 and tokens[1] == "status":
            return _payload_result(command.name, auth_status_result(env).payload)
        if len(tokens) > 2 and tokens[1] == "login":
            result = provider_login_capture_result(tokens[2])
            return SlashCommandResult(
                (result.text or "").replace("Provider auth", "Auth", 1)
            )
        return _payload_result(command.name, auth_summary_result(env).payload)
    if command.name == "login":
        result = operator_login_guidance_result()
        return SlashCommandResult(result.text or "")
    if command.name == "logout":
        profile = tokens[1] if len(tokens) > 1 else report.active_profile
        result = auth_logout_confirmation_result(profile, env=env)
        return SlashCommandResult(result.text or "")
    if command.name == "provider" and len(tokens) >= 3 and tokens[1] == "login":
        result = provider_login_capture_result(tokens[2])
        return SlashCommandResult(result.text or "")
    if command.name == "provider":
        return _payload_result(command.name, provider_list_result().payload)
    if command.name == "model":
        if len(tokens) >= 3 and tokens[1] == "set":
            try:
                result = model_set_result(tokens[2], env=env)
            except ValueError as error:
                return SlashCommandResult(str(error), exit_code=2)
            return SlashCommandResult(result.text or f"Active model set to `{tokens[2]}`.")
        if len(tokens) >= 2 and tokens[1] == "list":
            return _payload_result(command.name, model_list_result(env).payload)
        return _payload_result(command.name, model_status_result(env).payload)
    if command.name == "sessions":
        return _payload_result(command.name, session_shell_status_result(env).payload)
    if command.name == "rename":
        if len(tokens) < 2:
            return SlashCommandResult("rename requires a session name")
        return _rename_shell_session(" ".join(tokens[1:]), env=env)
    if command.name == "theme":
        return _theme_result(tokens[1:], env=env)
    if command.name == "resume":
        if len(tokens) < 2:
            return SlashCommandResult("resume requires a session id")
        try:
            result = session_activate_result(tokens[1], env=env)
        except ValueError as error:
            return SlashCommandResult(str(error), exit_code=2)
        return SlashCommandResult(result.text or "")
    if command.name == "approvals":
        if len(tokens) >= 3 and tokens[1] == "decide":
            return SlashCommandResult(
                f"Approval decision requested for `{tokens[2]}`. "
                "The interactive TUI opens the approval decision modal."
            )
        return _payload_result(command.name, approvals_list_result(env=env).payload)
    if command.name == "handoffs":
        return _payload_result(command.name, handoff_list_result(env).payload)
    if command.name == "receipts":
        return receipts_slash_result(tokens[1:], env=env)
    if command.name == "skills":
        return _payload_result(command.name, skills_overview_result(env).payload)
    if command.name == "memory":
        return _payload_result(command.name, memory_overview_result(env).payload)
    if command.name == "mcp":
        text, exit_code = render_mcp_discovery(tokens[1:], env=env)
        return SlashCommandResult(text, exit_code=exit_code)
    if command.name == "gateway":
        return gateway_slash_result(tokens[1:], env=env)
    if command.name == "doctor":
        return _payload_result(command.name, doctor_result(env=env).payload)
    if command.name == "policy":
        return _confirmation_slash_result("policy.reset")
    if command.name == "migrate":
        return _confirmation_slash_result("migrate.apply")
    if command.name == "agent":
        if len(tokens) >= 3 and tokens[1] == "delete":
            return _confirmation_slash_result("agent.delete", target_id=tokens[2])
        return SlashCommandResult("agent requires `delete <agent-id>` for inline confirmation.")
    if command.name == "session":
        if len(tokens) >= 3 and tokens[1] == "delete":
            return _confirmation_slash_result("session.delete", target_id=tokens[2])
        return SlashCommandResult("session requires `delete <session-id>` for inline confirmation.")
    return SlashCommandResult(f"`/{command.name}` is registered but has no inline handler yet.")


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


def _command_for_name(name: str) -> SlashCommand | None:
    for command in COMMANDS:
        if command.name == name or name in command.aliases:
            return command
    return None


def _argument_help_result(command: SlashCommand, args: list[str]) -> SlashCommandResult | None:
    spec = slash_command_spec_by_name(command.name)
    if spec is None:
        return None
    if spec.required_args and not args:
        return _payload_result("help", argument_help_markdown(spec))
    if command.name == "model" and args == ["set"]:
        return _payload_result("help", argument_help_markdown(spec))
    return None


def _help_text(args: list[str]) -> str:
    return _localized_help_text(args, env=None)


def _localized_help_text(args: list[str], *, env: dict[str, str] | None) -> str:
    if args:
        return command_detail_help(args[0], env=env)
    rows = [f"- `/{command.name}` - {command.summary}" for command in COMMANDS]
    return (
        f"## {localized_text('slash.help.title', env=env)}\n\n"
        + "\n".join(rows)
        + "\n\n"
        + MULTILINE_HELP_TEXT
    )


def _rename_shell_session(name: str, *, env: dict[str, str] | None) -> SlashCommandResult:
    try:
        result = rename_shell_session_result(name, env=env)
    except ValueError as error:
        return SlashCommandResult(str(error), exit_code=2)
    return SlashCommandResult(f"Shell session renamed to `{result.payload['session_name']}`.")


def _theme_result(args: list[str], *, env: dict[str, str] | None) -> SlashCommandResult:
    try:
        result = theme_result(args[0] if args else None, env=env)
    except ValueError as error:
        return SlashCommandResult(str(error), exit_code=2)
    if not args:
        return _payload_result("theme", result.payload)
    return SlashCommandResult(f"Theme set to `{result.payload['theme']}`.")


def _confirmation_slash_result(
    action: str,
    *,
    target_id: str | None = None,
) -> SlashCommandResult:
    result = confirmation_result(action, target_id=target_id)
    command_name = action.split(".", 1)[0]
    return SlashCommandResult(
        result.text or "",
        command_name=command_name,
        payload_shape=result.shape,
        payload=result.payload,
    )


def _status_payload(_report: object, env: dict[str, str] | None) -> dict[str, object]:
    payload = status_command_result(env).payload
    return payload if isinstance(payload, dict) else {"status": payload}


def _craik_prefix_recovery(tokens: list[str]) -> str:
    if len(tokens) == 1:
        return "Drop the `craik` prefix. `/help` lists all slash commands."
    rest = " ".join(tokens[1:])
    return f"Drop the `craik` prefix — try `/{rest}` instead. `/help` lists all slash commands."


def suggest_close_command(tokens: list[str]) -> str | None:
    """Suggest a close slash command for an unknown token sequence."""
    if not tokens:
        return None
    name = tokens[0].removeprefix("/")
    suggestion = _suggest(name)
    if suggestion is None:
        return None
    tail = " ".join(tokens[1:])
    return f"/{suggestion} {tail}".strip()


def _suggest(name: str) -> str | None:
    matches = difflib.get_close_matches(name, command_names(), n=1, cutoff=0.65)
    return matches[0] if matches else None
