"""Structured debate capture and contradiction escalation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from craik.contracts.models import (
    AdjudicatedFinding,
    AdjudicationOutcome,
    AgentRoleKind,
    CapabilityReceipt,
    DebateOutcome,
    DebateSummary,
    DebateTurn,
    DebateTurnPosition,
    HumanDelegationPoint,
    PolicyEnvelope,
    ReceiptResult,
    ReceiptStatus,
)
from craik.runtime.memory.contradictions import ContradictionManager
from craik.runtime.reviewing.delegations import HumanDelegationManager
from craik.runtime.store import LocalStore


@dataclass(frozen=True)
class DebatePositionInput:
    """Role-linked position to include in a bounded debate."""

    role_id: str
    role_kind: AgentRoleKind
    position: DebateTurnPosition
    claim: str
    rationale: str
    worker_result_id: str | None = None
    evidence_ids: list[str] = field(default_factory=list)
    assumption_ids: list[str] = field(default_factory=list)
    contradiction_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class StructuredDebateResult:
    """Result of a bounded structured debate workflow."""

    turns: list[DebateTurn]
    summary: DebateSummary
    receipt: CapabilityReceipt
    adjudication: AdjudicationOutcome | None = None
    delegation: HumanDelegationPoint | None = None


class DebateManager:
    """Persist debate turns and produce deterministic debate summaries."""

    def __init__(self, store: LocalStore) -> None:
        self._store = store
        self._contradictions = ContradictionManager(store)

    def record_turn(self, turn: DebateTurn) -> DebateTurn:
        """Persist one debate turn."""
        self._store.put_debate_turn(turn)
        return turn

    def summarize(
        self,
        *,
        task_id: str,
        debate_id: str,
        topic: str,
        turns: list[DebateTurn] | None = None,
        open_contradictions: bool = True,
        next_steps: list[str] | None = None,
    ) -> DebateSummary:
        """Summarize a debate, optionally opening contradictions for conflicting outputs."""
        debate_turns = sorted(
            turns if turns is not None else self._turns_for_debate(debate_id),
            key=lambda turn: (turn.created_at, turn.id),
        )
        for turn in debate_turns:
            self._store.put_debate_turn(turn)

        supports = [turn for turn in debate_turns if turn.position == "supports"]
        oppositions = [turn for turn in debate_turns if turn.position in {"opposes", "blocks"}]
        evidence_ids = sorted(
            {evidence_id for turn in debate_turns for evidence_id in turn.evidence_ids}
        )
        contradiction_ids = sorted(
            {
                contradiction_id
                for turn in debate_turns
                for contradiction_id in turn.contradiction_ids
            }
        )
        worker_result_ids = sorted(
            {turn.worker_result_id for turn in debate_turns if turn.worker_result_id is not None}
        )

        unresolved = _unresolved_disagreements(supports, oppositions)
        agreements = sorted({turn.claim for turn in supports}) if not unresolved else []
        outcome: DebateOutcome = "agreement"
        if unresolved and open_contradictions:
            report = self._contradictions.open_report(
                task_id=task_id,
                facts=[turn.claim for turn in [*supports, *oppositions]],
                summary=f"Debate disagreement: {topic}",
                affected_artifacts=worker_result_ids,
                evidence_ids=evidence_ids,
                proposed_resolution="Adjudicate the conflicting specialist outputs.",
            )
            contradiction_ids = sorted({*contradiction_ids, report.id})
            outcome = "contradiction_opened"
        elif unresolved:
            outcome = "unresolved_disagreement"

        summary = DebateSummary(
            id=f"debate_summary_{debate_id}",
            task_id=task_id,
            debate_id=debate_id,
            topic=topic,
            turn_ids=[turn.id for turn in debate_turns],
            outcome=outcome,
            summary=_summary_text(topic=topic, outcome=outcome, turn_count=len(debate_turns)),
            agreements=agreements,
            unresolved_disagreements=unresolved,
            contradiction_ids=contradiction_ids,
            evidence_ids=evidence_ids,
            next_steps=sorted(next_steps or []),
            created_at=datetime.now(UTC),
        )
        self._store.put_debate_summary(summary)
        return summary

    def run_structured_debate(
        self,
        *,
        policy: PolicyEnvelope,
        task_id: str,
        debate_id: str,
        topic: str,
        positions: list[DebatePositionInput],
        adjudicator_role_id: str | None = None,
        human_owner: str | None = None,
        open_contradictions: bool = True,
        next_steps: list[str] | None = None,
    ) -> StructuredDebateResult:
        """Run a bounded role-linked debate and persist its resolution artifact."""
        if len(positions) < 2:
            raise ValueError("structured debates require at least two positions")

        turns = [
            _turn_from_position(
                task_id=task_id,
                debate_id=debate_id,
                position=position,
                index=index,
            )
            for index, position in enumerate(positions, start=1)
        ]
        summary = self.summarize(
            task_id=task_id,
            debate_id=debate_id,
            topic=topic,
            turns=turns,
            open_contradictions=open_contradictions,
            next_steps=next_steps,
        )
        if summary.outcome == "agreement":
            receipt = self._store.put_receipt(
                _debate_receipt(
                    policy=policy,
                    task_id=task_id,
                    debate_id=debate_id,
                    target=summary.id,
                    capability="debate.resolve",
                    status="passed",
                    summary="Structured debate reached agreement.",
                    metadata=_receipt_metadata(summary=summary),
                )
            )
            return StructuredDebateResult(turns=turns, summary=summary, receipt=receipt)

        if adjudicator_role_id is not None:
            receipt = self._store.put_receipt(
                _debate_receipt(
                    policy=policy,
                    task_id=task_id,
                    debate_id=debate_id,
                    target=f"adjudication_{debate_id}",
                    capability="debate.adjudicate",
                    status="passed",
                    summary="Structured debate resolved by adjudicator.",
                    metadata={
                        **_receipt_metadata(summary=summary),
                        "adjudicator_role_id": adjudicator_role_id,
                    },
                )
            )
            adjudication = AdjudicationOutcome(
                id=f"adjudication_{debate_id}",
                task_id=task_id,
                adjudicator_role_id=adjudicator_role_id,
                decision="accepted",
                summary=f"Adjudicator accepted resolution for {topic}.",
                debate_summary_ids=[summary.id],
                adjudicated_findings=[
                    AdjudicatedFinding(
                        decision="accepted",
                        rationale="Adjudicator reviewed the structured debate summary.",
                        evidence_ids=summary.evidence_ids,
                    )
                ],
                unresolved_disagreements=summary.unresolved_disagreements,
                contradiction_ids=summary.contradiction_ids,
                receipt_ids=[receipt.id],
                created_at=datetime.now(UTC),
            )
            self._store.put_adjudication_outcome(adjudication)
            return StructuredDebateResult(
                turns=turns,
                summary=summary,
                receipt=receipt,
                adjudication=adjudication,
            )

        receipt = self._store.put_receipt(
            _debate_receipt(
                policy=policy,
                task_id=task_id,
                debate_id=debate_id,
                target=f"delegation_{debate_id}",
                capability="debate.delegate",
                status="blocked",
                summary="Structured debate requires human resolution.",
                metadata={**_receipt_metadata(summary=summary), "owner": human_owner},
            )
        )
        delegation = HumanDelegationPoint(
            id=f"delegation_{debate_id}",
            task_id=task_id,
            kind="escalation",
            summary=f"Resolve structured debate: {topic}",
            requested_decision="Choose the accepted position or request more evidence.",
            requested_by="craik:debate-runtime",
            owner=human_owner,
            policy_envelope_id=policy.id,
            contradiction_ids=summary.contradiction_ids,
            receipt_ids=[receipt.id],
            created_at=datetime.now(UTC),
        )
        HumanDelegationManager(self._store).open_delegation(delegation)
        return StructuredDebateResult(
            turns=turns,
            summary=summary,
            receipt=receipt,
            delegation=delegation,
        )

    def _turns_for_debate(self, debate_id: str) -> list[DebateTurn]:
        return [turn for turn in self._store.list_debate_turns() if turn.debate_id == debate_id]


def render_debate_markdown(summary: DebateSummary, turns: list[DebateTurn]) -> str:
    """Render a deterministic Markdown view of a debate summary and its turns."""
    turn_by_id = {turn.id: turn for turn in turns}
    ordered_turns = [turn_by_id[turn_id] for turn_id in summary.turn_ids if turn_id in turn_by_id]
    lines = [
        f"# Debate: {summary.topic}",
        "",
        f"- Outcome: {summary.outcome}",
        f"- Summary: {summary.summary}",
        "",
        "## Agreements",
        *_bullet_lines(summary.agreements),
        "",
        "## Unresolved Disagreements",
        *_bullet_lines(summary.unresolved_disagreements),
        "",
        "## Contradictions",
        *_bullet_lines(summary.contradiction_ids),
        "",
        "## Turns",
    ]
    for turn in ordered_turns:
        evidence = ", ".join(sorted(turn.evidence_ids)) or "none"
        assumptions = ", ".join(sorted(turn.assumption_ids)) or "none"
        lines.extend(
            [
                f"- {turn.id} ({turn.role_kind}/{turn.position})",
                f"  - Claim: {turn.claim}",
                f"  - Rationale: {turn.rationale}",
                f"  - Evidence: {evidence}",
                f"  - Assumptions: {assumptions}",
            ]
        )
    return "\n".join(lines) + "\n"


def render_debate_json(summary: DebateSummary) -> str:
    """Render a deterministic JSON representation of a debate summary."""
    return summary.model_dump_json(by_alias=True, exclude_none=True, indent=2) + "\n"


def _unresolved_disagreements(
    supports: list[DebateTurn],
    oppositions: list[DebateTurn],
) -> list[str]:
    if not supports or not oppositions:
        return []
    return sorted(
        {
            f"{support.role_id} claims {support.claim!r}; "
            f"{opposition.role_id} disputes with {opposition.claim!r}"
            for support in supports
            for opposition in oppositions
        }
    )


def _summary_text(*, topic: str, outcome: DebateOutcome, turn_count: int) -> str:
    if outcome == "agreement":
        return f"{turn_count} debate turn(s) reached agreement on {topic}."
    if outcome == "contradiction_opened":
        return f"{turn_count} debate turn(s) produced a contradiction report for {topic}."
    return f"{turn_count} debate turn(s) preserved unresolved disagreement on {topic}."


def _bullet_lines(values: list[str]) -> list[str]:
    if not values:
        return ["- None"]
    return [f"- {value}" for value in values]


def _turn_from_position(
    *,
    task_id: str,
    debate_id: str,
    position: DebatePositionInput,
    index: int,
) -> DebateTurn:
    return DebateTurn(
        id=f"debate_turn_{debate_id}_{index}_{_slug(position.role_id)}",
        task_id=task_id,
        debate_id=debate_id,
        role_id=position.role_id,
        role_kind=position.role_kind,
        worker_result_id=position.worker_result_id,
        position=position.position,
        claim=position.claim,
        rationale=position.rationale,
        evidence_ids=list(position.evidence_ids),
        assumption_ids=list(position.assumption_ids),
        contradiction_ids=list(position.contradiction_ids),
        created_at=datetime.now(UTC),
    )


def _debate_receipt(
    *,
    policy: PolicyEnvelope,
    task_id: str,
    debate_id: str,
    target: str,
    capability: str,
    status: ReceiptStatus,
    summary: str,
    metadata: dict[str, object],
) -> CapabilityReceipt:
    return CapabilityReceipt(
        id=f"receipt_{debate_id}_{capability.rsplit('.', maxsplit=1)[-1]}",
        task_id=task_id,
        actor="craik:debate-runtime",
        capability=capability,
        target=target,
        policy_profile=policy.profile,
        fail_open=policy.fail_open,
        reason=summary,
        result=ReceiptResult(status=status, summary=summary, metadata=metadata),
        redacted=True,
        created_at=datetime.now(UTC),
    )


def _receipt_metadata(summary: DebateSummary) -> dict[str, object]:
    return {
        "debate_id": summary.debate_id,
        "debate_summary_id": summary.id,
        "turn_ids": list(summary.turn_ids),
        "outcome": summary.outcome,
        "contradiction_ids": list(summary.contradiction_ids),
        "unresolved_disagreements": list(summary.unresolved_disagreements),
    }


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "role"
