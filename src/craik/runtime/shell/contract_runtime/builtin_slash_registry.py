"""Registry extension for shell-only slash command callbacks."""

from __future__ import annotations

from dataclasses import replace

from craik.runtime.contract.auto_registry import AutoSlashRegistry, CommandInventoryEntry
from craik.runtime.shell.contract_runtime.builtin_slash_specs import (
    HELP_SPEC_ORDER,
    builtin_spec,
    dedupe_entries,
    normalize_specs,
)
from craik.runtime.shell.slash_command_schema import SlashCommandSpec


def extend_registry_with_shell_builtins(registry: AutoSlashRegistry) -> AutoSlashRegistry:
    """Return ``registry`` extended with shell-only slash commands."""
    from craik.runtime.shell.contract_runtime import builtin_slash_commands as commands
    from craik.runtime.shell.contract_runtime.run_helpers import run_command

    builtins = (
        ("/help", commands.help_command, "Show slash-command help.", "markdown"),
        ("/setup", commands.setup_command, "Show progressive setup guidance.", "tree"),
        ("/status", commands.status_command, "Show readiness state.", "tree"),
        ("/clear", commands.clear_command, "Clear the current transcript.", "markdown"),
        (
            "/copy",
            commands.copy_command,
            "Copy transcript text in the interactive TUI.",
            "markdown",
        ),
        (
            "/export",
            commands.export_command,
            "Export transcript or run text from the interactive TUI.",
            "markdown",
        ),
        ("/exit", commands.exit_command, "Exit the shell.", "markdown"),
        ("/quit", commands.exit_command, "Exit the shell.", "markdown"),
        ("/auth", commands.auth_command, "Manage operator and provider auth.", "table"),
        (
            "/login",
            commands.login_command,
            "Start operator-session login guidance.",
            "markdown",
        ),
        (
            "/logout",
            commands.logout_command,
            "Remove a provider credential profile.",
            "markdown",
        ),
        ("/policy", commands.policy_command, "Manage local policy state.", "markdown"),
        ("/migrate", commands.migrate_command, "Apply migration plans.", "markdown"),
        (
            "/provider",
            commands.provider_command,
            "Inspect or configure provider credentials.",
            "table",
        ),
        ("/model", commands.model_command, "Inspect or select the active model.", "kv"),
        ("/mode", commands.mode_command, "Inspect or set Claude Code mode.", "kv"),
        ("/sessions", commands.sessions_command, "List persistent sessions.", "table"),
        ("/resume", commands.resume_command, "Resume a persistent session.", "kv"),
        ("/approvals", commands.approvals_command, "Inspect pending approvals.", "table"),
        ("/handoffs", commands.handoffs_command, "Inspect handoffs.", "table"),
        ("/skills", commands.skills_command, "Inspect learning-loop skill controls.", "tree"),
        ("/memory", commands.memory_command, "Inspect memory proposals and facts.", "tree"),
        ("/gateway", commands.gateway_command, "Inspect gateway state.", "tree"),
        ("/doctor", commands.doctor_command, "Run diagnostics inline.", "tree"),
        (
            "/run",
            run_command,
            "Create and execute an audited task run.",
            "card",
        ),
        ("/theme", commands.theme_command, "Inspect or switch the TUI theme.", "kv"),
        ("/rename", commands.rename_command, "Rename the current shell session.", "kv"),
        (
            "/note",
            commands.note_command_builtin,
            "Add an operator note to the active session.",
            "kv",
        ),
        ("/mcp", commands.mcp_command, "Inspect configured MCP clients.", "table"),
        ("/receipts", commands.receipts_command, "Inspect receipts.", "table"),
        ("/agent", commands.agent_command, "Manage agent records.", "markdown"),
        ("/session", commands.session_command, "Manage persistent sessions.", "markdown"),
    )
    builtin_names = {name for name, *_ in builtins}
    entries: list[CommandInventoryEntry] = [
        entry for entry in registry.inventory if entry.slash_name not in builtin_names
    ]
    specs: list[SlashCommandSpec] = [
        spec for spec in registry.slash_specs if spec.name not in builtin_names
    ]
    for name, callback, summary, shape in builtins:
        bare = name.removeprefix("/")
        specs.append(builtin_spec(name, summary=summary, shape=shape))
        entries.append(
            CommandInventoryEntry(
                command_name=bare,
                is_slash=True,
                slash_name=name,
                exempt_reason=None,
                metadata=None,
                callback=callback,
            )
        )
    extended = replace(
        registry,
        slash_specs=tuple(normalize_specs(specs)),
        inventory=tuple(dedupe_entries(entries)),
    )
    commands.set_active_specs(extended.slash_specs)
    commands.set_help_spec_names(set(HELP_SPEC_ORDER))
    return extended
