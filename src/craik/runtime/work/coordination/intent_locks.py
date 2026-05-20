"""Concurrent run coordination for intent-locked work."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from craik.contracts.models import (
    CapabilityReceipt,
    IntentLock,
    PolicyEnvelope,
    ReceiptResult,
    TaskRun,
)
from craik.runtime.store import LocalStore
from craik.runtime.work.runs import TERMINAL_RUN_STATUSES


@dataclass(frozen=True)
class IntentLockCoordinationDecision:
    """Outcome of checking one run against active intent locks."""

    allowed: bool
    reason: str
    conflicting_run_ids: tuple[str, ...] = ()
    conflicting_intent_lock_ids: tuple[str, ...] = ()


def check_intent_lock_coordination(
    store: LocalStore,
    *,
    run: TaskRun,
    intent_lock: IntentLock | None,
) -> IntentLockCoordinationDecision:
    """Return whether a run can proceed beside other active runs."""
    if intent_lock is None:
        return IntentLockCoordinationDecision(
            allowed=True,
            reason="run has no intent lock; coordination check skipped",
        )

    project_id = _project_id_for_run(store, run)
    if project_id is None:
        return IntentLockCoordinationDecision(
            allowed=True,
            reason="run project is unknown; coordination check skipped",
        )

    conflicting_runs: list[TaskRun] = []
    conflicting_locks: list[IntentLock] = []
    for candidate in store.list_task_runs():
        if candidate.id == run.id or candidate.status in TERMINAL_RUN_STATUSES:
            continue
        if _project_id_for_run(store, candidate) != project_id:
            continue
        candidate_lock = _intent_lock_for_run(store, candidate)
        if candidate_lock is None:
            continue
        if _scopes_overlap(intent_lock.in_scope, candidate_lock.in_scope):
            conflicting_runs.append(candidate)
            conflicting_locks.append(candidate_lock)

    if not conflicting_runs:
        return IntentLockCoordinationDecision(
            allowed=True,
            reason="no conflicting active intent locks",
        )

    return IntentLockCoordinationDecision(
        allowed=False,
        reason="active run already holds an overlapping intent lock",
        conflicting_run_ids=tuple(run.id for run in conflicting_runs),
        conflicting_intent_lock_ids=tuple(lock.id for lock in conflicting_locks),
    )


def intent_lock_coordination_receipt(
    *,
    policy: PolicyEnvelope,
    run: TaskRun,
    intent_lock: IntentLock | None,
    decision: IntentLockCoordinationDecision,
    actor: str,
    phase: str,
) -> CapabilityReceipt:
    """Build a denial receipt for a concurrent intent-lock conflict."""
    target = intent_lock.id if intent_lock is not None else run.id
    return CapabilityReceipt(
        id=f"receipt_{run.id}_intent_lock_coordination",
        task_id=run.task_id,
        actor=actor,
        capability="intent_lock.coordinate",
        target=target,
        policy_profile=policy.profile,
        fail_open=policy.fail_open,
        reason=decision.reason,
        result=ReceiptResult(
            status="denied",
            summary=decision.reason,
            metadata={
                "run_id": run.id,
                "phase": phase,
                "intent_lock_id": intent_lock.id if intent_lock else None,
                "conflicting_run_ids": list(decision.conflicting_run_ids),
                "conflicting_intent_lock_ids": list(decision.conflicting_intent_lock_ids),
            },
        ),
        redacted=True,
        auth_profile_id=run.auth_profile_id,
        auth_identity_hash=run.auth_identity_hash,
        operator_subject=run.operator_subject,
        operator_issuer=run.operator_issuer,
        created_at=datetime.now(UTC),
    )


def record_intent_lock_coordination_denial(
    store: LocalStore,
    *,
    policy: PolicyEnvelope,
    run: TaskRun,
    intent_lock: IntentLock | None,
    actor: str,
    phase: str,
) -> CapabilityReceipt | None:
    """Persist a coordination denial receipt when another active run conflicts."""
    decision = check_intent_lock_coordination(
        store,
        run=run,
        intent_lock=intent_lock,
    )
    if decision.allowed:
        return None
    receipt = intent_lock_coordination_receipt(
        policy=policy,
        run=run,
        intent_lock=intent_lock,
        decision=decision,
        actor=actor,
        phase=phase,
    )
    return store.put_receipt(receipt)


def _project_id_for_run(store: LocalStore, run: TaskRun) -> str | None:
    task = store.get_task(run.task_id)
    return task.project_id if task is not None else None


def _intent_lock_for_run(store: LocalStore, run: TaskRun) -> IntentLock | None:
    if run.intent_lock_id is None:
        return None
    return store.get_intent_lock(run.intent_lock_id)


def _scopes_overlap(left: list[str], right: list[str]) -> bool:
    if not left or not right:
        return True
    return any(_scope_item_overlaps(a, b) for a in left for b in right)


def _scope_item_overlaps(left: str, right: str) -> bool:
    left = left.strip()
    right = right.strip()
    if not left or not right:
        return True
    if left == right:
        return True
    if left.endswith("/") and right.startswith(left):
        return True
    return right.endswith("/") and left.startswith(right)
