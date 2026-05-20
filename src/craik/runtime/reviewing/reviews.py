"""Cross-agent review and adjudication helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from craik.contracts.models import (
    AdjudicatedFinding,
    AdjudicationDecision,
    AdjudicationOutcome,
    AgentRoleKind,
    CapabilityReceipt,
    FindingSeverity,
    PolicyEnvelope,
    ReceiptResult,
    ReceiptStatus,
    ReviewDecision,
    ReviewRequest,
    ReviewResult,
)
from craik.runtime.store import LocalStore
from craik.runtime.work.coordination.live_graph import WorkGraphCoordinator


@dataclass(frozen=True)
class CrossAgentReviewFinding:
    """Typed finding emitted by a reviewer against another agent's output."""

    id: str
    summary: str
    severity: FindingSeverity = "info"
    evidence_ids: list[str] = field(default_factory=list)
    contradiction_ids: list[str] = field(default_factory=list)


class ReviewAdjudicationManager:
    """Persist cross-agent reviews and deterministic adjudication outcomes."""

    def __init__(self, store: LocalStore) -> None:
        self._store = store

    def request_review(self, request: ReviewRequest) -> ReviewRequest:
        """Persist a bounded specialist review request."""
        self._store.put_review_request(request)
        WorkGraphCoordinator(self._store).record_artifact(
            task_id=request.task_id,
            artifact_type="review_request",
            artifact_id=request.id,
            receipt_ids=request.receipt_ids,
            metadata={
                "status": request.status,
                "reviewer_role_id": request.reviewer_role_id,
                "reviewer_role_kind": request.reviewer_role_kind,
            },
        )
        return request

    def request_cross_agent_review(
        self,
        *,
        policy: PolicyEnvelope,
        task_id: str,
        requester_role_id: str,
        reviewer_role_id: str,
        reviewer_role_kind: AgentRoleKind,
        subject_worker_result_ids: list[str] | None = None,
        subject_handoff_ids: list[str] | None = None,
        subject_debate_summary_ids: list[str] | None = None,
        focus: list[str] | None = None,
        due_at: datetime | None = None,
    ) -> ReviewRequest:
        """Create a receipted bounded review request against immutable source ids."""
        request_id = _review_request_id(
            task_id=task_id,
            reviewer_role_id=reviewer_role_id,
            subject_ids=[
                *(subject_worker_result_ids or []),
                *(subject_handoff_ids or []),
                *(subject_debate_summary_ids or []),
            ],
        )
        receipt = self._store.put_receipt(
            _review_receipt(
                policy=policy,
                task_id=task_id,
                capability="review.request",
                target=request_id,
                status="passed",
                summary=f"Cross-agent review requested from {reviewer_role_id}.",
                metadata={
                    "review_request_id": request_id,
                    "requester_role_id": requester_role_id,
                    "reviewer_role_id": reviewer_role_id,
                    "reviewer_role_kind": reviewer_role_kind,
                    "subject_worker_result_ids": list(subject_worker_result_ids or []),
                    "subject_handoff_ids": list(subject_handoff_ids or []),
                    "subject_debate_summary_ids": list(subject_debate_summary_ids or []),
                },
            )
        )
        request = ReviewRequest(
            id=request_id,
            task_id=task_id,
            requester_role_id=requester_role_id,
            reviewer_role_id=reviewer_role_id,
            reviewer_role_kind=reviewer_role_kind,
            subject_worker_result_ids=list(subject_worker_result_ids or []),
            subject_handoff_ids=list(subject_handoff_ids or []),
            subject_debate_summary_ids=list(subject_debate_summary_ids or []),
            focus=list(focus or []),
            policy_envelope_id=policy.id,
            receipt_ids=[receipt.id],
            due_at=due_at,
            created_at=datetime.now(UTC),
        )
        return self.request_review(request)

    def record_result(self, result: ReviewResult) -> ReviewResult:
        """Persist a specialist review result and mark its request complete."""
        self._store.put_review_result(result)
        WorkGraphCoordinator(self._store).record_artifact(
            task_id=result.task_id,
            artifact_type="review_result",
            artifact_id=result.id,
            receipt_ids=result.receipt_ids,
            source_node=f"review_request:{result.review_request_id}",
            relation="depends_on",
            metadata={"decision": result.decision, "reviewer_role_id": result.reviewer_role_id},
        )
        request = self._store.get_review_request(result.review_request_id)
        if request is not None and request.status == "open":
            self._store.put_review_request(request.model_copy(update={"status": "completed"}))
        return result

    def complete_cross_agent_review(
        self,
        *,
        policy: PolicyEnvelope,
        review_request_id: str,
        decision: ReviewDecision,
        summary: str,
        findings: list[CrossAgentReviewFinding],
        contradiction_ids: list[str] | None = None,
    ) -> ReviewResult:
        """Persist a reviewer result without mutating reviewed source artifacts."""
        request = self._store.get_review_request(review_request_id)
        if request is None:
            raise ReviewRequestNotFoundError(f"unknown review request: {review_request_id}")
        linked_evidence_ids = sorted(
            {evidence_id for finding in findings for evidence_id in finding.evidence_ids}
        )
        linked_contradiction_ids = sorted(
            {
                contradiction_id
                for finding in findings
                for contradiction_id in finding.contradiction_ids
            }
            | set(contradiction_ids or [])
        )
        result_id = f"review_result_{review_request_id}"
        receipt = self._store.put_receipt(
            _review_receipt(
                policy=policy,
                task_id=request.task_id,
                capability="review.complete",
                target=result_id,
                status="passed" if decision == "approved" else "blocked",
                summary=summary,
                metadata={
                    "review_request_id": review_request_id,
                    "review_result_id": result_id,
                    "reviewer_role_id": request.reviewer_role_id,
                    "reviewer_role_kind": request.reviewer_role_kind,
                    "decision": decision,
                    "finding_ids": [finding.id for finding in findings],
                    "findings": [_finding_metadata(finding) for finding in findings],
                    "subject_worker_result_ids": list(request.subject_worker_result_ids),
                    "subject_handoff_ids": list(request.subject_handoff_ids),
                    "subject_debate_summary_ids": list(request.subject_debate_summary_ids),
                },
            )
        )
        result = ReviewResult(
            id=result_id,
            task_id=request.task_id,
            review_request_id=request.id,
            reviewer_role_id=request.reviewer_role_id,
            reviewer_role_kind=request.reviewer_role_kind,
            decision=decision,
            summary=summary,
            finding_ids=[finding.id for finding in findings],
            worker_result_ids=list(request.subject_worker_result_ids),
            subject_handoff_ids=list(request.subject_handoff_ids),
            debate_summary_ids=list(request.subject_debate_summary_ids),
            evidence_ids=linked_evidence_ids,
            contradiction_ids=linked_contradiction_ids,
            receipt_ids=[receipt.id],
            created_at=datetime.now(UTC),
        )
        return self.record_result(result)

    def adjudicate(
        self,
        *,
        task_id: str,
        outcome_id: str,
        adjudicator_role_id: str,
        decision: AdjudicationDecision,
        summary: str,
        review_results: list[ReviewResult],
        findings: list[AdjudicatedFinding],
        debate_summary_ids: list[str] | None = None,
        unresolved_disagreements: list[str] | None = None,
        contradiction_ids: list[str] | None = None,
        receipt_ids: list[str] | None = None,
        handoff_ids: list[str] | None = None,
    ) -> AdjudicationOutcome:
        """Persist a deterministic adjudicator outcome over review results."""
        for result in review_results:
            self.record_result(result)
        linked_contradiction_ids = {
            contradiction_id
            for result in review_results
            for contradiction_id in result.contradiction_ids
        }
        linked_receipt_ids = {
            receipt_id for result in review_results for receipt_id in result.receipt_ids
        }
        linked_handoff_ids = {
            result.handoff_id for result in review_results if result.handoff_id
        } | {handoff_id for result in review_results for handoff_id in result.subject_handoff_ids}
        outcome = AdjudicationOutcome(
            id=outcome_id,
            task_id=task_id,
            adjudicator_role_id=adjudicator_role_id,
            decision=decision,
            summary=summary,
            review_result_ids=sorted(result.id for result in review_results),
            worker_result_ids=sorted(
                {worker_id for result in review_results for worker_id in result.worker_result_ids}
            ),
            debate_summary_ids=sorted(debate_summary_ids or []),
            adjudicated_findings=sorted(
                findings,
                key=lambda finding: (
                    finding.source_worker_result_id or "",
                    finding.source_finding_id or "",
                    finding.source_review_result_id or "",
                    finding.decision,
                ),
            ),
            unresolved_disagreements=sorted(unresolved_disagreements or []),
            contradiction_ids=sorted({*linked_contradiction_ids, *(contradiction_ids or [])}),
            receipt_ids=sorted({*linked_receipt_ids, *(receipt_ids or [])}),
            handoff_ids=sorted({*linked_handoff_ids, *(handoff_ids or [])}),
            policy_review_result_ids=sorted(
                result.id
                for result in review_results
                if result.reviewer_role_kind == "policy_reviewer"
            ),
            adversarial_review_result_ids=sorted(
                result.id
                for result in review_results
                if result.reviewer_role_kind == "adversarial_reviewer"
            ),
            created_at=datetime.now(UTC),
        )
        self._store.put_adjudication_outcome(outcome)
        WorkGraphCoordinator(self._store).record_artifact(
            task_id=task_id,
            artifact_type="adjudication",
            artifact_id=outcome.id,
            receipt_ids=outcome.receipt_ids,
            metadata={"decision": outcome.decision, "adjudicator_role_id": adjudicator_role_id},
        )
        return outcome


class ReviewRequestNotFoundError(RuntimeError):
    """Raised when a review result targets an unknown request."""


def _review_receipt(
    *,
    policy: PolicyEnvelope,
    task_id: str,
    capability: str,
    target: str,
    status: ReceiptStatus,
    summary: str,
    metadata: dict[str, object],
) -> CapabilityReceipt:
    return CapabilityReceipt(
        id=f"receipt_{target}_{capability.rsplit('.', maxsplit=1)[-1]}",
        task_id=task_id,
        actor="craik:review-protocol",
        capability=capability,
        target=target,
        policy_profile=policy.profile,
        fail_open=policy.fail_open,
        reason=summary,
        result=ReceiptResult(status=status, summary=summary, metadata=metadata),
        redacted=True,
        created_at=datetime.now(UTC),
    )


def _review_request_id(
    *,
    task_id: str,
    reviewer_role_id: str,
    subject_ids: list[str],
) -> str:
    raw = "_".join([task_id, reviewer_role_id, *sorted(subject_ids)])
    return f"review_request_{_slug(raw)}"


def _finding_metadata(finding: CrossAgentReviewFinding) -> dict[str, object]:
    return {
        "id": finding.id,
        "summary": finding.summary,
        "severity": finding.severity,
        "evidence_ids": list(finding.evidence_ids),
        "contradiction_ids": list(finding.contradiction_ids),
    }


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "review"
