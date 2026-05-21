"""Operator approval workflow for distilled instruction proposals."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from craik.contracts.models import (
    DistilledInstructionProposal,
    InstructionPromotionReview,
    PromotedInstructionConstraint,
)
from craik.runtime.auth.operator import (
    OperatorSessionNotFoundError,
    OperatorSessionStore,
)
from craik.runtime.store import LocalStore

_HMAC_SECRET_FILENAME = "instruction-approval-hmac.key"
_OWNER_ONLY_FILE_MODE = 0o600


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
    allow_unbound: bool = False,
    now: datetime | None = None,
) -> InstructionApprovalResult:
    """Approve a distilled instruction and make it governing."""
    proposal = _proposal(store, proposal_id)
    _require_operator(operator_identity, allow_unbound=allow_unbound)
    hmac_key = _hmac_key_for_store(store)
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
    review = _attach_receipt_hmac(review, hmac_key)
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
    allow_unbound: bool = False,
    now: datetime | None = None,
) -> InstructionApprovalResult:
    """Reject a distilled instruction with an auditable denial receipt."""
    proposal = _proposal(store, proposal_id)
    _require_operator(operator_identity, allow_unbound=allow_unbound)
    hmac_key = _hmac_key_for_store(store)
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
    review = _attach_receipt_hmac(review, hmac_key)
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
    proposals = {proposal.id: proposal for proposal in store.list_distilled_instruction_proposals()}
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
        review = store.get_instruction_promotion_review(_review_id(proposal.id))
        if review is None or not verify_review_hmac(review, store):
            continue
        if proposal.promotion_status == "governing" and not proposal.contradiction_ids:
            governing.append(constraint)
    return sorted(governing, key=lambda constraint: constraint.id)


def _proposal(store: LocalStore, proposal_id: str) -> DistilledInstructionProposal:
    proposal = store.get_distilled_instruction_proposal(proposal_id)
    if proposal is None:
        raise InstructionApprovalError(f"unknown distilled instruction proposal: {proposal_id}")
    return proposal


def verify_review_hmac(
    review: InstructionPromotionReview,
    store: LocalStore,
) -> bool:
    """Return whether a promotion review has a valid integrity HMAC."""
    if not review.receipt_hmac:
        return False
    key = _hmac_key_for_store(store)
    expected = _review_hmac(review, key)
    return hmac.compare_digest(review.receipt_hmac, expected)


def _require_operator(operator_identity: str, *, allow_unbound: bool) -> None:
    if not operator_identity.strip():
        raise InstructionApprovalError(
            "instruction approval requires an explicit operator identity"
        )
    try:
        session = OperatorSessionStore.from_env().get()
    except OperatorSessionNotFoundError:
        if not allow_unbound:
            raise InstructionApprovalError(
                "instruction approval requires an active operator session"
            ) from None
        return
    if session.subject != operator_identity:
        raise InstructionApprovalError(
            "instruction approval operator identity does not match active session"
        )


def _hmac_key_for_store(store: LocalStore) -> bytes:
    secret = _approval_secret_path(store)
    secret.parent.mkdir(parents=True, exist_ok=True)
    if secret.exists():
        raw = secret.read_text(encoding="utf-8").strip()
    else:
        raw = secrets.token_hex(32)
        secret.write_text(f"{raw}\n", encoding="utf-8")
        if os.name == "posix":
            secret.chmod(_OWNER_ONLY_FILE_MODE)
    return hashlib.sha256(raw.encode("utf-8")).digest()


def _approval_secret_path(store: LocalStore) -> Path:
    home = store.database_path.parent.parent
    return home / "secrets" / _HMAC_SECRET_FILENAME


def _attach_receipt_hmac(
    review: InstructionPromotionReview,
    key: bytes,
) -> InstructionPromotionReview:
    return review.model_copy(update={"receipt_hmac": _review_hmac(review, key)})


def _review_hmac(review: InstructionPromotionReview, key: bytes) -> str:
    payload = review.model_dump(mode="json", by_alias=True)
    payload.pop("receipt_hmac", None)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(key, encoded, hashlib.sha256).hexdigest()


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
            constraint = store.get_promoted_instruction_constraint(existing.promoted_constraint_id)
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
