"""Structured persistent-session command implementations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from craik.runtime.contract import CommandResult
from craik.runtime.shell.session_settings import (
    active_session_id,
    save_active_session,
    shell_session_name,
)
from craik.runtime.store import LocalStore


def session_list_result(env: dict[str, str] | None = None) -> CommandResult:
    """Return persistent agent sessions."""
    store = LocalStore.from_env(env)
    try:
        store.initialize()
        sessions = [_session_payload(session) for session in store.list_agent_session_states()]
    finally:
        store.close()
    return CommandResult(payload=sessions, shape="card_list")


def session_shell_status_result(env: dict[str, str] | None = None) -> CommandResult:
    """Return shell-facing session status and active-session pointer."""
    result = session_list_result(env)
    sessions = result.payload if isinstance(result.payload, list) else []
    return CommandResult(
        payload={
            "active_session": active_session_id(env),
            "shell_session_name": shell_session_name(env),
            "count": len(sessions),
            "sessions": sessions,
        },
        shape="table",
    )


def session_activate_result(
    session_id: str,
    *,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Set the active shell session pointer."""
    sessions = session_list_result(env).payload
    if isinstance(sessions, list) and sessions:
        if not any(item.get("id") == session_id for item in sessions if isinstance(item, dict)):
            raise ValueError(f"unknown session: {session_id}")
    save_active_session(session_id, env)
    return CommandResult(
        payload={"active_session": session_id},
        shape="kv",
        text=f"Active session set to `{session_id}`.",
    )


def session_show_result(session_id: str, env: dict[str, str] | None = None) -> CommandResult:
    """Return one persistent agent session."""
    session = _load_session(session_id, env)
    return CommandResult(payload=_session_payload(session), shape="card")


def session_resume_result(
    session_id: str,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Return resume guidance for one persistent session."""
    session = _load_session(session_id, env)
    return CommandResult(
        payload={
            "session_id": session.id,
            "status": session.status,
            "resume_supported": session.status in {"idle", "stopped", "auth_expired"},
            "next_action": f"craik session show {session.id}",
        },
        shape="kv",
    )


def session_rename_result(
    session_id: str,
    name: str,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Assign and return a display name for a persistent session."""
    store = LocalStore.from_env(env)
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


def session_export_result(session_id: str, env: dict[str, str] | None = None) -> CommandResult:
    """Return one redacted persistent-session export payload."""
    session = _load_session(session_id, env)
    payload = _session_payload(session)
    payload["redacted"] = True
    return CommandResult(payload=payload, shape="card")


def session_prune_result(env: dict[str, str] | None = None) -> CommandResult:
    """Preview stopped-session pruning without deleting records."""
    store = LocalStore.from_env(env)
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


def session_delete_result(
    session_id: str,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Mark a session as stopped; raw record deletion is intentionally unsupported."""
    store = LocalStore.from_env(env)
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


def _load_session(session_id: str, env: dict[str, str] | None = None) -> Any:
    store = LocalStore.from_env(env)
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
