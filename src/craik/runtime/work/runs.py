"""Task run state helpers for governed single-agent execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from craik.contracts.models import RunnerMode, TaskRun, TaskRunPhase, TaskRunStatus
from craik.runtime.store import LocalStore

TERMINAL_RUN_STATUSES: frozenset[TaskRunStatus] = frozenset(
    {"completed", "blocked", "failed", "interrupted"}
)


class TaskRunError(RuntimeError):
    """Base error for task run state failures."""


class TaskRunNotFoundError(TaskRunError):
    """Raised when a task run cannot be found."""


class TaskRunTransitionError(TaskRunError):
    """Raised when a run transition would make state inconsistent."""


class TaskRunIterationLimitError(TaskRunTransitionError):
    """Raised when a transition exceeds a run iteration limit."""


@dataclass(frozen=True)
class RunTransition:
    """Requested run state mutation."""

    status: TaskRunStatus | None = None
    phase: TaskRunPhase | None = None
    iteration: int | None = None
    receipt_id: str | None = None
    handoff_id: str | None = None
    stop_reason: str | None = None
    completed_step_key: str | None = None
    last_step_key: str | None = None
    provider_tokens_used_delta: int = 0
    auth_profile_id: str | None = None
    auth_identity_hash: str | None = None
    operator_subject: str | None = None
    operator_issuer: str | None = None
    at: datetime | None = None


class TaskRunManager:
    """Create and update durable task run state."""

    def __init__(self, store: LocalStore) -> None:
        self.store = store

    def create(
        self,
        *,
        task_id: str,
        case_file_id: str,
        policy_envelope_id: str,
        runner_id: str,
        runner_mode: RunnerMode,
        intent_lock_id: str | None = None,
        run_id: str | None = None,
        max_iterations: int = 5,
        wall_clock_budget_seconds: float | None = None,
        provider_token_budget: int | None = None,
        runner_metadata: list[dict[str, object]] | None = None,
        auth_profile_id: str | None = None,
        auth_identity_hash: str | None = None,
        operator_subject: str | None = None,
        operator_issuer: str | None = None,
        source_handoff_id: str | None = None,
        source_task_id: str | None = None,
        source_run_id: str | None = None,
        role_id: str | None = None,
        role_kind: str | None = None,
        receipt_ids: list[str] | None = None,
        created_at: datetime | None = None,
    ) -> TaskRun:
        now = created_at or datetime.now(UTC)
        run = TaskRun(
            id=run_id or task_run_id(task_id),
            task_id=task_id,
            case_file_id=case_file_id,
            policy_envelope_id=policy_envelope_id,
            intent_lock_id=intent_lock_id,
            runner_id=runner_id,
            runner_mode=runner_mode,
            max_iterations=max_iterations,
            wall_clock_budget_seconds=wall_clock_budget_seconds,
            provider_token_budget=provider_token_budget,
            provider_token_budget_remaining=provider_token_budget,
            started_at=now,
            phase_started_at=now,
            updated_at=now,
            runner_metadata=list(runner_metadata or []),
            receipt_ids=list(receipt_ids or []),
            auth_profile_id=auth_profile_id,
            auth_identity_hash=auth_identity_hash,
            operator_subject=operator_subject,
            operator_issuer=operator_issuer,
            source_handoff_id=source_handoff_id,
            source_task_id=source_task_id,
            source_run_id=source_run_id,
            role_id=role_id,
            role_kind=role_kind,
        )
        self.store.put_task_run(run)
        return run

    def get(self, run_id: str) -> TaskRun | None:
        return self.store.get_task_run(run_id)

    def require(self, run_id: str) -> TaskRun:
        run = self.get(run_id)
        if run is None:
            raise TaskRunNotFoundError(f"unknown task run: {run_id}")
        return run

    def transition(self, run_id: str, transition: RunTransition) -> TaskRun:
        run = self.require(run_id)
        if run.status in TERMINAL_RUN_STATUSES:
            raise TaskRunTransitionError(f"task run is already terminal: {run_id}")

        now = transition.at or datetime.now(UTC)
        status = transition.status or run.status
        phase = transition.phase or run.phase
        iteration = transition.iteration if transition.iteration is not None else run.iteration

        if iteration > run.max_iterations:
            message = f"task run iteration {iteration} exceeds max {run.max_iterations}"
            raise TaskRunIterationLimitError(message)

        receipt_ids = list(run.receipt_ids)
        if transition.receipt_id is not None and transition.receipt_id not in receipt_ids:
            receipt_ids.append(transition.receipt_id)
        completed_step_keys = list(run.completed_step_keys)
        if (
            transition.completed_step_key is not None
            and transition.completed_step_key not in completed_step_keys
        ):
            completed_step_keys.append(transition.completed_step_key)

        provider_tokens_used = run.provider_tokens_used + max(
            transition.provider_tokens_used_delta,
            0,
        )
        provider_token_budget_remaining = (
            None
            if run.provider_token_budget is None
            else max(run.provider_token_budget - provider_tokens_used, 0)
        )

        ended_at = now if status in TERMINAL_RUN_STATUSES else run.ended_at
        phase_started_at = now if phase != run.phase else run.phase_started_at
        updated = run.model_copy(
            update={
                "status": status,
                "phase": phase,
                "iteration": iteration,
                "phase_started_at": phase_started_at,
                "updated_at": now,
                "ended_at": ended_at,
                "stop_reason": transition.stop_reason or run.stop_reason,
                "receipt_ids": receipt_ids,
                "handoff_id": transition.handoff_id or run.handoff_id,
                "completed_step_keys": completed_step_keys,
                "last_step_key": transition.last_step_key or run.last_step_key,
                "provider_tokens_used": provider_tokens_used,
                "provider_token_budget_remaining": provider_token_budget_remaining,
                "auth_profile_id": transition.auth_profile_id or run.auth_profile_id,
                "auth_identity_hash": transition.auth_identity_hash or run.auth_identity_hash,
                "operator_subject": transition.operator_subject or run.operator_subject,
                "operator_issuer": transition.operator_issuer or run.operator_issuer,
            }
        )
        self.store.put_task_run(updated)
        return updated

    def prepare_resume(
        self,
        run_id: str,
        *,
        max_iterations: int | None = None,
        at: datetime | None = None,
    ) -> TaskRun:
        """Reopen an interrupted run so execution can continue from durable state."""
        run = self.require(run_id)
        if run.status != "interrupted":
            raise TaskRunTransitionError(f"task run is not interrupted: {run_id}")

        now = at or datetime.now(UTC)
        updated = run.model_copy(
            update={
                "status": "running",
                "ended_at": None,
                "stop_reason": None,
                "max_iterations": max(max_iterations or run.max_iterations, run.max_iterations),
                "phase_started_at": now,
                "updated_at": now,
            }
        )
        self.store.put_task_run(updated)
        return updated


def task_run_id(task_id: str) -> str:
    """Return the deterministic default run id for a task."""
    return f"run_{task_id.removeprefix('task_')}"
