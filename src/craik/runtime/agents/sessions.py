"""Persistent agent session state helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from craik.contracts.models import AgentSessionState, AgentSessionStatus
from craik.runtime.store import LocalStore


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
    pid: int | None = None,
    endpoint_url: str | None = None,
    now: datetime | None = None,
) -> AgentSessionState:
    """Create and persist the initial state for a launched persistent agent."""
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
        mode="interactive",
        status="running",
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


__all__ = ["start_agent_session", "update_agent_session_status"]
