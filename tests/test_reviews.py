from pathlib import Path

import pytest
from pydantic import ValidationError

from craik.contracts.models import (
    AdjudicatedFinding,
    AdjudicationOutcome,
    Handoff,
    ReviewRequest,
    ReviewResult,
    SelfAudit,
)
from craik.runtime.paths import ensure_craik_home
from craik.runtime.policy.policy import generate_policy_envelope
from craik.runtime.reviewing.reviews import (
    CrossAgentReviewFinding,
    ReviewAdjudicationManager,
    ReviewRequestNotFoundError,
)
from craik.runtime.store import LocalStore


def _store(tmp_path: Path) -> LocalStore:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    store = LocalStore.from_paths(paths)
    store.initialize()
    return store


def _request() -> ReviewRequest:
    return ReviewRequest(
        id="review_request_verifier",
        task_id="task_review",
        requester_role_id="role_orchestrator",
        reviewer_role_id="role_policy",
        reviewer_role_kind="policy_reviewer",
        subject_worker_result_ids=["worker_result_impl"],
        focus=["policy compliance"],
        policy_envelope_id="policy_review",
        receipt_ids=["receipt_request"],
        created_at="2026-05-15T22:30:00Z",
    )


def _result(
    *,
    result_id: str,
    reviewer_role_kind: str,
    decision: str,
    summary: str,
) -> ReviewResult:
    return ReviewResult(
        id=result_id,
        task_id="task_review",
        review_request_id="review_request_verifier",
        reviewer_role_id=f"role_{reviewer_role_kind}",
        reviewer_role_kind=reviewer_role_kind,
        decision=decision,
        summary=summary,
        finding_ids=[f"finding_{result_id}"],
        worker_result_ids=["worker_result_impl"],
        debate_summary_ids=["debate_summary_impl"],
        evidence_ids=[f"evidence_{result_id}"],
        receipt_ids=[f"receipt_{result_id}"],
        created_at="2026-05-15T22:31:00Z",
    )


def _finding(decision: str, revised_summary: str | None = None) -> AdjudicatedFinding:
    return AdjudicatedFinding(
        source_worker_result_id="worker_result_impl",
        source_finding_id="finding_result",
        source_review_result_id="review_result_policy",
        decision=decision,
        rationale=f"{decision} by adjudicator.",
        revised_summary=revised_summary,
        evidence_ids=["evidence_result"],
    )


@pytest.mark.parametrize(
    ("decision", "finding"),
    [
        ("accepted", _finding("accepted")),
        ("rejected", _finding("rejected")),
        ("revised", _finding("revised", revised_summary="Use the revised finding.")),
    ],
)
def test_adjudication_outcomes_for_final_decisions(
    tmp_path: Path,
    decision: str,
    finding: AdjudicatedFinding,
) -> None:
    store = _store(tmp_path)
    try:
        manager = ReviewAdjudicationManager(store)
        request = manager.request_review(_request())
        policy_result = _result(
            result_id="review_result_policy",
            reviewer_role_kind="policy_reviewer",
            decision="approved",
            summary="Policy reviewer approved.",
        )
        adversarial_result = _result(
            result_id="review_result_adversarial",
            reviewer_role_kind="adversarial_reviewer",
            decision="changes_requested",
            summary="Adversarial reviewer requested changes.",
        )

        outcome = manager.adjudicate(
            task_id="task_review",
            outcome_id=f"adjudication_{decision}",
            adjudicator_role_id="role_adjudicator",
            decision=decision,
            summary=f"Adjudicator {decision} the finding.",
            review_results=[adversarial_result, policy_result],
            findings=[finding],
            debate_summary_ids=["debate_summary_impl"],
        )

        assert store.get_review_request(request.id).status == "completed"
        assert outcome.decision == decision
        assert outcome.adjudicated_findings == [finding]
        assert outcome.policy_review_result_ids == ["review_result_policy"]
        assert outcome.adversarial_review_result_ids == ["review_result_adversarial"]
        assert store.get_adjudication_outcome(outcome.id) == outcome
    finally:
        store.close()


def test_deferred_adjudication_preserves_unresolved_disagreement(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        result = _result(
            result_id="review_result_adversarial",
            reviewer_role_kind="adversarial_reviewer",
            decision="blocked",
            summary="Adversarial reviewer blocked the result.",
        )

        outcome = ReviewAdjudicationManager(store).adjudicate(
            task_id="task_review",
            outcome_id="adjudication_deferred",
            adjudicator_role_id="role_adjudicator",
            decision="deferred",
            summary="Needs human review.",
            review_results=[result],
            findings=[],
            unresolved_disagreements=["Implementation completeness remains disputed."],
        )

        assert outcome.decision == "deferred"
        assert outcome.unresolved_disagreements == [
            "Implementation completeness remains disputed."
        ]
        assert outcome.adjudicated_findings == []
    finally:
        store.close()


def test_handoff_includes_adjudicated_results_and_unresolved_disagreements() -> None:
    handoff = Handoff(
        id="handoff_review",
        task_id="task_review",
        project_id="project_review",
        agent="agent:orchestrator",
        status="completed",
        summary="Review completed with one deferred disagreement.",
        self_audit=SelfAudit(
            schema_validated=True,
            redaction_reviewed=True,
            receipts_reviewed=True,
            assumptions_reviewed=True,
            validation_recorded=True,
            policy_exceptions_disclosed=True,
        ),
        adjudication_ids=["adjudication_deferred"],
        unresolved_disagreements=["Implementation completeness remains disputed."],
        created_at="2026-05-15T22:33:00Z",
    )

    assert handoff.adjudication_ids == ["adjudication_deferred"]
    assert handoff.unresolved_disagreements == [
        "Implementation completeness remains disputed."
    ]


def test_review_request_requires_a_subject() -> None:
    with pytest.raises(ValidationError, match="at least one review subject"):
        ReviewRequest(
            id="review_request_empty",
            task_id="task_review",
            requester_role_id="role_orchestrator",
            reviewer_role_id="role_policy",
            reviewer_role_kind="policy_reviewer",
            created_at="2026-05-15T22:30:00Z",
        )


def test_revised_adjudicated_findings_require_revised_summary() -> None:
    with pytest.raises(ValidationError, match="revised_summary"):
        AdjudicatedFinding(
            source_worker_result_id="worker_result_impl",
            decision="revised",
            rationale="Needs rewritten wording.",
        )


def test_deferred_adjudication_requires_unresolved_disagreement() -> None:
    with pytest.raises(ValidationError, match="unresolved disagreements"):
        AdjudicationOutcome(
            id="adjudication_invalid",
            task_id="task_review",
            adjudicator_role_id="role_adjudicator",
            decision="deferred",
            summary="Deferred without a reason.",
            created_at="2026-05-15T22:34:00Z",
        )


def test_cross_agent_review_protocol_accepts_worker_result(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        policy = generate_policy_envelope(task_id="task_review", actor="runner:fixture")
        manager = ReviewAdjudicationManager(store)
        request = manager.request_cross_agent_review(
            policy=policy,
            task_id="task_review",
            requester_role_id="role_implementer",
            reviewer_role_id="role_verifier",
            reviewer_role_kind="verifier",
            subject_worker_result_ids=["worker_result_impl"],
            focus=["behavior tests"],
        )

        result = manager.complete_cross_agent_review(
            policy=policy,
            review_request_id=request.id,
            decision="approved",
            summary="Verifier accepted the implementation.",
            findings=[
                CrossAgentReviewFinding(
                    id="finding_behavior_tests",
                    summary="Behavior tests cover the reviewed output.",
                    severity="info",
                    evidence_ids=["evidence_tests"],
                )
            ],
        )

        assert request.status == "open"
        assert store.get_review_request(request.id).status == "completed"
        assert result.decision == "approved"
        assert result.worker_result_ids == ["worker_result_impl"]
        assert result.finding_ids == ["finding_behavior_tests"]
        assert result.evidence_ids == ["evidence_tests"]
        assert result.receipt_ids
        assert store.get_receipt(result.receipt_ids[0]).capability == "review.complete"
    finally:
        store.close()


def test_cross_agent_review_protocol_rejects_handoff_subject(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        policy = generate_policy_envelope(task_id="task_review", actor="runner:fixture")
        manager = ReviewAdjudicationManager(store)
        request = manager.request_cross_agent_review(
            policy=policy,
            task_id="task_review",
            requester_role_id="role_implementer",
            reviewer_role_id="role_policy",
            reviewer_role_kind="policy_reviewer",
            subject_handoff_ids=["handoff_impl"],
            focus=["release posture"],
        )

        result = manager.complete_cross_agent_review(
            policy=policy,
            review_request_id=request.id,
            decision="changes_requested",
            summary="Policy reviewer rejected the handoff pending release notes.",
            findings=[
                CrossAgentReviewFinding(
                    id="finding_release_notes",
                    summary="Release notes are missing for the reviewed handoff.",
                    severity="high",
                    evidence_ids=["evidence_changelog"],
                    contradiction_ids=["contradiction_release_notes"],
                )
            ],
        )

        assert result.decision == "changes_requested"
        assert result.subject_handoff_ids == ["handoff_impl"]
        assert result.contradiction_ids == ["contradiction_release_notes"]
        assert store.get_review_request(request.id).status == "completed"
    finally:
        store.close()


def test_cross_agent_review_protocol_preserves_unresolved_debate_summary(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    try:
        policy = generate_policy_envelope(task_id="task_review", actor="runner:fixture")
        manager = ReviewAdjudicationManager(store)
        request = manager.request_cross_agent_review(
            policy=policy,
            task_id="task_review",
            requester_role_id="role_orchestrator",
            reviewer_role_id="role_adversarial",
            reviewer_role_kind="adversarial_reviewer",
            subject_debate_summary_ids=["debate_summary_impl"],
            focus=["unresolved disagreement"],
        )

        result = manager.complete_cross_agent_review(
            policy=policy,
            review_request_id=request.id,
            decision="deferred",
            summary="Adversarial review deferred pending more evidence.",
            findings=[],
            contradiction_ids=["contradiction_impl"],
        )

        assert result.decision == "deferred"
        assert result.debate_summary_ids == ["debate_summary_impl"]
        assert result.contradiction_ids == ["contradiction_impl"]
        receipt = store.get_receipt(result.receipt_ids[0])
        assert receipt.result.metadata["subject_debate_summary_ids"] == [
            "debate_summary_impl"
        ]
    finally:
        store.close()


def test_cross_agent_review_unknown_request_fails(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        with pytest.raises(ReviewRequestNotFoundError, match="unknown review request"):
            ReviewAdjudicationManager(store).complete_cross_agent_review(
                policy=generate_policy_envelope(task_id="task_review", actor="runner:fixture"),
                review_request_id="review_request_missing",
                decision="blocked",
                summary="Cannot complete a missing request.",
                findings=[],
            )
    finally:
        store.close()
