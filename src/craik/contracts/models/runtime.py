"""Work graph, case file, context, freshness, and exit-discipline contracts."""

# ruff: noqa

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import *
from .core import *
from .instructions import *
from .memory import *


class WorkGraphEvent(CraikModel):
    """Event that updates the work graph."""

    schema_: Literal["craik.work_graph_event"] = Field(
        default="craik.work_graph_event",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    task_id: str
    type: WorkGraphEventType
    from_node: str = Field(alias="from")
    to_node: str = Field(alias="to")
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class WorkGraphNode(CraikModel):
    """Exported work graph node."""

    id: str
    type: str
    label: str
    task_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkGraphEdge(CraikModel):
    """Exported work graph edge."""

    id: str
    type: str
    from_node: str = Field(alias="from")
    to_node: str = Field(alias="to")
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkGraphExport(CraikModel):
    """Deterministic export of graph-connected runtime objects."""

    schema_: Literal["craik.work_graph_export"] = Field(
        default="craik.work_graph_export",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    task_id: str | None = None
    nodes: list[WorkGraphNode] = Field(default_factory=list)
    edges: list[WorkGraphEdge] = Field(default_factory=list)
    created_at: datetime


class AgentMessage(CraikModel):
    """Typed agent-to-agent mailbox message with receipt provenance."""

    schema_: Literal["craik.agent_message"] = Field(
        default="craik.agent_message",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    task_id: str
    kind: AgentMessageKind = "request"
    status: AgentMessageStatus = "sent"
    from_agent: str = Field(min_length=1)
    to_agent: str = Field(min_length=1)
    from_role_id: str | None = None
    from_role_kind: str | None = None
    to_role_id: str | None = None
    to_role_kind: str | None = None
    run_id: str | None = None
    handoff_id: str | None = None
    subject: str = Field(min_length=1)
    body: str = Field(min_length=1, max_length=32768)
    receipt_ids: list[str] = Field(min_length=1)
    created_at: datetime
    received_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CaseFile(CraikModel):
    """Task-specific context assembled before execution."""

    schema_: Literal["craik.case_file"] = Field(default="craik.case_file", alias="schema")
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    task_id: str
    objective: str
    policy_envelope_id: str
    intent_lock_id: str | None = None
    facts: list[FactValue] = Field(default_factory=list)
    evidence: list[EvidenceReference] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    docs: list[str] = Field(default_factory=list)
    adrs: list[str] = Field(default_factory=list)
    repo_state: dict[str, Any] = Field(default_factory=dict)
    github_state: dict[str, Any] = Field(default_factory=dict)
    recent_handoffs: list[str] = Field(default_factory=list)
    stale_risks: list[str] = Field(default_factory=list)
    contradictions: list[ContradictionReport] = Field(default_factory=list)
    verification_plan: list[str] = Field(default_factory=list)
    context_budget: dict[str, Any] = Field(default_factory=dict)


class ContextDebtRecord(CraikModel):
    """First-class record for context that was omitted, stale, unresolved, or missing."""

    schema_: Literal["craik.context_debt_record"] = Field(
        default="craik.context_debt_record",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    task_id: str
    project_id: str | None = None
    case_file_id: str | None = None
    handoff_id: str | None = None
    kind: ContextDebtKind
    status: ContextDebtStatus = "created"
    summary: str
    owner: str | None = None
    next_action: str | None = None
    omitted_doc_paths: list[str] = Field(default_factory=list)
    stale_instruction_ids: list[str] = Field(default_factory=list)
    assumption_ids: list[str] = Field(default_factory=list)
    missing_external_state: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    resolved_at: datetime | None = None

    @model_validator(mode="after")
    def validate_context_debt_status(self) -> ContextDebtRecord:
        """Require open debt to be actionable and resolved debt to be timestamped."""
        if self.status in {"created", "carried_forward"} and not self.next_action:
            raise ValueError("open context debt requires next_action")
        if self.status == "resolved" and self.resolved_at is None:
            raise ValueError("resolved context debt requires resolved_at")
        if self.status != "resolved" and self.resolved_at is not None:
            raise ValueError("unresolved context debt must not set resolved_at")
        return self


class ToolResultAttestation(CraikModel):
    """Observed tool or command result with freshness and trust boundaries."""

    schema_: Literal["craik.tool_result_attestation"] = Field(
        default="craik.tool_result_attestation",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    task_id: str
    project_id: str | None = None
    case_file_id: str | None = None
    tool_name: str
    tool_identity: str
    command: str | None = None
    observed_output_summary: str
    output_hash: str | None = None
    hash_algorithm: Literal["sha256"] = "sha256"
    trust_class: TrustClass
    status: ToolAttestationStatus = "attested"
    evidence_ids: list[str] = Field(default_factory=list)
    receipt_id: str | None = None
    captured_at: datetime
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def validate_attestation_window(self) -> ToolResultAttestation:
        """Keep attestation expiry and missing state explicit."""
        if self.expires_at is not None and self.expires_at <= self.captured_at:
            raise ValueError("tool result attestation expires_at must be after captured_at")
        if self.status == "missing" and (self.evidence_ids or self.receipt_id):
            raise ValueError("missing attestations must not include evidence or receipt links")
        if self.status == "attested" and not self.evidence_ids and self.receipt_id is None:
            raise ValueError("attested tool results require evidence_ids or receipt_id")
        if self.status == "blocked" and self.receipt_id is None:
            raise ValueError("blocked tool results require receipt_id")
        return self


class KnowledgeFreshnessProbe(CraikModel):
    """Freshness probe for knowledge that can become stale or expire."""

    schema_: Literal["craik.knowledge_freshness_probe"] = Field(
        default="craik.knowledge_freshness_probe",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    task_id: str
    project_id: str | None = None
    target: str
    kind: FreshnessProbeKind
    status: FreshnessProbeStatus
    trust_class: TrustClass
    observed_output_summary: str
    attestation_id: str | None = None
    captured_at: datetime | None = None
    expires_at: datetime | None = None
    stale_risk_warning: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_freshness_state(self) -> KnowledgeFreshnessProbe:
        """Require stale-risk warnings for non-fresh probe states."""
        if self.expires_at is not None and self.captured_at is not None:
            if self.expires_at <= self.captured_at:
                raise ValueError("freshness probe expires_at must be after captured_at")
        if self.status in {"expiring", "expired", "missing"} and not self.stale_risk_warning:
            raise ValueError("non-fresh freshness probes require stale_risk_warning")
        if self.status == "missing" and self.attestation_id is not None:
            raise ValueError("missing freshness probes must not link an attestation")
        return self


class KnownTrap(CraikModel):
    """Known pitfall agents should avoid when working in a project."""

    schema_: Literal["craik.known_trap"] = Field(default="craik.known_trap", alias="schema")
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    project_id: str | None = None
    task_id: str | None = None
    kind: KnownTrapKind
    status: KnownTrapStatus = "active"
    statement: str
    avoidance: str
    evidence_ids: list[str] = Field(default_factory=list)
    handoff_ids: list[str] = Field(default_factory=list)
    contradiction_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def validate_known_trap_status(self) -> KnownTrap:
        """Require evidence for active traps and contradiction links for contradicted traps."""
        if self.expires_at is not None and self.expires_at <= self.created_at:
            raise ValueError("known trap expires_at must be after created_at")
        if self.status == "active" and not self.evidence_ids:
            raise ValueError("active known traps require evidence_ids")
        if self.status == "contradicted" and not self.contradiction_ids:
            raise ValueError("contradicted known traps require contradiction_ids")
        return self


class NegativeKnowledge(CraikModel):
    """Evidence-backed statement about what is not true or not available."""

    schema_: Literal["craik.negative_knowledge"] = Field(
        default="craik.negative_knowledge",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    project_id: str | None = None
    task_id: str | None = None
    statement: str
    scope: str
    trust_class: TrustClass
    evidence_ids: list[str] = Field(default_factory=list)
    handoff_ids: list[str] = Field(default_factory=list)
    contradiction_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def validate_negative_knowledge(self) -> NegativeKnowledge:
        """Keep negative knowledge evidence-backed and freshness-bounded."""
        if not self.evidence_ids:
            raise ValueError("negative knowledge requires evidence_ids")
        if self.expires_at is not None and self.expires_at <= self.created_at:
            raise ValueError("negative knowledge expires_at must be after created_at")
        return self


class ScratchpadRecord(CraikModel):
    """Temporary working note that must expire before it becomes durable context."""

    schema_: Literal["craik.scratchpad_record"] = Field(
        default="craik.scratchpad_record",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    task_id: str
    project_id: str | None = None
    owner: str
    status: ScratchpadStatus = "active"
    note: str
    evidence_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def validate_scratchpad_expiry(self) -> ScratchpadRecord:
        """Require scratchpad entries to have a future expiry at creation time."""
        if self.expires_at <= self.created_at:
            raise ValueError("scratchpad expires_at must be after created_at")
        return self


class UnknownRecord(CraikModel):
    """First-class unknown that identifies what is needed to resolve it."""

    schema_: Literal["craik.unknown_record"] = Field(
        default="craik.unknown_record",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    task_id: str
    project_id: str | None = None
    owner: str | None = None
    status: UnknownStatus = "unresolved"
    question: str
    needed_resolution: UnknownResolutionSource
    next_action: str
    evidence_ids: list[str] = Field(default_factory=list)
    resolved_answer: str | None = None
    created_at: datetime
    resolved_at: datetime | None = None

    @model_validator(mode="after")
    def validate_unknown_status(self) -> UnknownRecord:
        """Require resolved unknowns to carry answer and timestamp."""
        if self.status == "resolved" and (not self.resolved_answer or self.resolved_at is None):
            raise ValueError("resolved unknowns require resolved_answer and resolved_at")
        if self.status == "unresolved" and self.resolved_at is not None:
            raise ValueError("unresolved unknowns must not set resolved_at")
        return self


class ContextRequest(CraikModel):
    """Structured request for context needed before work can continue safely."""

    schema_: Literal["craik.context_request"] = Field(
        default="craik.context_request",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    task_id: str
    project_id: str | None = None
    requester: str
    kind: ContextRequestKind
    status: ContextRequestStatus = "open"
    question: str
    needed_for: str
    handoff_id: str | None = None
    recovery_session_id: str | None = None
    unknown_id: str | None = None
    fulfilled_by: str | None = None
    fulfilled_at: datetime | None = None
    created_at: datetime

    @model_validator(mode="after")
    def validate_context_request_status(self) -> ContextRequest:
        """Require fulfillment details only for fulfilled requests."""
        if self.status == "fulfilled" and (not self.fulfilled_by or self.fulfilled_at is None):
            raise ValueError("fulfilled context requests require fulfilled_by and fulfilled_at")
        if self.status != "fulfilled" and (self.fulfilled_by or self.fulfilled_at is not None):
            raise ValueError("open context requests must not include fulfillment details")
        return self


class ExitDisciplineCheck(CraikModel):
    """Checks that an agent exit includes validation, handoff, risks, and next steps."""

    schema_: Literal["craik.exit_discipline_check"] = Field(
        default="craik.exit_discipline_check",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    task_id: str
    project_id: str | None = None
    handoff_id: str | None = None
    status: ExitDisciplineStatus
    validation_recorded: bool
    handoff_recorded: bool
    residual_risks_recorded: bool
    next_steps_recorded: bool
    blocking_reasons: list[str] = Field(default_factory=list)
    context_request_ids: list[str] = Field(default_factory=list)
    unknown_ids: list[str] = Field(default_factory=list)
    created_at: datetime

    @model_validator(mode="after")
    def validate_exit_status(self) -> ExitDisciplineCheck:
        """Require blocking reasons for blocked exits and complete checklist for complete exits."""
        complete = all(
            [
                self.validation_recorded,
                self.handoff_recorded,
                self.residual_risks_recorded,
                self.next_steps_recorded,
            ]
        )
        if self.status == "complete" and (not complete or self.blocking_reasons):
            raise ValueError("complete exit discipline checks require all checks and no blockers")
        if self.status == "blocked" and not self.blocking_reasons:
            raise ValueError("blocked exit discipline checks require blocking_reasons")
        return self


if not TYPE_CHECKING:
    __all__ = [name for name in globals() if not name.startswith("_")]
