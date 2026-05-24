"""Central slash-command registry for shell, TUI, and tests."""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass
from typing import Any

from craik.runtime.agents.session_naming import SessionNameError, validate_session_name
from craik.runtime.auth.login import auth_status_payload
from craik.runtime.i18n import text as localized_text
from craik.runtime.paths import resolve_craik_paths
from craik.runtime.policy.envelope import is_auto_approve_shape
from craik.runtime.providers.model_providers import default_model_provider_registry
from craik.runtime.reviewing.approvals import approval_queue_payload
from craik.runtime.sandbox.mcp_discovery import render_mcp_discovery
from craik.runtime.shell.argument_validation import argument_validation_error
from craik.runtime.shell.model_settings import ModelSettingsStore
from craik.runtime.shell.readiness import readiness_allows_action, resolve_readiness
from craik.runtime.shell.session_settings import (
    active_session_id,
    save_active_session,
    save_shell_settings,
    shell_session_name,
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
from craik.runtime.shell.textual_widgets.theme_settings import THEMES, current_theme, save_theme
from craik.runtime.store import DATABASE_NAME, LocalStore


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
        return SlashCommandResult(f"unknown slash command: /{name}.{suffix}")
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
        return SlashCommandResult(_approval_text(env))
    if command.name == "handoffs":
        return _payload_result(command.name, _handoffs_payload(env))
    if command.name == "receipts":
        return _payload_result(command.name, _receipts_payload(env))
    if command.name == "skills":
        return _payload_result(command.name, _skills_payload(env))
    if command.name == "memory":
        return _payload_result(command.name, _memory_payload(env))
    if command.name == "mcp":
        text, exit_code = render_mcp_discovery(tokens[1:], env=env)
        return SlashCommandResult(text, exit_code=exit_code)
    if command.name == "gateway":
        return _payload_result(command.name, _gateway_payload(env))
    if command.name == "doctor":
        return _payload_result(command.name, _doctor_payload(report))
    return SlashCommandResult(f"`/{command.name}` is registered but has no inline handler yet.")


def _subcommand_listing_response(command_name: str, tokens: list[str]) -> str | None:
    subcommands = SUBCOMMAND_LISTINGS.get(command_name)
    if subcommands is None or len(tokens) > 1:
        return None
    rendered = ", ".join(f"`/{command_name} {subcommand}`" for subcommand in subcommands)
    return (
        f"`/{command_name}` requires a subcommand: {rendered}. "
        f"See `/help {command_name}` for details."
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


def _approval_text(env: dict[str, str] | None) -> str:
    paths = resolve_craik_paths(env)
    if not (paths.state / DATABASE_NAME).exists():
        return json.dumps({"count": 0, "approvals": []}, indent=2, sort_keys=True)
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        payload = approval_queue_payload(store)
    finally:
        store.close()
    return json.dumps(payload, indent=2, sort_keys=True)


def _auth_summary_payload(env: dict[str, str] | None) -> dict[str, Any]:
    report = resolve_readiness(env)
    return {
        "operator_authenticated": report.operator_authenticated,
        "operator_required": report.operator_required,
        "profiles": auth_status_payload(env),
    }


def _provider_payload() -> list[dict[str, Any]]:
    return [
        provider.model_dump(mode="json", by_alias=True)
        for provider in default_model_provider_registry().list()
    ]


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
        display_name = validate_session_name(name)
    except SessionNameError as error:
        return SlashCommandResult(f"invalid session name: {error}", exit_code=2)
    save_shell_settings(env, session_name=display_name)
    if env is not None:
        env["CRAIK_SESSION_NAME"] = display_name
    return SlashCommandResult(f"Shell session renamed to `{display_name}`.")


def _theme_result(args: list[str], *, env: dict[str, str] | None) -> SlashCommandResult:
    if not args:
        return SlashCommandResult(
            json.dumps(
                {"current": current_theme(env), "themes": list(THEMES)},
                indent=2,
                sort_keys=True,
            )
        )
    try:
        settings = save_theme(args[0], env)
    except ValueError as error:
        return SlashCommandResult(str(error), exit_code=2)
    return SlashCommandResult(f"Theme set to `{settings.theme}`.")


def _handoffs_payload(env: dict[str, str] | None) -> dict[str, Any]:
    handoffs = _store_list(env, "list_handoffs")
    return {"count": len(handoffs), "handoffs": [_json_ready(item) for item in handoffs]}


def _receipts_payload(env: dict[str, str] | None) -> dict[str, Any]:
    receipts = [
        *_store_list(env, "list_receipts"),
        *_store_list(env, "list_plugin_receipts"),
        *_store_list(env, "list_gateway_receipts"),
    ]
    return {"count": len(receipts), "receipts": [_json_ready(item) for item in receipts]}


def _skills_payload(env: dict[str, str] | None) -> dict[str, Any]:
    packages = _store_list(env, "list_skill_packages")
    registries = _store_list(env, "list_skill_registries")
    proposals = _store_list(env, "list_distilled_instruction_proposals")
    return {
        "packages": [_json_ready(item) for item in packages],
        "registries": [_json_ready(item) for item in registries],
        "proposals": [_json_ready(item) for item in proposals],
    }


def _memory_payload(env: dict[str, str] | None) -> dict[str, Any]:
    proposals = _store_list(env, "list_proposals")
    diffs = _store_list(env, "list_memory_diffs")
    previews = _store_list(env, "list_memory_impact_previews")
    return {
        "proposals": [_json_ready(item) for item in proposals],
        "diffs": [_json_ready(item) for item in diffs],
        "impact_previews": [_json_ready(item) for item in previews],
    }


def _gateway_payload(env: dict[str, str] | None) -> dict[str, Any]:
    configs = _store_list(env, "list_gateway_configs")
    states = _store_list(env, "list_gateway_runtime_states")
    schedules = _store_list(env, "list_gateway_schedules")
    return {
        "configs": [_json_ready(item) for item in configs],
        "runtime_states": [_json_ready(item) for item in states],
        "schedules": [_json_ready(item) for item in schedules],
    }


def _doctor_payload(report: Any) -> dict[str, Any]:
    return {"readiness": report.as_dict()}


def _status_payload(report: Any, env: dict[str, str] | None) -> dict[str, Any]:
    payload = dict(report.as_dict())
    auto_approve = auto_approve_status_payload(env)
    if auto_approve is not None:
        payload["auto_approve"] = auto_approve
    return payload


def auto_approve_status_payload(env: dict[str, str] | None) -> dict[str, Any] | None:
    """Return operator-facing auto-approve policy warning data when active."""
    for policy in _store_list(env, "list_policy_envelopes"):
        if not is_auto_approve_shape(policy):
            continue
        return {
            "active": True,
            "policy_id": getattr(policy, "id", None),
            "detail": (
                "An active policy envelope auto-approves capabilities; use a gated policy "
                "when operator review is required."
            ),
        }
    return None


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
