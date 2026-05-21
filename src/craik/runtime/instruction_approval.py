"""Operator approval workflow for distilled instruction proposals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from craik.contracts.models import (
    DistilledInstructionProposal,
    InstructionPromotionReview,
    PromotedInstructionConstraint,
)
from craik.runtime.store import LocalStore


class InstructionApprovalError(RuntimeError):
    """Raised when instruction approval cannot proceed."""


@dataclass(frozen=True)
class InstructionApprovalResult:
    """Artifacts produced by one approval or rejection decision."""

    proposal: DistilledInstructionProposal
    review: InstructionPromotionReview
    constraint: PromotedInstructionConstraint | None = None


def approve_instruction(
    store: LocalStore,
    *,
    proposal_id: str,
    operator_identity: str,
    rationale: str,
    override: bool = False,
    override_rationale: str | None = None,
    now: datetime | None = None,
) -> InstructionApprovalResult:
    """Approve a distilled instruction and make it governing."""
    proposal = _proposal(store, proposal_id)
    _require_operator(operator_identity)
    existing = store.get_instruction_promotion_review(_review_id(proposal.id))
    if proposal.promotion_status == "governing" and existing is not None:
        constraint = store.get_promoted_instruction_constraint(
            existing.promoted_constraint_id or ""
        )
        return InstructionApprovalResult(proposal=proposal, review=existing, constraint=constraint)
    _require_approvable(proposal, override=override, override_rationale=override_rationale)
    if proposal.snapshot_id is None:
        raise InstructionApprovalError("approval requires source snapshot provenance")

    decided_at = now or datetime.now(UTC)
    _supersede_existing_governing(store, proposal, operator_identity, decided_at)
    constraint = PromotedInstructionConstraint(
        id=_constraint_id(proposal.id),
        project_id=proposal.project_id,
        proposal_id=proposal.id,
        source_id=proposal.source_id,
        snapshot_id=proposal.snapshot_id,
        category=proposal.category,
        statement=proposal.statement,
        provenance_ids=proposal.provenance_ids,
        evidence_ids=proposal.evidence_ids,
        active=True,
        created_at=decided_at,
    )
    review = InstructionPromotionReview(
        id=_review_id(proposal.id),
        project_id=proposal.project_id,
        proposal_id=proposal.id,
        decision="approved",
        decided_by=operator_identity,
        rationale=rationale,
        promoted_constraint_id=constraint.id,
        override_stale=proposal.promotion_status == "deferred" and override,
        override_contradiction=bool(proposal.contradiction_ids) and override,
        override_rationale=override_rationale if override else None,
        created_at=decided_at,
    )
    updated = _proposal_update(
        proposal,
        promotion_status="governing",
        promoted_constraint_id=constraint.id,
        decided_by=operator_identity,
        decided_at=decided_at,
    )
    store.put_promoted_instruction_constraint(constraint)
    store.put_instruction_promotion_review(review)
    store.put_distilled_instruction_proposal(updated)
    return InstructionApprovalResult(proposal=updated, review=review, constraint=constraint)


def reject_instruction(
    store: LocalStore,
    *,
    proposal_id: str,
    operator_identity: str,
    rationale: str,
    now: datetime | None = None,
) -> InstructionApprovalResult:
    """Reject a distilled instruction with an auditable denial receipt."""
    proposal = _proposal(store, proposal_id)
    _require_operator(operator_identity)
    decided_at = now or datetime.now(UTC)
    review = InstructionPromotionReview(
        id=_review_id(proposal.id),
        project_id=proposal.project_id,
        proposal_id=proposal.id,
        decision="rejected",
        decided_by=operator_identity,
        rationale=rationale,
        created_at=decided_at,
    )
    updated = _proposal_update(
        proposal,
        promotion_status="rejected",
        promoted_constraint_id=None,
        decided_by=operator_identity,
        decided_at=decided_at,
    )
    store.put_instruction_promotion_review(review)
    store.put_distilled_instruction_proposal(updated)
    return InstructionApprovalResult(proposal=updated, review=review)


def list_governing(
    store: LocalStore,
    *,
    project_id: str | None = None,
) -> list[PromotedInstructionConstraint]:
    """Return active constraints from governing distilled instructions only."""
    proposals = {
        proposal.id: proposal for proposal in store.list_distilled_instruction_proposals()
    }
    constraints = [
        constraint
        for constraint in store.list_promoted_instruction_constraints()
        if constraint.active and (project_id is None or constraint.project_id == project_id)
    ]
    governing = []
    for constraint in constraints:
        proposal = proposals.get(constraint.proposal_id)
        if proposal is None:
            continue
        if proposal.promotion_status == "governing" and not proposal.contradiction_ids:
            governing.append(constraint)
    return sorted(governing, key=lambda constraint: constraint.id)


def _proposal(store: LocalStore, proposal_id: str) -> DistilledInstructionProposal:
    proposal = store.get_distilled_instruction_proposal(proposal_id)
    if proposal is None:
        raise InstructionApprovalError(f"unknown distilled instruction proposal: {proposal_id}")
    return proposal


def _require_operator(operator_identity: str) -> None:
    if not operator_identity.strip():
        raise InstructionApprovalError(
            "instruction approval requires an explicit operator identity"
        )


def _require_approvable(
    proposal: DistilledInstructionProposal,
    *,
    override: bool,
    override_rationale: str | None,
) -> None:
    stale = proposal.promotion_status == "deferred"
    contradicted = bool(proposal.contradiction_ids)
    if not stale and not contradicted:
        return
    if not override:
        raise InstructionApprovalError(
            "stale or contradicted instructions require --override and rationale"
        )
    if not (override_rationale or "").strip():
        raise InstructionApprovalError("override approval requires override rationale")


def _supersede_existing_governing(
    store: LocalStore,
    proposal: DistilledInstructionProposal,
    decided_by: str,
    decided_at: datetime,
) -> None:
    for existing in store.list_distilled_instruction_proposals():
        if existing.id == proposal.id or existing.promotion_status != "governing":
            continue
        if (
            existing.project_id,
            existing.source_id,
            existing.category,
        ) != (proposal.project_id, proposal.source_id, proposal.category):
            continue
        store.put_distilled_instruction_proposal(
            _proposal_update(
                existing,
                promotion_status="superseded",
                promoted_constraint_id=existing.promoted_constraint_id,
                decided_by=decided_by,
                decided_at=decided_at,
            )
        )
        if existing.promoted_constraint_id:
            constraint = store.get_promoted_instruction_constraint(
                existing.promoted_constraint_id
            )
            if constraint is not None:
                store.put_promoted_instruction_constraint(
                    constraint.model_copy(update={"active": False})
                )


def _proposal_update(
    proposal: DistilledInstructionProposal,
    *,
    promotion_status: str,
    promoted_constraint_id: str | None,
    decided_by: str,
    decided_at: datetime,
) -> DistilledInstructionProposal:
    updated = proposal.model_copy(
        update={
            "promotion_status": promotion_status,
            "promoted_constraint_id": promoted_constraint_id,
            "decided_by": decided_by,
            "decided_at": decided_at,
        }
    )
    return DistilledInstructionProposal.model_validate(
        updated.model_dump(mode="json", by_alias=True)
    )


def _constraint_id(proposal_id: str) -> str:
    return f"constraint_{proposal_id}"


def _review_id(proposal_id: str) -> str:
    return f"promotion_review_{proposal_id}"
