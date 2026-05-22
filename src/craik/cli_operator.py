"""Read-only operator surface CLI commands."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Annotated

import typer

from craik.cli import operator_app
from craik.runtime.companions.operator_views import (
    OperatorSurfaceSnapshot,
    build_operator_surface_snapshot,
    format_operator_surface_overview,
)
from craik.runtime.store import LocalStore


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
