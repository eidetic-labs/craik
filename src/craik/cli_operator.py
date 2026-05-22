"""Read-only operator surface CLI commands."""

from __future__ import annotations

import json
from typing import Annotated, cast

import typer

from craik.cli import operator_app
from craik.cli_operator_auth import operator_identity_or_fail
from craik.cli_operator_support import (
    contradiction_status,
    json_ready,
    project_scope,
    receipt_hmac_status,
    receipt_json,
    record_in_project,
    require_section,
    task_ids_for_project,
)
from craik.contracts.models import CapabilityReceipt, PluginReceipt
from craik.runtime.companions.operator_views import (
    BudgetQuotaSnapshot,
    InstructionDistillationSnapshot,
    MemoryImpactPreviewSnapshot,
    QualityGateSnapshot,
    build_operator_surface_snapshot,
    format_budget_quota_view,
    format_contradiction_inbox,
    format_delegation_queue,
    format_evidence_assumption_view,
    format_handoff_viewer,
    format_instruction_distillation_view,
    format_memory_impact_preview_view,
    format_operator_surface_overview,
    format_quality_gate_view,
    format_receipt_viewer,
    format_work_graph_explorer,
)
from craik.runtime.memory.contradictions import ContradictionManager
from craik.runtime.store import LocalStore, LocalStoreCorruptError
from craik.runtime.work.graph import WorkGraphExporter, WorkGraphTaskNotFoundError
from craik.runtime.work.handoffs import HandoffNotFoundError, HandoffWriter


@operator_app.command("overview")
def operator_overview(
    project_id: Annotated[
        str | None,
        typer.Option("--project", help="Only include records in this project scope."),
    ] = None,
    section_id: Annotated[
        str | None,
        typer.Option("--section", help="Only print one operator surface section."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json/--view", help="Print JSON instead of the operator view."),
    ] = False,
) -> None:
    """Print the read-only operator surface overview."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        snapshot = build_operator_surface_snapshot(store, project_id=project_id)
    finally:
        store.close()

    if section_id is not None:
        snapshot = require_section(snapshot, section_id)

    if json_output:
        typer.echo(json.dumps(json_ready(snapshot), indent=2, sort_keys=True))
    else:
        typer.echo("\n".join(format_operator_surface_overview(snapshot)))


@operator_app.command("work-graph")
def operator_work_graph(
    task_id: Annotated[
        str | None,
        typer.Option("--task-id", help="Only include graph objects for this task."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json/--view", help="Print JSON instead of the operator view."),
    ] = False,
) -> None:
    """Print the read-only work graph explorer."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        export = WorkGraphExporter(store).export(task_id=task_id)
    except WorkGraphTaskNotFoundError as error:
        raise typer.BadParameter(str(error)) from None
    finally:
        store.close()

    if json_output:
        typer.echo(json.dumps(json_ready(export), indent=2, sort_keys=True))
    else:
        typer.echo("\n".join(format_work_graph_explorer(export)))


@operator_app.command("handoff")
def operator_handoff(
    handoff_or_task_id: Annotated[
        str,
        typer.Argument(help="Handoff id or task id to inspect."),
    ],
    json_output: Annotated[
        bool,
        typer.Option("--json/--view", help="Print JSON instead of the operator view."),
    ] = False,
) -> None:
    """Print the read-only handoff viewer."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        handoff = HandoffWriter(store).require(handoff_or_task_id)
    except HandoffNotFoundError as error:
        raise typer.BadParameter(str(error)) from None
    finally:
        store.close()

    if json_output:
        typer.echo(json.dumps(json_ready(handoff), indent=2, sort_keys=True))
    else:
        typer.echo("\n".join(format_handoff_viewer(handoff)))


@operator_app.command("receipt")
def operator_receipt(
    receipt_id: Annotated[
        str,
        typer.Argument(help="Capability or plugin receipt id to inspect."),
    ],
    json_output: Annotated[
        bool,
        typer.Option("--json/--view", help="Print JSON instead of the operator view."),
    ] = False,
) -> None:
    """Print the read-only receipt viewer."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        receipt: CapabilityReceipt | PluginReceipt | None = store.get_receipt(receipt_id)
        hmac_status = receipt_hmac_status(receipt)
        if receipt is None:
            try:
                receipt = store.get_plugin_receipt(receipt_id)
                hmac_status = receipt_hmac_status(receipt)
            except LocalStoreCorruptError:
                raw_receipt = store.get_contract("craik.plugin_receipt", receipt_id)
                if raw_receipt is None:
                    raise
                receipt = cast(PluginReceipt, raw_receipt)
                hmac_status = "tampered"
    finally:
        store.close()

    if receipt is None:
        raise typer.BadParameter(f"unknown receipt: {receipt_id}")
    if json_output:
        typer.echo(json.dumps(receipt_json(receipt, hmac_status), indent=2, sort_keys=True))
    else:
        typer.echo("\n".join(format_receipt_viewer(receipt, hmac_status=hmac_status)))


@operator_app.command("contradictions")
def operator_contradictions(
    project_id: Annotated[
        str | None,
        typer.Option("--project", help="Only include reports in this project scope."),
    ] = None,
    task_id: Annotated[
        str | None,
        typer.Option("--task-id", help="Only include reports for this task."),
    ] = None,
    status: Annotated[
        str | None,
        typer.Option(
            "--status",
            help="Only include reports with status open, resolved, or ignored.",
        ),
    ] = None,
    include_all: Annotated[
        bool,
        typer.Option("--all", help="Include reports owned by other operators."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json/--view", help="Print JSON instead of the operator view."),
    ] = False,
) -> None:
    """Print the read-only contradiction inbox."""
    operator_identity = operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        resolved_project_id = project_scope(store, project_id)
        task_ids = task_ids_for_project(store, resolved_project_id)
        reports = ContradictionManager(store).list_reports(
            task_id=task_id,
            status=contradiction_status(status) if status else None,
        )
    finally:
        store.close()

    if resolved_project_id is not None:
        reports = [
            item
            for item in reports
            if record_in_project(item, resolved_project_id, task_ids)
        ]
    if not include_all:
        reports = [
            item for item in reports if item.owner in {None, operator_identity}
        ]

    if json_output:
        payload = json_ready(reports)
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        typer.echo("\n".join(format_contradiction_inbox(reports)))


@operator_app.command("evidence")
def operator_evidence(
    project_id: Annotated[
        str | None,
        typer.Option("--project", help="Only include records in this project scope."),
    ] = None,
    task_id: Annotated[
        str | None,
        typer.Option(
            "--task-id",
            help="Only include assumptions and scoped evidence for this task.",
        ),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json/--view", help="Print JSON instead of the operator view."),
    ] = False,
) -> None:
    """Print the read-only evidence and assumption view."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        resolved_project_id = project_scope(store, project_id)
        task_ids = task_ids_for_project(store, resolved_project_id)
        evidence = store.list_evidence()
        assumptions = store.list_assumptions()
    finally:
        store.close()

    if resolved_project_id is not None:
        evidence = [
            item for item in evidence if record_in_project(item, resolved_project_id, task_ids)
        ]
        assumptions = [
            item
            for item in assumptions
            if record_in_project(item, resolved_project_id, task_ids)
        ]
    if task_id is not None:
        evidence = [
            item for item in evidence if item.metadata.get("task_id") in {None, task_id}
        ]
        assumptions = [item for item in assumptions if item.task_id == task_id]

    if json_output:
        payload = {
            "evidence": json_ready(evidence),
            "assumptions": json_ready(assumptions),
        }
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        typer.echo("\n".join(format_evidence_assumption_view(evidence, assumptions)))


@operator_app.command("delegations")
def operator_delegations(
    project_id: Annotated[
        str | None,
        typer.Option("--project", help="Only include records in this project scope."),
    ] = None,
    task_id: Annotated[
        str | None,
        typer.Option("--task-id", help="Only include delegation points for this task."),
    ] = None,
    status: Annotated[
        str | None,
        typer.Option("--status", help="Only include delegation points with this status."),
    ] = None,
    include_all: Annotated[
        bool,
        typer.Option("--all", help="Include delegation points owned by other operators."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json/--view", help="Print JSON instead of the operator view."),
    ] = False,
) -> None:
    """Print the read-only delegation queue."""
    operator_identity = operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        resolved_project_id = project_scope(store, project_id)
        task_ids = task_ids_for_project(store, resolved_project_id)
        delegations = store.list_human_delegations()
    finally:
        store.close()

    if resolved_project_id is not None:
        delegations = [
            item
            for item in delegations
            if record_in_project(item, resolved_project_id, task_ids)
        ]
    if task_id is not None:
        delegations = [item for item in delegations if item.task_id == task_id]
    if status is not None:
        delegations = [item for item in delegations if item.status == status]
    if not include_all:
        delegations = [
            item for item in delegations if item.owner in {None, operator_identity}
        ]

    if json_output:
        payload = json_ready(delegations)
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        typer.echo("\n".join(format_delegation_queue(delegations)))


@operator_app.command("budget")
def operator_budget(
    json_output: Annotated[
        bool,
        typer.Option("--json/--view", help="Print JSON instead of the operator view."),
    ] = False,
) -> None:
    """Print the read-only budget and quota view."""
    operator_identity_or_fail()
    snapshot = BudgetQuotaSnapshot(
        missing=["cost", "tokens", "requests", "quota"],
        notes=[
            "No persisted budget or quota usage source is configured.",
            "Missing data is displayed explicitly and not inferred from logs.",
        ],
    )
    if json_output:
        typer.echo(json.dumps(json_ready(snapshot), indent=2, sort_keys=True))
    else:
        typer.echo("\n".join(format_budget_quota_view(snapshot)))


@operator_app.command("instructions")
def operator_instructions(
    project_id: Annotated[
        str | None,
        typer.Option("--project", help="Only include records in this project scope."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json/--view", help="Print JSON instead of the operator view."),
    ] = False,
) -> None:
    """Print the read-only instruction distillation view."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        resolved_project_id = project_scope(store, project_id)
        snapshot = InstructionDistillationSnapshot(
            sources=[
                item
                for item in store.list_instruction_sources()
                if record_in_project(item, resolved_project_id)
            ],
            snapshots=[
                item
                for item in store.list_instruction_source_snapshots()
                if record_in_project(item, resolved_project_id)
            ],
            provenance=[
                item
                for item in store.list_instruction_provenance()
                if record_in_project(item, resolved_project_id)
            ],
            proposals=[
                item
                for item in store.list_distilled_instruction_proposals()
                if record_in_project(item, resolved_project_id)
            ],
            reviews=[
                item
                for item in store.list_instruction_promotion_reviews()
                if record_in_project(item, resolved_project_id)
            ],
        )
    finally:
        store.close()

    if json_output:
        typer.echo(json.dumps(json_ready(snapshot), indent=2, sort_keys=True))
    else:
        typer.echo("\n".join(format_instruction_distillation_view(snapshot)))


@operator_app.command("quality")
def operator_quality(
    project_id: Annotated[
        str | None,
        typer.Option("--project", help="Only include records in this project scope."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json/--view", help="Print JSON instead of the operator view."),
    ] = False,
) -> None:
    """Print the read-only quality gate view."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        resolved_project_id = project_scope(store, project_id)
        task_ids = task_ids_for_project(store, resolved_project_id)
        snapshot = QualityGateSnapshot(
            handoff_scores=[
                item
                for item in store.list_handoff_quality_scores()
                if record_in_project(item, resolved_project_id, task_ids)
            ],
            evidence_scores=[
                item
                for item in store.list_evidence_coverage_scores()
                if record_in_project(item, resolved_project_id, task_ids)
            ],
            critic_findings=[
                item
                for item in store.list_runtime_critic_findings()
                if record_in_project(item, resolved_project_id, task_ids)
            ],
            red_team_findings=[
                item
                for item in store.list_red_team_findings()
                if record_in_project(item, resolved_project_id, task_ids)
            ],
        )
    finally:
        store.close()

    if json_output:
        typer.echo(json.dumps(json_ready(snapshot), indent=2, sort_keys=True))
    else:
        typer.echo("\n".join(format_quality_gate_view(snapshot)))


@operator_app.command("memory-impact")
def operator_memory_impact(
    preview_id: Annotated[
        str,
        typer.Argument(help="Memory impact preview id to inspect."),
    ],
    json_output: Annotated[
        bool,
        typer.Option("--json/--view", help="Print JSON instead of the operator view."),
    ] = False,
) -> None:
    """Print the read-only memory impact preview view."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        preview = store.get_memory_impact_preview(preview_id)
        if preview is None:
            raise typer.BadParameter(f"unknown memory impact preview: {preview_id}")
        snapshot = MemoryImpactPreviewSnapshot(
            preview=preview,
            proposals=[
                proposal
                for proposal in store.list_proposals()
                if proposal.task_id == preview.task_id
            ],
        )
    finally:
        store.close()

    if json_output:
        typer.echo(json.dumps(json_ready(snapshot), indent=2, sort_keys=True))
    else:
        typer.echo("\n".join(format_memory_impact_preview_view(snapshot)))
