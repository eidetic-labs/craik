from pathlib import Path

import pytest
from pydantic import ValidationError

from craik.contracts.models import (
    Handoff,
    HumanDelegationPoint,
    ScopeChangeRequest,
    ScopeChangeResult,
    SelfAudit,
)
from craik.runtime.paths import ensure_craik_home
from craik.runtime.policy.policy import generate_policy_envelope
from craik.runtime.reviewing.delegations import (
    HumanDelegationManager,
    HumanDelegationStateError,
    must_stop_for_human_decision,
)
from craik.runtime.store import LocalStore
from craik.runtime.work.runs import RunTransition, TaskRunManager


def _store(tmp_path: Path) -> LocalStore:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    store = LocalStore.from_paths(paths)
    store.initialize()
    return store


def _delegation(kind: str, delegation_id: str) -> HumanDelegationPoint:
    return HumanDelegationPoint(
        id=delegation_id,
        task_id="task_delegate",
        kind=kind,
        summary=f"{kind} needed.",
        requested_decision=f"Provide {kind}.",
        requested_by="agent:orchestrator",
        owner="user:maintainer",
        role_id="role_orchestrator",
        intent_lock_id="intent_delegate",
        policy_envelope_id="policy_delegate",
        created_at="2026-05-15T22:30:00Z",
    )


def _scope_request() -> ScopeChangeRequest:
    return ScopeChangeRequest(
        id="scope_change_add_files",
        task_id="task_delegate",
        intent_lock_id="intent_delegate",
        requested_by="agent:orchestrator",
        reason="The requested fix requires changing an out-of-scope file.",
        current_scope=["Update docs only."],
        proposed_scope=["Update docs and contract fixtures."],
        policy_envelope_id="policy_delegate",
        delegation_id="delegation_escalation",
        contradiction_ids=["contradiction_scope"],
        handoff_ids=["handoff_delegate"],
        created_at="2026-05-15T22:31:00Z",
    )


def _run(
    store: LocalStore,
    *,
    operator_subject: str | None = None,
    operator_issuer: str | None = None,
) -> str:
    run = TaskRunManager(store).create(
        task_id="task_delegate",
        case_file_id="case_delegate",
        policy_envelope_id="policy_delegate",
        runner_id="provider_openai",
        runner_mode="live",
        intent_lock_id="intent_delegate",
        operator_subject=operator_subject,
        operator_issuer=operator_issuer,
    )
    return run.id


@pytest.mark.parametrize(
    ("kind", "delegation_id"),
    [
        ("approval", "delegation_approval"),
        ("clarification", "delegation_clarification"),
        ("escalation", "delegation_escalation"),
        ("ownership_transfer", "delegation_transfer"),
    ],
)
def test_human_delegation_points_stop_until_resolved(
    tmp_path: Path,
    kind: str,
    delegation_id: str,
) -> None:
    store = _store(tmp_path)
    try:
        manager = HumanDelegationManager(store)
        delegation = manager.open_delegation(_delegation(kind, delegation_id))

        assert must_stop_for_human_decision([delegation], []) is True

        resolved = manager.resolve_delegation(delegation.id, "Human decision recorded.")

        assert resolved.status == "resolved"
        assert resolved.resolution == "Human decision recorded."
        assert must_stop_for_human_decision([resolved], []) is False
        assert store.get_human_delegation(delegation.id) == resolved
    finally:
        store.close()


def test_run_can_pause_for_human_delegation_and_resume_after_acceptance(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    try:
        run_id = _run(store)
        policy = generate_policy_envelope(task_id="task_delegate", actor="runner:fixture")
        manager = HumanDelegationManager(store)

        paused = manager.pause_run_for_delegation(
            policy=policy,
            run_id=run_id,
            kind="approval",
            summary="Approval needed before continuing.",
            requested_decision="Approve continuing the run.",
            requested_by="agent:orchestrator",
            owner="user:maintainer",
        )
        resolved = manager.resolve_run_delegation(
            policy=policy,
            delegation_id=paused.delegation.id,
            resolution="Approved; continue.",
            outcome="accepted",
            operator_subject="operator-a",
            operator_issuer="https://issuer.example.test",
        )
        resumed = TaskRunManager(store).prepare_resume(run_id)

        assert paused.run.status == "interrupted"
        assert paused.delegation.run_id == run_id
        assert paused.receipt.id in paused.run.receipt_ids
        assert resolved.delegation.status == "resolved"
        assert resolved.receipt.id in resolved.run.receipt_ids
        assert resumed.status == "running"
    finally:
        store.close()


def test_run_delegation_rejection_keeps_run_interrupted(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        run_id = _run(store)
        policy = generate_policy_envelope(task_id="task_delegate", actor="runner:fixture")
        manager = HumanDelegationManager(store)
        paused = manager.pause_run_for_delegation(
            policy=policy,
            run_id=run_id,
            kind="clarification",
            summary="Clarification needed before continuing.",
            requested_decision="Clarify whether to continue.",
            requested_by="agent:orchestrator",
        )

        resolved = manager.resolve_run_delegation(
            policy=policy,
            delegation_id=paused.delegation.id,
            resolution="Rejected; do not continue.",
            outcome="rejected",
            operator_subject="operator-a",
            operator_issuer="https://issuer.example.test",
        )

        assert resolved.delegation.status == "resolved"
        assert resolved.receipt.result.status == "denied"
        assert resolved.run.status == "interrupted"
    finally:
        store.close()


def test_run_delegation_cancel_path_records_cancelled_state(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        run_id = _run(store)
        policy = generate_policy_envelope(task_id="task_delegate", actor="runner:fixture")
        manager = HumanDelegationManager(store)
        paused = manager.pause_run_for_delegation(
            policy=policy,
            run_id=run_id,
            kind="escalation",
            summary="Escalation needed.",
            requested_decision="Decide whether to transfer ownership.",
            requested_by="agent:orchestrator",
        )

        cancelled = manager.resolve_run_delegation(
            policy=policy,
            delegation_id=paused.delegation.id,
            resolution="Timed out; cancel delegation.",
            outcome="cancelled",
            operator_subject="operator-a",
            operator_issuer="https://issuer.example.test",
        )

        assert cancelled.delegation.status == "cancelled"
        assert cancelled.receipt.result.metadata["outcome"] == "cancelled"
        assert cancelled.run.status == "interrupted"
    finally:
        store.close()


def test_run_delegation_resolution_requires_matching_operator(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        run_id = _run(
            store,
            operator_subject="operator-a",
            operator_issuer="https://issuer.example.test",
        )
        policy = generate_policy_envelope(task_id="task_delegate", actor="runner:fixture")
        manager = HumanDelegationManager(store)
        paused = manager.pause_run_for_delegation(
            policy=policy,
            run_id=run_id,
            kind="approval",
            summary="Approval needed.",
            requested_decision="Approve continuing the run.",
            requested_by="agent:orchestrator",
        )

        with pytest.raises(HumanDelegationStateError, match="does not match"):
            manager.resolve_run_delegation(
                policy=policy,
                delegation_id=paused.delegation.id,
                resolution="Wrong operator.",
                outcome="accepted",
                operator_subject="operator-b",
                operator_issuer="https://issuer.example.test",
            )
    finally:
        store.close()


def test_pausing_terminal_run_is_rejected(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        run_id = _run(store)
        TaskRunManager(store).transition(run_id, RunTransition(status="completed", phase="stop"))
        with pytest.raises(HumanDelegationStateError, match="already terminal"):
            HumanDelegationManager(store).pause_run_for_delegation(
                policy=generate_policy_envelope(task_id="task_delegate", actor="runner:fixture"),
                run_id=run_id,
                kind="approval",
                summary="Approval needed.",
                requested_decision="Approve.",
                requested_by="agent:orchestrator",
            )
    finally:
        store.close()


def test_rejected_scope_change_keeps_request_rejected(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        manager = HumanDelegationManager(store)
        request = manager.request_scope_change(_scope_request())

        assert must_stop_for_human_decision([], [request]) is True

        result = manager.decide_scope_change(
            ScopeChangeResult(
                id="scope_change_result_rejected",
                task_id=request.task_id,
                scope_change_request_id=request.id,
                decision="rejected",
                decided_by="user:maintainer",
                rationale="Keep the original documentation-only scope.",
                created_at="2026-05-15T22:32:00Z",
            )
        )

        updated = store.get_scope_change_request(request.id)
        assert result.decision == "rejected"
        assert updated.status == "rejected"
        assert must_stop_for_human_decision([], [updated]) is False
    finally:
        store.close()


def test_accepted_scope_change_links_updated_intent_lock(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        manager = HumanDelegationManager(store)
        request = manager.request_scope_change(_scope_request())

        result = manager.decide_scope_change(
            ScopeChangeResult(
                id="scope_change_result_accepted",
                task_id=request.task_id,
                scope_change_request_id=request.id,
                decision="accepted",
                decided_by="user:maintainer",
                rationale="Fixture updates are required to complete the contract work.",
                updated_intent_lock_id="intent_delegate_updated",
                policy_envelope_id="policy_delegate",
                handoff_ids=["handoff_delegate"],
                created_at="2026-05-15T22:33:00Z",
            )
        )

        updated = store.get_scope_change_request(request.id)
        assert result.decision == "accepted"
        assert result.updated_intent_lock_id == "intent_delegate_updated"
        assert updated.status == "accepted"
        assert store.get_scope_change_result(result.id) == result
    finally:
        store.close()


def test_handoff_surfaces_open_human_delegation_points() -> None:
    handoff = Handoff(
        id="handoff_delegate",
        task_id="task_delegate",
        project_id="project_delegate",
        agent="agent:orchestrator",
        status="blocked",
        summary="Blocked on human clarification.",
        self_audit=SelfAudit(
            schema_validated=True,
            redaction_reviewed=True,
            receipts_reviewed=True,
            assumptions_reviewed=True,
            validation_recorded=False,
            policy_exceptions_disclosed=True,
        ),
        open_human_delegation_ids=["delegation_clarification"],
        scope_change_request_ids=["scope_change_add_files"],
        created_at="2026-05-15T22:34:00Z",
    )

    assert handoff.open_human_delegation_ids == ["delegation_clarification"]
    assert handoff.scope_change_request_ids == ["scope_change_add_files"]


def test_resolved_delegation_requires_resolution_text() -> None:
    with pytest.raises(ValidationError, match="resolution text"):
        HumanDelegationPoint(
            id="delegation_invalid",
            task_id="task_delegate",
            kind="approval",
            status="resolved",
            summary="Approval was resolved.",
            requested_decision="Approve the action.",
            requested_by="agent:orchestrator",
            created_at="2026-05-15T22:35:00Z",
        )


def test_accepted_scope_change_requires_updated_intent_lock() -> None:
    with pytest.raises(ValidationError, match="updated_intent_lock_id"):
        ScopeChangeResult(
            id="scope_change_result_invalid",
            task_id="task_delegate",
            scope_change_request_id="scope_change_add_files",
            decision="accepted",
            decided_by="user:maintainer",
            rationale="Accepted but missing updated intent lock.",
            created_at="2026-05-15T22:36:00Z",
        )
