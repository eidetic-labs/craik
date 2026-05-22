import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from craik.runtime.agents import sessions
from craik.runtime.agents.prompt_loop import execute_agent_prompt
from craik.runtime.agents.sessions import (
    AgentSessionLifecycleError,
    get_agent_session_status,
    restart_agent_session,
    start_agent_session,
    stop_agent_session,
    update_agent_session_status,
)
from craik.runtime.projects.project_registry import ProjectRegistry
from craik.runtime.store import LocalStore


def test_start_agent_session_persists_redacted_provider_state(tmp_path) -> None:
    store = LocalStore(tmp_path / "craik.sqlite3")
    store.initialize()
    now = datetime(2026, 5, 22, 6, 15, tzinfo=UTC)

    try:
        state = start_agent_session(
            store,
            session_id="agent_session_docs",
            project_id="project_docs",
            operator_subject="operator-123",
            operator_issuer="https://issuer.example.test",
            provider_id="provider_openai",
            model_id="gpt-5.2",
            auth_profile_id="openai:work",
            auth_identity_hash="auth-hash",
            policy_envelope_id="policy_docs",
            active_task_id="task_docs",
            active_run_id="run_docs",
            pid=4321,
            endpoint_url="http://127.0.0.1:8766",
            now=now,
        )

        stored = store.get_agent_session_state(state.id)
        assert stored is not None
        assert stored == state
        assert stored.status == "running"
        assert stored.redacted is True
        assert stored.auth_identity_hash == "auth-hash"
    finally:
        store.close()


def test_update_agent_session_status_clears_pid_when_stopped(tmp_path) -> None:
    store = LocalStore(tmp_path / "craik.sqlite3")
    store.initialize()
    started_at = datetime(2026, 5, 22, 6, 15, tzinfo=UTC)
    stopped_at = datetime(2026, 5, 22, 6, 20, tzinfo=UTC)

    try:
        state = start_agent_session(
            store,
            session_id="agent_session_docs",
            operator_subject="operator-123",
            provider_id="provider_openai",
            pid=4321,
            now=started_at,
        )

        stopped = update_agent_session_status(
            store,
            state,
            status="stopped",
            supervision_note="Operator stopped the session.",
            now=stopped_at,
        )

        assert stopped.pid is None
        assert stopped.stopped_at == stopped_at
        assert stopped.supervision_notes[-1] == "Operator stopped the session."
        assert store.get_agent_session_state(state.id) == stopped
    finally:
        store.close()


def test_stop_and_restart_agent_session_enforce_lifecycle(tmp_path) -> None:
    store = LocalStore(tmp_path / "craik.sqlite3")
    store.initialize()
    started_at = datetime(2026, 5, 22, 6, 15, tzinfo=UTC)
    stopped_at = datetime(2026, 5, 22, 6, 20, tzinfo=UTC)
    restarted_at = datetime(2026, 5, 22, 6, 25, tzinfo=UTC)

    try:
        start_agent_session(
            store,
            session_id="agent_session_docs",
            operator_subject="operator-123",
            provider_id="provider_openai",
            now=started_at,
        )

        stopped = stop_agent_session(
            store,
            "agent_session_docs",
            supervision_note="Operator stopped the session.",
            now=stopped_at,
        )
        restarted = restart_agent_session(
            store,
            "agent_session_docs",
            supervision_note="Operator restarted the session.",
            now=restarted_at,
        )

        assert stopped.status == "stopped"
        assert restarted.status == "running"
        assert restarted.stopped_at is None
        assert restarted.started_at == restarted_at
        assert restarted.supervision_notes[-1] == "Operator restarted the session."
        with pytest.raises(AgentSessionLifecycleError, match="active sessions cannot be restarted"):
            restart_agent_session(
                store,
                "agent_session_docs",
                supervision_note="Invalid restart.",
                now=restarted_at,
            )
    finally:
        store.close()


def test_status_marks_stale_pid_session_failed(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = LocalStore(tmp_path / "craik.sqlite3")
    store.initialize()
    started_at = datetime(2026, 5, 22, 6, 15, tzinfo=UTC)
    checked_at = datetime(2026, 5, 22, 6, 16, tzinfo=UTC)

    def missing_process(pid: int, signal: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(sessions.os, "kill", missing_process)
    try:
        start_agent_session(
            store,
            session_id="agent_session_docs",
            operator_subject="operator-123",
            provider_id="provider_openai",
            pid=4321,
            now=started_at,
        )

        failed = get_agent_session_status(store, "agent_session_docs", now=checked_at)

        assert failed.status == "failed"
        assert failed.pid is None
        assert failed.supervision_notes[-1] == "Persistent agent pid is no longer running."
    finally:
        store.close()


def test_agent_prompt_persists_events_receipts_handoff_and_links(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "craik.sqlite3")
    store.initialize()
    project_id = _seed_project(store, tmp_path)
    started_at = datetime(2026, 5, 22, 6, 15, tzinfo=UTC)

    try:
        start_agent_session(
            store,
            session_id="agent_session_docs",
            project_id=project_id,
            operator_subject="operator-123",
            operator_issuer="https://issuer.example.test",
            provider_id="provider_openai",
            model_id="gpt-5.2",
            policy_envelope_id="policy_docs",
            now=started_at,
        )

        result = execute_agent_prompt(
            store,
            session_id="agent_session_docs",
            operator_subject="operator-123",
            operator_issuer="https://issuer.example.test",
            prompt="Implement the next bounded provider task.",
            now=started_at,
        )

        events = store.list_agent_session_events()
        stored = store.get_agent_session_state("agent_session_docs")
        assert result.exit_behavior == "completed"
        assert stored is not None
        assert stored.status == "idle"
        assert stored.active_task_id == result.task_id
        assert stored.active_run_id == result.run_result.run.id
        assert result.run_result.handoff.id in stored.handoff_ids
        assert set(result.run_result.run.receipt_ids).issubset(stored.receipt_ids)
        assert [event.event_type for event in result.events] == [
            "prompt_received",
            "run_completed",
        ]
        assert {event.id for event in result.events}.issubset({event.id for event in events})
        assert result.events[1].run_id == result.run_result.run.id
        assert result.events[1].handoff_id == result.run_result.handoff.id
    finally:
        store.close()


def test_agent_prompt_records_interruption_recovery_metadata(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "craik.sqlite3")
    store.initialize()
    project_id = _seed_project(store, tmp_path)

    try:
        start_agent_session(
            store,
            session_id="agent_session_docs",
            project_id=project_id,
            operator_subject="operator-123",
            operator_issuer="https://issuer.example.test",
            provider_id="provider_openai",
        )

        result = execute_agent_prompt(
            store,
            session_id="agent_session_docs",
            operator_subject="operator-123",
            operator_issuer="https://issuer.example.test",
            prompt="Start work but interrupt quickly.",
            max_iterations=1,
        )

        stored = store.get_agent_session_state("agent_session_docs")
        assert result.exit_behavior == "interrupted"
        assert stored is not None
        assert stored.status == "idle"
        assert stored.recovery_metadata["exit_behavior"] == "interrupted"
        assert stored.recovery_metadata["interrupted_error"] == "max iterations 1 reached"
        assert result.events[1].event_type == "run_interrupted"
    finally:
        store.close()


def test_agent_prompt_exit_stops_session_without_run(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "craik.sqlite3")
    store.initialize()
    project_id = _seed_project(store, tmp_path)

    try:
        start_agent_session(
            store,
            session_id="agent_session_docs",
            project_id=project_id,
            operator_subject="operator-123",
            operator_issuer="https://issuer.example.test",
            provider_id="provider_openai",
        )

        result = execute_agent_prompt(
            store,
            session_id="agent_session_docs",
            operator_subject="operator-123",
            operator_issuer="https://issuer.example.test",
            prompt="/exit",
        )

        assert result.exit_behavior == "operator_exit"
        assert result.run_result is None
        assert result.session.status == "stopped"
        assert result.events[0].event_type == "exited"
    finally:
        store.close()


def test_agent_prompt_rejects_operator_mismatch(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "craik.sqlite3")
    store.initialize()
    project_id = _seed_project(store, tmp_path)

    try:
        start_agent_session(
            store,
            session_id="agent_session_docs",
            project_id=project_id,
            operator_subject="operator-123",
            operator_issuer="https://issuer.example.test",
            provider_id="provider_openai",
        )

        with pytest.raises(AgentSessionLifecycleError, match="operator does not match"):
            execute_agent_prompt(
                store,
                session_id="agent_session_docs",
                operator_subject="operator-456",
                operator_issuer="https://issuer.example.test",
                prompt="Try to drive another operator session.",
            )
    finally:
        store.close()


def _seed_project(store: LocalStore, tmp_path: Path) -> str:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Repo\n")
    _run_git(repo, "init", "-b", "main")
    _run_git(repo, "add", "README.md")
    _run_git(repo, "commit", "-m", "initial")
    return ProjectRegistry(store).add_project(repo, name="Example").id


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
