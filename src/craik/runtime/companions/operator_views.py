"""Read-only operator view formatters."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from craik.contracts.models import (
    DistilledInstructionProposal,
    EvidenceCoverageScore,
    HandoffQualityScore,
    HumanDelegationPoint,
    InstructionPromotionReview,
    InstructionProvenance,
    InstructionSource,
    InstructionSourceSnapshot,
    KnownTrap,
    NegativeKnowledge,
    RecoverySession,
    RedTeamFinding,
    RunDelta,
    RunDeltaItem,
    RuntimeCriticFinding,
)
from craik.runtime.companions import operator_artifact_views as _operator_artifact_views
from craik.runtime.companions import operator_knowledge_views as _operator_knowledge_views
from craik.runtime.companions import operator_surface as _operator_surface
from craik.runtime.memory import operator_memory_views as _operator_memory_views
from craik.runtime.policy.redaction import redact
from craik.runtime.policy.text import sanitize_runtime_text

format_contradiction_inbox = _operator_artifact_views.format_contradiction_inbox
format_evidence_assumption_view = _operator_artifact_views.format_evidence_assumption_view
format_handoff_viewer = _operator_artifact_views.format_handoff_viewer
format_receipt_viewer = _operator_artifact_views.format_receipt_viewer
format_work_graph_explorer = _operator_artifact_views.format_work_graph_explorer
KnowledgeResolutionSnapshot = _operator_knowledge_views.KnowledgeResolutionSnapshot
format_knowledge_resolution_view = _operator_knowledge_views.format_knowledge_resolution_view
MemoryImpactPreviewSnapshot = _operator_memory_views.MemoryImpactPreviewSnapshot
format_memory_impact_preview_view = _operator_memory_views.format_memory_impact_preview_view
OperatorSurfaceSection = _operator_surface.OperatorSurfaceSection
OperatorSurfaceSnapshot = _operator_surface.OperatorSurfaceSnapshot
build_operator_surface_snapshot = _operator_surface.build_operator_surface_snapshot
format_operator_surface_overview = _operator_surface.format_operator_surface_overview


@dataclass(frozen=True)
class BudgetQuotaSnapshot:
    """Operator-visible budget and quota state."""

    configured_limits: dict[str, float | int | str] = field(default_factory=dict)
    usage: dict[str, float | int | str] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    exceeded: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class QualityGateSnapshot:
    """Operator-visible quality gate review state."""

    handoff_scores: list[HandoffQualityScore] = field(default_factory=list)
    evidence_scores: list[EvidenceCoverageScore] = field(default_factory=list)
    critic_findings: list[RuntimeCriticFinding] = field(default_factory=list)
    red_team_findings: list[RedTeamFinding] = field(default_factory=list)


@dataclass(frozen=True)
class InstructionDistillationSnapshot:
    """Operator-visible instruction distillation review state."""

    sources: list[InstructionSource] = field(default_factory=list)
    snapshots: list[InstructionSourceSnapshot] = field(default_factory=list)
    provenance: list[InstructionProvenance] = field(default_factory=list)
    proposals: list[DistilledInstructionProposal] = field(default_factory=list)
    reviews: list[InstructionPromotionReview] = field(default_factory=list)


@dataclass(frozen=True)
class KnownTrapsSnapshot:
    """Operator-visible known traps and negative knowledge state."""

    known_traps: list[KnownTrap] = field(default_factory=list)
    negative_knowledge: list[NegativeKnowledge] = field(default_factory=list)
    now: datetime | None = None


@dataclass(frozen=True)
class RunDeltaSnapshot:
    """Operator-visible run delta and recovery-link state."""

    delta: RunDelta
    recovery_sessions: list[RecoverySession] = field(default_factory=list)


def format_quality_gate_view(snapshot: QualityGateSnapshot) -> list[str]:
    """Format quality gate state while keeping findings non-authoritative."""
    lines = [
        f"Quality Gate: {_quality_gate_state(snapshot)}",
        "",
        "Handoff Quality Scores",
    ]
    if not snapshot.handoff_scores:
        lines.append("- none")
    else:
        for score in sorted(snapshot.handoff_scores, key=lambda item: item.id):
            lines.extend(
                [
                    f"- {score.id} [{score.band}] score={score.score:.2f} "
                    f"handoff={score.handoff_id}",
                    f"  Blocking Reasons: {_join_or_none(score.blocking_reasons)}",
                    f"  Components: {_format_score_components(score)}",
                ]
            )

    lines.extend(["", "Evidence Coverage Scores"])
    if not snapshot.evidence_scores:
        lines.append("- none")
    else:
        for coverage_score in sorted(snapshot.evidence_scores, key=lambda item: item.id):
            lines.extend(
                [
                    f"- {coverage_score.id} [{coverage_score.band}] "
                    f"score={coverage_score.score:.2f} "
                    f"handoff={coverage_score.handoff_id or 'none'}",
                    f"  Evidence: {_join_or_none(coverage_score.evidence_ids)}",
                    "  Missing Evidence: "
                    f"{_join_or_none(coverage_score.missing_evidence_ids)}",
                    f"  Weak Claims: {_join_or_none(coverage_score.weak_claims)}",
                ]
            )

    lines.extend(["", "Critic Findings"])
    if not snapshot.critic_findings:
        lines.append("- none")
    else:
        for finding in sorted(
            snapshot.critic_findings,
            key=lambda item: (item.review_status, item.severity, item.id),
        ):
            lines.extend(
                [
                    f"- {finding.id} [{finding.review_status}/{finding.severity}] "
                    f"type={finding.finding_type}",
                    f"  Authoritative: {finding.authoritative}",
                    f"  Adjudication: {finding.adjudication_id or 'none'}",
                    f"  Affected Artifacts: {_join_or_none(finding.affected_artifacts)}",
                    f"  Evidence: {_join_or_none(finding.evidence_ids)}",
                    f"  Proposed Actions: {_join_or_none(finding.proposed_actions)}",
                    f"  Summary: {_safe(finding.summary)}",
                ]
            )

    lines.extend(["", "Red-Team Findings"])
    if not snapshot.red_team_findings:
        lines.append("- none")
    else:
        for red_team_finding in sorted(
            snapshot.red_team_findings,
            key=lambda item: (not item.blocking, item.review_status, item.severity, item.id),
        ):
            lines.extend(
                [
                    f"- {red_team_finding.id} "
                    f"[{red_team_finding.review_status}/{red_team_finding.severity}] "
                    f"type={red_team_finding.finding_type} "
                    f"blocking={red_team_finding.blocking}",
                    f"  Authoritative: {red_team_finding.authoritative}",
                    f"  Adjudication: {red_team_finding.adjudication_id or 'none'}",
                    "  Affected Artifacts: "
                    f"{_join_or_none(red_team_finding.affected_artifacts)}",
                    f"  Evidence: {_join_or_none(red_team_finding.evidence_ids)}",
                    "  Proposed Actions: "
                    f"{_join_or_none(red_team_finding.proposed_actions)}",
                    f"  Summary: {_safe(red_team_finding.summary)}",
                ]
            )

    return lines


def format_run_delta_view(snapshot: RunDeltaSnapshot) -> list[str]:
    """Format continuity-relevant run delta state."""
    delta = snapshot.delta
    lines = [
        f"Run Delta: {delta.id}",
        f"Project: {delta.project_id}",
        f"Task: {delta.task_id or 'all'}",
        f"Previous Handoff: {delta.previous_handoff_id or 'none'}",
        f"Current Handoff: {delta.current_handoff_id or 'none'}",
        f"Summary: {_safe(delta.summary)}",
        "",
        "Case Files",
        *_format_items(delta.case_file_ids),
        "",
        "Receipts",
        *_format_items(delta.receipt_ids),
        "",
        "Contradictions",
        *_format_items(delta.contradiction_ids),
        "",
        "Active Instruction Constraints",
        *_format_items(delta.active_instruction_constraint_ids),
        "",
        "Changes",
    ]
    if not delta.changes:
        lines.append("- none")
    else:
        for kind in ("created", "updated", "removed", "unchanged"):
            changes = sorted(
                (change for change in delta.changes if change.kind == kind),
                key=lambda item: (item.entity_type, item.entity_id),
            )
            lines.append(f"{kind.title()}: {len(changes)}")
            lines.extend(_format_run_delta_change(change) for change in changes)

    lines.extend(["", "Recovery Sessions"])
    if not snapshot.recovery_sessions:
        lines.append("- none")
    else:
        for session in sorted(snapshot.recovery_sessions, key=lambda item: item.id):
            lines.extend(
                [
                    f"- {session.id} [{session.status}] delta={session.run_delta_id}",
                    f"  Task: {session.task_id or 'all'}",
                    f"  Summary: {_safe(session.resume_summary)}",
                    f"  Required Actions: {_join_or_none(session.required_actions)}",
                    f"  Stale Risks: {_join_or_none(session.stale_risks)}",
                    f"  Handoffs: {_join_or_none(session.handoff_ids)}",
                    f"  Receipts: {_join_or_none(session.receipt_ids)}",
                    f"  Contradictions: {_join_or_none(session.contradiction_ids)}",
                    "  Active Instruction Constraints: "
                    f"{_join_or_none(session.active_instruction_constraint_ids)}",
                ]
            )
    return lines


def format_known_traps_view(snapshot: KnownTrapsSnapshot) -> list[str]:
    """Format known traps and negative knowledge without promoting guesses."""
    lines = ["Known Traps", ""]
    if not snapshot.known_traps:
        lines.append("- none")
    else:
        for trap in sorted(snapshot.known_traps, key=lambda item: (item.status, item.id)):
            lines.extend(
                [
                    f"- {trap.id} [{_known_trap_state(trap, snapshot.now)}/{trap.kind}]",
                    f"  Project: {trap.project_id or 'none'}",
                    f"  Task: {trap.task_id or 'none'}",
                    f"  Statement: {_safe(trap.statement)}",
                    f"  Avoidance: {_safe(trap.avoidance)}",
                    f"  Evidence: {_join_or_none(trap.evidence_ids)}",
                    f"  Handoffs: {_join_or_none(trap.handoff_ids)}",
                    f"  Contradictions: {_join_or_none(trap.contradiction_ids)}",
                    f"  Expires: {trap.expires_at.isoformat() if trap.expires_at else 'none'}",
                ]
            )

    lines.extend(["", "Negative Knowledge"])
    if not snapshot.negative_knowledge:
        lines.append("- none")
    else:
        for knowledge in sorted(
            snapshot.negative_knowledge,
            key=lambda item: (_negative_knowledge_state(item, snapshot.now), item.id),
        ):
            lines.extend(
                [
                    f"- {knowledge.id} [{_negative_knowledge_state(knowledge, snapshot.now)}] "
                    f"scope={knowledge.scope} trust={knowledge.trust_class}",
                    f"  Project: {knowledge.project_id or 'none'}",
                    f"  Task: {knowledge.task_id or 'none'}",
                    f"  Statement: {_safe(knowledge.statement)}",
                    f"  Evidence: {_join_or_none(knowledge.evidence_ids)}",
                    f"  Handoffs: {_join_or_none(knowledge.handoff_ids)}",
                    f"  Contradictions: {_join_or_none(knowledge.contradiction_ids)}",
                    "  Expires: "
                    f"{knowledge.expires_at.isoformat() if knowledge.expires_at else 'none'}",
                ]
            )

    return lines


def format_instruction_distillation_view(
    snapshot: InstructionDistillationSnapshot,
) -> list[str]:
    """Format instruction distillation state without promoting proposals."""
    lines = [
        "Instruction Distillation",
        "",
        "Sources",
    ]
    if not snapshot.sources:
        lines.append("- none")
    else:
        for source in sorted(snapshot.sources, key=lambda item: item.id):
            active = "active" if source.active else "inactive"
            lines.append(
                f"- {source.id} [{source.kind}/{active}] path={source.path} "
                f"owner={source.owner} trust={source.trust_boundary}"
            )

    lines.extend(["", "Snapshots"])
    if not snapshot.snapshots:
        lines.append("- none")
    else:
        for source_snapshot in sorted(snapshot.snapshots, key=lambda item: item.id):
            lines.append(
                f"- {source_snapshot.id} source={source_snapshot.source_id} "
                f"status={source_snapshot.hash_status} path={source_snapshot.path}"
            )

    lines.extend(["", "Provenance"])
    if not snapshot.provenance:
        lines.append("- none")
    else:
        for provenance in sorted(snapshot.provenance, key=lambda item: item.id):
            lines.append(
                f"- {provenance.id} source={provenance.source_id} "
                f"snapshot={provenance.snapshot_id or 'none'} "
                f"range={_format_line_range(provenance)}: {_safe(provenance.summary)}"
            )

    lines.extend(["", "Distilled Proposals"])
    if not snapshot.proposals:
        lines.append("- none")
    else:
        for proposal in sorted(
            snapshot.proposals,
            key=lambda item: (item.promotion_status, item.id),
        ):
            lines.extend(
                [
                    f"- {proposal.id} [{proposal.promotion_status}/{proposal.category}]",
                    f"  Source: {proposal.source_id}",
                    f"  Snapshot: {proposal.snapshot_id or 'none'}",
                    f"  Active Constraint: {proposal.promoted_constraint_id or 'none'}",
                    f"  Provenance: {_join_or_none(proposal.provenance_ids)}",
                    f"  Evidence: {_join_or_none(proposal.evidence_ids)}",
                    f"  Contradictions: {_join_or_none(proposal.contradiction_ids)}",
                    f"  Statement: {_safe(proposal.statement)}",
                ]
            )

    lines.extend(["", "Promotion Reviews"])
    if not snapshot.reviews:
        lines.append("- none")
    else:
        for review in sorted(snapshot.reviews, key=lambda item: (item.decision, item.id)):
            lines.extend(
                [
                    f"- {review.id} [{review.decision}] proposal={review.proposal_id}",
                    f"  Reviewer: {review.decided_by}",
                    f"  Active Constraint: {review.promoted_constraint_id or 'none'}",
                    f"  Policy: {review.policy_envelope_id or 'none'}",
                    f"  Receipts: {_join_or_none(review.receipt_ids)}",
                    f"  Handoffs: {_join_or_none(review.handoff_ids)}",
                    f"  Rationale: {_safe(review.rationale)}",
                ]
            )

    return lines


def format_budget_quota_view(snapshot: BudgetQuotaSnapshot) -> list[str]:
    """Format budget and quota state without inventing missing data."""
    return [
        "Budget And Quota",
        "",
        "Configured Limits",
        *_format_mapping(snapshot.configured_limits),
        "",
        "Usage",
        *_format_mapping(snapshot.usage),
        "",
        "Missing Data",
        *_format_items(snapshot.missing),
        "",
        "Exceeded",
        *_format_items(snapshot.exceeded),
        "",
        "Notes",
        *_format_items(snapshot.notes),
    ]


def format_delegation_queue(delegations: list[HumanDelegationPoint]) -> list[str]:
    """Format a read-only human delegation queue."""
    lines = [f"Delegation Queue: {len(delegations)}", ""]
    if not delegations:
        return [*lines, "- none"]
    for delegation in sorted(delegations, key=lambda item: (item.status, item.id)):
        lines.extend(
            [
                f"- {delegation.id} [{delegation.status}/{delegation.kind}]",
                f"  Task: {delegation.task_id}",
                f"  Owner: {delegation.owner or 'unassigned'}",
                f"  Requested By: {delegation.requested_by}",
                f"  Decision: {_safe(delegation.requested_decision)}",
                f"  Summary: {_safe(delegation.summary)}",
                f"  Policy: {delegation.policy_envelope_id or 'none'}",
                f"  Receipts: {_join_or_none(delegation.receipt_ids)}",
                "  Resolution: "
                f"{_safe(delegation.resolution) if delegation.resolution else 'none'}",
            ]
        )
    return lines


def _format_items(items: list[str]) -> list[str]:
    if not items:
        return ["- none"]
    return [f"- {_safe(item)}" for item in items]


def _format_mapping(items: Mapping[Any, float | int | str]) -> list[str]:
    if not items:
        return ["- none"]
    return [f"- {_safe(str(key))}: {_safe(str(items[key]))}" for key in sorted(items, key=str)]


def _format_run_delta_change(change: RunDeltaItem) -> str:
    previous = change.previous_ref
    current = change.current_ref
    return (
        f"- {change.entity_type}:{change.entity_id} "
        f"prev={previous or 'none'} current={current or 'none'} "
        f"evidence={_join_or_none(change.evidence_ids)}: {_safe(change.summary)}"
    )


def _known_trap_state(trap: KnownTrap, now: datetime | None) -> str:
    if trap.status == "active" and _is_expired(trap.expires_at, now):
        return "expired"
    return trap.status


def _negative_knowledge_state(knowledge: NegativeKnowledge, now: datetime | None) -> str:
    if knowledge.contradiction_ids:
        return "contradicted"
    if _is_expired(knowledge.expires_at, now):
        return "expired"
    return "active"


def _is_expired(expires_at: datetime | None, now: datetime | None) -> bool:
    return expires_at is not None and now is not None and expires_at <= now


def _format_line_range(provenance: InstructionProvenance) -> str:
    if provenance.start_line is None or provenance.end_line is None:
        return "source"
    if provenance.start_line == provenance.end_line:
        return f"L{provenance.start_line}"
    return f"L{provenance.start_line}-L{provenance.end_line}"


def _quality_gate_state(snapshot: QualityGateSnapshot) -> str:
    if any(score.band == "poor" for score in snapshot.handoff_scores):
        return "blocked"
    if any(score.band == "poor" for score in snapshot.evidence_scores):
        return "blocked"
    if any(
        finding.blocking and finding.review_status != "adjudicated"
        for finding in snapshot.red_team_findings
    ):
        return "blocked"
    if any(
        finding.review_status == "reviewable"
        and finding.severity in {"high", "critical"}
        for finding in snapshot.critic_findings
    ):
        return "reviewable"
    if any(score.band == "adequate" for score in snapshot.handoff_scores):
        return "reviewable"
    if any(score.band == "adequate" for score in snapshot.evidence_scores):
        return "reviewable"
    return "clear"


def _format_score_components(score: HandoffQualityScore) -> str:
    return ", ".join(
        f"{component.name}={component.score:.2f}" for component in score.components
    )


def _join_or_none(items: list[str]) -> str:
    if not items:
        return "none"
    return ", ".join(_safe(item) for item in items)


def _safe(value: str) -> str:
    return sanitize_runtime_text(str(redact(value).value))
