"""Handoff CLI commands."""

from __future__ import annotations

from typing import Annotated, cast

import typer

from craik.cli import handoff_app
from craik.cli_operator_auth import operator_identity_or_fail
from craik.cli_output import emit_command_result
from craik.contracts.models import RunStatus
from craik.runtime.contract import CommandResult, craik_command
from craik.runtime.work.commands.handoff_commands import (
    handoff_create_result,
    handoff_list_result,
    handoff_show_result,
)


@handoff_app.command("list")
@craik_command(slash_alias="handoffs", payload_shape="card_list")
def handoff_list() -> CommandResult:
    """List persisted handoffs."""
    operator_identity_or_fail()
    result = handoff_list_result()
    emit_command_result(result)
    return result


@handoff_app.command("create")
@craik_command(payload_shape="card")
def handoff_create(
    task_id: Annotated[str, typer.Argument(help="Task id to create a handoff for.")],
    summary: Annotated[str, typer.Option("--summary", help="Handoff summary.")],
    agent: Annotated[str, typer.Option("--agent", help="Agent identity.")] = "agent:local",
    status: Annotated[
        str,
        typer.Option("--status", help="Status: completed, incomplete, blocked, or failed."),
    ] = "completed",
    completed_action: Annotated[
        list[str] | None,
        typer.Option("--completed-action", help="Completed action. May be repeated."),
    ] = None,
    file_changed: Annotated[
        list[str] | None,
        typer.Option("--file-changed", help="Changed file. May be repeated."),
    ] = None,
    artifact: Annotated[
        list[str] | None,
        typer.Option("--artifact", help="Artifact path or id. May be repeated."),
    ] = None,
    command_run: Annotated[
        list[str] | None,
        typer.Option("--command-run", help="Command run. May be repeated."),
    ] = None,
    test_run: Annotated[
        list[str] | None,
        typer.Option("--test-run", help="Validation run. May be repeated."),
    ] = None,
    risk: Annotated[
        list[str] | None,
        typer.Option("--risk", help="Residual risk. May be repeated."),
    ] = None,
    next_step: Annotated[
        list[str] | None,
        typer.Option("--next-step", help="Next step. May be repeated."),
    ] = None,
    policy_exception: Annotated[
        list[str] | None,
        typer.Option("--policy-exception", help="Policy exception or fail-open note."),
    ] = None,
    self_audit_note: Annotated[
        list[str] | None,
        typer.Option("--self-audit-note", help="Self-audit note. May be repeated."),
    ] = None,
    markdown: Annotated[
        bool,
        typer.Option("--markdown", help="Print Markdown instead of JSON."),
    ] = False,
    allow_blocked_exit: Annotated[
        bool,
        typer.Option(
            "--allow-blocked-exit",
            help="Persist the handoff despite a blocked exit-discipline check.",
        ),
    ] = False,
    blocked_exit_rationale: Annotated[
        str | None,
        typer.Option("--blocked-exit-rationale", help="Required with --allow-blocked-exit."),
    ] = None,
) -> CommandResult:
    """Create a structured handoff for a task."""
    operator_identity_or_fail()
    try:
        result = handoff_create_result(
            task_id=task_id,
            agent=agent,
            summary=summary,
            status=_run_status(status),
            completed_actions=completed_action,
            files_changed=file_changed,
            artifacts=artifact,
            commands_run=command_run,
            tests_run=test_run,
            risks=risk,
            next_steps=next_step,
            policy_exceptions=policy_exception,
            self_audit_notes=self_audit_note,
            allow_blocked_exit=allow_blocked_exit,
            blocked_exit_rationale=blocked_exit_rationale,
            markdown=markdown,
        )
    except ValueError as error:
        raise typer.BadParameter(str(error)) from None

    if markdown:
        typer.echo(result.text or "")
    else:
        emit_command_result(result)
    return result


@handoff_app.command("show")
@craik_command(payload_shape="card")
def handoff_show(
    handoff_or_task_id: str,
    markdown: Annotated[
        bool,
        typer.Option("--markdown", help="Print Markdown instead of JSON."),
    ] = False,
) -> CommandResult:
    """Show one persisted handoff by handoff id or task id."""
    operator_identity_or_fail()
    try:
        result = handoff_show_result(handoff_or_task_id, markdown=markdown)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from None

    if markdown:
        typer.echo(result.text or "")
    else:
        emit_command_result(result)
    return result


def _run_status(value: str) -> RunStatus:
    if value not in {"completed", "incomplete", "blocked", "failed"}:
        raise typer.BadParameter(f"unsupported run status: {value}")
    return cast(RunStatus, value)
