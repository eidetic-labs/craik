import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from craik.contracts.models import (
    CapabilityReceipt,
    ReceiptResult,
    RunOutput,
    RunStatus,
    TaskRun,
    TaskRunStatus,
)
from craik.runtime.paths import ensure_craik_home
from craik.runtime.projects.project_registry import ProjectRegistry
from craik.runtime.store import LocalStore
from craik.runtime.work.case_files import CaseFileAssembler
from craik.runtime.work.coordination.handoff_consumption import (
    HandoffConsumptionError,
    consume_handoff,
)
from craik.runtime.work.handoffs import HandoffContextError, HandoffWriter, render_markdown
from craik.runtime.work.receipts import ReceiptStore
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


def test_handoff_writer_creates_structured_handoff(store: LocalStore, tmp_path: Path) -> None:
    task_id = _seed_case(store, tmp_path)
    receipt = _receipt(task_id)
    ReceiptStore(store).record_receipt(receipt)

    handoff = HandoffWriter(store).create(
        task_id=task_id,
        agent="agent:codex",
        summary="Completed docs review.",
        completed_actions=["Reviewed docs."],
        commands_run=["uv run pytest"],
        tests_run=["pytest"],
        next_steps=["Implement handoff reader."],
    )

    assert handoff.id == "handoff_review_docs"
    assert handoff.intent_lock_id == "intent_review_docs"
    assert handoff.receipt_ids == [receipt.id]
    assert handoff.self_audit.schema_validated is True
    assert handoff.self_audit.redaction_reviewed is True
    assert handoff.self_audit.receipts_reviewed is True
    assert handoff.self_audit.assumptions_reviewed is True
    assert handoff.self_audit.validation_recorded is True
    assert "GitHub state was not loaded" in handoff.context_debt[0]
    debt_records = store.list_context_debt_records()
    assert [record.summary for record in debt_records] == handoff.context_debt
    assert all(record.handoff_id == handoff.id for record in debt_records)
    assert store.get_handoff(handoff.id) == handoff
    exit_check = store.get_exit_discipline_check(f"exit_discipline_{task_id}")
    assert exit_check is not None
    assert exit_check.status == "complete"
    assert exit_check.handoff_id == handoff.id


def test_handoff_preserves_runner_metadata_from_receipts(
    store: LocalStore,
    tmp_path: Path,
) -> None:
    task_id = _seed_case(store, tmp_path)
    ReceiptStore(store).record_receipt(
        _receipt(
            task_id,
            metadata={
                "runner_metadata": {
                    "runner_id": "codex",
                    "adapter": "codex",
                    "adapter_version": "0.2.0-preview",
                    "execution_mode": "fixture",
                    "trust_profile": {"level": "medium"},
                    "runner_specific": {"api_token": "[REDACTED]"},
                },
            },
        )
    )

    handoff = HandoffWriter(store).create(
        task_id=task_id,
        agent="runner:codex",
        summary="Adapter completed.",
        tests_run=["pytest"],
    )
    markdown = render_markdown(handoff)

    assert handoff.runner_metadata == [
        {
            "runner_id": "codex",
            "adapter": "codex",
            "adapter_version": "0.2.0-preview",
            "execution_mode": "fixture",
            "trust_profile": {"level": "medium"},
            "runner_specific": {"api_token": "[REDACTED]"},
        }
    ]
    assert "## Runner Metadata" in markdown
    assert "- codex: adapter=codex; version=0.2.0-preview; mode=fixture; trust=medium" in markdown


def test_incomplete_handoff_records_missing_validation_and_policy_exception(
    store: LocalStore,
    tmp_path: Path,
) -> None:
    task_id = _seed_case(store, tmp_path)

    handoff = HandoffWriter(store).create(
        task_id=task_id,
        agent="agent:codex",
        summary="Blocked before validation.",
        status="incomplete",
        policy_exceptions=["No policy exception used."],
    )

    assert handoff.status == "incomplete"
    assert handoff.self_audit.validation_recorded is False
    assert handoff.policy_exceptions == ["No policy exception used."]
    exit_check = store.get_exit_discipline_check(f"exit_discipline_{task_id}")
    assert exit_check is not None
    assert exit_check.status == "blocked"
    assert "Validation was not recorded." in exit_check.blocking_reasons
    assert "Residual risks were not recorded." in exit_check.blocking_reasons
    assert "Next steps were not recorded." in exit_check.blocking_reasons


def test_markdown_handoff_is_deterministic(store: LocalStore, tmp_path: Path) -> None:
    task_id = _seed_case(store, tmp_path)
    handoff = HandoffWriter(store).create(
        task_id=task_id,
        agent="agent:codex",
        summary="Completed docs review.",
        completed_actions=["Reviewed docs."],
        tests_run=["pytest"],
        next_steps=["Continue with memory backend."],
    )

    markdown = render_markdown(handoff)

    assert markdown.startswith("# Handoff: task_review_docs\n")
    assert "- [x] Schema validated" in markdown
    assert "## Context Debt" in markdown
    assert "- Continue with memory backend." in markdown


@pytest.mark.parametrize(
    ("run_status", "handoff_status", "next_step"),
    [
        ("completed", "completed", "Review receipts, memory proposals, and merged handoff state."),
        ("blocked", "blocked", "Resolve the blocking approval, context, or intent-lock condition."),
        ("failed", "failed", "Inspect diagnostics and decide whether recovery is appropriate."),
        ("interrupted", "incomplete", "Inspect run state and recover from the last safe boundary."),
    ],
)
def test_handoff_writer_creates_run_outcome_handoffs(
    store: LocalStore,
    tmp_path: Path,
    run_status: TaskRunStatus,
    handoff_status: RunStatus,
    next_step: str,
) -> None:
    task_id = _seed_case(store, tmp_path)
    run = _task_run(task_id, status=run_status)
    output = _run_output(task_id, run.id, diagnostics=["runner [REDACTED]"])
    receipt = _receipt(task_id)
    store.put_task_run(run)
    store.put_run_output(output)
    ReceiptStore(store).record_receipt(receipt)

    handoff = HandoffWriter(store).create_from_run(run.id, tests_run=["pytest"])
    updated_run = store.get_task_run(run.id)

    assert handoff.status == handoff_status
    assert output.id in handoff.artifacts
    assert receipt.id in handoff.receipt_ids
    assert "memprop_docs_reconcile" in handoff.memory_proposal_ids
    assert handoff.runner_metadata == [{"runner_id": "runner_fixture", "execution_mode": "fixture"}]
    assert handoff.self_audit.receipts_reviewed is True
    assert "runner [REDACTED]" in handoff.self_audit.notes
    assert next_step in handoff.next_steps
    assert updated_run is not None
    assert updated_run.handoff_id == handoff.id
    assert "## Runner Metadata" in render_markdown(handoff)


def test_handoff_records_run_credential_and_operator_identity(
    store: LocalStore,
    tmp_path: Path,
) -> None:
    task_id = _seed_case(store, tmp_path)
    run = _task_run(task_id, status="completed")
    receipt = _receipt(
        task_id,
        receipt_id="receipt_reader",
        auth_profile_id="openai:reader",
        auth_identity_hash="reader-hash",
        operator_subject="operator-a",
        operator_issuer="https://issuer.example.test",
    )
    store.put_task_run(run)
    ReceiptStore(store).record_receipt(receipt)

    handoff = HandoffWriter(store).create_from_run(run.id, tests_run=["pytest"])
    updated_run = store.get_task_run(run.id)
    markdown = render_markdown(handoff)

    assert handoff.auth_profile_id == "openai:reader"
    assert handoff.auth_identity_hash == "reader-hash"
    assert handoff.operator_subject == "operator-a"
    assert handoff.operator_issuer == "https://issuer.example.test"
    assert updated_run is not None
    assert updated_run.auth_profile_id == "openai:reader"
    assert updated_run.operator_subject == "operator-a"
    assert "- Auth profile: openai:reader" in markdown
    assert "- Operator: https://issuer.example.test#operator-a" in markdown


def test_follow_up_handoff_keeps_distinct_credential_and_operator_identity(
    store: LocalStore,
    tmp_path: Path,
) -> None:
    first_task_id = _seed_case(store, tmp_path, title="Read docs")
    first_run = _task_run(first_task_id, status="completed")
    ReceiptStore(store).record_receipt(
        _receipt(
            first_task_id,
            receipt_id="receipt_reader",
            auth_profile_id="openai:reader",
            auth_identity_hash="reader-hash",
            operator_subject="operator-a",
            operator_issuer="https://issuer.example.test",
        )
    )
    store.put_task_run(first_run)
    first_handoff = HandoffWriter(store).create_from_run(first_run.id, tests_run=["pytest"])

    second_task_id = _seed_case(store, tmp_path, title="Write docs")
    second_run = _task_run(second_task_id, status="completed")
    ReceiptStore(store).record_receipt(
        _receipt(
            second_task_id,
            receipt_id="receipt_writer",
            auth_profile_id="openai:writer",
            auth_identity_hash="writer-hash",
            operator_subject="operator-b",
            operator_issuer="https://issuer.example.test",
        )
    )
    store.put_task_run(second_run)
    second_handoff = HandoffWriter(store).create_from_run(second_run.id, tests_run=["pytest"])
    stored_first = store.get_handoff(first_handoff.id)

    assert stored_first is not None
    assert stored_first.auth_profile_id == "openai:reader"
    assert stored_first.auth_identity_hash == "reader-hash"
    assert stored_first.operator_subject == "operator-a"
    assert second_handoff.auth_profile_id == "openai:writer"
    assert second_handoff.auth_identity_hash == "writer-hash"
    assert second_handoff.operator_subject == "operator-b"


def test_consume_handoff_creates_new_task_case_and_pending_run(
    store: LocalStore,
    tmp_path: Path,
) -> None:
    source_task_id = _seed_case(store, tmp_path)
    source_run = _task_run(source_task_id, status="completed")
    store.put_task_run(source_run.model_copy(update={"handoff_id": "handoff_review_docs"}))
    source_handoff = HandoffWriter(store).create(
        task_id=source_task_id,
        agent="agent:reader",
        summary="Reader finished review.",
        next_steps=["Patch stale installation docs."],
        tests_run=["pytest"],
    )

    result = consume_handoff(
        store,
        handoff_id_or_task_id=source_handoff.id,
        auth_profile_id="openai:writer",
        operator_subject="operator-b",
        operator_issuer="https://issuer.example.test",
        runner_id="codex",
        runner_mode="prompt-handoff",
    )

    assert result.source_handoff == source_handoff
    assert result.task.id == "task_continue_from_handoff_review_docs"
    assert result.task.source_handoff_id == source_handoff.id
    assert result.task.source_task_id == source_task_id
    assert result.task.source_run_id == source_run.id
    assert result.task.auth_profile_id == "openai:writer"
    assert result.task.operator_subject == "operator-b"
    assert "Source next step: Patch stale installation docs." in result.task.constraints
    assert result.case_file.task_id == result.task.id
    assert source_handoff.id in " ".join(result.case_file.recent_handoffs)
    assert result.run.status == "pending"
    assert result.run.runner_id == "codex"
    assert result.run.runner_mode == "prompt-handoff"
    assert result.run.source_handoff_id == source_handoff.id
    assert result.run.auth_profile_id == "openai:writer"
    assert result.run.operator_subject == "operator-b"
    assert result.run.receipt_ids
    identity_receipt = store.get_receipt(result.run.receipt_ids[0])
    assert identity_receipt is not None
    assert identity_receipt.capability == "handoff.identity.assign"
    assert identity_receipt.result.metadata["continued_producer_identity"] is False


def test_consume_handoff_requires_explicit_consumer_identity(
    store: LocalStore,
    tmp_path: Path,
) -> None:
    source_task_id = _seed_case(store, tmp_path)
    source_handoff = HandoffWriter(store).create(
        task_id=source_task_id,
        agent="agent:reader",
        summary="Reader finished review.",
        tests_run=["pytest"],
    )

    with pytest.raises(HandoffConsumptionError, match="requires --auth-profile-id"):
        consume_handoff(
            store,
            handoff_id_or_task_id=source_handoff.id,
            auth_profile_id="",
            operator_subject="operator-b",
            operator_issuer="https://issuer.example.test",
        )
    receipts = store.list_receipts()
    assert receipts[-1].capability == "handoff.identity.assign"
    assert receipts[-1].result.status == "denied"


def test_consume_handoff_denies_implicit_producer_identity_reuse(
    store: LocalStore,
    tmp_path: Path,
) -> None:
    source_task_id = _seed_case(store, tmp_path)
    source_handoff = HandoffWriter(store).create(
        task_id=source_task_id,
        agent="agent:reader",
        summary="Reader finished review.",
        tests_run=["pytest"],
        auth_profile_id="openai:reader",
        operator_subject="operator-a",
        operator_issuer="https://issuer.example.test",
    )

    with pytest.raises(HandoffConsumptionError, match="matches producer identity"):
        consume_handoff(
            store,
            handoff_id_or_task_id=source_handoff.id,
            auth_profile_id="openai:reader",
            operator_subject="operator-a",
            operator_issuer="https://issuer.example.test",
        )

    receipts = store.list_receipts()
    assert receipts[-1].result.status == "denied"
    assert receipts[-1].result.metadata["producer_auth_profile_id"] == "openai:reader"
    assert receipts[-1].result.metadata["consumer_auth_profile_id"] == "openai:reader"


def test_consume_handoff_allows_explicit_identity_continuation(
    store: LocalStore,
    tmp_path: Path,
) -> None:
    source_task_id = _seed_case(store, tmp_path)
    source_handoff = HandoffWriter(store).create(
        task_id=source_task_id,
        agent="agent:reader",
        summary="Reader finished review.",
        tests_run=["pytest"],
        auth_profile_id="openai:reader",
        operator_subject="operator-a",
        operator_issuer="https://issuer.example.test",
    )

    result = consume_handoff(
        store,
        handoff_id_or_task_id=source_handoff.id,
        auth_profile_id="openai:reader",
        operator_subject="operator-a",
        operator_issuer="https://issuer.example.test",
        allow_identity_continuation=True,
    )

    identity_receipt = store.get_receipt(result.run.receipt_ids[0])
    assert result.run.auth_profile_id == "openai:reader"
    assert result.run.operator_subject == "operator-a"
    assert identity_receipt is not None
    assert identity_receipt.result.status == "passed"
    assert identity_receipt.result.metadata["continued_producer_identity"] is True


def test_handoff_requires_existing_task(store: LocalStore) -> None:
    with pytest.raises(HandoffContextError, match="unknown task"):
        HandoffWriter(store).create(
            task_id="task_missing",
            agent="agent:codex",
            summary="No task.",
        )


def test_handoff_from_run_requires_existing_run(store: LocalStore) -> None:
    with pytest.raises(HandoffContextError, match="unknown task run"):
        HandoffWriter(store).create_from_run("run_missing")


def _seed_case(store: LocalStore, tmp_path: Path, *, title: str = "Review docs") -> str:
    repo = tmp_path / title.lower().replace(" ", "_")
    repo.mkdir()
    (repo / "README.md").write_text("# Repo\n")
    _run_git(repo, "init", "-b", "main")
    _run_git(repo, "add", "README.md")
    _run_git(repo, "commit", "-m", "initial")
    project = ProjectRegistry(store).add_project(repo, name="Example")
    task = create_task(
        store,
        title=title,
        objective="Review docs against implementation.",
        project_id=project.id,
        mode="review",
    )
    CaseFileAssembler(store).build(task.id)
    return task.id


def _task_run(task_id: str, *, status: TaskRunStatus) -> TaskRun:
    return TaskRun(
        id=f"run_{task_id.removeprefix('task_')}",
        task_id=task_id,
        case_file_id=f"case_{task_id.removeprefix('task_')}",
        policy_envelope_id=f"policy_{task_id.removeprefix('task_')}",
        intent_lock_id=f"intent_{task_id.removeprefix('task_')}",
        runner_id="runner_fixture",
        runner_mode="fixture",
        status=status,
        phase="stop",
        iteration=2,
        max_iterations=5,
        started_at=datetime(2026, 5, 16, 12, 0, tzinfo=UTC),
        phase_started_at=datetime(2026, 5, 16, 12, 1, tzinfo=UTC),
        updated_at=datetime(2026, 5, 16, 12, 2, tzinfo=UTC),
        ended_at=datetime(2026, 5, 16, 12, 2, tzinfo=UTC),
        stop_reason=f"run {status}",
        receipt_ids=["receipt_pytest"],
    )


def _run_output(task_id: str, run_id: str, diagnostics: list[str]) -> RunOutput:
    return RunOutput(
        id=f"runout_{task_id.removeprefix('task_')}",
        run_id=run_id,
        step_result_id="runner_step_result_docs_reconcile_plan",
        task_id=task_id,
        phase="evaluate",
        summary="Runner evaluated the task.",
        observed_output={"status": "done"},
        diagnostics=diagnostics,
        receipt_ids=["receipt_pytest"],
        memory_proposal_ids=["memprop_docs_reconcile"],
        artifacts=["case_docs_reconcile"],
        redacted=True,
        created_at=datetime(2026, 5, 16, 12, 2, tzinfo=UTC),
    )


def _receipt(
    task_id: str,
    metadata: dict[str, object] | None = None,
    *,
    receipt_id: str = "receipt_pytest",
    auth_profile_id: str | None = None,
    auth_identity_hash: str | None = None,
    operator_subject: str | None = None,
    operator_issuer: str | None = None,
) -> CapabilityReceipt:
    return CapabilityReceipt(
        id=receipt_id,
        task_id=task_id,
        actor="agent:codex",
        capability="shell.test",
        target="uv run pytest",
        policy_profile="strict",
        fail_open=False,
        reason="Validate handoff.",
        result=ReceiptResult(status="passed", summary="Tests passed.", metadata=metadata or {}),
        redacted=True,
        auth_profile_id=auth_profile_id,
        auth_identity_hash=auth_identity_hash,
        operator_subject=operator_subject,
        operator_issuer=operator_issuer,
        created_at=datetime(2026, 5, 15, 12, 0, tzinfo=UTC),
    )


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
