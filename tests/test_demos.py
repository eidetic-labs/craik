import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from craik.runtime.agents import demo as agent_demo
from craik.runtime.agents.demo import DemoConfigError, PersistentAgentLaunchDemo
from craik.runtime.paths import ensure_craik_home
from craik.runtime.projects.demos import DEMO_TASK_ID, StigmemDocsDemo
from craik.runtime.store import LocalStore


@pytest.fixture
def store(tmp_path: Path):
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    local_store = LocalStore.from_paths(paths)
    local_store.initialize()
    try:
        yield local_store
    finally:
        local_store.close()


def test_stigmem_docs_demo_produces_runnable_artifacts(
    tmp_path: Path,
    store: LocalStore,
) -> None:
    repo = _repo(tmp_path)

    result = StigmemDocsDemo(store).run(repo_path=repo, github=False)

    assert result["schema"] == "craik.demo.stigmem_docs_reconciliation"
    assert result["status"] == "runnable"
    assert result["task"]["id"] == DEMO_TASK_ID
    assert result["project"]["memory"]["backend"] == "stigmem"
    assert result["stigmem_backend_status"]["status"] == "not_configured"
    assert store.get_case_file(result["case_file_id"]) is not None
    assert store.get_handoff(result["handoff_id"]) is not None
    assert result["memory_write"]["status"] == "proposal_created"
    assert result["memory_write"]["proposal_id"] in result["memory_proposal_ids"]
    assert result["memory_write"]["direct_write"] == "not_requested"
    assert [item["provider_id"] for item in result["provider_executions"]] == [
        "provider_openai",
        "provider_anthropic",
    ]
    assert {item["run_status"] for item in result["provider_executions"]} == {"completed"}
    assert {tuple(item["provider_families"]) for item in result["provider_executions"]} == {
        ("openai",),
        ("anthropic",),
    }
    assert result["work_graph_id"].startswith("graph_")
    assert store.get_task(DEMO_TASK_ID) is not None
    assert store.list_contradictions()[0].task_id == DEMO_TASK_ID
    assert len(store.list_run_outputs()) == 8
    assert any(
        receipt.result.metadata.get("policy_envelope_id")
        == store.get_case_file(result["case_file_id"]).policy_envelope_id
        for receipt in store.list_receipts()
    )


def test_stigmem_docs_demo_surfaces_boundaries_and_evidence(
    tmp_path: Path,
    store: LocalStore,
) -> None:
    repo = _repo(tmp_path)

    result = StigmemDocsDemo(store).run(repo_path=repo, github=False)

    assert "ADRs are present and must remain immutable evidence." in result["findings"]["risks"]
    assert result["findings"]["evidence_ids"]
    assert any(
        "internal-only labels" in item
        for item in result["findings"]["public_internal_boundary"]
    )
    assert result["proposed_doc_updates"][0]["path"] == "README.md"


def test_stigmem_docs_demo_reports_doc_code_mismatch_from_fixture_repo(
    tmp_path: Path,
    store: LocalStore,
) -> None:
    repo = _repo(
        tmp_path,
        symbol_claim="StigmemSyncEngine",
        source_symbol="ExistingRuntime",
    )

    result = StigmemDocsDemo(store).run(repo_path=repo, github=False)

    mismatch = "README.md references `StigmemSyncEngine`, but no matching source symbol exists."
    assert mismatch in result["findings"]["docs_code_mismatches"]
    contradiction = store.list_contradictions()[0]
    assert contradiction.summary == mismatch
    assert "README.md" in contradiction.affected_artifacts
    proposal = store.get_proposal(result["memory_proposal_ids"][0])
    assert proposal is not None
    assert proposal.fact.value == mismatch
    assert [evidence.locator for evidence in proposal.evidence] == ["README.md"]


def test_stigmem_docs_demo_mismatch_output_varies_with_repo_content(
    tmp_path: Path,
) -> None:
    first_store = _store(tmp_path / "first")
    second_store = _store(tmp_path / "second")
    first_repo = _repo(
        tmp_path / "repo_one",
        symbol_claim="MissingScheduler",
        source_symbol="ExistingScheduler",
    )
    second_repo = _repo(
        tmp_path / "repo_two",
        symbol_claim="AbsentMemoryBridge",
        source_symbol="ExistingMemoryBridge",
    )

    try:
        first = StigmemDocsDemo(first_store).run(repo_path=first_repo, github=False)
        second = StigmemDocsDemo(second_store).run(repo_path=second_repo, github=False)
        first_summary = first_store.list_contradictions()[0].summary
        second_summary = second_store.list_contradictions()[0].summary
    finally:
        first_store.close()
        second_store.close()

    assert first_summary != second_summary
    assert "MissingScheduler" in first_summary
    assert "AbsentMemoryBridge" in second_summary
    assert first["findings"]["docs_code_mismatches"] != second["findings"]["docs_code_mismatches"]


def test_stigmem_docs_demo_can_limit_provider_execution(
    tmp_path: Path,
    store: LocalStore,
) -> None:
    repo = _repo(tmp_path)

    result = StigmemDocsDemo(store).run(
        repo_path=repo,
        github=False,
        provider_ids=("provider_openai",),
    )

    assert [item["provider_id"] for item in result["provider_executions"]] == [
        "provider_openai"
    ]


def test_persistent_agent_launch_demo_runs_provider_matrix(
    tmp_path: Path,
    store: LocalStore,
) -> None:
    repo = _repo(tmp_path)

    result = PersistentAgentLaunchDemo(store).run(repo_path=repo)

    assert result["schema"] == "craik.demo.persistent_agent_launch"
    assert result["mode"] == "fixture"
    assert result["provider_ids"] == [
        "provider_openai",
        "provider_anthropic",
        "provider_gemini",
        "provider_local_ollama",
    ]
    assert len(result["provider_executions"]) == 4
    for execution in result["provider_executions"]:
        assert execution["launch_status"] == "running"
        assert execution["prompt_exit_behavior"] == "completed"
        assert execution["run_status"] == "completed"
        assert execution["handoff_status"] == "completed"
        assert execution["receipt_ids"]
        assert execution["provider_setup"]["certification_status"] == "certified"
        assert execution["status_inspection"]["status"] == "idle"
        assert store.get_agent_session_state(execution["session_id"]) is None
        assert store.get_handoff(execution["handoff_id"]) is not None
    assert any("craik agent launch" in command for command in result["commands"])
    assert any("craik auth setup" in command for command in result["commands"])
    assert result["artifacts_cleaned"] is True


def test_persistent_agent_launch_demo_can_limit_providers(
    tmp_path: Path,
    store: LocalStore,
) -> None:
    repo = _repo(tmp_path)

    result = PersistentAgentLaunchDemo(store).run(
        repo_path=repo,
        provider_ids=("provider_openai", "provider_anthropic"),
    )

    assert [item["provider_id"] for item in result["provider_executions"]] == [
        "provider_openai",
        "provider_anthropic",
    ]


def test_persistent_agent_launch_demo_can_keep_artifacts(
    tmp_path: Path,
    store: LocalStore,
) -> None:
    repo = _repo(tmp_path)

    result = PersistentAgentLaunchDemo(store).run(
        repo_path=repo,
        provider_ids=("provider_openai",),
        cleanup=False,
    )

    session_id = result["provider_executions"][0]["session_id"]
    assert result["artifacts_cleaned"] is False
    assert store.get_agent_session_state(session_id) is not None
    assert store.list_agent_session_events()


def test_persistent_agent_launch_demo_rejects_non_fixture_transport(
    tmp_path: Path,
    store: LocalStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _repo(tmp_path)
    monkeypatch.setattr(
        agent_demo,
        "adapter_for_provider",
        lambda provider: SimpleNamespace(transport=object()),
    )

    with pytest.raises(DemoConfigError, match="requires fixture transport"):
        PersistentAgentLaunchDemo(store).run(
            repo_path=repo,
            provider_ids=("provider_openai",),
        )


def _repo(
    tmp_path: Path,
    *,
    symbol_claim: str = "DocumentedFeature",
    source_symbol: str = "DocumentedFeature",
) -> Path:
    repo = tmp_path / "stigmem"
    (repo / "docs" / "adr").mkdir(parents=True)
    (repo / "src").mkdir()
    (repo / "README.md").write_text(f"# Stigmem\n\nUse `{symbol_claim}` for sync.\n")
    (repo / "src" / "runtime.py").write_text(
        f"class {source_symbol}:\n    pass\n",
        encoding="utf-8",
    )
    (repo / "docs" / "guide.md").write_text("# Guide\n")
    (repo / "docs" / "adr" / "0001-record.md").write_text("# ADR\n")
    _run_git(repo, "init", "-b", "main")
    _run_git(repo, "add", "README.md", "docs", "src")
    _run_git(repo, "commit", "-m", "initial")
    return repo


def _store(path: Path) -> LocalStore:
    paths = ensure_craik_home({"CRAIK_HOME": str(path / "home")})
    local_store = LocalStore.from_paths(paths)
    local_store.initialize()
    return local_store


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
