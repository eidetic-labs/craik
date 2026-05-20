from datetime import UTC, datetime
from pathlib import Path

import pytest

from craik.contracts.models import IntentLock, PolicyEnvelope, RunnerMetadata, TaskRequest, TaskRun
from craik.runtime.memory.memory import LocalMemoryStore
from craik.runtime.paths import ensure_craik_home
from craik.runtime.policy.intent_locks import IntentLockManager
from craik.runtime.policy.policy import generate_policy_envelope
from craik.runtime.store import LocalStore
from craik.runtime.work.coordination.scope_changes import (
    ScopeChangeProtocolError,
    ScopeChangeProtocolManager,
    outside_scope,
)
from craik.runtime.work.loop import FixtureStepRunner, LoopStep, SingleAgentLoopExecutor
from craik.runtime.work.tasks import create_task


@pytest.fixture
def store(tmp_path: Path) -> LocalStore:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    local_store = LocalStore.from_paths(paths)
    local_store.initialize()
    try:
        yield local_store
    finally:
        local_store.close()


def test_loop_pauses_for_discovered_out_of_scope_work(store: LocalStore) -> None:
    task, lock, policy = _task_lock_policy(store)

    result = SingleAgentLoopExecutor(
        store=store,
        memory=LocalMemoryStore(store),
        runner=FixtureStepRunner(),
    ).execute(
        task_id=task.id,
        case_file_id="case_scope",
        policy=policy,
        runner_metadata=_runner(),
        intent_lock=lock,
        steps=[
            LoopStep(
                phase="plan",
                input_prompt="Plan.",
                context={"discovered_scope": ["src/craik/runtime/new_feature.py"]},
            )
        ],
        started_at=datetime(2026, 5, 20, 12, 0, tzinfo=UTC),
    )

    requests = store.list_scope_change_requests()
    assert result.run.status == "interrupted"
    assert result.run.stop_reason == f"scope change pending: {requests[0].id}"
    assert result.step_results == []
    assert requests[0].status == "pending"
    assert requests[0].proposed_scope == ["docs/", "src/craik/runtime/new_feature.py"]
    assert result.receipts[0].capability == "scope_change.request"
    assert result.receipts[0].result.status == "blocked"


def test_scope_change_expand_updates_intent_lock_and_run(store: LocalStore) -> None:
    task, lock, policy = _task_lock_policy(store)
    run = _paused_scope_change(store, task.id, policy, lock.id)
    request = store.list_scope_change_requests()[0]

    outcome = ScopeChangeProtocolManager(store).decide(
        policy=policy,
        request_id=request.id,
        protocol_decision="expand",
        decided_by="user:maintainer",
        rationale="The source edit is required to complete the requested docs work.",
        run_id=run.id,
    )

    assert outcome.result.decision == "accepted"
    assert outcome.result.protocol_decision == "expand"
    assert outcome.updated_intent_lock is not None
    assert "src/craik/runtime/new_feature.py" in outcome.updated_intent_lock.in_scope
    assert outcome.run is not None
    assert outcome.run.intent_lock_id == outcome.updated_intent_lock.id
    assert store.get_scope_change_request(request.id).status == "accepted"


def test_scope_change_sibling_creates_follow_up_task(store: LocalStore) -> None:
    task, lock, policy = _task_lock_policy(store)
    _paused_scope_change(store, task.id, policy, lock.id)
    request = store.list_scope_change_requests()[0]

    outcome = ScopeChangeProtocolManager(store).decide(
        policy=policy,
        request_id=request.id,
        protocol_decision="sibling",
        decided_by="user:maintainer",
        rationale="Keep this run docs-only and create a separate implementation task.",
        sibling_title="Implement discovered runtime feature",
    )

    assert outcome.result.decision == "accepted"
    assert outcome.result.protocol_decision == "sibling"
    assert outcome.sibling_task is not None
    assert outcome.result.sibling_task_id == outcome.sibling_task.id
    assert outcome.sibling_task.source_task_id == task.id
    assert outcome.receipt.result.metadata["sibling_task_id"] == outcome.sibling_task.id


def test_scope_change_handoff_links_existing_handoff(store: LocalStore) -> None:
    task, lock, policy = _task_lock_policy(store)
    _paused_scope_change(store, task.id, policy, lock.id)
    request = store.list_scope_change_requests()[0]

    outcome = ScopeChangeProtocolManager(store).decide(
        policy=policy,
        request_id=request.id,
        protocol_decision="handoff",
        decided_by="user:maintainer",
        rationale="Hand the discovered implementation work to the implementation agent.",
        handoff_ids=["handoff_scope_impl"],
    )

    assert outcome.result.decision == "accepted"
    assert outcome.result.protocol_decision == "handoff"
    assert outcome.result.handoff_ids == ["handoff_scope_impl"]
    assert outcome.receipt.result.metadata["handoff_ids"] == ["handoff_scope_impl"]


def test_scope_change_denial_records_rejected_request(store: LocalStore) -> None:
    task, lock, policy = _task_lock_policy(store)
    _paused_scope_change(store, task.id, policy, lock.id)
    request = store.list_scope_change_requests()[0]

    outcome = ScopeChangeProtocolManager(store).decide(
        policy=policy,
        request_id=request.id,
        protocol_decision="denied",
        decided_by="user:maintainer",
        rationale="Do not expand this task beyond docs.",
    )

    assert outcome.result.decision == "rejected"
    assert outcome.result.protocol_decision == "denied"
    assert outcome.receipt.result.status == "denied"
    assert store.get_scope_change_request(request.id).status == "rejected"


def test_scope_change_handoff_requires_handoff_id(store: LocalStore) -> None:
    task, lock, policy = _task_lock_policy(store)
    _paused_scope_change(store, task.id, policy, lock.id)
    request = store.list_scope_change_requests()[0]

    with pytest.raises(ScopeChangeProtocolError, match="handoff_ids"):
        ScopeChangeProtocolManager(store).decide(
            policy=policy,
            request_id=request.id,
            protocol_decision="handoff",
            decided_by="user:maintainer",
            rationale="Handoff without a target is incomplete.",
        )


def test_scope_detection_respects_out_of_scope_overrides(store: LocalStore) -> None:
    task, lock, _policy = _task_lock_policy(store)
    lock = lock.model_copy(update={"out_of_scope": ["docs/private/"]})
    store.put_intent_lock(lock)

    assert task.id
    assert outside_scope(lock, ["docs/public/guide.md", "docs/private/secret.md"]) == [
        "docs/private/secret.md"
    ]


def _task_lock_policy(store: LocalStore) -> tuple[TaskRequest, IntentLock, PolicyEnvelope]:
    task = create_task(
        store,
        title="Update docs",
        objective="Update the documentation.",
        project_id="project_craik",
    )
    lock = IntentLockManager(store).create_for_task(task, in_scope=["docs/"])
    policy = generate_policy_envelope(task_id=task.id, actor="runner:fixture")
    return task, lock, policy


def _paused_scope_change(
    store: LocalStore,
    task_id: str,
    policy: PolicyEnvelope,
    intent_lock_id: str,
) -> TaskRun:
    run = SingleAgentLoopExecutor(
        store=store,
        memory=LocalMemoryStore(store),
        runner=FixtureStepRunner(),
    ).execute(
        task_id=task_id,
        case_file_id="case_scope",
        policy=policy,
        runner_metadata=_runner(),
        intent_lock=store.get_intent_lock(intent_lock_id),
        steps=[
            LoopStep(
                phase="plan",
                input_prompt="Plan.",
                context={"discovered_scope": ["src/craik/runtime/new_feature.py"]},
            )
        ],
        started_at=datetime(2026, 5, 20, 12, 0, tzinfo=UTC),
    ).run
    return run


def _runner() -> RunnerMetadata:
    return RunnerMetadata(
        id="runner_fixture",
        name="Fixture Runner",
        adapter="fixture",
        adapter_version="0.1.0",
        mode="fixture",
        capabilities=["prompt.read", "result.structured"],
    )
