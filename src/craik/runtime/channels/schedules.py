"""Cron-like gateway schedule task creation."""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import Field

from craik.contracts.models import CraikModel, Priority, TaskMode, TaskRequest

MINIMUM_SCHEDULE_INTERVAL_MINUTES = 5


class GatewaySchedule(CraikModel):
    """Cron-like schedule definition for gateway-created tasks."""

    id: str
    project_id: str
    title: str
    objective: str
    cron: str
    requested_by: str = "gateway:scheduler"
    priority: Priority = "normal"
    mode: TaskMode = "implement"
    policy_envelope_id: str | None = None
    channel: str | None = None
    receipt_ids: list[str] = Field(default_factory=list)


class ScheduledTaskCreation(CraikModel):
    """Result of converting one schedule tick into a task request."""

    created: bool
    reason: str
    schedule_id: str
    tick_id: str
    task: TaskRequest | None = None


def create_task_from_schedule_tick(
    *,
    schedule: GatewaySchedule,
    tick_id: str,
    run_at: datetime,
    seen_tick_ids: set[str],
) -> ScheduledTaskCreation:
    """Create one deterministic task for a schedule tick unless already seen."""
    validate_cron_expression(schedule.cron)
    if tick_id in seen_tick_ids:
        return ScheduledTaskCreation(
            created=False,
            reason="schedule tick already created a task",
            schedule_id=schedule.id,
            tick_id=tick_id,
        )
    constraints = [
        f"schedule_id={schedule.id}",
        f"schedule_tick_id={tick_id}",
        f"schedule_cron={schedule.cron}",
        f"schedule_run_at={run_at.isoformat()}",
    ]
    if schedule.policy_envelope_id:
        constraints.append(f"policy_envelope_id={schedule.policy_envelope_id}")
    if schedule.channel:
        constraints.append(f"channel={schedule.channel}")
    constraints.extend(f"receipt_id={receipt_id}" for receipt_id in schedule.receipt_ids)
    task = TaskRequest(
        id=f"task_schedule_{_slug(schedule.id)}_{_slug(tick_id)}",
        title=schedule.title,
        objective=schedule.objective,
        project_id=schedule.project_id,
        requested_by=schedule.requested_by,
        priority=schedule.priority,
        mode=schedule.mode,
        constraints=constraints,
        expected_outputs=["case_file", "handoff", "receipt"],
        created_at=run_at,
    )
    return ScheduledTaskCreation(
        created=True,
        reason="schedule tick created task",
        schedule_id=schedule.id,
        tick_id=tick_id,
        task=task,
    )


def validate_cron_expression(expression: str) -> None:
    """Validate a conservative five-field cron-like expression."""
    fields = expression.split()
    if len(fields) != 5:
        raise ValueError("cron-like schedule requires five fields")
    for field in fields:
        if not re.fullmatch(r"[\d*/,\-]+", field):
            raise ValueError(f"unsupported cron field: {field}")
    minute_values = _expand_minute_field(fields[0])
    gaps = [
        (right - left) % 60 or 60
        for left, right in zip(
            minute_values,
            minute_values[1:] + minute_values[:1],
            strict=True,
        )
    ]
    if min(gaps) < MINIMUM_SCHEDULE_INTERVAL_MINUTES:
        raise ValueError(
            "cron-like schedule must not run more often than every "
            f"{MINIMUM_SCHEDULE_INTERVAL_MINUTES} minutes"
        )


def _expand_minute_field(field: str) -> list[int]:
    values: set[int] = set()
    for part in field.split(","):
        base, step = _split_step(part)
        if step <= 0:
            raise ValueError("cron minute step must be greater than zero")
        if base == "*":
            start, end = 0, 59
        elif "-" in base:
            start_text, end_text = base.split("-", 1)
            start = _parse_minute(start_text)
            end = _parse_minute(end_text)
            if start > end:
                raise ValueError("cron minute range start must not exceed range end")
        else:
            start = end = _parse_minute(base)
        values.update(range(start, end + 1, step))
    if not values:
        raise ValueError("cron minute field must select at least one minute")
    return sorted(values)


def _split_step(part: str) -> tuple[str, int]:
    if "/" not in part:
        return part, 1
    base, step_text = part.split("/", 1)
    if not base or not step_text:
        raise ValueError("cron minute step requires base and step")
    return base, int(step_text)


def _parse_minute(value: str) -> int:
    minute = int(value)
    if minute < 0 or minute > 59:
        raise ValueError("cron minute value must be between 0 and 59")
    return minute


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "unknown"
