"""Slash-command adapters for gateway and receipt system surfaces."""

from __future__ import annotations

from craik.runtime.services.gateway_commands import (
    gateway_doctor_result,
    gateway_logs_result,
    gateway_status_result,
)
from craik.runtime.shell.slash_command_schema.results import (
    SlashCommandResult,
    payload_result,
)
from craik.runtime.work.receipts import receipts_list_result, receipts_show_result


def receipts_slash_result(
    args: list[str],
    *,
    env: dict[str, str] | None,
) -> SlashCommandResult:
    """Return a slash result for receipt list/detail operations."""
    subcommand = args[0] if args else "list"
    if subcommand == "list":
        return payload_result("receipts", receipts_list_result(env=env).payload)
    if subcommand in {"detail", "show"}:
        if len(args) < 2:
            return SlashCommandResult("receipts detail requires a receipt id", exit_code=2)
        try:
            return payload_result("receipts", receipts_show_result(args[1], env=env).payload)
        except ValueError as error:
            return SlashCommandResult(str(error), exit_code=2)
    if subcommand == "verify":
        return SlashCommandResult(
            "Receipt verification requires a receipt path. "
            "Run `craik receipts verify <path>` from an outer shell."
        )
    return SlashCommandResult(f"unknown receipts subcommand: {subcommand}", exit_code=2)


def gateway_slash_result(
    args: list[str],
    *,
    env: dict[str, str] | None,
) -> SlashCommandResult:
    """Return a slash result for gateway status, logs, and diagnostics."""
    subcommand = args[0] if args else "status"
    if subcommand == "status":
        return payload_result("gateway", gateway_status_result(env).payload)
    if subcommand == "logs":
        return payload_result("gateway", gateway_logs_result(env=env).payload)
    if subcommand == "doctor":
        return payload_result("gateway", gateway_doctor_result(env).payload)
    if subcommand in {"start", "stop", "restart", "install", "uninstall"}:
        return SlashCommandResult(
            f"Gateway {subcommand} is available from the CLI as "
            f"`craik gateway {subcommand}`."
        )
    return SlashCommandResult(f"unknown gateway subcommand: {subcommand}", exit_code=2)
