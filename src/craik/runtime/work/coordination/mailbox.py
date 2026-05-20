"""Receipt-backed agent-to-agent mailbox helpers."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from craik.contracts.models import (
    AgentMessage,
    AgentMessageKind,
    CapabilityReceipt,
    PolicyEnvelope,
    ReceiptResult,
)
from craik.runtime.store import LocalStore
from craik.runtime.work.coordination.live_graph import WorkGraphCoordinator


class AgentMessageNotFoundError(RuntimeError):
    """Raised when a mailbox message cannot be found."""


class AgentMessageAuthorizationError(RuntimeError):
    """Raised when a mailbox caller cannot authenticate the sender identity."""


def send_agent_message(
    store: LocalStore,
    *,
    policy: PolicyEnvelope,
    task_id: str,
    from_agent: str,
    to_agent: str,
    subject: str,
    body: str,
    kind: AgentMessageKind = "request",
    from_role_id: str | None = None,
    from_role_kind: str | None = None,
    to_role_id: str | None = None,
    to_role_kind: str | None = None,
    run_id: str | None = None,
    handoff_id: str | None = None,
) -> AgentMessage:
    """Persist a sent agent message and its send receipt."""
    _authorize_sender(
        store,
        run_id=run_id,
        from_agent=from_agent,
        from_role_id=from_role_id,
        from_role_kind=from_role_kind,
    )
    message_id = _available_agent_message_id(store, task_id, from_agent, to_agent, subject)
    receipt = _message_receipt(
        policy=policy,
        message_id=message_id,
        task_id=task_id,
        capability="agent.message.send",
        actor=from_agent,
        target=to_agent,
        summary=f"Message sent to {to_agent}.",
        metadata={
            "message_id": message_id,
            "kind": kind,
            "from_role_id": from_role_id,
            "from_role_kind": from_role_kind,
            "to_role_id": to_role_id,
            "to_role_kind": to_role_kind,
            "run_id": run_id,
            "handoff_id": handoff_id,
        },
    )
    store.put_receipt(receipt)
    message = AgentMessage(
        id=message_id,
        task_id=task_id,
        kind=kind,
        status="sent",
        from_agent=from_agent,
        to_agent=to_agent,
        from_role_id=from_role_id,
        from_role_kind=from_role_kind,
        to_role_id=to_role_id,
        to_role_kind=to_role_kind,
        run_id=run_id,
        handoff_id=handoff_id,
        subject=subject,
        body=body,
        receipt_ids=[receipt.id],
        created_at=datetime.now(UTC),
    )
    store.put_agent_message(message)
    WorkGraphCoordinator(store).record_artifact(
        task_id=task_id,
        artifact_type="message",
        artifact_id=message.id,
        receipt_ids=message.receipt_ids,
        metadata={"from_agent": from_agent, "to_agent": to_agent, "kind": kind},
    )
    return message


def record_agent_message_received(
    store: LocalStore,
    *,
    policy: PolicyEnvelope,
    message_id: str,
    received_by: str,
) -> AgentMessage:
    """Mark a sent message as received and append a receive receipt."""
    message = store.get_agent_message(message_id)
    if message is None:
        raise AgentMessageNotFoundError(f"unknown agent message: {message_id}")
    receipt = _message_receipt(
        policy=policy,
        message_id=message.id,
        task_id=message.task_id,
        capability="agent.message.receive",
        actor=received_by,
        target=message.id,
        summary=f"Message received by {received_by}.",
        metadata={
            "message_id": message.id,
            "kind": message.kind,
            "from_agent": message.from_agent,
            "to_agent": message.to_agent,
            "run_id": message.run_id,
            "handoff_id": message.handoff_id,
        },
    )
    store.put_receipt(receipt)
    updated = message.model_copy(
        update={
            "status": "received",
            "received_at": datetime.now(UTC),
            "receipt_ids": [*message.receipt_ids, receipt.id],
        }
    )
    store.put_agent_message(updated)
    WorkGraphCoordinator(store).record_artifact(
        task_id=message.task_id,
        artifact_type="message",
        artifact_id=message.id,
        receipt_ids=[receipt.id],
        metadata={"status": "received", "received_by": received_by},
    )
    return updated


def agent_message_id(task_id: str, from_agent: str, to_agent: str, subject: str) -> str:
    """Return a deterministic mailbox message id."""
    raw = "_".join([task_id, from_agent, to_agent, subject])
    slug = re.sub(r"[^a-z0-9]+", "_", raw.lower()).strip("_")
    return f"agent_message_{slug or 'untitled'}"


def _available_agent_message_id(
    store: LocalStore,
    task_id: str,
    from_agent: str,
    to_agent: str,
    subject: str,
) -> str:
    base_id = agent_message_id(task_id, from_agent, to_agent, subject)
    if store.get_agent_message(base_id) is None:
        return base_id
    suffix = 2
    while store.get_agent_message(f"{base_id}_{suffix}") is not None:
        suffix += 1
    return f"{base_id}_{suffix}"


def _authorize_sender(
    store: LocalStore,
    *,
    run_id: str | None,
    from_agent: str,
    from_role_id: str | None,
    from_role_kind: str | None,
) -> None:
    if run_id is None:
        raise AgentMessageAuthorizationError("mailbox sends require a sender run_id")
    run = store.get_task_run(run_id)
    if run is None:
        raise AgentMessageAuthorizationError(f"unknown task run for mailbox sender: {run_id}")
    allowed_senders = {f"runner:{run.runner_id}"}
    if run.role_id:
        allowed_senders.add(run.role_id)
        allowed_senders.add(f"role:{run.role_id}")
    if run.role_kind:
        allowed_senders.add(f"agent:{run.role_kind}")
        allowed_senders.add(f"role:{run.role_kind}")
    if from_agent not in allowed_senders:
        raise AgentMessageAuthorizationError(
            f"run {run.id} is not authorized to send as {from_agent}"
        )
    if from_role_id is not None and run.role_id is not None and from_role_id != run.role_id:
        raise AgentMessageAuthorizationError(
            f"run {run.id} role id {run.role_id} cannot send as {from_role_id}"
        )
    if (
        from_role_kind is not None
        and run.role_kind is not None
        and from_role_kind != run.role_kind
    ):
        raise AgentMessageAuthorizationError(
            f"run {run.id} role kind {run.role_kind} cannot send as {from_role_kind}"
        )


def _message_receipt(
    *,
    policy: PolicyEnvelope,
    message_id: str,
    task_id: str,
    capability: str,
    actor: str,
    target: str,
    summary: str,
    metadata: dict[str, object],
) -> CapabilityReceipt:
    return CapabilityReceipt(
        id=f"receipt_{message_id}_{capability.rsplit('.', maxsplit=1)[-1]}",
        task_id=task_id,
        actor=actor,
        capability=capability,
        target=target,
        policy_profile=policy.profile,
        fail_open=policy.fail_open,
        reason=summary,
        result=ReceiptResult(status="passed", summary=summary, metadata=metadata),
        redacted=True,
        created_at=datetime.now(UTC),
    )
