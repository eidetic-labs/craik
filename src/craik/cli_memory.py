"""Memory CLI commands."""

from __future__ import annotations

from typing import Annotated, cast

import typer

from craik.cli import memory_app
from craik.cli_operator_auth import operator_identity_or_fail
from craik.cli_output import emit_command_result
from craik.contracts.models import MemoryScope, ProposalOperation, TrustClass
from craik.runtime.contract import CommandResult, craik_command
from craik.runtime.memory.commands import (
    memory_decide_result,
    memory_diff_result,
    memory_list_result,
    memory_preview_result,
    memory_propose_result,
    memory_search_result,
    memory_show_result,
)


@memory_app.command("propose")
@craik_command(payload_shape="card")
def memory_propose(
    task_id: Annotated[str, typer.Argument(help="Task id for the proposal.")],
    entity: Annotated[str, typer.Option("--entity", help="Fact entity.")],
    relation: Annotated[str, typer.Option("--relation", help="Fact relation.")],
    value: Annotated[str, typer.Option("--value", help="Fact value.")],
    source: Annotated[str, typer.Option("--source", help="Fact source.")],
    evidence_source: Annotated[
        str,
        typer.Option("--evidence-source", help="Evidence source supporting the proposal."),
    ],
    evidence_locator: Annotated[
        str,
        typer.Option("--evidence-locator", help="Evidence locator supporting the proposal."),
    ],
    evidence_summary: Annotated[
        str,
        typer.Option("--evidence-summary", help="Evidence summary supporting the proposal."),
    ],
    confidence: Annotated[
        float,
        typer.Option("--confidence", min=0.0, max=1.0, help="Fact confidence."),
    ] = 0.8,
    scope: Annotated[
        str,
        typer.Option("--scope", help="Memory scope: local, team, company, or public."),
    ] = "local",
    trust_class: Annotated[
        str,
        typer.Option(
            "--trust-class",
            help="Trust class: observed, reported, inferred, policy, external, or stale-risk.",
        ),
    ] = "observed",
    operation: Annotated[
        str,
        typer.Option("--operation", help="Operation: add, update, or invalidate."),
    ] = "add",
) -> CommandResult:
    """Create a reviewable local memory proposal."""
    operator_identity_or_fail()
    result = memory_propose_result(
        task_id=task_id,
        entity=entity,
        relation=relation,
        value=value,
        source=source,
        evidence_source=evidence_source,
        evidence_locator=evidence_locator,
        evidence_summary=evidence_summary,
        confidence=confidence,
        scope=_memory_scope(scope),
        trust_class=_trust_class(trust_class),
        operation=_proposal_operation(operation),
    )
    emit_command_result(result)
    return result


@memory_app.command("list")
@craik_command(slash_alias="memory-list", payload_shape="card_list")
def memory_list(
    task_id: Annotated[
        str | None,
        typer.Option("--task-id", help="Only include proposals for this task id."),
    ] = None,
    status: Annotated[
        str | None,
        typer.Option("--status", help="Only include proposals with this status."),
    ] = None,
) -> CommandResult:
    """List local memory proposals."""
    operator_identity_or_fail()
    result = memory_list_result(task_id=task_id, status=status)
    emit_command_result(result)
    return result


@memory_app.command("show")
@craik_command(payload_shape="card")
def memory_show(proposal_id: str) -> CommandResult:
    """Show one local memory proposal."""
    operator_identity_or_fail()
    try:
        result = memory_show_result(proposal_id)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from None
    emit_command_result(result)
    return result


@memory_app.command("approve")
@craik_command(payload_shape="card")
def memory_approve(
    proposal_id: str,
    decided_by: Annotated[
        str,
        typer.Option("--decided-by", help="Reviewer identity."),
    ] = "user:local",
    reason: Annotated[
        str,
        typer.Option("--reason", help="Decision reason."),
    ] = "Evidence reviewed.",
) -> CommandResult:
    """Approve a local memory proposal for local search."""
    operator_identity_or_fail()
    return _decide(proposal_id, decision="approve", decided_by=decided_by, reason=reason)


@memory_app.command("reject")
@craik_command(payload_shape="card")
def memory_reject(
    proposal_id: str,
    decided_by: Annotated[
        str,
        typer.Option("--decided-by", help="Reviewer identity."),
    ] = "user:local",
    reason: Annotated[
        str,
        typer.Option("--reason", help="Decision reason."),
    ] = "Rejected during review.",
) -> CommandResult:
    """Reject a local memory proposal."""
    operator_identity_or_fail()
    return _decide(proposal_id, decision="reject", decided_by=decided_by, reason=reason)


@memory_app.command("search")
@craik_command(payload_shape="card_list")
def memory_search(query: str) -> CommandResult:
    """Search approved local memory facts."""
    operator_identity_or_fail()
    result = memory_search_result(query)
    emit_command_result(result)
    return result


@memory_app.command("diff")
@craik_command(payload_shape="card")
def memory_diff(task_id: str) -> CommandResult:
    """Print a run-scoped memory diff for local proposal activity."""
    operator_identity_or_fail()
    result = memory_diff_result(task_id)
    emit_command_result(result)
    return result


@memory_app.command("preview")
@craik_command(payload_shape="card")
def memory_preview(task_id: str) -> CommandResult:
    """Preview local memory impact before promotion or direct writes."""
    operator_identity_or_fail()
    result = memory_preview_result(task_id)
    emit_command_result(result)
    return result


def _decide(
    proposal_id: str,
    *,
    decision: str,
    decided_by: str,
    reason: str,
) -> CommandResult:
    try:
        result = memory_decide_result(
            proposal_id,
            decision=decision,
            decided_by=decided_by,
            reason=reason,
        )
    except ValueError as error:
        raise typer.BadParameter(str(error)) from None
    emit_command_result(result)
    return result


def _memory_scope(value: str) -> MemoryScope:
    if value not in {"local", "team", "company", "public"}:
        raise typer.BadParameter(f"unsupported memory scope: {value}")
    return cast(MemoryScope, value)


def _trust_class(value: str) -> TrustClass:
    allowed = {"observed", "reported", "inferred", "policy", "external", "stale-risk"}
    if value not in allowed:
        raise typer.BadParameter(f"unsupported trust class: {value}")
    return cast(TrustClass, value)


def _proposal_operation(value: str) -> ProposalOperation:
    if value not in {"add", "update", "invalidate"}:
        raise typer.BadParameter(f"unsupported proposal operation: {value}")
    return cast(ProposalOperation, value)
