"""Contradiction, graph, handoff, memory, and policy CLI commands."""

from __future__ import annotations

import json
from importlib import import_module
from typing import Annotated, cast

import typer

from craik.cli import contradictions_app, graph_app, memory_app, policy_app
from craik.cli_operator_auth import operator_identity_or_fail
from craik.contracts.models import (
    ContradictionStatus,
    MemoryScope,
    PolicyProfile,
    ProposalOperation,
    TrustClass,
)
from craik.runtime.memory.contradictions import ContradictionManager, ContradictionNotFoundError
from craik.runtime.memory.memory import (
    EvidenceRequiredError,
    LocalMemoryStore,
    MemoryProposalNotFoundError,
    build_memory_diff,
    create_proposal,
    evidence_reference,
    preview_memory_impact,
)
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


@memory_app.command("propose")
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
) -> None:
    """Create a reviewable local memory proposal."""
    operator_identity_or_fail()
    evidence = evidence_reference(
        task_id=task_id,
        source=evidence_source,
        locator=evidence_locator,
        summary=evidence_summary,
    )
    proposal = create_proposal(
        task_id=task_id,
        entity=entity,
        relation=relation,
        value=value,
        source=source,
        confidence=confidence,
        scope=_memory_scope(scope),
        trust_class=_trust_class(trust_class),
        operation=_proposal_operation(operation),
        evidence=[evidence],
    )
    store = LocalStore.from_env()
    try:
        store.initialize()
        proposal = LocalMemoryStore(store).propose(proposal)
    finally:
        store.close()

    typer.echo(
        json.dumps(proposal.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True)
    )


@memory_app.command("list")
def memory_list(
    task_id: Annotated[
        str | None,
        typer.Option("--task-id", help="Only include proposals for this task id."),
    ] = None,
    status: Annotated[
        str | None,
        typer.Option("--status", help="Only include proposals with this status."),
    ] = None,
) -> None:
    """List local memory proposals."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        proposals = LocalMemoryStore(store).list_proposals(task_id=task_id, status=status)
    finally:
        store.close()

    payload = [proposal.model_dump(mode="json", by_alias=True) for proposal in proposals]
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@memory_app.command("show")
def memory_show(proposal_id: str) -> None:
    """Show one local memory proposal."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        proposal = LocalMemoryStore(store).get_proposal(proposal_id)
    finally:
        store.close()

    if proposal is None:
        raise typer.BadParameter(f"unknown memory proposal: {proposal_id}")
    typer.echo(
        json.dumps(proposal.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True)
    )


@memory_app.command("approve")
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
) -> None:
    """Approve a local memory proposal for local search."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        proposal = LocalMemoryStore(store).approve(
            proposal_id,
            decided_by=decided_by,
            reason=reason,
        )
    except (MemoryProposalNotFoundError, EvidenceRequiredError) as error:
        raise typer.BadParameter(str(error)) from None
    finally:
        store.close()

    typer.echo(
        json.dumps(proposal.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True)
    )


@memory_app.command("reject")
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
) -> None:
    """Reject a local memory proposal."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        proposal = LocalMemoryStore(store).reject(
            proposal_id,
            decided_by=decided_by,
            reason=reason,
        )
    except MemoryProposalNotFoundError as error:
        raise typer.BadParameter(str(error)) from None
    finally:
        store.close()

    typer.echo(
        json.dumps(proposal.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True)
    )


@memory_app.command("search")
def memory_search(query: str) -> None:
    """Search approved local memory facts."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        facts = LocalMemoryStore(store).search(query)
    finally:
        store.close()

    payload = [fact.model_dump(mode="json", by_alias=True) for fact in facts]
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@memory_app.command("diff")
def memory_diff(task_id: str) -> None:
    """Print a run-scoped memory diff for local proposal activity."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        proposals = store.list_proposals()
        diff = build_memory_diff(task_id=task_id, proposals=proposals)
        store.put_memory_diff(diff)
    finally:
        store.close()

    typer.echo(json.dumps(diff.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True))


@memory_app.command("preview")
def memory_preview(task_id: str) -> None:
    """Preview local memory impact before promotion or direct writes."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        proposals = store.list_proposals()
        existing_facts = LocalMemoryStore(store).search("")
        preview = preview_memory_impact(
            task_id=task_id,
            proposals=proposals,
            existing_facts=existing_facts,
        )
        store.put_memory_impact_preview(preview)
    finally:
        store.close()

    typer.echo(json.dumps(preview.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True))


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


def _contradiction_status(value: str) -> ContradictionStatus:
    if value not in {"open", "resolved", "ignored"}:
        raise typer.BadParameter(f"unsupported contradiction status: {value}")
    return cast(ContradictionStatus, value)
