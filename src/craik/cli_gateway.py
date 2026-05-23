"""Gateway daemon CLI commands."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated

import typer

from craik.runtime.auth.operator import OperatorSessionNotFoundError, OperatorSessionStore
from craik.runtime.doctor import run_doctor
from craik.runtime.gateway import GatewayDaemonError, run_gateway_daemon
from craik.runtime.paths import resolve_craik_home, resolve_craik_paths
from craik.runtime.services.gateway import (
    gateway_logs_payload,
    gateway_status_payload,
    install_gateway_service,
    request_gateway_stop,
    uninstall_gateway_service,
)

gateway_app = typer.Typer(help="Run and inspect the local gateway daemon.")


@gateway_app.command("start")
def gateway_start_command() -> None:
    """Run the foreground gateway daemon until interrupted."""
    _operator_identity()
    paths = resolve_craik_paths()
    try:
        state = run_gateway_daemon(paths)
    except GatewayDaemonError as error:
        raise typer.BadParameter(str(error)) from None
    typer.echo(json.dumps(state.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True))


@gateway_app.command("stop")
def gateway_stop_command(
    signal_process: Annotated[
        bool,
        typer.Option(
            "--signal-process",
            help="Send SIGTERM to the recorded pid before marking the gateway stopped.",
        ),
    ] = False,
) -> None:
    """Request gateway stop and recover stale pid state."""
    _operator_identity()
    try:
        state = request_gateway_stop(resolve_craik_paths(), signal_process=signal_process)
    except GatewayDaemonError as error:
        raise typer.BadParameter(str(error)) from None
    typer.echo(json.dumps(state.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True))


@gateway_app.command("restart")
def gateway_restart_command() -> None:
    """Request a gateway restart by stopping the current lifecycle state."""
    _operator_identity()
    try:
        state = request_gateway_stop(resolve_craik_paths())
    except GatewayDaemonError as error:
        raise typer.BadParameter(str(error)) from None
    payload = {
        "status": "restart_requested",
        "stopped_state": state.model_dump(mode="json", by_alias=True),
        "next_step": "start the installed service, or run `craik gateway start` in foreground",
    }
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@gateway_app.command("status")
def gateway_status_command() -> None:
    """Show gateway config, runtime state, pid, bind, and stale-pid status."""
    typer.echo(json.dumps(gateway_status_payload(resolve_craik_paths()), indent=2, sort_keys=True))


@gateway_app.command("logs")
def gateway_logs_command(
    tail: Annotated[int, typer.Option("--tail", min=1, max=500)] = 50,
) -> None:
    """Show recent gateway log lines."""
    _operator_identity()
    typer.echo(
        json.dumps(gateway_logs_payload(resolve_craik_paths(), tail=tail), indent=2, sort_keys=True)
    )


@gateway_app.command("doctor")
def gateway_doctor_command() -> None:
    """Run gateway-focused diagnostics."""
    payload = run_doctor(resolve_craik_paths(), env=dict(os.environ))
    typer.echo(json.dumps({"gateway": payload["checks"]}, indent=2, sort_keys=True))


@gateway_app.command("install")
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
) -> None:
    """Generate a user-service definition for the local gateway."""
    try:
        install = install_gateway_service(
            resolve_craik_paths(),
            backend=backend,
            executable_path=executable_path,
            log_path=log_path,
            dry_run=dry_run,
            output_path=output,
        )
    except GatewayDaemonError as error:
        raise typer.BadParameter(str(error)) from None
    if dry_run or output == "-":
        typer.echo(install.content, nl=False)
        return
    payload = {
        "backend": install.backend,
        "path": str(install.path),
        "installed": install.installed,
        "notes": list(install.notes),
    }
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@gateway_app.command("uninstall")
def gateway_uninstall_command() -> None:
    """Remove generated gateway service definitions."""
    payload = uninstall_gateway_service(resolve_craik_paths())
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


def _operator_identity() -> str:
    try:
        session = OperatorSessionStore(resolve_craik_home()).get()
    except OperatorSessionNotFoundError:
        raise typer.BadParameter("active operator session required; run craik login") from None
    return session.subject
