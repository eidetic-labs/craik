"""Consume a completed handoff into a new governed task/run."""

from __future__ import annotations

from dataclasses import dataclass

from craik.contracts.models import (
    CaseFile,
    Handoff,
    IntentLock,
    Priority,
    RunnerMode,
    TaskMode,
    TaskRequest,
    TaskRun,
)
from craik.runtime.policy.intent_locks import IntentLockManager
from craik.runtime.store import LocalStore
from craik.runtime.work.case_files import CaseFileAssembler
from craik.runtime.work.handoffs import HandoffContextError, HandoffWriter
from craik.runtime.work.runs import TaskRunManager
from craik.runtime.work.tasks import create_task


class HandoffConsumptionError(RuntimeError):
    """Raised when a handoff cannot be consumed into follow-up work."""


@dataclass(frozen=True)
class HandoffConsumptionResult:
    """State produced while consuming one source handoff."""

    source_handoff: Handoff
    task: TaskRequest
    intent_lock: IntentLock
    case_file: CaseFile
    run: TaskRun


def consume_handoff(
    store: LocalStore,
    *,
    handoff_id_or_task_id: str,
    title: str | None = None,
    objective: str | None = None,
    requested_by: str = "user:local",
    priority: Priority = "normal",
    mode: TaskMode = "implement",
    auth_profile_id: str,
    operator_subject: str,
    operator_issuer: str,
    runner_id: str = "fixture",
    runner_mode: RunnerMode = "fixture",
    max_iterations: int = 5,
) -> HandoffConsumptionResult:
    """Create a new task, case file, and pending run from a source handoff."""
    if not auth_profile_id:
        raise HandoffConsumptionError("handoff consumption requires --auth-profile-id")
    if not operator_subject or not operator_issuer:
        raise HandoffConsumptionError(
            "handoff consumption requires --operator-subject and --operator-issuer"
        )

    try:
        handoff = HandoffWriter(store).require(handoff_id_or_task_id)
    except HandoffContextError as error:
        raise HandoffConsumptionError(str(error)) from None

    if store.get_project(handoff.project_id) is None:
        raise HandoffConsumptionError(f"unknown project for handoff: {handoff.project_id}")

    source_run_id = _source_run_id(store, handoff.id)
    task = create_task(
        store,
        title=title or f"Continue from {handoff.id}",
        objective=objective or _default_objective(handoff),
        project_id=handoff.project_id,
        requested_by=requested_by,
        priority=priority,
        mode=mode,
        auth_profile_id=auth_profile_id,
        operator_subject=operator_subject,
        operator_issuer=operator_issuer,
        source_handoff_id=handoff.id,
        source_task_id=handoff.task_id,
        source_run_id=source_run_id,
        constraints=_consumption_constraints(handoff),
        expected_outputs=["case_file", "run", "handoff"],
    )
    intent_lock = IntentLockManager(store).create_for_task(
        task,
        accepted_interpretation=f"Consume source handoff {handoff.id} into follow-up work.",
        in_scope=[
            f"Continue from handoff {handoff.id}.",
            *handoff.next_steps,
        ],
        out_of_scope=[
            "Implicitly inherit the producer agent credential or operator identity.",
        ],
        allowed_autonomy=[
            "Assemble governed case context before execution.",
            "Start a pending run under the explicitly assigned consumer identity.",
        ],
        stop_conditions=[
            "Source handoff is missing, invalid, or not linked to a registered project.",
        ],
        scope_change_rules=[
            "Create a sibling task or scope-change request instead of silently expanding scope.",
        ],
    )
    case_file = CaseFileAssembler(store).build(task.id)
    run = TaskRunManager(store).create(
        task_id=task.id,
        case_file_id=case_file.id,
        policy_envelope_id=case_file.policy_envelope_id,
        intent_lock_id=intent_lock.id,
        runner_id=runner_id,
        runner_mode=runner_mode,
        max_iterations=max_iterations,
        auth_profile_id=auth_profile_id,
        operator_subject=operator_subject,
        operator_issuer=operator_issuer,
        source_handoff_id=handoff.id,
        source_task_id=handoff.task_id,
        source_run_id=source_run_id,
    )
    return HandoffConsumptionResult(
        source_handoff=handoff,
        task=task,
        intent_lock=intent_lock,
        case_file=case_file,
        run=run,
    )


def _source_run_id(store: LocalStore, handoff_id: str) -> str | None:
    for run in store.list_task_runs():
        if run.handoff_id == handoff_id:
            return run.id
    return None


def _default_objective(handoff: Handoff) -> str:
    if handoff.next_steps:
        return f"Continue from {handoff.id}: {handoff.next_steps[0]}"
    return f"Continue from {handoff.id}: {handoff.summary}"


def _consumption_constraints(handoff: Handoff) -> list[str]:
    constraints = [
        f"Source handoff: {handoff.id}",
        f"Source task: {handoff.task_id}",
        "Use the explicitly assigned consumer credential and operator identity.",
    ]
    if handoff.next_steps:
        constraints.extend(f"Source next step: {step}" for step in handoff.next_steps)
    if handoff.risks:
        constraints.extend(f"Source risk: {risk}" for risk in handoff.risks)
    return constraints
