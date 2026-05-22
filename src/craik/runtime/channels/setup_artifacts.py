"""Persistent setup artifacts for real channel adapters."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from craik.contracts.models import (
    ChannelAdapterContract,
    ChannelAllowlist,
    ChannelIdentityPairing,
    PolicyEnvelope,
)
from craik.runtime.channels.identity import pair_channel_identity, unpaired_channel_identity
from craik.runtime.channels.policy import (
    DEFAULT_CHANNEL_ALLOWED_CAPABILITIES,
    DEFAULT_CHANNEL_DENIED_CAPABILITIES,
)
from craik.runtime.channels.real_adapters import (
    RealChannelService,
    default_channel_allowlist,
    real_channel_adapter_contract,
)

CHANNEL_PAIRING_TTL = timedelta(days=365)


def channel_setup_artifacts(
    service: RealChannelService,
    *,
    operator_subject: str,
    created_at: datetime | None = None,
) -> tuple[ChannelAdapterContract, ChannelIdentityPairing, ChannelAllowlist, PolicyEnvelope]:
    """Build the durable artifacts installed by ``craik channels setup``."""
    now = created_at or datetime.now(UTC)
    policy = channel_setup_policy_envelope(
        service,
        operator_subject=operator_subject,
        created_at=now,
    )
    pairing = channel_setup_identity_pairing(
        service,
        operator_subject=operator_subject,
        policy_envelope_id=policy.id,
        created_at=now,
    )
    allowlist = default_channel_allowlist(
        service,
        sender_external_ids=[pairing.external_account.external_id],
        workspace_ids=[_default_workspace(service)],
        created_at=now,
    )
    return real_channel_adapter_contract(service, created_at=now), pairing, allowlist, policy


def channel_setup_identity_pairing(
    service: RealChannelService,
    *,
    operator_subject: str,
    policy_envelope_id: str,
    created_at: datetime | None = None,
) -> ChannelIdentityPairing:
    """Build the initial operator-owned pairing for a configured adapter."""
    now = created_at or datetime.now(UTC)
    external_id = f"{service}:{operator_subject}"
    return pair_channel_identity(
        unpaired_channel_identity(
            pairing_id=f"channel_pairing_{service}",
            channel="messaging",
            external_id=external_id,
            service=service,
            display_name=f"{service} operator bootstrap",
            created_at=now,
            expires_at=now + CHANNEL_PAIRING_TTL,
        ),
        subject=operator_subject,
        policy_envelope_id=policy_envelope_id,
        paired_by=operator_subject,
        audit_id=f"receipt_channel_setup_{service}",
        paired_at=now,
        expires_at=now + CHANNEL_PAIRING_TTL,
    )


def channel_setup_policy_envelope(
    service: RealChannelService,
    *,
    operator_subject: str,
    created_at: datetime | None = None,
) -> PolicyEnvelope:
    """Build the least-privilege policy envelope installed for one adapter."""
    _ = created_at
    return PolicyEnvelope(
        id=f"policy_channel_{service}",
        task_id=f"task_channel_setup_{service}",
        actor=operator_subject,
        profile="strict",
        fail_open=False,
        allowed_capabilities=list(DEFAULT_CHANNEL_ALLOWED_CAPABILITIES),
        denied_capabilities=list(DEFAULT_CHANNEL_DENIED_CAPABILITIES),
        approval_required=["channel.message.respond"],
        verification_required=["channel.allowlist", "channel.identity_pairing"],
        handoff_required=True,
        receipt_required=True,
        redaction_required=True,
        required_operator=True,
        allowed_operator_subjects=[operator_subject],
    )


def _default_workspace(service: RealChannelService) -> str:
    if service == "webchat":
        return "local-browser"
    return service
