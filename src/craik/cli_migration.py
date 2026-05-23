"""Migration command surfaces."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from craik.cli import migrate_app
from craik.runtime.projects.migration.adjacent_runtime import (
    dry_run_payload,
    format_dry_run_text,
    format_inspection_text,
    inspect_adjacent_runtime_source,
    inspection_payload,
    plan_adjacent_runtime_migration,
    report_adjacent_runtime_migration,
)
from craik.runtime.projects.migration.apply import (
    apply_adjacent_runtime_migration,
    apply_payload,
    format_apply_text,
)
from craik.runtime.projects.migration.reports import format_migration_report


@migrate_app.command("inspect")
def migrate_inspect(
    source: Annotated[Path, typer.Option("--source", help="Adjacent runtime source path.")],
    kind: Annotated[str, typer.Option("--kind", help="Migration source kind.")] = (
        "agent-runtime"
    ),
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON output."),
    ] = False,
) -> None:
    """Inspect an adjacent runtime source without mutating it."""
    _validate_kind(kind)
    try:
        inspection = inspect_adjacent_runtime_source(source, kind="agent-runtime")
    except (FileNotFoundError, ValueError) as error:
        raise typer.BadParameter(str(error)) from None
    if json_output:
        typer.echo(json.dumps(inspection_payload(inspection), indent=2, sort_keys=True))
        return
    typer.echo("\n".join(format_inspection_text(inspection)))


@migrate_app.command("plan")
def migrate_plan(
    source: Annotated[Path, typer.Option("--source", help="Adjacent runtime source path.")],
    kind: Annotated[str, typer.Option("--kind", help="Migration source kind.")] = (
        "agent-runtime"
    ),
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON output."),
    ] = False,
) -> None:
    """Plan an adjacent runtime migration without mutating source or Craik state."""
    _validate_kind(kind)
    try:
        report = plan_adjacent_runtime_migration(source, kind="agent-runtime")
    except (FileNotFoundError, ValueError) as error:
        raise typer.BadParameter(str(error)) from None
    if json_output:
        typer.echo(json.dumps(dry_run_payload(report), indent=2, sort_keys=True))
        return
    typer.echo("\n".join(format_dry_run_text(report)))


@migrate_app.command("import")
def migrate_import(
    source: Annotated[Path, typer.Option("--source", help="Adjacent runtime source path.")],
    kind: Annotated[str, typer.Option("--kind", help="Migration source kind.")] = (
        "agent-runtime"
    ),
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run/--apply", help="Preview import actions without writing state."),
    ] = True,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON output."),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option("--yes", help="Apply without an interactive confirmation prompt."),
    ] = False,
    include_records: Annotated[
        str | None,
        typer.Option(
            "--include-records",
            help="Comma-separated source record ids to apply; defaults to all importable records.",
        ),
    ] = None,
    include_secrets: Annotated[
        bool,
        typer.Option(
            "--include-secrets",
            help="Acknowledge secret-bearing records; secret values are still not copied.",
        ),
    ] = False,
) -> None:
    """Run an adjacent runtime import dry-run or explicitly apply importable records."""
    _validate_kind(kind)
    try:
        if dry_run:
            report = plan_adjacent_runtime_migration(source, kind="agent-runtime")
        else:
            selected = _parse_include_records(include_records)
            if not yes and not typer.confirm(
                "Apply importable adjacent-runtime records into Craik state?",
                default=False,
            ):
                raise typer.Abort()
            result = apply_adjacent_runtime_migration(
                source,
                kind="agent-runtime",
                include_records=selected,
                include_secrets=include_secrets,
            )
            if json_output:
                typer.echo(json.dumps(apply_payload(result), indent=2, sort_keys=True))
                return
            typer.echo("\n".join(format_apply_text(result)))
            return
    except (FileNotFoundError, ValueError) as error:
        raise typer.BadParameter(str(error)) from None
    if json_output:
        typer.echo(json.dumps(dry_run_payload(report), indent=2, sort_keys=True))
        return
    typer.echo("\n".join(format_dry_run_text(report)))


@migrate_app.command("report")
def migrate_report(
    source: Annotated[Path, typer.Option("--source", help="Adjacent runtime source path.")],
    kind: Annotated[str, typer.Option("--kind", help="Migration source kind.")] = (
        "agent-runtime"
    ),
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON output."),
    ] = False,
    locale: Annotated[
        str | None,
        typer.Option("--locale", help="Locale for text output. Defaults to CRAIK_LOCALE."),
    ] = None,
) -> None:
    """Render a safe-to-share adjacent runtime migration report."""
    _validate_kind(kind)
    try:
        report = report_adjacent_runtime_migration(source, kind="agent-runtime")
    except (FileNotFoundError, ValueError) as error:
        raise typer.BadParameter(str(error)) from None
    if json_output:
        typer.echo(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
        return
    typer.echo("\n".join(format_migration_report(report, locale=locale)))


def _validate_kind(kind: str) -> None:
    if kind != "agent-runtime":
        raise typer.BadParameter(f"unsupported migration kind: {kind}")


def _parse_include_records(value: str | None) -> set[str] | None:
    if value is None:
        return None
    records = {item.strip() for item in value.split(",") if item.strip()}
    return records or None
