from datetime import UTC, datetime

import pytest

from craik.runtime.channels.schedules import (
    GatewaySchedule,
    create_task_from_schedule_tick,
    validate_cron_expression,
)

NOW = datetime(2026, 5, 16, 19, 25, tzinfo=UTC)


def _schedule() -> GatewaySchedule:
    return GatewaySchedule(
        id="daily_status",
        project_id="project_craik",
        title="Daily gateway status",
        objective="Summarize gateway health and open risks.",
        cron="0 9 * * *",
        policy_envelope_id="policy_schedule",
        channel="scheduler",
        receipt_ids=["receipt_schedule_tick"],
    )


def test_schedule_tick_creates_task_request_with_context() -> None:
    result = create_task_from_schedule_tick(
        schedule=_schedule(),
        tick_id="2026-05-16T09:00:00Z",
        run_at=NOW,
        seen_tick_ids=set(),
    )

    assert result.created is True
    assert result.task is not None
    assert result.task.id == "task_schedule_daily_status_2026_05_16t09_00_00z"
    assert result.task.project_id == "project_craik"
    assert result.task.requested_by == "gateway:scheduler"
    assert "policy_envelope_id=policy_schedule" in result.task.constraints
    assert "channel=scheduler" in result.task.constraints
    assert "receipt_id=receipt_schedule_tick" in result.task.constraints
    assert result.task.expected_outputs == ["case_file", "handoff", "receipt"]


def test_schedule_tick_deduplicates_seen_tick() -> None:
    result = create_task_from_schedule_tick(
        schedule=_schedule(),
        tick_id="2026-05-16T09:00:00Z",
        run_at=NOW,
        seen_tick_ids={"2026-05-16T09:00:00Z"},
    )

    assert result.created is False
    assert result.reason == "schedule tick already created a task"
    assert result.task is None


def test_schedule_validates_cron_like_expression() -> None:
    validate_cron_expression("*/15 9-17 * * 1,2,3,4,5")


@pytest.mark.parametrize("expression", ["* * * * *", "*/4 * * * *", "0,1 * * * *"])
def test_schedule_rejects_too_frequent_cron_expression(expression: str) -> None:
    with pytest.raises(ValueError, match="more often than every 5 minutes"):
        validate_cron_expression(expression)


def test_schedule_accepts_minimum_interval_boundary() -> None:
    validate_cron_expression("0,5,10 * * * *")


def test_schedule_rejects_unsupported_cron_shape() -> None:
    with pytest.raises(ValueError, match="five fields"):
        validate_cron_expression("0 9 * *")


def test_schedule_rejects_unsupported_cron_tokens() -> None:
    with pytest.raises(ValueError, match="unsupported cron field"):
        validate_cron_expression("@daily * * * *")
