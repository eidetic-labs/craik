"""Human delegation and scope-change lifecycle helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from craik.contracts.models import (
    CapabilityReceipt,
    HumanDelegationKind,
    HumanDelegationPoint,
    PolicyEnvelope,
    ReceiptResult,
    ReceiptStatus,
    ScopeChangeRequest,
    ScopeChangeResult,
    TaskRun,
)
from craik.runtime.store import LocalStore
from craik.runtime.work.coordination.live_graph import WorkGraphCoordinator
from craik.runtime.work.runs import TERMINAL_RUN_STATUSES, RunTransition, TaskRunManager

DelegationResolution = Literal["accepted", "rejected", "cancelled"]


@dataclass(frozen=True)
class RunDelegationPause:
    """A run paused for human input."""

    run: TaskRun
    delegation: HumanDelegationPoint
    receipt: CapabilityReceipt


@dataclass(frozen=True)
class RunDelegationResolution:
    """A resolved delegation and its linked run state."""

    delegation: HumanDelegationPoint
    receipt: CapabilityReceipt
    run: TaskRun | None = None


class HumanDelegationManager:
    """Persist human delegation points and scope-change decisions."""

    def __init__(self, store: LocalStore) -> None:
        self._store = store

    def open_delegation(self, delegation: HumanDelegationPoint) -> HumanDelegationPoint:
        """Persist an open human delegation point."""
        self._store.put_human_delegation(delegation)
        WorkGraphCoordinator(self._store).record_artifact(
            task_id=delegation.task_id,
            artifact_type="delegation",
            artifact_id=delegation.id,
            receipt_ids=delegation.receipt_ids,
            metadata={"kind": delegation.kind, "status": delegation.status},
        )
        return delegation

    def pause_run_for_delegation(
        self,
        *,
        policy: PolicyEnvelope,
        run_id: str,
        kind: HumanDelegationKind,
        summary: str,
        requested_decision: str,
        requested_by: str,
        owner: str | None = None,
        role_id: str | None = None,
    ) -> RunDelegationPause:
        """Interrupt a non-terminal run and open a receipted human delegation."""
        run = self._store.get_task_run(run_id)
        if run is None:
            raise HumanDelegationNotFoundError(f"unknown task run: {run_id}")
        if run.status in TERMINAL_RUN_STATUSES:
            raise HumanDelegationStateError(f"task run is already terminal: {run_id}")
        delegation_id = f"delegation_{run.id}"
        receipt = self._store.put_receipt(
            _delegation_receipt(
                policy=policy,
                task_id=run.task_id,
                capability="human_delegation.open",
                target=delegation_id,
                status="blocked",
                summary=summary,
                metadata={
                    "run_id": run.id,
                    "delegation_id": delegation_id,
                    "kind": kind,
                    "requested_decision": requested_decision,
                    "owner": owner,
                },
            )
        )
        delegation = HumanDelegationPoint(
            id=delegation_id,
            task_id=run.task_id,
            kind=kind,
            summary=summary,
            requested_decision=requested_decision,
            requested_by=requested_by,
            owner=owner,
            run_id=run.id,
            role_id=role_id,
            intent_lock_id=run.intent_lock_id,
            policy_envelope_id=policy.id,
            receipt_ids=[receipt.id],
            created_at=datetime.now(UTC),
        )
        self.open_delegation(delegation)
        paused = TaskRunManager(self._store).transition(
            run.id,
            RunTransition(
                status="interrupted",
                phase="stop",
                iteration=run.iteration,
                receipt_id=receipt.id,
                stop_reason=f"human delegation pending: {delegation.id}",
                at=datetime.now(UTC),
            ),
        )
        return RunDelegationPause(run=paused, delegation=delegation, receipt=receipt)

    def resolve_delegation(self, delegation_id: str, resolution: str) -> HumanDelegationPoint:
        """Resolve an open delegation point with human-provided resolution text."""
        delegation = self._store.get_human_delegation(delegation_id)
        if delegation is None:
            raise HumanDelegationNotFoundError(f"unknown human delegation: {delegation_id}")
        resolved = delegation.model_copy(
            update={
                "status": "resolved",
                "resolution": resolution,
                "resolved_at": datetime.now(UTC),
            }
        )
        self._store.put_human_delegation(resolved)
        return resolved

    def resolve_run_delegation(
        self,
        *,
        policy: PolicyEnvelope,
        delegation_id: str,
        resolution: str,
        outcome: DelegationResolution,
    ) -> RunDelegationResolution:
        """Resolve or cancel a run delegation and link the decision receipt to the run."""
        delegation = self._store.get_human_delegation(delegation_id)
        if delegation is None:
            raise HumanDelegationNotFoundError(f"unknown human delegation: {delegation_id}")
        if delegation.status != "open":
            message = f"human delegation is {delegation.status}: {delegation_id}"
            raise HumanDelegationStateError(message)
        receipt = self._store.put_receipt(
            _delegation_receipt(
                policy=policy,
                task_id=delegation.task_id,
                capability="human_delegation.resolve",
                target=delegation.id,
                status="passed" if outcome == "accepted" else "denied",
                summary=resolution,
                metadata={
                    "delegation_id": delegation.id,
                    "run_id": delegation.run_id,
                    "outcome": outcome,
                },
            )
        )
        status = "cancelled" if outcome == "cancelled" else "resolved"
        updated = delegation.model_copy(
            update={
                "status": status,
                "resolution": resolution if status == "resolved" else delegation.resolution,
                "resolved_at": (
                    datetime.now(UTC) if status == "resolved" else delegation.resolved_at
                ),
                "receipt_ids": [*delegation.receipt_ids, receipt.id],
            }
        )
        self._store.put_human_delegation(updated)
        WorkGraphCoordinator(self._store).record_artifact(
            task_id=delegation.task_id,
            artifact_type="delegation",
            artifact_id=delegation.id,
            receipt_ids=[receipt.id],
            metadata={"status": updated.status, "outcome": outcome},
        )
        run = _append_receipt_to_run(self._store, delegation.run_id, receipt.id)
        return RunDelegationResolution(delegation=updated, receipt=receipt, run=run)

    def request_scope_change(self, request: ScopeChangeRequest) -> ScopeChangeRequest:
        """Persist a pending scope-change request."""
        self._store.put_scope_change_request(request)
        WorkGraphCoordinator(self._store).record_artifact(
            task_id=request.task_id,
            artifact_type="scope_change_request",
            artifact_id=request.id,
            receipt_ids=request.receipt_ids,
            metadata={"status": request.status, "intent_lock_id": request.intent_lock_id},
        )
        return request

    def decide_scope_change(self, result: ScopeChangeResult) -> ScopeChangeResult:
        """Persist a human scope-change decision and update the request status."""
        self._store.put_scope_change_result(result)
        WorkGraphCoordinator(self._store).record_artifact(
            task_id=result.task_id,
            artifact_type="scope_change_result",
            artifact_id=result.id,
            receipt_ids=result.receipt_ids,
            source_node=f"scope_change_request:{result.scope_change_request_id}",
            relation="depends_on",
            metadata={"decision": result.decision},
        )
        request = self._store.get_scope_change_request(result.scope_change_request_id)
        if request is not None:
            self._store.put_scope_change_request(
                request.model_copy(update={"status": result.decision})
            )
        return result


class HumanDelegationNotFoundError(RuntimeError):
    """Raised when a human delegation point cannot be found."""


class HumanDelegationStateError(RuntimeError):
    """Raised when a delegation or run cannot transition."""


def must_stop_for_human_decision(
    delegations: list[HumanDelegationPoint],
    scope_changes: list[ScopeChangeRequest],
) -> bool:
    """Return true when open human input should stop autonomous agent work."""
    return any(delegation.status == "open" for delegation in delegations) or any(
        request.status == "pending" for request in scope_changes
    )


def _delegation_receipt(
    *,
    policy: PolicyEnvelope,
    task_id: str,
    capability: str,
    target: str,
    status: ReceiptStatus,
    summary: str,
    metadata: dict[str, object],
) -> CapabilityReceipt:
    return CapabilityReceipt(
        id=f"receipt_{target}_{capability.rsplit('.', maxsplit=1)[-1]}",
        task_id=task_id,
        actor="craik:human-delegation",
        capability=capability,
        target=target,
        policy_profile=policy.profile,
        fail_open=policy.fail_open,
        reason=summary,
        result=ReceiptResult(status=status, summary=summary, metadata=metadata),
        redacted=True,
        created_at=datetime.now(UTC),
    )


def _append_receipt_to_run(
    store: LocalStore,
    run_id: str | None,
    receipt_id: str,
) -> TaskRun | None:
    if run_id is None:
        return None
    run = store.get_task_run(run_id)
    if run is None or receipt_id in run.receipt_ids:
        return run
    updated = run.model_copy(update={"receipt_ids": [*run.receipt_ids, receipt_id]})
    store.put_task_run(updated)
    return updated
