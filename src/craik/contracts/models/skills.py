"""Skill, plugin, adapter, and reference integration contracts."""

# ruff: noqa

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .base import *
from .core import *
from .instructions import *
from .memory import *
from .runtime import *

_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


class SkillEntrypoint(CraikModel):
    """One callable or readable entrypoint inside a skill package."""

    id: str
    kind: SkillEntrypointKind
    path: str
    description: str
    expected_input_schemas: list[str] = Field(default_factory=list)
    expected_output_schemas: list[str] = Field(default_factory=list)


class SkillContextRequirement(CraikModel):
    """Context input a skill package expects callers to supply or explain."""

    schema_name: str
    required: bool = True
    trust_boundary: InstructionTrustBoundary
    missing_context_behavior: SkillMissingContextBehavior = "reject"
    summary: str
    evidence_ids: list[str] = Field(default_factory=list)


class SkillPackage(CraikModel):
    """Reusable skill package metadata without plugin runtime authority."""

    schema_: Literal["craik.skill_package"] = Field(
        default="craik.skill_package",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    name: str
    package_version: str
    description: str
    entrypoints: list[SkillEntrypoint] = Field(min_length=1)
    docs: list[str] = Field(default_factory=list)
    assets: list[str] = Field(default_factory=list)
    expected_input_schemas: list[str] = Field(default_factory=list)
    expected_output_schemas: list[str] = Field(default_factory=list)
    context_requirements: list[SkillContextRequirement] = Field(default_factory=list)
    provenance_ids: list[str] = Field(default_factory=list)
    plugin_descriptor_id: str | None = None
    runtime_authority: Literal[False] = False
    created_at: datetime

    @model_validator(mode="after")
    def validate_skill_package(self) -> SkillPackage:
        """Require versioned packages with docs and at least one entrypoint."""
        if not _SEMVER_RE.fullmatch(self.package_version):
            raise ValueError("skill package_version must be semantic-version-like")
        if not self.docs:
            raise ValueError("skill packages require docs")
        if self.runtime_authority is not False:
            raise ValueError("skill packages must not carry runtime authority")
        declared_context = {requirement.schema_name for requirement in self.context_requirements}
        missing_context_declarations = sorted(set(self.expected_input_schemas) - declared_context)
        if missing_context_declarations:
            raise ValueError(
                f"skill expected input schemas require context requirements: {missing_context_declarations}"
            )
        return self

    def validate_invocation_context(self, context: SkillInvocationContext) -> None:
        """Validate one invocation context against this package's context requirements."""
        if context.skill_package_id != self.id:
            raise ValueError("skill invocation context skill_package_id does not match package")
        supplied_inputs = {context_input.schema_name: context_input for context_input in context.inputs}
        omitted_schemas = {omission.schema_name for omission in context.omissions}
        for requirement in self.context_requirements:
            context_input = supplied_inputs.get(requirement.schema_name)
            if context_input is not None:
                if context_input.trust_boundary != requirement.trust_boundary:
                    raise ValueError(
                        f"skill context input trust_boundary does not match requirement: {requirement.schema_name}"
                    )
                continue
            if not requirement.required:
                continue
            if requirement.missing_context_behavior == "reject":
                raise ValueError(f"missing required skill context input: {requirement.schema_name}")
            if (
                requirement.missing_context_behavior == "record_omission"
                and requirement.schema_name not in omitted_schemas
            ):
                raise ValueError(
                    f"missing skill context input requires omission: {requirement.schema_name}"
                )


class SkillContextInput(CraikModel):
    """Input contract made available to a skill invocation."""

    schema_name: str
    contract_id: str
    required: bool = True
    trust_boundary: InstructionTrustBoundary = "project"
    summary: str
    evidence_ids: list[str] = Field(default_factory=list)


class SkillContextOutput(CraikModel):
    """Output expected from or produced by a skill invocation."""

    schema_name: str
    contract_id: str | None = None
    required: bool = True
    produced: bool = False
    summary: str
    evidence_ids: list[str] = Field(default_factory=list)


class SkillContextOmission(CraikModel):
    """Required or expected context omitted from a skill invocation."""

    schema_name: str
    reason: str
    impact: str
    severity: SkillOmissionSeverity
    mitigation: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class SkillInvocationContext(CraikModel):
    """Auditable context boundary for one skill invocation."""

    schema_: Literal["craik.skill_invocation_context"] = Field(
        default="craik.skill_invocation_context",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    task_id: str
    skill_package_id: str
    policy_envelope_id: str
    handoff_id: str | None = None
    inputs: list[SkillContextInput] = Field(min_length=1)
    outputs: list[SkillContextOutput] = Field(default_factory=list)
    omissions: list[SkillContextOmission] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    receipt_ids: list[str] = Field(default_factory=list)
    redacted: bool = True
    created_at: datetime

    @model_validator(mode="after")
    def validate_skill_invocation_context(self) -> SkillInvocationContext:
        """Require policy-linked, redacted skill context with tracked outputs."""
        if not self.policy_envelope_id:
            raise ValueError("skill invocation context requires a policy_envelope_id")
        if not self.redacted:
            raise ValueError("skill invocation context must be redacted")
        if not self.outputs and not self.omissions:
            raise ValueError("skill invocation context requires outputs or omissions")
        missing_required_outputs = [
            output.schema_name
            for output in self.outputs
            if output.required and not output.produced and not output.contract_id
        ]
        if missing_required_outputs and not self.omissions:
            raise ValueError("missing required outputs must be explained by omissions")
        return self


class SkillRegistryEntry(CraikModel):
    """One discovered project-local or global skill package entry."""

    id: str
    skill_package_id: str
    scope: SkillScope
    project_id: str | None = None
    source_path: str
    trust_boundary: InstructionTrustBoundary
    precedence: int = Field(ge=0)
    active: bool = True
    provenance_ids: list[str] = Field(min_length=1)
    declared_by: str
    created_at: datetime

    @model_validator(mode="after")
    def validate_scope_project_link(self) -> SkillRegistryEntry:
        """Require project ids only for project-scoped skills."""
        if self.scope == "project" and not self.project_id:
            raise ValueError("project-scoped skill entries require project_id")
        if self.scope == "global" and self.project_id is not None:
            raise ValueError("global skill entries must not set project_id")
        return self


class SkillRegistry(CraikModel):
    """Registry of project-local and global skills with explicit precedence."""

    schema_: Literal["craik.skill_registry"] = Field(
        default="craik.skill_registry",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    project_id: str
    entries: list[SkillRegistryEntry] = Field(min_length=1)
    active_entry_ids: list[str] = Field(default_factory=list)
    precedence_order: list[str] = Field(default_factory=list)
    created_at: datetime

    @model_validator(mode="after")
    def validate_skill_registry(self) -> SkillRegistry:
        """Require active links and project-local precedence over globals."""
        entry_by_id = {entry.id: entry for entry in self.entries}
        unknown = sorted(set(self.active_entry_ids) - set(entry_by_id))
        if unknown:
            raise ValueError(f"unknown active skill entry ids: {unknown}")
        inactive = sorted(
            entry_id
            for entry_id in self.active_entry_ids
            if not entry_by_id[entry_id].active
        )
        if inactive:
            raise ValueError(f"inactive skill entry ids marked active: {inactive}")
        missing_active_entries = sorted(
            entry.id
            for entry in self.entries
            if entry.active and entry.id not in self.active_entry_ids
        )
        if missing_active_entries:
            raise ValueError(f"active skill entries missing active_entry_ids: {missing_active_entries}")
        if self.precedence_order:
            unknown_order = sorted(set(self.precedence_order) - set(entry_by_id))
            if unknown_order:
                raise ValueError(f"unknown precedence skill entry ids: {unknown_order}")
            inactive_order = sorted(
                entry_id
                for entry_id in self.precedence_order
                if not entry_by_id[entry_id].active
            )
            if inactive_order:
                raise ValueError(f"inactive skill entry ids in precedence_order: {inactive_order}")
            missing_active = sorted(set(self.active_entry_ids) - set(self.precedence_order))
            if missing_active:
                raise ValueError(f"active skill entry ids missing precedence: {missing_active}")
        active_entries = [entry_by_id[entry_id] for entry_id in self.active_entry_ids]
        precedence_values = [entry.precedence for entry in active_entries]
        if len(precedence_values) != len(set(precedence_values)):
            raise ValueError("active skill entry precedence values must be unique")
        packages = {entry.skill_package_id for entry in active_entries}
        for package_id in packages:
            project_precedence = [
                entry.precedence
                for entry in active_entries
                if entry.skill_package_id == package_id and entry.scope == "project"
            ]
            global_precedence = [
                entry.precedence
                for entry in active_entries
                if entry.skill_package_id == package_id and entry.scope == "global"
            ]
            if project_precedence and global_precedence:
                if min(project_precedence) > min(global_precedence):
                    raise ValueError("project-scoped skills must outrank global skills")
        return self


class PluginEntrypoint(CraikModel):
    """One declared entrypoint inside a governed plugin descriptor."""

    id: str
    kind: PluginEntrypointKind
    path: str
    description: str


class PluginCapabilityDeclaration(CraikModel):
    """Capability a plugin may request, without granting runtime authority."""

    capability: str
    description: str
    required: bool = True
    grant_required: bool = True
    risk: PluginCapabilityRisk
    operations: list[str] = Field(default_factory=list)
    targets: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_plugin_capability_declaration(self) -> PluginCapabilityDeclaration:
        """Require grant-scoped capability declarations to name operations and targets."""
        if self.grant_required:
            if not self.operations:
                raise ValueError("grant-required plugin capabilities require operations")
            if not self.targets:
                raise ValueError("grant-required plugin capabilities require targets")
        return self


class PluginCompatibility(CraikModel):
    """Runtime and platform compatibility metadata for a plugin descriptor."""

    craik_versions: list[str] = Field(min_length=1)
    python_versions: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)
    status: PluginCompatibilityStatus
    notes: str | None = None

    @model_validator(mode="after")
    def validate_plugin_compatibility(self) -> PluginCompatibility:
        """Require explicit supported runtime compatibility boundaries."""
        invalid_craik_versions = [
            version for version in self.craik_versions if not _SEMVER_RE.fullmatch(version)
        ]
        if invalid_craik_versions:
            raise ValueError(
                f"plugin compatibility craik_versions must be semantic-version-like: {invalid_craik_versions}"
            )
        if self.status == "supported":
            if not self.python_versions:
                raise ValueError("supported plugin compatibility requires python_versions")
            if not self.platforms:
                raise ValueError("supported plugin compatibility requires platforms")
        if self.status == "unsupported" and not self.notes:
            raise ValueError("unsupported plugin compatibility requires notes")
        return self


class PluginDescriptor(CraikModel):
    """Governed plugin metadata that declares needs but grants no authority."""

    schema_: Literal["craik.plugin_descriptor"] = Field(
        default="craik.plugin_descriptor",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    name: str
    plugin_version: str
    description: str
    publisher: str
    trust_boundary: InstructionTrustBoundary
    entrypoints: list[PluginEntrypoint] = Field(min_length=1)
    capabilities: list[PluginCapabilityDeclaration] = Field(min_length=1)
    docs: list[str] = Field(min_length=1)
    compatibility: PluginCompatibility
    security_notes: list[str] = Field(min_length=1)
    skill_package_ids: list[str] = Field(default_factory=list)
    provenance_ids: list[str] = Field(default_factory=list)
    runtime_authority: Literal[False] = False
    created_at: datetime

    @model_validator(mode="after")
    def validate_plugin_descriptor(self) -> PluginDescriptor:
        """Require versioned descriptors and grant separation for risky capabilities."""
        if not _SEMVER_RE.fullmatch(self.plugin_version):
            raise ValueError("plugin plugin_version must be semantic-version-like")
        for capability in self.capabilities:
            if capability.risk in {"high", "critical"} and not capability.grant_required:
                raise ValueError("high-risk plugin capabilities require explicit grants")
        if self.runtime_authority is not False:
            raise ValueError("plugin descriptors must not carry runtime authority")
        return self


class PluginProbationCriterion(CraikModel):
    """One review criterion for probationary plugin governance."""

    name: str
    required: bool = True
    passed: bool = False
    summary: str
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_plugin_probation_criterion(self) -> PluginProbationCriterion:
        """Require evidence for criteria marked as passed."""
        if self.passed and not self.evidence_ids:
            raise ValueError("passed plugin probation criteria require evidence")
        return self


class PluginProbationDecision(CraikModel):
    """Promotion, rejection, or expiration decision for plugin probation."""

    decision: PluginProbationDecisionKind
    decided_by: str
    rationale: str
    evidence_ids: list[str] = Field(min_length=1)
    decided_at: datetime


class PluginProbation(CraikModel):
    """Governance record for probationary plugin review."""

    schema_: Literal["craik.plugin_probation"] = Field(
        default="craik.plugin_probation",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    plugin_descriptor_id: str
    policy_envelope_id: str
    status: PluginProbationStatus = "probationary"
    criteria: list[PluginProbationCriterion] = Field(min_length=1)
    compatibility_check_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    receipt_ids: list[str] = Field(default_factory=list)
    decision: PluginProbationDecision | None = None
    expires_at: datetime | None = None
    durable_trust_granted: bool = False
    created_at: datetime

    @model_validator(mode="after")
    def validate_plugin_probation(self) -> PluginProbation:
        """Require review evidence before promotion and deny durable trust by default."""
        if self.status == "probationary":
            if self.decision is not None:
                raise ValueError("probationary plugin records must not include a decision")
            if self.durable_trust_granted:
                raise ValueError("probationary plugins must not receive durable trust")
        if self.status == "promoted":
            if self.decision is None or self.decision.decision != "promote":
                raise ValueError("promoted plugin records require a promote decision")
            failed_required = [
                criterion.name
                for criterion in self.criteria
                if criterion.required and not criterion.passed
            ]
            if failed_required:
                raise ValueError("promoted plugin records require required criteria to pass")
            if not self.compatibility_check_ids:
                raise ValueError("promoted plugin records require compatibility checks")
        if self.status == "rejected":
            if self.decision is None or self.decision.decision != "reject":
                raise ValueError("rejected plugin records require a reject decision")
        if self.status == "expired":
            if self.decision is None or self.decision.decision != "expire":
                raise ValueError("expired plugin records require an expire decision")
            if self.expires_at is None:
                raise ValueError("expired plugin records require expires_at")
        if self.status != "promoted" and self.durable_trust_granted:
            raise ValueError("only promoted plugin records may grant durable trust")
        return self


class PluginReceipt(CraikModel):
    """Redacted receipt for a plugin action or output."""

    schema_: Literal["craik.plugin_receipt"] = Field(
        default="craik.plugin_receipt",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    task_id: str
    actor: str
    plugin_descriptor_id: str
    plugin_probation_id: str | None = None
    action: str
    capability_grant_ids: list[str] = Field(min_length=1)
    trust_boundary: InstructionTrustBoundary
    result: ReceiptResult
    evidence_ids: list[str] = Field(min_length=1)
    handoff_ids: list[str] = Field(min_length=1)
    redacted: bool = True
    created_at: datetime

    @model_validator(mode="after")
    def validate_plugin_receipt(self) -> PluginReceipt:
        """Require redacted plugin receipts with grant and evidence links."""
        if not self.redacted:
            raise ValueError("plugin receipts must be redacted")
        if self.result.status == "passed" and not self.capability_grant_ids:
            raise ValueError("successful plugin receipts require capability grants")
        if self.result.status == "denied" and not self.result.summary:
            raise ValueError("denied plugin receipts require a denial summary")
        return self


class PluginCapabilityGrant(CraikModel):
    """Least-privilege capability grant scoped to one plugin descriptor."""

    schema_: Literal["craik.plugin_capability_grant"] = Field(
        default="craik.plugin_capability_grant",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    task_id: str
    plugin_descriptor_id: str
    policy_envelope_id: str
    capability: str
    target: CapabilityTarget
    operations: list[str] = Field(min_length=1)
    status: PluginGrantStatus
    approval_required: bool = False
    approved_by: str | None = None
    expires_at: datetime | None = None
    reason: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    receipt_ids: list[str] = Field(default_factory=list)
    created_at: datetime

    @model_validator(mode="after")
    def validate_plugin_capability_grant(self) -> PluginCapabilityGrant:
        """Validate plugin grant state and least-privilege approval boundaries."""
        if "*" in self.operations or "all" in self.operations:
            raise ValueError("plugin grants must name explicit operations")
        if not self.target.repo and not self.target.paths and not self.target.metadata:
            raise ValueError("plugin grants require a scoped target")
        if self.status == "allowed":
            if self.approval_required and not self.approved_by:
                raise ValueError("approval-required allowed plugin grants require approved_by")
            if self.expires_at is None:
                raise ValueError("allowed plugin grants require expires_at")
        if self.status == "denied" and self.approved_by is not None:
            raise ValueError("denied plugin grants must not include approved_by")
        if self.status == "expired" and self.expires_at is None:
            raise ValueError("expired plugin grants require expires_at")
        if self.status == "approval_required":
            if not self.approval_required:
                raise ValueError("approval_required grants must set approval_required")
            if self.approved_by is not None:
                raise ValueError("approval_required grants must not include approved_by")
        return self

    def permits_operation(self, operation: str, *, at: datetime) -> bool:
        """Return whether this grant currently authorizes one operation."""
        if self.status != "allowed":
            return False
        if operation not in self.operations:
            return False
        if self.expires_at is None or at >= self.expires_at:
            return False
        return True


class AdapterEntrypoint(CraikModel):
    """One callable or readable entrypoint in an adapter package."""

    id: str
    kind: AdapterEntrypointKind
    path: str
    description: str


class AdapterCompatibility(CraikModel):
    """Runtime compatibility metadata for an adapter package."""

    craik_versions: list[str] = Field(min_length=1)
    runner_modes: list[RunnerMode] = Field(min_length=1)
    python_versions: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)
    notes: str | None = None


class AdapterPackage(CraikModel):
    """Adapter package metadata and compatibility contract."""

    schema_: Literal["craik.adapter_package"] = Field(
        default="craik.adapter_package",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    name: str
    package_version: str
    adapter: str
    description: str
    entrypoints: list[AdapterEntrypoint] = Field(min_length=1)
    capability_surfaces: list[str] = Field(min_length=1)
    compatibility: AdapterCompatibility
    runner_metadata_ids: list[str] = Field(default_factory=list)
    plugin_descriptor_ids: list[str] = Field(default_factory=list)
    docs: list[str] = Field(min_length=1)
    provenance_ids: list[str] = Field(min_length=1)
    version_constraints: list[str] = Field(default_factory=list)
    created_at: datetime

    @model_validator(mode="after")
    def validate_adapter_package(self) -> AdapterPackage:
        """Require versioned adapter packages with entrypoints and compatibility."""
        if "." not in self.package_version:
            raise ValueError("adapter package_version must be semantic-version-like")
        if not self.compatibility.runner_modes:
            raise ValueError("adapter packages require runner mode compatibility")
        return self


class ReferenceIntegration(CraikModel):
    """Safe reproducible reference integration for a skill, plugin, or adapter."""

    schema_: Literal["craik.reference_integration"] = Field(
        default="craik.reference_integration",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    kind: ReferenceIntegrationKind
    name: str
    description: str
    skill_package_id: str | None = None
    plugin_descriptor_id: str | None = None
    adapter_package_id: str | None = None
    docs: list[str] = Field(min_length=1)
    fixture_paths: list[str] = Field(min_length=1)
    check_commands: list[str] = Field(min_length=1)
    receipt_ids: list[str] = Field(default_factory=list)
    compatibility_notes: list[str] = Field(min_length=1)
    safe_to_run_locally: bool = True
    reproducible: bool = True
    provenance_ids: list[str] = Field(min_length=1)
    created_at: datetime

    @model_validator(mode="after")
    def validate_reference_integration(self) -> ReferenceIntegration:
        """Require the reference id that matches the integration kind."""
        if self.kind == "skill" and not self.skill_package_id:
            raise ValueError("skill reference integrations require skill_package_id")
        if self.kind == "plugin" and not self.plugin_descriptor_id:
            raise ValueError("plugin reference integrations require plugin_descriptor_id")
        if self.kind == "adapter" and not self.adapter_package_id:
            raise ValueError("adapter reference integrations require adapter_package_id")
        if not self.safe_to_run_locally or not self.reproducible:
            raise ValueError("reference integrations must be safe and reproducible")
        return self


if not TYPE_CHECKING:
    __all__ = [name for name in globals() if not name.startswith("_")]
