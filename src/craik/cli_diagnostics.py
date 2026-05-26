"""Root diagnostic and update CLI commands."""

from __future__ import annotations

from typing import Annotated

import typer

from craik.cli_output import emit_command_result
from craik.runtime.contract import CommandResult, craik_command
from craik.runtime.diagnostics.commands import doctor_result, update_guidance_result


@craik_command(slash_alias="doctor", payload_shape="tree")
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
) -> CommandResult:
    """Run diagnostics for local and gateway readiness."""
    result = doctor_result(
        fix=fix,
        dry_run=dry_run,
        confirm_unsafe=yes,
    )
    _ = json_output
    emit_command_result(result)
    return result


@craik_command(payload_shape="tree")
def update_command(
    check: Annotated[
        bool,
        typer.Option("--check", help="Check for update guidance without changing installation."),
    ] = False,
) -> CommandResult:
    """Print safe update guidance without modifying the installation."""
    from craik.cli import package_version

    result = update_guidance_result(installed_version=package_version(), check=check)
    emit_command_result(result)
    return result
