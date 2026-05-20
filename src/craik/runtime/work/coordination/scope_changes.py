"""Scope-change protocol helpers for governed multi-agent work."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from craik.contracts.models import (
    CapabilityReceipt,
    IntentLock,
    PolicyEnvelope,
    ReceiptResult,
    ScopeChangeProtocolDecision,
    ScopeChangeRequest,
    ScopeChangeResult,
    TaskRequest,
    TaskRun,
)
from craik.runtime.policy.intent_locks import IntentLockNotFoundError
from craik.runtime.store import LocalStore
from craik.runtime.work.runs import RunTransition, TaskRunManager
from craik.runtime.work.tasks import create_task


@dataclass(frozen=True)
class ScopeChangeRequirement:
    """A run discovered work outside its current intent lock."""

    request: ScopeChangeRequest
    receipt: CapabilityReceipt | None
    out_of_scope: tuple[str, ...]
    run: TaskRun | None = None


@dataclass(frozen=True)
class ScopeChangeProtocolOutcome:
    """Persisted outcome for one scope-change protocol decision."""

    result: ScopeChangeResult
    receipt: CapabilityReceipt
    updated_intent_lock: IntentLock | None = None
    sibling_task: TaskRequest | None = None
    run: TaskRun | None = None


class ScopeChangeProtocolError(RuntimeError):
    """Raised when a scope-change protocol transition is invalid."""


class ScopeChangeRequestNotFoundError(ScopeChangeProtocolError):
    """Raised when a scope-change request cannot be found."""


class ScopeChangeProtocolManager:
    """Create and decide scope-change requests with receipts."""

    def __init__(self, store: LocalStore) -> None:
        self._store = store

    def require_decision_for_discovered_scope(
        self,
        *,
        policy: PolicyEnvelope,
        run: TaskRun,
        intent_lock: IntentLock | None,
        discovered_scope: list[str],
        requested_by: str,
        reason: str,
        evidence_ids: list[str] | None = None,
    ) -> ScopeChangeRequirement | None:
        """Record a pending scope-change request when discovered scope is outside bounds."""
        if intent_lock is None:
            return None
        out_of_scope = tuple(outside_scope(intent_lock, discovered_scope))
        if not out_of_scope:
            return None
        existing = self._matching_request(run, intent_lock, list(out_of_scope))
        if existing is not None:
            if existing.status == "accepted":
                return None
            return ScopeChangeRequirement(
                request=existing,
                receipt=None,
                out_of_scope=out_of_scope,
                run=self._interrupt_run_for_existing_request(run, existing),
            )

        request = ScopeChangeRequest(
            id=scope_change_request_id(run.id, intent_lock.id, out_of_scope),
            task_id=run.task_id,
            intent_lock_id=intent_lock.id,
            requested_by=requested_by,
            reason=reason,
            current_scope=list(intent_lock.in_scope),
            proposed_scope=[*intent_lock.in_scope, *out_of_scope],
            policy_envelope_id=policy.id,
            receipt_ids=[],
            created_at=datetime.now(UTC),
        )
        receipt = self._receipt(
            policy=policy,
            run=run,
            capability="scope_change.request",
            target=request.id,
            status="blocked",
            summary=reason,
            metadata={
                "run_id": run.id,
                "intent_lock_id": intent_lock.id,
                "out_of_scope": list(out_of_scope),
                "evidence_ids": list(evidence_ids or []),
                "protocol_required": ["expand", "sibling", "handoff", "denied"],
            },
        )
        receipt = self._store.put_receipt(receipt)
        request = request.model_copy(update={"receipt_ids": [receipt.id]})
        self._store.put_scope_change_request(request)
        paused_run = TaskRunManager(self._store).transition(
            run.id,
            RunTransition(
                status="interrupted",
                phase="stop",
                iteration=run.iteration,
                receipt_id=receipt.id,
                stop_reason=f"scope change pending: {request.id}",
                at=datetime.now(UTC),
            ),
        )
        return ScopeChangeRequirement(
            request=request,
            receipt=receipt,
            out_of_scope=out_of_scope,
            run=paused_run,
        )

    def decide(
        self,
        *,
        policy: PolicyEnvelope,
        request_id: str,
        protocol_decision: ScopeChangeProtocolDecision,
        decided_by: str,
        rationale: str,
        run_id: str | None = None,
        sibling_title: str | None = None,
        handoff_ids: list[str] | None = None,
    ) -> ScopeChangeProtocolOutcome:
        """Apply an explicit expand, sibling, handoff, or denial decision."""
        request = self._store.get_scope_change_request(request_id)
        if request is None:
            raise ScopeChangeRequestNotFoundError(f"unknown scope-change request: {request_id}")
        run = self._store.get_task_run(run_id) if run_id is not None else None
        updated_intent_lock: IntentLock | None = None
        sibling_task: TaskRequest | None = None
        decision: Literal["accepted", "rejected"] = (
            "rejected" if protocol_decision == "denied" else "accepted"
        )

        if protocol_decision == "expand":
            updated_intent_lock = self._expanded_intent_lock(request)
        elif protocol_decision == "sibling":
            sibling_task = self._sibling_task(request, title=sibling_title)
        elif protocol_decision == "handoff" and not handoff_ids:
            raise ScopeChangeProtocolError("handoff decisions require handoff_ids")

        result = ScopeChangeResult(
            id=f"scope_change_result_{request.id.removeprefix('scope_change_')}",
            task_id=request.task_id,
            scope_change_request_id=request.id,
            decision=decision,
            protocol_decision=protocol_decision,
            decided_by=decided_by,
            rationale=rationale,
            updated_intent_lock_id=updated_intent_lock.id if updated_intent_lock else None,
            sibling_task_id=sibling_task.id if sibling_task else None,
            policy_envelope_id=policy.id,
            handoff_ids=list(handoff_ids or []),
            receipt_ids=[],
            created_at=datetime.now(UTC),
        )
        receipt = self._receipt(
            policy=policy,
            run=run,
            capability="scope_change.decide",
            target=request.id,
            status="denied" if protocol_decision == "denied" else "passed",
            summary=rationale,
            metadata={
                "request_id": request.id,
                "run_id": run_id,
                "protocol_decision": protocol_decision,
                "updated_intent_lock_id": result.updated_intent_lock_id,
                "sibling_task_id": result.sibling_task_id,
                "handoff_ids": result.handoff_ids,
            },
        )
        receipt = self._store.put_receipt(receipt)
        result = result.model_copy(update={"receipt_ids": [receipt.id]})
        self._store.put_scope_change_result(result)
        self._store.put_scope_change_request(
            request.model_copy(
                update={
                    "status": decision,
                    "receipt_ids": [*request.receipt_ids, receipt.id],
                }
            )
        )
        updated_run = self._update_run_after_decision(run, result, receipt.id)
        return ScopeChangeProtocolOutcome(
            result=result,
            receipt=receipt,
            updated_intent_lock=updated_intent_lock,
            sibling_task=sibling_task,
            run=updated_run,
        )

    def _matching_request(
        self,
        run: TaskRun,
        intent_lock: IntentLock,
        out_of_scope: list[str],
    ) -> ScopeChangeRequest | None:
        expected = scope_change_request_id(run.id, intent_lock.id, out_of_scope)
        return self._store.get_scope_change_request(expected)

    def _expanded_intent_lock(self, request: ScopeChangeRequest) -> IntentLock:
        current = self._store.get_intent_lock(request.intent_lock_id)
        if current is None:
            raise IntentLockNotFoundError(f"unknown intent lock: {request.intent_lock_id}")
        expanded = current.model_copy(
            update={
                "id": f"{current.id}_expanded_{_slug(request.id)}",
                "in_scope": _unique([*current.in_scope, *request.proposed_scope]),
                "scope_change_rules": [
                    *current.scope_change_rules,
                    f"Scope expanded by {request.id}.",
                ],
                "created_at": datetime.now(UTC),
            }
        )
        self._store.put_intent_lock(expanded)
        return expanded

    def _sibling_task(self, request: ScopeChangeRequest, *, title: str | None) -> TaskRequest:
        source_task = self._store.get_task(request.task_id)
        if source_task is None:
            raise ScopeChangeProtocolError(f"unknown source task: {request.task_id}")
        return create_task(
            self._store,
            title=title or f"Follow-up scope from {request.id}",
            objective=request.reason,
            project_id=source_task.project_id,
            requested_by="craik:scope-change",
            priority=source_task.priority,
            mode=source_task.mode,
            auth_profile_id=source_task.auth_profile_id,
            operator_subject=source_task.operator_subject,
            operator_issuer=source_task.operator_issuer,
            source_task_id=source_task.id,
            source_run_id=_run_id_for_task(self._store, source_task.id),
            constraints=[f"Created from scope-change request {request.id}."],
            expected_outputs=request.proposed_scope,
        )

    def _update_run_after_decision(
        self,
        run: TaskRun | None,
        result: ScopeChangeResult,
        receipt_id: str,
    ) -> TaskRun | None:
        if run is None:
            return None
        receipt_ids = list(run.receipt_ids)
        if receipt_id not in receipt_ids:
            receipt_ids.append(receipt_id)
        updates: dict[str, object] = {"receipt_ids": receipt_ids}
        if result.updated_intent_lock_id is not None:
            updates["intent_lock_id"] = result.updated_intent_lock_id
        updated = run.model_copy(update=updates)
        self._store.put_task_run(updated)
        return updated

    def _interrupt_run_for_existing_request(
        self,
        run: TaskRun,
        request: ScopeChangeRequest,
    ) -> TaskRun:
        if run.status == "interrupted":
            return run
        return TaskRunManager(self._store).transition(
            run.id,
            RunTransition(
                status="interrupted",
                phase="stop",
                iteration=run.iteration,
                receipt_id=request.receipt_ids[-1] if request.receipt_ids else None,
                stop_reason=f"scope change pending: {request.id}",
                at=datetime.now(UTC),
            ),
        )

    def _receipt(
        self,
        *,
        policy: PolicyEnvelope,
        run: TaskRun | None,
        capability: str,
        target: str,
        status: Literal["passed", "blocked", "denied"],
        summary: str,
        metadata: dict[str, object],
    ) -> CapabilityReceipt:
        return CapabilityReceipt(
            id=f"receipt_{target}_{capability.rsplit('.', maxsplit=1)[-1]}",
            task_id=policy.task_id,
            actor="craik:scope-change",
            capability=capability,
            target=target,
            policy_profile=policy.profile,
            fail_open=policy.fail_open,
            reason=summary,
            result=ReceiptResult(status=status, summary=summary, metadata=metadata),
            redacted=True,
            auth_profile_id=run.auth_profile_id if run else None,
            auth_identity_hash=run.auth_identity_hash if run else None,
            operator_subject=run.operator_subject if run else None,
            operator_issuer=run.operator_issuer if run else None,
            created_at=datetime.now(UTC),
        )


def outside_scope(intent_lock: IntentLock, discovered_scope: list[str]) -> list[str]:
    """Return discovered scope items that are not allowed by the current lock."""
    outside: list[str] = []
    for item in discovered_scope:
        normalized = item.strip()
        if not normalized:
            continue
        if _overlaps_any(normalized, intent_lock.out_of_scope):
            outside.append(normalized)
            continue
        if intent_lock.in_scope and not _overlaps_any(normalized, intent_lock.in_scope):
            outside.append(normalized)
    return _unique(outside)


def discovered_scope_from_context(context: dict[str, object]) -> list[str]:
    """Extract discovered scope items from loop context."""
    raw = context.get("discovered_scope") or context.get("discovered_work_scope")
    if isinstance(raw, str):
        return [raw]
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if str(item).strip()]


def scope_change_request_id(
    run_id: str,
    intent_lock_id: str,
    out_of_scope: tuple[str, ...] | list[str],
) -> str:
    """Build a deterministic request id for one run/scope boundary."""
    joined = "_".join(_slug(item) for item in out_of_scope) or "unspecified"
    return f"scope_change_{_slug(run_id)}_{_slug(intent_lock_id)}_{joined}"


def _run_id_for_task(store: LocalStore, task_id: str) -> str | None:
    for run in store.list_task_runs():
        if run.task_id == task_id:
            return run.id
    return None


def _overlaps_any(item: str, scopes: list[str]) -> bool:
    return any(_scope_item_overlaps(item, scope) for scope in scopes)


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


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "item"
