"""Receipts CLI commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from craik.cli_operator_auth import operator_identity_or_fail
from craik.runtime.contract import CommandResult, craik_command
from craik.runtime.work.receipts import (
    receipts_list_result,
    receipts_show_result,
    receipts_verify_result,
)

receipts_app = typer.Typer(help="Inspect persisted capability receipts.")


@receipts_app.command("list")
@craik_command(slash_alias="receipts-list", payload_shape="card_list")
def receipts_list(
    task_id: Annotated[
        str | None,
        typer.Option("--task-id", help="Only include receipts for this task id."),
    ] = None,
    policy_id: Annotated[
        str | None,
        typer.Option("--policy-id", help="Only include receipts linked to this policy envelope."),
    ] = None,
    handoff_id: Annotated[
        str | None,
        typer.Option("--handoff-id", help="Only include receipts linked to this handoff."),
    ] = None,
) -> CommandResult:
    """Print persisted capability receipts as JSON."""
    operator_identity_or_fail()
    result = receipts_list_result(task_id=task_id, policy_id=policy_id, handoff_id=handoff_id)
    typer.echo(json.dumps(result.payload, indent=2, sort_keys=True))
    return result


@receipts_app.command("show")
@craik_command(slash_alias="receipts-show", payload_shape="card")
def receipts_show(receipt_id: str) -> CommandResult:
    """Print one capability receipt by id as JSON."""
    operator_identity_or_fail()
    try:
        result = receipts_show_result(receipt_id)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from None
    typer.echo(json.dumps(result.payload, indent=2, sort_keys=True))
    return result


@receipts_app.command("verify")
@craik_command(slash_alias="receipts-verify", payload_shape="kv")
def receipts_verify(
    path: Annotated[
        str,
        typer.Argument(help="Receipt JSON path, or '-' to read from stdin."),
    ],
    public_key: Annotated[
        Path | None,
        typer.Option("--public-key", help="HMAC key material path for verification."),
    ] = None,
    auto_discover: Annotated[
        bool,
        typer.Option("--auto-discover", help="Discover the local Craik HMAC key from CRAIK_HOME."),
    ] = False,
    side_log_base: Annotated[
        Path | None,
        typer.Option("--side-log-base", help="Directory containing shell side-log files."),
    ] = None,
) -> CommandResult:
    """Verify a receipt JSON file without trusting the producing runtime."""
    try:
        result = receipts_verify_result(
            path,
            public_key=public_key,
            auto_discover=auto_discover,
            side_log_base=side_log_base,
        )
    except OSError as error:
        raise typer.BadParameter(str(error)) from None
    typer.echo(json.dumps(result.payload, indent=2, sort_keys=True))
    if result.exit_code:
        raise typer.Exit(result.exit_code)
    return result
