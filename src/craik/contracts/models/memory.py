"""Run output, memory, channel, provider, and sandbox contracts."""

# ruff: noqa

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import *
from .core import *
from .instructions import *


class RunOutput(CraikModel):
    """Inspectable observed output captured from one runner step."""

    schema_: Literal["craik.run_output"] = Field(default="craik.run_output", alias="schema")
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    run_id: str
    step_result_id: str
    task_id: str
    phase: TaskRunPhase
    summary: str
    observed_output: dict[str, Any] = Field(default_factory=dict)
    diagnostics: list[str] = Field(default_factory=list)
    receipt_ids: list[str] = Field(default_factory=list)
    memory_proposal_ids: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    redacted: bool = True
    created_at: datetime


class FactValue(CraikModel):
    """Proposed fact payload for memory updates."""

    entity: str
    relation: str
    value: str
    source: str
    confidence: float = Field(ge=0.0, le=1.0)
    scope: MemoryScope
    trust_class: TrustClass


class MemoryProposal(CraikModel):
    """Reviewable memory update proposal."""

    schema_: Literal["craik.memory_proposal"] = Field(
        default="craik.memory_proposal",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    task_id: str
    run_id: str | None = None
    step_id: str | None = None
    handoff_id: str | None = None
    operation: ProposalOperation
    fact: FactValue
    evidence: list[EvidenceReference] = Field(default_factory=list)
    requires_approval: bool = True
    status: ProposalStatus = "pending"
    decision_reason: str | None = None
    decided_by: str | None = None
    decided_at: datetime | None = None


class MemoryRequiredCapabilities(CraikModel):
    """Minimum memory backend behaviors Craik depends on."""

    health: bool
    metadata: bool
    fact_write: bool
    fact_query: bool
    fact_get: bool
    fact_provenance: bool


class MemoryOptionalCapabilities(CraikModel):
    """Optional memory backend behaviors Craik can use when available."""

    recall: bool = False
    conflicts: bool = False
    source_attestation: Literal["warn", "enforce", "off"] = "off"
    federation: bool = False


class MemoryBackendCapabilities(CraikModel):
    """Detected memory backend capability snapshot."""

    schema_: Literal["craik.memory_backend_capabilities"] = Field(
        default="craik.memory_backend_capabilities",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    backend: MemoryBackend
    node_url: str | None = None
    node_id: str | None = None
    auth_required: bool = False
    required: MemoryRequiredCapabilities
    optional: MemoryOptionalCapabilities = Field(default_factory=MemoryOptionalCapabilities)
    checked_at: datetime


class GatewayConfig(CraikModel):
    """Configuration for the always-on operator gateway process."""

    schema_: Literal["craik.gateway_config"] = Field(
        default="craik.gateway_config",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    project_id: str | None = None
    mode: GatewayMode = "daemon"
    bind_host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1, le=65535)
    pid_file: str | None = None
    log_file: str | None = None
    policy_envelope_id: str | None = None
    enabled: bool = False
    created_at: datetime

    @model_validator(mode="after")
    def validate_gateway_config(self) -> GatewayConfig:
        """Keep daemon mode explicit and local by default."""
        if self.mode == "daemon" and not self.pid_file:
            raise ValueError("daemon gateway mode requires pid_file")
        if self.bind_host in {"0.0.0.0", "::"} and not self.policy_envelope_id:
            raise ValueError("public gateway bind requires policy_envelope_id")
        return self


class GatewayRuntimeState(CraikModel):
    """Persisted lifecycle state for the operator gateway process."""

    schema_: Literal["craik.gateway_runtime_state"] = Field(
        default="craik.gateway_runtime_state",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    config_id: str
    project_id: str | None = None
    mode: GatewayMode
    status: GatewayRuntimeStatus
    pid: int | None = Field(default=None, ge=1)
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    updated_at: datetime
    policy_envelope_id: str | None = None
    receipt_ids: list[str] = Field(default_factory=list)
    supervision_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_gateway_state(self) -> GatewayRuntimeState:
        """Keep lifecycle state internally consistent."""
        if self.status == "running" and self.started_at is None:
            raise ValueError("running gateway state requires started_at")
        if self.status == "stopped" and self.stopped_at is None:
            raise ValueError("stopped gateway state requires stopped_at")
        if self.status == "failed" and not self.supervision_notes:
            raise ValueError("failed gateway state requires supervision_notes")
        if self.pid is not None and self.status not in {"starting", "running", "stopping"}:
            raise ValueError("gateway pid is only valid while process may be active")
        return self


class AgentSessionState(CraikModel):
    """Persisted lifecycle state for a persistent Craik agent session."""

    schema_: Literal["craik.agent_session_state"] = Field(
        default="craik.agent_session_state",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    project_id: str | None = None
    operator_subject: str = Field(min_length=1)
    operator_issuer: str | None = None
    provider_id: str = Field(min_length=1)
    model_id: str | None = None
    auth_profile_id: str | None = None
    auth_identity_hash: str | None = None
    policy_envelope_id: str | None = None
    mode: AgentSessionMode = "foreground"
    status: AgentSessionStatus
    pid: int | None = Field(default=None, ge=1)
    endpoint_url: str | None = None
    active_task_id: str | None = None
    active_run_id: str | None = None
    started_at: datetime | None = None
    last_activity_at: datetime | None = None
    stopped_at: datetime | None = None
    updated_at: datetime
    receipt_ids: list[str] = Field(default_factory=list)
    handoff_ids: list[str] = Field(default_factory=list)
    recovery_session_id: str | None = None
    recovery_metadata: dict[str, Any] = Field(default_factory=dict)
    supervision_notes: list[str] = Field(default_factory=list)
    redacted: bool = True
    receipt_hmac: str | None = None

    @model_validator(mode="after")
    def validate_agent_session_state(self) -> AgentSessionState:
        """Keep persistent agent lifecycle and trust-boundary state consistent."""
        if self.status in {"running", "idle", "stopping"} and self.started_at is None:
            raise ValueError("active agent session state requires started_at")
        if self.status == "stopped" and self.stopped_at is None:
            raise ValueError("stopped agent session state requires stopped_at")
        if self.status in {"failed", "auth_expired", "provider_unavailable", "sandbox_failed"}:
            if not self.supervision_notes:
                raise ValueError("failed agent session state requires supervision_notes")
        if self.pid is not None and self.status not in {"starting", "running", "idle", "stopping"}:
            raise ValueError("agent session pid is only valid while process may be active")
        if (
            self.started_at is not None
            and self.last_activity_at is not None
            and self.last_activity_at < self.started_at
        ):
            raise ValueError("last_activity_at cannot precede started_at")
        if (
            self.started_at is not None
            and self.stopped_at is not None
            and self.stopped_at < self.started_at
        ):
            raise ValueError("stopped_at cannot precede started_at")
        return self


class AgentSessionEvent(CraikModel):
    """Durable event emitted by a persistent Craik agent session."""

    schema_: Literal["craik.agent_session_event"] = Field(
        default="craik.agent_session_event",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    session_id: str
    event_type: str = Field(min_length=1)
    operator_subject: str = Field(min_length=1)
    operator_issuer: str | None = None
    project_id: str | None = None
    provider_id: str | None = None
    model_id: str | None = None
    policy_envelope_id: str | None = None
    task_id: str | None = None
    run_id: str | None = None
    handoff_id: str | None = None
    receipt_ids: list[str] = Field(default_factory=list)
    recovery_metadata: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    redacted: bool = True
    receipt_hmac: str | None = None


class GatewaySchedule(CraikModel):
    """Cron-like schedule definition for gateway-created tasks."""

    schema_: Literal["craik.gateway_schedule"] = Field(
        default="craik.gateway_schedule",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    project_id: str
    title: str
    objective: str
    cron: str
    requested_by: str = "gateway:scheduler"
    priority: Priority = "normal"
    mode: TaskMode = "implement"
    policy_envelope_id: str | None = None
    channel: str | None = None
    receipt_ids: list[str] = Field(default_factory=list)


class ScheduledAutomation(CraikModel):
    """Gateway automation definition backed by a cron-like schedule."""

    schema_: Literal["craik.scheduled_automation"] = Field(
        default="craik.scheduled_automation",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    schedule: GatewaySchedule
    enabled: bool = False
    policy_envelope_id: str
    required_capability: str = "gateway.schedule.execute"
    receipt_ids: list[str] = Field(default_factory=list)


class ChannelAdapterIdentity(CraikModel):
    """Stable identity for one external operator channel adapter."""

    adapter_id: str
    channel: ChannelKind
    name: str
    adapter_version: str
    service: str | None = None


class ChannelAdapterCapability(CraikModel):
    """One capability exposed by a channel adapter boundary."""

    name: str
    direction: ChannelCapabilityDirection
    description: str
    grant_required: bool = True
    receipt_required: bool = True


class ChannelPayloadShape(CraikModel):
    """Inspectable payload fields for channel ingress and egress."""

    fields: list[str] = Field(min_length=1)
    redacted_fields: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChannelReceiptRequirement(CraikModel):
    """Receipt requirements for channel adapter activity."""

    required: bool = True
    receipt_schema: Literal["craik.capability_receipt"] = "craik.capability_receipt"
    capabilities: list[str] = Field(min_length=1)


class ChannelTrustBoundary(CraikModel):
    """Policy and trust boundaries preserved across external channels."""

    policy_envelope_required: bool = True
    allowlist_required: bool = True
    inbound_identity_required: bool = True
    secrets_in_config_allowed: Literal[False] = False
    notes: list[str] = Field(default_factory=list)


class ChannelAdapterContract(CraikModel):
    """Contract for external operator ingress and response channel adapters."""

    schema_: Literal["craik.channel_adapter_contract"] = Field(
        default="craik.channel_adapter_contract",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    identity: ChannelAdapterIdentity
    capabilities: list[ChannelAdapterCapability] = Field(min_length=1)
    inbound_event: ChannelPayloadShape
    outbound_response: ChannelPayloadShape
    receipts: ChannelReceiptRequirement
    trust_boundary: ChannelTrustBoundary = Field(default_factory=ChannelTrustBoundary)
    docs: list[str] = Field(min_length=1)
    created_at: datetime

    @model_validator(mode="after")
    def validate_channel_adapter_contract(self) -> ChannelAdapterContract:
        """Keep channel adapters policy-bound and receipt-producing."""
        inbound_required = {"event_id", "channel", "received_at", "sender"}
        outbound_required = {"status", "summary"}
        inbound_fields = set(self.inbound_event.fields)
        outbound_fields = set(self.outbound_response.fields)
        if missing := sorted(inbound_required - inbound_fields):
            raise ValueError(f"inbound event shape missing fields: {', '.join(missing)}")
        if missing := sorted(outbound_required - outbound_fields):
            raise ValueError(f"outbound response shape missing fields: {', '.join(missing)}")
        capability_names = {capability.name for capability in self.capabilities}
        receipt_capabilities = set(self.receipts.capabilities)
        if missing := sorted(receipt_capabilities - capability_names):
            raise ValueError(f"receipt capabilities are not declared: {', '.join(missing)}")
        if not self.receipts.required:
            raise ValueError("channel adapter contracts require receipts")
        if not self.trust_boundary.policy_envelope_required:
            raise ValueError("channel adapter contracts require policy envelopes")
        return self


class ChannelExternalAccount(CraikModel):
    """External account observed at a channel boundary."""

    channel: ChannelKind
    external_id: str
    service: str | None = None
    display_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChannelIdentityPairing(CraikModel):
    """Pairing state between an external channel account and a Craik subject."""

    schema_: Literal["craik.channel_identity_pairing"] = Field(
        default="craik.channel_identity_pairing",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    external_account: ChannelExternalAccount
    status: ChannelPairingStatus
    subject: str | None = None
    policy_envelope_id: str | None = None
    paired_at: datetime | None = None
    paired_by: str | None = None
    revoked_at: datetime | None = None
    revoked_by: str | None = None
    revocation_reason: str | None = None
    audit_ids: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_channel_identity_pairing(self) -> ChannelIdentityPairing:
        """Require explicit pairing and revocation evidence."""
        if self.status == "unpaired":
            forbidden = {
                "subject": self.subject,
                "policy_envelope_id": self.policy_envelope_id,
                "paired_at": self.paired_at,
                "paired_by": self.paired_by,
                "revoked_at": self.revoked_at,
                "revoked_by": self.revoked_by,
                "revocation_reason": self.revocation_reason,
            }
            if any(value is not None for value in forbidden.values()):
                raise ValueError("unpaired channel identities must not carry authority fields")
            if self.expires_at is None:
                raise ValueError("unpaired channel identities require expires_at")
        if self.status == "paired":
            if not self.subject:
                raise ValueError("paired channel identities require subject")
            if not self.policy_envelope_id:
                raise ValueError("paired channel identities require policy_envelope_id")
            if self.paired_at is None or not self.paired_by:
                raise ValueError("paired channel identities require paired_at and paired_by")
            if not self.audit_ids:
                raise ValueError("paired channel identities require audit_ids")
            if self.expires_at is None:
                raise ValueError("paired channel identities require expires_at")
            if self.revoked_at is not None or self.revoked_by or self.revocation_reason:
                raise ValueError("paired channel identities must not carry revocation fields")
        if self.status == "revoked":
            if not self.subject:
                raise ValueError("revoked channel identities preserve subject")
            if self.paired_at is None or not self.paired_by:
                raise ValueError("revoked channel identities preserve pairing audit fields")
            if self.revoked_at is None or not self.revoked_by or not self.revocation_reason:
                raise ValueError("revoked channel identities require revocation audit fields")
            if not self.audit_ids:
                raise ValueError("revoked channel identities require audit_ids")
        return self


class ChannelAllowlistRule(CraikModel):
    """One allowlist selector for normalized inbound channel events."""

    id: str
    description: str
    channel: ChannelKind | None = None
    service: str | None = None
    sender_external_ids: list[str] = Field(default_factory=list)
    workspace_ids: list[str] = Field(default_factory=list)
    thread_ids: list[str] = Field(default_factory=list)
    metadata_match: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_allowlist_rule(self) -> ChannelAllowlistRule:
        """Require at least one selector so broad allows are explicit."""
        if not any(
            (
                self.channel,
                self.service,
                self.sender_external_ids,
                self.workspace_ids,
                self.thread_ids,
                self.metadata_match,
            )
        ):
            raise ValueError("channel allowlist rules require at least one selector")
        return self


class ChannelAllowlist(CraikModel):
    """Allowlist policy for controlled external channel ingress."""

    schema_: Literal["craik.channel_allowlist"] = Field(
        default="craik.channel_allowlist",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    channel: ChannelKind
    default_action: ChannelAllowlistAction = "deny"
    rules: list[ChannelAllowlistRule] = Field(default_factory=list)
    audit_required: bool = True
    denial_capability: str = "channel.ingress.denied"
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_channel_allowlist(self) -> ChannelAllowlist:
        """Keep external ingress deny-by-default and auditable."""
        if self.default_action != "deny":
            raise ValueError("channel allowlists must default to deny")
        if not self.audit_required:
            raise ValueError("channel allowlist decisions require audit")
        return self


class ModelProviderCapability(CraikModel):
    """One capability exposed by a model provider."""

    name: str
    mode: ModelProviderMode
    description: str
    grant_required: bool = True


class ModelProvider(CraikModel):
    """Model provider and runtime execution path metadata."""

    schema_: Literal["craik.model_provider"] = Field(
        default="craik.model_provider",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    name: str
    provider: str
    modes: list[ModelProviderMode] = Field(min_length=1)
    capabilities: list[ModelProviderCapability] = Field(min_length=1)
    trust_boundary: ModelProviderTrustBoundary
    config_refs: list[str] = Field(default_factory=list)
    secret_ref_names: list[str] = Field(default_factory=list)
    budget_ref: str | None = None
    quota_ref: str | None = None
    runtime_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    docs: list[str] = Field(min_length=1)
    created_at: datetime

    @model_validator(mode="after")
    def validate_model_provider(self) -> ModelProvider:
        """Keep provider metadata separate from secrets."""
        capability_modes = {capability.mode for capability in self.capabilities}
        missing_modes = capability_modes - set(self.modes)
        if missing_modes:
            missing = ", ".join(sorted(missing_modes))
            raise ValueError(f"provider capabilities reference undeclared modes: {missing}")
        secret_tokens = ("secret", "token", "api_key", "apikey", "password", "credential")
        for key in self.metadata:
            normalized = key.lower().replace("-", "_")
            if any(token in normalized for token in secret_tokens):
                raise ValueError("provider metadata must not contain secret-like keys")
        return self


class SandboxBackendCapability(CraikModel):
    """One provider-neutral capability exposed by a sandbox backend."""

    name: str
    operations: list[str] = Field(min_length=1)
    grant_required: bool = True
    receipt_required: bool = True
    description: str


class SandboxBackendPolicy(CraikModel):
    """Policy controls required before a sandbox backend can execute."""

    policy_envelope_required: bool = True
    capability_grant_required: bool = True
    receipt_required: bool = True
    redaction_required: bool = True
    secrets_in_config_allowed: Literal[False] = False
    notes: list[str] = Field(default_factory=list)


class SandboxBackend(CraikModel):
    """Provider-neutral execution environment backend contract."""

    schema_: Literal["craik.sandbox_backend"] = Field(
        default="craik.sandbox_backend",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    name: str
    kind: SandboxBackendKind
    isolation_mode: SandboxIsolationMode
    capabilities: list[SandboxBackendCapability] = Field(min_length=1)
    policy: SandboxBackendPolicy = Field(default_factory=SandboxBackendPolicy)
    runtime_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    docs: list[str] = Field(min_length=1)
    created_at: datetime

    @model_validator(mode="after")
    def validate_sandbox_backend(self) -> SandboxBackend:
        """Keep sandbox backends provider-neutral and policy-bound."""
        expected_isolation: dict[SandboxBackendKind, SandboxIsolationMode] = {
            "local_process": "process",
            "container": "container",
            "remote_shell": "remote",
            "browser_tool": "browser",
        }
        expected = expected_isolation[self.kind]
        if self.isolation_mode != expected:
            raise ValueError(f"{self.kind} backends require {expected!r} isolation")
        if not self.policy.policy_envelope_required:
            raise ValueError("sandbox backends require policy envelopes")
        if not self.policy.capability_grant_required:
            raise ValueError("sandbox backends require capability grants")
        if not self.policy.receipt_required:
            raise ValueError("sandbox backends require receipts")
        if not self.policy.redaction_required:
            raise ValueError("sandbox backends require redaction")
        for capability in self.capabilities:
            if not capability.grant_required:
                raise ValueError("sandbox backend capabilities require grants")
            if not capability.receipt_required:
                raise ValueError("sandbox backend capabilities require receipts")
        forbidden_tokens = (
            "secret",
            "token",
            "api_key",
            "apikey",
            "password",
            "credential",
            "provider_id",
        )
        for key in self.metadata:
            normalized = key.lower().replace("-", "_")
            if any(token in normalized for token in forbidden_tokens):
                raise ValueError(
                    "sandbox backend metadata must not contain secret or provider keys"
                )
        return self


class MemoryFactReference(CraikModel):
    """Reference to a memory fact involved in a run-scoped diff."""

    id: str | None = None
    cid: str | None = None
    entity: str
    relation: str
    value: str
    source: str
    scope: MemoryScope
    trust_class: TrustClass


class MemoryWriteFailure(CraikModel):
    """A failed attempt to write memory."""

    fact: MemoryFactReference
    reason: str
    attempted_at: datetime


class MemoryContradictionPreview(CraikModel):
    """Likely contradiction identified before memory promotion."""

    entity: str
    relation: str
    existing_value: str
    proposed_value: str
    reason: str


class MemoryDiff(CraikModel):
    """Run-scoped explanation of memory reads, proposals, writes, and failures."""

    schema_: Literal["craik.memory_diff"] = Field(default="craik.memory_diff", alias="schema")
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    task_id: str
    proposals_created: list[str] = Field(default_factory=list)
    proposals_approved: list[str] = Field(default_factory=list)
    proposals_rejected: list[str] = Field(default_factory=list)
    facts_written: list[MemoryFactReference] = Field(default_factory=list)
    write_failures: list[MemoryWriteFailure] = Field(default_factory=list)
    facts_read: list[MemoryFactReference] = Field(default_factory=list)
    created_at: datetime


class MemoryImpactPreview(CraikModel):
    """Pre-write preview of memory changes and likely contradictions."""

    schema_: Literal["craik.memory_impact_preview"] = Field(
        default="craik.memory_impact_preview",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    task_id: str
    facts_to_add: list[MemoryFactReference] = Field(default_factory=list)
    facts_to_invalidate: list[MemoryFactReference] = Field(default_factory=list)
    likely_contradictions: list[MemoryContradictionPreview] = Field(default_factory=list)
    evidence_missing: list[str] = Field(default_factory=list)
    scope_summary: dict[MemoryScope, int] = Field(default_factory=dict)
    created_at: datetime


class ContradictionReport(CraikModel):
    """Incompatible assertions that need resolution."""

    schema_: Literal["craik.contradiction_report"] = Field(
        default="craik.contradiction_report",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    task_id: str | None = None
    facts: list[str] = Field(min_length=2)
    summary: str
    affected_artifacts: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    proposed_resolution: str | None = None
    status: ContradictionStatus = "open"
    owner: str | None = None
    stigmem_conflict_id: str | None = None
    created_at: datetime | None = None
    resolved_at: datetime | None = None


if not TYPE_CHECKING:
    __all__ = [name for name in globals() if not name.startswith("_")]
