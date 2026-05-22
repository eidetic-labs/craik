from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from craik.contracts.models import ChannelIdentityPairing
from craik.contracts.registry import schema_model
from craik.runtime.channels.identity import (
    allows_privileged_ingress,
    pair_channel_identity,
    revoke_channel_identity,
    unpaired_channel_identity,
)

NOW = datetime(2026, 5, 16, 18, 45, tzinfo=UTC)
DEFAULT_EXPIRY = NOW + timedelta(hours=24)


def test_channel_identity_pairing_registers_schema() -> None:
    assert schema_model("craik.channel_identity_pairing") is ChannelIdentityPairing


def test_unpaired_channel_identity_has_no_privileged_authority() -> None:
    pairing = unpaired_channel_identity(
        pairing_id="channel_identity_alice",
        channel="messaging",
        external_id="external:alice",
        service="fixture-chat",
        display_name="Alice",
        created_at=NOW,
    )

    assert pairing.status == "unpaired"
    assert pairing.external_account.channel == "messaging"
    assert pairing.external_account.external_id == "external:alice"
    assert pairing.subject is None
    assert pairing.policy_envelope_id is None
    assert pairing.expires_at == DEFAULT_EXPIRY
    assert allows_privileged_ingress(pairing) is False


def test_paired_channel_identity_requires_audit_and_policy_context() -> None:
    pairing = unpaired_channel_identity(
        pairing_id="channel_identity_alice",
        channel="messaging",
        external_id="external:alice",
        created_at=NOW,
    )
    paired = pair_channel_identity(
        pairing,
        subject="user:alice",
        policy_envelope_id="policy_gateway",
        paired_by="user:maintainer",
        audit_id="receipt_pair_alice",
        paired_at=NOW,
    )

    assert paired.status == "paired"
    assert paired.subject == "user:alice"
    assert paired.policy_envelope_id == "policy_gateway"
    assert paired.paired_by == "user:maintainer"
    assert paired.expires_at == DEFAULT_EXPIRY
    assert paired.audit_ids == ["receipt_pair_alice"]
    assert allows_privileged_ingress(paired, now=NOW) is True


def test_channel_identity_rejects_expired_pairing_token() -> None:
    pairing = unpaired_channel_identity(
        pairing_id="channel_identity_alice",
        channel="messaging",
        external_id="external:alice",
        created_at=NOW,
        expires_at=NOW - timedelta(minutes=1),
    )

    with pytest.raises(ValueError, match="pairing token has expired"):
        pair_channel_identity(
            pairing,
            subject="user:alice",
            policy_envelope_id="policy_gateway",
            paired_by="user:maintainer",
            audit_id="receipt_pair_alice",
            paired_at=NOW,
        )


def test_expired_paired_channel_identity_blocks_ingress() -> None:
    pairing = pair_channel_identity(
        unpaired_channel_identity(
            pairing_id="channel_identity_alice",
            channel="messaging",
            external_id="external:alice",
            created_at=NOW,
            expires_at=NOW + timedelta(minutes=30),
        ),
        subject="user:alice",
        policy_envelope_id="policy_gateway",
        paired_by="user:maintainer",
        audit_id="receipt_pair_alice",
        paired_at=NOW,
    )

    assert allows_privileged_ingress(pairing, now=NOW + timedelta(minutes=31)) is False


def test_revoked_channel_identity_preserves_audit_but_blocks_ingress() -> None:
    pairing = pair_channel_identity(
        unpaired_channel_identity(
            pairing_id="channel_identity_alice",
            channel="messaging",
            external_id="external:alice",
            created_at=NOW,
        ),
        subject="user:alice",
        policy_envelope_id="policy_gateway",
        paired_by="user:maintainer",
        audit_id="receipt_pair_alice",
        paired_at=NOW,
    )

    revoked = revoke_channel_identity(
        pairing,
        revoked_by="user:maintainer",
        reason="operator removed channel access",
        audit_id="receipt_revoke_alice",
        revoked_at=NOW,
    )

    assert revoked.status == "revoked"
    assert revoked.subject == "user:alice"
    assert revoked.policy_envelope_id == "policy_gateway"
    assert revoked.revoked_by == "user:maintainer"
    assert revoked.revocation_reason == "operator removed channel access"
    assert revoked.audit_ids == ["receipt_pair_alice", "receipt_revoke_alice"]
    assert allows_privileged_ingress(revoked) is False


def test_unpaired_channel_identity_rejects_authority_fields() -> None:
    with pytest.raises(ValidationError, match="must not carry authority"):
        ChannelIdentityPairing.model_validate(
            {
                "schema": "craik.channel_identity_pairing",
                "version": "0.1.0",
                "id": "channel_identity_alice",
                "external_account": {
                    "channel": "messaging",
                    "external_id": "external:alice",
                },
                "status": "unpaired",
                "subject": "user:alice",
                "expires_at": DEFAULT_EXPIRY,
                "created_at": NOW,
                "updated_at": NOW,
            }
        )


def test_paired_channel_identity_rejects_missing_audit_link() -> None:
    with pytest.raises(ValidationError, match="audit_ids"):
        ChannelIdentityPairing.model_validate(
            {
                "schema": "craik.channel_identity_pairing",
                "version": "0.1.0",
                "id": "channel_identity_alice",
                "external_account": {
                    "channel": "messaging",
                    "external_id": "external:alice",
                },
                "status": "paired",
                "subject": "user:alice",
                "policy_envelope_id": "policy_gateway",
                "paired_at": NOW,
                "paired_by": "user:maintainer",
                "expires_at": DEFAULT_EXPIRY,
                "created_at": NOW,
                "updated_at": NOW,
            }
        )


def test_revoked_channel_identity_requires_revocation_audit_fields() -> None:
    with pytest.raises(ValidationError, match="revocation audit"):
        ChannelIdentityPairing.model_validate(
            {
                "schema": "craik.channel_identity_pairing",
                "version": "0.1.0",
                "id": "channel_identity_alice",
                "external_account": {
                    "channel": "messaging",
                    "external_id": "external:alice",
                },
                "status": "revoked",
                "subject": "user:alice",
                "policy_envelope_id": "policy_gateway",
                "paired_at": NOW,
                "paired_by": "user:maintainer",
                "audit_ids": ["receipt_pair_alice"],
                "expires_at": DEFAULT_EXPIRY,
                "created_at": NOW,
                "updated_at": NOW,
            }
        )
