from pathlib import Path

from craik.contracts.models import DebateSummary, DebateTurn
from craik.runtime.paths import ensure_craik_home
from craik.runtime.policy.policy import generate_policy_envelope
from craik.runtime.reviewing.debates import (
    DebateManager,
    DebatePositionInput,
    render_debate_json,
    render_debate_markdown,
)
from craik.runtime.store import LocalStore


def _store(tmp_path: Path) -> LocalStore:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    store = LocalStore.from_paths(paths)
    store.initialize()
    return store


def _turn(
    *,
    turn_id: str,
    position: str,
    role_id: str,
    claim: str,
    worker_result_id: str | None = None,
) -> DebateTurn:
    return DebateTurn(
        id=turn_id,
        task_id="task_debate",
        debate_id="debate_architecture",
        role_id=role_id,
        role_kind="verifier",
        worker_result_id=worker_result_id,
        position=position,
        claim=claim,
        rationale=f"Rationale for {turn_id}.",
        evidence_ids=[f"evidence_{turn_id}"],
        assumption_ids=[f"assumption_{turn_id}"],
        created_at="2026-05-15T22:30:00Z",
    )


def test_debate_agreement_summary_and_deterministic_rendering(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        manager = DebateManager(store)
        turns = [
            _turn(
                turn_id="turn_docs",
                position="supports",
                role_id="role_docs",
                claim="The docs match the implementation.",
            ),
            _turn(
                turn_id="turn_verifier",
                position="supports",
                role_id="role_verifier",
                claim="The docs match the implementation.",
            ),
        ]

        summary = manager.summarize(
            task_id="task_debate",
            debate_id="debate_architecture",
            topic="documentation status",
            turns=turns,
        )

        assert summary.outcome == "agreement"
        assert summary.agreements == ["The docs match the implementation."]
        assert summary.contradiction_ids == []
        markdown = render_debate_markdown(summary, turns)
        assert markdown == render_debate_markdown(summary, list(reversed(turns)))
        assert "- Outcome: agreement" in markdown
        assert render_debate_json(summary) == render_debate_json(
            DebateSummary.model_validate_json(render_debate_json(summary))
        )
    finally:
        store.close()


def test_debate_preserves_unresolved_disagreement_without_forcing_consensus(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    try:
        turns = [
            _turn(
                turn_id="turn_support",
                position="supports",
                role_id="role_verifier",
                claim="The implementation is complete.",
            ),
            _turn(
                turn_id="turn_oppose",
                position="opposes",
                role_id="role_adversarial",
                claim="The implementation lacks deterministic rendering.",
            ),
        ]

        summary = DebateManager(store).summarize(
            task_id="task_debate",
            debate_id="debate_architecture",
            topic="implementation completeness",
            turns=turns,
            open_contradictions=False,
        )

        assert summary.outcome == "unresolved_disagreement"
        assert summary.agreements == []
        assert summary.unresolved_disagreements
        assert summary.contradiction_ids == []
        assert store.list_contradictions() == []
    finally:
        store.close()


def test_debate_opens_contradiction_report_for_conflicting_specialist_outputs(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    try:
        turns = [
            _turn(
                turn_id="turn_support",
                position="supports",
                role_id="role_verifier",
                claim="The implementation is complete.",
                worker_result_id="worker_result_verifier",
            ),
            _turn(
                turn_id="turn_block",
                position="blocks",
                role_id="role_adversarial",
                claim="The implementation lacks deterministic rendering.",
                worker_result_id="worker_result_adversarial",
            ),
        ]

        summary = DebateManager(store).summarize(
            task_id="task_debate",
            debate_id="debate_architecture",
            topic="implementation completeness",
            turns=turns,
            open_contradictions=True,
        )

        reports = store.list_contradictions()
        assert summary.outcome == "contradiction_opened"
        assert summary.contradiction_ids == [reports[0].id]
        assert reports[0].summary == "Debate disagreement: implementation completeness"
        assert reports[0].affected_artifacts == [
            "worker_result_adversarial",
            "worker_result_verifier",
        ]
    finally:
        store.close()


def test_structured_debate_runtime_records_agreement_receipt(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        result = DebateManager(store).run_structured_debate(
            policy=generate_policy_envelope(task_id="task_debate", actor="runner:fixture"),
            task_id="task_debate",
            debate_id="debate_runtime_agreement",
            topic="docs readiness",
            positions=[
                DebatePositionInput(
                    role_id="role_docs",
                    role_kind="docs_reviewer",
                    position="supports",
                    claim="Docs are ready.",
                    rationale="The docs build and match the feature set.",
                    evidence_ids=["evidence_docs"],
                    assumption_ids=["assumption_docs"],
                ),
                DebatePositionInput(
                    role_id="role_verifier",
                    role_kind="verifier",
                    position="supports",
                    claim="Docs are ready.",
                    rationale="Verification found no blocker.",
                    evidence_ids=["evidence_verify"],
                ),
            ],
        )

        assert result.summary.outcome == "agreement"
        assert result.adjudication is None
        assert result.delegation is None
        assert result.receipt.capability == "debate.resolve"
        assert result.receipt.result.metadata["turn_ids"] == [
            "debate_turn_debate_runtime_agreement_1_role_docs",
            "debate_turn_debate_runtime_agreement_2_role_verifier",
        ]
        assert store.get_receipt(result.receipt.id) == result.receipt
        assert len(store.list_debate_turns()) == 2
    finally:
        store.close()


def test_structured_debate_runtime_delegates_unresolved_disagreement(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    try:
        result = DebateManager(store).run_structured_debate(
            policy=generate_policy_envelope(task_id="task_debate", actor="runner:fixture"),
            task_id="task_debate",
            debate_id="debate_runtime_unresolved",
            topic="release readiness",
            positions=[
                DebatePositionInput(
                    role_id="role_verifier",
                    role_kind="verifier",
                    position="supports",
                    claim="Release is ready.",
                    rationale="All validation passed.",
                ),
                DebatePositionInput(
                    role_id="role_adversarial",
                    role_kind="adversarial_reviewer",
                    position="opposes",
                    claim="Release needs more evidence.",
                    rationale="A migration path is not demonstrated.",
                ),
            ],
            open_contradictions=False,
            human_owner="user:maintainer",
        )

        assert result.summary.outcome == "unresolved_disagreement"
        assert result.receipt.capability == "debate.delegate"
        assert result.receipt.result.status == "blocked"
        assert result.delegation is not None
        assert result.delegation.owner == "user:maintainer"
        assert result.delegation.receipt_ids == [result.receipt.id]
        assert store.get_human_delegation(result.delegation.id) == result.delegation
    finally:
        store.close()


def test_structured_debate_runtime_adjudicates_disagreement(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        result = DebateManager(store).run_structured_debate(
            policy=generate_policy_envelope(task_id="task_debate", actor="runner:fixture"),
            task_id="task_debate",
            debate_id="debate_runtime_adjudicated",
            topic="implementation completeness",
            positions=[
                DebatePositionInput(
                    role_id="role_verifier",
                    role_kind="verifier",
                    worker_result_id="worker_result_verifier",
                    position="supports",
                    claim="Implementation is complete.",
                    rationale="The feature has behavior tests.",
                    evidence_ids=["evidence_verifier"],
                ),
                DebatePositionInput(
                    role_id="role_adversarial",
                    role_kind="adversarial_reviewer",
                    worker_result_id="worker_result_adversarial",
                    position="blocks",
                    claim="Implementation still needs a rollback path.",
                    rationale="A failure mode is not covered.",
                    evidence_ids=["evidence_adversarial"],
                ),
            ],
            adjudicator_role_id="role_adjudicator",
        )

        assert result.summary.outcome == "contradiction_opened"
        assert result.receipt.capability == "debate.adjudicate"
        assert result.adjudication is not None
        assert result.adjudication.debate_summary_ids == [result.summary.id]
        assert result.adjudication.receipt_ids == [result.receipt.id]
        assert result.adjudication.contradiction_ids == result.summary.contradiction_ids
        assert store.get_adjudication_outcome(result.adjudication.id) == result.adjudication
    finally:
        store.close()
