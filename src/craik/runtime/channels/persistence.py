"""Persistence helpers for gateway and channel runtime artifacts."""

from __future__ import annotations

from typing import Protocol

from craik.contracts.models import (
    CapabilityReceipt,
    ChannelAdapterContract,
    ChannelAllowlist,
    ChannelIdentityPairing,
    GatewaySchedule,
    PolicyEnvelope,
    ScheduledAutomation,
)


class GatewayArtifactStore(Protocol):
    """Store surface required by gateway channel persistence helpers."""

    def put_channel_adapter_contract(self, contract: ChannelAdapterContract) -> None: ...
    def put_channel_identity_pairing(self, pairing: ChannelIdentityPairing) -> None: ...
    def put_channel_allowlist(self, allowlist: ChannelAllowlist) -> None: ...
    def put_gateway_receipt(self, receipt: CapabilityReceipt) -> CapabilityReceipt: ...
    def put_gateway_schedule(self, schedule: GatewaySchedule) -> None: ...
    def put_scheduled_automation(self, automation: ScheduledAutomation) -> None: ...
    def put_channel_policy_envelope(self, policy: PolicyEnvelope) -> None: ...


def persist_gateway_channel_artifacts(
    store: GatewayArtifactStore,
    *,
    adapter_contract: ChannelAdapterContract | None = None,
    identity_pairing: ChannelIdentityPairing | None = None,
    allowlist: ChannelAllowlist | None = None,
    receipt: CapabilityReceipt | None = None,
    schedule: GatewaySchedule | None = None,
    automation: ScheduledAutomation | None = None,
    policy: PolicyEnvelope | None = None,
) -> None:
    """Persist gateway/channel artifacts produced by one ingress or scheduling flow."""
    if adapter_contract is not None:
        store.put_channel_adapter_contract(adapter_contract)
    if identity_pairing is not None:
        store.put_channel_identity_pairing(identity_pairing)
    if allowlist is not None:
        store.put_channel_allowlist(allowlist)
    if receipt is not None:
        store.put_gateway_receipt(receipt)
    if schedule is not None:
        store.put_gateway_schedule(schedule)
    if automation is not None:
        store.put_scheduled_automation(automation)
    if policy is not None:
        store.put_channel_policy_envelope(policy)
