"""Scope-control helpers for the governed loop."""

from __future__ import annotations

from craik.contracts.models import IntentLock, PolicyEnvelope, TaskRun
from craik.runtime.store import LocalStore
from craik.runtime.work.coordination.scope_changes import (
    ScopeChangeProtocolManager,
    ScopeChangeRequirement,
    discovered_scope_from_context,
)
from craik.runtime.work.loop_support.execution import LoopStep


def record_scope_change_pause(
    *,
    store: LocalStore,
    policy: PolicyEnvelope,
    run: TaskRun,
    intent_lock: IntentLock | None,
    step: LoopStep,
    actor: str,
) -> ScopeChangeRequirement | None:
    """Record and pause when a loop step discovers out-of-scope work."""
    return ScopeChangeProtocolManager(store).require_decision_for_discovered_scope(
        policy=policy,
        run=run,
        intent_lock=intent_lock,
        discovered_scope=discovered_scope_from_context(step.context),
        requested_by=actor,
        reason=f"Discovered work outside the current scope during {step.phase}.",
    )
