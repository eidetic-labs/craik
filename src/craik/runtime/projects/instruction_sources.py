"""Instruction source provenance rendering helpers."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import cast

from craik.contracts.models import (
    ContradictionReport,
    DistilledInstructionProposal,
    InstructionPromotionDecision,
    InstructionPromotionReview,
    InstructionProvenance,
    InstructionSourceSnapshot,
    PromotedInstructionConstraint,
)
from craik.runtime.memory.contradictions import ContradictionManager
from craik.runtime.store import LocalStore


def render_instruction_snapshot_json(snapshot: InstructionSourceSnapshot) -> str:
    """Render a deterministic JSON representation of an instruction snapshot."""
    return snapshot.model_dump_json(by_alias=True, exclude_none=True, indent=2) + "\n"


def render_instruction_provenance_markdown(provenance: InstructionProvenance) -> str:
    """Render deterministic Markdown for instruction source provenance."""
    if provenance.start_line is None:
        location = provenance.path
    else:
        location = f"{provenance.path}:{provenance.start_line}-{provenance.end_line}"
    lines = [
        f"# Instruction Provenance: {provenance.id}",
        "",
        f"- Source: {provenance.source_id}",
        f"- Snapshot: {provenance.snapshot_id or 'none'}",
        f"- Location: {location}",
        f"- Summary: {provenance.summary}",
    ]
    if provenance.excerpt_hash:
        lines.append(f"- Excerpt Hash: {provenance.excerpt_hash}")
    return "\n".join(lines) + "\n"


def render_distilled_instruction_markdown(proposal: DistilledInstructionProposal) -> str:
    """Render deterministic Markdown for a distilled instruction proposal."""
    lines = [
        f"# Distilled Instruction: {proposal.id}",
        "",
        f"- Category: {proposal.category}",
        f"- Promotion Status: {proposal.promotion_status}",
        f"- Source: {proposal.source_id}",
        f"- Confidence: {proposal.confidence:.2f}",
        f"- Statement: {proposal.statement}",
        f"- Rationale: {proposal.rationale}",
        "- Provenance:",
        *_bullet_lines(proposal.provenance_ids),
        "- Evidence:",
        *_bullet_lines(proposal.evidence_ids),
    ]
    if proposal.contradiction_ids:
        lines.extend(["- Contradictions:", *_bullet_lines(proposal.contradiction_ids)])
    return "\n".join(lines) + "\n"


def render_distilled_instruction_json(proposal: DistilledInstructionProposal) -> str:
    """Render deterministic JSON for a distilled instruction proposal."""
    return proposal.model_dump_json(by_alias=True, exclude_none=True, indent=2) + "\n"


def invalidate_stale_distillations(
    store: LocalStore,
    *,
    current_snapshots: list[InstructionSourceSnapshot],
    decided_by: str = "agent:instruction-distillation",
) -> list[DistilledInstructionProposal]:
    """Mark proposals stale when their source snapshot changed, disappeared, or is new."""
    previous_by_source = _previous_snapshots_for_invalidation(store, current_snapshots)
    stale_source_ids = _stale_source_ids(previous_by_source, current_snapshots)
    if not stale_source_ids:
        for snapshot in current_snapshots:
            store.put_instruction_source_snapshot(snapshot)
        return []

    invalidated: list[DistilledInstructionProposal] = []
    for proposal in store.list_distilled_instruction_proposals():
        if proposal.source_id not in stale_source_ids or proposal.promotion_status == "rejected":
            continue
        updated = proposal.model_copy(
            update={
                "promotion_status": "deferred",
                "decided_by": decided_by,
                "decided_at": max(snapshot.captured_at for snapshot in current_snapshots),
            }
        )
        updated = DistilledInstructionProposal.model_validate(
            updated.model_dump(mode="json", by_alias=True)
        )
        store.put_distilled_instruction_proposal(updated)
        invalidated.append(updated)

    for snapshot in current_snapshots:
        store.put_instruction_source_snapshot(snapshot)
    return sorted(invalidated, key=lambda proposal: proposal.id)


def instruction_stale_risk_warnings(store: LocalStore, project_id: str) -> list[str]:
    """Return stale-risk warnings for deferred instruction proposals in a project."""
    warnings = []
    for proposal in store.list_distilled_instruction_proposals():
        if proposal.project_id != project_id or proposal.promotion_status != "deferred":
            continue
        warnings.append(
            f"Instruction distillation {proposal.id} from {proposal.source_id} is stale; "
            "review provenance before promotion."
        )
    return sorted(set(warnings))


def promotable_distilled_instructions(
    proposals: list[DistilledInstructionProposal],
) -> list[DistilledInstructionProposal]:
    """Return proposals eligible for automatic promotion review."""
    return sorted(
        (
            proposal
            for proposal in proposals
            if proposal.promotion_status == "proposed" and not proposal.contradiction_ids
        ),
        key=lambda proposal: proposal.id,
    )


def active_instruction_context(store: LocalStore, project_id: str) -> list[dict[str, object]]:
    """Return active promoted instruction constraints for runtime context."""
    constraints = [
        constraint
        for constraint in store.list_promoted_instruction_constraints()
        if constraint.project_id == project_id and constraint.active
    ]
    proposal_by_id = {
        proposal.id: proposal for proposal in store.list_distilled_instruction_proposals()
    }
    active: list[dict[str, object]] = []
    for constraint in sorted(constraints, key=lambda item: item.id):
        proposal = proposal_by_id.get(constraint.proposal_id)
        if proposal is not None and (
            proposal.promotion_status != "approved" or proposal.contradiction_ids
        ):
            continue
        active.append(
            {
                "id": constraint.id,
                "category": constraint.category,
                "statement": constraint.statement,
                "source_id": constraint.source_id,
                "snapshot_id": constraint.snapshot_id,
                "provenance_ids": list(constraint.provenance_ids),
            }
        )
    return active


def detect_instruction_contradictions(
    store: LocalStore,
    *,
    task_id: str | None = None,
    owner: str | None = None,
) -> list[ContradictionReport]:
    """Open contradiction reports for incompatible distilled instruction proposals."""
    proposals = sorted(
        (
            proposal
            for proposal in store.list_distilled_instruction_proposals()
            if proposal.promotion_status not in {"deferred", "rejected"}
        ),
        key=lambda proposal: proposal.id,
    )
    reports: list[ContradictionReport] = []
    for index, left in enumerate(proposals):
        for right in proposals[index + 1 :]:
            conflict = _instruction_conflict(left, right)
            if conflict is None:
                continue
            report = ContradictionManager(store).open_report(
                task_id=task_id or left.task_id or right.task_id,
                facts=[
                    f"{conflict.subject}: {conflict.left_value}",
                    f"{conflict.subject}: {conflict.right_value}",
                ],
                summary=f"Instruction source conflict: {left.category}",
                affected_artifacts=[
                    left.id,
                    right.id,
                    left.source_id,
                    right.source_id,
                ],
                evidence_ids=sorted({*left.provenance_ids, *right.provenance_ids}),
                owner=owner,
                proposed_resolution=(
                    "Human review must decide which instruction source applies: "
                    f"{conflict.subject}."
                ),
            )
            _defer_conflicting_proposal(store, left, report.id)
            _defer_conflicting_proposal(store, right, report.id)
            reports.append(report)
    return sorted(reports, key=lambda report: report.id)


def review_instruction_promotion(
    store: LocalStore,
    *,
    proposal_id: str,
    decision: str,
    decided_by: str,
    rationale: str,
    policy_envelope_id: str | None = None,
    receipt_ids: list[str] | None = None,
    memory_proposal_ids: list[str] | None = None,
    handoff_ids: list[str] | None = None,
) -> InstructionPromotionReview:
    """Persist a promotion review and update the proposal/constraint state."""
    proposal = store.get_distilled_instruction_proposal(proposal_id)
    if proposal is None:
        raise InstructionPromotionError(f"unknown distilled instruction proposal: {proposal_id}")
    now = proposal.created_at
    normalized_decision = cast(InstructionPromotionDecision, decision)
    constraint_id = f"constraint_{proposal.id}" if normalized_decision == "approved" else None
    if normalized_decision == "approved":
        if proposal.snapshot_id is None:
            raise InstructionPromotionError("approved promotions require source snapshot")
        active_constraint_id = f"constraint_{proposal.id}"
        constraint = PromotedInstructionConstraint(
            id=active_constraint_id,
            project_id=proposal.project_id,
            proposal_id=proposal.id,
            source_id=proposal.source_id,
            snapshot_id=proposal.snapshot_id,
            category=proposal.category,
            statement=proposal.statement,
            provenance_ids=proposal.provenance_ids,
            evidence_ids=proposal.evidence_ids,
            policy_envelope_id=policy_envelope_id,
            receipt_ids=receipt_ids or [],
            memory_proposal_ids=memory_proposal_ids or [],
            handoff_ids=handoff_ids or [],
            created_at=now,
        )
        store.put_promoted_instruction_constraint(constraint)
    review = InstructionPromotionReview(
        id=f"promotion_review_{proposal.id}",
        project_id=proposal.project_id,
        proposal_id=proposal.id,
        decision=normalized_decision,
        decided_by=decided_by,
        rationale=rationale,
        promoted_constraint_id=constraint_id,
        policy_envelope_id=policy_envelope_id,
        receipt_ids=receipt_ids or [],
        memory_proposal_ids=memory_proposal_ids or [],
        handoff_ids=handoff_ids or [],
        created_at=now,
    )
    store.put_instruction_promotion_review(review)
    updated = proposal.model_copy(
        update={
            "promotion_status": decision,
            "promoted_constraint_id": constraint_id,
            "decided_by": decided_by,
            "decided_at": now,
        }
    )
    store.put_distilled_instruction_proposal(
        DistilledInstructionProposal.model_validate(
            updated.model_dump(mode="json", by_alias=True)
        )
    )
    return review


def _bullet_lines(values: list[str]) -> list[str]:
    if not values:
        return ["  - None"]
    return [f"  - {value}" for value in values]


@dataclass(frozen=True)
class _InstructionConflict:
    subject: str
    left_value: str
    right_value: str


def _proposals_conflict(
    left: DistilledInstructionProposal,
    right: DistilledInstructionProposal,
) -> bool:
    return _instruction_conflict(left, right) is not None


def _instruction_conflict(
    left: DistilledInstructionProposal,
    right: DistilledInstructionProposal,
) -> _InstructionConflict | None:
    if left.source_id == right.source_id or left.category != right.category:
        return None
    if left.category not in {"instruction", "policy", "command", "boundary", "security_rule"}:
        return None
    left_fact = _instruction_fact(left)
    right_fact = _instruction_fact(right)
    if left_fact is None or right_fact is None:
        return None
    left_subject, left_value = left_fact
    right_subject, right_value = right_fact
    if left_subject != right_subject or left_value == right_value:
        return None
    return _InstructionConflict(
        subject=left_subject,
        left_value=left_value,
        right_value=right_value,
    )


def _instruction_fact(proposal: DistilledInstructionProposal) -> tuple[str, str] | None:
    statement = _normalize_statement(proposal.statement)
    if proposal.category == "policy":
        policy_fact = _policy_fact(statement)
        if policy_fact is not None:
            return policy_fact
    if proposal.category == "command":
        command_fact = _command_fact(statement)
        if command_fact is not None:
            return command_fact
    subject = _normalized_subject(statement)
    if not subject:
        return None
    return (f"{proposal.category}:{subject}", _polarity(statement))


def _policy_fact(statement: str) -> tuple[str, str] | None:
    if "tool-allowlist" in statement:
        _, _, remainder = statement.partition("tool-allowlist")
        parts = [part for part in re.split(r"[:=\s]+", remainder.strip()) if part]
        if len(parts) >= 2:
            return (f"policy:tool-allowlist:{parts[0]}", " ".join(parts[1:]))
    allow_match = re.search(r"\ballow(?:list)? tool (?P<tool>[a-z0-9_.-]+)\b", statement)
    if allow_match:
        return (f"policy:tool-allowlist:{allow_match.group('tool')}", "allowed")
    deny_match = re.search(r"\b(?:deny|block) tool (?P<tool>[a-z0-9_.-]+)\b", statement)
    if deny_match:
        return (f"policy:tool-allowlist:{deny_match.group('tool')}", "denied")
    return None


def _command_fact(statement: str) -> tuple[str, str] | None:
    command_match = re.search(
        r"\b(?:run|execute|call|invoke)\s+(?P<command>[a-z0-9_.:/-]+)",
        statement,
    )
    if command_match is None:
        return None
    value = "denied" if _polarity(statement) == "deny" else "allowed"
    return (f"command:{command_match.group('command')}", value)


def _polarity(statement: str) -> str:
    if any(term in statement for term in ("must not", "do not", "never", "deny", "block")):
        return "deny"
    return "allow"


def _normalized_subject(statement: str) -> str:
    value = statement
    for phrase in (
        "must not",
        "should not",
        "do not",
        "never",
        "must",
        "should",
        "may",
        "always",
        "ensure",
    ):
        value = re.sub(rf"\b{phrase}\b", " ", value)
    return " ".join(value.strip(". ").split())


def _defer_conflicting_proposal(
    store: LocalStore,
    proposal: DistilledInstructionProposal,
    contradiction_id: str,
) -> None:
    updated = proposal.model_copy(
        update={
            "promotion_status": "deferred",
            "decided_by": "agent:instruction-distillation",
            "decided_at": proposal.created_at,
            "contradiction_ids": sorted({*proposal.contradiction_ids, contradiction_id}),
        }
    )
    store.put_distilled_instruction_proposal(
        DistilledInstructionProposal.model_validate(
            updated.model_dump(mode="json", by_alias=True)
        )
    )


def _normalized_positive(statement: str) -> str:
    value = _normalize_statement(statement)
    for prefix in ("must ", "should ", "may "):
        if value.startswith(prefix):
            return value.removeprefix(prefix)
    return value


def _normalized_negative(statement: str) -> str:
    value = _normalize_statement(statement)
    for prefix in ("must not ", "should not ", "may not "):
        if value.startswith(prefix):
            return value.removeprefix(prefix)
    return ""


def _normalize_statement(statement: str) -> str:
    return " ".join(statement.lower().rstrip(".").split())


class InstructionPromotionError(RuntimeError):
    """Raised when a distilled instruction cannot be reviewed for promotion."""


def _previous_snapshots_for_invalidation(
    store: LocalStore,
    current_snapshots: list[InstructionSourceSnapshot],
) -> dict[str, InstructionSourceSnapshot]:
    current_ids = {snapshot.id for snapshot in current_snapshots}
    all_snapshots = store.list_instruction_source_snapshots()
    previous_by_source = _latest_snapshots_by_source(
        snapshot for snapshot in all_snapshots if snapshot.id not in current_ids
    )
    current_by_source = {snapshot.source_id: snapshot for snapshot in current_snapshots}
    for source_id, snapshot in current_by_source.items():
        previous_by_source.setdefault(source_id, snapshot)
    return previous_by_source


def _latest_snapshots_by_source(
    snapshots: Iterable[InstructionSourceSnapshot],
) -> dict[str, InstructionSourceSnapshot]:
    latest: dict[str, InstructionSourceSnapshot] = {}
    for snapshot in snapshots:
        existing = latest.get(snapshot.source_id)
        if existing is None or (snapshot.captured_at, snapshot.id) > (
            existing.captured_at,
            existing.id,
        ):
            latest[snapshot.source_id] = snapshot
    return latest


def _stale_source_ids(
    previous_by_source: dict[str, InstructionSourceSnapshot],
    current_snapshots: list[InstructionSourceSnapshot],
) -> set[str]:
    stale = set()
    current_by_source = {snapshot.source_id: snapshot for snapshot in current_snapshots}
    for source_id, current in current_by_source.items():
        previous = previous_by_source.get(source_id)
        if previous is None:
            stale.add(source_id)
            continue
        if current.hash_status in {"changed", "missing", "new"}:
            stale.add(source_id)
            continue
        if current.content_hash != previous.content_hash:
            stale.add(source_id)
    for source_id in set(previous_by_source) - set(current_by_source):
        stale.add(source_id)
    return stale
