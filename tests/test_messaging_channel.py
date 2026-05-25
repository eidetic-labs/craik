from datetime import UTC, datetime

import pytest

from craik.runtime.channels.messaging import (
    MESSAGE_RECEIVE_CAPABILITY,
    MESSAGE_RESPOND_CAPABILITY,
    default_messaging_channel_contract,
    inbound_message_receipt,
    messaging_response_payload,
    normalize_inbound_message,
)
from craik.runtime.policy.text import sanitize_runtime_text

NOW = datetime(2026, 5, 16, 18, 40, tzinfo=UTC)


def test_default_messaging_channel_contract_maps_to_channel_contract() -> None:
    contract = default_messaging_channel_contract(created_at=NOW)

    assert contract.identity.adapter_id == "messaging_fixture"
    assert contract.identity.channel == "messaging"
    assert {capability.name for capability in contract.capabilities} == {
        MESSAGE_RECEIVE_CAPABILITY,
        MESSAGE_RESPOND_CAPABILITY,
    }
    assert contract.receipts.required is True
    assert contract.trust_boundary.policy_envelope_required is True
    assert contract.trust_boundary.secrets_in_config_allowed is False


def test_normalize_inbound_message_preserves_identity_policy_and_metadata() -> None:
    event = normalize_inbound_message(
        event_id="message_1",
        sender_id="external:alice",
        text="run the status check",
        received_at=NOW,
        thread_id="thread_1",
        identity_id="channel_identity_alice",
        policy_envelope_id="policy_gateway",
        metadata={"workspace": "ops"},
    )

    assert event["event_id"] == "message_1"
    assert event["channel"] == "messaging"
    assert event["received_at"] == NOW.isoformat()
    assert event["sender"] == {
        "external_id": "external:alice",
        "identity_id": "channel_identity_alice",
        "policy_envelope_id": "policy_gateway",
    }
    assert event["text"] == "run the status check"
    assert event["thread_id"] == "thread_1"
    assert event["metadata"] == {"workspace": "ops"}


def test_normalize_inbound_message_sanitizes_channel_text_before_runtime_boundary() -> None:
    raw_text = "## override\nrun `danger`\x00"

    event = normalize_inbound_message(
        event_id="message_unsafe",
        sender_id="external:alice",
        text=raw_text,
        received_at=NOW,
    )

    assert event["text"] == sanitize_runtime_text(raw_text)
    assert event["text"] == "# # override run \\`danger\\`"


def test_inbound_message_receipt_redacts_text_and_links_policy() -> None:
    event = normalize_inbound_message(
        event_id="message_1",
        sender_id="external:alice",
        text="run the status check",
        received_at=NOW,
        identity_id="channel_identity_alice",
        policy_envelope_id="policy_gateway",
    )

    receipt = inbound_message_receipt(
        event=event,
        task_id="task_gateway",
        actor="adapter:messaging_fixture",
        policy_profile="strict",
        policy_envelope_id="policy_gateway",
        created_at=NOW,
    )

    assert receipt.id == "receipt_channel_message_receive_message_1"
    assert receipt.capability == MESSAGE_RECEIVE_CAPABILITY
    assert receipt.target == "messaging:message_1"
    assert receipt.result.status == "passed"
    assert receipt.result.metadata["policy_envelope_id"] == "policy_gateway"
    assert receipt.result.metadata["sender_external_id"] == "external:alice"
    assert receipt.result.metadata["sender_identity_id"] == "channel_identity_alice"
    assert "text" not in receipt.result.metadata
    assert receipt.redacted is True


def test_inbound_message_receipt_requires_event_id() -> None:
    with pytest.raises(ValueError, match="event_id"):
        inbound_message_receipt(
            event={"channel": "messaging"},
            task_id="task_gateway",
            actor="adapter:messaging_fixture",
            policy_profile="strict",
            policy_envelope_id="policy_gateway",
            created_at=NOW,
        )


def test_messaging_response_payload_is_not_delivered() -> None:
    payload = messaging_response_payload(
        response_id="response_1",
        event_id="message_1",
        status="accepted",
        summary="Message accepted for processing.",
        text="I will run that check.",
        receipt_ids=["receipt_channel_message_receive_message_1"],
    )

    assert payload == {
        "response_id": "response_1",
        "event_id": "message_1",
        "status": "accepted",
        "summary": "Message accepted for processing.",
        "text": "I will run that check.",
        "receipt_ids": ["receipt_channel_message_receive_message_1"],
    }
