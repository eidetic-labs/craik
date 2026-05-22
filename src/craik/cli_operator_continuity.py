"""Read-only operator continuity CLI commands."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Annotated

import typer

from craik.cli import operator_app
from craik.cli_operator_auth import operator_identity_or_fail
from craik.cli_operator_support import (
    json_ready,
    project_scope,
    record_in_project,
    task_ids_for_project,
)
from craik.contracts.models import RunDelta
from craik.runtime.companions.operator_views import (
    KnownTrapsSnapshot,
    RunDeltaSnapshot,
    format_known_traps_view,
    format_run_delta_view,
)
from craik.runtime.store import LocalStore


@operator_app.command("traps")
def operator_traps(
    project_id: Annotated[
        str | None,
        typer.Option("--project", help="Only include records in this project scope."),
    ] = None,
    task_id: Annotated[
        str | None,
        typer.Option("--task-id", help="Only include records for this task."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json/--view", help="Print JSON instead of the operator view."),
    ] = False,
) -> None:
    """Print the read-only known traps and negative knowledge view."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        resolved_project_id = project_scope(store, project_id)
        task_ids = task_ids_for_project(store, resolved_project_id)
        known_traps = store.list_known_traps()
        negative_knowledge = store.list_negative_knowledge()
    finally:
        store.close()

    if resolved_project_id is not None:
        known_traps = [
            item
            for item in known_traps
            if record_in_project(item, resolved_project_id, task_ids)
        ]
        negative_knowledge = [
            item
            for item in negative_knowledge
            if record_in_project(item, resolved_project_id, task_ids)
        ]
    if task_id is not None:
        known_traps = [item for item in known_traps if item.task_id == task_id]
        negative_knowledge = [item for item in negative_knowledge if item.task_id == task_id]

    snapshot = KnownTrapsSnapshot(
        known_traps=known_traps,
        negative_knowledge=negative_knowledge,
        now=datetime.now(UTC),
    )

    if json_output:
        typer.echo(json.dumps(json_ready(snapshot), indent=2, sort_keys=True))
    else:
        typer.echo("\n".join(format_known_traps_view(snapshot)))


@operator_app.command("run-delta")
@operator_app.command("run-deltas")
def operator_run_delta(
    delta_id_or_run_id_or_task_id: Annotated[
        str,
        typer.Argument(help="Run delta id, run id, or task id to inspect."),
    ],
    json_output: Annotated[
        bool,
        typer.Option("--json/--view", help="Print JSON instead of the operator view."),
    ] = False,
) -> None:
    """Print the read-only run delta and recovery view."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        delta = _find_run_delta(store, delta_id_or_run_id_or_task_id)
        if delta is None:
            raise typer.BadParameter(
                f"unknown run delta, run, or task: {delta_id_or_run_id_or_task_id}"
            )
        recovery_sessions = [
            session
            for session in store.list_recovery_sessions()
            if session.run_delta_id == delta.id
        ]
        snapshot = RunDeltaSnapshot(
            delta=delta,
            recovery_sessions=recovery_sessions,
        )
    finally:
        store.close()

    if json_output:
        typer.echo(json.dumps(json_ready(snapshot), indent=2, sort_keys=True))
    else:
        typer.echo("\n".join(format_run_delta_view(snapshot)))


def _find_run_delta(
    store: LocalStore,
    delta_id_or_run_id_or_task_id: str,
) -> RunDelta | None:
    delta = store.get_run_delta(delta_id_or_run_id_or_task_id)
    if delta is not None:
        return delta
    run = store.get_task_run(delta_id_or_run_id_or_task_id)
    if run is None:
        runs = [
            candidate
            for candidate in store.list_task_runs()
            if candidate.task_id == delta_id_or_run_id_or_task_id
        ]
        run = runs[-1] if runs else None
    task_id = run.task_id if run is not None else delta_id_or_run_id_or_task_id
    candidates = [item for item in store.list_run_deltas() if item.task_id == task_id]
    if run is not None and run.handoff_id:
        handoff_matches = [
            item
            for item in candidates
            if item.current_handoff_id == run.handoff_id
            or item.previous_handoff_id == run.handoff_id
        ]
        if handoff_matches:
            candidates = handoff_matches
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: (item.created_at, item.id))[-1]
