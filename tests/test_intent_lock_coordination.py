from datetime import UTC, datetime
from pathlib import Path

import pytest

from craik.contracts.models import RunnerMetadata
from craik.runtime.memory.memory import LocalMemoryStore
from craik.runtime.paths import ensure_craik_home
from craik.runtime.policy.intent_locks import IntentLockManager
from craik.runtime.policy.policy import generate_policy_envelope
from craik.runtime.store import LocalStore
from craik.runtime.work.coordination.intent_locks import check_intent_lock_coordination
from craik.runtime.work.loop import FixtureStepRunner, SingleAgentLoopExecutor
from craik.runtime.work.runs import RunTransition, TaskRunManager
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


def test_intent_lock_coordination_denies_overlapping_active_run(
    store: LocalStore,
) -> None:
    lock_manager = IntentLockManager(store)
    first_task = create_task(
        store,
        title="Edit docs",
        objective="Edit docs.",
        project_id="project_craik",
    )
    first_lock = lock_manager.create_for_task(first_task, in_scope=["docs/"])
    TaskRunManager(store).create(
        task_id=first_task.id,
        case_file_id="case_first",
        policy_envelope_id="policy_first",
        runner_id="runner_first",
        runner_mode="fixture",
        intent_lock_id=first_lock.id,
    )
    second_task = create_task(
        store,
        title="Edit guide",
        objective="Edit guide.",
        project_id="project_craik",
    )
    second_lock = lock_manager.create_for_task(second_task, in_scope=["docs/guide.md"])

    result = SingleAgentLoopExecutor(
        store=store,
        memory=LocalMemoryStore(store),
        runner=FixtureStepRunner(),
    ).execute(
        task_id=second_task.id,
        case_file_id="case_second",
        policy=generate_policy_envelope(task_id=second_task.id, actor="runner:fixture"),
        runner_metadata=_runner(),
        intent_lock=second_lock,
        started_at=datetime(2026, 5, 20, 12, 0, tzinfo=UTC),
    )

    assert result.run.status == "blocked"
    assert result.run.stop_reason == "active run already holds an overlapping intent lock"
    assert result.step_results == []
    assert result.receipts[0].capability == "intent_lock.coordinate"
    assert result.receipts[0].result.status == "denied"
    assert result.receipts[0].result.metadata["conflicting_run_ids"] == ["run_edit_docs"]


def test_intent_lock_coordination_allows_disjoint_scope(store: LocalStore) -> None:
    lock_manager = IntentLockManager(store)
    first_task = create_task(
        store,
        title="Edit docs",
        objective="Edit docs.",
        project_id="project_craik",
    )
    first_lock = lock_manager.create_for_task(first_task, in_scope=["docs/"])
    first_run = TaskRunManager(store).create(
        task_id=first_task.id,
        case_file_id="case_first",
        policy_envelope_id="policy_first",
        runner_id="runner_first",
        runner_mode="fixture",
        intent_lock_id=first_lock.id,
    )
    second_task = create_task(
        store,
        title="Edit source",
        objective="Edit source.",
        project_id="project_craik",
    )
    second_lock = lock_manager.create_for_task(second_task, in_scope=["src/craik/"])
    second_run = TaskRunManager(store).create(
        task_id=second_task.id,
        case_file_id="case_second",
        policy_envelope_id="policy_second",
        runner_id="runner_second",
        runner_mode="fixture",
        intent_lock_id=second_lock.id,
        run_id="run_second",
    )

    decision = check_intent_lock_coordination(
        store,
        run=second_run,
        intent_lock=second_lock,
    )

    assert first_run.status == "pending"
    assert decision.allowed is True
    assert decision.conflicting_run_ids == ()


def test_intent_lock_coordination_ignores_terminal_conflict(store: LocalStore) -> None:
    lock_manager = IntentLockManager(store)
    first_task = create_task(
        store,
        title="Edit docs",
        objective="Edit docs.",
        project_id="project_craik",
    )
    first_lock = lock_manager.create_for_task(first_task, in_scope=["docs/"])
    runs = TaskRunManager(store)
    first_run = runs.create(
        task_id=first_task.id,
        case_file_id="case_first",
        policy_envelope_id="policy_first",
        runner_id="runner_first",
        runner_mode="fixture",
        intent_lock_id=first_lock.id,
    )
    runs.transition(first_run.id, RunTransition(status="completed", phase="stop"))
    second_task = create_task(
        store,
        title="Edit guide",
        objective="Edit guide.",
        project_id="project_craik",
    )
    second_lock = lock_manager.create_for_task(second_task, in_scope=["docs/guide.md"])
    second_run = runs.create(
        task_id=second_task.id,
        case_file_id="case_second",
        policy_envelope_id="policy_second",
        runner_id="runner_second",
        runner_mode="fixture",
        intent_lock_id=second_lock.id,
        run_id="run_second",
    )

    decision = check_intent_lock_coordination(
        store,
        run=second_run,
        intent_lock=second_lock,
    )

    assert decision.allowed is True
    assert decision.conflicting_run_ids == ()


def _runner() -> RunnerMetadata:
    return RunnerMetadata(
        id="runner_fixture",
        name="Fixture Runner",
        adapter="fixture",
        adapter_version="0.1.0",
        mode="fixture",
        capabilities=["prompt.read", "result.structured"],
    )
