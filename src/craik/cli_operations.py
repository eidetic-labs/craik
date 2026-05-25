"""Contradiction, graph, handoff, memory, and policy CLI commands."""

from __future__ import annotations

import json
from importlib import import_module
from typing import Annotated, cast

import typer

from craik.cli import contradictions_app, graph_app, policy_app
from craik.cli_operator_auth import operator_identity_or_fail
from craik.contracts.models import (
    ContradictionStatus,
    PolicyProfile,
)
from craik.runtime.memory.contradictions import ContradictionManager, ContradictionNotFoundError
from craik.runtime.policy.policy import (
    FailOpenNotAllowedError,
    fail_open_receipt,
    generate_policy_envelope,
)
from craik.runtime.policy.policy_tests import PolicyTestHarness
from craik.runtime.store import LocalStore
from craik.runtime.work.graph import WorkGraphExporter, WorkGraphTaskNotFoundError

import_module("craik.cli_handoffs")


@contradictions_app.command("open")
def contradiction_open(
    summary: Annotated[str, typer.Option("--summary", help="Contradiction summary.")],
    fact: Annotated[
        list[str],
        typer.Option("--fact", help="Conflicting fact id or statement. Repeat at least twice."),
    ],
    task_id: Annotated[
        str | None,
        typer.Option("--task-id", help="Task associated with this contradiction."),
    ] = None,
    affected_artifact: Annotated[
        list[str] | None,
        typer.Option("--affected-artifact", help="Affected artifact path or id."),
    ] = None,
    evidence_id: Annotated[
        list[str] | None,
        typer.Option("--evidence-id", help="Supporting evidence id."),
    ] = None,
    owner: Annotated[
        str | None,
        typer.Option("--owner", help="Owner responsible for resolution."),
    ] = None,
    proposed_resolution: Annotated[
        str | None,
        typer.Option("--proposed-resolution", help="Proposed resolution."),
    ] = None,
    stigmem_conflict_id: Annotated[
        str | None,
        typer.Option("--stigmem-conflict-id", help="Optional future Stigmem conflict id."),
    ] = None,
) -> None:
    """Open and persist a local contradiction report."""
    operator_identity_or_fail()
    if len(fact) < 2:
        raise typer.BadParameter("at least two --fact values are required")
    store = LocalStore.from_env()
    try:
        store.initialize()
        report = ContradictionManager(store).open_report(
            task_id=task_id,
            facts=fact,
            summary=summary,
            affected_artifacts=affected_artifact or [],
            evidence_ids=evidence_id or [],
            owner=owner,
            proposed_resolution=proposed_resolution,
            stigmem_conflict_id=stigmem_conflict_id,
        )
    finally:
        store.close()

    typer.echo(json.dumps(report.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True))


@contradictions_app.command("list")
def contradiction_list(
    task_id: Annotated[
        str | None,
        typer.Option("--task-id", help="Only include reports for this task."),
    ] = None,
    status: Annotated[
        str | None,
        typer.Option("--status", help="Only include reports with this status."),
    ] = None,
) -> None:
    """List local contradiction reports."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        reports = ContradictionManager(store).list_reports(
            task_id=task_id,
            status=_contradiction_status(status) if status else None,
        )
    finally:
        store.close()

    payload = [report.model_dump(mode="json", by_alias=True) for report in reports]
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@contradictions_app.command("show")
def contradiction_show(report_id: str) -> None:
    """Show one local contradiction report and linked evidence."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        manager = ContradictionManager(store)
        report = manager.get_report(report_id)
        evidence = manager.evidence_for(report_id)
    except ContradictionNotFoundError as error:
        raise typer.BadParameter(str(error)) from None
    finally:
        store.close()

    payload = {
        "contradiction": report.model_dump(mode="json", by_alias=True),
        "evidence": [item.model_dump(mode="json", by_alias=True) for item in evidence],
    }
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@graph_app.command("export")
def graph_export(
    task_id: Annotated[
        str | None,
        typer.Option("--task-id", help="Only export graph objects for this task."),
    ] = None,
) -> None:
    """Export the local work graph as deterministic JSON."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        export = WorkGraphExporter(store).export(task_id=task_id)
    except WorkGraphTaskNotFoundError as error:
        raise typer.BadParameter(str(error)) from None
    finally:
        store.close()

    typer.echo(json.dumps(export.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True))


@policy_app.command("show")
def policy_show(
    task_id: Annotated[
        str,
        typer.Option("--task-id", help="Task id for the envelope."),
    ] = "task_preview",
    actor: Annotated[
        str,
        typer.Option("--actor", help="Actor for the envelope."),
    ] = "agent:preview",
    profile: Annotated[
        str,
        typer.Option("--profile", help="Policy profile: strict, trusted-local, or automation."),
    ] = "strict",
    trusted_local_fail_open: Annotated[
        bool,
        typer.Option(
            "--trusted-local-fail-open",
            help="Explicitly opt in to trusted-local fail-open semantics.",
        ),
    ] = False,
    include_receipt: Annotated[
        bool,
        typer.Option("--include-receipt", help="Include the fail-open receipt when applicable."),
    ] = False,
) -> None:
    """Print a generated policy envelope."""
    policy_profile = _policy_profile(profile)
    try:
        envelope = generate_policy_envelope(
            task_id=task_id,
            actor=actor,
            profile=policy_profile,
            trusted_local_fail_open=trusted_local_fail_open,
        )
    except FailOpenNotAllowedError as error:
        raise typer.BadParameter(str(error)) from None

    payload: dict[str, object] = {
        "policy_envelope": envelope.model_dump(mode="json", by_alias=True),
    }
    if include_receipt and envelope.fail_open:
        receipt = fail_open_receipt(
            task_id=task_id,
            actor=actor,
            target=profile,
            reason="Policy preview requested fail-open receipt.",
        )
        payload["receipt"] = receipt.model_dump(mode="json", by_alias=True)
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@policy_app.command("test")
def policy_test() -> None:
    """Run policy regression checks required for release gates."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        report = PolicyTestHarness(store).run()
    finally:
        store.close()

    payload = report.to_payload()
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    if report.status != "passed":
        raise typer.Exit(code=1)



def _policy_profile(value: str) -> PolicyProfile:
    if value not in {"strict", "trusted-local", "automation", "custom"}:
        raise typer.BadParameter(f"unsupported policy profile: {value}")
    return cast(PolicyProfile, value)


def _contradiction_status(value: str) -> ContradictionStatus:
    if value not in {"open", "resolved", "ignored"}:
        raise typer.BadParameter(f"unsupported contradiction status: {value}")
    return cast(ContradictionStatus, value)
