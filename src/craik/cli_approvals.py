"""Approval queue CLI commands."""

from __future__ import annotations

from typing import Annotated

import typer

from craik.cli_operator_auth import operator_identity_or_fail
from craik.cli_output import emit_command_result
from craik.runtime.contract import CommandResult, craik_command
from craik.runtime.reviewing.approval_commands import (
    approvals_decide_result,
    approvals_list_result,
    approvals_show_result,
)

approvals_app = typer.Typer(help="Review and decide pending approval requests.")


@approvals_app.command("list")
@craik_command(slash_alias="approvals", payload_shape="card_list")
def approvals_list_command(
    include_resolved: Annotated[
        bool,
        typer.Option("--include-resolved", help="Include resolved approval records."),
    ] = False,
) -> CommandResult:
    """List approval requests."""
    operator_identity_or_fail()
    result = approvals_list_result(include_resolved=include_resolved)
    emit_command_result(result)
    return result


@approvals_app.command("show")
@craik_command(payload_shape="card")
def approvals_show_command(approval_id: str) -> CommandResult:
    """Show one approval request."""
    operator_identity_or_fail()
    try:
        result = approvals_show_result(approval_id)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from None
    emit_command_result(result)
    return result


@approvals_app.command("approve")
@craik_command(payload_shape="card")
def approvals_approve_command(
    approval_id: str,
    reason: Annotated[str, typer.Option("--reason", help="Approval reason.")],
) -> CommandResult:
    """Approve one request and emit a decision receipt."""
    return _decide(approval_id, decision="approved", reason=reason)


@approvals_app.command("deny")
@craik_command(payload_shape="card")
def approvals_deny_command(
    approval_id: str,
    reason: Annotated[str, typer.Option("--reason", help="Denial reason.")],
) -> CommandResult:
    """Deny one request and emit an actionable decision receipt."""
    return _decide(approval_id, decision="denied", reason=reason)


def _decide(approval_id: str, *, decision: str, reason: str) -> CommandResult:
    operator = operator_identity_or_fail()
    try:
        result = approvals_decide_result(
            approval_id,
            decision=decision,
            operator=operator,
            reason=reason,
        )
    except ValueError as error:
        raise typer.BadParameter(str(error)) from None
    emit_command_result(result)
    return result
