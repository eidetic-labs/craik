"""Pydantic models for Craik's v0.1 contract surface."""

# ruff: noqa

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "0.1.0"

Priority = Literal["low", "normal", "high", "urgent"]
TaskMode = Literal["plan", "review", "implement", "verify"]
MemoryBackend = Literal["ephemeral", "local", "stigmem"]
MemoryScope = Literal["local", "team", "company", "public"]
PolicyProfile = Literal["strict", "trusted-local", "automation", "custom"]
ProposalOperation = Literal["add", "update", "invalidate"]
ProposalStatus = Literal["pending", "approved", "rejected"]
TrustClass = Literal["observed", "reported", "inferred", "policy", "external", "stale-risk"]
MemoryDiffChangeKind = Literal["created", "approved", "rejected", "written", "failed", "read"]
ContradictionStatus = Literal["open", "resolved", "ignored"]
WorkGraphEventType = Literal[
    "created",
    "depends_on",
    "verified_by",
    "contradicts",
    "supersedes",
    "implements",
    "blocks",
]
ReceiptStatus = Literal["passed", "failed", "blocked", "denied", "skipped"]
RunStatus = Literal["completed", "incomplete", "blocked", "failed"]
TaskRunPhase = Literal["plan", "act", "observe", "evaluate", "continue", "stop"]
TaskRunStatus = Literal["pending", "running", "completed", "blocked", "failed", "interrupted"]
AgentMessageKind = Literal[
    "request",
    "response",
    "status",
    "question",
    "answer",
    "decision",
    "handoff",
    "review",
]
AgentMessageStatus = Literal["sent", "received", "acknowledged", "blocked"]
RunnerMode = Literal["fixture", "prompt-handoff", "live"]
RunnerResultStatus = Literal["completed", "blocked", "failed", "partial"]
WorkerResultStatus = Literal["completed", "blocked", "failed", "partial"]
DebateTurnPosition = Literal["supports", "opposes", "clarifies", "questions", "blocks"]
DebateOutcome = Literal["agreement", "unresolved_disagreement", "contradiction_opened"]
ReviewRequestStatus = Literal["open", "completed", "cancelled"]
ReviewDecision = Literal["approved", "changes_requested", "blocked", "deferred"]
AdjudicationDecision = Literal["accepted", "rejected", "revised", "deferred"]
FindingSeverity = Literal["info", "low", "medium", "high", "critical"]
FindingReviewStatus = Literal["reviewable", "adjudicated", "dismissed"]
RuntimeCriticFindingType = Literal[
    "unsupported_claim",
    "policy_violation",
    "scope_drift",
    "missing_validation",
    "stale_evidence",
    "missing_handoff",
    "unredacted_sensitive_content",
    "risky_memory_write",
    "other",
]
RedTeamFindingType = Literal[
    "prompt_injection",
    "privilege_escalation",
    "data_exfiltration",
    "destructive_action",
    "policy_bypass",
    "memory_poisoning",
    "adversarial_input",
    "other",
]
QualityScoreBand = Literal["excellent", "adequate", "poor"]
HandoffQualityComponentName = Literal[
    "summary",
    "completed_actions",
    "validation_records",
    "receipt_links",
    "evidence_links",
    "context_debt",
    "unresolved_risks",
    "next_steps",
    "self_audit",
]
ContextDebtKind = Literal[
    "omitted_doc",
    "excluded_doc",
    "stale_instruction",
    "unresolved_assumption",
    "missing_external_state",
    "missing_memory_facts",
    "active_instruction_constraint",
    "missing_case_file",
    "other",
]
ContextDebtStatus = Literal["created", "carried_forward", "resolved"]
ToolAttestationStatus = Literal["attested", "missing", "expired", "blocked"]
FreshnessProbeStatus = Literal["fresh", "expiring", "expired", "missing"]
FreshnessProbeKind = Literal[
    "github_state",
    "documentation",
    "memory_fact",
    "tool_result",
    "external_state",
    "instruction_source",
    "other",
]
KnownTrapStatus = Literal["active", "expired", "contradicted"]
KnownTrapKind = Literal[
    "workflow",
    "policy",
    "tool",
    "memory",
    "documentation",
    "security",
    "other",
]
ScratchpadStatus = Literal["active", "expired", "promoted", "discarded"]
UnknownStatus = Literal["unresolved", "resolved"]
UnknownResolutionSource = Literal[
    "user_input",
    "web_access",
    "repo_inspection",
    "tool_access",
    "memory_query",
    "external_wait",
    "other",
]
ContextRequestStatus = Literal["open", "fulfilled", "cancelled"]
ContextRequestKind = Literal[
    "user_input",
    "repo_inspection",
    "web_access",
    "tool_access",
    "memory_query",
    "external_state",
    "other",
]
ExitDisciplineStatus = Literal["complete", "blocked"]
SkillEntrypointKind = Literal["prompt", "script", "module", "workflow", "docs"]
SkillOmissionSeverity = Literal["low", "medium", "high", "critical"]
SkillScope = Literal["project", "global"]
PluginEntrypointKind = Literal["command", "module", "workflow", "service", "docs"]
PluginCapabilityRisk = Literal["low", "medium", "high", "critical"]
PluginCompatibilityStatus = Literal["supported", "experimental", "unsupported"]
PluginProbationStatus = Literal["probationary", "promoted", "rejected", "expired"]
PluginProbationDecisionKind = Literal["promote", "reject", "expire"]
PluginGrantStatus = Literal["allowed", "denied", "expired", "approval_required"]
AdapterEntrypointKind = Literal["module", "command", "service", "docs"]
ReferenceIntegrationKind = Literal["skill", "plugin", "adapter"]
HumanDelegationKind = Literal["approval", "clarification", "escalation", "ownership_transfer"]
HumanDelegationStatus = Literal["open", "resolved", "cancelled"]
ScopeChangeStatus = Literal["pending", "accepted", "rejected"]
ScopeChangeProtocolDecision = Literal["expand", "sibling", "handoff", "denied"]
InstructionSourceKind = Literal[
    "agents_md",
    "claude_md",
    "gemini_md",
    "hermes_md",
    "skills_md",
    "cursor_rules",
    "github_copilot_instructions",
    "codex_instructions",
    "policy_doc",
]
InstructionTrustBoundary = Literal["project", "repository", "organization", "user", "external"]
InstructionSourceHashStatus = Literal["unchanged", "changed", "missing", "new"]
DistilledInstructionCategory = Literal[
    "instruction",
    "policy",
    "preference",
    "command",
    "boundary",
    "handoff_rule",
    "memory_rule",
    "security_rule",
    "stale_risk",
]
DistilledInstructionPromotionStatus = Literal["proposed", "approved", "rejected", "deferred"]
InstructionPromotionDecision = Literal["approved", "rejected", "deferred"]
RecoveryStatus = Literal["clean_resume", "changed_state", "missing_prior_context"]
GatewayMode = Literal["foreground", "daemon"]
GatewayRuntimeStatus = Literal["stopped", "starting", "running", "stopping", "failed"]
ChannelKind = Literal["messaging", "webhook", "scheduler", "voice", "custom"]
ChannelCapabilityDirection = Literal["inbound", "outbound", "bidirectional"]
ChannelPairingStatus = Literal["unpaired", "paired", "revoked"]
ChannelAllowlistAction = Literal["allow", "deny"]
ModelProviderMode = Literal["chat", "completion", "embedding", "tool", "runner"]
ModelProviderTrustBoundary = Literal["local", "self-hosted", "hosted", "third-party"]
SandboxBackendKind = Literal["local_process", "container", "remote_shell", "browser_tool"]
SandboxIsolationMode = Literal["none", "process", "container", "remote", "browser"]
RunDeltaChangeKind = Literal["created", "updated", "removed", "unchanged"]
RunDeltaEntityType = Literal[
    "handoff",
    "case_file",
    "receipt",
    "contradiction",
    "instruction_constraint",
]
RunnerTrustLevel = Literal["low", "medium", "high"]
RunnerGrantPosture = Literal["deny-by-default", "prompt-for-approval", "allow-with-receipt"]
RunnerCapabilitySupport = Literal["unsupported", "prompt-handoff", "supported"]
AgentRoleKind = Literal[
    "orchestrator",
    "implementer",
    "verifier",
    "adversarial_reviewer",
    "policy_reviewer",
    "docs_reviewer",
    "memory_curator",
    "adjudicator",
]
AgentRoleAuthority = Literal["coordinate", "read", "propose", "review", "adjudicate", "implement"]


class CraikModel(BaseModel):
    """Base model for strict, alias-aware Craik contracts."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


from craik.contracts import runner_models as _runner_models  # noqa: E402

RunnerAdapterRequest = _runner_models.RunnerAdapterRequest
RunnerAdapterResult = _runner_models.RunnerAdapterResult
RunnerCapability = _runner_models.RunnerCapability
RunnerCapabilityMatrix = _runner_models.RunnerCapabilityMatrix
RunnerMetadata = _runner_models.RunnerMetadata
RunnerStepRequest = _runner_models.RunnerStepRequest
RunnerStepResult = _runner_models.RunnerStepResult
RunnerTrustProfile = _runner_models.RunnerTrustProfile

__all__ = [
    "datetime",
    "Any",
    "Literal",
    "BaseModel",
    "ConfigDict",
    "Field",
    "model_validator",
    "SCHEMA_VERSION",
    "Priority",
    "TaskMode",
    "MemoryBackend",
    "MemoryScope",
    "PolicyProfile",
    "ProposalOperation",
    "ProposalStatus",
    "TrustClass",
    "MemoryDiffChangeKind",
    "ContradictionStatus",
    "WorkGraphEventType",
    "ReceiptStatus",
    "RunStatus",
    "TaskRunPhase",
    "TaskRunStatus",
    "AgentMessageKind",
    "AgentMessageStatus",
    "RunnerMode",
    "RunnerResultStatus",
    "WorkerResultStatus",
    "DebateTurnPosition",
    "DebateOutcome",
    "ReviewRequestStatus",
    "ReviewDecision",
    "AdjudicationDecision",
    "FindingSeverity",
    "FindingReviewStatus",
    "RuntimeCriticFindingType",
    "RedTeamFindingType",
    "QualityScoreBand",
    "HandoffQualityComponentName",
    "ContextDebtKind",
    "ContextDebtStatus",
    "ToolAttestationStatus",
    "FreshnessProbeStatus",
    "FreshnessProbeKind",
    "KnownTrapStatus",
    "KnownTrapKind",
    "ScratchpadStatus",
    "UnknownStatus",
    "UnknownResolutionSource",
    "ContextRequestStatus",
    "ContextRequestKind",
    "ExitDisciplineStatus",
    "SkillEntrypointKind",
    "SkillOmissionSeverity",
    "SkillScope",
    "PluginEntrypointKind",
    "PluginCapabilityRisk",
    "PluginCompatibilityStatus",
    "PluginProbationStatus",
    "PluginProbationDecisionKind",
    "PluginGrantStatus",
    "AdapterEntrypointKind",
    "ReferenceIntegrationKind",
    "HumanDelegationKind",
    "HumanDelegationStatus",
    "ScopeChangeStatus",
    "ScopeChangeProtocolDecision",
    "InstructionSourceKind",
    "InstructionTrustBoundary",
    "InstructionSourceHashStatus",
    "DistilledInstructionCategory",
    "DistilledInstructionPromotionStatus",
    "InstructionPromotionDecision",
    "RecoveryStatus",
    "GatewayMode",
    "GatewayRuntimeStatus",
    "ChannelKind",
    "ChannelCapabilityDirection",
    "ChannelPairingStatus",
    "ChannelAllowlistAction",
    "ModelProviderMode",
    "ModelProviderTrustBoundary",
    "SandboxBackendKind",
    "SandboxIsolationMode",
    "RunDeltaChangeKind",
    "RunDeltaEntityType",
    "RunnerTrustLevel",
    "RunnerGrantPosture",
    "RunnerCapabilitySupport",
    "AgentRoleKind",
    "AgentRoleAuthority",
    "CraikModel",
    "RunnerAdapterRequest",
    "RunnerAdapterResult",
    "RunnerCapability",
    "RunnerCapabilityMatrix",
    "RunnerMetadata",
    "RunnerStepRequest",
    "RunnerStepResult",
    "RunnerTrustProfile",
]
