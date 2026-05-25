"""Fixture messaging channel adapter for controlled gateway ingress."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from craik.contracts.models import (
    CapabilityReceipt,
    ChannelAdapterContract,
    PolicyProfile,
    ReceiptResult,
)
from craik.runtime.policy.text import sanitize_runtime_text

MESSAGING_ADAPTER_ID = "messaging_fixture"
MESSAGE_RECEIVE_CAPABILITY = "channel.message.receive"
MESSAGE_RESPOND_CAPABILITY = "channel.message.respond"


def default_messaging_channel_contract(
    *,
    created_at: datetime | None = None,
) -> ChannelAdapterContract:
    """Return the built-in fixture messaging channel adapter contract."""
    return ChannelAdapterContract.model_validate(
        {
            "id": "channel_adapter_messaging_fixture",
            "identity": {
            "adapter_id": MESSAGING_ADAPTER_ID,
            "channel": "messaging",
            "name": "Messaging Fixture Adapter",
            "adapter_version": "0.1.0",
            "service": "fixture-chat",
            },
            "capabilities": [
            {
                "name": MESSAGE_RECEIVE_CAPABILITY,
                "direction": "inbound",
                "description": "Receive normalized operator messages.",
                "grant_required": True,
                "receipt_required": True,
            },
            {
                "name": MESSAGE_RESPOND_CAPABILITY,
                "direction": "outbound",
                "description": "Send redacted operator responses.",
                "grant_required": True,
                "receipt_required": True,
            },
            ],
            "inbound_event": {
            "fields": [
                "event_id",
                "channel",
                "received_at",
                "sender",
                "text",
                "thread_id",
                "metadata",
            ],
            "redacted_fields": ["text"],
            "metadata": {"identity_model": "external sender id is paired separately"},
            },
            "outbound_response": {
            "fields": ["response_id", "event_id", "status", "summary", "text", "receipt_ids"],
            "redacted_fields": ["text"],
            "metadata": {"delivery": "fixture adapter does not contact external services"},
            },
            "receipts": {
            "required": True,
            "receipt_schema": "craik.capability_receipt",
            "capabilities": [MESSAGE_RECEIVE_CAPABILITY, MESSAGE_RESPOND_CAPABILITY],
            },
            "trust_boundary": {
            "policy_envelope_required": True,
            "allowlist_required": True,
            "inbound_identity_required": True,
            "secrets_in_config_allowed": False,
            "notes": [
                "Inbound sender ids must be paired before privileged action.",
                "Fixture adapter normalizes messages without network delivery.",
            ],
            },
            "docs": ["docs/reference/messaging-channel-adapter.md"],
            "created_at": created_at or datetime.now(UTC),
        }
    )


def normalize_inbound_message(
    *,
    event_id: str,
    sender_id: str,
    text: str,
    received_at: datetime | None = None,
    thread_id: str | None = None,
    identity_id: str | None = None,
    policy_envelope_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Map a raw fixture message into the channel adapter inbound event shape."""
    received = received_at or datetime.now(UTC)
    return {
        "event_id": event_id,
        "channel": "messaging",
        "received_at": received.isoformat(),
        "sender": {
            "external_id": sender_id,
            "identity_id": identity_id,
            "policy_envelope_id": policy_envelope_id,
        },
        "text": sanitize_runtime_text(text),
        "thread_id": thread_id,
        "metadata": metadata or {},
    }


def inbound_message_receipt(
    *,
    event: dict[str, Any],
    task_id: str,
    actor: str,
    policy_profile: PolicyProfile,
    policy_envelope_id: str,
    created_at: datetime | None = None,
) -> CapabilityReceipt:
    """Build a redacted receipt for normalized inbound messaging activity."""
    now = created_at or datetime.now(UTC)
    event_id = _required_string(event, "event_id")
    sender = event.get("sender")
    sender_identity = sender if isinstance(sender, dict) else {}
    return CapabilityReceipt(
        id=f"receipt_channel_message_receive_{event_id}",
        task_id=task_id,
        actor=actor,
        capability=MESSAGE_RECEIVE_CAPABILITY,
        target=f"messaging:{event_id}",
        policy_profile=policy_profile,
        fail_open=False,
        reason="Normalized inbound messaging channel event.",
        result=ReceiptResult(
            status="passed",
            summary="Inbound messaging event normalized.",
            metadata={
                "policy_envelope_id": policy_envelope_id,
                "channel": event.get("channel"),
                "event_id": event_id,
                "sender_external_id": sender_identity.get("external_id"),
                "sender_identity_id": sender_identity.get("identity_id"),
                "redacted_fields": ["text"],
            },
        ),
        redacted=True,
        created_at=now,
    )


def messaging_response_payload(
    *,
    response_id: str,
    event_id: str,
    status: str,
    summary: str,
    text: str | None = None,
    receipt_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Return an outbound fixture response payload without delivering it."""
    return {
        "response_id": response_id,
        "event_id": event_id,
        "status": status,
        "summary": summary,
        "text": text,
        "receipt_ids": receipt_ids or [],
    }


def _required_string(event: dict[str, Any], key: str) -> str:
    value = event.get(key)
    if isinstance(value, str) and value:
        return value
    raise ValueError(f"event requires non-empty {key}")
