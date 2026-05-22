"""Persistent agent failure recovery helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from craik.contracts.models import AgentSessionState, AgentSessionStatus
from craik.runtime.policy.redaction import redact
from craik.runtime.store import LocalStore

AgentSessionFailureReason = Literal[
    "stale_pid",
    "stale_endpoint",
    "auth_expired",
    "provider_unavailable",
    "sandbox_failed",
]
AgentSessionRecoveryAction = Literal["reconnect", "resume"]

FAILURE_STATUS_BY_REASON: dict[AgentSessionFailureReason, AgentSessionStatus] = {
    "stale_pid": "failed",
    "stale_endpoint": "failed",
    "auth_expired": "auth_expired",
    "provider_unavailable": "provider_unavailable",
    "sandbox_failed": "sandbox_failed",
}

RECOVERY_REASON_LABELS: dict[AgentSessionFailureReason, str] = {
    "stale_pid": "stale pid",
    "stale_endpoint": "stale endpoint",
    "auth_expired": "auth expired",
    "provider_unavailable": "provider unavailable",
    "sandbox_failed": "sandbox failed",
}


class AgentSessionRecoveryError(RuntimeError):
    """Raised when a persistent agent recovery transition is invalid."""


def mark_agent_session_failure(
    store: LocalStore,
    state: AgentSessionState,
    *,
    reason: AgentSessionFailureReason,
    detail: str | None = None,
    source: str = "runtime",
    metadata: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> AgentSessionState:
    """Persist a recoverable failure state with redacted operator metadata."""
    timestamp = now or datetime.now(UTC)
    status = FAILURE_STATUS_BY_REASON[reason]
    recovery_metadata = _failure_metadata(
        state,
        reason=reason,
        detail=detail,
        source=source,
        metadata=metadata,
        now=timestamp,
    )
    updated = AgentSessionState.model_validate(
        {
            **state.model_dump(mode="json", by_alias=True),
            "status": status,
            "pid": None,
            "last_activity_at": timestamp,
            "updated_at": timestamp,
            "recovery_metadata": {
                **state.recovery_metadata,
                **recovery_metadata,
            },
            "supervision_notes": [
                *state.supervision_notes,
                f"Persistent agent recovery required: {RECOVERY_REASON_LABELS[reason]}.",
            ],
        }
    )
    store.put_agent_session_state(updated)
    return updated


def mark_agent_session_failure_by_id(
    store: LocalStore,
    session_id: str,
    *,
    reason: AgentSessionFailureReason,
    detail: str | None = None,
    source: str = "runtime",
    metadata: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> AgentSessionState:
    """Load a session and mark it failed for recovery."""
    state = store.get_agent_session_state(session_id)
    if state is None:
        raise AgentSessionRecoveryError(f"unknown agent session: {session_id}")
    return mark_agent_session_failure(
        store,
        state,
        reason=reason,
        detail=detail,
        source=source,
        metadata=metadata,
        now=now,
    )


def recover_agent_session(
    store: LocalStore,
    state: AgentSessionState,
    *,
    action: AgentSessionRecoveryAction,
    supervision_note: str,
    pid: int | None = None,
    endpoint_url: str | None = None,
    now: datetime | None = None,
) -> AgentSessionState:
    """Represent an explicit reconnect or resume recovery transition."""
    if state.status not in {
        "stopped",
        "failed",
        "auth_expired",
        "provider_unavailable",
        "sandbox_failed",
    }:
        raise AgentSessionRecoveryError(
            f"agent session {state.id} is {state.status}; recovery action is not supported"
        )
    timestamp = now or datetime.now(UTC)
    status: AgentSessionStatus = "running" if action == "reconnect" else "idle"
    metadata = {
        **state.recovery_metadata,
        "recovery_action": action,
        "recovery_action_at": timestamp.isoformat(),
        "recovered_from_status": state.status,
    }
    updated = AgentSessionState.model_validate(
        {
            **state.model_dump(mode="json", by_alias=True),
            "status": status,
            "pid": pid,
            "endpoint_url": endpoint_url if endpoint_url is not None else state.endpoint_url,
            "started_at": timestamp if state.started_at is None else state.started_at,
            "last_activity_at": timestamp,
            "stopped_at": None,
            "updated_at": timestamp,
            "recovery_metadata": metadata,
            "supervision_notes": [*state.supervision_notes, supervision_note],
        }
    )
    store.put_agent_session_state(updated)
    return updated


def recover_agent_session_by_id(
    store: LocalStore,
    session_id: str,
    *,
    action: AgentSessionRecoveryAction,
    supervision_note: str,
    pid: int | None = None,
    endpoint_url: str | None = None,
    now: datetime | None = None,
) -> AgentSessionState:
    """Load a session and perform an explicit recovery action."""
    state = store.get_agent_session_state(session_id)
    if state is None:
        raise AgentSessionRecoveryError(f"unknown agent session: {session_id}")
    return recover_agent_session(
        store,
        state,
        action=action,
        supervision_note=supervision_note,
        pid=pid,
        endpoint_url=endpoint_url,
        now=now,
    )


def _failure_metadata(
    state: AgentSessionState,
    *,
    reason: AgentSessionFailureReason,
    detail: str | None,
    source: str,
    metadata: dict[str, Any] | None,
    now: datetime,
) -> dict[str, Any]:
    redacted_detail = redact(detail).value if detail is not None else None
    redacted_metadata = redact(metadata or {}).value
    return {
        "recovery_reason": reason,
        "recovery_status": FAILURE_STATUS_BY_REASON[reason],
        "recovery_source": source,
        "recovery_detected_at": now.isoformat(),
        "recovery_detail": redacted_detail,
        "recovery_context": redacted_metadata,
        "recoverable": True,
        "recommended_action": _recommended_action(reason),
        "provider_id": state.provider_id,
        "model_id": state.model_id,
        "project_id": state.project_id,
    }


def _recommended_action(reason: AgentSessionFailureReason) -> str:
    if reason == "auth_expired":
        return "reauthenticate provider credentials, then resume"
    if reason == "provider_unavailable":
        return "retry provider route or switch provider, then resume"
    if reason == "sandbox_failed":
        return "inspect sandbox policy/backend, then resume"
    return "reconnect session process, then resume"
