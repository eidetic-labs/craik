"""Structured persistent-session command implementations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from craik.runtime.contract import CommandResult
from craik.runtime.store import LocalStore


def session_list_result() -> CommandResult:
    """Return persistent agent sessions."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        sessions = [_session_payload(session) for session in store.list_agent_session_states()]
    finally:
        store.close()
    return CommandResult(payload=sessions, shape="card_list")


def session_show_result(session_id: str) -> CommandResult:
    """Return one persistent agent session."""
    session = _load_session(session_id)
    return CommandResult(payload=_session_payload(session), shape="card")


def session_resume_result(session_id: str) -> CommandResult:
    """Return resume guidance for one persistent session."""
    session = _load_session(session_id)
    return CommandResult(
        payload={
            "session_id": session.id,
            "status": session.status,
            "resume_supported": session.status in {"idle", "stopped", "auth_expired"},
            "next_action": f"craik session show {session.id}",
        },
        shape="kv",
    )


def session_rename_result(session_id: str, name: str) -> CommandResult:
    """Assign and return a display name for a persistent session."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        session = store.get_agent_session_state(session_id)
        if session is None:
            raise ValueError(f"unknown session: {session_id}")
        metadata = dict(session.recovery_metadata)
        metadata["name"] = name
        updated = session.model_copy(update={"recovery_metadata": metadata, "updated_at": _now()})
        store.put_agent_session_state(updated)
    finally:
        store.close()
    return CommandResult(payload=_session_payload(updated), shape="card")


def session_export_result(session_id: str) -> CommandResult:
    """Return one redacted persistent-session export payload."""
    session = _load_session(session_id)
    payload = _session_payload(session)
    payload["redacted"] = True
    return CommandResult(payload=payload, shape="card")


def session_prune_result() -> CommandResult:
    """Preview stopped-session pruning without deleting records."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        stopped = [
            session.id
            for session in store.list_agent_session_states()
            if session.status in {"stopped", "failed"}
        ]
    finally:
        store.close()
    return CommandResult(payload={"prunable": stopped, "deleted": []}, shape="kv")


def session_delete_result(session_id: str) -> CommandResult:
    """Mark a session as stopped; raw record deletion is intentionally unsupported."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        session = store.get_agent_session_state(session_id)
        if session is None:
            raise ValueError(f"unknown session: {session_id}")
        updated = session.model_copy(
            update={
                "status": "stopped",
                "stopped_at": _now(),
                "updated_at": _now(),
                "supervision_notes": [*session.supervision_notes, "marked stopped by CLI delete"],
            }
        )
        store.put_agent_session_state(updated)
    finally:
        store.close()
    return CommandResult(payload={"session_id": session_id, "marked_stopped": True}, shape="kv")


def _load_session(session_id: str) -> Any:
    store = LocalStore.from_env()
    try:
        store.initialize()
        session = store.get_agent_session_state(session_id)
    finally:
        store.close()
    if session is None:
        raise ValueError(f"unknown session: {session_id}")
    return session


def _now() -> datetime:
    return datetime.now(UTC)


def _session_payload(session: Any) -> dict[str, object]:
    return {
        "id": session.id,
        "name": session.recovery_metadata.get("name") if session.recovery_metadata else None,
        "project_id": session.project_id,
        "operator_subject": session.operator_subject,
        "provider_id": session.provider_id,
        "model_id": session.model_id,
        "status": session.status,
        "mode": session.mode,
        "active_task_id": session.active_task_id,
        "active_run_id": session.active_run_id,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "last_activity_at": session.last_activity_at.isoformat()
        if session.last_activity_at
        else None,
        "stopped_at": session.stopped_at.isoformat() if session.stopped_at else None,
        "receipt_ids": session.receipt_ids,
        "handoff_ids": session.handoff_ids,
        "redacted": True,
    }
