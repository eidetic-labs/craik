"""Gateway and channel contract store methods."""

# ruff: noqa: F403,F405,I001

from __future__ import annotations

from typing import Protocol, cast

from .base import *


class _WorkStoreSurface(Protocol):
    def put_receipt(self, receipt: CapabilityReceipt) -> CapabilityReceipt:
        raise NotImplementedError

    def get_receipt(self, receipt_id: str) -> CapabilityReceipt | None:
        raise NotImplementedError

    def list_receipts(self) -> list[CapabilityReceipt]:
        raise NotImplementedError

    def put_policy_envelope(self, policy: PolicyEnvelope) -> None:
        raise NotImplementedError

    def get_policy_envelope(self, policy_id: str) -> PolicyEnvelope | None:
        raise NotImplementedError

    def list_policy_envelopes(self) -> list[PolicyEnvelope]:
        raise NotImplementedError


class GatewayStoreMixin(LocalStoreCore):
    def put_channel_adapter_contract(self, contract: ChannelAdapterContract) -> None:
        """Persist a channel adapter contract."""
        self.put_contract(contract)

    def get_channel_adapter_contract(
        self,
        contract_id: str,
    ) -> ChannelAdapterContract | None:
        """Load a channel adapter contract by id."""
        contract = self.get_contract("craik.channel_adapter_contract", contract_id)
        return _cast_optional(ChannelAdapterContract, contract)

    def list_channel_adapter_contracts(self) -> list[ChannelAdapterContract]:
        """List channel adapter contracts."""
        return _cast_list(
            ChannelAdapterContract,
            self.list_contracts("craik.channel_adapter_contract"),
        )

    def put_channel_identity_pairing(self, pairing: ChannelIdentityPairing) -> None:
        """Persist a channel identity pairing."""
        self.put_contract(pairing)

    def get_channel_identity_pairing(self, pairing_id: str) -> ChannelIdentityPairing | None:
        """Load a channel identity pairing by id."""
        contract = self.get_contract("craik.channel_identity_pairing", pairing_id)
        return _cast_optional(ChannelIdentityPairing, contract)

    def list_channel_identity_pairings(self) -> list[ChannelIdentityPairing]:
        """List channel identity pairings."""
        return _cast_list(
            ChannelIdentityPairing,
            self.list_contracts("craik.channel_identity_pairing"),
        )

    def put_channel_allowlist(self, allowlist: ChannelAllowlist) -> None:
        """Persist a channel allowlist."""
        self.put_contract(allowlist)

    def get_channel_allowlist(self, allowlist_id: str) -> ChannelAllowlist | None:
        """Load a channel allowlist by id."""
        contract = self.get_contract("craik.channel_allowlist", allowlist_id)
        return _cast_optional(ChannelAllowlist, contract)

    def list_channel_allowlists(self) -> list[ChannelAllowlist]:
        """List channel allowlists."""
        return _cast_list(ChannelAllowlist, self.list_contracts("craik.channel_allowlist"))

    def put_gateway_receipt(self, receipt: CapabilityReceipt) -> CapabilityReceipt:
        """Persist a redacted gateway receipt."""
        return cast(_WorkStoreSurface, self).put_receipt(receipt)

    def get_gateway_receipt(self, receipt_id: str) -> CapabilityReceipt | None:
        """Load a gateway receipt by id."""
        return cast(_WorkStoreSurface, self).get_receipt(receipt_id)

    def list_gateway_receipts(self, *, channel_id: str | None = None) -> list[CapabilityReceipt]:
        """List gateway receipts, optionally filtered by receipt metadata channel."""
        receipts = [
            receipt
            for receipt in cast(_WorkStoreSurface, self).list_receipts()
            if str(receipt.capability).startswith(("gateway.", "channel.", "webhook."))
            or str(receipt.result.metadata.get("gateway_action", "")).strip()
        ]
        if channel_id is None:
            return receipts
        return [
            receipt
            for receipt in receipts
            if receipt.result.metadata.get("channel") == channel_id
        ]

    def put_gateway_schedule(self, schedule: GatewaySchedule) -> None:
        """Persist a gateway schedule contract."""
        self.put_contract(schedule)

    def get_gateway_schedule(self, schedule_id: str) -> GatewaySchedule | None:
        """Load a gateway schedule by id."""
        contract = self.get_contract("craik.gateway_schedule", schedule_id)
        return _cast_optional(GatewaySchedule, contract)

    def list_gateway_schedules(self) -> list[GatewaySchedule]:
        """List gateway schedules."""
        return _cast_list(GatewaySchedule, self.list_contracts("craik.gateway_schedule"))

    def put_scheduled_automation(self, automation: ScheduledAutomation) -> None:
        """Persist a scheduled automation contract."""
        self.put_contract(automation)

    def get_scheduled_automation(self, automation_id: str) -> ScheduledAutomation | None:
        """Load a scheduled automation by id."""
        contract = self.get_contract("craik.scheduled_automation", automation_id)
        return _cast_optional(ScheduledAutomation, contract)

    def list_scheduled_automations(self) -> list[ScheduledAutomation]:
        """List scheduled automations."""
        return _cast_list(
            ScheduledAutomation,
            self.list_contracts("craik.scheduled_automation"),
        )

    def put_channel_policy_envelope(self, policy: PolicyEnvelope) -> None:
        """Persist the policy envelope selected for channel ingress."""
        cast(_WorkStoreSurface, self).put_policy_envelope(policy)

    def get_channel_policy_envelope(self, policy_id: str) -> PolicyEnvelope | None:
        """Load a channel policy envelope by id."""
        return cast(_WorkStoreSurface, self).get_policy_envelope(policy_id)

    def list_channel_policy_envelopes(self) -> list[PolicyEnvelope]:
        """List policy envelopes that grant channel or gateway capabilities."""
        return [
            policy
            for policy in cast(_WorkStoreSurface, self).list_policy_envelopes()
            if any(
                capability.startswith(("channel.", "gateway."))
                for capability in policy.allowed_capabilities
            )
        ]
