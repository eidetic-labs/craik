"""Read-only operator surface CLI commands."""

from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from typing import Annotated, Any, cast

import typer

from craik.cli import operator_app
from craik.contracts.models import ContradictionStatus
from craik.runtime.companions.operator_views import (
    BudgetQuotaSnapshot,
    InstructionDistillationSnapshot,
    MemoryImpactPreviewSnapshot,
    OperatorSurfaceSnapshot,
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
from craik.runtime.store import LocalStore
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
    store = LocalStore.from_env()
    try:
        store.initialize()
        snapshot = build_operator_surface_snapshot(store, project_id=project_id)
    finally:
        store.close()

    if section_id is not None:
        snapshot = _require_section(snapshot, section_id)

    if json_output:
        typer.echo(json.dumps(_json_ready(snapshot), indent=2, sort_keys=True))
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
    store = LocalStore.from_env()
    try:
        store.initialize()
        export = WorkGraphExporter(store).export(task_id=task_id)
    except WorkGraphTaskNotFoundError as error:
        raise typer.BadParameter(str(error)) from None
    finally:
        store.close()

    if json_output:
        typer.echo(
            json.dumps(export.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True)
        )
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
    store = LocalStore.from_env()
    try:
        store.initialize()
        handoff = HandoffWriter(store).require(handoff_or_task_id)
    except HandoffNotFoundError as error:
        raise typer.BadParameter(str(error)) from None
    finally:
        store.close()

    if json_output:
        typer.echo(
            json.dumps(handoff.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True)
        )
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
    store = LocalStore.from_env()
    try:
        store.initialize()
        receipt = store.get_receipt(receipt_id) or store.get_plugin_receipt(receipt_id)
    finally:
        store.close()

    if receipt is None:
        raise typer.BadParameter(f"unknown receipt: {receipt_id}")
    if json_output:
        typer.echo(
            json.dumps(receipt.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True)
        )
    else:
        typer.echo("\n".join(format_receipt_viewer(receipt)))


@operator_app.command("contradictions")
def operator_contradictions(
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
    json_output: Annotated[
        bool,
        typer.Option("--json/--view", help="Print JSON instead of the operator view."),
    ] = False,
) -> None:
    """Print the read-only contradiction inbox."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        reports = ContradictionManager(store).list_reports(
            task_id=task_id,
            status=_contradiction_status(status) if status else None,
        )
    finally:
        store.close()

    if json_output:
        payload = [report.model_dump(mode="json", by_alias=True) for report in reports]
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        typer.echo("\n".join(format_contradiction_inbox(reports)))


@operator_app.command("evidence")
def operator_evidence(
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
    store = LocalStore.from_env()
    try:
        store.initialize()
        evidence = store.list_evidence()
        assumptions = store.list_assumptions()
    finally:
        store.close()

    if task_id is not None:
        evidence = [
            item for item in evidence if item.metadata.get("task_id") in {None, task_id}
        ]
        assumptions = [item for item in assumptions if item.task_id == task_id]

    if json_output:
        payload = {
            "evidence": [item.model_dump(mode="json", by_alias=True) for item in evidence],
            "assumptions": [item.model_dump(mode="json", by_alias=True) for item in assumptions],
        }
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        typer.echo("\n".join(format_evidence_assumption_view(evidence, assumptions)))


@operator_app.command("delegations")
def operator_delegations(
    task_id: Annotated[
        str | None,
        typer.Option("--task-id", help="Only include delegation points for this task."),
    ] = None,
    status: Annotated[
        str | None,
        typer.Option("--status", help="Only include delegation points with this status."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json/--view", help="Print JSON instead of the operator view."),
    ] = False,
) -> None:
    """Print the read-only delegation queue."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        delegations = store.list_human_delegations()
    finally:
        store.close()

    if task_id is not None:
        delegations = [item for item in delegations if item.task_id == task_id]
    if status is not None:
        delegations = [item for item in delegations if item.status == status]

    if json_output:
        payload = [item.model_dump(mode="json", by_alias=True) for item in delegations]
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
    snapshot = BudgetQuotaSnapshot(
        missing=["cost", "tokens", "requests", "quota"],
        notes=[
            "No persisted budget or quota usage source is configured.",
            "Missing data is displayed explicitly and not inferred from logs.",
        ],
    )
    if json_output:
        typer.echo(json.dumps(_json_ready(snapshot), indent=2, sort_keys=True))
    else:
        typer.echo("\n".join(format_budget_quota_view(snapshot)))


@operator_app.command("instructions")
def operator_instructions(
    json_output: Annotated[
        bool,
        typer.Option("--json/--view", help="Print JSON instead of the operator view."),
    ] = False,
) -> None:
    """Print the read-only instruction distillation view."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        snapshot = InstructionDistillationSnapshot(
            sources=store.list_instruction_sources(),
            snapshots=store.list_instruction_source_snapshots(),
            provenance=store.list_instruction_provenance(),
            proposals=store.list_distilled_instruction_proposals(),
            reviews=store.list_instruction_promotion_reviews(),
        )
    finally:
        store.close()

    if json_output:
        typer.echo(json.dumps(_json_ready(snapshot), indent=2, sort_keys=True))
    else:
        typer.echo("\n".join(format_instruction_distillation_view(snapshot)))


@operator_app.command("quality")
def operator_quality(
    json_output: Annotated[
        bool,
        typer.Option("--json/--view", help="Print JSON instead of the operator view."),
    ] = False,
) -> None:
    """Print the read-only quality gate view."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        snapshot = QualityGateSnapshot(
            handoff_scores=store.list_handoff_quality_scores(),
            evidence_scores=store.list_evidence_coverage_scores(),
            critic_findings=store.list_runtime_critic_findings(),
            red_team_findings=store.list_red_team_findings(),
        )
    finally:
        store.close()

    if json_output:
        typer.echo(json.dumps(_json_ready(snapshot), indent=2, sort_keys=True))
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
        typer.echo(json.dumps(_json_ready(snapshot), indent=2, sort_keys=True))
    else:
        typer.echo("\n".join(format_memory_impact_preview_view(snapshot)))


def _require_section(
    snapshot: OperatorSurfaceSnapshot,
    section_id: str,
) -> OperatorSurfaceSnapshot:
    sections = [section for section in snapshot.sections if section.id == section_id]
    if not sections:
        known = ", ".join(section.id for section in snapshot.sections)
        raise typer.BadParameter(f"unknown operator section {section_id!r}; known: {known}")
    return OperatorSurfaceSnapshot(
        project_id=snapshot.project_id,
        read_only=snapshot.read_only,
        sections=sections,
        notes=snapshot.notes,
    )


def _contradiction_status(value: str) -> ContradictionStatus:
    if value not in {"open", "resolved", "ignored"}:
        raise typer.BadParameter(f"unsupported contradiction status: {value}")
    return cast(ContradictionStatus, value)


def _json_ready(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    if is_dataclass(value):
        return {
            field.name: _json_ready(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    return value
