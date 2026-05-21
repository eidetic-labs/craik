"""Instruction provenance, promotion, delta, and recovery contracts."""

# ruff: noqa

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import *
from .core import *


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


class InstructionSource(CraikModel):
    """Declared source file for runtime instruction distillation."""

    schema_: Literal["craik.instruction_source"] = Field(
        default="craik.instruction_source",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    project_id: str
    kind: InstructionSourceKind
    path: str
    owner: str
    trust_boundary: InstructionTrustBoundary = "project"
    active: bool = True
    declared_by: str
    registered_by: str | None = None
    registered_at: datetime | None = None
    content_hash: str | None = None
    policy_envelope_id: str | None = None
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    @model_validator(mode="after")
    def validate_declared_path(self) -> InstructionSource:
        """Ensure standard source kinds use their canonical paths."""
        expected_path = INSTRUCTION_SOURCE_DEFAULT_PATHS[self.kind]
        if expected_path and self.path != expected_path:
            raise ValueError(f"{self.kind} instruction source path must be {expected_path!r}")
        if self.kind == "policy_doc" and not self.path:
            raise ValueError("policy_doc instruction sources require a declared path")
        if self.content_hash is not None and not _is_sha256(self.content_hash):
            raise ValueError("instruction source content_hash must be a sha256 hex digest")
        if self.registered_by is None:
            self.registered_by = self.declared_by
        if self.registered_at is None:
            self.registered_at = self.created_at
        return self


class InstructionSourceRegistration(CraikModel):
    """Receiptable registration event for one declared instruction source."""

    schema_: Literal["craik.instruction_source_registration"] = Field(
        default="craik.instruction_source_registration",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    project_id: str
    source_id: str
    kind: InstructionSourceKind
    path: str
    owner: str
    registered_by: str
    registered_at: datetime
    trust_boundary: InstructionTrustBoundary = "project"
    content_hash: str | None = None
    policy_envelope_id: str | None = None
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_registration_path(self) -> InstructionSourceRegistration:
        """Ensure source registrations use the same canonical-path rules as sources."""
        expected_path = INSTRUCTION_SOURCE_DEFAULT_PATHS[self.kind]
        if expected_path and self.path != expected_path:
            raise ValueError(f"{self.kind} instruction source path must be {expected_path!r}")
        if self.kind == "policy_doc" and not self.path:
            raise ValueError("policy_doc instruction sources require a declared path")
        if self.content_hash is not None and not _is_sha256(self.content_hash):
            raise ValueError("instruction source content_hash must be a sha256 hex digest")
        return self


class InstructionRegistryReceipt(CraikModel):
    """Audit record proving an instruction source registration was persisted."""

    schema_: Literal["craik.instruction_registry_receipt"] = Field(
        default="craik.instruction_registry_receipt",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    project_id: str
    source_id: str
    registration_id: str
    action: Literal["registered"] = "registered"
    registered_by: str
    capability: Literal["instructions.register"] = "instructions.register"
    target: str
    result_status: ReceiptStatus = "passed"
    summary: str
    created_at: datetime


class InstructionSourceRegistry(CraikModel):
    """Project registry of declared instruction sources."""

    schema_: Literal["craik.instruction_source_registry"] = Field(
        default="craik.instruction_source_registry",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    project_id: str
    sources: list[InstructionSource] = Field(default_factory=list)
    active_source_ids: list[str] = Field(default_factory=list)
    declared_policy_doc_paths: list[str] = Field(default_factory=list)
    created_at: datetime

    @model_validator(mode="after")
    def validate_registry_links(self) -> InstructionSourceRegistry:
        """Require active source ids to refer to active registered sources."""
        source_by_id = {source.id: source for source in self.sources}
        unknown = sorted(set(self.active_source_ids) - set(source_by_id))
        if unknown:
            raise ValueError(f"unknown active instruction source ids: {unknown}")
        inactive = sorted(
            source_id
            for source_id in self.active_source_ids
            if not source_by_id[source_id].active
        )
        if inactive:
            raise ValueError(f"inactive instruction source ids marked active: {inactive}")
        policy_paths = sorted(
            source.path for source in self.sources if source.kind == "policy_doc"
        )
        if sorted(self.declared_policy_doc_paths) != policy_paths:
            raise ValueError("declared policy doc paths must match policy_doc sources")
        return self


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdefABCDEF" for char in value)


class InstructionSourceSnapshot(CraikModel):
    """Hash identity for one observed instruction source state."""

    schema_: Literal["craik.instruction_source_snapshot"] = Field(
        default="craik.instruction_source_snapshot",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    project_id: str
    source_id: str
    path: str
    hash_algorithm: Literal["sha256"] = "sha256"
    content_hash: str | None = None
    hash_status: InstructionSourceHashStatus
    byte_count: int | None = Field(default=None, ge=0)
    line_count: int | None = Field(default=None, ge=0)
    captured_at: datetime

    @model_validator(mode="after")
    def validate_hash_state(self) -> InstructionSourceSnapshot:
        """Require hashes for present sources and omit hashes for missing sources."""
        if self.hash_status in {"missing", "oversize"} and self.content_hash is not None:
            raise ValueError("missing or oversize instruction sources must not include content_hash")
        if self.hash_status not in {"missing", "oversize"} and not self.content_hash:
            raise ValueError("present instruction sources require content_hash")
        return self


class InstructionProvenance(CraikModel):
    """Line/range provenance for distilled instruction material."""

    schema_: Literal["craik.instruction_provenance"] = Field(
        default="craik.instruction_provenance",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    project_id: str
    source_id: str
    snapshot_id: str | None = None
    path: str
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    start_column: int | None = Field(default=None, ge=1)
    end_column: int | None = Field(default=None, ge=1)
    summary: str
    excerpt_hash: str | None = None
    captured_at: datetime

    @model_validator(mode="after")
    def validate_range(self) -> InstructionProvenance:
        """Allow source-level provenance or complete line ranges."""
        has_any_line = self.start_line is not None or self.end_line is not None
        if has_any_line and (self.start_line is None or self.end_line is None):
            raise ValueError("instruction provenance line ranges require start_line and end_line")
        if self.start_line is not None and self.end_line is not None:
            if self.end_line < self.start_line:
                raise ValueError("instruction provenance end_line must be >= start_line")
        has_any_column = self.start_column is not None or self.end_column is not None
        if has_any_column and (self.start_column is None or self.end_column is None):
            raise ValueError(
                "instruction provenance column ranges require start_column and end_column"
            )
        return self


class DistilledInstructionProposal(CraikModel):
    """Reviewable instruction distilled from declared runtime instruction sources."""

    schema_: Literal["craik.distilled_instruction_proposal"] = Field(
        default="craik.distilled_instruction_proposal",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    project_id: str
    task_id: str | None = None
    source_id: str
    snapshot_id: str | None = None
    category: DistilledInstructionCategory
    statement: str
    rationale: str
    confidence: float = Field(ge=0.0, le=1.0)
    provenance_ids: list[str] = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    assumption_ids: list[str] = Field(default_factory=list)
    contradiction_ids: list[str] = Field(default_factory=list)
    promotion_status: DistilledInstructionPromotionStatus = "proposed"
    promoted_constraint_id: str | None = None
    decided_by: str | None = None
    decided_at: datetime | None = None
    created_at: datetime

    @model_validator(mode="after")
    def validate_promotion_review(self) -> DistilledInstructionProposal:
        """Keep distilled instructions reviewable until a decision is recorded."""
        if self.promotion_status in {"approved", "governing"} and not self.promoted_constraint_id:
            raise ValueError("governing distilled instructions require promoted_constraint_id")
        if self.promotion_status in {"approved", "governing", "rejected", "deferred", "superseded"}:
            if not self.decided_by or self.decided_at is None:
                raise ValueError(
                    "decided distilled instructions require reviewer and decision time"
                )
        if self.category in {"policy", "security_rule"} and not self.evidence_ids:
            raise ValueError("policy and security-rule distillations require evidence ids")
        return self


class PromotedInstructionConstraint(CraikModel):
    """Approved distilled instruction that can be used as an active runtime constraint."""

    schema_: Literal["craik.promoted_instruction_constraint"] = Field(
        default="craik.promoted_instruction_constraint",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    project_id: str
    proposal_id: str
    source_id: str
    snapshot_id: str
    category: DistilledInstructionCategory
    statement: str
    provenance_ids: list[str] = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    policy_envelope_id: str | None = None
    receipt_ids: list[str] = Field(default_factory=list)
    memory_proposal_ids: list[str] = Field(default_factory=list)
    handoff_ids: list[str] = Field(default_factory=list)
    active: bool = True
    created_at: datetime


class RunDeltaItem(CraikModel):
    """One observed continuity-relevant state change for recovery mode."""

    kind: RunDeltaChangeKind
    entity_type: RunDeltaEntityType
    entity_id: str
    summary: str
    previous_ref: str | None = None
    current_ref: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class RunDelta(CraikModel):
    """What changed since the previous usable handoff or resume point."""

    schema_: Literal["craik.run_delta"] = Field(default="craik.run_delta", alias="schema")
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    project_id: str
    task_id: str | None = None
    previous_handoff_id: str | None = None
    current_handoff_id: str | None = None
    case_file_ids: list[str] = Field(default_factory=list)
    receipt_ids: list[str] = Field(default_factory=list)
    contradiction_ids: list[str] = Field(default_factory=list)
    active_instruction_constraint_ids: list[str] = Field(default_factory=list)
    changes: list[RunDeltaItem] = Field(default_factory=list)
    summary: str
    created_at: datetime


class RecoverySession(CraikModel):
    """Resume-time continuity summary for an agent picking work back up."""

    schema_: Literal["craik.recovery_session"] = Field(
        default="craik.recovery_session",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    project_id: str
    task_id: str | None = None
    status: RecoveryStatus
    run_delta_id: str
    resume_summary: str
    required_actions: list[str] = Field(default_factory=list)
    stale_risks: list[str] = Field(default_factory=list)
    handoff_ids: list[str] = Field(default_factory=list)
    case_file_ids: list[str] = Field(default_factory=list)
    receipt_ids: list[str] = Field(default_factory=list)
    contradiction_ids: list[str] = Field(default_factory=list)
    active_instruction_constraint_ids: list[str] = Field(default_factory=list)
    decided_by: str | None = None
    receipt_hmac: str | None = None
    created_at: datetime

    @model_validator(mode="after")
    def validate_recovery_actions(self) -> RecoverySession:
        """Require explicit next actions when recovery is not clean."""
        if self.status != "clean_resume" and not self.required_actions:
            raise ValueError("non-clean recovery sessions require required_actions")
        return self


class InstructionPromotionReview(CraikModel):
    """Auditable human or policy decision for distilled instruction promotion."""

    schema_: Literal["craik.instruction_promotion_review"] = Field(
        default="craik.instruction_promotion_review",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    id: str
    project_id: str
    proposal_id: str
    decision: InstructionPromotionDecision
    decided_by: str
    rationale: str
    promoted_constraint_id: str | None = None
    policy_envelope_id: str | None = None
    receipt_ids: list[str] = Field(default_factory=list)
    memory_proposal_ids: list[str] = Field(default_factory=list)
    handoff_ids: list[str] = Field(default_factory=list)
    override_stale: bool = False
    override_contradiction: bool = False
    override_rationale: str | None = None
    receipt_hmac: str | None = None
    created_at: datetime

    @model_validator(mode="after")
    def validate_decision_links(self) -> InstructionPromotionReview:
        """Approved reviews must link the active promoted constraint."""
        if self.decision == "approved" and not self.promoted_constraint_id:
            raise ValueError("approved promotion reviews require promoted_constraint_id")
        if self.decision != "approved" and self.promoted_constraint_id is not None:
            raise ValueError("unapproved promotion reviews must not link active constraints")
        return self


if not TYPE_CHECKING:
    __all__ = [name for name in globals() if not name.startswith("_")]
