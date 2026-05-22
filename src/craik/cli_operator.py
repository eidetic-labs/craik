"""Read-only operator surface CLI commands."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Annotated, cast

import typer

from craik.cli import operator_app
from craik.contracts.models import ContradictionStatus
from craik.runtime.companions.operator_views import (
    OperatorSurfaceSnapshot,
    build_operator_surface_snapshot,
    format_contradiction_inbox,
    format_handoff_viewer,
    format_operator_surface_overview,
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
        typer.echo(json.dumps(asdict(snapshot), indent=2, sort_keys=True))
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
