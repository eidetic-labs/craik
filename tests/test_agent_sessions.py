from datetime import UTC, datetime

import pytest

from craik.runtime.agents import sessions
from craik.runtime.agents.sessions import (
    AgentSessionLifecycleError,
    get_agent_session_status,
    restart_agent_session,
    start_agent_session,
    stop_agent_session,
    update_agent_session_status,
)
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
