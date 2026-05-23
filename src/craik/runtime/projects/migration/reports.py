"""Deterministic migration reports for adjacent runtime dry-runs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import Field, model_validator

from craik.contracts.models import CraikModel
from craik.runtime.projects.migration_maps import MigrationObjectMap, MigrationPlanMap

MigrationReportSection = Literal[
    "summary",
    "importable_objects",
    "manual_actions",
    "skipped_secrets",
    "security_posture_changes",
    "unsupported_capabilities",
    "recommended_next_commands",
    "validation_checklist",
]


class MigrationReportItem(CraikModel):
    """One safe-to-share item in a migration report section."""

    source_id: str
    target_schema: str | None = None
    target_id: str | None = None
    status: str
    summary: str
    actions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    secret_fields: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_report_item(self) -> MigrationReportItem:
        """Keep report items redacted and source-linked."""
        if not self.source_id:
            raise ValueError("migration report items require source_id")
        if _contains_secret_value(self.summary):
            raise ValueError("migration report item summary appears to contain a raw secret")
        if any(_contains_secret_value(value) for value in self.actions + self.warnings):
            raise ValueError("migration report item text appears to contain a raw secret")
        return self


class MigrationReport(CraikModel):
    """Safe-to-share migration report produced from an object map."""

    id: str
    source_name: str
    summary: dict[str, int]
    importable_objects: list[MigrationReportItem] = Field(default_factory=list)
    manual_actions: list[MigrationReportItem] = Field(default_factory=list)
    skipped_secrets: list[MigrationReportItem] = Field(default_factory=list)
    security_posture_changes: list[str] = Field(default_factory=list)
    unsupported_capabilities: list[MigrationReportItem] = Field(default_factory=list)
    recommended_next_commands: list[str] = Field(default_factory=list)
    validation_checklist: list[str] = Field(default_factory=list)
    redacted: bool = True
    policy_envelope_id: str
    evidence_ids: list[str] = Field(min_length=1)
    receipt_ids: list[str] = Field(min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_report(self) -> MigrationReport:
        """Keep reports deterministic, redacted, and policy-bound."""
        if not self.policy_envelope_id:
            raise ValueError("migration reports require policy_envelope_id")
        for command in self.recommended_next_commands:
            if _contains_secret_value(command):
                raise ValueError("recommended commands must not contain raw secrets")
        for item in self.skipped_secrets:
            if not item.secret_fields:
                raise ValueError("skipped secret report items require secret_fields")
        return self


def build_migration_report(
    plan: MigrationPlanMap,
    *,
    report_id: str | None = None,
    created_at: datetime | None = None,
) -> MigrationReport:
    """Build a deterministic report from an object-level migration plan."""
    object_maps = sorted(plan.object_maps, key=lambda item: item.source_id)
    importable = [_report_item(item) for item in object_maps if item.status == "importable"]
    manual = [
        _report_item(item)
        for item in object_maps
        if item.status in {"partial", "manual"}
    ]
    skipped = [_report_item(item) for item in object_maps if item.status == "skipped-secret"]
    unsupported = [_report_item(item) for item in object_maps if item.status == "unsupported"]
    security_changes = _security_posture_changes(object_maps)
    return MigrationReport(
        id=report_id or f"migration_report_{plan.id}",
        source_name=plan.source_name,
        summary={str(status): count for status, count in plan.by_status().items()},
        importable_objects=importable,
        manual_actions=manual,
        skipped_secrets=skipped,
        security_posture_changes=security_changes,
        unsupported_capabilities=unsupported,
        recommended_next_commands=_recommended_next_commands(skipped, manual, unsupported),
        validation_checklist=_validation_checklist(object_maps),
        policy_envelope_id=plan.policy_envelope_id,
        evidence_ids=plan.evidence_ids,
        receipt_ids=plan.receipt_ids,
        created_at=created_at or plan.created_at,
    )


def format_migration_report(report: MigrationReport) -> list[str]:
    """Render a migration report for text output."""
    lines = [
        f"Migration report: {report.id}",
        f"Source: {report.source_name}",
        "Summary:",
    ]
    lines.extend(f"- {status}: {count}" for status, count in sorted(report.summary.items()))
    lines.extend(_section_lines("Importable objects", report.importable_objects))
    lines.extend(_section_lines("Manual actions", report.manual_actions))
    lines.extend(_section_lines("Skipped secrets", report.skipped_secrets))
    if report.security_posture_changes:
        lines.append("Security posture changes:")
        lines.extend(f"- {item}" for item in report.security_posture_changes)
    lines.extend(_section_lines("Unsupported capabilities", report.unsupported_capabilities))
    if report.recommended_next_commands:
        lines.append("Recommended next commands:")
        lines.extend(f"- {command}" for command in report.recommended_next_commands)
    if report.validation_checklist:
        lines.append("Validation checklist:")
        lines.extend(f"- {item}" for item in report.validation_checklist)
    return lines


def _report_item(item: MigrationObjectMap) -> MigrationReportItem:
    return MigrationReportItem(
        source_id=item.source_id,
        target_schema=item.target_schema,
        target_id=item.target_id,
        status=item.status,
        summary=item.target_summary,
        actions=item.required_actions,
        warnings=item.warnings,
        secret_fields=item.secret_fields,
    )


def _security_posture_changes(object_maps: list[MigrationObjectMap]) -> list[str]:
    changes: list[str] = []
    for item in object_maps:
        if item.status == "skipped-secret":
            changes.append(f"{item.source_id}: credential material must be reconfigured")
        elif item.source_type in {"approval", "gateway", "sandbox", "channel"}:
            changes.append(f"{item.source_id}: authority boundary requires operator review")
    return sorted(set(changes))


def _recommended_next_commands(
    skipped: list[MigrationReportItem],
    manual: list[MigrationReportItem],
    unsupported: list[MigrationReportItem],
) -> list[str]:
    commands = ["craik migrate plan --source PATH --kind agent-runtime --json"]
    if skipped:
        commands.append("craik auth login PROVIDER")
    if manual:
        commands.append("craik doctor --fix --dry-run")
    if unsupported:
        commands.append("craik migrate inspect --source PATH --kind agent-runtime --json")
    return commands


def _validation_checklist(object_maps: list[MigrationObjectMap]) -> list[str]:
    checklist = [
        "Confirm source files were not modified.",
        "Review every partial, manual, unsupported, and skipped-secret item.",
        "Run the generated plan again after credential reconfiguration.",
    ]
    if any(item.source_type == "gateway" for item in object_maps):
        checklist.append("Validate gateway bind host, TLS posture, and policy envelope.")
    if any(item.source_type == "channel" for item in object_maps):
        checklist.append("Validate channel webhook signature and allowlist configuration.")
    return checklist


def _section_lines(title: str, items: list[MigrationReportItem]) -> list[str]:
    if not items:
        return []
    lines = [f"{title}:"]
    for item in items:
        target = f" -> {item.target_schema}/{item.target_id}" if item.target_schema else ""
        lines.append(f"- {item.source_id}{target} [{item.status}] {item.summary}")
        lines.extend(f"  action: {action}" for action in item.actions)
        lines.extend(f"  warning: {warning}" for warning in item.warnings)
        if item.secret_fields:
            lines.append(f"  skipped fields: {', '.join(item.secret_fields)}")
    return lines


def _contains_secret_value(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in ("sk_live", "sk-", "api_key=", "password="))
