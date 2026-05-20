"""Human delegation CLI commands."""

from __future__ import annotations

import json
from typing import Annotated, cast

import typer

from craik.cli import delegation_app
from craik.contracts.models import HumanDelegationKind
from craik.runtime.policy.policy import generate_policy_envelope
from craik.runtime.reviewing.delegations import (
    DelegationResolution,
    HumanDelegationManager,
    HumanDelegationNotFoundError,
    HumanDelegationStateError,
)
from craik.runtime.store import LocalStore


@delegation_app.command("pause")
def delegation_pause(
    run_id: Annotated[str, typer.Argument(help="Run id to pause for human input.")],
    summary: Annotated[str, typer.Option("--summary", help="Delegation summary.")],
    requested_decision: Annotated[
        str,
        typer.Option("--decision", help="Decision requested from the human operator."),
    ],
    kind: Annotated[
        str,
        typer.Option(
            "--kind",
            help="Delegation kind: approval, clarification, escalation, or ownership_transfer.",
        ),
    ] = "clarification",
    owner: Annotated[str | None, typer.Option("--owner", help="Delegation owner.")] = None,
) -> None:
    """Pause a run by opening a receipted human delegation."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        run = store.get_task_run(run_id)
        if run is None:
            raise typer.BadParameter(f"unknown task run: {run_id}")
        result = HumanDelegationManager(store).pause_run_for_delegation(
            policy=generate_policy_envelope(task_id=run.task_id, actor="craik:cli"),
            run_id=run.id,
            kind=_delegation_kind(kind),
            summary=summary,
            requested_decision=requested_decision,
            requested_by="craik:cli",
            owner=owner,
        )
    except (HumanDelegationNotFoundError, HumanDelegationStateError, ValueError) as error:
        raise typer.BadParameter(str(error)) from None
    finally:
        store.close()
    typer.echo(
        json.dumps(
            {
                "run": result.run.model_dump(mode="json", by_alias=True),
                "delegation": result.delegation.model_dump(mode="json", by_alias=True),
                "receipt": result.receipt.model_dump(mode="json", by_alias=True),
            },
            indent=2,
            sort_keys=True,
        )
    )


@delegation_app.command("resolve")
def delegation_resolve(
    delegation_id: Annotated[str, typer.Argument(help="Delegation id to resolve.")],
    resolution: Annotated[str, typer.Option("--resolution", help="Human resolution text.")],
    outcome: Annotated[
        str,
        typer.Option("--outcome", help="accepted, rejected, or cancelled."),
    ] = "accepted",
) -> None:
    """Resolve or cancel a human delegation and link the decision receipt to its run."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        delegation = store.get_human_delegation(delegation_id)
        if delegation is None:
            raise typer.BadParameter(f"unknown human delegation: {delegation_id}")
        result = HumanDelegationManager(store).resolve_run_delegation(
            policy=generate_policy_envelope(task_id=delegation.task_id, actor="craik:cli"),
            delegation_id=delegation.id,
            resolution=resolution,
            outcome=_delegation_outcome(outcome),
        )
    except (HumanDelegationNotFoundError, HumanDelegationStateError, ValueError) as error:
        raise typer.BadParameter(str(error)) from None
    finally:
        store.close()
    typer.echo(
        json.dumps(
            {
                "delegation": result.delegation.model_dump(mode="json", by_alias=True),
                "receipt": result.receipt.model_dump(mode="json", by_alias=True),
                "run": result.run.model_dump(mode="json", by_alias=True)
                if result.run is not None
                else None,
            },
            indent=2,
            sort_keys=True,
        )
    )


def _delegation_outcome(value: str) -> DelegationResolution:
    if value in {"accepted", "rejected", "cancelled"}:
        return cast(DelegationResolution, value)
    raise typer.BadParameter("outcome must be accepted, rejected, or cancelled")


def _delegation_kind(value: str) -> HumanDelegationKind:
    if value in {"approval", "clarification", "escalation", "ownership_transfer"}:
        return cast(HumanDelegationKind, value)
    raise typer.BadParameter(
        "kind must be approval, clarification, escalation, or ownership_transfer"
    )
