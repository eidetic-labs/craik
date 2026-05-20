"""Live work-graph coordination state helpers."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from craik.contracts.models import WorkGraphEvent, WorkGraphEventType, WorkGraphExport
from craik.runtime.store import LocalStore
from craik.runtime.work.graph import WorkGraphExporter


class WorkGraphCoordinator:
    """Persist work-graph events and query the active coordination graph."""

    def __init__(self, store: LocalStore) -> None:
        self._store = store

    def active_graph(self, *, task_id: str | None = None) -> WorkGraphExport:
        """Return the current persisted coordination graph."""
        return WorkGraphExporter(self._store).export(task_id=task_id)

    def events_for_node(self, node_id: str) -> list[WorkGraphEvent]:
        """Return persisted graph events connected to one node."""
        return [
            event
            for event in self._store.list_graph_events()
            if event.from_node == node_id or event.to_node == node_id
        ]

    def record_artifact(
        self,
        *,
        task_id: str,
        artifact_type: str,
        artifact_id: str,
        receipt_ids: list[str] | None = None,
        source_node: str | None = None,
        relation: WorkGraphEventType = "created",
        metadata: dict[str, object] | None = None,
    ) -> list[WorkGraphEvent]:
        """Record a live artifact node and optional receipt provenance links."""
        artifact_node = f"{artifact_type}:{artifact_id}"
        events = [
            self.record_event(
                task_id=task_id,
                type=relation,
                from_node=source_node or f"task:{task_id}",
                to_node=artifact_node,
                metadata=metadata,
            )
        ]
        for receipt_id in receipt_ids or []:
            events.append(
                self.record_event(
                    task_id=task_id,
                    type="verified_by",
                    from_node=artifact_node,
                    to_node=f"receipt:{receipt_id}",
                    metadata={"artifact_type": artifact_type},
                )
            )
        return events

    def record_event(
        self,
        *,
        task_id: str,
        type: WorkGraphEventType,
        from_node: str,
        to_node: str,
        metadata: dict[str, object] | None = None,
    ) -> WorkGraphEvent:
        """Persist one deterministic work-graph event."""
        event = WorkGraphEvent.model_validate(
            {
                "id": work_graph_event_id(task_id, type, from_node, to_node),
                "task_id": task_id,
                "type": type,
                "from": from_node,
                "to": to_node,
                "metadata": dict(metadata or {}),
                "created_at": datetime.now(UTC),
            }
        )
        self._store.put_graph_event(event)
        return event


def work_graph_event_id(
    task_id: str,
    type: WorkGraphEventType,
    from_node: str,
    to_node: str,
) -> str:
    """Return a stable event id for one graph edge."""
    return f"graph_event_{_slug(task_id)}_{_slug(type)}_{_slug(from_node)}_{_slug(to_node)}"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "node"
