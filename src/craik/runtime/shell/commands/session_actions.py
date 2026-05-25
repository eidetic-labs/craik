"""Shared session-action command results."""

from __future__ import annotations

import hashlib
import os
import re
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from craik.contracts.models import AgentSessionEvent, AgentSessionState
from craik.runtime.auth.operator import OperatorSessionNotFoundError, OperatorSessionStore
from craik.runtime.contract import CommandResult, NextAction
from craik.runtime.paths import resolve_craik_paths
from craik.runtime.policy.text import sanitize_runtime_text
from craik.runtime.shell.session_settings import active_session_id, save_active_session
from craik.runtime.store import LocalStore

ATTACHMENT_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_SESSION_ID = "shell"
DEFAULT_OPERATOR = "local:unauthenticated"


def note_result(text: str, env: dict[str, str] | None = None) -> CommandResult:
    """Persist an operator note as a durable session event."""
    cleaned = sanitize_runtime_text(text.strip())
    if not cleaned:
        raise ValueError("note requires non-empty text")
    now = _now()
    session_id = _current_session_id(env)
    operator = _operator_identity(env)
    event = AgentSessionEvent(
        id=_event_id("note", session_id, cleaned),
        session_id=session_id,
        event_type="operator.note",
        operator_subject=operator["subject"] or DEFAULT_OPERATOR,
        operator_issuer=operator["issuer"],
        metadata={"text": cleaned},
        created_at=now,
    )
    _put_event(event, env)
    return CommandResult(
        payload={
            "session_id": session_id,
            "event_id": event.id,
            "event_type": event.event_type,
            "text": cleaned,
        },
        shape="kv",
        text=f"Note added to session `{session_id}`.",
    )


def fork_result(env: dict[str, str] | None = None) -> CommandResult:
    """Create a persistent fork of the active session and make it active."""
    now = _now()
    source_id = active_session_id(env) or DEFAULT_SESSION_ID
    fork_id = _fork_session_id(source_id)
    operator = _operator_identity(env)
    store = LocalStore.from_env(env)
    try:
        store.initialize()
        source = store.get_agent_session_state(source_id)
        state = _fork_state(source, fork_id, source_id, operator, now)
        store.put_agent_session_state(state)
        store.put_agent_session_event(
            AgentSessionEvent(
                id=_event_id("fork", source_id, fork_id),
                session_id=fork_id,
                event_type="session.forked",
                operator_subject=operator["subject"] or DEFAULT_OPERATOR,
                operator_issuer=operator["issuer"],
                project_id=state.project_id,
                provider_id=state.provider_id,
                model_id=state.model_id,
                policy_envelope_id=state.policy_envelope_id,
                task_id=state.active_task_id,
                run_id=state.active_run_id,
                recovery_metadata={"forked_from": source_id},
                created_at=now,
            )
        )
    finally:
        store.close()
    save_active_session(fork_id, env)
    return CommandResult(
        payload={
            "source_session": source_id,
            "fork_session": fork_id,
            "active_session": fork_id,
        },
        shape="kv",
        text=f"Forked `{source_id}` to `{fork_id}` and made it active.",
        next_actions=[
            NextAction(
                text="Show active sessions",
                command="/sessions",
                field="active_session",
            )
        ],
    )


def attach_result(path: str, env: dict[str, str] | None = None) -> CommandResult:
    """Attach a local file reference to the active session context."""
    if not path.strip():
        raise ValueError("attach requires a path")
    resolved = _resolve_attachment_path(path, env)
    if not resolved.is_file():
        raise ValueError(f"attachment path is not a file: {path}")
    size = resolved.stat().st_size
    if size > ATTACHMENT_MAX_BYTES:
        raise ValueError("attachment exceeds the 10 MiB per-file cap")
    digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
    session_id = _current_session_id(env)
    operator = _operator_identity(env)
    event = AgentSessionEvent(
        id=_event_id("attach", session_id, str(resolved), digest),
        session_id=session_id,
        event_type="context.attachment",
        operator_subject=operator["subject"] or DEFAULT_OPERATOR,
        operator_issuer=operator["issuer"],
        metadata={
            "path": str(resolved),
            "name": resolved.name,
            "size_bytes": size,
            "sha256": digest,
        },
        created_at=_now(),
    )
    _put_event(event, env)
    return CommandResult(
        payload={
            "session_id": session_id,
            "event_id": event.id,
            "name": resolved.name,
            "size_bytes": size,
            "sha256": digest,
        },
        shape="kv",
        text=f"Attached `{resolved.name}` to session `{session_id}` ({size} bytes).",
    )


def redo_result(env: dict[str, str] | None = None) -> CommandResult:
    """Record a redo request for the latest replayable provider turn."""
    session_id = _current_session_id(env)
    events = _session_events(session_id, env)
    replayable = _latest_replayable_event(events)
    if replayable is None:
        return CommandResult(
            payload={
                "session_id": session_id,
                "redo_supported": False,
                "reason": "no replayable agent turn found",
            },
            shape="kv",
            text=f"No replayable agent turn found for session `{session_id}`.",
            exit_code=2,
        )
    operator = _operator_identity(env)
    event = AgentSessionEvent(
        id=_event_id("redo", session_id, replayable.id),
        session_id=session_id,
        event_type="agent.redo_requested",
        operator_subject=operator["subject"] or DEFAULT_OPERATOR,
        operator_issuer=operator["issuer"],
        task_id=replayable.task_id,
        run_id=replayable.run_id,
        recovery_metadata={"replay_event_id": replayable.id},
        created_at=_now(),
    )
    _put_event(event, env)
    return CommandResult(
        payload={
            "session_id": session_id,
            "redo_supported": True,
            "replay_event_id": replayable.id,
            "event_id": event.id,
        },
        shape="kv",
        text=f"Redo requested for event `{replayable.id}` in session `{session_id}`.",
    )


def _fork_state(
    source: AgentSessionState | None,
    fork_id: str,
    source_id: str,
    operator: dict[str, str | None],
    now: datetime,
) -> AgentSessionState:
    if source is None:
        return AgentSessionState(
            id=fork_id,
            display_name=f"Fork of {source_id}",
            operator_subject=operator["subject"] or DEFAULT_OPERATOR,
            operator_issuer=operator["issuer"],
            provider_id="provider_unselected",
            status="idle",
            started_at=now,
            updated_at=now,
            recovery_metadata={"forked_from": source_id},
            supervision_notes=["Session fork created from shell context."],
        )
    metadata = dict(source.recovery_metadata)
    metadata["forked_from"] = source.id
    return source.model_copy(
        update={
            "id": fork_id,
            "display_name": f"Fork of {source.display_name or source.id}",
            "status": "idle",
            "pid": None,
            "started_at": source.started_at or now,
            "last_activity_at": now,
            "stopped_at": None,
            "updated_at": now,
            "recovery_metadata": metadata,
            "supervision_notes": [
                *source.supervision_notes,
                f"Forked from {source.id}.",
            ],
            "receipt_hmac": None,
        }
    )


def _put_event(event: AgentSessionEvent, env: dict[str, str] | None) -> None:
    store = LocalStore.from_env(env)
    try:
        store.initialize()
        store.put_agent_session_event(event)
    finally:
        store.close()


def _session_events(
    session_id: str,
    env: dict[str, str] | None,
) -> list[AgentSessionEvent]:
    store = LocalStore.from_env(env)
    try:
        store.initialize()
        return [
            event
            for event in store.list_agent_session_events()
            if event.session_id == session_id
        ]
    finally:
        store.close()


def _latest_replayable_event(events: list[AgentSessionEvent]) -> AgentSessionEvent | None:
    replayable = [
        event
        for event in events
        if event.event_type in {"agent.turn", "provider.response", "agent.response"}
    ]
    if not replayable:
        return None
    return sorted(replayable, key=lambda event: (event.created_at, event.id))[-1]


def _current_session_id(env: dict[str, str] | None) -> str:
    return active_session_id(env) or DEFAULT_SESSION_ID


def _operator_identity(env: dict[str, str] | None) -> dict[str, str | None]:
    try:
        session = OperatorSessionStore.from_env(env).get()
    except OperatorSessionNotFoundError:
        return {"subject": DEFAULT_OPERATOR, "issuer": None}
    return {"subject": session.subject, "issuer": session.issuer}


def _resolve_attachment_path(path: str, env: dict[str, str] | None) -> Path:
    requested = _requested_relative_path(path)
    base_path = resolve_craik_paths(env).home
    base = os.path.realpath(base_path)
    for candidate in base_path.rglob("*"):
        if not candidate.is_file():
            continue
        resolved = os.path.realpath(candidate)
        if os.path.commonpath([base, resolved]) != base:
            continue
        relative = Path(resolved).relative_to(base).as_posix()
        if relative == requested:
            return Path(resolved)
    raise ValueError(f"attachment path is not a file: {path}")


def _requested_relative_path(path: str) -> str:
    expanded = os.path.expanduser(path.strip())
    if os.path.isabs(expanded):
        raise ValueError("attachment path must stay within CRAIK_HOME")
    normalized = PurePosixPath(expanded.replace(os.sep, "/"))
    if normalized.is_absolute() or any(part in {"", ".", ".."} for part in normalized.parts):
        raise ValueError("attachment path must stay within CRAIK_HOME")
    return normalized.as_posix()


def _event_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _fork_session_id(source_id: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", source_id).strip("_").lower() or "shell"
    return f"{slug}_fork"


def _now() -> datetime:
    return datetime.now(UTC)
