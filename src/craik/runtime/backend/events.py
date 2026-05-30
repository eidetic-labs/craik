"""Canonical Gateway event records for backend clients."""

from __future__ import annotations

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
    """Payload for an assistant-text event (emitted as `run.event`)."""

    kind: Literal["assistant_text"]
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
    return BackendEvent(
        type="receipt.created",
        data=dict(data),
        source=source,
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
    return BackendEvent(
        type="tool.used",
        data=dict(data),
        source=source,
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
    """Build an assistant-text event (emitted as a `run.event` for now)."""
    data: AssistantTextData = {"kind": "assistant_text", "text": text}
    return BackendEvent(
        type="run.event",
        data=dict(data),
        source=source,
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
    return BackendEvent(
        type="approval.requested",
        data=dict(data),
        source=source,
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
    return BackendEvent(
        type="approval.resolved",
        data=dict(data),
        source=source,
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
    return BackendEvent(
        type="run.started",
        data=dict(data),
        source=source,
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
    return BackendEvent(
        type="run.completed",
        data=dict(data),
        source=source,
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
    return BackendEvent(
        type="error",
        data=dict(data),
        source=source,
        run_id=run_id,
        task_id=task_id,
    )
