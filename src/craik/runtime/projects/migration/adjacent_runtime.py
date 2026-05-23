"""Read-only adjacent-runtime migration inspection and planning."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from craik.runtime.projects.import_dry_run import (
    ImportCandidateRecord,
    ImportDryRunReport,
    ImportMappedRecord,
    import_dry_run_report,
)
from craik.runtime.projects.migration.reports import (
    MigrationReport,
    build_migration_report,
)
from craik.runtime.projects.migration_maps import (
    MigrationPlanMap,
    migration_map_for_object,
    migration_plan_map,
)

MigrationKind = Literal["agent-runtime"]
_MAX_MIGRATION_FILES = 10_000
_MAX_MIGRATION_DEPTH = 16

SECRET_MARKERS = (
    "api_key",
    "apikey",
    "auth_token",
    "credential",
    "password",
    "private_key",
    "secret",
    "token",
)

TARGET_SCHEMA_BY_SOURCE_TYPE = {
    "agent": "craik.agent_profile",
    "approval": "craik.approval_policy",
    "channel": "craik.channel_binding",
    "config": "craik.runtime_config",
    "fallback": "craik.model_fallback_chain",
    "gateway": "craik.gateway_config",
    "memory": "craik.memory_record",
    "model": "craik.model_provider",
    "profile": "craik.profile",
    "schedule": "craik.schedule",
    "sandbox": "craik.sandbox_config",
    "session": "craik.agent_session",
    "skill": "craik.skill_package",
}


class MigrationSourceTooLarge(RuntimeError):
    """Raised when an adjacent runtime source exceeds bounded scan limits."""


@dataclass(frozen=True)
class AdjacentRuntimeSourceRecord:
    """One source object discovered in an adjacent runtime export."""

    source_id: str
    source_type: str
    path: str
    summary: str
    secret_fields: tuple[str, ...] = ()

    @property
    def contains_secret(self) -> bool:
        return bool(self.secret_fields)


@dataclass(frozen=True)
class AdjacentRuntimeInspection:
    """Read-only source inspection result."""

    source: str
    kind: MigrationKind
    records: tuple[AdjacentRuntimeSourceRecord, ...]
    warnings: tuple[str, ...] = ()

    @property
    def secret_record_count(self) -> int:
        return sum(1 for record in self.records if record.contains_secret)


def inspect_adjacent_runtime_source(
    source: Path,
    *,
    kind: MigrationKind = "agent-runtime",
) -> AdjacentRuntimeInspection:
    """Inspect an adjacent runtime source without mutating it."""
    resolved = source.expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"migration source does not exist: {source}")
    if kind != "agent-runtime":
        raise ValueError(f"unsupported migration kind: {kind}")

    records: list[AdjacentRuntimeSourceRecord] = []
    warnings: list[str] = []
    for path in _json_source_files(resolved):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            warnings.append(f"{path.relative_to(resolved)}: skipped invalid JSON ({error.msg})")
            continue
        records.extend(_records_from_payload(payload, root=resolved, path=path))

    if not records:
        warnings.append("no importable JSON runtime records discovered")

    return AdjacentRuntimeInspection(
        source=str(resolved),
        kind=kind,
        records=tuple(records),
        warnings=tuple(warnings),
    )


def plan_adjacent_runtime_migration(
    source: Path,
    *,
    kind: MigrationKind = "agent-runtime",
) -> ImportDryRunReport:
    """Create a deterministic dry-run report for an adjacent runtime source."""
    inspection = inspect_adjacent_runtime_source(source, kind=kind)
    candidates = [
        ImportCandidateRecord(
            source_id=record.source_id,
            source_type=record.source_type,
            summary=record.summary,
            redacted=True,
        )
        for record in inspection.records
    ]
    mapped_records = [_mapped_record(record) for record in inspection.records]
    warnings = list(inspection.warnings)
    warnings.extend(
        f"{record.source_id}: secret-like fields skipped ({', '.join(record.secret_fields)})"
        for record in inspection.records
        if record.secret_fields
    )
    errors = [
        f"{record.source_id}: unsupported source type {record.source_type}"
        for record in inspection.records
        if _target_schema(record.source_type) is None
    ]

    return import_dry_run_report(
        report_id=f"import_dry_run_{_stable_id(inspection.source)}",
        source_name=Path(inspection.source).name,
        source_kind=kind,
        candidates=candidates,
        mapped_records=mapped_records,
        warnings=warnings,
        errors=errors,
        policy_envelope_id="policy_adjacent_runtime_migration",
        evidence_ids=["evidence_adjacent_runtime_source"],
        receipt_ids=["receipt_adjacent_runtime_dry_run"],
    )


def plan_adjacent_runtime_object_map(
    source: Path,
    *,
    kind: MigrationKind = "agent-runtime",
) -> MigrationPlanMap:
    """Create an object-level migration map for an adjacent runtime source."""
    inspection = inspect_adjacent_runtime_source(source, kind=kind)
    objects = [
        migration_map_for_object(
            source_id=record.source_id,
            source_type=record.source_type,
            secret_fields=list(record.secret_fields),
        )
        for record in inspection.records
    ]
    return migration_plan_map(
        plan_id=f"migration_plan_map_{_stable_id(inspection.source)}",
        source_name=Path(inspection.source).name,
        objects=objects,
    )


def report_adjacent_runtime_migration(
    source: Path,
    *,
    kind: MigrationKind = "agent-runtime",
) -> MigrationReport:
    """Create a safe-to-share migration report for an adjacent runtime source."""
    return build_migration_report(plan_adjacent_runtime_object_map(source, kind=kind))


def inspection_payload(inspection: AdjacentRuntimeInspection) -> dict[str, Any]:
    """Return a JSON-ready inspection payload."""
    return {
        "source": inspection.source,
        "kind": inspection.kind,
        "record_count": len(inspection.records),
        "secret_record_count": inspection.secret_record_count,
        "records": [
            {
                "source_id": record.source_id,
                "source_type": record.source_type,
                "path": record.path,
                "summary": record.summary,
                "contains_secret": record.contains_secret,
                "secret_fields": list(record.secret_fields),
            }
            for record in inspection.records
        ],
        "warnings": list(inspection.warnings),
    }


def dry_run_payload(report: ImportDryRunReport) -> dict[str, Any]:
    """Return a JSON-ready dry-run payload."""
    return report.model_dump(mode="json", by_alias=True)


def format_inspection_text(inspection: AdjacentRuntimeInspection) -> list[str]:
    """Render inspection output for operators."""
    lines = [
        f"Migration source: {inspection.source}",
        f"Kind: {inspection.kind}",
        f"Records: {len(inspection.records)}",
        f"Records with skipped secrets: {inspection.secret_record_count}",
    ]
    if inspection.warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in inspection.warnings)
    if inspection.records:
        lines.append("Discovered records:")
        lines.extend(
            f"- {record.source_id} ({record.source_type}) -> "
            f"{_target_schema(record.source_type) or 'manual review'}"
            for record in inspection.records
        )
    return lines


def format_dry_run_text(report: ImportDryRunReport) -> list[str]:
    """Render migration plan and import dry-run output for operators."""
    mapped = sum(1 for record in report.mapped_records if record.status == "mapped")
    warnings = sum(1 for record in report.mapped_records if record.status == "warning")
    unsupported = sum(1 for record in report.mapped_records if record.status == "unsupported")
    lines = [
        f"Migration dry run: {report.id}",
        f"Source: {report.source_name} ({report.source_kind})",
        f"Candidates: {len(report.candidates)}",
        f"Mapped: {mapped}",
        f"Warnings: {warnings + len(report.warnings)}",
        f"Unsupported: {unsupported}",
        "Mutated source: no",
        "Mutated Craik state: no",
    ]
    if report.warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in report.warnings)
    if report.errors:
        lines.append("Errors:")
        lines.extend(f"- {error}" for error in report.errors)
    if report.mapped_records:
        lines.append("Proposed records:")
        lines.extend(
            f"- {record.source_id} -> {record.target_schema}/{record.target_id} "
            f"[{record.status}]"
            for record in report.mapped_records
        )
    return lines


def _json_source_files(source: Path) -> list[Path]:
    if source.is_file():
        return [source] if source.suffix.lower() == ".json" else []
    paths: list[Path] = []
    for path in source.rglob("*.json"):
        if not path.is_file():
            continue
        if len(path.relative_to(source).parts) > _MAX_MIGRATION_DEPTH:
            continue
        paths.append(path)
        if len(paths) > _MAX_MIGRATION_FILES:
            raise MigrationSourceTooLarge(
                f"migration source contains more than {_MAX_MIGRATION_FILES} JSON files"
            )
    return sorted(paths)


def _records_from_payload(
    payload: Any,
    *,
    root: Path,
    path: Path,
) -> list[AdjacentRuntimeSourceRecord]:
    records: list[AdjacentRuntimeSourceRecord] = []
    if isinstance(payload, dict):
        if _looks_like_record(payload):
            records.append(_record_from_mapping(payload, root=root, path=path, pointer=""))
        for key, value in payload.items():
            if isinstance(value, list):
                for index, item in enumerate(value):
                    if isinstance(item, dict):
                        records.append(
                            _record_from_mapping(
                                item,
                                root=root,
                                path=path,
                                pointer=f"{key}[{index}]",
                                fallback_type=key,
                            )
                        )
    elif isinstance(payload, list):
        for index, item in enumerate(payload):
            if isinstance(item, dict):
                records.append(
                    _record_from_mapping(item, root=root, path=path, pointer=f"[{index}]")
                )
    return records


def _looks_like_record(payload: dict[str, Any]) -> bool:
    return any(key in payload for key in ("id", "name", "type", "kind", "provider", "model"))


def _record_from_mapping(
    payload: dict[str, Any],
    *,
    root: Path,
    path: Path,
    pointer: str,
    fallback_type: str | None = None,
) -> AdjacentRuntimeSourceRecord:
    relative_path = path.relative_to(root).as_posix() if path != root else path.name
    source_type = _infer_source_type(payload, path=path, fallback=fallback_type)
    source_name = _safe_identifier(payload.get("id") or payload.get("name") or path.stem)
    pointer_id = _safe_identifier(pointer) if pointer else "root"
    source_id = f"{relative_path}:{pointer_id}:{source_name}"
    secret_fields = tuple(sorted(_secret_fields(payload)))
    return AdjacentRuntimeSourceRecord(
        source_id=source_id,
        source_type=source_type,
        path=relative_path,
        summary=_summary(payload, source_type=source_type, secret_fields=secret_fields),
        secret_fields=secret_fields,
    )


def _mapped_record(record: AdjacentRuntimeSourceRecord) -> ImportMappedRecord:
    object_map = migration_map_for_object(
        source_id=record.source_id,
        source_type=record.source_type,
        secret_fields=list(record.secret_fields),
    )
    if object_map.status == "unsupported":
        error = object_map.unsupported_reason or f"unsupported source type {record.source_type}"
        return ImportMappedRecord(
            source_id=record.source_id,
            target_schema=object_map.target_schema,
            target_id=f"manual_{_stable_id(record.source_id)}",
            status="unsupported",
            errors=[error],
        )
    if object_map.status in {"partial", "manual", "skipped-secret"}:
        return ImportMappedRecord(
            source_id=record.source_id,
            target_schema=object_map.target_schema,
            target_id=f"migrated_{_stable_id(record.source_id)}",
            status="warning",
            warnings=object_map.warnings or object_map.required_actions,
        )
    return ImportMappedRecord(
        source_id=record.source_id,
        target_schema=object_map.target_schema,
        target_id=f"migrated_{_stable_id(record.source_id)}",
        status="mapped",
    )


def _infer_source_type(
    payload: dict[str, Any],
    *,
    path: Path,
    fallback: str | None,
) -> str:
    raw_type = str(payload.get("type") or payload.get("kind") or fallback or path.stem).lower()
    normalized = raw_type.replace("-", "_").replace(" ", "_")
    if normalized.endswith("s"):
        normalized = normalized[:-1]
    for candidate in TARGET_SCHEMA_BY_SOURCE_TYPE:
        if candidate in normalized:
            return candidate
    if "provider" in payload:
        return "model"
    if "cron" in payload:
        return "schedule"
    return normalized or "config"


def _target_schema(source_type: str) -> str | None:
    return TARGET_SCHEMA_BY_SOURCE_TYPE.get(source_type)


def _secret_fields(payload: Any, prefix: str = "") -> set[str]:
    fields: set[str] = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            field = f"{prefix}.{key}" if prefix else str(key)
            lowered = str(key).lower()
            if any(marker in lowered for marker in SECRET_MARKERS):
                fields.add(field)
                continue
            fields.update(_secret_fields(value, field))
    elif isinstance(payload, list):
        for index, item in enumerate(payload):
            fields.update(_secret_fields(item, f"{prefix}[{index}]"))
    return fields


def _summary(
    payload: dict[str, Any],
    *,
    source_type: str,
    secret_fields: tuple[str, ...],
) -> str:
    name = payload.get("name") or payload.get("id") or payload.get("provider") or "unnamed"
    suffix = " Secret-like fields skipped." if secret_fields else ""
    return f"{source_type} record {name!s}.{suffix}".strip()


def _stable_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _safe_identifier(value: object) -> str:
    text = str(value or "record").strip().lower()
    normalized = "".join(character if character.isalnum() else "_" for character in text)
    return "_".join(part for part in normalized.split("_") if part) or "record"
