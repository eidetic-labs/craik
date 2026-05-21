"""Handoff CLI commands."""

from __future__ import annotations

import json
from typing import Annotated, cast

import typer

from craik.cli import handoff_app
from craik.contracts.models import RunStatus
from craik.runtime.store import LocalStore
from craik.runtime.work.handoffs import (
    HandoffBlockedByExitDisciplineError,
    HandoffContextError,
    HandoffNotFoundError,
    HandoffWriter,
    render_markdown,
)


@handoff_app.command("create")
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
) -> None:
    """Create a structured handoff for a task."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        writer = HandoffWriter(store)
        handoff = writer.create(
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
        )
    except (HandoffContextError, HandoffBlockedByExitDisciplineError) as error:
        raise typer.BadParameter(str(error)) from None
    finally:
        store.close()

    if markdown:
        typer.echo(render_markdown(handoff))
    else:
        typer.echo(
            json.dumps(handoff.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True)
        )


@handoff_app.command("show")
def handoff_show(
    handoff_or_task_id: str,
    markdown: Annotated[
        bool,
        typer.Option("--markdown", help="Print Markdown instead of JSON."),
    ] = False,
) -> None:
    """Show one persisted handoff by handoff id or task id."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        handoff = HandoffWriter(store).require(handoff_or_task_id)
    except HandoffNotFoundError as error:
        raise typer.BadParameter(str(error)) from None
    finally:
        store.close()

    if markdown:
        typer.echo(render_markdown(handoff))
    else:
        typer.echo(
            json.dumps(handoff.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True)
        )


def _run_status(value: str) -> RunStatus:
    if value not in {"completed", "incomplete", "blocked", "failed"}:
        raise typer.BadParameter(f"unsupported run status: {value}")
    return cast(RunStatus, value)
