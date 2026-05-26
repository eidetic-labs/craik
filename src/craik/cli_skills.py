"""Skill package CLI commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from craik.cli import skills_app
from craik.cli_output import emit_command_result
from craik.runtime.auth.operator import OperatorSessionNotFoundError, OperatorSessionStore
from craik.runtime.contract import CommandResult, craik_command
from craik.runtime.skills.commands import (
    skills_eval_result,
    skills_history_result,
    skills_install_result,
    skills_list_result,
    skills_overview_result,
    skills_promote_result,
    skills_proposals_result,
    skills_rollback_result,
    skills_set_active_result,
    skills_show_result,
    skills_telemetry_result,
)


@skills_app.command("install")
@craik_command(payload_shape="card")
def skills_install(
    path: Annotated[Path, typer.Argument(help="Skill package JSON manifest.")],
) -> CommandResult:
    """Install a skill package manifest."""
    _operator_identity()
    result = skills_install_result(path)
    emit_command_result(result)
    return result


@skills_app.command("list")
@craik_command(slash_alias="skills-list", payload_shape="card_list")
def skills_list(
    scope: Annotated[
        str | None,
        typer.Option("--scope", help="Optional registry scope: project or global."),
    ] = None,
) -> CommandResult:
    """List installed skill packages."""
    _operator_identity()
    result = skills_list_result(scope=scope)
    emit_command_result(result)
    return result


@skills_app.command("enable")
@craik_command(payload_shape="card")
def skills_enable(
    entry_id: Annotated[str, typer.Argument(help="Skill registry entry id.")],
) -> CommandResult:
    """Enable a skill registry entry."""
    _operator_identity()
    return _set_active(entry_id, active=True)


@skills_app.command("disable")
@craik_command(payload_shape="card")
def skills_disable(
    entry_id: Annotated[str, typer.Argument(help="Skill registry entry id.")],
) -> CommandResult:
    """Disable a skill registry entry."""
    _operator_identity()
    return _set_active(entry_id, active=False)


@skills_app.command("show")
@craik_command(payload_shape="card")
def skills_show(
    package_id: Annotated[str, typer.Argument(help="Skill package id.")],
) -> CommandResult:
    """Show one installed skill package."""
    _operator_identity()
    try:
        result = skills_show_result(package_id)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from None
    emit_command_result(result)
    return result


@skills_app.command("telemetry")
@craik_command(payload_shape="card_list")
def skills_telemetry() -> CommandResult:
    """Summarize redacted skill invocation telemetry inputs."""
    _operator_identity()
    result = skills_telemetry_result()
    emit_command_result(result)
    return result


@skills_app.command("proposals")
@craik_command(payload_shape="card_list")
def skills_proposals() -> CommandResult:
    """List reviewable learning-loop proposal sources."""
    _operator_identity()
    result = skills_proposals_result()
    emit_command_result(result)
    return result


@skills_app.command("eval")
@craik_command(payload_shape="card_list")
def skills_eval(
    package_id: Annotated[str | None, typer.Option("--package-id")] = None,
) -> CommandResult:
    """Report replay/eval readiness for skill promotion gates."""
    _operator_identity()
    result = skills_eval_result(package_id=package_id)
    emit_command_result(result)
    return result


@skills_app.command("promote")
@craik_command(payload_shape="card")
def skills_promote(
    proposal_id: Annotated[str, typer.Argument(help="Proposal id to review for promotion.")],
    dry_run: Annotated[bool, typer.Option("--dry-run/--apply")] = True,
) -> CommandResult:
    """Preview a skill promotion decision; promotion remains approval-gated."""
    _operator_identity()
    result = skills_promote_result(proposal_id, dry_run=dry_run)
    emit_command_result(result)
    return result


@skills_app.command("rollback")
@craik_command(payload_shape="card")
def skills_rollback(
    package_id: Annotated[str, typer.Argument(help="Skill package id.")],
    dry_run: Annotated[bool, typer.Option("--dry-run/--apply")] = True,
) -> CommandResult:
    """Preview rollback posture for a skill package."""
    _operator_identity()
    result = skills_rollback_result(package_id, dry_run=dry_run)
    emit_command_result(result)
    return result


@skills_app.command("history")
@craik_command(payload_shape="card_list")
def skills_history() -> CommandResult:
    """Show skill package and learning-loop receipt history."""
    _operator_identity()
    result = skills_history_result()
    emit_command_result(result)
    return result


def skills_overview() -> CommandResult:
    """Return the operator-facing skills overview payload."""
    return skills_overview_result()


def _set_active(entry_id: str, *, active: bool) -> CommandResult:
    try:
        result = skills_set_active_result(entry_id, active=active)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from None
    emit_command_result(result)
    return result


def _operator_identity() -> str:
    try:
        session = OperatorSessionStore.from_env().get()
    except OperatorSessionNotFoundError:
        raise typer.BadParameter("active operator session required; run craik login") from None
    return session.subject
