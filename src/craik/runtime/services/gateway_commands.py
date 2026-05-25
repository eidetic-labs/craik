"""CommandResult helpers for gateway CLI and slash-command surfaces."""

from __future__ import annotations

import os
from pathlib import Path

from craik.runtime.contract import CommandResult
from craik.runtime.doctor import run_doctor
from craik.runtime.gateway import run_gateway_daemon
from craik.runtime.paths import resolve_craik_paths
from craik.runtime.services.gateway import (
    gateway_logs_payload,
    gateway_status_payload,
    install_gateway_service,
    request_gateway_stop,
    uninstall_gateway_service,
)


def gateway_start_result(env: dict[str, str] | None = None) -> CommandResult:
    """Run the foreground gateway daemon and return its final state."""
    state = run_gateway_daemon(resolve_craik_paths(env))
    return CommandResult(
        payload=state.model_dump(mode="json", by_alias=True),
        shape="card",
    )


def gateway_stop_result(
    *,
    signal_process: bool = False,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Request gateway shutdown and return the persisted stopped state."""
    state = request_gateway_stop(resolve_craik_paths(env), signal_process=signal_process)
    return CommandResult(
        payload=state.model_dump(mode="json", by_alias=True),
        shape="card",
    )


def gateway_restart_result(env: dict[str, str] | None = None) -> CommandResult:
    """Request gateway restart by stopping the current lifecycle state."""
    state = request_gateway_stop(resolve_craik_paths(env))
    return CommandResult(
        payload={
            "status": "restart_requested",
            "stopped_state": state.model_dump(mode="json", by_alias=True),
            "next_step": "start the installed service, or run `craik gateway start` in foreground",
        },
        shape="card",
    )


def gateway_status_result(env: dict[str, str] | None = None) -> CommandResult:
    """Return gateway config, runtime state, pid, bind, and stale-pid status."""
    return CommandResult(
        payload=gateway_status_payload(resolve_craik_paths(env)),
        shape="kv",
    )


def gateway_logs_result(*, tail: int = 50, env: dict[str, str] | None = None) -> CommandResult:
    """Return recent gateway log lines."""
    return CommandResult(
        payload=gateway_logs_payload(resolve_craik_paths(env), tail=tail),
        shape="card",
        empty_state_message="No gateway logs are available yet.",
    )


def gateway_doctor_result(env: dict[str, str] | None = None) -> CommandResult:
    """Run gateway-focused diagnostics."""
    command_env = dict(os.environ)
    if env:
        command_env.update(env)
    payload = run_doctor(resolve_craik_paths(env), env=command_env)
    return CommandResult(payload={"gateway": payload["checks"]}, shape="card_list")


def gateway_install_result(
    *,
    backend: str | None = None,
    executable_path: Path | None = None,
    log_path: Path | None = None,
    dry_run: bool = False,
    output: str | None = None,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Generate a user-service definition for the local gateway."""
    install = install_gateway_service(
        resolve_craik_paths(env),
        backend=backend,
        executable_path=executable_path,
        log_path=log_path,
        dry_run=dry_run,
        output_path=output,
    )
    if dry_run or output == "-":
        return CommandResult(
            payload={"content": install.content},
            shape="markdown",
            text=install.content,
        )
    return CommandResult(
        payload={
            "backend": install.backend,
            "path": str(install.path),
            "installed": install.installed,
            "notes": list(install.notes),
        },
        shape="card",
    )


def gateway_uninstall_result(env: dict[str, str] | None = None) -> CommandResult:
    """Remove generated gateway service definitions."""
    return CommandResult(payload=uninstall_gateway_service(resolve_craik_paths(env)), shape="card")
