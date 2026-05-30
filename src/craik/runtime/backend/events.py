"""Canonical Gateway event records for backend clients."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, TypedDict

BackendEventType = Literal[
    "prompt.submitted",
    "approval.resolved",
    "session.ready",
    "session.status",
    "session.history",
    "slash.completed",
    "slash.catalog",
    "model.changed",
    "run.interrupt.requested",
    "run.started",
    "run.working",
    "run.progress",
    "run.event",
    "tool.used",
    "file.changed",
    "approval.requested",
    "approval.denied",
    "model.selected",
    "receipt.created",
    "run.output",
    "run.completed",
    "assistant_text",
    "error",
]

# Originating-adapter identifiers carried on the event envelope. "gateway" is
# used for session-level events emitted by the Gateway itself.
EventSource = Literal[
    "anthropic-cli",
    "anthropic-api",
    "openai-cli",
    "openai-api",
    "google-cli",
    "google-api",
    "gateway",
]

# Governance vocabularies recorded on receipts.
ReceiptExecution = Literal["craik", "delegated-observed"]
ReceiptMode = Literal[
    "ask",
    "auto",
    "acceptEdits",
    "plan",
    "default",
    "bypassPermissions",
]
ReceiptDecision = Literal["allow", "deny"]
ReceiptDecidedBy = Literal["operator", "policy", "bypass"]


@dataclass(frozen=True)
class BackendEvent:
    """One normalized backend event emitted by a Craik Gateway session."""

    type: BackendEventType
    data: dict[str, Any] = field(default_factory=dict)
    source: str = "gateway"
    run_id: str | None = None
    task_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def as_dict(self) -> dict[str, Any]:
        """Return a JSONL-friendly event payload."""
        return {
            "type": self.type,
            "source": self.source,
            "created_at": self.created_at.isoformat(),
            "run_id": self.run_id,
            "task_id": self.task_id,
            "data": self.data,
        }


# --- Contract validation ----------------------------------------------------
# `validate_event` is the raising, emission-time guard. The actual checking
# lives in `event_contract.py` (the single source of truth over the
# machine-readable `gateway_event_contract.json`); this is a thin adapter over
# it. Builders invoke it only when CRAIK_VALIDATE_EVENTS is set, so production
# stays fast while CI catches contract drift.


class EventContractError(ValueError):
    """Raised when an event violates the Gateway event contract."""


def validate_event(ev: BackendEvent) -> None:
    """Raise EventContractError if ev violates the gateway event contract.

    Delegates to the single source of truth in event_contract.py. Imported
    lazily because event_contract imports BackendEvent from this module.
    """
    from craik.runtime.backend.event_contract import (
        format_gateway_event_contract_issues,
        validate_gateway_event,
    )

    issues = validate_gateway_event(ev)
    if issues:
        raise EventContractError(format_gateway_event_contract_issues(issues))


def _validation_enabled() -> bool:
    """Whether emission-time contract validation is enabled (env-gated)."""
    return os.environ.get("CRAIK_VALIDATE_EVENTS") == "1"


def _make(
    event_type: BackendEventType,
    *,
    source: EventSource,
    data: dict[str, Any],
    run_id: str | None,
    task_id: str | None,
) -> BackendEvent:
    """Construct a BackendEvent, validating it when the env-gate is enabled."""
    ev = BackendEvent(
        type=event_type,
        data=data,
        source=source,
        run_id=run_id,
        task_id=task_id,
    )
    if _validation_enabled():
        validate_event(ev)
    return ev


# --- Typed payloads ---------------------------------------------------------
# Each TypedDict describes the `data` payload for one event type, matching the
# Gateway event contract. Optional keys are split into a separate non-total
# TypedDict and combined via inheritance.


class ReceiptData(TypedDict):
    """Payload for a `receipt.created` event (governance record)."""

    receipt_id: str
    purpose: str
    execution: ReceiptExecution
    mode: ReceiptMode
    decision: ReceiptDecision
    decided_by: ReceiptDecidedBy


class _ToolDataOptional(TypedDict, total=False):
    target: str
    command: str
    message: str


class ToolData(_ToolDataOptional):
    """Payload for a `tool.used` event."""

    tool: str


class AssistantTextData(TypedDict):
    """Payload for a first-class `assistant_text` event."""

    text: str


class _ApprovalRequestedOptional(TypedDict, total=False):
    tool: str
    target: str
    reason: str


class ApprovalRequestedData(_ApprovalRequestedOptional):
    """Payload for an `approval.requested` event."""

    message: str


class _ApprovalResolvedOptional(TypedDict, total=False):
    decided_by: ReceiptDecidedBy
    mode: ReceiptMode


class ApprovalResolvedData(_ApprovalResolvedOptional):
    """Payload for an `approval.resolved` event."""

    approval_id: str
    decision: ReceiptDecision


class RunStartedData(TypedDict):
    """Payload for a `run.started` event (envelope carries run_id)."""


class RunCompletedData(TypedDict):
    """Payload for a `run.completed` event."""

    status: str


class ErrorData(TypedDict):
    """Payload for an `error` event."""

    message: str


# --- Builders ---------------------------------------------------------------
# `source` is a required argument on every builder: the builders are the
# enforcement point for explicit event origin.


def receipt_event(
    *,
    receipt_id: str,
    source: EventSource,
    purpose: str,
    execution: ReceiptExecution,
    mode: ReceiptMode,
    decision: ReceiptDecision,
    decided_by: ReceiptDecidedBy,
    run_id: str | None = None,
    task_id: str | None = None,
) -> BackendEvent:
    """Build a `receipt.created` event carrying the governance record."""
    data: ReceiptData = {
        "receipt_id": receipt_id,
        "purpose": purpose,
        "execution": execution,
        "mode": mode,
        "decision": decision,
        "decided_by": decided_by,
    }
    return _make(
        "receipt.created",
        source=source,
        data=dict(data),
        run_id=run_id,
        task_id=task_id,
    )


def tool_event(
    *,
    tool: str,
    source: EventSource,
    target: str | None = None,
    command: str | None = None,
    message: str | None = None,
    run_id: str | None = None,
    task_id: str | None = None,
) -> BackendEvent:
    """Build a `tool.used` event for a tool invocation."""
    data: ToolData = {"tool": tool}
    if target is not None:
        data["target"] = target
    if command is not None:
        data["command"] = command
    if message is not None:
        data["message"] = message
    return _make(
        "tool.used",
        source=source,
        data=dict(data),
        run_id=run_id,
        task_id=task_id,
    )


def assistant_text_event(
    *,
    text: str,
    source: EventSource,
    run_id: str | None = None,
    task_id: str | None = None,
) -> BackendEvent:
    """Build a first-class `assistant_text` event carrying model text."""
    data: AssistantTextData = {"text": text}
    return _make(
        "assistant_text",
        source=source,
        data=dict(data),
        run_id=run_id,
        task_id=task_id,
    )


def approval_requested_event(
    *,
    message: str,
    source: EventSource,
    tool: str | None = None,
    target: str | None = None,
    reason: str | None = None,
    run_id: str | None = None,
    task_id: str | None = None,
) -> BackendEvent:
    """Build an `approval.requested` event."""
    data: ApprovalRequestedData = {"message": message}
    if tool is not None:
        data["tool"] = tool
    if target is not None:
        data["target"] = target
    if reason is not None:
        data["reason"] = reason
    return _make(
        "approval.requested",
        source=source,
        data=dict(data),
        run_id=run_id,
        task_id=task_id,
    )


def approval_resolved_event(
    *,
    approval_id: str,
    decision: ReceiptDecision,
    source: EventSource,
    decided_by: ReceiptDecidedBy | None = None,
    mode: ReceiptMode | None = None,
    run_id: str | None = None,
    task_id: str | None = None,
) -> BackendEvent:
    """Build an `approval.resolved` event."""
    data: ApprovalResolvedData = {"approval_id": approval_id, "decision": decision}
    if decided_by is not None:
        data["decided_by"] = decided_by
    if mode is not None:
        data["mode"] = mode
    return _make(
        "approval.resolved",
        source=source,
        data=dict(data),
        run_id=run_id,
        task_id=task_id,
    )


def run_started_event(
    *,
    source: EventSource,
    run_id: str | None = None,
    task_id: str | None = None,
) -> BackendEvent:
    """Build a `run.started` event (run_id carried on the envelope)."""
    data: RunStartedData = {}
    return _make(
        "run.started",
        source=source,
        data=dict(data),
        run_id=run_id,
        task_id=task_id,
    )


def run_completed_event(
    *,
    status: str,
    source: EventSource,
    run_id: str | None = None,
    task_id: str | None = None,
) -> BackendEvent:
    """Build a `run.completed` event."""
    data: RunCompletedData = {"status": status}
    return _make(
        "run.completed",
        source=source,
        data=dict(data),
        run_id=run_id,
        task_id=task_id,
    )


def error_event(
    *,
    message: str,
    source: EventSource,
    run_id: str | None = None,
    task_id: str | None = None,
) -> BackendEvent:
    """Build an `error` event."""
    data: ErrorData = {"message": message}
    return _make(
        "error",
        source=source,
        data=dict(data),
        run_id=run_id,
        task_id=task_id,
    )


# --- Streaming coalescing ---------------------------------------------------
# Backends that stream assistant text emit CUMULATIVE snapshots: each chunk is
# the full text-so-far, typically a prefix-extension of the prior one. The
# Coalescer collapses those snapshots per run into a single superseding text,
# so consumers see one `assistant_text` event instead of N partial fragments.


class Coalescer:
    """Collapse cumulative assistant-text snapshots per run; latest supersedes."""

    def __init__(self) -> None:
        # run_id -> latest full-text snapshot. None keys group run-less streams.
        self._latest: dict[str | None, str] = {}

    def update(self, run_id: str | None, snapshot: str) -> None:
        """Record the latest cumulative snapshot for a run (supersede, never append)."""
        self._latest[run_id] = snapshot

    def assistant_text(self, run_id: str | None) -> str | None:
        """Return the current coalesced text for a run, or None if absent."""
        return self._latest.get(run_id)

    def flush(
        self,
        run_id: str | None,
        *,
        source: EventSource,
        task_id: str | None = None,
    ) -> BackendEvent | None:
        """Consume a run's coalesced text as one `assistant_text` event.

        Returns None when the run accumulated no text. The run's state is
        cleared regardless, so a subsequent flush without new snapshots is None.
        """
        text = self._latest.pop(run_id, None)
        if not text:
            return None
        return assistant_text_event(
            text=text,
            source=source,
            run_id=run_id,
            task_id=task_id,
        )
