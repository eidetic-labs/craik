"""Central slash-command registry for shell, TUI, and tests."""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass
from typing import Any

from rich.markup import escape

from craik.runtime.auth.login import auth_status_payload
from craik.runtime.i18n import text as localized_text
from craik.runtime.paths import resolve_craik_paths
from craik.runtime.providers.commands import provider_summary_payload
from craik.runtime.providers.model_providers import default_model_provider_registry
from craik.runtime.reviewing.approval_commands import approvals_list_result
from craik.runtime.sandbox.mcp_discovery import render_mcp_discovery
from craik.runtime.shell.argument_validation import argument_validation_error
from craik.runtime.shell.model_settings import ModelSettingsStore
from craik.runtime.shell.readiness import readiness_allows_action, resolve_readiness
from craik.runtime.shell.session_settings import (
    active_session_id,
    save_active_session,
    shell_session_name,
)
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
from craik.runtime.status import status_payload
from craik.runtime.store import DATABASE_NAME, LocalStore
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
        return SlashCommandResult(
            "Transcript clear confirmation requested. "
            "The interactive TUI opens a confirmation modal for this action."
        )
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
            return SlashCommandResult(
                f"Auth logout confirmation requested for `{profile}`. "
                "The interactive TUI opens a confirmation modal for this action."
            )
        if len(tokens) > 1 and tokens[1] == "status":
            return _payload_result(command.name, auth_status_payload(env))
        if len(tokens) > 2 and tokens[1] == "login":
            return SlashCommandResult(
                f"Auth capture requested for `{tokens[2]}`. "
                "The interactive TUI opens the credential capture modal."
            )
        return _payload_result(command.name, _auth_summary_payload(env))
    if command.name == "login":
        return SlashCommandResult(
            "Operator login is handled by Craik's browser/device-code flow. "
            "Start it from an outer shell, then return here and use `/status`."
        )
    if command.name == "provider" and len(tokens) >= 3 and tokens[1] == "login":
        return SlashCommandResult(
            f"Provider auth capture requested for `{tokens[2]}`. "
            "The interactive TUI opens the credential capture modal."
        )
    if command.name == "provider":
        return _payload_result(command.name, _provider_payload())
    if command.name == "model":
        if len(tokens) >= 3 and tokens[1] == "set":
            return _set_active_model(tokens[2], env=env)
        if len(tokens) >= 2 and tokens[1] == "list":
            return _payload_result(command.name, _model_list_payload())
        return _payload_result(command.name, _model_payload(env))
    if command.name == "sessions":
        return _payload_result(command.name, _sessions_payload(env))
    if command.name == "rename":
        if len(tokens) < 2:
            return SlashCommandResult("rename requires a session name")
        return _rename_shell_session(" ".join(tokens[1:]), env=env)
    if command.name == "theme":
        return _theme_result(tokens[1:], env=env)
    if command.name == "resume":
        if len(tokens) < 2:
            return SlashCommandResult("resume requires a session id")
        return _resume_session(tokens[1], env=env)
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
        return _payload_result(command.name, _memory_payload(env))
    if command.name == "mcp":
        text, exit_code = render_mcp_discovery(tokens[1:], env=env)
        return SlashCommandResult(text, exit_code=exit_code)
    if command.name == "gateway":
        return gateway_slash_result(tokens[1:], env=env)
    if command.name == "doctor":
        return _payload_result(command.name, _doctor_payload(report))
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


def _auth_summary_payload(env: dict[str, str] | None) -> dict[str, Any]:
    report = resolve_readiness(env)
    return {
        "operator_authenticated": report.operator_authenticated,
        "operator_required": report.operator_required,
        "profiles": auth_status_payload(env),
    }


def _provider_payload() -> list[dict[str, Any]]:
    return provider_summary_payload()


def _model_payload(env: dict[str, str] | None) -> dict[str, Any]:
    settings = ModelSettingsStore.from_env(env).load()
    return {
        "active_model": settings.active_model,
        "aliases": settings.aliases,
        "fallbacks": settings.fallbacks,
    }


def _model_list_payload() -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for provider in default_model_provider_registry().list():
        default_model = provider.metadata.get("default_model")
        if isinstance(default_model, str):
            payload.append(
                {
                    "provider": provider.provider,
                    "provider_id": provider.id,
                    "model": default_model,
                    "selector": f"{provider.provider}/{default_model}",
                }
            )
    return payload


def _set_active_model(model: str, *, env: dict[str, str] | None) -> SlashCommandResult:
    if "/" not in model or model.startswith("/") or model.endswith("/"):
        return SlashCommandResult("model set requires a provider/model selector")
    store = ModelSettingsStore.from_env(env)
    settings = store.load()
    updated = settings.__class__(
        active_model=model,
        aliases=settings.aliases,
        fallbacks=settings.fallbacks,
    )
    store.save(updated)
    return SlashCommandResult(f"Active model set to `{model}`.")


def _sessions_payload(env: dict[str, str] | None) -> dict[str, Any]:
    sessions = _store_list(env, "list_agent_session_states")
    return {
        "active_session": active_session_id(env),
        "shell_session_name": shell_session_name(env),
        "count": len(sessions),
        "sessions": [_json_ready(item) for item in sessions],
    }


def _resume_session(session_id: str, *, env: dict[str, str] | None) -> SlashCommandResult:
    sessions = _store_list(env, "list_agent_session_states")
    if sessions and not any(getattr(session, "id", None) == session_id for session in sessions):
        return SlashCommandResult(f"unknown session: {session_id}")
    if not sessions and _database_exists(env):
        return SlashCommandResult(f"unknown session: {session_id}")
    save_active_session(session_id, env)
    return SlashCommandResult(f"Active session set to `{session_id}`.")


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
        return SlashCommandResult(json.dumps(result.payload, indent=2, sort_keys=True))
    return SlashCommandResult(f"Theme set to `{result.payload['theme']}`.")


def _memory_payload(env: dict[str, str] | None) -> dict[str, Any]:
    proposals = _store_list(env, "list_proposals")
    diffs = _store_list(env, "list_memory_diffs")
    previews = _store_list(env, "list_memory_impact_previews")
    return {
        "proposals": [_json_ready(item) for item in proposals],
        "diffs": [_json_ready(item) for item in diffs],
        "impact_previews": [_json_ready(item) for item in previews],
    }


def _doctor_payload(report: Any) -> dict[str, Any]:
    return {"readiness": report.as_dict()}


def _status_payload(_report: Any, env: dict[str, str] | None) -> dict[str, Any]:
    return status_payload(env)


def _store_list(env: dict[str, str] | None, method_name: str) -> list[Any]:
    if not _database_exists(env):
        return []
    paths = resolve_craik_paths(env)
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        method = getattr(store, method_name, None)
        if method is None:
            return []
        return list(method())
    except Exception:
        return []
    finally:
        store.close()


def _database_exists(env: dict[str, str] | None) -> bool:
    return (resolve_craik_paths(env).state / DATABASE_NAME).exists()


def _json_ready(item: Any) -> Any:
    if hasattr(item, "model_dump"):
        return item.model_dump(mode="json", by_alias=True)
    if hasattr(item, "as_dict"):
        return item.as_dict()
    if isinstance(item, dict):
        return item
    return str(item)


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
