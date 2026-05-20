"""Worker, review, debate, adjudication, and delegation contracts."""

# ruff: noqa

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import *
from .core import *


class WorkerFinding(CraikModel):
    """One structured finding from a specialist worker."""

    summary: str
    severity: FindingSeverity = "info"
    evidence_ids: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    contradiction_ids: list[str] = Field(default_factory=list)


class WorkerResult(CraikModel):
    """Typed output from a role-specific specialist agent."""

    schema_: Literal["craik.worker_result"] = Field(
        default="craik.worker_result",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    task_id: str
    run_id: str | None = None
    role_id: str
    role_kind: AgentRoleKind
    runner: RunnerMetadata | None = None
    status: WorkerResultStatus
    summary: str
    findings: list[WorkerFinding] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    proposed_actions: list[str] = Field(default_factory=list)
    contradiction_ids: list[str] = Field(default_factory=list)
    evidence: list[EvidenceReference] = Field(default_factory=list)
    receipt_ids: list[str] = Field(default_factory=list)
    handoff_id: str | None = None
    diagnostics: list[str] = Field(default_factory=list)
    redacted: bool = True
    created_at: datetime


class RuntimeCriticFinding(CraikModel):
    """Reviewable, non-authoritative runtime critic finding."""

    schema_: Literal["craik.runtime_critic_finding"] = Field(
        default="craik.runtime_critic_finding",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    task_id: str
    project_id: str | None = None
    run_id: str | None = None
    handoff_id: str | None = None
    critic_role_id: str | None = None
    finding_type: RuntimeCriticFindingType
    severity: FindingSeverity = "medium"
    summary: str
    rationale: str
    affected_artifacts: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    proposed_actions: list[str] = Field(default_factory=list)
    authoritative: Literal[False] = False
    review_status: FindingReviewStatus = "reviewable"
    adjudication_id: str | None = None
    created_at: datetime

    @model_validator(mode="after")
    def validate_review_boundary(self) -> RuntimeCriticFinding:
        """Keep critic findings actionable and non-authoritative until adjudication."""
        if self.review_status == "adjudicated" and not self.adjudication_id:
            raise ValueError("adjudicated critic findings require adjudication_id")
        if self.severity in {"high", "critical"} and not self.proposed_actions:
            raise ValueError("high-severity critic findings require proposed_actions")
        if self.finding_type in {"unsupported_claim", "stale_evidence"} and not self.evidence_ids:
            raise ValueError("evidence-related critic findings require evidence_ids")
        return self


class RedTeamFinding(CraikModel):
    """Reviewable, non-authoritative adversarial finding for high-risk work."""

    schema_: Literal["craik.red_team_finding"] = Field(
        default="craik.red_team_finding",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    task_id: str
    project_id: str | None = None
    run_id: str | None = None
    handoff_id: str | None = None
    red_team_role_id: str | None = None
    finding_type: RedTeamFindingType
    severity: FindingSeverity = "high"
    summary: str
    attack_path: str
    affected_artifacts: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    proposed_actions: list[str] = Field(default_factory=list)
    blocking: bool = False
    authoritative: Literal[False] = False
    review_status: FindingReviewStatus = "reviewable"
    adjudication_id: str | None = None
    created_at: datetime

    @model_validator(mode="after")
    def validate_red_team_boundary(self) -> RedTeamFinding:
        """Require blockers to be actionable and keep findings reviewable."""
        if self.review_status == "adjudicated" and not self.adjudication_id:
            raise ValueError("adjudicated red-team findings require adjudication_id")
        if self.blocking and not self.proposed_actions:
            raise ValueError("blocking red-team findings require proposed_actions")
        if self.blocking and self.severity not in {"high", "critical"}:
            raise ValueError("blocking red-team findings must be high or critical severity")
        return self


class DebateTurn(CraikModel):
    """One structured contribution to an agent debate."""

    schema_: Literal["craik.debate_turn"] = Field(default="craik.debate_turn", alias="schema")
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    task_id: str
    debate_id: str
    role_id: str
    role_kind: AgentRoleKind
    worker_result_id: str | None = None
    position: DebateTurnPosition
    claim: str
    rationale: str
    evidence_ids: list[str] = Field(default_factory=list)
    assumption_ids: list[str] = Field(default_factory=list)
    contradiction_ids: list[str] = Field(default_factory=list)
    created_at: datetime


class DebateSummary(CraikModel):
    """Deterministic outcome summary for a bounded agent debate."""

    schema_: Literal["craik.debate_summary"] = Field(
        default="craik.debate_summary",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    task_id: str
    debate_id: str
    topic: str
    turn_ids: list[str] = Field(default_factory=list)
    outcome: DebateOutcome
    summary: str
    agreements: list[str] = Field(default_factory=list)
    unresolved_disagreements: list[str] = Field(default_factory=list)
    contradiction_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    created_at: datetime

    @model_validator(mode="after")
    def validate_outcome_links(self) -> DebateSummary:
        """Require explicit disagreement or contradiction links for non-agreement outcomes."""
        if self.outcome == "unresolved_disagreement" and not self.unresolved_disagreements:
            raise ValueError("unresolved debate summaries require unresolved disagreement text")
        if self.outcome == "contradiction_opened" and not self.contradiction_ids:
            raise ValueError("contradiction debate summaries require contradiction ids")
        return self


class ReviewRequest(CraikModel):
    """Request from one role for bounded cross-agent review."""

    schema_: Literal["craik.review_request"] = Field(
        default="craik.review_request",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    task_id: str
    requester_role_id: str
    reviewer_role_id: str
    reviewer_role_kind: AgentRoleKind
    subject_worker_result_ids: list[str] = Field(default_factory=list)
    subject_handoff_ids: list[str] = Field(default_factory=list)
    subject_debate_summary_ids: list[str] = Field(default_factory=list)
    focus: list[str] = Field(default_factory=list)
    policy_envelope_id: str | None = None
    receipt_ids: list[str] = Field(default_factory=list)
    status: ReviewRequestStatus = "open"
    due_at: datetime | None = None
    created_at: datetime

    @model_validator(mode="after")
    def validate_subjects(self) -> ReviewRequest:
        """Require at least one worker result or debate summary under review."""
        if (
            not self.subject_worker_result_ids
            and not self.subject_handoff_ids
            and not self.subject_debate_summary_ids
        ):
            raise ValueError("review requests require at least one review subject")
        return self


class ReviewResult(CraikModel):
    """Result returned by a specialist reviewer."""

    schema_: Literal["craik.review_result"] = Field(
        default="craik.review_result",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    task_id: str
    review_request_id: str
    reviewer_role_id: str
    reviewer_role_kind: AgentRoleKind
    decision: ReviewDecision
    summary: str
    finding_ids: list[str] = Field(default_factory=list)
    worker_result_ids: list[str] = Field(default_factory=list)
    subject_handoff_ids: list[str] = Field(default_factory=list)
    debate_summary_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    contradiction_ids: list[str] = Field(default_factory=list)
    receipt_ids: list[str] = Field(default_factory=list)
    handoff_id: str | None = None
    created_at: datetime


class AdjudicatedFinding(CraikModel):
    """One finding decision made by an adjudicator."""

    source_worker_result_id: str | None = None
    source_finding_id: str | None = None
    source_review_result_id: str | None = None
    decision: AdjudicationDecision
    rationale: str
    revised_summary: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_revision(self) -> AdjudicatedFinding:
        """Require replacement text for revised findings."""
        if self.decision == "revised" and not self.revised_summary:
            raise ValueError("revised adjudicated findings require revised_summary")
        return self


class AdjudicationOutcome(CraikModel):
    """Final or deferred adjudicator decision over reviewed specialist outputs."""

    schema_: Literal["craik.adjudication_outcome"] = Field(
        default="craik.adjudication_outcome",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    task_id: str
    adjudicator_role_id: str
    decision: AdjudicationDecision
    summary: str
    review_result_ids: list[str] = Field(default_factory=list)
    worker_result_ids: list[str] = Field(default_factory=list)
    debate_summary_ids: list[str] = Field(default_factory=list)
    adjudicated_findings: list[AdjudicatedFinding] = Field(default_factory=list)
    unresolved_disagreements: list[str] = Field(default_factory=list)
    contradiction_ids: list[str] = Field(default_factory=list)
    receipt_ids: list[str] = Field(default_factory=list)
    handoff_ids: list[str] = Field(default_factory=list)
    policy_review_result_ids: list[str] = Field(default_factory=list)
    adversarial_review_result_ids: list[str] = Field(default_factory=list)
    created_at: datetime

    @model_validator(mode="after")
    def validate_decision_payload(self) -> AdjudicationOutcome:
        """Ensure adjudication payloads explain their durable decision."""
        if self.decision == "deferred" and not self.unresolved_disagreements:
            raise ValueError("deferred adjudication requires unresolved disagreements")
        if self.decision != "deferred" and not self.adjudicated_findings:
            raise ValueError("non-deferred adjudication requires adjudicated findings")
        return self


class HumanDelegationPoint(CraikModel):
    """Human decision point that requires agent stop, clarification, or transfer."""

    schema_: Literal["craik.human_delegation_point"] = Field(
        default="craik.human_delegation_point",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    task_id: str
    kind: HumanDelegationKind
    status: HumanDelegationStatus = "open"
    summary: str
    requested_decision: str
    requested_by: str
    owner: str | None = None
    run_id: str | None = None
    role_id: str | None = None
    intent_lock_id: str | None = None
    policy_envelope_id: str | None = None
    contradiction_ids: list[str] = Field(default_factory=list)
    scope_change_request_ids: list[str] = Field(default_factory=list)
    handoff_ids: list[str] = Field(default_factory=list)
    receipt_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    resolved_at: datetime | None = None
    resolution: str | None = None

    @model_validator(mode="after")
    def validate_resolution(self) -> HumanDelegationPoint:
        """Require resolution details when a delegation point is resolved."""
        if self.status == "resolved" and not self.resolution:
            raise ValueError("resolved delegation points require resolution text")
        return self


class ScopeChangeRequest(CraikModel):
    """Request to change a task's accepted intent or authority boundary."""

    schema_: Literal["craik.scope_change_request"] = Field(
        default="craik.scope_change_request",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    task_id: str
    intent_lock_id: str
    requested_by: str
    reason: str
    current_scope: list[str] = Field(default_factory=list)
    proposed_scope: list[str] = Field(default_factory=list)
    policy_envelope_id: str | None = None
    delegation_id: str | None = None
    contradiction_ids: list[str] = Field(default_factory=list)
    handoff_ids: list[str] = Field(default_factory=list)
    receipt_ids: list[str] = Field(default_factory=list)
    status: ScopeChangeStatus = "pending"
    created_at: datetime

    @model_validator(mode="after")
    def validate_scope_delta(self) -> ScopeChangeRequest:
        """Require proposed scope for meaningful scope-change requests."""
        if not self.proposed_scope:
            raise ValueError("scope change requests require proposed scope")
        return self


class ScopeChangeResult(CraikModel):
    """Human decision for a requested scope change."""

    schema_: Literal["craik.scope_change_result"] = Field(
        default="craik.scope_change_result",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    task_id: str
    scope_change_request_id: str
    decision: Literal["accepted", "rejected"]
    decided_by: str
    rationale: str
    updated_intent_lock_id: str | None = None
    policy_envelope_id: str | None = None
    contradiction_ids: list[str] = Field(default_factory=list)
    handoff_ids: list[str] = Field(default_factory=list)
    receipt_ids: list[str] = Field(default_factory=list)
    created_at: datetime

    @model_validator(mode="after")
    def validate_accepted_scope_change(self) -> ScopeChangeResult:
        """Accepted scope changes must point at the updated intent lock."""
        if self.decision == "accepted" and not self.updated_intent_lock_id:
            raise ValueError("accepted scope changes require updated_intent_lock_id")
        return self


INSTRUCTION_SOURCE_DEFAULT_PATHS: dict[InstructionSourceKind, str] = {
    "agents_md": "AGENTS.md",
    "claude_md": "CLAUDE.md",
    "gemini_md": "GEMINI.md",
    "hermes_md": "HERMES.md",
    "skills_md": "SKILLS.md",
    "cursor_rules": ".cursorrules",
    "github_copilot_instructions": ".github/copilot-instructions.md",
    "codex_instructions": ".codex/instructions.md",
    "policy_doc": "",
}


if not TYPE_CHECKING:
    __all__ = [name for name in globals() if not name.startswith("_")]
