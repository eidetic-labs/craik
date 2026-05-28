"""Run command group for the Craik CLI."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, NoReturn

import click
import typer
from typer.core import TyperGroup

from craik.cli_operator_auth import operator_identity_or_fail
from craik.cli_output import emit_command_result
from craik.cli_run_support import (
    fixture_shell_grant,
    next_allowed_action,
    provider_run_payload,
    role_kind,
)
from craik.cli_run_views import run_inspection_payload
from craik.contracts.models import (
    RecoverySession,
    RunDelta,
    TaskRun,
)
from craik.runtime.backend.session import execute_prompt
from craik.runtime.companions.operator_views import (
    RunDeltaSnapshot,
    format_run_delta_view,
)
from craik.runtime.contract import CommandResult, craik_command
from craik.runtime.providers.model_providers import ModelProviderNotFoundError
from craik.runtime.providers.provider_runner import (
    ProviderBackedRunExecutor,
)
from craik.runtime.runners.role_dispatch import RoleDispatchError
from craik.runtime.store import LocalStore
from craik.runtime.work.case_files import ProjectNotFoundError, TaskNotFoundError
from craik.runtime.work.runs import TERMINAL_RUN_STATUSES, RunTransition, TaskRunManager


class RunPromptFallbackGroup(TyperGroup):
    """Treat unknown `craik run ...` subcommands as direct prompt text."""

    def resolve_command(
        self,
        ctx: click.Context,
        args: list[str],
    ) -> tuple[str | None, click.Command | None, list[str]]:
        try:
            return super().resolve_command(ctx, args)
        except click.UsageError:
            if args and not args[0].startswith("-"):
                command = self.get_command(ctx, "prompt")
                if command is not None:
                    return "prompt", command, args
            raise


run_app = typer.Typer(
    cls=RunPromptFallbackGroup,
    help=(
        "Execute, inspect, and recover single-agent task runs. "
        "Use `craik run \"prompt\"` for a direct audited prompt run."
    ),
)


@run_app.command("prompt")
@craik_command(payload_shape="card")
def run_prompt(
    prompt: Annotated[
        list[str],
        typer.Argument(help="Prompt text to execute as an audited run."),
    ],
) -> CommandResult:
    """Execute a raw prompt through the audited Gateway run path."""
    prompt_text = " ".join(prompt).strip()
    if not prompt_text:
        raise typer.BadParameter("run prompt requires prompt text.")
    try:
        payload = execute_prompt(prompt_text, source="cli").payload_with_events()
    except (
        ModelProviderNotFoundError,
        ProjectNotFoundError,
        TaskNotFoundError,
        ValueError,
    ) as error:
        raise typer.BadParameter(str(error)) from None
    result = CommandResult(payload=payload, shape="card")
    emit_command_result(result)
    return result


@run_app.command("execute")
@craik_command(payload_shape="card")
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
) -> CommandResult:
    """Execute a deterministic provider-backed MVP runner path for a task."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        grants = [fixture_shell_grant(task_id)] if allow_fixture_action else []
        execution_result = ProviderBackedRunExecutor(store).execute(
            task_id=task_id,
            provider_id=provider_id,
            grants=grants,
            max_iterations=max_iterations,
            role_kind=role_kind(role) if role is not None else None,
            role_runner_id=role_runner,
        )
        payload = provider_run_payload(execution_result)
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
    result = CommandResult(payload=payload, shape="card")
    emit_command_result(result)
    return result


@run_app.command("list")
@craik_command(payload_shape="card_list")
def run_list(
    task_id: Annotated[
        str | None,
        typer.Option("--task-id", help="Only include runs for this task id."),
    ] = None,
) -> CommandResult:
    """List persisted task runs."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        runs = store.list_task_runs()
    finally:
        store.close()
    if task_id is not None:
        runs = [run for run in runs if run.task_id == task_id]
    payload = [run.model_dump(mode="json", by_alias=True) for run in runs]
    result = CommandResult(payload=payload, shape="card_list")
    emit_command_result(result)
    return result


@run_app.command("inspect")
@craik_command(payload_shape="card")
def run_inspect(
    run_id_or_task_id: str,
    include_outputs: Annotated[
        bool,
        typer.Option(
            "--include-outputs/--no-include-outputs",
            help="Include full captured output payloads.",
        ),
    ] = False,
) -> CommandResult:
    """Inspect one persisted task run and linked local state."""
    operator_identity_or_fail()
    result = _run_inspection_result(run_id_or_task_id, include_outputs=include_outputs)
    emit_command_result(result)
    return result


@run_app.command("show")
@craik_command(payload_shape="card")
def run_show(
    run_id_or_task_id: str,
    include_outputs: Annotated[
        bool,
        typer.Option(
            "--include-outputs/--no-include-outputs",
            help="Include full captured output payloads.",
        ),
    ] = False,
) -> CommandResult:
    """Show one persisted task run and linked local state."""
    operator_identity_or_fail()
    result = _run_inspection_result(run_id_or_task_id, include_outputs=include_outputs)
    emit_command_result(result)
    return result


@run_app.command("resume")
@craik_command(payload_shape="card")
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
) -> CommandResult:
    """Resume an interrupted provider-backed run from durable phase boundaries."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        run = _find_run(store, run_id_or_task_id)
        if run is None:
            raise typer.BadParameter(f"unknown run or task: {run_id_or_task_id}")
        if run.status != "interrupted":
            _reject_run_state(f"run {run.id} is {run.status}; only interrupted runs can be resumed")
        grants = [fixture_shell_grant(run.task_id)] if allow_fixture_action else []
        execution_result = ProviderBackedRunExecutor(store).execute(
            task_id=run.task_id,
            provider_id=provider_id or run.runner_id,
            grants=grants,
            max_iterations=max_iterations,
            resume_run_id=run.id,
        )
        payload = provider_run_payload(execution_result)
    except (
        ModelProviderNotFoundError,
        ProjectNotFoundError,
        TaskNotFoundError,
        ValueError,
    ) as error:
        raise typer.BadParameter(str(error)) from None
    finally:
        store.close()
    result = CommandResult(payload=payload, shape="card")
    emit_command_result(result)
    return result


@run_app.command("cancel")
@craik_command(payload_shape="card")
def run_cancel(
    run_id_or_task_id: str,
    reason: Annotated[
        str,
        typer.Option("--reason", help="Reason recorded on the interrupted run."),
    ] = "cancelled by operator",
) -> CommandResult:
    """Cancel a non-terminal run by persisting an interrupted stop state."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        run = _find_run(store, run_id_or_task_id)
        if run is None:
            raise typer.BadParameter(f"unknown run or task: {run_id_or_task_id}")
        if run.status in TERMINAL_RUN_STATUSES:
            _reject_run_state(f"run {run.id} is {run.status}; terminal runs cannot be cancelled")
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
    result = CommandResult(payload=payload, shape="card")
    emit_command_result(result)
    return result


def _run_inspection_result(run_id_or_task_id: str, *, include_outputs: bool) -> CommandResult:
    store = LocalStore.from_env()
    try:
        store.initialize()
        run = _find_run(store, run_id_or_task_id)
        if run is None:
            raise typer.BadParameter(f"unknown run or task: {run_id_or_task_id}")
        payload = run_inspection_payload(store, run, include_outputs=include_outputs)
    finally:
        store.close()
    return CommandResult(payload=payload, shape="card")


def _reject_run_state(message: str) -> NoReturn:
    typer.echo(message, err=True)
    raise typer.Exit(1)


@run_app.command("recover")
@craik_command(payload_shape="card")
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
) -> CommandResult:
    """Print a deterministic recovery plan for an interrupted run."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        run = _find_run(store, run_id_or_task_id)
        if run is None:
            raise typer.BadParameter(f"unknown run or task: {run_id_or_task_id}")
        if run.status != "interrupted":
            _reject_run_state(
                f"run {run.id} is {run.status}; only interrupted runs can be recovered"
            )
        payload = _run_recovery_payload(store, run, dry_run=dry_run, reason=reason)
    finally:
        store.close()
    result = CommandResult(payload=payload, shape="card")
    emit_command_result(result)
    return result


@run_app.command("delta")
@craik_command(payload_shape="card")
def run_delta(
    delta_id_or_run_id_or_task_id: str,
    json_output: Annotated[
        bool,
        typer.Option("--json/--view", help="Print JSON instead of the operator view."),
    ] = False,
) -> CommandResult:
    """Show what changed since the previous usable handoff or resume point."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        delta = _find_run_delta(store, delta_id_or_run_id_or_task_id)
        if delta is None:
            raise typer.BadParameter(
                f"unknown run delta, run, or task: {delta_id_or_run_id_or_task_id}"
            )
        recovery_sessions = _recovery_sessions_for_delta(store, delta.id)
        payload = _run_delta_payload(delta, recovery_sessions)
    finally:
        store.close()
    text = None if json_output else "\n".join(payload["lines"])
    result = CommandResult(payload=payload, shape="card", text=text)
    emit_command_result(result)
    return result


def _find_run(store: LocalStore, run_id_or_task_id: str) -> TaskRun | None:
    run = store.get_task_run(run_id_or_task_id)
    if run is not None:
        return run
    matches = [
        candidate for candidate in store.list_task_runs() if candidate.task_id == run_id_or_task_id
    ]
    return matches[-1] if matches else None


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
        "next_allowed_action": next_allowed_action(run),
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
