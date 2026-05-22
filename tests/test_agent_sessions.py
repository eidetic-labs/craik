from datetime import UTC, datetime

from craik.runtime.agents.sessions import start_agent_session, update_agent_session_status
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
