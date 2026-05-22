"""Provider-backed prompt execution for persistent agent sessions."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from craik.contracts.models import (
    AgentSessionEvent,
    AgentSessionState,
    CapabilityGrant,
    CapabilityTarget,
)
from craik.runtime.agents.sessions import (
    ACTIVE_AGENT_SESSION_STATUSES,
    AgentSessionLifecycleError,
)
from craik.runtime.providers.provider_runner import (
    ProviderBackedRunExecutor,
    ProviderBackedRunResult,
)
from craik.runtime.store import LocalStore
from craik.runtime.work.tasks import create_task

EXIT_PROMPTS = {"/exit", "exit", "quit", "/quit"}


@dataclass(frozen=True)
class AgentPromptResult:
    """Result of one provider-backed persistent agent prompt."""

    session: AgentSessionState
    events: list[AgentSessionEvent]
    task_id: str | None = None
    run_result: ProviderBackedRunResult | None = None
    exit_behavior: str = "completed"


def execute_agent_prompt(
    store: LocalStore,
    *,
    session_id: str,
    operator_subject: str,
    operator_issuer: str | None,
    prompt: str,
    allow_fixture_action: bool = True,
    max_iterations: int = 5,
    provider_token_budget: int | None = None,
    now: datetime | None = None,
) -> AgentPromptResult:
    """Execute one prompt through the session's provider-backed run path."""
    timestamp = now or datetime.now(UTC)
    state = _require_promptable_session(
        store,
        session_id=session_id,
        operator_subject=operator_subject,
        operator_issuer=operator_issuer,
    )
    normalized_prompt = prompt.strip()
    if not normalized_prompt:
        raise AgentSessionLifecycleError("agent prompt cannot be empty")
    if normalized_prompt.lower() in EXIT_PROMPTS:
        event = record_agent_session_event(
            store,
            state,
            event_type="exited",
            metadata={"exit_command": normalized_prompt},
            now=timestamp,
        )
        stopped = _update_session_links(
            store,
            state,
            status="stopped",
            recovery_metadata={"exit_behavior": "operator_exit"},
            note="Persistent agent prompt loop exited by operator.",
            now=timestamp,
        )
        return AgentPromptResult(
            session=stopped,
            events=[event],
            exit_behavior="operator_exit",
        )
    project_id = state.project_id
    if project_id is None:
        raise AgentSessionLifecycleError(
            f"agent session {session_id} has no project_id; prompt execution requires a project"
        )
    task = create_task(
        store,
        title=_prompt_task_title(state, normalized_prompt, timestamp),
        objective=normalized_prompt,
        project_id=project_id,
        requested_by=f"operator:{operator_subject}",
        mode="implement",
        auth_profile_id=state.auth_profile_id,
        operator_subject=operator_subject,
        operator_issuer=operator_issuer,
        expected_outputs=["runner_step_result", "handoff"],
    )
    prompt_event = record_agent_session_event(
        store,
        state,
        event_type="prompt_received",
        task_id=task.id,
        metadata={"prompt_hash": _prompt_hash(normalized_prompt)},
        now=timestamp,
    )
    running = _update_session_links(
        store,
        state,
        status="running",
        active_task_id=task.id,
        note="Persistent agent prompt received.",
        now=timestamp,
    )
    result = ProviderBackedRunExecutor(store).execute(
        task_id=task.id,
        provider_id=running.provider_id,
        grants=[_fixture_shell_grant(task.id)] if allow_fixture_action else [],
        max_iterations=max_iterations,
        provider_token_budget=provider_token_budget,
        started_at=timestamp,
    )
    receipt_ids = _receipt_ids(result)
    exit_behavior = "interrupted" if result.interrupted_error else result.run.status
    metadata: dict[str, Any] = {"run_status": result.run.status}
    recovery_metadata: dict[str, Any] = {
        "exit_behavior": exit_behavior,
        "handoff_id": result.handoff.id,
    }
    if result.interrupted_error:
        metadata["interrupted_error"] = result.interrupted_error
        recovery_metadata["interrupted_error"] = result.interrupted_error
    run_event = record_agent_session_event(
        store,
        running,
        event_type="run_interrupted" if result.interrupted_error else "run_completed",
        task_id=task.id,
        run_id=result.run.id,
        handoff_id=result.handoff.id,
        receipt_ids=receipt_ids,
        recovery_metadata=recovery_metadata,
        metadata=metadata,
        now=datetime.now(UTC),
    )
    updated = _update_session_links(
        store,
        running,
        status="idle",
        active_task_id=task.id,
        active_run_id=result.run.id,
        receipt_ids=receipt_ids,
        handoff_ids=[result.handoff.id],
        recovery_metadata=recovery_metadata,
        note=f"Persistent agent prompt finished with {exit_behavior}.",
        now=datetime.now(UTC),
    )
    return AgentPromptResult(
        session=updated,
        events=[prompt_event, run_event],
        task_id=task.id,
        run_result=result,
        exit_behavior=exit_behavior,
    )


def record_agent_session_event(
    store: LocalStore,
    state: AgentSessionState,
    *,
    event_type: str,
    task_id: str | None = None,
    run_id: str | None = None,
    handoff_id: str | None = None,
    receipt_ids: list[str] | None = None,
    recovery_metadata: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> AgentSessionEvent:
    """Persist one redacted event for a persistent agent session."""
    timestamp = now or datetime.now(UTC)
    event = AgentSessionEvent(
        id=_event_id(state.id, event_type, timestamp),
        session_id=state.id,
        event_type=event_type,
        operator_subject=state.operator_subject,
        operator_issuer=state.operator_issuer,
        project_id=state.project_id,
        provider_id=state.provider_id,
        model_id=state.model_id,
        policy_envelope_id=state.policy_envelope_id,
        task_id=task_id,
        run_id=run_id,
        handoff_id=handoff_id,
        receipt_ids=receipt_ids or [],
        recovery_metadata=recovery_metadata or {},
        metadata=metadata or {},
        created_at=timestamp,
    )
    store.put_agent_session_event(event)
    return event


def _require_promptable_session(
    store: LocalStore,
    *,
    session_id: str,
    operator_subject: str,
    operator_issuer: str | None,
) -> AgentSessionState:
    state = store.get_agent_session_state(session_id)
    if state is None:
        raise AgentSessionLifecycleError(f"unknown agent session: {session_id}")
    if state.status not in ACTIVE_AGENT_SESSION_STATUSES:
        raise AgentSessionLifecycleError(
            f"agent session {session_id} is {state.status}; only active sessions accept prompts"
        )
    if state.operator_subject != operator_subject or state.operator_issuer != operator_issuer:
        raise AgentSessionLifecycleError(
            "agent session operator does not match the active operator session"
        )
    return state


def _update_session_links(
    store: LocalStore,
    state: AgentSessionState,
    *,
    status: str,
    active_task_id: str | None = None,
    active_run_id: str | None = None,
    receipt_ids: list[str] | None = None,
    handoff_ids: list[str] | None = None,
    recovery_metadata: dict[str, Any] | None = None,
    note: str | None = None,
    now: datetime | None = None,
) -> AgentSessionState:
    timestamp = now or datetime.now(UTC)
    notes = [*state.supervision_notes, *([note] if note else [])]
    updated = AgentSessionState.model_validate(
        {
            **state.model_dump(mode="json", by_alias=True),
            "status": status,
            "active_task_id": active_task_id or state.active_task_id,
            "active_run_id": active_run_id or state.active_run_id,
            "receipt_ids": sorted({*state.receipt_ids, *(receipt_ids or [])}),
            "handoff_ids": sorted({*state.handoff_ids, *(handoff_ids or [])}),
            "recovery_metadata": {
                **state.recovery_metadata,
                **(recovery_metadata or {}),
            },
            "supervision_notes": notes,
            "last_activity_at": timestamp,
            "stopped_at": timestamp if status == "stopped" else state.stopped_at,
            "updated_at": timestamp,
        }
    )
    store.put_agent_session_state(updated)
    return updated


def _fixture_shell_grant(task_id: str) -> CapabilityGrant:
    return CapabilityGrant(
        id=f"grant_{task_id.removeprefix('task_')}_agent_prompt_fixture_shell",
        task_id=task_id,
        capability="shell.execute",
        target=CapabilityTarget(paths=["fixture-action"]),
        operations=["execute"],
        reason="Allow the persistent agent deterministic fixture action.",
        approved_by="user:local-operator",
    )


def _receipt_ids(result: ProviderBackedRunResult) -> list[str]:
    output_receipts = {
        receipt_id
        for output in (result.loop.output_captures if result.loop else [])
        for receipt_id in output.output.receipt_ids
    }
    return sorted(output_receipts | set(result.run.receipt_ids) | set(result.handoff.receipt_ids))


def _prompt_task_title(state: AgentSessionState, prompt: str, timestamp: datetime) -> str:
    digest = _prompt_hash(prompt)
    return f"Agent {state.id} prompt {timestamp:%Y%m%d%H%M%S} {digest}"


def _prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]


def _event_id(session_id: str, event_type: str, timestamp: datetime) -> str:
    raw = f"{session_id}:{event_type}:{timestamp.isoformat()}".encode()
    return f"agent_event_{hashlib.sha256(raw).hexdigest()[:24]}"
