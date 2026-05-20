"""Task creation helpers."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from craik.contracts.models import Priority, TaskMode, TaskRequest
from craik.runtime.store import LocalStore


def create_task(
    store: LocalStore,
    *,
    title: str,
    objective: str,
    project_id: str,
    requested_by: str = "user:local",
    priority: Priority = "normal",
    mode: TaskMode = "implement",
    auth_profile_id: str | None = None,
    operator_subject: str | None = None,
    operator_issuer: str | None = None,
    source_handoff_id: str | None = None,
    source_task_id: str | None = None,
    source_run_id: str | None = None,
    expected_duration_minutes: int | None = None,
    constraints: list[str] | None = None,
    expected_outputs: list[str] | None = None,
) -> TaskRequest:
    """Create and persist a deterministic task id for a project/title pair."""
    task = TaskRequest(
        id=task_id(title),
        title=title,
        objective=objective,
        project_id=project_id,
        requested_by=requested_by,
        priority=priority,
        mode=mode,
        auth_profile_id=auth_profile_id,
        operator_subject=operator_subject,
        operator_issuer=operator_issuer,
        source_handoff_id=source_handoff_id,
        source_task_id=source_task_id,
        source_run_id=source_run_id,
        expected_duration_minutes=expected_duration_minutes,
        constraints=constraints or [],
        expected_outputs=expected_outputs or ["case_file", "handoff"],
        created_at=datetime.now(UTC),
    )
    store.put_task(task)
    return task


def task_id(title: str) -> str:
    """Create a stable task id from a title."""
    slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    return f"task_{slug or 'untitled'}"
