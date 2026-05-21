import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from craik.contracts.models import FactValue
from craik.runtime.auth.profile import AuthProfile, CredentialKind
from craik.runtime.auth.store import AuthProfileStore
from craik.runtime.memory.contradictions import ContradictionManager
from craik.runtime.paths import ensure_craik_home
from craik.runtime.projects.project_registry import ProjectRegistry
from craik.runtime.store import LocalStore
from craik.runtime.work.case_files import (
    CaseFileAssembler,
    CaseFilePathTraversalError,
    DiscoveryOverrides,
    ProjectNotFoundError,
    TaskNotFoundError,
)
from craik.runtime.work.case_support import context_budget
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


def test_case_file_build_is_deterministic_and_persisted(
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
        mode="review",
    )
    assembler = CaseFileAssembler(store)

    first = assembler.build(task.id)
    second = assembler.build(task.id)

    assert first == second
    loaded = assembler.latest_for_task(task.id)
    assert loaded is not None
    assert loaded.model_dump(mode="json", by_alias=True) == first.model_dump(
        mode="json",
        by_alias=True,
    )
    assert first.id == "case_review_docs"
    assert first.policy_envelope_id == "policy_task_review_docs"
    assert first.intent_lock_id == "intent_review_docs"
    assert first.docs == ["README.md", "docs/guide.md"]
    assert first.adrs == ["docs/adr/0001-record.md"]
    assert first.repo_state["status"] == "clean"
    assert first.context_budget["max_tokens"] == 24000
    assert first.context_budget["docs_included"] == 2
    assert first.context_budget["adrs_included"] == 1


def test_case_file_labels_immutable_evidence(tmp_path: Path, store: LocalStore) -> None:
    repo = _repo(tmp_path)
    project = ProjectRegistry(store).add_project(repo, name="Example")
    task = create_task(
        store,
        title="Check ADRs",
        objective="Check immutable docs.",
        project_id=project.id,
    )

    case_file = CaseFileAssembler(store).build(task.id)

    immutable = [
        evidence for evidence in case_file.evidence if evidence.locator == "docs/adr/0001-record.md"
    ]
    assert immutable
    assert immutable[0].metadata["immutable"] is True


def test_case_file_tracks_missing_context_as_assumptions(
    tmp_path: Path,
    store: LocalStore,
) -> None:
    repo = _repo(tmp_path)
    project = ProjectRegistry(store).add_project(repo, name="Example", docs_paths=("missing/",))
    task = create_task(
        store,
        title="Missing docs",
        objective="Build case with missing docs.",
        project_id=project.id,
    )

    case_file = CaseFileAssembler(store).build(task.id)

    statements = {assumption.statement for assumption in case_file.assumptions}
    assert "No memory facts were loaded into this case file." in statements
    assert "No GitHub issue or pull request state was loaded into this case file." in statements
    assert "No mutable documentation files were discovered for this project." in statements
    assert case_file.github_state == {"status": "not_loaded"}
    assert "Case file contains open assumptions" in case_file.stale_risks[-1]


def test_case_file_path_traversal_denial_records_receipt(
    tmp_path: Path,
    store: LocalStore,
) -> None:
    repo = _repo(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text("# Outside\n")
    try:
        (repo / "docs" / "leak.md").symlink_to(outside)
    except OSError as exc:  # pragma: no cover - platform permission guard
        pytest.skip(f"symlinks unavailable: {exc}")
    project = ProjectRegistry(store).add_project(repo, name="Traversal")
    task = create_task(
        store,
        title="Build escaped case",
        objective="Reject escaped docs.",
        project_id=project.id,
    )

    with pytest.raises(CaseFilePathTraversalError, match="escapes repository root"):
        CaseFileAssembler(store).build(task.id)

    receipts = store.list_receipts()
    assert len(receipts) == 1
    assert receipts[0].task_id == task.id
    assert receipts[0].capability == "case_file.read"
    assert receipts[0].result.status == "denied"
    assert receipts[0].target == "case_file.discovery"


def test_case_context_budget_counts_extracted_context_inputs() -> None:
    budget = context_budget(
        max_tokens=128,
        docs=["README.md"],
        adrs=["docs/adr/0001-record.md"],
        omitted_docs=["docs/large.md"],
        excluded_docs=[{"path": "docs/build", "reason": "excluded by pattern"}],
        discovery_rules={"default_exclude": ["docs/build/**"]},
        evidence=[],
        assumptions=[],
        active_instruction_constraints=[{"path": "AGENTS.md"}],
        distillations=[{"id": "distilled_instruction_docs"}],
        memory_fact_count=2,
        recent_handoffs=["handoff_1: completed: Done"],
        contradiction_ids=["contradiction_1"],
    )

    assert budget["docs_included"] == 1
    assert budget["adrs_included"] == 1
    assert budget["docs_omitted"] == ["docs/large.md"]
    assert budget["memory_fact_count"] == 2
    assert budget["contradiction_ids"] == ["contradiction_1"]
    assert budget["distillations"] == [{"id": "distilled_instruction_docs"}]


def test_case_file_loads_memory_handoffs_and_contradictions(
    tmp_path: Path,
    store: LocalStore,
) -> None:
    repo = _repo(tmp_path)
    project = ProjectRegistry(store).add_project(repo, name="Example")
    task = create_task(
        store,
        title="Memory context",
        objective="Build case with memory.",
        project_id=project.id,
    )
    CaseFileAssembler(store).build(task.id)
    handoff = HandoffWriter(store).create(
        task_id=task.id,
        agent="agent:codex",
        summary="Prior memory handoff.",
        tests_run=["pytest"],
    )
    contradiction = ContradictionManager(store).open_report(
        task_id=task.id,
        facts=["old fact", "new fact"],
        summary="Facts disagree.",
        affected_artifacts=["README.md"],
        evidence_ids=["evidence_memory"],
    )
    memory = _FactMemory(
        [
            FactValue(
                entity="repo:Example",
                relation="memory:note",
                value="Memory fact loaded.",
                source="stigmem:fixture",
                confidence=1.0,
                scope="local",
                trust_class="observed",
            )
        ]
    )

    case_file = CaseFileAssembler(store, memory=memory).build(task.id)

    assert case_file.facts == memory.facts
    assert handoff.id in case_file.recent_handoffs[0]
    assert case_file.contradictions == [contradiction]
    assert case_file.context_budget["memory_fact_count"] == 1
    assert case_file.context_budget["contradiction_ids"] == [contradiction.id]
    assert "Memory facts were not loaded" not in {
        assumption.statement for assumption in case_file.assumptions
    }


def test_case_file_reports_omitted_docs_from_context_budget(
    tmp_path: Path,
    store: LocalStore,
) -> None:
    repo = _repo(tmp_path)
    (repo / "docs" / "long.md").write_text("x" * 100)
    _run_git(repo, "add", "docs/long.md")
    _run_git(repo, "commit", "-m", "add long doc")
    project = ProjectRegistry(store).add_project(repo, name="Example")
    task = create_task(
        store,
        title="Small budget",
        objective="Build case with a small context budget.",
        project_id=project.id,
    )

    case_file = CaseFileAssembler(store).build(task.id, max_tokens=1)

    assert "docs/long.md" in case_file.context_budget["docs_omitted"]
    assert any("omitted from the case file" in item.statement for item in case_file.assumptions)


def test_case_file_records_credential_expiry_risk(
    tmp_path: Path,
    store: LocalStore,
) -> None:
    repo = _repo(tmp_path)
    project = ProjectRegistry(store).add_project(repo, name="Example")
    expires_at = datetime.now(UTC) + timedelta(minutes=30)
    _put_auth_profile(
        store,
        "anthropic:local-cli",
        kind=CredentialKind.OAUTH_TOKEN,
        metadata={"source": "local-cli", "expires_at": expires_at.isoformat()},
    )
    task = create_task(
        store,
        title="Credential expiry",
        objective="Build case with credential expiry context.",
        project_id=project.id,
        auth_profile_id="anthropic:local-cli",
        expected_duration_minutes=60,
    )

    case_file = CaseFileAssembler(store).build(task.id)

    auth_evidence = [
        evidence
        for evidence in case_file.evidence
        if evidence.id == f"evidence_{task.id}_auth_profile"
    ]
    assert auth_evidence
    assert auth_evidence[0].metadata["auth_profile_id"] == "anthropic:local-cli"
    assert auth_evidence[0].metadata["expires_at"] == expires_at.isoformat()
    assert any("credential_expiry_risk" in risk for risk in case_file.stale_risks)


def test_case_file_skips_credential_expiry_risk_for_long_lived_token(
    tmp_path: Path,
    store: LocalStore,
) -> None:
    repo = _repo(tmp_path)
    project = ProjectRegistry(store).add_project(repo, name="Example")
    _put_auth_profile(
        store,
        "anthropic:local-cli",
        kind=CredentialKind.OAUTH_TOKEN,
        metadata={
            "source": "local-cli",
            "expires_at": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
        },
    )
    task = create_task(
        store,
        title="Long lived credential",
        objective="Build case with credential expiry context.",
        project_id=project.id,
        auth_profile_id="anthropic:local-cli",
        expected_duration_minutes=60,
    )

    case_file = CaseFileAssembler(store).build(task.id)

    assert any(
        evidence.metadata.get("auth_profile_id") == "anthropic:local-cli"
        for evidence in case_file.evidence
    )
    assert not any("credential_expiry_risk" in risk for risk in case_file.stale_risks)


def test_case_file_excludes_generated_dependency_and_archive_paths_by_default(
    tmp_path: Path,
    store: LocalStore,
) -> None:
    repo = _repo(tmp_path)
    (repo / "docs" / "archive").mkdir()
    (repo / "docs" / "archive" / "old.md").write_text("# Old\n")
    (repo / "docs" / "build").mkdir()
    (repo / "docs" / "build" / "generated.md").write_text("# Generated\n")
    (repo / "docs" / "reference" / "generated").mkdir(parents=True)
    (repo / "docs" / "reference" / "generated" / "api.md").write_text("# API\n")
    (repo / "docs" / "node_modules" / "pkg").mkdir(parents=True)
    (repo / "docs" / "node_modules" / "pkg" / "README.md").write_text("# Dependency\n")
    _run_git(repo, "add", "docs")
    _run_git(repo, "commit", "-m", "add polluted docs")
    project = ProjectRegistry(store).add_project(repo, name="Example")
    task = create_task(
        store,
        title="Clean context",
        objective="Build case without generated docs.",
        project_id=project.id,
    )

    case_file = CaseFileAssembler(store).build(task.id)

    assert "docs/archive/old.md" not in case_file.docs
    assert "docs/build/generated.md" not in case_file.docs
    assert "docs/reference/generated/api.md" not in case_file.docs
    assert "docs/node_modules/pkg/README.md" not in case_file.docs
    excluded = {item["path"] for item in case_file.context_budget["docs_excluded"]}
    assert "docs/archive" in excluded
    assert "docs/build" in excluded
    assert "docs/reference/generated" in excluded
    assert "docs/node_modules" in excluded
    assert case_file.context_budget["discovery_rules"]["default_exclude"]


def test_case_file_project_and_user_discovery_overrides_are_deterministic(
    tmp_path: Path,
    store: LocalStore,
) -> None:
    repo = _repo(tmp_path)
    (repo / "docs" / "archive").mkdir()
    (repo / "docs" / "archive" / "old.md").write_text("# Old\n")
    (repo / "docs" / "draft.md").write_text("# Draft\n")
    _run_git(repo, "add", "docs")
    _run_git(repo, "commit", "-m", "add override docs")
    project = ProjectRegistry(store).add_project(
        repo,
        name="Example",
        discovery_include=("docs/archive/**",),
        discovery_exclude=("docs/draft.md",),
    )
    task = create_task(
        store,
        title="Override context",
        objective="Build case with discovery overrides.",
        project_id=project.id,
    )

    case_file = CaseFileAssembler(store).build(
        task.id,
        discovery_overrides=DiscoveryOverrides(exclude=("docs/guide.md",)),
    )

    assert "docs/archive/old.md" in case_file.docs
    assert "docs/draft.md" not in case_file.docs
    assert "docs/guide.md" not in case_file.docs
    excluded = {item["path"] for item in case_file.context_budget["docs_excluded"]}
    assert "docs/draft.md" in excluded
    assert "docs/guide.md" in excluded
    rules = case_file.context_budget["discovery_rules"]
    assert rules["project_include"] == ["docs/archive/**"]
    assert rules["project_exclude"] == ["docs/draft.md"]
    assert rules["user_exclude"] == ["docs/guide.md"]


def test_case_file_errors_for_missing_task_or_project(store: LocalStore) -> None:
    assembler = CaseFileAssembler(store)

    with pytest.raises(TaskNotFoundError, match="unknown task"):
        assembler.build("task_missing")

    task = create_task(
        store,
        title="Bad project",
        objective="Missing project.",
        project_id="project_missing",
    )

    with pytest.raises(ProjectNotFoundError, match="unknown project"):
        assembler.build(task.id)


class _FactMemory:
    def __init__(self, facts: list[FactValue]) -> None:
        self.facts = facts

    def search(self, query: str) -> list[FactValue]:
        return self.facts


def _put_auth_profile(
    store: LocalStore,
    profile_id: str,
    *,
    kind: CredentialKind,
    metadata: dict[str, object],
) -> None:
    AuthProfileStore(store.database_path.parent.parent).put(
        AuthProfile(
            id=profile_id,
            kind=kind,
            provider_family=profile_id.split(":", 1)[0],
            metadata=metadata,
            created_at=datetime.now(UTC),
        )
    )


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "docs" / "adr").mkdir(parents=True)
    (repo / "README.md").write_text("# Example\n")
    (repo / "docs" / "guide.md").write_text("# Guide\n")
    (repo / "docs" / "adr" / "0001-record.md").write_text("# ADR\n")
    _run_git(repo, "init", "-b", "main")
    _run_git(repo, "add", "README.md", "docs")
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
