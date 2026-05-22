"""Persistent agent session state helpers."""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime

from craik.contracts.models import AgentSessionMode, AgentSessionState, AgentSessionStatus
from craik.runtime.store import LocalStore

ACTIVE_AGENT_SESSION_STATUSES = {"starting", "running", "idle", "stopping"}
RECOVERABLE_AGENT_SESSION_STATUSES = {
    "stopped",
    "failed",
    "auth_expired",
    "provider_unavailable",
    "sandbox_failed",
}


class AgentSessionLifecycleError(RuntimeError):
    """Raised when an agent session lifecycle transition is invalid."""


def agent_session_id(
    *,
    project_id: str | None,
    provider_id: str,
    now: datetime | None = None,
) -> str:
    """Return a stable, readable default id for a newly launched agent session."""
    timestamp = (now or datetime.now(UTC)).strftime("%Y%m%d%H%M%S")
    scope = _slug(project_id or "default")
    provider = _slug(provider_id)
    return f"agent_{scope}_{provider}_{timestamp}"


def get_agent_session_status(
    store: LocalStore,
    session_id: str,
    *,
    now: datetime | None = None,
) -> AgentSessionState:
    """Return one persisted session, marking stale pid-backed sessions failed."""
    state = store.get_agent_session_state(session_id)
    if state is None:
        raise AgentSessionLifecycleError(f"unknown agent session: {session_id}")
    if state.status in ACTIVE_AGENT_SESSION_STATUSES and _pid_is_stale(state.pid):
        from craik.runtime.agents.failure_recovery import mark_agent_session_failure

        return mark_agent_session_failure(
            store,
            state,
            reason="stale_pid",
            source="status",
            now=now,
        )
    if state.status in ACTIVE_AGENT_SESSION_STATUSES and _endpoint_state_is_stale(state):
        from craik.runtime.agents.failure_recovery import mark_agent_session_failure

        return mark_agent_session_failure(
            store,
            state,
            reason="stale_endpoint",
            source="status",
            now=now,
        )
    return state


def start_agent_session(
    store: LocalStore,
    *,
    session_id: str,
    operator_subject: str,
    provider_id: str,
    project_id: str | None = None,
    model_id: str | None = None,
    auth_profile_id: str | None = None,
    auth_identity_hash: str | None = None,
    operator_issuer: str | None = None,
    policy_envelope_id: str | None = None,
    active_task_id: str | None = None,
    active_run_id: str | None = None,
    mode: AgentSessionMode = "foreground",
    status: AgentSessionStatus = "running",
    pid: int | None = None,
    endpoint_url: str | None = None,
    now: datetime | None = None,
    replace_stopped: bool = False,
) -> AgentSessionState:
    """Create and persist the initial state for a launched persistent agent."""
    existing = store.get_agent_session_state(session_id)
    if existing is not None and (
        existing.status in ACTIVE_AGENT_SESSION_STATUSES or not replace_stopped
    ):
        raise AgentSessionLifecycleError(f"agent session already exists: {session_id}")
    timestamp = now or datetime.now(UTC)
    state = AgentSessionState(
        id=session_id,
        project_id=project_id,
        operator_subject=operator_subject,
        operator_issuer=operator_issuer,
        provider_id=provider_id,
        model_id=model_id,
        auth_profile_id=auth_profile_id,
        auth_identity_hash=auth_identity_hash,
        policy_envelope_id=policy_envelope_id,
        mode=mode,
        status=status,
        pid=pid,
        endpoint_url=endpoint_url,
        active_task_id=active_task_id,
        active_run_id=active_run_id,
        started_at=timestamp,
        last_activity_at=timestamp,
        updated_at=timestamp,
        supervision_notes=["Persistent agent session started."],
    )
    store.put_agent_session_state(state)
    return state


def stop_agent_session(
    store: LocalStore,
    session_id: str,
    *,
    supervision_note: str,
    now: datetime | None = None,
) -> AgentSessionState:
    """Stop an active persistent agent session."""
    state = get_agent_session_status(store, session_id, now=now)
    if state.status not in ACTIVE_AGENT_SESSION_STATUSES:
        raise AgentSessionLifecycleError(
            f"agent session {session_id} is {state.status}; only active sessions can be stopped"
        )
    return update_agent_session_status(
        store,
        state,
        status="stopped",
        supervision_note=supervision_note,
        now=now,
    )


def restart_agent_session(
    store: LocalStore,
    session_id: str,
    *,
    supervision_note: str,
    pid: int | None = None,
    endpoint_url: str | None = None,
    now: datetime | None = None,
) -> AgentSessionState:
    """Restart a stopped or failed persistent agent session."""
    state = get_agent_session_status(store, session_id, now=now)
    if state.status in ACTIVE_AGENT_SESSION_STATUSES:
        raise AgentSessionLifecycleError(
            f"agent session {session_id} is {state.status}; active sessions cannot be restarted"
        )
    if state.status not in RECOVERABLE_AGENT_SESSION_STATUSES:
        raise AgentSessionLifecycleError(
            f"agent session {session_id} is {state.status}; restart is not supported"
        )
    timestamp = now or datetime.now(UTC)
    notes = [*state.supervision_notes, supervision_note]
    updated = AgentSessionState.model_validate(
        {
            **state.model_dump(mode="json", by_alias=True),
            "status": "running",
            "pid": pid,
            "endpoint_url": endpoint_url if endpoint_url is not None else state.endpoint_url,
            "started_at": timestamp,
            "last_activity_at": timestamp,
            "stopped_at": None,
            "updated_at": timestamp,
            "supervision_notes": notes,
        }
    )
    store.put_agent_session_state(updated)
    return updated


def update_agent_session_status(
    store: LocalStore,
    state: AgentSessionState,
    *,
    status: AgentSessionStatus,
    supervision_note: str | None = None,
    now: datetime | None = None,
) -> AgentSessionState:
    """Persist a lifecycle transition for an existing persistent agent session."""
    timestamp = now or datetime.now(UTC)
    notes = list(state.supervision_notes)
    if supervision_note:
        notes.append(supervision_note)
    if status in {"failed", "auth_expired", "provider_unavailable", "sandbox_failed"} and not notes:
        notes.append(f"Persistent agent session entered {status}.")
    stopped_at = timestamp if status == "stopped" else state.stopped_at
    pid = state.pid if status in {"starting", "running", "idle", "stopping"} else None
    updated = AgentSessionState.model_validate(
        {
            **state.model_dump(mode="json", by_alias=True),
            "status": status,
            "pid": pid,
            "last_activity_at": timestamp,
            "stopped_at": stopped_at,
            "updated_at": timestamp,
            "supervision_notes": notes,
        }
    )
    store.put_agent_session_state(updated)
    return updated


def _pid_is_stale(pid: int | None) -> bool:
    if pid is None:
        return False
    if pid <= 0:
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False


def _endpoint_state_is_stale(state: AgentSessionState) -> bool:
    return state.mode == "background" and bool(state.endpoint_url) and state.pid is None


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()
    return slug or "default"


__all__ = [
    "ACTIVE_AGENT_SESSION_STATUSES",
    "AgentSessionLifecycleError",
    "agent_session_id",
    "get_agent_session_status",
    "restart_agent_session",
    "start_agent_session",
    "stop_agent_session",
    "update_agent_session_status",
]
