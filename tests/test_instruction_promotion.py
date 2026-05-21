from datetime import UTC, datetime

import pytest

from craik.contracts.models import DistilledInstructionProposal
from craik.runtime.instruction_approval import (
    InstructionApprovalError,
    approve_instruction,
    list_governing,
    reject_instruction,
)
from craik.runtime.paths import ensure_craik_home
from craik.runtime.projects.instruction_sources import (
    InstructionPromotionError,
    review_instruction_promotion,
)
from craik.runtime.store import LocalStore


def _store(tmp_path) -> LocalStore:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    store = LocalStore.from_paths(paths)
    store.initialize()
    return store


def _proposal(snapshot_id: str | None = "snapshot_agents") -> DistilledInstructionProposal:
    return DistilledInstructionProposal(
        id="distilled_instruction_agents_rule",
        project_id="project_docs",
        source_id="instruction_source_agents_md",
        snapshot_id=snapshot_id,
        category="instruction",
        statement="Run tests before merge.",
        rationale="Extracted from AGENTS.md.",
        confidence=0.9,
        provenance_ids=["provenance_agents_rule"],
        evidence_ids=["evidence_agents_rule"],
        created_at="2026-05-15T22:30:00Z",
    )


def test_approved_promotion_creates_active_constraint_and_audit_links(tmp_path) -> None:
    store = _store(tmp_path)
    try:
        proposal = _proposal()
        store.put_distilled_instruction_proposal(proposal)

        review = review_instruction_promotion(
            store,
            proposal_id=proposal.id,
            decision="approved",
            decided_by="user:maintainer",
            rationale="Instruction is valid.",
            policy_envelope_id="policy_distill",
            receipt_ids=["receipt_review"],
            memory_proposal_ids=["proposal_memory"],
            handoff_ids=["handoff_distill"],
        )

        updated = store.get_distilled_instruction_proposal(proposal.id)
        constraint = store.get_promoted_instruction_constraint(review.promoted_constraint_id)
        assert review.decision == "approved"
        assert updated.promotion_status == "approved"
        assert updated.promoted_constraint_id == constraint.id
        assert constraint.active is True
        assert constraint.snapshot_id == proposal.snapshot_id
        assert constraint.provenance_ids == proposal.provenance_ids
        assert constraint.receipt_ids == ["receipt_review"]
        assert store.list_instruction_promotion_reviews() == [review]
        assert store.list_promoted_instruction_constraints() == [constraint]
    finally:
        store.close()


def test_approval_requires_operator_and_makes_instruction_governing(tmp_path) -> None:
    store = _store(tmp_path)
    try:
        proposal = _proposal()
        store.put_distilled_instruction_proposal(proposal)

        with pytest.raises(InstructionApprovalError, match="operator identity"):
            approve_instruction(
                store,
                proposal_id=proposal.id,
                operator_identity="",
                rationale="Missing operator.",
            )

        result = approve_instruction(
            store,
            proposal_id=proposal.id,
            operator_identity="user:maintainer",
            rationale="Instruction is valid.",
        )

        assert result.proposal.promotion_status == "governing"
        assert result.review.decision == "approved"
        assert result.review.decided_by == "user:maintainer"
        assert result.constraint is not None
        assert list_governing(store) == [result.constraint]
    finally:
        store.close()


def test_reapproval_of_governing_instruction_is_noop(tmp_path) -> None:
    store = _store(tmp_path)
    try:
        proposal = _proposal()
        store.put_distilled_instruction_proposal(proposal)
        first = approve_instruction(
            store,
            proposal_id=proposal.id,
            operator_identity="user:maintainer",
            rationale="Instruction is valid.",
        )
        second = approve_instruction(
            store,
            proposal_id=proposal.id,
            operator_identity="user:maintainer",
            rationale="Still valid.",
        )

        assert second.review == first.review
        assert store.list_instruction_promotion_reviews() == [first.review]
        assert store.list_promoted_instruction_constraints() == [first.constraint]
    finally:
        store.close()


def test_stale_or_contradicted_approval_requires_override(tmp_path) -> None:
    store = _store(tmp_path)
    try:
        stale = _proposal().model_copy(
            update={
                "promotion_status": "deferred",
                "decided_by": "agent:instruction-distillation",
                "decided_at": datetime(2026, 5, 15, 22, 31, tzinfo=UTC),
            }
        )
        stale = DistilledInstructionProposal.model_validate(
            stale.model_dump(mode="json", by_alias=True)
        )
        store.put_distilled_instruction_proposal(stale)

        with pytest.raises(InstructionApprovalError, match="--override"):
            approve_instruction(
                store,
                proposal_id=stale.id,
                operator_identity="user:maintainer",
                rationale="Approve despite stale state.",
            )

        result = approve_instruction(
            store,
            proposal_id=stale.id,
            operator_identity="user:maintainer",
            rationale="Approve despite stale state.",
            override=True,
            override_rationale="Source change reviewed manually.",
        )

        assert result.proposal.promotion_status == "governing"
        assert result.review.override_stale is True
        assert result.review.override_rationale == "Source change reviewed manually."
    finally:
        store.close()


def test_review_promotion_override_on_stale_records_bypass(tmp_path) -> None:
    store = _store(tmp_path)
    try:
        stale = _proposal().model_copy(
            update={
                "promotion_status": "deferred",
                "decided_by": "agent:instruction-distillation",
                "decided_at": datetime(2026, 5, 15, 22, 31, tzinfo=UTC),
            }
        )
        stale = DistilledInstructionProposal.model_validate(
            stale.model_dump(mode="json", by_alias=True)
        )
        store.put_distilled_instruction_proposal(stale)

        with pytest.raises(InstructionPromotionError, match="override"):
            review_instruction_promotion(
                store,
                proposal_id=stale.id,
                decision="approved",
                decided_by="user:maintainer",
                rationale="Reviewed stale instruction.",
            )

        review = review_instruction_promotion(
            store,
            proposal_id=stale.id,
            decision="approved",
            decided_by="user:maintainer",
            rationale="Reviewed stale instruction.",
            override=True,
            override_reason="Source drift reviewed manually.",
        )

        assert review.override_stale is True
        assert review.override_contradiction is False
        assert review.override_rationale == "Source drift reviewed manually."
    finally:
        store.close()


def test_review_promotion_override_on_contradiction_records_bypass(tmp_path) -> None:
    store = _store(tmp_path)
    try:
        proposal = _proposal().model_copy(
            update={"contradiction_ids": ["contradiction_docs"]}
        )
        proposal = DistilledInstructionProposal.model_validate(
            proposal.model_dump(mode="json", by_alias=True)
        )
        store.put_distilled_instruction_proposal(proposal)

        review = review_instruction_promotion(
            store,
            proposal_id=proposal.id,
            decision="approved",
            decided_by="user:maintainer",
            rationale="Reviewed contradiction.",
            override=True,
            override_reason="Contradiction resolved offline.",
        )

        assert review.override_stale is False
        assert review.override_contradiction is True
        assert review.override_rationale == "Contradiction resolved offline."
    finally:
        store.close()


def test_review_promotion_override_without_need_is_informational(tmp_path) -> None:
    store = _store(tmp_path)
    try:
        proposal = _proposal()
        store.put_distilled_instruction_proposal(proposal)

        review = review_instruction_promotion(
            store,
            proposal_id=proposal.id,
            decision="approved",
            decided_by="user:maintainer",
            rationale="Operator requested explicit override audit.",
            override=True,
            override_reason="Operator checked source state before approval.",
        )

        assert review.override_stale is False
        assert review.override_contradiction is False
        assert review.override_rationale == "Operator checked source state before approval."
    finally:
        store.close()


def test_contradicted_approval_records_override(tmp_path) -> None:
    store = _store(tmp_path)
    try:
        proposal = _proposal()
        proposal = proposal.model_copy(update={"contradiction_ids": ["contradiction_docs"]})
        proposal = DistilledInstructionProposal.model_validate(
            proposal.model_dump(mode="json", by_alias=True)
        )
        store.put_distilled_instruction_proposal(proposal)

        result = approve_instruction(
            store,
            proposal_id=proposal.id,
            operator_identity="user:maintainer",
            rationale="Reviewed contradiction.",
            override=True,
            override_rationale="Contradiction resolved offline.",
        )

        assert result.review.override_contradiction is True
    finally:
        store.close()


def test_reject_instruction_persists_denial_receipt(tmp_path) -> None:
    store = _store(tmp_path)
    try:
        proposal = _proposal()
        store.put_distilled_instruction_proposal(proposal)

        result = reject_instruction(
            store,
            proposal_id=proposal.id,
            operator_identity="user:maintainer",
            rationale="Not valid for this project.",
        )

        assert result.proposal.promotion_status == "rejected"
        assert result.review.decision == "rejected"
        assert result.review.promoted_constraint_id is None
        assert list_governing(store) == []
    finally:
        store.close()


def test_new_approval_supersedes_previous_governing_instruction(tmp_path) -> None:
    store = _store(tmp_path)
    try:
        first = _proposal()
        second = _proposal().model_copy(
            update={
                "id": "distilled_instruction_agents_rule_v2",
                "statement": "Run tests and docs before merge.",
            }
        )
        second = DistilledInstructionProposal.model_validate(
            second.model_dump(mode="json", by_alias=True)
        )
        store.put_distilled_instruction_proposal(first)
        store.put_distilled_instruction_proposal(second)

        first_result = approve_instruction(
            store,
            proposal_id=first.id,
            operator_identity="user:maintainer",
            rationale="Initial rule.",
        )
        second_result = approve_instruction(
            store,
            proposal_id=second.id,
            operator_identity="user:maintainer",
            rationale="Updated rule.",
        )

        updated_first = store.get_distilled_instruction_proposal(first.id)
        assert updated_first.promotion_status == "superseded"
        assert store.get_promoted_instruction_constraint(first_result.constraint.id).active is False
        assert list_governing(store) == [second_result.constraint]
    finally:
        store.close()


@pytest.mark.parametrize("decision", ["rejected", "deferred"])
def test_unapproved_promotion_decisions_are_persisted_without_constraints(
    tmp_path,
    decision: str,
) -> None:
    store = _store(tmp_path)
    try:
        proposal = _proposal()
        store.put_distilled_instruction_proposal(proposal)

        review = review_instruction_promotion(
            store,
            proposal_id=proposal.id,
            decision=decision,
            decided_by="user:maintainer",
            rationale=f"Promotion {decision}.",
            receipt_ids=["receipt_review"],
        )

        updated = store.get_distilled_instruction_proposal(proposal.id)
        assert review.decision == decision
        assert review.promoted_constraint_id is None
        assert updated.promotion_status == decision
        assert updated.promoted_constraint_id is None
        assert store.list_promoted_instruction_constraints() == []
    finally:
        store.close()


def test_approved_promotion_requires_source_snapshot(tmp_path) -> None:
    store = _store(tmp_path)
    try:
        proposal = _proposal(snapshot_id=None)
        store.put_distilled_instruction_proposal(proposal)

        with pytest.raises(InstructionPromotionError, match="source snapshot"):
            review_instruction_promotion(
                store,
                proposal_id=proposal.id,
                decision="approved",
                decided_by="user:maintainer",
                rationale="Cannot approve without snapshot.",
            )
    finally:
        store.close()


def test_unknown_promotion_proposal_raises(tmp_path) -> None:
    store = _store(tmp_path)
    try:
        with pytest.raises(InstructionPromotionError, match="unknown"):
            review_instruction_promotion(
                store,
                proposal_id="missing",
                decision="approved",
                decided_by="user:maintainer",
                rationale="Missing.",
            )
    finally:
        store.close()
