import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from craik.contracts.models import CapabilityGrant, CapabilityTarget
from craik.runtime.paths import ensure_craik_home
from craik.runtime.projects.project_registry import ProjectRegistry
from craik.runtime.providers.provider_runner import ProviderBackedRunExecutor
from craik.runtime.store import LocalStore
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


@pytest.mark.parametrize(
    ("provider_id", "provider_family"),
    [
        ("provider_openai", "openai"),
        ("provider_anthropic", "anthropic"),
        ("provider_google", "google"),
        ("provider_local_ollama", "chat_completions"),
    ],
)
def test_provider_backed_runner_completes_full_mvp_path(
    store: LocalStore,
    tmp_path: Path,
    provider_id: str,
    provider_family: str,
) -> None:
    task_id = _seed_task(store, tmp_path)

    result = ProviderBackedRunExecutor(store).execute(
        task_id=task_id,
        provider_id=provider_id,
        grants=[_shell_grant(task_id)],
        started_at=datetime(2026, 5, 17, 12, 0, tzinfo=UTC),
    )

    assert result.run.status == "completed"
    assert result.run.handoff_id == result.handoff.id
    assert result.handoff.status == "completed"
    assert result.compiled_prompt.runner_id == provider_id
    assert len(result.provider_results) == 4
    assert {item.provider_family for item in result.provider_results} == {provider_family}
    assert len(store.list_run_outputs()) == 4
    assert _receipt_count(store, "provider_action") == 4
    assert any(receipt.capability == "shell.execute" for receipt in store.list_receipts())
    assert result.handoff.receipt_ids
    run_output_ids = [output.id for output in store.list_run_outputs()]
    assert set(result.handoff.artifacts) >= {*run_output_ids, result.compiled_prompt.id}
    exit_check = store.get_exit_discipline_check(f"exit_discipline_{task_id}")
    assert exit_check is not None
    assert exit_check.status == "complete"
    assert exit_check.handoff_id == result.handoff.id


def test_provider_backed_runner_blocks_with_durable_handoff_when_policy_denies(
    store: LocalStore,
    tmp_path: Path,
) -> None:
    task_id = _seed_task(store, tmp_path)

    result = ProviderBackedRunExecutor(store).execute(
        task_id=task_id,
        provider_id="provider_openai",
        grants=[],
    )

    assert result.run.status == "blocked"
    assert result.handoff.status == "blocked"
    assert result.run.handoff_id == result.handoff.id
    assert len(result.provider_results) == 1
    assert _receipt_count(store, "provider_action") == 1
    assert any(receipt.result.status == "denied" for receipt in store.list_receipts())
    assert "Resolve the blocking approval" in result.handoff.next_steps[0]


def test_provider_backed_runner_records_failure_handoff(
    store: LocalStore,
    tmp_path: Path,
) -> None:
    task_id = _seed_task(store, tmp_path)

    result = ProviderBackedRunExecutor(store).execute(
        task_id=task_id,
        provider_id="provider_anthropic",
        grants=[_shell_grant(task_id)],
        statuses=["completed", "failed"],
    )

    assert result.run.status == "failed"
    assert result.handoff.status == "failed"
    assert len(result.provider_results) == 2
    assert result.handoff.self_audit.validation_recorded is True
    assert "Inspect diagnostics" in result.handoff.next_steps[0]


def test_provider_backed_runner_records_interruption_handoff(
    store: LocalStore,
    tmp_path: Path,
) -> None:
    task_id = _seed_task(store, tmp_path)

    result = ProviderBackedRunExecutor(store).execute(
        task_id=task_id,
        provider_id="provider_openai",
        grants=[_shell_grant(task_id)],
        max_iterations=1,
    )

    assert result.interrupted_error == "max iterations 1 reached"
    assert result.run.status == "interrupted"
    assert result.handoff.status == "incomplete"
    assert len(result.provider_results) == 1
    assert "Inspect run state" in result.handoff.next_steps[0]


def test_provider_backed_runner_interrupts_when_provider_token_budget_exhausts(
    store: LocalStore,
    tmp_path: Path,
) -> None:
    task_id = _seed_task(store, tmp_path)

    result = ProviderBackedRunExecutor(store).execute(
        task_id=task_id,
        provider_id="provider_openai",
        grants=[_shell_grant(task_id)],
        provider_token_budget=30,
    )

    assert result.interrupted_error == "provider token budget exhausted"
    assert result.run.status == "interrupted"
    assert result.run.provider_token_budget == 30
    assert result.run.provider_tokens_used == 30
    assert result.run.provider_token_budget_remaining == 0
    assert len(result.provider_results) == 1
    assert result.handoff.status == "incomplete"


def test_provider_backed_runner_records_role_dispatch(
    store: LocalStore,
    tmp_path: Path,
) -> None:
    task_id = _seed_task(store, tmp_path)

    result = ProviderBackedRunExecutor(store).execute(
        task_id=task_id,
        provider_id="provider_openai",
        grants=[_shell_grant(task_id)],
        role_kind="docs_reviewer",
        started_at=datetime(2026, 5, 17, 12, 0, tzinfo=UTC),
    )
    dispatch_receipt = store.get_receipt(f"receipt_{task_id}_role_dispatch_docs_reviewer")

    assert result.compiled_prompt.runner_id == "provider_openai_chat"
    assert result.run.role_id == "role_docs_reviewer"
    assert result.run.role_kind == "docs_reviewer"
    assert dispatch_receipt is not None
    assert dispatch_receipt.id in result.run.receipt_ids
    assert dispatch_receipt.result.metadata["runner_id"] == "provider_openai_chat"


def _seed_task(store: LocalStore, tmp_path: Path) -> str:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Repo\n")
    _run_git(repo, "init", "-b", "main")
    _run_git(repo, "add", "README.md")
    _run_git(repo, "commit", "-m", "initial")
    project = ProjectRegistry(store).add_project(repo, name="Example")
    task = create_task(
        store,
        title="Run provider MVP path",
        objective="Execute a provider-backed MVP runner path.",
        project_id=project.id,
        mode="implement",
        expected_outputs=["runner_step_result", "handoff"],
    )
    return task.id


def _shell_grant(task_id: str) -> CapabilityGrant:
    return CapabilityGrant(
        id=f"grant_{task_id.removeprefix('task_')}_shell",
        task_id=task_id,
        capability="shell.execute",
        target=CapabilityTarget(paths=["fixture-action"]),
        operations=["execute"],
        reason="Allow deterministic MVP fixture action.",
        approved_by="user:maintainer",
    )


def _receipt_count(store: LocalStore, action: str) -> int:
    return sum(
        1
        for receipt in store.list_receipts()
        if receipt.result.metadata.get("environment_action") == action
    )


def _run_git(repo: Path, *args: str) -> None:
    subprocess.run(
        ("git", *args),
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_AUTHOR_NAME": "Craik Test",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "Craik Test",
        },
    )
