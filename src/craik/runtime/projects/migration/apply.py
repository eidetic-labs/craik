"""Adjacent-runtime migration apply helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from craik.contracts.models import AgentSessionState
from craik.runtime.paths import resolve_craik_paths
from craik.runtime.projects.import_dry_run import ImportMappedRecord
from craik.runtime.projects.migration.adjacent_runtime import (
    MigrationKind,
    plan_adjacent_runtime_migration,
)
from craik.runtime.store import LocalStore


@dataclass(frozen=True)
class AppliedMigrationRecord:
    """One record materialized into Craik state by migration apply."""

    source_id: str
    target_schema: str
    target_id: str
    status: str
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "target_schema": self.target_schema,
            "target_id": self.target_id,
            "status": self.status,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class AppliedMigration:
    """Structured result for an adjacent-runtime migration apply."""

    id: str
    source_name: str
    applied_records: tuple[AppliedMigrationRecord, ...]
    warnings: tuple[str, ...]
    mutated_state: bool = True
    mutated_source: bool = False
    redacted: bool = True

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "source_name": self.source_name,
            "applied_records": [record.as_dict() for record in self.applied_records],
            "warnings": list(self.warnings),
            "mutated_state": self.mutated_state,
            "mutated_source": self.mutated_source,
            "redacted": self.redacted,
        }


def apply_adjacent_runtime_migration(
    source: Path,
    *,
    kind: MigrationKind = "agent-runtime",
    include_records: set[str] | None = None,
    include_secrets: bool = False,
    env: dict[str, str] | None = None,
) -> AppliedMigration:
    """Apply importable adjacent-runtime records into Craik state without mutating source."""
    report = plan_adjacent_runtime_migration(source, kind=kind)
    if report.errors:
        raise ValueError("migration plan contains errors; inspect with `craik migrate plan`")
    candidates = {candidate.source_id: candidate for candidate in report.candidates}
    selected = [
        record
        for record in report.mapped_records
        if record.status != "unsupported"
        and (include_records is None or record.source_id in include_records)
    ]
    if include_records is not None:
        missing = sorted(include_records - {record.source_id for record in report.mapped_records})
        if missing:
            raise ValueError(f"unknown migration record id(s): {', '.join(missing)}")

    paths = resolve_craik_paths(env)
    store = LocalStore.from_paths(paths)
    applied: list[AppliedMigrationRecord] = []
    try:
        store.initialize()
        for record in selected:
            candidate = candidates.get(record.source_id)
            if candidate and candidate.source_type == "agent":
                _put_migrated_agent_session(store, record)
                applied.append(
                    AppliedMigrationRecord(
                        source_id=record.source_id,
                        target_schema=record.target_schema,
                        target_id=record.target_id,
                        status="applied",
                        warnings=tuple(record.warnings),
                    )
                )
                continue
            source_type = candidate.source_type if candidate else "unknown"
            skipped_warning = (
                f"migration apply does not yet support source_type={source_type!r}; "
                "record was not written to Craik state"
            )
            applied.append(
                AppliedMigrationRecord(
                    source_id=record.source_id,
                    target_schema=record.target_schema,
                    target_id=record.target_id,
                    status="skipped",
                    warnings=(*record.warnings, skipped_warning),
                )
            )
    finally:
        store.close()

    warnings = list(report.warnings)
    if not include_secrets:
        warnings.append("secret-like fields were not imported; reconfigure credentials manually")
    manifest = AppliedMigration(
        id=report.id.replace("import_dry_run_", "import_apply_"),
        source_name=report.source_name,
        applied_records=tuple(applied),
        warnings=tuple(warnings),
    )
    _write_apply_manifest(paths.config / "migrations", manifest)
    return manifest


def apply_payload(result: AppliedMigration) -> dict[str, Any]:
    """Return a JSON-ready apply result."""
    return result.as_dict()


def format_apply_text(result: AppliedMigration) -> list[str]:
    """Render migration apply output for operators."""
    lines = [
        f"Migration applied: {result.id}",
        f"Source: {result.source_name}",
        f"Processed records: {len(result.applied_records)}",
        "Mutated source: no",
        "Mutated Craik state: yes",
    ]
    if result.warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in result.warnings)
    if result.applied_records:
        lines.append("Processed records:")
        lines.extend(
            f"- {record.source_id} [{record.status}] -> {record.target_schema}/{record.target_id}"
            for record in result.applied_records
        )
    return lines


def _put_migrated_agent_session(store: LocalStore, record: ImportMappedRecord) -> None:
    timestamp = datetime.now(UTC)
    state = AgentSessionState(
        id=record.target_id,
        operator_subject="migration:adjacent-runtime",
        provider_id="provider_migrated",
        mode="foreground",
        status="idle",
        started_at=timestamp,
        last_activity_at=timestamp,
        updated_at=timestamp,
        supervision_notes=[f"Migrated from adjacent runtime source {record.source_id}."],
    )
    store.put_agent_session_state(state)


def _write_apply_manifest(directory: Path, result: AppliedMigration) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{result.id}.json").write_text(
        json.dumps(result.as_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
