"""Registry metadata helpers for shell-only slash commands."""

from __future__ import annotations

from craik.runtime.contract.auto_registry import CommandInventoryEntry
from craik.runtime.shell.slash_command_schema import (
    ActionKeySet,
    EmptyState,
    ModelArgs,
    NamedArg,
    SlashCommandSpec,
    ThemeArgs,
)

HELP_SPEC_ORDER: tuple[str, ...] = (
    "/help",
    "/setup",
    "/auth",
    "/login",
    "/logout",
    "/provider",
    "/model",
    "/status",
    "/clear",
    "/doctor",
    "/policy",
    "/migrate",
    "/agent",
    "/session",
    "/sessions",
    "/rename",
    "/theme",
    "/resume",
    "/approvals",
    "/handoffs",
    "/receipts",
    "/skills",
    "/memory",
    "/mcp",
    "/gateway",
    "/cost",
    "/quota",
    "/who",
    "/note",
    "/fork",
    "/attach",
    "/redo",
    "/compact",
    "/share",
    "/exit",
)

_HELP_SUMMARY_OVERRIDES: dict[str, str] = {
    "/cost": "Show provider cost and token usage.",
    "/quota": "Show provider quota state.",
    "/who": "Show active operator identity.",
    "/note": "Add an operator note.",
    "/fork": "Fork the active session.",
    "/attach": "Attach a file to session context.",
    "/redo": "Redo the latest agent turn.",
    "/compact": "Compact the current conversation.",
    "/share": "Share the current transcript.",
}


def help_spec(spec: SlashCommandSpec) -> SlashCommandSpec:
    """Return the help-list presentation copy for ``spec``."""
    summary = _HELP_SUMMARY_OVERRIDES.get(spec.name)
    if summary is None:
        return spec
    return spec.model_copy(update={"summary": summary})


def normalize_specs(specs: list[SlashCommandSpec]) -> list[SlashCommandSpec]:
    """Deduplicate registry specs and apply default empty-state metadata."""
    normalized: dict[str, SlashCommandSpec] = {}
    for spec in specs:
        if spec.empty_state is None:
            spec = spec.model_copy(
                update={
                    "empty_state": EmptyState(
                        message=f"No {spec.command_name} results found."
                    )
                }
            )
        normalized[spec.name] = spec
    return list(normalized.values())


def dedupe_entries(entries: list[CommandInventoryEntry]) -> list[CommandInventoryEntry]:
    """Deduplicate registry inventory entries by their slash command key."""
    normalized: dict[str, CommandInventoryEntry] = {}
    for entry in entries:
        key = entry.slash_name or entry.command_name
        normalized[key] = entry
    return list(normalized.values())


def builtin_spec(name: str, *, summary: str, shape: str) -> SlashCommandSpec:
    """Build the shell-only slash spec for a builtin command."""
    kwargs: dict[str, object] = {
        "name": name,
        "summary": summary,
        "usage": _builtin_usage(name),
        "payload_shape": shape,
        "help": summary,
        "empty_state": EmptyState(message=f"No {name.removeprefix('/')} results found."),
    }
    if name in {
        "/auth",
        "/provider",
        "/model",
        "/logout",
        "/policy",
        "/migrate",
        "/agent",
        "/session",
        "/receipts",
        "/rename",
        "/theme",
        "/resume",
    }:
        kwargs["mutating"] = True
    if name in {"/logout", "/policy", "/migrate", "/agent", "/session", "/receipts"}:
        kwargs["requires_confirmation"] = True
        kwargs["confirm_message"] = "This command changes local Craik state."
    if name == "/clear":
        kwargs["mutating"] = True
        kwargs["requires_confirmation"] = True
        kwargs["confirm_message"] = (
            "This discards the current session transcript from the screen. "
            "Persisted receipts and audit records remain stored."
        )
    if name == "/theme":
        kwargs["args_schema"] = ThemeArgs
        kwargs["choices"] = {"theme": ("dark", "light", "monochrome")}
    if name == "/model":
        kwargs["args_schema"] = ModelArgs
        kwargs["example"] = "/model set openai/gpt-4o-mini"
    if name == "/provider":
        kwargs["example"] = "/provider login openai"
        kwargs["examples"] = ("/provider login openai", "/provider login local")
    if name == "/auth":
        kwargs["empty_state"] = EmptyState(message="No auth status rows found.")
    if name == "/approvals":
        kwargs["empty_state"] = EmptyState(message="No pending approvals.")
        kwargs["action_keys"] = ActionKeySet(**{"/": "focus-search"})
    if name == "/handoffs":
        kwargs["empty_state"] = EmptyState(message="No handoffs found.")
    if name == "/sessions":
        kwargs["empty_state"] = EmptyState(
            message="No persistent sessions found.",
            remediation="Start a prompt or run `/resume <session-id>` with a known session.",
        )
    if name in {"/note", "/resume", "/rename"}:
        kwargs["args_schema"] = NamedArg
        required = {
            "/note": "text",
            "/resume": "session-id",
            "/rename": "name",
        }[name]
        kwargs["required_args"] = (required,)
    return SlashCommandSpec(**kwargs)  # type: ignore[arg-type]


def _builtin_usage(name: str) -> str:
    return {
        "/auth": "/auth [login|logout|status]",
        "/setup": "/setup",
        "/status": "/status",
        "/logout": "/logout [profile]",
        "/provider": "/provider [login <provider>]",
        "/model": "/model [set <provider/model>]",
        "/policy": "/policy reset",
        "/migrate": "/migrate apply",
        "/sessions": "/sessions",
        "/resume": "/resume <session-id>",
        "/approvals": "/approvals [decide <approval>]",
        "/theme": "/theme [dark|light|monochrome]",
        "/rename": "/rename <name>",
        "/note": "/note <text>",
        "/receipts": "/receipts [detail <receipt-id>]",
        "/agent": "/agent [list|launch|rename|delete]",
        "/session": "/session [list|rename|delete]",
    }.get(name, name)
