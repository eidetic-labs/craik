"""Gateway event replay helpers for TUI client evaluation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class GatewayReplaySummary:
    """Client-neutral summary of one Gateway JSONL replay fixture."""

    event_types: list[str]
    run_ids: list[str] = field(default_factory=list)
    task_ids: list[str] = field(default_factory=list)
    receipt_ids: list[str] = field(default_factory=list)
    progress_messages: list[str] = field(default_factory=list)

    @property
    def has_lifecycle(self) -> bool:
        """Return whether the replay has the minimum run lifecycle events."""
        required = {"prompt.submitted", "run.started", "receipt.created", "run.completed"}
        return required.issubset(set(self.event_types))

    @property
    def has_working_state(self) -> bool:
        """Return whether the replay gives clients something to show while running."""
        return "run.working" in self.event_types or bool(self.progress_messages)


def load_gateway_replay(path: Path) -> list[dict[str, Any]]:
    """Load Gateway JSONL events from a fixture path."""
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"Gateway replay event must be an object: {path}")
        events.append(payload)
    return events


def summarize_gateway_replay(events: list[dict[str, Any]]) -> GatewayReplaySummary:
    """Summarize replay events for Textual/Rust client comparison tests."""
    event_types: list[str] = []
    run_ids: list[str] = []
    task_ids: list[str] = []
    receipt_ids: list[str] = []
    progress_messages: list[str] = []
    for event in events:
        event_type = event.get("type")
        if isinstance(event_type, str):
            event_types.append(event_type)
        run_id = event.get("run_id")
        if isinstance(run_id, str) and run_id not in run_ids:
            run_ids.append(run_id)
        task_id = event.get("task_id")
        if isinstance(task_id, str) and task_id not in task_ids:
            task_ids.append(task_id)
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        receipt_id = data.get("receipt_id")
        if isinstance(receipt_id, str) and receipt_id not in receipt_ids:
            receipt_ids.append(receipt_id)
        message = data.get("message")
        if event_type == "run.progress" and isinstance(message, str):
            progress_messages.append(message)
    return GatewayReplaySummary(
        event_types=event_types,
        run_ids=run_ids,
        task_ids=task_ids,
        receipt_ids=receipt_ids,
        progress_messages=progress_messages,
    )
