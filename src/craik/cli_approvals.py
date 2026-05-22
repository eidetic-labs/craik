"""Approval queue CLI commands."""

from __future__ import annotations

import json
from typing import Annotated

import typer

from craik.cli_operator_auth import operator_identity_or_fail
from craik.runtime.reviewing.approvals import (
    ApprovalNotFoundError,
    ApprovalStateError,
    approval_queue_payload,
    approval_view,
    decide_approval,
)
from craik.runtime.store import LocalStore

approvals_app = typer.Typer(help="Review and decide pending approval requests.")


@approvals_app.command("list")
def approvals_list_command(
    include_resolved: Annotated[
        bool,
        typer.Option("--include-resolved", help="Include resolved approval records."),
    ] = False,
) -> None:
    """List approval requests."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
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
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@approvals_app.command("show")
def approvals_show_command(approval_id: str) -> None:
    """Show one approval request."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        delegation = store.get_human_delegation(approval_id)
        if delegation is None or delegation.kind != "approval":
            raise typer.BadParameter(f"unknown approval: {approval_id}")
        payload = approval_view(delegation).as_dict()
    finally:
        store.close()
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@approvals_app.command("approve")
def approvals_approve_command(
    approval_id: str,
    reason: Annotated[str, typer.Option("--reason", help="Approval reason.")],
) -> None:
    """Approve one request and emit a decision receipt."""
    _decide(approval_id, decision="approved", reason=reason)


@approvals_app.command("deny")
def approvals_deny_command(
    approval_id: str,
    reason: Annotated[str, typer.Option("--reason", help="Denial reason.")],
) -> None:
    """Deny one request and emit an actionable decision receipt."""
    _decide(approval_id, decision="denied", reason=reason)


def _decide(approval_id: str, *, decision: str, reason: str) -> None:
    operator = operator_identity_or_fail()
    store = LocalStore.from_env()
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
        raise typer.BadParameter(str(error)) from None
    finally:
        store.close()
    typer.echo(
        json.dumps(
            {
                "approval": result.approval.as_dict(),
                "receipt": result.receipt.model_dump(mode="json", by_alias=True),
            },
            indent=2,
            sort_keys=True,
        )
    )
