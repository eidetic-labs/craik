"""Contract-native callbacks for shell-only slash commands."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Literal

from rich.markup import escape

from craik.contracts.models import ProjectProfile, RunOutput
from craik.runtime.auth.commands import (
    auth_logout_confirmation_result,
    auth_status_result,
    auth_summary_result,
    operator_login_guidance_result,
    provider_login_capture_result,
)
from craik.runtime.backend.claude_code import (
    CLAUDE_CODE_RUN_APPROVED_ENV as CLAUDE_CODE_RUN_APPROVED_ENV,
)
from craik.runtime.backend.claude_code import (
    CLAUDE_PERMISSION_MODE_ENV as CLAUDE_PERMISSION_MODE_ENV,
)
from craik.runtime.backend.claude_code import (
    _clip_block as _clip_block,
)
from craik.runtime.backend.claude_code import (
    _emit_claude_code_progress as _emit_claude_code_progress,
)
from craik.runtime.backend.claude_code import (
    anthropic_uses_claude_cli_marker as anthropic_uses_claude_cli_marker,
)
from craik.runtime.backend.claude_code import (
    claude_code_progress as claude_code_progress,
)
from craik.runtime.backend.claude_code import (
    execute_claude_code_run,
)
from craik.runtime.backend.session import (
    active_provider_and_model,
    execute_prompt,
    live_provider_enabled,
)
from craik.runtime.contract.auto_registry import AutoSlashRegistry, CommandInventoryEntry
from craik.runtime.contract.command_result import CommandResult
from craik.runtime.diagnostics.commands import doctor_result
from craik.runtime.i18n import text as localized_text
from craik.runtime.memory.commands import memory_overview_result
from craik.runtime.model_commands import model_list_result, model_set_result, model_status_result
from craik.runtime.projects.project_registry import NotGitRepositoryError, ProjectRegistry
from craik.runtime.providers.commands import provider_list_result
from craik.runtime.providers.model_providers import ModelProviderNotFoundError
from craik.runtime.reviewing.approval_commands import approvals_list_result
from craik.runtime.sandbox.mcp_discovery import render_mcp_discovery
from craik.runtime.session_commands import session_activate_result, session_shell_status_result
from craik.runtime.setup import setup_command_result
from craik.runtime.shell.commands import note_result
from craik.runtime.shell.commands.confirmation import confirmation_result
from craik.runtime.shell.contract_runtime.builtin_slash_specs import HELP_SPEC_ORDER, help_spec
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
from craik.runtime.store import LocalStore
from craik.runtime.work.case_files import ProjectNotFoundError, TaskNotFoundError
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
            result = model_set_result(args[1], env=env)
            return CommandResult(
                payload=result.payload,
                shape=result.shape,
                text=result.text or f"Active model set to `{args[1]}`.",
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
    allowed = {"default", "acceptEdits", "plan", "auto"}
    if args:
        mode = args[0]
        if mode not in allowed:
            text = "mode must be one of `default`, `acceptEdits`, `plan`, or `auto`."
            return CommandResult(payload=text, shape="markdown", text=text, exit_code=2)
        values[CLAUDE_PERMISSION_MODE_ENV] = mode
    mode = values.get(CLAUDE_PERMISSION_MODE_ENV, "default")
    payload = {
        "claude_permission_mode": mode,
        "choices": ["default", "acceptEdits", "plan", "auto"],
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


def run_command(*args: str, env: dict[str, str] | None = None) -> CommandResult:
    """Create and execute an audited task run from the TUI."""
    if not args:
        text = (
            "Usage: `/run <prompt>` or `/run --backend claude-code <prompt>`\n\n"
            "Also available: `/run list`, `/run inspect <run-or-task-id>`."
        )
        return CommandResult(payload=text, shape="markdown", text=text, command_name="run")
    if args[0] == "list":
        return _run_list_result(env)
    if args[0] in {"inspect", "show"}:
        if len(args) < 2:
            text = "run inspect requires a run id or task id."
            return CommandResult(payload=text, shape="markdown", text=text, exit_code=2)
        return _run_inspect_result(args[1], env)
    if args[0] == "timeline":
        if len(args) < 2:
            text = "run timeline requires a run id or task id."
            return CommandResult(payload=text, shape="markdown", text=text, exit_code=2)
        return _run_timeline_result(args[1], env)
    try:
        backend, prompt_args = _parse_run_backend(args)
    except ValueError as error:
        text = str(error)
        return CommandResult(payload=text, shape="markdown", text=text, exit_code=2)
    prompt = " ".join(prompt_args).strip()
    if not prompt:
        text = "run requires a prompt."
        return CommandResult(payload=text, shape="markdown", text=text, exit_code=2)
    try:
        payload = (
            execute_claude_code_run(prompt, env)
            if backend == "claude-code"
            else _create_and_execute_run(prompt, env)
        )
    except (
        ModelProviderNotFoundError,
        NotGitRepositoryError,
        ProjectNotFoundError,
        TaskNotFoundError,
        RuntimeError,
        ValueError,
    ) as error:
        text = str(error)
        return CommandResult(payload=text, shape="markdown", text=text, exit_code=2)
    label = "Claude Code run" if backend == "claude-code" else "Audited run"
    text = _run_completion_text(label, payload)
    shape: Literal["markdown", "card"] = "markdown" if backend == "claude-code" else "card"
    return CommandResult(payload=payload, shape=shape, text=text, command_name="run")


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


def _create_and_execute_run(prompt: str, env: dict[str, str] | None) -> dict[str, object]:
    return execute_prompt(prompt, env=env, source="tui").payload_with_events()




def _parse_run_backend(args: tuple[str, ...]) -> tuple[str, tuple[str, ...]]:
    backend = "provider"
    remaining: list[str] = []
    index = 0
    while index < len(args):
        argument = args[index]
        if argument == "--backend":
            if index + 1 >= len(args):
                raise ValueError("run --backend requires a value.")
            backend = args[index + 1]
            index += 2
            continue
        if argument.startswith("--backend="):
            backend = argument.split("=", 1)[1]
            index += 1
            continue
        remaining.append(argument)
        index += 1
    if backend not in {"provider", "claude-code"}:
        raise ValueError("run backend must be `provider` or `claude-code`.")
    return backend, tuple(remaining)




def _run_completion_text(label: str, payload: dict[str, object]) -> str:
    run = payload["run"]
    handoff = payload["handoff"]
    receipt_ids = payload["receipt_ids"]
    if not isinstance(run, dict) or not isinstance(handoff, dict) or not isinstance(
        receipt_ids,
        list,
    ):
        raise ValueError("run payload is malformed")
    lines = [
        f"{label} `{run['id']}` completed with status "
        f"`{payload['status']}` for `{run['task_id']}`.",
        "",
        f"Handoff: `{handoff['id']}`",
        f"Receipts: {', '.join(str(item) for item in receipt_ids) or 'none'}",
    ]
    outputs = payload.get("run_outputs")
    run_outputs = outputs if isinstance(outputs, list) else []
    activity_text = _completion_activity_text(run_outputs)
    if activity_text:
        lines.extend(["", activity_text])
    final_text = _completion_final_text(run_outputs)
    if final_text:
        lines.extend(["", "Final output:", final_text])
    next_commands = payload.get("next_commands")
    if isinstance(next_commands, list) and next_commands:
        lines.extend(["", "Next:", *[f"- `{item}`" for item in next_commands if item]])
    text = "\n".join(lines)
    if payload.get("status") == "failed":
        failure = _failure_card_text(run_outputs)
        if failure:
            text = f"{text}\n\n{failure}"
    return text


def _completion_activity_text(outputs: list[object]) -> str:
    activity = _completion_activity(outputs)
    if not activity:
        return ""
    lines = ["Activity:"]
    tools = _string_list(activity.get("tools"))
    files = _string_list(activity.get("files"))
    commands = _string_list(activity.get("commands"))
    denials = activity.get("permission_denials")
    approvals = activity.get("runtime_approvals")
    if tools:
        lines.append(f"- Tools: {', '.join(f'`{item}`' for item in tools)}")
    if files:
        lines.append(f"- Files: {', '.join(f'`{item}`' for item in files)}")
    if commands:
        lines.append("- Commands:")
        lines.extend(f"  - `{item}`" for item in commands)
    if isinstance(approvals, list) and approvals:
        lines.append(f"- Runtime approvals observed: {len(approvals)}")
    if isinstance(denials, list) and denials:
        lines.append("- Permission denials:")
        for denial in denials[:5]:
            if isinstance(denial, dict):
                message = denial.get("message") or denial.get("reason") or denial.get("tool")
                if message:
                    lines.append(f"  - {message}")
    return "\n".join(lines) if len(lines) > 1 else ""


def _completion_activity(outputs: list[object]) -> dict[str, object]:
    for output in outputs:
        if not isinstance(output, dict):
            continue
        observed = output.get("observed_output")
        if not isinstance(observed, dict):
            continue
        activity = observed.get("activity")
        if isinstance(activity, dict):
            return activity
    return {}


def _completion_final_text(outputs: list[object]) -> str:
    for output in outputs:
        if not isinstance(output, dict):
            continue
        observed = output.get("observed_output")
        if not isinstance(observed, dict):
            continue
        text = observed.get("text")
        if isinstance(text, str) and text.strip():
            return _clip_block(text.strip(), limit=1200)
    return ""


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item]


def _failure_card_text(outputs: list[object]) -> str:
    diagnostics: list[str] = []
    last_event: str | None = None
    for output in outputs:
        if not isinstance(output, dict):
            continue
        raw_diagnostics = output.get("diagnostics")
        if isinstance(raw_diagnostics, list):
            diagnostics.extend(str(item) for item in raw_diagnostics if item)
        observed = output.get("observed_output")
        if isinstance(observed, dict):
            events = observed.get("progress_events")
            if isinstance(events, list) and events:
                last_event = str(events[-1])
    if not diagnostics and last_event is None:
        return ""
    lines = ["Failure details:"]
    if diagnostics:
        lines.append(f"- Cause: {diagnostics[0]}")
    if last_event:
        lines.append(f"- Last event: {last_event}")
    lines.append("- Next: inspect the run with `/run inspect <run-or-task-id>`.")
    return "\n".join(lines)


def _project_for_cwd(store: LocalStore) -> ProjectProfile:
    registry = ProjectRegistry(store)
    project = registry.add_project(Path.cwd())
    return project


def _active_provider_id(env: dict[str, str] | None) -> str:
    return _active_provider_and_model(env)[0]


def _active_provider_and_model(env: dict[str, str] | None) -> tuple[str, str | None]:
    return active_provider_and_model(env)


def _live_provider_enabled(env: dict[str, str] | None) -> bool:
    return live_provider_enabled(env)


def _title_from_prompt(prompt: str) -> str:
    normalized = re.sub(r"\s+", " ", prompt).strip()
    if not normalized:
        return "TUI run"
    return normalized[:60].rstrip(" .,;:") or "TUI run"


def _run_list_result(env: dict[str, str] | None) -> CommandResult:
    store = LocalStore.from_env(env)
    try:
        store.initialize()
        payload = [run.model_dump(mode="json", by_alias=True) for run in store.list_task_runs()]
    finally:
        store.close()
    return CommandResult(payload=payload, shape="card_list", command_name="run")


def _run_inspect_result(run_or_task_id: str, env: dict[str, str] | None) -> CommandResult:
    store = LocalStore.from_env(env)
    try:
        store.initialize()
        run = next(
            (
                candidate
                for candidate in store.list_task_runs()
                if candidate.id == run_or_task_id or candidate.task_id == run_or_task_id
            ),
            None,
        )
        if run is None:
            text = f"unknown run or task: {run_or_task_id}"
            return CommandResult(payload=text, shape="markdown", text=text, exit_code=2)
        outputs = [output for output in store.list_run_outputs() if output.run_id == run.id]
        receipts = [
            receipt
            for receipt in store.list_receipts()
            if receipt.id in run.receipt_ids
            or any(receipt.id in output.receipt_ids for output in outputs)
        ]
        payload = {
            "run": run.model_dump(mode="json", by_alias=True),
            "outputs": [output.model_dump(mode="json", by_alias=True) for output in outputs],
            "receipts": [receipt.model_dump(mode="json", by_alias=True) for receipt in receipts],
            "activity": _merged_activity(outputs),
        }
    finally:
        store.close()
    return CommandResult(payload=payload, shape="card", command_name="run")


def _run_timeline_result(run_or_task_id: str, env: dict[str, str] | None) -> CommandResult:
    store = LocalStore.from_env(env)
    try:
        store.initialize()
        run = next(
            (
                candidate
                for candidate in store.list_task_runs()
                if candidate.id == run_or_task_id or candidate.task_id == run_or_task_id
            ),
            None,
        )
        if run is None:
            text = f"unknown run or task: {run_or_task_id}"
            return CommandResult(payload=text, shape="markdown", text=text, exit_code=2)
        outputs = [output for output in store.list_run_outputs() if output.run_id == run.id]
        timeline: list[dict[str, object]] = [
            {
                "kind": "run",
                "message": f"Run {run.id} started.",
                "status": run.status,
                "phase": run.phase,
            }
        ]
        for output in outputs:
            observed = output.observed_output
            for event in observed.get("structured_events", []):
                if isinstance(event, dict):
                    timeline.append(
                        {
                            "kind": str(event.get("kind", "event")),
                            "message": str(event.get("message", "")),
                            "tool": event.get("tool"),
                            "target": event.get("target"),
                            "command": event.get("command"),
                        }
                    )
        timeline.append(
            {
                "kind": "run",
                "message": f"Run {run.id} ended with status {run.status}.",
                "status": run.status,
                "stop_reason": run.stop_reason,
            }
        )
    finally:
        store.close()
    return CommandResult(
        payload={"run_id": run.id, "task_id": run.task_id, "timeline": timeline},
        shape="card",
        command_name="run",
    )


def _merged_activity(outputs: list[RunOutput]) -> dict[str, object]:
    merged: dict[str, list[object]] = {
        "tools": [],
        "files": [],
        "commands": [],
        "permission_denials": [],
        "runtime_approvals": [],
    }
    for output in outputs:
        activity = output.observed_output.get("activity")
        if not isinstance(activity, dict):
            continue
        for key in merged:
            values = activity.get(key)
            if not isinstance(values, list):
                continue
            for value in values:
                if value not in merged[key]:
                    merged[key].append(value)
    return dict(merged)


def _argument_help(command_name: str) -> CommandResult:
    spec = find_slash_command_spec(_active_specs(), command_name)
    text = (
        argument_help_markdown(spec)
        if spec is not None
        else f"{command_name} requires arguments"
    )
    return CommandResult(payload=text, shape="markdown", text=text, command_name="help")


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


def _registry() -> AutoSlashRegistry:
    from craik.runtime.shell.contract_runtime.registry_provider import get_tui_registry

    return get_tui_registry()
