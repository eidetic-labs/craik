"""Root diagnostic and update CLI commands."""

from __future__ import annotations

import json
import os
from typing import Annotated

import typer

from craik.runtime.doctor import run_doctor
from craik.runtime.paths import resolve_craik_paths
from craik.runtime.projects.update_guidance import update_guidance_payload


def doctor_command(
    fix: Annotated[
        bool,
        typer.Option("--fix", help="Plan or apply narrow supported fixes."),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run/--apply",
            help="Preview fixes without writing state, or apply supported safe fixes.",
        ),
    ] = True,
    yes: Annotated[
        bool,
        typer.Option("--yes", help="Confirm unsafe fix actions such as public-bind rebinding."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print the diagnostic report as JSON."),
    ] = False,
) -> None:
    """Run diagnostics for local and gateway readiness."""
    payload = run_doctor(
        resolve_craik_paths(),
        env=dict(os.environ),
        fix=fix,
        dry_run=dry_run,
        confirm_unsafe=yes,
    )
    _ = json_output
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


def update_command(
    check: Annotated[
        bool,
        typer.Option("--check", help="Check for update guidance without changing installation."),
    ] = False,
) -> None:
    """Print safe update guidance without modifying the installation."""
    from craik.cli import package_version

    payload = update_guidance_payload(installed_version=package_version())
    payload["mode"] = "check" if check else "manual"
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))
