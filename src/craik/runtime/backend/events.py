"""Canonical Gateway event records for backend clients."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

BackendEventType = Literal[
    "prompt.submitted",
    "approval.resolved",
    "session.ready",
    "session.status",
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


@dataclass(frozen=True)
class BackendEvent:
    """One normalized backend event emitted by a Craik Gateway session."""

    type: BackendEventType
    data: dict[str, Any] = field(default_factory=dict)
    run_id: str | None = None
    task_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def as_dict(self) -> dict[str, Any]:
        """Return a JSONL-friendly event payload."""
        return {
            "type": self.type,
            "created_at": self.created_at.isoformat(),
            "run_id": self.run_id,
            "task_id": self.task_id,
            "data": self.data,
        }
