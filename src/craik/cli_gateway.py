"""Gateway daemon CLI commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from craik.cli_output import emit_command_result
from craik.runtime.auth.operator import OperatorSessionNotFoundError, OperatorSessionStore
from craik.runtime.contract import CommandResult, craik_command
from craik.runtime.gateway import GatewayDaemonError
from craik.runtime.paths import resolve_craik_home
from craik.runtime.services.gateway_commands import (
    gateway_doctor_result,
    gateway_install_result,
    gateway_logs_result,
    gateway_restart_result,
    gateway_start_result,
    gateway_status_result,
    gateway_stop_result,
    gateway_uninstall_result,
)

gateway_app = typer.Typer(help="Run and inspect the local gateway daemon.")


@gateway_app.command("start")
@craik_command(payload_shape="card")
def gateway_start_command() -> CommandResult:
    """Run the foreground gateway daemon until interrupted."""
    _operator_identity()
    try:
        result = gateway_start_result()
    except GatewayDaemonError as error:
        raise typer.BadParameter(str(error)) from None
    emit_command_result(result)
    return result


@gateway_app.command("stop")
@craik_command(payload_shape="card")
def gateway_stop_command(
    signal_process: Annotated[
        bool,
        typer.Option(
            "--signal-process",
            help="Send SIGTERM to the recorded pid before marking the gateway stopped.",
        ),
    ] = False,
) -> CommandResult:
    """Request gateway stop and recover stale pid state."""
    _operator_identity()
    try:
        result = gateway_stop_result(signal_process=signal_process)
    except GatewayDaemonError as error:
        raise typer.BadParameter(str(error)) from None
    emit_command_result(result)
    return result


@gateway_app.command("restart")
@craik_command(payload_shape="card")
def gateway_restart_command() -> CommandResult:
    """Request a gateway restart by stopping the current lifecycle state."""
    _operator_identity()
    try:
        result = gateway_restart_result()
    except GatewayDaemonError as error:
        raise typer.BadParameter(str(error)) from None
    emit_command_result(result)
    return result


@gateway_app.command("status")
@craik_command(slash_alias="gateway", payload_shape="kv")
def gateway_status_command() -> CommandResult:
    """Show gateway config, runtime state, pid, bind, and stale-pid status."""
    result = gateway_status_result()
    emit_command_result(result)
    return result


@gateway_app.command("logs")
@craik_command(payload_shape="card")
def gateway_logs_command(
    tail: Annotated[int, typer.Option("--tail", min=1, max=500)] = 50,
) -> CommandResult:
    """Show recent gateway log lines."""
    _operator_identity()
    result = gateway_logs_result(tail=tail)
    emit_command_result(result)
    return result


@gateway_app.command("doctor")
@craik_command(payload_shape="card_list")
def gateway_doctor_command() -> CommandResult:
    """Run gateway-focused diagnostics."""
    result = gateway_doctor_result()
    emit_command_result(result)
    return result


@gateway_app.command("install")
@craik_command(payload_shape="card")
def gateway_install_command(
    backend: Annotated[
        str | None,
        typer.Option("--backend", help="Service backend: systemd, launchd, or windows-plan."),
    ] = None,
    executable_path: Annotated[
        Path | None,
        typer.Option("--executable-path", help="Override resolved craik binary path."),
    ] = None,
    log_path: Annotated[
        Path | None,
        typer.Option("--log-path", help="Override gateway log path in generated service unit."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Print generated service unit without writing it."),
    ] = False,
    output: Annotated[
        str | None,
        typer.Option(
            "--output",
            help="Write unit to PATH instead of default location; '-' for stdout.",
        ),
    ] = None,
) -> CommandResult:
    """Generate a user-service definition for the local gateway."""
    try:
        result = gateway_install_result(
            backend=backend,
            executable_path=executable_path,
            log_path=log_path,
            dry_run=dry_run,
            output=output,
        )
    except GatewayDaemonError as error:
        raise typer.BadParameter(str(error)) from None
    if dry_run or output == "-":
        typer.echo(result.text or "", nl=False)
        return result
    emit_command_result(result)
    return result


@gateway_app.command("uninstall")
@craik_command(payload_shape="card")
def gateway_uninstall_command() -> CommandResult:
    """Remove generated gateway service definitions."""
    result = gateway_uninstall_result()
    emit_command_result(result)
    return result


def _operator_identity() -> str:
    try:
        session = OperatorSessionStore(resolve_craik_home()).get()
    except OperatorSessionNotFoundError:
        raise typer.BadParameter("active operator session required; run craik login") from None
    return session.subject
