"""Scheduled automation execution boundaries for the gateway."""

from __future__ import annotations

from datetime import UTC, datetime

from craik.contracts.models import (
    CapabilityReceipt,
    CraikModel,
    PolicyEnvelope,
    ReceiptResult,
    ScheduledAutomation,
    ScheduledAutomationStatus,
)
from craik.runtime.channels.schedules import (
    ScheduledTaskCreation,
    create_task_from_schedule_tick,
)


class ScheduledAutomationResult(CraikModel):
    """Result of evaluating one scheduled automation tick."""

    status: ScheduledAutomationStatus
    reason: str
    automation_id: str
    schedule_id: str
    tick_id: str
    task_creation: ScheduledTaskCreation | None = None


def run_scheduled_automation_tick(
    *,
    automation: ScheduledAutomation,
    policy: PolicyEnvelope,
    tick_id: str,
    run_at: datetime,
    seen_tick_ids: set[str],
) -> ScheduledAutomationResult:
    """Evaluate one scheduled automation tick under explicit gateway policy."""
    if not automation.enabled:
        return ScheduledAutomationResult(
            status="disabled",
            reason="scheduled automation is disabled",
            automation_id=automation.id,
            schedule_id=automation.schedule.id,
            tick_id=tick_id,
        )
    if not _policy_allows(policy, automation.required_capability):
        return ScheduledAutomationResult(
            status="policy_denied",
            reason=f"policy does not allow {automation.required_capability}",
            automation_id=automation.id,
            schedule_id=automation.schedule.id,
            tick_id=tick_id,
        )

    schedule = automation.schedule.model_copy(
        update={
            "policy_envelope_id": automation.policy_envelope_id,
            "receipt_ids": [*automation.schedule.receipt_ids, *automation.receipt_ids],
        }
    )
    task_creation = create_task_from_schedule_tick(
        schedule=schedule,
        tick_id=tick_id,
        run_at=run_at,
        seen_tick_ids=seen_tick_ids,
    )
    return ScheduledAutomationResult(
        status="created" if task_creation.created else "duplicate",
        reason=task_creation.reason,
        automation_id=automation.id,
        schedule_id=automation.schedule.id,
        tick_id=tick_id,
        task_creation=task_creation,
    )


def scheduled_automation_receipt(
    *,
    result: ScheduledAutomationResult,
    policy: PolicyEnvelope,
    created_at: datetime | None = None,
) -> CapabilityReceipt:
    """Build a redacted receipt for one scheduled automation decision."""
    now = created_at or datetime.now(UTC)
    return CapabilityReceipt(
        id=f"receipt_scheduled_automation_{result.status}_{result.tick_id}",
        task_id=policy.task_id,
        actor=policy.actor,
        capability="gateway.schedule.execute",
        target=f"{result.automation_id}:{result.tick_id}",
        policy_profile=policy.profile,
        fail_open=False,
        reason=result.reason,
        result=ReceiptResult(
            status="passed" if result.status == "created" else "denied",
            summary=f"Scheduled automation {result.status}.",
            metadata={
                "policy_envelope_id": policy.id,
                "automation_id": result.automation_id,
                "schedule_id": result.schedule_id,
                "tick_id": result.tick_id,
                "task_id": result.task_creation.task.id
                if result.task_creation and result.task_creation.task
                else None,
            },
        ),
        redacted=True,
        created_at=now,
    )


def _policy_allows(policy: PolicyEnvelope, capability: str) -> bool:
    return (
        capability in policy.allowed_capabilities
        and capability not in policy.denied_capabilities
    )
