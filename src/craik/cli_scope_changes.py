"""Scope-change protocol CLI commands."""

from __future__ import annotations

import json
from typing import Annotated, cast

import typer

from craik.cli import scope_change_app
from craik.contracts.models import ScopeChangeProtocolDecision
from craik.runtime.policy.policy import generate_policy_envelope
from craik.runtime.store import LocalStore
from craik.runtime.work.coordination.scope_changes import (
    ScopeChangeProtocolError,
    ScopeChangeProtocolManager,
)


@scope_change_app.command("decide")
def scope_change_decide(
    request_id: Annotated[str, typer.Argument(help="Scope-change request id.")],
    decision: Annotated[
        str,
        typer.Option("--decision", help="Decision: expand, sibling, handoff, or denied."),
    ],
    rationale: Annotated[str, typer.Option("--rationale", help="Decision rationale.")],
    decided_by: Annotated[str, typer.Option("--decided-by", help="Operator or agent deciding.")],
    run_id: Annotated[
        str | None,
        typer.Option("--run-id", help="Paused run id to resume or update."),
    ] = None,
    sibling_title: Annotated[
        str | None,
        typer.Option("--sibling-title", help="Title for a sibling task decision."),
    ] = None,
    handoff_id: Annotated[
        list[str] | None,
        typer.Option("--handoff-id", help="Handoff id for a handoff decision."),
    ] = None,
) -> None:
    """Resolve a pending scope-change request through the explicit protocol."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        request = store.get_scope_change_request(request_id)
        if request is None:
            raise ScopeChangeProtocolError(f"unknown scope-change request: {request_id}")
        policy = generate_policy_envelope(task_id=request.task_id, actor=decided_by)
        outcome = ScopeChangeProtocolManager(store).decide(
            policy=policy,
            request_id=request_id,
            protocol_decision=_protocol_decision(decision),
            decided_by=decided_by,
            rationale=rationale,
            run_id=run_id,
            sibling_title=sibling_title,
            handoff_ids=handoff_id,
        )
    except ScopeChangeProtocolError as error:
        raise typer.BadParameter(str(error)) from None
    finally:
        store.close()

    payload = {
        "result": outcome.result.model_dump(mode="json", by_alias=True),
        "receipt": outcome.receipt.model_dump(mode="json", by_alias=True),
        "updated_intent_lock": (
            outcome.updated_intent_lock.model_dump(mode="json", by_alias=True)
            if outcome.updated_intent_lock is not None
            else None
        ),
        "sibling_task": (
            outcome.sibling_task.model_dump(mode="json", by_alias=True)
            if outcome.sibling_task is not None
            else None
        ),
        "run": (
            outcome.run.model_dump(mode="json", by_alias=True)
            if outcome.run is not None
            else None
        ),
    }
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


def _protocol_decision(value: str) -> ScopeChangeProtocolDecision:
    if value not in {"expand", "sibling", "handoff", "denied"}:
        raise typer.BadParameter(f"unsupported scope-change decision: {value}")
    return cast(ScopeChangeProtocolDecision, value)
