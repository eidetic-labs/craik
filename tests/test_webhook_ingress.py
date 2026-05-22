import json
from datetime import UTC, datetime, timedelta

from craik.runtime.channels.webhook_ingress import (
    JsonFileWebhookReplayStore,
    validate_webhook_request,
    webhook_ingress_receipt,
    webhook_signature,
)

NOW = datetime(2026, 5, 16, 19, 15, tzinfo=UTC)
SECRET = "webhook-secret"


def _body(event_id: str = "webhook_1", event_type: str = "message.created") -> bytes:
    return json.dumps(
        {
            "event_id": event_id,
            "event_type": event_type,
            "timestamp": NOW.isoformat(),
            "payload": {"text": "run status"},
        }
    ).encode("utf-8")


def _headers(body: bytes) -> dict[str, str]:
    return {"X-Craik-Signature": webhook_signature(body, SECRET)}


def test_webhook_ingress_accepts_valid_authorized_event() -> None:
    body = _body()

    result = validate_webhook_request(
        body=body,
        headers=_headers(body),
        secret=SECRET,
        allowed_event_types={"message.created"},
        seen_event_ids=set(),
        now=NOW,
    )

    assert result.accepted is True
    assert result.status == "accepted"
    assert result.event_id == "webhook_1"
    assert result.event_type == "message.created"
    assert result.dispatch_payload["payload"] == {"text": "run status"}


def test_webhook_ingress_rejects_invalid_signature() -> None:
    result = validate_webhook_request(
        body=_body(),
        headers={"X-Craik-Signature": "sha256:bad"},
        secret=SECRET,
        allowed_event_types={"message.created"},
        seen_event_ids=set(),
        now=NOW,
    )

    assert result.accepted is False
    assert result.status == "invalid"
    assert result.reason == "webhook signature is missing or invalid"


def test_webhook_ingress_rejects_duplicate_event() -> None:
    body = _body()

    result = validate_webhook_request(
        body=body,
        headers=_headers(body),
        secret=SECRET,
        allowed_event_types={"message.created"},
        seen_event_ids={"webhook_1"},
        now=NOW,
    )

    assert result.accepted is False
    assert result.status == "duplicate"
    assert result.event_id == "webhook_1"


def test_webhook_ingress_rejects_unauthorized_event_type() -> None:
    body = _body(event_type="workspace.deleted")

    result = validate_webhook_request(
        body=body,
        headers=_headers(body),
        secret=SECRET,
        allowed_event_types={"message.created"},
        seen_event_ids=set(),
        now=NOW,
    )

    assert result.accepted is False
    assert result.status == "unauthorized"
    assert "not allowed" in result.reason


def test_webhook_ingress_rejects_invalid_json_shape() -> None:
    body = b"[]"

    result = validate_webhook_request(
        body=body,
        headers=_headers(body),
        secret=SECRET,
        allowed_event_types={"message.created"},
        seen_event_ids=set(),
        now=NOW,
    )

    assert result.accepted is False
    assert result.status == "invalid"
    assert result.reason == "webhook body must be a JSON object"


def test_webhook_ingress_receipt_redacts_payload_and_signature() -> None:
    body = _body()
    result = validate_webhook_request(
        body=body,
        headers=_headers(body),
        secret=SECRET,
        allowed_event_types={"message.created"},
        seen_event_ids=set(),
        now=NOW,
    )

    receipt = webhook_ingress_receipt(
        result=result,
        task_id="task_gateway",
        actor="gateway:webhook",
        policy_profile="strict",
        policy_envelope_id="policy_gateway",
        created_at=NOW,
    )

    assert receipt.result.status == "passed"
    assert receipt.capability == "webhook.ingress"
    assert receipt.result.metadata["event_id"] == "webhook_1"
    assert receipt.result.metadata["event_type"] == "message.created"
    assert "payload" not in receipt.result.metadata
    assert "signature" not in receipt.result.metadata


def test_webhook_ingress_records_accepted_event_for_replay_detection() -> None:
    body = _body()
    seen: set[str] = set()

    first = validate_webhook_request(
        body=body,
        headers=_headers(body),
        secret=SECRET,
        allowed_event_types={"message.created"},
        seen_event_ids=seen,
        now=NOW,
    )
    second = validate_webhook_request(
        body=body,
        headers=_headers(body),
        secret=SECRET,
        allowed_event_types={"message.created"},
        seen_event_ids=seen,
        now=NOW,
    )

    assert first.accepted is True
    assert seen == {"webhook_1"}
    assert second.status == "duplicate"


def test_webhook_ingress_persists_replay_detection_across_store_instances(tmp_path) -> None:
    body = _body(event_id="webhook_persisted")
    path = tmp_path / "webhooks" / "seen.json"

    first = validate_webhook_request(
        body=body,
        headers=_headers(body),
        secret=SECRET,
        allowed_event_types={"message.created"},
        seen_event_ids=set(),
        replay_store=JsonFileWebhookReplayStore(path),
        now=NOW,
    )
    second = validate_webhook_request(
        body=body,
        headers=_headers(body),
        secret=SECRET,
        allowed_event_types={"message.created"},
        seen_event_ids=set(),
        replay_store=JsonFileWebhookReplayStore(path),
        now=NOW,
    )

    assert first.accepted is True
    assert second.status == "duplicate"


def test_webhook_ingress_rejects_oversized_body_before_signature() -> None:
    result = validate_webhook_request(
        body=b"{}",
        headers={},
        secret=SECRET,
        allowed_event_types={"message.created"},
        seen_event_ids=set(),
        max_body_bytes=1,
        now=NOW,
    )

    assert result.status == "invalid"
    assert result.reason == "webhook body exceeds maximum size"


def test_webhook_ingress_rejects_stale_timestamp() -> None:
    body = json.dumps(
        {
            "event_id": "webhook_stale",
            "event_type": "message.created",
            "timestamp": (NOW - timedelta(minutes=6)).isoformat(),
        }
    ).encode("utf-8")

    result = validate_webhook_request(
        body=body,
        headers=_headers(body),
        secret=SECRET,
        allowed_event_types={"message.created"},
        seen_event_ids=set(),
        now=NOW,
    )

    assert result.status == "invalid"
    assert result.reason == "webhook timestamp is outside the allowed window"


def test_webhook_ingress_rejects_deeply_nested_json() -> None:
    payload = {
        "event_id": "webhook_deep",
        "event_type": "message.created",
        "timestamp": NOW.isoformat(),
    }
    for _ in range(4):
        payload = {"payload": payload}
    body = json.dumps(payload).encode("utf-8")

    result = validate_webhook_request(
        body=body,
        headers=_headers(body),
        secret=SECRET,
        allowed_event_types={"message.created"},
        seen_event_ids=set(),
        max_json_depth=3,
        now=NOW,
    )

    assert result.status == "invalid"
    assert result.reason == "webhook body exceeds maximum JSON depth"


def test_webhook_ingress_rejects_ambiguous_signature_header() -> None:
    body = _body(event_id="webhook_ambiguous")

    result = validate_webhook_request(
        body=body,
        headers={
            "X-Craik-Signature": webhook_signature(body, SECRET),
            "x-craik-signature": webhook_signature(body, SECRET),
        },
        secret=SECRET,
        allowed_event_types={"message.created"},
        seen_event_ids=set(),
        now=NOW,
    )

    assert result.status == "invalid"
    assert result.reason == "webhook signature header is ambiguous"
