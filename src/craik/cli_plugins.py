"""Plugin governance CLI commands."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer

from craik.cli import plugins_app
from craik.contracts.models import CapabilityTarget, PluginCapabilityGrant
from craik.runtime.auth.operator import OperatorSessionNotFoundError, OperatorSessionStore
from craik.runtime.skills.plugins import (
    install_plugin_descriptor,
    record_plugin_capability_grant,
    review_plugin_probation,
)
from craik.runtime.store import LocalStore

probation_app = typer.Typer(help="Review plugin probation records.")
plugins_app.add_typer(probation_app, name="probation")
grants_app = typer.Typer(help="Inspect plugin grants.")
plugins_app.add_typer(grants_app, name="grants")
receipts_app = typer.Typer(help="Inspect plugin receipts.")
plugins_app.add_typer(receipts_app, name="receipts")


@plugins_app.command("install")
def plugins_install(
    path: Annotated[Path, typer.Argument(help="Plugin descriptor JSON manifest.")],
) -> None:
    """Install a plugin descriptor manifest."""
    _operator_identity()
    store = LocalStore.from_env()
    try:
        store.initialize()
        descriptor = install_plugin_descriptor(store, path)
    finally:
        store.close()
    _print(descriptor)


@probation_app.command("review")
def plugins_probation_review(
    probation_id: Annotated[str, typer.Argument(help="Plugin probation id.")],
    evidence: Annotated[list[str], typer.Option("--evidence", help="Evidence id. May repeat.")],
    decide: Annotated[str, typer.Option("--decide", help="pass or fail.")],
    rationale: Annotated[
        str,
        typer.Option("--rationale", help="Review rationale."),
    ] = "Reviewed from CLI.",
) -> None:
    """Decide a plugin probation review."""
    operator = _operator_identity()
    store = LocalStore.from_env()
    try:
        store.initialize()
        probation = review_plugin_probation(
            store,
            probation_id,
            decision=decide,
            decided_by=operator,
            rationale=rationale,
            evidence_ids=evidence,
        )
    finally:
        store.close()
    _print(probation)


@plugins_app.command("grant")
def plugins_grant(
    plugin_id: Annotated[str, typer.Argument(help="Plugin descriptor id.")],
    operation: Annotated[list[str], typer.Option("--operation", help="Operation. May repeat.")],
    target: Annotated[list[str], typer.Option("--target", help="Target path. May repeat.")],
    expiry: Annotated[str, typer.Option("--expiry", help="ISO-8601 expiry.")],
    task_id: Annotated[str, typer.Option("--task", help="Task id.")],
    policy_envelope_id: Annotated[str, typer.Option("--policy", help="Policy envelope id.")],
    evidence: Annotated[list[str], typer.Option("--evidence", help="Evidence id. May repeat.")],
    capability: Annotated[
        str,
        typer.Option("--capability", help="Capability name."),
    ] = "plugin.operation",
    grant_id: Annotated[str | None, typer.Option("--id", help="Grant id.")] = None,
    repo: Annotated[str | None, typer.Option("--repo", help="Repository target.")] = None,
    reason: Annotated[str, typer.Option("--reason", help="Grant reason.")] = "Approved from CLI.",
) -> None:
    """Grant plugin capability authority."""
    operator = _operator_identity()
    grant = PluginCapabilityGrant(
        id=grant_id or f"plugin_grant_{plugin_id}_{operation[0]}",
        task_id=task_id,
        plugin_descriptor_id=plugin_id,
        policy_envelope_id=policy_envelope_id,
        capability=capability,
        target=CapabilityTarget(repo=repo, paths=target, metadata={}),
        operations=operation,
        status="allowed",
        approval_required=True,
        approved_by=operator,
        expires_at=_parse_datetime(expiry),
        reason=reason,
        evidence_ids=evidence,
        created_at=datetime.now(tz=_parse_datetime(expiry).tzinfo),
    )
    store = LocalStore.from_env()
    try:
        store.initialize()
        grant = record_plugin_capability_grant(store, grant)
    finally:
        store.close()
    _print(grant)


@grants_app.command("list")
def plugin_grants_list(
    plugin: Annotated[str | None, typer.Option("--plugin", help="Plugin descriptor id.")] = None,
) -> None:
    """List plugin capability grants."""
    _operator_identity()
    store = LocalStore.from_env()
    try:
        store.initialize()
        grants = store.list_plugin_capability_grants()
    finally:
        store.close()
    if plugin:
        grants = [grant for grant in grants if grant.plugin_descriptor_id == plugin]
    typer.echo(json.dumps([_payload(grant) for grant in grants], indent=2, sort_keys=True))


@receipts_app.command("list")
def plugin_receipts_list(
    plugin: Annotated[str | None, typer.Option("--plugin", help="Plugin descriptor id.")] = None,
) -> None:
    """List plugin receipts."""
    _operator_identity()
    store = LocalStore.from_env()
    try:
        store.initialize()
        receipts = store.list_plugin_receipts()
    finally:
        store.close()
    if plugin:
        receipts = [receipt for receipt in receipts if receipt.plugin_descriptor_id == plugin]
    typer.echo(json.dumps([_payload(receipt) for receipt in receipts], indent=2, sort_keys=True))


def _operator_identity() -> str:
    try:
        session = OperatorSessionStore.from_env().get()
    except OperatorSessionNotFoundError:
        raise typer.BadParameter("active operator session required; run craik auth login") from None
    return session.subject


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _payload(model: object) -> dict[str, object]:
    return model.model_dump(mode="json", by_alias=True)  # type: ignore[attr-defined,no-any-return]


def _print(model: object) -> None:
    typer.echo(json.dumps(_payload(model), indent=2, sort_keys=True))
