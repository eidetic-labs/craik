"""CommandResult helpers for diagnostic CLI and slash-command surfaces."""

from __future__ import annotations

import os

from craik.runtime.contract import CommandResult
from craik.runtime.doctor import run_doctor
from craik.runtime.paths import resolve_craik_paths
from craik.runtime.projects.update_guidance import update_guidance_payload


def doctor_result(
    *,
    fix: bool = False,
    dry_run: bool = True,
    confirm_unsafe: bool = False,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Run diagnostics and return a structured command result."""
    command_env = dict(os.environ) if env is None else dict(env)
    payload = run_doctor(
        resolve_craik_paths(env),
        env=command_env,
        fix=fix,
        dry_run=dry_run,
        confirm_unsafe=confirm_unsafe,
    )
    return CommandResult(payload=payload, shape="tree")


def update_guidance_result(
    *,
    installed_version: str,
    check: bool = False,
) -> CommandResult:
    """Return safe update guidance without modifying the installation."""
    payload = update_guidance_payload(installed_version=installed_version)
    payload["mode"] = "check" if check else "manual"
    return CommandResult(payload=payload, shape="tree")
