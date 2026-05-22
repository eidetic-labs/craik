"""Channel-scoped policy envelope helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from craik.contracts.models import (
    CapabilityReceipt,
    ChannelIdentityPairing,
    CraikModel,
    PolicyEnvelope,
    PolicyProfile,
    ReceiptResult,
)
from craik.runtime.channels.allowlist import ChannelAllowlistDecision
from craik.runtime.channels.identity import allows_privileged_ingress

DEFAULT_CHANNEL_ALLOWED_CAPABILITIES = [
    "channel.message.receive",
    "channel.message.respond",
    "receipt.write",
]
DEFAULT_CHANNEL_DENIED_CAPABILITIES = [
    "repo.write",
    "repo.write.immutable",
    "shell.execute",
    "memory.write",
    "github.write",
    "gateway.admin",
]


class ChannelPolicySelection(CraikModel):
    """Result of binding an inbound event to a channel-scoped policy envelope."""

    allowed: bool
    reason: str
    policy: PolicyEnvelope | None = None
    event_id: str | None = None
    subject: str | None = None


def select_channel_policy(
    *,
    event: dict[str, Any],
    pairing: ChannelIdentityPairing,
    allowlist_decision: ChannelAllowlistDecision,
    policy_id: str,
    task_id: str,
    profile: PolicyProfile = "strict",
    allowed_capabilities: list[str] | None = None,
) -> ChannelPolicySelection:
    """Bind a normalized inbound channel event to a narrow policy envelope."""
    event_id = _optional_string(event.get("event_id"))
    checked_at = _optional_datetime(event.get("received_at")) or datetime.now(UTC)
    if not allows_privileged_ingress(pairing, now=checked_at):
        return ChannelPolicySelection(
            allowed=False,
            reason=f"channel identity {pairing.id} is not paired",
            event_id=event_id,
            subject=pairing.subject,
        )
    if not allowlist_decision.allowed:
        return ChannelPolicySelection(
            allowed=False,
            reason=allowlist_decision.reason,
            event_id=event_id,
            subject=pairing.subject,
        )

    policy = PolicyEnvelope(
        id=policy_id,
        task_id=task_id,
        actor=pairing.subject or "channel:unknown",
        profile=profile,
        fail_open=False,
        allowed_capabilities=allowed_capabilities or DEFAULT_CHANNEL_ALLOWED_CAPABILITIES,
        denied_capabilities=DEFAULT_CHANNEL_DENIED_CAPABILITIES,
        approval_required=["channel.message.respond"],
        verification_required=["channel.allowlist", "channel.identity_pairing"],
        handoff_required=True,
        receipt_required=True,
        redaction_required=True,
    )
    return ChannelPolicySelection(
        allowed=True,
        reason="channel policy selected",
        policy=policy,
        event_id=event_id,
        subject=pairing.subject,
    )


def channel_capability_allowed(policy: PolicyEnvelope, capability: str) -> bool:
    """Return whether a channel-scoped policy permits a capability."""
    return (
        capability in policy.allowed_capabilities
        and capability not in policy.denied_capabilities
    )


def channel_policy_denial_receipt(
    *,
    event: dict[str, Any],
    policy: PolicyEnvelope | None,
    capability: str,
    reason: str,
    task_id: str,
    actor: str,
    policy_profile: PolicyProfile,
    created_at: datetime | None = None,
) -> CapabilityReceipt:
    """Build a redacted receipt for a channel policy denial."""
    now = created_at or datetime.now(UTC)
    event_id = _optional_string(event.get("event_id")) or "unknown"
    return CapabilityReceipt(
        id=f"receipt_channel_policy_denied_{event_id}_{capability.replace('.', '_')}",
        task_id=task_id,
        actor=actor,
        capability=capability,
        target=f"channel:{event_id}",
        policy_profile=policy_profile,
        fail_open=False,
        reason=reason,
        result=ReceiptResult(
            status="denied",
            summary="Channel policy denied requested capability.",
            metadata={
                "policy_envelope_id": policy.id if policy else None,
                "event_id": event_id,
                "requested_capability": capability,
                "channel": event.get("channel"),
                "redacted_fields": ["text"],
            },
        ),
        redacted=True,
        created_at=now,
    )


def _optional_string(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _optional_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None
