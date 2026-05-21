import subprocess
from pathlib import Path

import pytest

from craik.contracts.models import FactValue, MemoryProposal
from craik.runtime.memory.contradictions import ContradictionManager
from craik.runtime.memory.memory_hygiene import memory_hygiene_report
from craik.runtime.paths import ensure_craik_home
from craik.runtime.projects.project_registry import ProjectRegistry
from craik.runtime.store import LocalStore
from craik.runtime.work.handoffs import HandoffWriter
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


def test_memory_hygiene_reports_pending_proposals_contradictions_and_handoffs(
    store: LocalStore,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Repo\n")
    subprocess.run(("git", "init", "-b", "main"), cwd=repo, check=True, capture_output=True)
    subprocess.run(("git", "add", "README.md"), cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ("git", "commit", "-m", "initial"),
        cwd=repo,
        check=True,
        capture_output=True,
        env={
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_AUTHOR_NAME": "Craik Test",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "Craik Test",
        },
    )
    project = ProjectRegistry(store).add_project(repo, name="Example")
    task = create_task(
        store,
        title="Memory hygiene",
        objective="Check memory health.",
        project_id=project.id,
    )
    store.put_proposal(
        MemoryProposal(
            id="proposal_memory_hygiene",
            task_id=task.id,
            operation="add",
            fact=FactValue(
                entity="repo:Example",
                relation="memory:hygiene",
                value="pending",
                source="agent:codex",
                confidence=0.8,
                scope="local",
                trust_class="inferred",
            ),
        )
    )
    HandoffWriter(store).create(
        task_id=task.id,
        agent="agent:codex",
        summary="Memory hygiene handoff.",
        tests_run=["pytest"],
        next_steps=["Review memory hygiene contradiction."],
    )
    contradiction = ContradictionManager(store).open_report(
        task_id=task.id,
        facts=["a", "b"],
        summary="Memory conflict.",
        affected_artifacts=["README.md"],
        evidence_ids=["evidence_memory"],
    )

    report = memory_hygiene_report(store, task_id=task.id)

    assert report.healthy is False
    assert report.pending_proposals == ["proposal_memory_hygiene"]
    assert report.open_contradictions == [contradiction.id]
    assert report.recent_handoffs == [f"handoff_{task.id.removeprefix('task_')}"]
    assert "pending memory proposals" in report.warnings[0]
    assert report.task_id == task.id
