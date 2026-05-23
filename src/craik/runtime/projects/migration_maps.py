"""Migration maps for adjacent runtime imports."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import Field, model_validator

from craik.contracts.models import CraikModel
from craik.runtime.projects.migration_assessment import MigrationSupport

MigrationMapSurface = Literal[
    "agent",
    "approval",
    "channel",
    "config",
    "fallback",
    "gateway",
    "memory",
    "model",
    "profile",
    "schedule",
    "sandbox",
    "session",
    "skill",
]
MigrationObjectStatus = Literal["importable", "partial", "manual", "unsupported", "skipped-secret"]


class MigrationObjectMap(CraikModel):
    """One source object mapped to a target Craik object."""

    source_id: str
    source_type: str
    target_schema: str
    target_id: str | None = None
    status: MigrationObjectStatus
    target_summary: str
    required_actions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    unsupported_reason: str | None = None
    secret_fields: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_object_map(self) -> MigrationObjectMap:
        """Keep object importability explicit."""
        if self.status == "importable" and not self.target_id:
            raise ValueError("importable object maps require target_id")
        if self.status in {"manual", "unsupported"} and not self.required_actions:
            raise ValueError("manual and unsupported object maps require required_actions")
        if self.status == "unsupported" and not self.unsupported_reason:
            raise ValueError("unsupported object maps require unsupported_reason")
        if self.status == "skipped-secret" and not self.secret_fields:
            raise ValueError("skipped-secret object maps require secret_fields")
        return self


class MigrationPlanMap(CraikModel):
    """Object-level migration map for one adjacent runtime source."""

    id: str
    source_name: str
    object_maps: list[MigrationObjectMap] = Field(min_length=1)
    policy_envelope_id: str
    evidence_ids: list[str] = Field(min_length=1)
    receipt_ids: list[str] = Field(min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_plan_map(self) -> MigrationPlanMap:
        """Keep migration plans policy-bound."""
        if not self.policy_envelope_id:
            raise ValueError("migration plan maps require policy_envelope_id")
        return self

    def by_status(self) -> dict[MigrationObjectStatus, int]:
        """Count mapped objects by importability status."""
        counts: dict[MigrationObjectStatus, int] = {
            "importable": 0,
            "partial": 0,
            "manual": 0,
            "unsupported": 0,
            "skipped-secret": 0,
        }
        for item in self.object_maps:
            counts[item.status] += 1
        return counts


DEFAULT_TARGET_SCHEMAS: dict[str, str] = {
    "agent": "craik.agent_profile",
    "approval": "craik.approval_security_posture",
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

DEFAULT_OBJECT_TYPE_MAPS: tuple[MigrationObjectMap, ...] = (
    MigrationObjectMap(
        source_id="agent",
        source_type="agent",
        target_schema="craik.agent_profile",
        target_id="agent_profile",
        status="importable",
        target_summary="Agent identity, default model, and role metadata.",
    ),
    MigrationObjectMap(
        source_id="profile",
        source_type="profile",
        target_schema="craik.profile",
        target_id="profile",
        status="importable",
        target_summary="Profile or persona metadata.",
    ),
    MigrationObjectMap(
        source_id="model",
        source_type="model",
        target_schema="craik.model_provider",
        target_id="model_provider",
        status="partial",
        target_summary="Provider, model, alias, and routing metadata.",
        required_actions=["validate provider credentials after import"],
        warnings=["credentials are not imported by object maps"],
    ),
    MigrationObjectMap(
        source_id="fallback",
        source_type="fallback",
        target_schema="craik.model_fallback_chain",
        target_id="model_fallback_chain",
        status="importable",
        target_summary="Model fallback chain ordering.",
    ),
    MigrationObjectMap(
        source_id="channel",
        source_type="channel",
        target_schema="craik.channel_binding",
        target_id="channel_binding",
        status="partial",
        target_summary="Channel account and binding metadata.",
        required_actions=["reconfigure channel secrets and webhook signatures"],
        warnings=["channel secrets are skipped"],
    ),
    MigrationObjectMap(
        source_id="skill",
        source_type="skill",
        target_schema="craik.skill_package",
        target_id="skill_package",
        status="manual",
        target_summary="Skill package metadata and docs path.",
        required_actions=["review skill trust policy before enabling"],
    ),
    MigrationObjectMap(
        source_id="memory",
        source_type="memory",
        target_schema="craik.memory_record",
        target_id="memory_record",
        status="partial",
        target_summary="Memory files and preference facts.",
        required_actions=["review private facts before import"],
        warnings=["private or secret-like values must be redacted"],
    ),
    MigrationObjectMap(
        source_id="session",
        source_type="session",
        target_schema="craik.agent_session",
        target_id="agent_session",
        status="partial",
        target_summary="Session transcript and provenance metadata.",
        required_actions=["review unsupported tool calls"],
    ),
    MigrationObjectMap(
        source_id="schedule",
        source_type="schedule",
        target_schema="craik.schedule",
        target_id="schedule",
        status="manual",
        target_summary="Schedule or cron metadata.",
        required_actions=["confirm schedule authority before enabling"],
    ),
    MigrationObjectMap(
        source_id="sandbox",
        source_type="sandbox",
        target_schema="craik.sandbox_config",
        target_id="sandbox_config",
        status="manual",
        target_summary="Sandbox backend and execution boundary metadata.",
        required_actions=["review sandbox trust boundary"],
    ),
    MigrationObjectMap(
        source_id="gateway",
        source_type="gateway",
        target_schema="craik.gateway_config",
        target_id="gateway_config",
        status="manual",
        target_summary="Gateway listener and routing metadata.",
        required_actions=["confirm bind host, TLS posture, and policy envelope"],
    ),
    MigrationObjectMap(
        source_id="approval",
        source_type="approval",
        target_schema="craik.approval_security_posture",
        target_id="approval_security_posture",
        status="manual",
        target_summary="Approval policy and security posture metadata.",
        required_actions=["review approval gates before enabling"],
    ),
)


class MigrationFieldMap(CraikModel):
    """One source-to-target field mapping."""

    source_field: str
    target_field: str | None
    support: MigrationSupport
    transform_notes: str
    redaction_required: bool = True
    unsupported_reason: str | None = None

    @model_validator(mode="after")
    def validate_field_map(self) -> MigrationFieldMap:
        """Keep supported and unsupported fields explicit."""
        if self.support == "supported" and self.target_field is None:
            raise ValueError("supported migration fields require target_field")
        if self.support == "unsupported" and self.unsupported_reason is None:
            raise ValueError("unsupported migration fields require unsupported_reason")
        return self


class MigrationMap(CraikModel):
    """Migration map for one import surface."""

    id: str
    surface: MigrationMapSurface
    source_name: str
    field_maps: list[MigrationFieldMap] = Field(min_length=1)
    compatibility_notes: list[str] = Field(default_factory=list)
    policy_envelope_id: str
    evidence_ids: list[str] = Field(min_length=1)
    receipt_ids: list[str] = Field(min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_migration_map(self) -> MigrationMap:
        """Keep maps policy-bound."""
        if not self.policy_envelope_id:
            raise ValueError("migration maps require policy_envelope_id")
        return self


def migration_map_for_object(
    *,
    source_id: str,
    source_type: str,
    secret_fields: list[str] | None = None,
) -> MigrationObjectMap:
    """Map one adjacent runtime object to its target Craik object."""
    normalized_type = _normalize_source_type(source_type)
    target_schema = DEFAULT_TARGET_SCHEMAS.get(normalized_type)
    if secret_fields:
        return MigrationObjectMap(
            source_id=source_id,
            source_type=normalized_type,
            target_schema=target_schema or "manual.review",
            target_id=None,
            status="skipped-secret",
            target_summary="Secret-bearing source object skipped until secret migration runs.",
            required_actions=["run secret migration or reconfigure credentials manually"],
            warnings=["raw secret values are not imported"],
            secret_fields=secret_fields,
        )
    template = next(
        (item for item in DEFAULT_OBJECT_TYPE_MAPS if item.source_type == normalized_type),
        None,
    )
    if template is None:
        return MigrationObjectMap(
            source_id=source_id,
            source_type=normalized_type,
            target_schema="manual.review",
            target_id=None,
            status="unsupported",
            target_summary="Unsupported adjacent runtime object.",
            required_actions=["review source object manually"],
            unsupported_reason=f"no Craik migration target is defined for {normalized_type}",
        )
    target_id = f"{template.target_id}_{_object_suffix(source_id)}" if template.target_id else None
    return template.model_copy(update={"source_id": source_id, "target_id": target_id})


def migration_plan_map(
    *,
    plan_id: str,
    source_name: str,
    objects: list[MigrationObjectMap],
    policy_envelope_id: str = "policy_adjacent_runtime_migration",
    evidence_ids: list[str] | None = None,
    receipt_ids: list[str] | None = None,
) -> MigrationPlanMap:
    """Create an object-level migration map."""
    return MigrationPlanMap(
        id=plan_id,
        source_name=source_name,
        object_maps=objects,
        policy_envelope_id=policy_envelope_id,
        evidence_ids=evidence_ids or ["evidence_adjacent_runtime_source"],
        receipt_ids=receipt_ids or ["receipt_adjacent_runtime_map"],
    )


def _normalize_source_type(source_type: str) -> str:
    normalized = source_type.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in {"persona", "personas"}:
        return "profile"
    if normalized in {"provider", "alias", "model_alias"}:
        return "model"
    if normalized in {"fallback_chain", "fallback_chains"}:
        return "fallback"
    if normalized in {"channel_account", "channel_accounts", "channel_binding"}:
        return "channel"
    if normalized in {"security", "security_posture", "policy"}:
        return "approval"
    if normalized.endswith("s"):
        normalized = normalized[:-1]
    return normalized


def _object_suffix(source_id: str) -> str:
    normalized = "".join(character if character.isalnum() else "_" for character in source_id)
    return "_".join(part for part in normalized.lower().split("_") if part)[-48:] or "object"
