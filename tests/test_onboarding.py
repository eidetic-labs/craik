import subprocess
from pathlib import Path

import pytest

from craik.runtime.memory.contradictions import ContradictionManager
from craik.runtime.paths import ensure_craik_home
from craik.runtime.projects.onboarding import AgentOnboardingBuilder, OnboardingProjectNotFoundError
from craik.runtime.projects.project_registry import ProjectRegistry
from craik.runtime.store import LocalStore
from craik.runtime.work.handoffs import HandoffWriter
from craik.runtime.work.tasks import create_task


@pytest.fixture
def store(tmp_path: Path):
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    local_store = LocalStore.from_paths(paths)
    local_store.initialize()
    try:
        yield local_store
    finally:
        local_store.close()


def test_onboarding_report_includes_project_boundaries_and_state(
    tmp_path: Path,
    store: LocalStore,
) -> None:
    repo = _repo(tmp_path)
    project = ProjectRegistry(store).add_project(repo, name="Example")
    task = create_task(
        store,
        title="Review docs",
        objective="Review docs against implementation.",
        project_id=project.id,
    )
    HandoffWriter(store).create(
        task_id=task.id,
        agent="agent:test",
        summary="Reviewed docs state.",
        tests_run=["pytest"],
        next_steps=["Continue implementation."],
    )
    contradiction = ContradictionManager(store).open_report(
        task_id=task.id,
        facts=["docs say pending", "implementation is complete"],
        summary="Docs and implementation disagree.",
        affected_artifacts=["README.md"],
        evidence_ids=[],
    )

    report = AgentOnboardingBuilder(store).build(project.id)

    assert report.schema_ == "craik.agent_onboarding"
    assert report.project_id == project.id
    assert report.project_model["task_count"] == 1
    assert report.project_model["repo"]["status"] == "clean"
    assert report.active_policy.profile == "strict"
    assert report.docs_boundaries["immutable_paths"] == ["docs/adr/"]
    assert report.recent_handoffs[0]["id"] == "handoff_review_docs"
    assert [item.id for item in report.unresolved_contradictions] == [contradiction.id]
    assert "uv run --python 3.12 --extra dev pytest" in report.validation_commands
    assert report.stigmem_backend_status["backend"] == "local"
    assert any("immutable" in trap for trap in report.known_traps)
    assert any("case file" in action for action in report.allowed_next_actions)


def test_onboarding_reports_stale_risks_for_missing_context(
    tmp_path: Path,
    store: LocalStore,
) -> None:
    repo = _repo(tmp_path)
    (repo / "scratch.txt").write_text("dirty\n")
    project = ProjectRegistry(store).add_project(
        repo,
        name="Example",
        docs_paths=("missing-docs/",),
        immutable_paths=("docs/adr/",),
    )

    report = AgentOnboardingBuilder(store).build(project.id)

    assert report.docs_boundaries["missing_mutable_paths"] == ["missing-docs/"]
    assert any("uncommitted changes" in warning for warning in report.stale_risk_warnings)
    assert any("No task requests" in warning for warning in report.stale_risk_warnings)
    assert any("No prior handoffs" in warning for warning in report.stale_risk_warnings)
    assert any(
        "documentation paths are missing" in warning for warning in report.stale_risk_warnings
    )


def test_onboarding_errors_for_unknown_project(store: LocalStore) -> None:
    with pytest.raises(OnboardingProjectNotFoundError, match="unknown project"):
        AgentOnboardingBuilder(store).build("project_missing")


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "docs" / "adr").mkdir(parents=True)
    (repo / "README.md").write_text("# Example\n")
    (repo / "docs" / "guide.md").write_text("# Guide\n")
    (repo / "docs" / "adr" / "0001-record.md").write_text("# ADR\n")
    (repo / "pyproject.toml").write_text("[project]\nname = \"example\"\n")
    _run_git(repo, "init", "-b", "main")
    _run_git(repo, "add", "README.md", "docs", "pyproject.toml")
    _run_git(repo, "commit", "-m", "initial")
    return repo


def _run_git(repo: Path, *args: str) -> None:
    subprocess.run(
        ("git", *args),
        cwd=repo,
        check=True,
        env={
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_AUTHOR_NAME": "Craik Test",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "Craik Test",
        },
    )
