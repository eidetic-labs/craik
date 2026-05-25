"""CommandResult helpers for handoff CLI and slash-command surfaces."""

from __future__ import annotations

from craik.contracts.models import RunStatus
from craik.runtime.companions.handoff_markdown import render_markdown
from craik.runtime.contract import CommandResult
from craik.runtime.paths import resolve_craik_paths
from craik.runtime.store import LocalStore
from craik.runtime.work.handoffs import (
    HandoffBlockedByExitDisciplineError,
    HandoffContextError,
    HandoffNotFoundError,
    HandoffWriter,
)


def handoff_list_result(env: dict[str, str] | None = None) -> CommandResult:
    """Return persisted handoffs."""
    store = LocalStore.from_paths(resolve_craik_paths(env))
    try:
        store.initialize()
        handoffs = store.list_handoffs()
    finally:
        store.close()
    return CommandResult(
        payload={
            "count": len(handoffs),
            "handoffs": [handoff.model_dump(mode="json", by_alias=True) for handoff in handoffs],
        },
        shape="card_list",
        empty_state_message="No handoffs found.",
    )


def handoff_create_result(
    *,
    task_id: str,
    agent: str,
    summary: str,
    status: RunStatus,
    completed_actions: list[str] | None = None,
    files_changed: list[str] | None = None,
    artifacts: list[str] | None = None,
    commands_run: list[str] | None = None,
    tests_run: list[str] | None = None,
    risks: list[str] | None = None,
    next_steps: list[str] | None = None,
    policy_exceptions: list[str] | None = None,
    self_audit_notes: list[str] | None = None,
    markdown: bool = False,
    allow_blocked_exit: bool = False,
    blocked_exit_rationale: str | None = None,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Create a structured handoff for a task."""
    store = LocalStore.from_paths(resolve_craik_paths(env))
    try:
        store.initialize()
        writer = HandoffWriter(store)
        handoff = writer.create(
            task_id=task_id,
            agent=agent,
            summary=summary,
            status=status,
            completed_actions=completed_actions,
            files_changed=files_changed,
            artifacts=artifacts,
            commands_run=commands_run,
            tests_run=tests_run,
            risks=risks,
            next_steps=next_steps,
            policy_exceptions=policy_exceptions,
            self_audit_notes=self_audit_notes,
            allow_blocked_exit=allow_blocked_exit,
            blocked_exit_rationale=blocked_exit_rationale,
        )
    except (HandoffContextError, HandoffBlockedByExitDisciplineError) as error:
        raise ValueError(str(error)) from None
    finally:
        store.close()
    payload = handoff.model_dump(mode="json", by_alias=True)
    return CommandResult(
        payload=payload,
        shape="markdown" if markdown else "card",
        text=render_markdown(handoff) if markdown else None,
    )


def handoff_show_result(
    handoff_or_task_id: str,
    *,
    markdown: bool = False,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Return one persisted handoff by handoff id or task id."""
    store = LocalStore.from_paths(resolve_craik_paths(env))
    try:
        store.initialize()
        handoff = HandoffWriter(store).require(handoff_or_task_id)
    except HandoffNotFoundError as error:
        raise ValueError(str(error)) from None
    finally:
        store.close()
    payload = handoff.model_dump(mode="json", by_alias=True)
    return CommandResult(
        payload=payload,
        shape="markdown" if markdown else "card",
        text=render_markdown(handoff) if markdown else None,
    )
