"""Core project, task, policy, receipt, and prompt contracts."""

# ruff: noqa

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

from .base import *


class EvidenceReference(CraikModel):
    """Reference to source material used to support a contract assertion."""

    schema_: Literal["craik.evidence_reference"] = Field(
        default="craik.evidence_reference",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    source: str
    kind: Literal["file", "url", "command", "fact", "issue", "pull_request", "handoff", "other"]
    locator: str
    summary: str
    captured_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Assumption(CraikModel):
    """An unresolved assumption that must not be promoted to fact without evidence."""

    schema_: Literal["craik.assumption"] = Field(default="craik.assumption", alias="schema")
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    task_id: str
    statement: str
    rationale: str
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    status: Literal["open", "validated", "rejected"] = "open"


class IntentLock(CraikModel):
    """Stable task intent used to detect scope drift during a run."""

    schema_: Literal["craik.intent_lock"] = Field(default="craik.intent_lock", alias="schema")
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    task_id: str
    original_request: str
    objective: str
    accepted_interpretation: str
    in_scope: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    allowed_autonomy: list[str] = Field(default_factory=list)
    stop_conditions: list[str] = Field(default_factory=list)
    scope_change_rules: list[str] = Field(default_factory=list)
    created_at: datetime


class TaskRequest(CraikModel):
    """Work requested by a user, system, or another agent."""

    schema_: Literal["craik.task_request"] = Field(default="craik.task_request", alias="schema")
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    title: str
    objective: str
    project_id: str
    requested_by: str
    priority: Priority = "normal"
    mode: TaskMode
    auth_profile_id: str | None = None
    operator_subject: str | None = None
    operator_issuer: str | None = None
    source_handoff_id: str | None = None
    source_task_id: str | None = None
    source_run_id: str | None = None
    expected_duration_minutes: int | None = Field(default=None, gt=0)
    constraints: list[str] = Field(default_factory=list)
    expected_outputs: list[str] = Field(default_factory=list)
    created_at: datetime


class RepoProfile(CraikModel):
    """Repository configuration for a project."""

    type: Literal["git"]
    local_path: str
    remote: str | None = None
    default_branch: str = "main"


class DocsProfile(CraikModel):
    """Documentation paths and immutable areas for a project."""

    paths: list[str] = Field(default_factory=list)
    immutable_paths: list[str] = Field(default_factory=list)
    discovery_include: list[str] = Field(default_factory=list)
    discovery_exclude: list[str] = Field(default_factory=list)


class MemoryProfile(CraikModel):
    """Configured memory backend for a project."""

    backend: MemoryBackend
    scope: MemoryScope = "team"


class ProjectProfile(CraikModel):
    """Project configuration Craik can reason about."""

    schema_: Literal["craik.project_profile"] = Field(
        default="craik.project_profile",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    name: str
    repo: RepoProfile
    docs: DocsProfile = Field(default_factory=DocsProfile)
    memory: MemoryProfile
    policies: list[str] = Field(default_factory=list)


class PolicyEnvelope(CraikModel):
    """Runtime authority and obligations for a task."""

    schema_: Literal["craik.policy_envelope"] = Field(
        default="craik.policy_envelope",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    task_id: str
    actor: str
    profile: PolicyProfile
    fail_open: bool = False
    allowed_capabilities: list[str] = Field(default_factory=list)
    denied_capabilities: list[str] = Field(default_factory=list)
    approval_required: list[str] = Field(default_factory=list)
    verification_required: list[str] = Field(default_factory=list)
    handoff_required: bool = True
    receipt_required: bool = True
    redaction_required: bool = True
    required_operator: bool = False
    allowed_operator_groups: list[str] | None = None
    allowed_operator_subjects: list[str] | None = None
    required_operator_issuer: str | None = None
    allowed_credential_kinds: list[str] | None = None
    allowed_credential_profiles: list[str] | None = None


class CapabilityTarget(CraikModel):
    """Scope of a capability grant."""

    repo: str | None = None
    paths: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CapabilityGrant(CraikModel):
    """Concrete permission for an action family."""

    schema_: Literal["craik.capability_grant"] = Field(
        default="craik.capability_grant",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    task_id: str
    capability: str
    target: CapabilityTarget
    operations: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None
    reason: str
    approved_by: str


class ReceiptResult(CraikModel):
    """Redacted result summary for an auditable action."""

    status: ReceiptStatus
    summary: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class CapabilityReceipt(CraikModel):
    """Record of an important action performed under policy."""

    schema_: Literal["craik.capability_receipt"] = Field(
        default="craik.capability_receipt",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    task_id: str
    actor: str
    capability: str
    target: str
    policy_profile: PolicyProfile
    fail_open: bool = False
    reason: str
    result: ReceiptResult
    redacted: bool = True
    auth_profile_id: str | None = None
    auth_kind: str | None = None
    auth_identity_hash: str | None = None
    operator_subject: str | None = None
    operator_issuer: str | None = None
    operator_email: str | None = None
    operator_groups: list[str] = Field(default_factory=list)
    previous_receipt_hash: str | None = None
    self_hash: str = ""
    created_at: datetime

    @model_validator(mode="after")
    def validate_receipt_hash(self) -> CapabilityReceipt:
        """Compute or verify the canonical receipt hash."""
        expected = _capability_receipt_hash(self)
        if self.self_hash and self.self_hash != expected:
            raise ValueError("capability receipt hash did not match payload")
        self.self_hash = expected
        return self


def _capability_receipt_hash(receipt: CapabilityReceipt) -> str:
    payload = receipt.model_dump(
        mode="json",
        by_alias=True,
        exclude={"self_hash"},
    )
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class AgentRole(CraikModel):
    """Policy-aware role definition for multi-agent coordination."""

    schema_: Literal["craik.agent_role"] = Field(default="craik.agent_role", alias="schema")
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    kind: AgentRoleKind
    name: str
    description: str
    runner_id: str | None = None
    runner_mode: RunnerMode | None = None
    authority: list[AgentRoleAuthority] = Field(default_factory=list)
    allowed_capabilities: list[str] = Field(default_factory=list)
    denied_capabilities: list[str] = Field(default_factory=list)
    policy_envelope_id: str | None = None
    expected_input_schemas: list[str] = Field(default_factory=list)
    expected_output_schemas: list[str] = Field(default_factory=list)
    handoff_required: bool = True
    receipt_required: bool = True
    redaction_required: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_role_contract(self) -> AgentRole:
        """Ensure roles carry enough authority and output boundary information."""
        if not self.authority:
            raise ValueError("agent roles require at least one authority value")
        if not self.expected_output_schemas:
            raise ValueError("agent roles require at least one expected output schema")
        required_authority: dict[AgentRoleKind, AgentRoleAuthority] = {
            "orchestrator": "coordinate",
            "implementer": "implement",
            "verifier": "review",
            "adversarial_reviewer": "review",
            "policy_reviewer": "review",
            "docs_reviewer": "review",
            "memory_curator": "review",
            "adjudicator": "adjudicate",
        }
        authority = required_authority[self.kind]
        if authority not in self.authority:
            raise ValueError(f"{self.kind} role requires {authority!r} authority")
        return self


class PromptSection(CraikModel):
    """Named deterministic section in a compiled runner prompt."""

    title: str
    body: str


class CompiledPrompt(CraikModel):
    """Policy-aware runner prompt compiled from Craik runtime state."""

    schema_: Literal["craik.compiled_prompt"] = Field(
        default="craik.compiled_prompt",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    task_id: str
    case_file_id: str
    policy_envelope_id: str
    runner_id: str
    runner_mode: RunnerMode
    capability_grant_ids: list[str] = Field(default_factory=list)
    expected_output_schemas: list[str] = Field(default_factory=list)
    context_omissions: list[str] = Field(default_factory=list)
    stop_conditions: list[str] = Field(default_factory=list)
    sections: list[PromptSection] = Field(default_factory=list)
    prompt: str


if not TYPE_CHECKING:
    __all__ = [name for name in globals() if not name.startswith("_")]
