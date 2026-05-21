"""Run command group for the Craik CLI."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Annotated, Any

import typer

from craik.cli_run_support import fixture_shell_grant, provider_run_payload, role_kind
from craik.contracts.models import (
    RecoverySession,
    RunDelta,
    TaskRun,
)
from craik.runtime.auth.operator import OperatorSessionNotFoundError, OperatorSessionStore
from craik.runtime.companions.operator_views import (
    RunDeltaSnapshot,
    format_run_delta_view,
)
from craik.runtime.providers.model_providers import ModelProviderNotFoundError
from craik.runtime.providers.provider_runner import (
    ProviderBackedRunExecutor,
)
from craik.runtime.runners.role_dispatch import RoleDispatchError
from craik.runtime.store import LocalStore
from craik.runtime.work.case_files import ProjectNotFoundError, TaskNotFoundError
from craik.runtime.work.runs import TERMINAL_RUN_STATUSES, RunTransition, TaskRunManager

run_app = typer.Typer(help="Execute, inspect, and recover single-agent task runs.")


@run_app.command("execute")
def run_execute(
    task_id: Annotated[str, typer.Argument(help="Task id to execute.")],
    provider_id: Annotated[
        str,
        typer.Option(
            "--provider-id",
            help="Configured provider runner id. Use provider list to inspect options.",
        ),
    ] = "provider_openai",
    allow_fixture_action: Annotated[
        bool,
        typer.Option(
            "--allow-fixture-action/--no-allow-fixture-action",
            help=(
                "Grant the deterministic fixture shell action required by the MVP loop. "
                "This records a governed receipt; it does not execute arbitrary shell."
            ),
        ),
    ] = True,
    max_iterations: Annotated[
        int,
        typer.Option("--max-iterations", help="Maximum single-agent loop iterations."),
    ] = 5,
    role: Annotated[
        str | None,
        typer.Option("--role", help="Specialist role kind to dispatch for this run."),
    ] = None,
    role_runner: Annotated[
        str | None,
        typer.Option("--role-runner", help="Override the default runner for the selected role."),
    ] = None,
) -> None:
    """Execute a deterministic provider-backed MVP runner path for a task."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        grants = [fixture_shell_grant(task_id)] if allow_fixture_action else []
        result = ProviderBackedRunExecutor(store).execute(
            task_id=task_id,
            provider_id=provider_id,
            grants=grants,
            max_iterations=max_iterations,
            role_kind=role_kind(role) if role is not None else None,
            role_runner_id=role_runner,
        )
        payload = provider_run_payload(result)
    except (
        ModelProviderNotFoundError,
        ProjectNotFoundError,
        TaskNotFoundError,
        RoleDispatchError,
        ValueError,
    ) as error:
        raise typer.BadParameter(str(error)) from None
    finally:
        store.close()
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@run_app.command("list")
def run_list(
    task_id: Annotated[
        str | None,
        typer.Option("--task-id", help="Only include runs for this task id."),
    ] = None,
) -> None:
    """List persisted task runs."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        runs = store.list_task_runs()
    finally:
        store.close()
    if task_id is not None:
        runs = [run for run in runs if run.task_id == task_id]
    payload = [run.model_dump(mode="json", by_alias=True) for run in runs]
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@run_app.command("inspect")
def run_inspect(
    run_id_or_task_id: str,
    include_outputs: Annotated[
        bool,
        typer.Option(
            "--include-outputs/--no-include-outputs",
            help="Include full captured output payloads.",
        ),
    ] = False,
) -> None:
    """Inspect one persisted task run and linked local state."""
    _echo_run_inspection(run_id_or_task_id, include_outputs=include_outputs)


@run_app.command("show")
def run_show(
    run_id_or_task_id: str,
    include_outputs: Annotated[
        bool,
        typer.Option(
            "--include-outputs/--no-include-outputs",
            help="Include full captured output payloads.",
        ),
    ] = False,
) -> None:
    """Show one persisted task run and linked local state."""
    _echo_run_inspection(run_id_or_task_id, include_outputs=include_outputs)


@run_app.command("resume")
def run_resume(
    run_id_or_task_id: str,
    provider_id: Annotated[
        str | None,
        typer.Option(
            "--provider-id",
            help="Override the provider runner id recorded on the interrupted run.",
        ),
    ] = None,
    allow_fixture_action: Annotated[
        bool,
        typer.Option(
            "--allow-fixture-action/--no-allow-fixture-action",
            help="Grant the deterministic fixture shell action required by the MVP loop.",
        ),
    ] = True,
    max_iterations: Annotated[
        int,
        typer.Option("--max-iterations", help="Maximum single-agent loop iterations."),
    ] = 5,
) -> None:
    """Resume an interrupted provider-backed run from durable phase boundaries."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        run = _find_run(store, run_id_or_task_id)
        if run is None:
            raise typer.BadParameter(f"unknown run or task: {run_id_or_task_id}")
        if run.status != "interrupted":
            typer.echo(
                f"run {run.id} is {run.status}; only interrupted runs can be resumed",
                err=True,
            )
            raise typer.Exit(1)
        grants = [fixture_shell_grant(run.task_id)] if allow_fixture_action else []
        result = ProviderBackedRunExecutor(store).execute(
            task_id=run.task_id,
            provider_id=provider_id or run.runner_id,
            grants=grants,
            max_iterations=max_iterations,
            resume_run_id=run.id,
        )
        payload = provider_run_payload(result)
    except (
        ModelProviderNotFoundError,
        ProjectNotFoundError,
        TaskNotFoundError,
        ValueError,
    ) as error:
        raise typer.BadParameter(str(error)) from None
    finally:
        store.close()
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@run_app.command("cancel")
def run_cancel(
    run_id_or_task_id: str,
    reason: Annotated[
        str,
        typer.Option("--reason", help="Reason recorded on the interrupted run."),
    ] = "cancelled by operator",
) -> None:
    """Cancel a non-terminal run by persisting an interrupted stop state."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        run = _find_run(store, run_id_or_task_id)
        if run is None:
            raise typer.BadParameter(f"unknown run or task: {run_id_or_task_id}")
        if run.status in TERMINAL_RUN_STATUSES:
            typer.echo(
                f"run {run.id} is {run.status}; terminal runs cannot be cancelled",
                err=True,
            )
            raise typer.Exit(1)
        run = TaskRunManager(store).transition(
            run.id,
            RunTransition(
                status="interrupted",
                phase="stop",
                iteration=run.iteration,
                stop_reason=reason,
                at=datetime.now(UTC),
            ),
        )
        payload = {"cancelled": True, "run": run.model_dump(mode="json", by_alias=True)}
    finally:
        store.close()
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


def _echo_run_inspection(run_id_or_task_id: str, *, include_outputs: bool) -> None:
    store = LocalStore.from_env()
    try:
        store.initialize()
        run = _find_run(store, run_id_or_task_id)
        if run is None:
            raise typer.BadParameter(f"unknown run or task: {run_id_or_task_id}")
        payload = _run_inspection_payload(store, run, include_outputs=include_outputs)
    finally:
        store.close()
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@run_app.command("recover")
def run_recover(
    run_id_or_task_id: str,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Print recovery plan without writing new state."),
    ] = False,
    reason: Annotated[
        str | None,
        typer.Option("--reason", help="Reason for recovery."),
    ] = None,
) -> None:
    """Print a deterministic recovery plan for an interrupted run."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        run = _find_run(store, run_id_or_task_id)
        if run is None:
            raise typer.BadParameter(f"unknown run or task: {run_id_or_task_id}")
        if run.status != "interrupted":
            typer.echo(
                f"run {run.id} is {run.status}; only interrupted runs can be recovered",
                err=True,
            )
            raise typer.Exit(1)
        _operator_identity()
        payload = _run_recovery_payload(store, run, dry_run=dry_run, reason=reason)
    finally:
        store.close()
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@run_app.command("delta")
def run_delta(
    delta_id_or_run_id_or_task_id: str,
    json_output: Annotated[
        bool,
        typer.Option("--json/--view", help="Print JSON instead of the operator view."),
    ] = False,
) -> None:
    """Show what changed since the previous usable handoff or resume point."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        delta = _find_run_delta(store, delta_id_or_run_id_or_task_id)
        if delta is None:
            raise typer.BadParameter(
                f"unknown run delta, run, or task: {delta_id_or_run_id_or_task_id}"
            )
        _operator_identity()
        recovery_sessions = _recovery_sessions_for_delta(store, delta.id)
        payload = _run_delta_payload(delta, recovery_sessions)
    finally:
        store.close()
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    typer.echo("\n".join(payload["lines"]))


def _find_run(store: LocalStore, run_id_or_task_id: str) -> TaskRun | None:
    run = store.get_task_run(run_id_or_task_id)
    if run is not None:
        return run
    matches = [
        candidate for candidate in store.list_task_runs() if candidate.task_id == run_id_or_task_id
    ]
    return matches[-1] if matches else None


def _run_inspection_payload(
    store: LocalStore,
    run: TaskRun,
    *,
    include_outputs: bool,
) -> dict[str, Any]:
    outputs = [output for output in store.list_run_outputs() if output.run_id == run.id]
    receipts = [
        receipt for receipt in store.list_receipts() if receipt.id in _run_receipt_ids(run, outputs)
    ]
    proposals = [
        proposal
        for proposal in store.list_proposals()
        if proposal.id in {item for output in outputs for item in output.memory_proposal_ids}
    ]
    handoff = store.get_handoff(run.handoff_id) if run.handoff_id else None
    return {
        "run": run.model_dump(mode="json", by_alias=True),
        "status": run.status,
        "phase": run.phase,
        "stop_reason": run.stop_reason,
        "next_allowed_action": _next_allowed_action(run),
        "receipts": [receipt.model_dump(mode="json", by_alias=True) for receipt in receipts],
        "outputs": [
            _run_output_payload(output, include_outputs=include_outputs) for output in outputs
        ],
        "memory_proposals": [
            proposal.model_dump(mode="json", by_alias=True) for proposal in proposals
        ],
        "handoff": handoff.model_dump(mode="json", by_alias=True) if handoff else None,
        "runner_metadata": run.runner_metadata,
    }


def _run_recovery_payload(
    store: LocalStore,
    run: TaskRun,
    *,
    dry_run: bool,
    reason: str | None,
) -> dict[str, Any]:
    outputs = [output for output in store.list_run_outputs() if output.run_id == run.id]
    return {
        "run_id": run.id,
        "task_id": run.task_id,
        "recoverable": True,
        "dry_run": dry_run,
        "reason": reason,
        "resume_phase": "continue" if run.iteration < run.max_iterations else "stop",
        "last_phase": run.phase,
        "last_iteration": run.iteration,
        "next_allowed_action": _next_allowed_action(run),
        "required_checks": [
            "reload task run state",
            "re-check policy grants",
            "re-check intent-lock stop conditions",
            "verify max-iteration budget",
        ],
        "output_ids": [output.id for output in outputs],
    }


def _find_run_delta(store: LocalStore, delta_id_or_run_id_or_task_id: str) -> RunDelta | None:
    delta = store.get_run_delta(delta_id_or_run_id_or_task_id)
    if delta is not None:
        return delta
    run = _find_run(store, delta_id_or_run_id_or_task_id)
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


def _operator_identity() -> str:
    try:
        session = OperatorSessionStore.from_env().get()
    except OperatorSessionNotFoundError:
        raise typer.BadParameter("active operator session required; run craik auth login") from None
    return session.subject


def _recovery_sessions_for_delta(
    store: LocalStore,
    delta_id: str,
) -> list[RecoverySession]:
    return [
        session
        for session in store.list_recovery_sessions()
        if session.run_delta_id == delta_id
    ]


def _run_delta_payload(
    delta: RunDelta,
    recovery_sessions: list[RecoverySession],
) -> dict[str, Any]:
    snapshot = RunDeltaSnapshot(delta=delta, recovery_sessions=recovery_sessions)
    return {
        "schema": "craik.run_delta_view",
        "version": "0.1.0",
        "delta": delta.model_dump(mode="json", by_alias=True),
        "recovery_sessions": [
            session.model_dump(mode="json", by_alias=True) for session in recovery_sessions
        ],
        "lines": format_run_delta_view(snapshot),
    }


def _run_output_payload(output: Any, *, include_outputs: bool) -> dict[str, Any]:
    payload = output.model_dump(mode="json", by_alias=True)
    if include_outputs:
        return dict(payload)
    return {
        "id": payload["id"],
        "run_id": payload["run_id"],
        "step_result_id": payload["step_result_id"],
        "phase": payload["phase"],
        "summary": payload["summary"],
        "diagnostics": payload["diagnostics"],
        "receipt_ids": payload["receipt_ids"],
        "memory_proposal_ids": payload["memory_proposal_ids"],
        "artifacts": payload["artifacts"],
        "redacted": payload["redacted"],
    }


def _run_receipt_ids(run: TaskRun, outputs: list[Any]) -> set[str]:
    output_receipt_ids = [receipt for output in outputs for receipt in output.receipt_ids]
    return {*run.receipt_ids, *output_receipt_ids}


def _next_allowed_action(run: TaskRun) -> str:
    if run.status == "interrupted":
        return "recover from the last safe boundary"
    if run.status == "blocked":
        return "resolve the blocking condition before recovery"
    if run.status == "failed":
        return "inspect diagnostics before deciding whether to retry"
    if run.status == "completed":
        return "review handoff, receipts, and memory proposals"
    return "continue within policy and iteration limits"
