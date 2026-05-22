"""Approval queue lifecycle helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol

from craik.contracts.models import CapabilityReceipt, HumanDelegationPoint, ReceiptResult
from craik.runtime.policy.text import sanitize_runtime_text

ApprovalDecision = Literal["approved", "denied"]


class ApprovalStore(Protocol):
    """Store surface required by approval queue helpers."""

    def put_human_delegation(self, delegation: HumanDelegationPoint) -> None:
        raise NotImplementedError

    def get_human_delegation(self, delegation_id: str) -> HumanDelegationPoint | None:
        raise NotImplementedError

    def list_human_delegations(self) -> list[HumanDelegationPoint]:
        raise NotImplementedError

    def put_receipt(self, receipt: CapabilityReceipt) -> CapabilityReceipt:
        raise NotImplementedError


@dataclass(frozen=True)
class ApprovalRequestView:
    """Operator-facing approval request view."""

    id: str
    status: str
    task_id: str
    capability: str
    target: str
    risk: str
    policy: str
    operator: str | None
    retry_path: str
    requested_by: str
    created_at: datetime
    receipt_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "status": self.status,
            "task_id": self.task_id,
            "capability": self.capability,
            "target": self.target,
            "risk": self.risk,
            "policy": self.policy,
            "operator": self.operator,
            "retry_path": self.retry_path,
            "requested_by": self.requested_by,
            "created_at": self.created_at.isoformat(),
            "receipt_ids": list(self.receipt_ids),
        }


@dataclass(frozen=True)
class ApprovalDecisionResult:
    """Resolved approval plus its decision receipt."""

    approval: ApprovalRequestView
    delegation: HumanDelegationPoint
    receipt: CapabilityReceipt


def open_approval_request(
    store: ApprovalStore,
    *,
    approval_id: str,
    task_id: str,
    capability: str,
    target: str,
    risk: str,
    policy: str,
    requested_by: str,
    retry_path: str,
    operator: str | None = None,
    policy_envelope_id: str | None = None,
    created_at: datetime | None = None,
) -> HumanDelegationPoint:
    """Persist an open approval request as a human delegation point."""
    now = created_at or datetime.now(UTC)
    payload = _approval_payload(
        capability=capability,
        target=target,
        risk=risk,
        policy=policy,
        operator=operator,
        retry_path=retry_path,
    )
    delegation = HumanDelegationPoint(
        id=approval_id,
        task_id=task_id,
        kind="approval",
        status="open",
        summary=f"Approval required for {capability} on {target}",
        requested_decision=json.dumps(payload, sort_keys=True),
        requested_by=requested_by,
        owner=operator,
        policy_envelope_id=policy_envelope_id,
        created_at=now,
    )
    store.put_human_delegation(delegation)
    return delegation


def list_approval_requests(
    store: ApprovalStore,
    *,
    include_resolved: bool = False,
) -> list[ApprovalRequestView]:
    """Return approval delegation points in stable queue order."""
    approvals = [
        approval_view(delegation)
        for delegation in store.list_human_delegations()
        if delegation.kind == "approval"
    ]
    if not include_resolved:
        approvals = [approval for approval in approvals if approval.status == "open"]
    return sorted(approvals, key=lambda approval: (approval.created_at, approval.id))


def approval_queue_payload(store: ApprovalStore) -> dict[str, object]:
    """Return redacted queue payload for CLI, dashboard, and shell surfaces."""
    approvals = list_approval_requests(store)
    return {
        "count": len(approvals),
        "approvals": [approval.as_dict() for approval in approvals],
    }


def approval_view(delegation: HumanDelegationPoint) -> ApprovalRequestView:
    """Render one approval delegation as a structured view."""
    payload = _parse_requested_decision(delegation.requested_decision)
    return ApprovalRequestView(
        id=delegation.id,
        status=delegation.status,
        task_id=delegation.task_id,
        capability=payload.get("capability", "unknown"),
        target=payload.get("target", "unknown"),
        risk=payload.get("risk", delegation.summary),
        policy=payload.get("policy", delegation.policy_envelope_id or "unspecified"),
        operator=payload.get("operator") or delegation.owner,
        retry_path=payload.get("retry_path", "retry the blocked command after approval"),
        requested_by=delegation.requested_by,
        created_at=delegation.created_at,
        receipt_ids=tuple(delegation.receipt_ids),
    )


def decide_approval(
    store: ApprovalStore,
    approval_id: str,
    *,
    decision: ApprovalDecision,
    operator: str,
    reason: str,
    decided_at: datetime | None = None,
) -> ApprovalDecisionResult:
    """Resolve one approval request and emit a decision receipt."""
    delegation = store.get_human_delegation(approval_id)
    if delegation is None or delegation.kind != "approval":
        raise ApprovalNotFoundError(f"unknown approval: {approval_id}")
    if delegation.status != "open":
        raise ApprovalStateError(f"approval is {delegation.status}: {approval_id}")
    now = decided_at or datetime.now(UTC)
    view = approval_view(delegation)
    receipt = store.put_receipt(
        CapabilityReceipt(
            id=f"receipt_approval_{approval_id}_{decision}",
            task_id=delegation.task_id,
            actor="craik:approval-queue",
            capability="approval.decide",
            target=approval_id,
            policy_profile="strict",
            fail_open=False,
            reason=reason,
            result=ReceiptResult(
                status="passed" if decision == "approved" else "denied",
                summary=f"Approval {decision}.",
                metadata={
                    "approval_id": approval_id,
                    "decision": decision,
                    "operator": operator,
                    "capability": view.capability,
                    "target": view.target,
                    "risk": view.risk,
                    "policy": view.policy,
                    "retry_path": view.retry_path,
                },
            ),
            operator_subject=operator,
            redacted=True,
            created_at=now,
        )
    )
    resolution = f"{decision}: {reason}. Retry path: {view.retry_path}"
    updated = delegation.model_copy(
        update={
            "status": "resolved",
            "resolution": sanitize_runtime_text(resolution),
            "resolved_at": now,
            "receipt_ids": [*delegation.receipt_ids, receipt.id],
        }
    )
    store.put_human_delegation(updated)
    return ApprovalDecisionResult(
        approval=approval_view(updated),
        delegation=updated,
        receipt=receipt,
    )


class ApprovalNotFoundError(RuntimeError):
    """Raised when an approval request cannot be found."""


class ApprovalStateError(RuntimeError):
    """Raised when an approval request cannot transition."""


def _approval_payload(
    *,
    capability: str,
    target: str,
    risk: str,
    policy: str,
    operator: str | None,
    retry_path: str,
) -> dict[str, str | None]:
    return {
        "capability": sanitize_runtime_text(capability),
        "target": sanitize_runtime_text(target),
        "risk": sanitize_runtime_text(risk),
        "policy": sanitize_runtime_text(policy),
        "operator": sanitize_runtime_text(operator) if operator else None,
        "retry_path": sanitize_runtime_text(retry_path),
    }


def _parse_requested_decision(value: str) -> dict[str, str]:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        str(key): sanitize_runtime_text(str(raw_value))
        for key, raw_value in payload.items()
        if raw_value is not None
    }
