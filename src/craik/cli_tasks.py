"""Task continuation CLI commands."""

from __future__ import annotations

import json
from typing import Annotated, cast

import typer

from craik.cli import task_app
from craik.contracts.models import Priority, RunnerMode, TaskMode
from craik.runtime.store import LocalStore
from craik.runtime.work.coordination.handoff_consumption import (
    HandoffConsumptionError,
    consume_handoff,
)


@task_app.command("resume")
def task_resume(
    from_handoff: Annotated[
        str,
        typer.Option("--from-handoff", help="Source handoff id or source task id to consume."),
    ],
    auth_profile_id: Annotated[
        str,
        typer.Option("--auth-profile-id", help="Consumer auth profile for the new run."),
    ],
    operator_subject: Annotated[
        str,
        typer.Option("--operator-subject", help="Consumer operator subject for the new run."),
    ],
    operator_issuer: Annotated[
        str,
        typer.Option("--operator-issuer", help="Consumer operator issuer for the new run."),
    ],
    title: Annotated[str | None, typer.Option("--title", help="Follow-up task title.")] = None,
    objective: Annotated[
        str | None,
        typer.Option("--objective", help="Follow-up task objective."),
    ] = None,
    requested_by: Annotated[
        str,
        typer.Option("--requested-by", help="Requester identity to store on the task."),
    ] = "user:local",
    priority: Annotated[
        str,
        typer.Option("--priority", help="Priority: low, normal, high, or urgent."),
    ] = "normal",
    mode: Annotated[
        str,
        typer.Option("--mode", help="Mode: plan, review, implement, or verify."),
    ] = "implement",
    runner_id: Annotated[
        str,
        typer.Option("--runner", help="Runner id assigned to the pending run."),
    ] = "fixture",
    runner_mode: Annotated[
        str,
        typer.Option("--runner-mode", help="Runner mode: fixture, prompt-handoff, or live."),
    ] = "fixture",
    max_iterations: Annotated[
        int,
        typer.Option("--max-iterations", help="Maximum run iterations."),
    ] = 5,
    allow_identity_continuation: Annotated[
        bool,
        typer.Option(
            "--allow-identity-continuation",
            help="Explicitly allow the consumer to reuse the producer identity.",
        ),
    ] = False,
) -> None:
    """Consume a handoff into a new task, case file, and pending run."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        result = consume_handoff(
            store,
            handoff_id_or_task_id=from_handoff,
            title=title,
            objective=objective,
            requested_by=requested_by,
            priority=_priority(priority),
            mode=_task_mode(mode),
            auth_profile_id=auth_profile_id,
            operator_subject=operator_subject,
            operator_issuer=operator_issuer,
            runner_id=runner_id,
            runner_mode=_runner_mode(runner_mode),
            max_iterations=max_iterations,
            allow_identity_continuation=allow_identity_continuation,
        )
    except HandoffConsumptionError as error:
        raise typer.BadParameter(str(error)) from None
    finally:
        store.close()

    payload = {
        "source_handoff": result.source_handoff.model_dump(mode="json", by_alias=True),
        "task": result.task.model_dump(mode="json", by_alias=True),
        "intent_lock": result.intent_lock.model_dump(mode="json", by_alias=True),
        "case_file": result.case_file.model_dump(mode="json", by_alias=True),
        "run": result.run.model_dump(mode="json", by_alias=True),
    }
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


def _priority(value: str) -> Priority:
    if value not in {"low", "normal", "high", "urgent"}:
        raise typer.BadParameter(f"unsupported priority: {value}")
    return cast(Priority, value)


def _task_mode(value: str) -> TaskMode:
    if value not in {"plan", "review", "implement", "verify"}:
        raise typer.BadParameter(f"unsupported task mode: {value}")
    return cast(TaskMode, value)


def _runner_mode(value: str) -> RunnerMode:
    if value not in {"fixture", "prompt-handoff", "live"}:
        raise typer.BadParameter(f"unsupported runner mode: {value}")
    return cast(RunnerMode, value)
