"""Contract-native callbacks for shell-only slash commands."""

from __future__ import annotations

import os

from craik.runtime.auth.commands import (
    auth_logout_confirmation_result,
    auth_status_result,
    auth_summary_result,
    operator_login_guidance_result,
    provider_login_capture_result,
)
from craik.runtime.backend.claude_code import (
    CLAUDE_PERMISSION_MODE_ENV as CLAUDE_PERMISSION_MODE_ENV,
)
from craik.runtime.contract.auto_registry import AutoSlashRegistry
from craik.runtime.contract.command_result import CommandResult
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
from craik.runtime.session_commands import session_activate_result, session_shell_status_result
from craik.runtime.setup import setup_command_result
from craik.runtime.shell.commands import note_result
from craik.runtime.shell.commands.confirmation import confirmation_result
from craik.runtime.shell.contract_runtime.builtin_slash_specs import HELP_SPEC_ORDER, help_spec
from craik.runtime.shell.contract_runtime.model_args import parse_model_set_args
from craik.runtime.shell.contract_runtime.result_helpers import (
    _named_result,
    _subcommand_listing,
)
from craik.runtime.shell.slash_command_adapters.system_command_results import (
    gateway_slash_result,
    receipts_slash_result,
)
from craik.runtime.shell.slash_command_schema import SlashCommandSpec
from craik.runtime.shell.slash_command_schema.detail_help import command_detail_help
from craik.runtime.shell.slash_command_schema.help import argument_help_markdown
from craik.runtime.shell.slash_command_schema.lookup import find_slash_command_spec
from craik.runtime.shell.textual_widgets.craik_input import MULTILINE_HELP_TEXT
from craik.runtime.shell_preferences import rename_shell_session_result, theme_result
from craik.runtime.skills.commands import skills_overview_result
from craik.runtime.status.command import status_command_result
from craik.runtime.work.commands.handoff_commands import handoff_list_result

_ACTIVE_SPECS: tuple[SlashCommandSpec, ...] = ()
_HELP_SPEC_NAMES: frozenset[str] = frozenset()


def set_active_specs(specs: tuple[SlashCommandSpec, ...]) -> None:
    global _ACTIVE_SPECS
    _ACTIVE_SPECS = specs


def set_help_spec_names(names: set[str]) -> None:
    global _HELP_SPEC_NAMES
    _HELP_SPEC_NAMES = frozenset(names)


def _active_specs() -> tuple[SlashCommandSpec, ...]:
    return _ACTIVE_SPECS


def _help_specs() -> list[SlashCommandSpec]:
    specs_by_name = {spec.name: spec for spec in _ACTIVE_SPECS}
    return [
        help_spec(specs_by_name[name])
        for name in HELP_SPEC_ORDER
        if name in _HELP_SPEC_NAMES and name in specs_by_name
    ]


def help_command(*args: str, env: dict[str, str] | None = None) -> CommandResult:
    """Return slash-command help text."""
    topic = args[0].removeprefix("/") if args else None
    if topic:
        text = command_detail_help(topic, env=env, specs=_active_specs())
    else:
        rows = [f"- `{spec.name}` - {spec.summary}" for spec in _help_specs()]
        text = (
            f"## {localized_text('slash.help.title', env=env)}\n\n"
            + "\n".join(rows)
            + "\n\n"
            + MULTILINE_HELP_TEXT
        )
    return CommandResult(payload=text, shape="markdown", text=text, command_name="help")


def setup_command(*_args: str, env: dict[str, str] | None = None) -> CommandResult:
    """Return progressive setup guidance."""
    _ = env
    return _named_result(setup_command_result(), "setup")


def status_command(*_args: str, env: dict[str, str] | None = None) -> CommandResult:
    """Return current readiness state."""
    return _named_result(status_command_result(env=env), "status")


def clear_command(*_args: str, env: dict[str, str] | None = None) -> CommandResult:
    """Return clear confirmation guidance for non-Textual shell dispatch."""
    return _named_result(confirmation_result("clear"), "clear")


def copy_command(*_args: str, env: dict[str, str] | None = None) -> CommandResult:
    """Return copy guidance for non-Textual shell dispatch."""
    text = (
        "In the interactive TUI, select text normally in your terminal and use the "
        "terminal copy shortcut. `/copy` remains available for the latest response, "
        "and `/copy transcript` copies everything."
    )
    return CommandResult(payload=text, shape="markdown", text=text, command_name="copy")


def export_command(*args: str, env: dict[str, str] | None = None) -> CommandResult:
    """Return export guidance for non-Textual shell dispatch."""
    target = args[0] if args else "transcript"
    text = (
        "`/export transcript` writes the current TUI transcript under "
        "`$CRAIK_HOME/state/exports/`."
        if target == "transcript"
        else "export currently supports `transcript`."
    )
    return CommandResult(payload=text, shape="markdown", text=text, command_name="export")


def exit_command(*_args: str, env: dict[str, str] | None = None) -> CommandResult:
    """Return an exit-shell result."""
    return CommandResult(
        payload="Session ended.",
        shape="markdown",
        text="Session ended.",
        exit_shell=True,
        command_name="exit",
    )


def auth_command(*args: str, env: dict[str, str] | None = None) -> CommandResult:
    """Return auth summary or logout confirmation for grouped /auth forms."""
    if args and args[0] == "login":
        provider = args[1] if len(args) > 1 else "openai"
        result = provider_login_capture_result(provider)
        return CommandResult(
            payload=result.payload,
            shape=result.shape,
            text=(result.text or "").replace("Provider auth", "Auth", 1),
            command_name="auth",
        )
    if args and args[0] == "logout":
        profile = args[1] if len(args) > 1 else "default"
        return _named_result(auth_logout_confirmation_result(profile, env=env), "auth")
    if args and args[0] == "status":
        result = auth_status_result(env)
        return CommandResult(payload=result.payload, shape=result.shape, command_name="auth")
    return auth_summary_result(env)


def logout_command(*args: str, env: dict[str, str] | None = None) -> CommandResult:
    """Return logout confirmation for a provider profile."""
    profile = args[0] if args else "default"
    return _named_result(auth_logout_confirmation_result(profile, env=env), "logout")


def policy_command(*args: str, env: dict[str, str] | None = None) -> CommandResult:
    """Return policy reset confirmation."""
    if args and args[0] == "reset":
        return _named_result(confirmation_result("policy.reset"), "policy")
    text = "policy requires `reset` for inline confirmation."
    return CommandResult(
        payload=text,
        shape="markdown",
        text=text,
        exit_code=2,
        command_name="policy",
    )


def migrate_command(*args: str, env: dict[str, str] | None = None) -> CommandResult:
    """Return migration apply confirmation."""
    if args and args[0] == "apply":
        return _named_result(confirmation_result("migrate.apply"), "migrate")
    text = "migrate requires `apply` for inline confirmation."
    return CommandResult(
        payload=text,
        shape="markdown",
        text=text,
        exit_code=2,
        command_name="migrate",
    )


def login_command(*_args: str, env: dict[str, str] | None = None) -> CommandResult:
    """Return operator login guidance."""
    return operator_login_guidance_result()


def provider_command(*args: str, env: dict[str, str] | None = None) -> CommandResult:
    """Return provider summary or login capture guidance."""
    if len(args) >= 2 and args[0] == "login":
        result = provider_login_capture_result(args[1])
        return CommandResult(
            payload=result.payload,
            shape=result.shape,
            text=result.text or "",
            command_name="provider",
        )
    result = provider_list_result()
    return CommandResult(payload=result.payload, shape=result.shape, command_name="provider")


def model_command(*args: str, env: dict[str, str] | None = None) -> CommandResult:
    """Return model status, list, or set result."""
    try:
        if args == ("set",):
            return _argument_help("model")
        if len(args) >= 2 and args[0] == "set":
            selector, display_name, backend, options = parse_model_set_args(args[1:])
            result = model_set_result(
                selector,
                env=env,
                display_name=display_name,
                backend=backend,
                options=options,
            )
            return CommandResult(
                payload=result.payload,
                shape=result.shape,
                text=result.text or f"Active model set to `{selector}`.",
                command_name="model",
            )
        if args and args[0] == "list":
            result = model_list_result(env)
        else:
            result = model_status_result(env)
    except ValueError as error:
        text = str(error)
        if "formatted as <provider>/<model>" in text:
            text = (
                "model set requires a provider/model selector\n\n"
                "Usage: `/model [set <provider/model>]`"
            )
        return CommandResult(payload=text, shape="markdown", text=text, exit_code=2)
    return CommandResult(payload=result.payload, shape=result.shape, command_name="model")


def mode_command(*args: str, env: dict[str, str] | None = None) -> CommandResult:
    """Inspect or set Claude Code permission mode."""
    values = env if env is not None else os.environ
    allowed = {"default", "acceptEdits", "plan", "auto", "dontAsk", "bypassPermissions"}
    if args:
        mode = args[0]
        if mode not in allowed:
            text = (
                "mode must be one of `default`, `acceptEdits`, `plan`, `auto`, "
                "`dontAsk`, or `bypassPermissions`."
            )
            return CommandResult(payload=text, shape="markdown", text=text, exit_code=2)
        values[CLAUDE_PERMISSION_MODE_ENV] = mode
    mode = values.get(CLAUDE_PERMISSION_MODE_ENV, "default")
    payload = {
        "claude_permission_mode": mode,
        "choices": ["default", "acceptEdits", "plan", "auto", "dontAsk", "bypassPermissions"],
        "hint": "Shift-Tab cycles this mode inside the TUI.",
    }
    return CommandResult(
        payload=payload,
        shape="kv",
        text=f"Claude permission mode: `{mode}`." if args else None,
        command_name="mode",
    )


def sessions_command(*_args: str, env: dict[str, str] | None = None) -> CommandResult:
    """Return persistent session status."""
    result = session_shell_status_result(env)
    return CommandResult(payload=result.payload, shape=result.shape, command_name="sessions")


def resume_command(*args: str, env: dict[str, str] | None = None) -> CommandResult:
    """Resume a persistent session."""
    if not args:
        spec = find_slash_command_spec(_active_specs(), "resume")
        text = argument_help_markdown(spec) if spec is not None else "resume requires a session id"
        return CommandResult(payload=text, shape="markdown", text=text, command_name="help")
    try:
        result = session_activate_result(args[0], env=env)
    except ValueError as error:
        return CommandResult(payload=str(error), shape="markdown", text=str(error), exit_code=2)
    return CommandResult(
        payload=result.payload,
        shape=result.shape,
        text=result.text or "",
        command_name="resume",
    )


def approvals_command(*args: str, env: dict[str, str] | None = None) -> CommandResult:
    """Return approval list or modal guidance."""
    if len(args) >= 2 and args[0] == "decide":
        text = (
            f"Approval decision requested for `{args[1]}`. "
            "The interactive TUI opens the approval decision modal."
        )
        return CommandResult(payload=text, shape="markdown", text=text, command_name="approvals")
    result = approvals_list_result(env=env)
    return CommandResult(payload=result.payload, shape=result.shape, command_name="approvals")


def handoffs_command(*_args: str, env: dict[str, str] | None = None) -> CommandResult:
    """Return handoff list."""
    result = handoff_list_result(env)
    return CommandResult(payload=result.payload, shape=result.shape, command_name="handoffs")


def skills_command(*_args: str, env: dict[str, str] | None = None) -> CommandResult:
    """Return skill overview."""
    result = skills_overview_result(env)
    return CommandResult(payload=result.payload, shape=result.shape, command_name="skills")


def memory_command(*_args: str, env: dict[str, str] | None = None) -> CommandResult:
    """Return memory overview."""
    result = memory_overview_result(env)
    return CommandResult(payload=result.payload, shape=result.shape, command_name="memory")


def gateway_command(*args: str, env: dict[str, str] | None = None) -> CommandResult:
    """Return gateway slash output."""
    result = gateway_slash_result(list(args), env=env)
    return CommandResult(
        payload=result.payload if result.payload is not None else result.text,
        shape=result.payload_shape or "auto",
        text=result.text,
        exit_code=result.exit_code,
        command_name="gateway",
    )


def doctor_command(*_args: str, env: dict[str, str] | None = None) -> CommandResult:
    """Return doctor output."""
    result = doctor_result(env=env)
    return CommandResult(payload=result.payload, shape=result.shape, command_name="doctor")


def theme_command(*args: str, env: dict[str, str] | None = None) -> CommandResult:
    """Return or set theme."""
    try:
        result = theme_result(args[0] if args else None, env=env)
    except ValueError as error:
        text = str(error)
        if text.startswith("unknown theme:"):
            bad_theme = args[0] if args else ""
            text = f"unknown theme `{bad_theme}`: choose `dark`, `light`, or `monochrome`"
        return CommandResult(payload=text, shape="markdown", text=text, exit_code=2)
    if args:
        return CommandResult(
            payload=result.payload,
            shape=result.shape,
            text=f"Theme set to `{result.payload['theme']}`.",
            command_name="theme",
        )
    return CommandResult(payload=result.payload, shape=result.shape, command_name="theme")


def rename_command(*args: str, env: dict[str, str] | None = None) -> CommandResult:
    """Rename shell session, preserving spaces in the requested name."""
    if not args:
        return _argument_help("rename")
    name = " ".join(args)
    try:
        result = rename_shell_session_result(name, env=env)
    except ValueError as error:
        text = str(error)
        return CommandResult(payload=text, shape="markdown", text=text, exit_code=2)
    return CommandResult(
        payload=result.payload,
        shape=result.shape,
        text=f"Shell session renamed to `{result.payload['session_name']}`.",
        command_name="rename",
    )


def note_command_builtin(*args: str, env: dict[str, str] | None = None) -> CommandResult:
    """Add a session note, preserving spaces."""
    try:
        result = note_result(" ".join(args), env)
    except ValueError as error:
        text = str(error)
        return CommandResult(payload=text, shape="markdown", text=text, exit_code=2)
    return CommandResult(
        payload=result.payload,
        shape=result.shape,
        text=result.text,
        next_actions=result.next_actions,
        command_name="note",
    )


def mcp_command(*args: str, env: dict[str, str] | None = None) -> CommandResult:
    """Return MCP discovery output."""
    text, exit_code = render_mcp_discovery(list(args), env=env)
    return CommandResult(payload=text, shape="markdown", text=text, exit_code=exit_code)


def receipts_command(*args: str, env: dict[str, str] | None = None) -> CommandResult:
    """Return receipt list/detail output for grouped /receipts forms."""
    if not args:
        text = _subcommand_listing("receipts", ("list", "detail", "verify"))
        return CommandResult(payload=None, shape="markdown", text=text, command_name="receipts")
    result = receipts_slash_result(list(args), env=env)
    return CommandResult(
        payload=result.payload if result.payload is not None else result.text,
        shape=result.payload_shape or "auto",
        text=result.text,
        exit_code=result.exit_code,
    )


def agent_command(*args: str, env: dict[str, str] | None = None) -> CommandResult:
    """Return agent subcommand guidance for shell dispatch."""
    if len(args) >= 2 and args[0] == "delete":
        return _named_result(
            confirmation_result("agent.delete", target_id=args[1]),
            "agent",
        )
    if not args:
        text = _subcommand_listing("agent", ("list", "launch", "rename", "delete"))
        return CommandResult(payload=text, shape="markdown", text=text, command_name="agent")
    text = "agent requires `delete <agent-id>` for inline confirmation."
    return CommandResult(
        payload=text,
        shape="markdown",
        text=text,
        exit_code=2,
        command_name="agent",
    )


def session_command(*args: str, env: dict[str, str] | None = None) -> CommandResult:
    """Return session subcommand guidance for shell dispatch."""
    if len(args) >= 2 and args[0] == "delete":
        return _named_result(
            confirmation_result("session.delete", target_id=args[1]),
            "session",
        )
    if not args:
        text = _subcommand_listing("session", ("list", "rename", "delete"))
        return CommandResult(payload=text, shape="markdown", text=text, command_name="session")
    text = "session requires `delete <session-id>` for inline confirmation."
    return CommandResult(
        payload=text,
        shape="markdown",
        text=text,
        exit_code=2,
        command_name="session",
    )


def _argument_help(command_name: str) -> CommandResult:
    spec = find_slash_command_spec(_active_specs(), command_name)
    text = (
        argument_help_markdown(spec) if spec is not None else f"{command_name} requires arguments"
    )
    return CommandResult(payload=text, shape="markdown", text=text, command_name="help")


def _registry() -> AutoSlashRegistry:
    from craik.runtime.shell.contract_runtime.registry_provider import get_tui_registry

    return get_tui_registry()
