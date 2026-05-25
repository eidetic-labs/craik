"""CommandResult helpers for approval review commands."""

from __future__ import annotations

from craik.runtime.contract import CommandResult
from craik.runtime.paths import resolve_craik_paths
from craik.runtime.reviewing.approvals import (
    ApprovalNotFoundError,
    ApprovalStateError,
    approval_queue_payload,
    approval_view,
    decide_approval,
)
from craik.runtime.store import LocalStore


def approvals_list_result(
    *,
    include_resolved: bool = False,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Return pending or all approval requests."""
    store = LocalStore.from_paths(resolve_craik_paths(env))
    try:
        store.initialize()
        if include_resolved:
            approvals = [
                approval_view(delegation).as_dict()
                for delegation in store.list_human_delegations()
                if delegation.kind == "approval"
            ]
            payload = {"count": len(approvals), "approvals": approvals}
        else:
            payload = approval_queue_payload(store)
    finally:
        store.close()
    return CommandResult(
        payload=payload,
        shape="card_list",
        empty_state_message="No pending approvals.",
    )


def approvals_show_result(
    approval_id: str,
    *,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Return one approval request."""
    store = LocalStore.from_paths(resolve_craik_paths(env))
    try:
        store.initialize()
        delegation = store.get_human_delegation(approval_id)
        if delegation is None or delegation.kind != "approval":
            raise ValueError(f"unknown approval: {approval_id}")
        payload = approval_view(delegation).as_dict()
    finally:
        store.close()
    return CommandResult(payload=payload, shape="card")


def approvals_decide_result(
    approval_id: str,
    *,
    decision: str,
    operator: str,
    reason: str,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Apply an approval decision and return the decision receipt payload."""
    store = LocalStore.from_paths(resolve_craik_paths(env))
    try:
        store.initialize()
        result = decide_approval(
            store,
            approval_id,
            decision="approved" if decision == "approved" else "denied",
            operator=operator,
            reason=reason,
        )
    except (ApprovalNotFoundError, ApprovalStateError) as error:
        raise ValueError(str(error)) from None
    finally:
        store.close()
    return CommandResult(
        payload={
            "approval": result.approval.as_dict(),
            "receipt": result.receipt.model_dump(mode="json", by_alias=True),
        },
        shape="card",
    )
