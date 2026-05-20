"""Onboarding, audit, handoff, scoring, and task run contracts."""

# ruff: noqa

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import *
from .core import *
from .instructions import *
from .memory import *
from .review import *
from .runtime import *
from .skills import *


class AgentOnboarding(CraikModel):
    """Runner-readable project context for an agent starting work."""

    schema_: Literal["craik.agent_onboarding"] = Field(
        default="craik.agent_onboarding",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    project_id: str
    project_model: dict[str, Any]
    active_policy: PolicyEnvelope
    docs_boundaries: dict[str, Any]
    recent_handoffs: list[dict[str, Any]] = Field(default_factory=list)
    unresolved_contradictions: list[ContradictionReport] = Field(default_factory=list)
    stale_risk_warnings: list[str] = Field(default_factory=list)
    validation_commands: list[str] = Field(default_factory=list)
    stigmem_backend_status: dict[str, Any] = Field(default_factory=dict)
    known_traps: list[str] = Field(default_factory=list)
    allowed_next_actions: list[str] = Field(default_factory=list)
    created_at: datetime


class SelfAudit(CraikModel):
    """Required handoff self-audit checklist."""

    schema_validated: bool
    redaction_reviewed: bool
    receipts_reviewed: bool
    assumptions_reviewed: bool
    validation_recorded: bool
    policy_exceptions_disclosed: bool
    notes: list[str] = Field(default_factory=list)


class Handoff(CraikModel):
    """Durable run summary for future agents."""

    schema_: Literal["craik.handoff"] = Field(default="craik.handoff", alias="schema")
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    task_id: str
    project_id: str
    intent_lock_id: str | None = None
    agent: str
    status: RunStatus = "completed"
    summary: str
    self_audit: SelfAudit
    completed_actions: list[str] = Field(default_factory=list)
    files_changed: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    commands_run: list[str] = Field(default_factory=list)
    tests_run: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    context_debt: list[str] = Field(default_factory=list)
    policy_exceptions: list[str] = Field(default_factory=list)
    facts_learned: list[str] = Field(default_factory=list)
    facts_invalidated: list[str] = Field(default_factory=list)
    contradictions_opened: list[str] = Field(default_factory=list)
    adjudication_ids: list[str] = Field(default_factory=list)
    unresolved_disagreements: list[str] = Field(default_factory=list)
    open_human_delegation_ids: list[str] = Field(default_factory=list)
    scope_change_request_ids: list[str] = Field(default_factory=list)
    scope_change_result_ids: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    receipt_ids: list[str] = Field(default_factory=list)
    memory_proposal_ids: list[str] = Field(default_factory=list)
    runner_metadata: list[dict[str, Any]] = Field(default_factory=list)
    auth_profile_id: str | None = None
    auth_identity_hash: str | None = None
    operator_subject: str | None = None
    operator_issuer: str | None = None
    created_at: datetime


class QualityScoreComponent(CraikModel):
    """One weighted scoring input for a handoff or evidence coverage score."""

    name: HandoffQualityComponentName
    score: float = Field(ge=0.0, le=1.0)
    weight: float = Field(gt=0.0, le=1.0)
    rationale: str


class HandoffQualityScore(CraikModel):
    """Derived quality score for a handoff's completeness and recovery value."""

    schema_: Literal["craik.handoff_quality_score"] = Field(
        default="craik.handoff_quality_score",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    task_id: str
    project_id: str
    handoff_id: str
    score: float = Field(ge=0.0, le=1.0)
    band: QualityScoreBand
    components: list[QualityScoreComponent] = Field(min_length=1)
    blocking_reasons: list[str] = Field(default_factory=list)
    created_at: datetime

    @model_validator(mode="after")
    def validate_handoff_score_band(self) -> HandoffQualityScore:
        """Keep the derived band aligned with the numeric score."""
        if self.score >= 0.85 and self.band != "excellent":
            raise ValueError("handoff scores >= 0.85 must be excellent")
        if 0.60 <= self.score < 0.85 and self.band != "adequate":
            raise ValueError("handoff scores between 0.60 and 0.85 must be adequate")
        if self.score < 0.60 and self.band != "poor":
            raise ValueError("handoff scores below 0.60 must be poor")
        if self.band == "poor" and not self.blocking_reasons:
            raise ValueError("poor handoff quality scores require blocking_reasons")
        return self


class EvidenceCoverageScore(CraikModel):
    """Derived score for evidence links supporting a handoff or output."""

    schema_: Literal["craik.evidence_coverage_score"] = Field(
        default="craik.evidence_coverage_score",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    task_id: str
    project_id: str | None = None
    handoff_id: str | None = None
    score: float = Field(ge=0.0, le=1.0)
    band: QualityScoreBand
    evidence_ids: list[str] = Field(default_factory=list)
    required_evidence_ids: list[str] = Field(default_factory=list)
    missing_evidence_ids: list[str] = Field(default_factory=list)
    weak_claims: list[str] = Field(default_factory=list)
    created_at: datetime

    @model_validator(mode="after")
    def validate_evidence_score(self) -> EvidenceCoverageScore:
        """Require explicit gaps for poor evidence coverage scores."""
        if self.score >= 0.85 and self.band != "excellent":
            raise ValueError("evidence scores >= 0.85 must be excellent")
        if 0.60 <= self.score < 0.85 and self.band != "adequate":
            raise ValueError("evidence scores between 0.60 and 0.85 must be adequate")
        if self.score < 0.60 and self.band != "poor":
            raise ValueError("evidence scores below 0.60 must be poor")
        if self.band == "poor" and not self.missing_evidence_ids and not self.weak_claims:
            raise ValueError(
                "poor evidence coverage scores require missing evidence or weak claims"
            )
        return self


class TaskRun(CraikModel):
    """Durable state for one governed single-agent task run."""

    schema_: Literal["craik.task_run"] = Field(default="craik.task_run", alias="schema")
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    task_id: str
    case_file_id: str
    policy_envelope_id: str
    intent_lock_id: str | None = None
    runner_id: str
    runner_mode: RunnerMode
    status: TaskRunStatus = "pending"
    phase: TaskRunPhase = "plan"
    iteration: int = Field(default=0, ge=0)
    max_iterations: int = Field(default=5, ge=1)
    wall_clock_budget_seconds: float | None = Field(default=None, gt=0)
    provider_token_budget: int | None = Field(default=None, gt=0)
    provider_tokens_used: int = Field(default=0, ge=0)
    provider_token_budget_remaining: int | None = Field(default=None, ge=0)
    started_at: datetime
    phase_started_at: datetime
    updated_at: datetime
    ended_at: datetime | None = None
    stop_reason: str | None = None
    receipt_ids: list[str] = Field(default_factory=list)
    handoff_id: str | None = None
    runner_metadata: list[dict[str, Any]] = Field(default_factory=list)
    completed_step_keys: list[str] = Field(default_factory=list)
    last_step_key: str | None = None
    auth_profile_id: str | None = None
    auth_identity_hash: str | None = None
    operator_subject: str | None = None
    operator_issuer: str | None = None
    source_handoff_id: str | None = None
    source_task_id: str | None = None
    source_run_id: str | None = None


if not TYPE_CHECKING:
    __all__ = [name for name in globals() if not name.startswith("_")]
