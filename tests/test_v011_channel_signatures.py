import builtins
import json
from datetime import UTC, datetime, timedelta

from craik.runtime.channels import webhook_ingress
from craik.runtime.channels.real_adapters import diagnose_channel_adapter
from craik.runtime.channels.webhook_ingress import (
    slack_webhook_signature,
    validate_webhook_request,
    webhook_signature,
)

NOW = datetime(2026, 5, 22, 14, 0, tzinfo=UTC)
SECRET = "webhook-secret"


def _body(event_id: str = "evt_platform", event_type: str = "channel.message") -> bytes:
    return json.dumps(
        {
            "event_id": event_id,
            "event_type": event_type,
            "timestamp": NOW.isoformat(),
            "payload": {"text": "hello"},
        },
        sort_keys=True,
    ).encode("utf-8")


def test_webchat_uses_generic_craik_signature_header() -> None:
    body = _body()

    result = validate_webhook_request(
        body=body,
        headers={"X-Craik-Signature": webhook_signature(body, SECRET)},
        secret=SECRET,
        allowed_event_types={"channel.message"},
        seen_event_ids=set(),
        signature_platform="webchat",
        now=NOW,
    )

    assert result.accepted is True


def test_slack_signature_accepts_happy_path_and_rejects_tampering() -> None:
    body = _body()
    timestamp = str(int(NOW.timestamp()))
    headers = {
        "X-Slack-Request-Timestamp": timestamp,
        "X-Slack-Signature": slack_webhook_signature(body, SECRET, timestamp),
    }

    accepted = validate_webhook_request(
        body=body,
        headers=headers,
        secret=SECRET,
        allowed_event_types={"channel.message"},
        seen_event_ids=set(),
        signature_platform="slack",
        now=NOW,
    )
    tampered = validate_webhook_request(
        body=body.replace(b"hello", b"bye"),
        headers=headers,
        secret=SECRET,
        allowed_event_types={"channel.message"},
        seen_event_ids=set(),
        signature_platform="slack",
        now=NOW,
    )

    assert accepted.accepted is True
    assert tampered.status == "invalid"
    assert tampered.reason == "webhook signature is missing or invalid"


def test_slack_signature_rejects_replay_window() -> None:
    body = _body()
    old_timestamp = str(int((NOW - timedelta(minutes=10)).timestamp()))

    result = validate_webhook_request(
        body=body,
        headers={
            "X-Slack-Request-Timestamp": old_timestamp,
            "X-Slack-Signature": slack_webhook_signature(body, SECRET, old_timestamp),
        },
        secret=SECRET,
        allowed_event_types={"channel.message"},
        seen_event_ids=set(),
        signature_platform="slack",
        now=NOW,
    )

    assert result.status == "invalid"
    assert result.reason == "webhook signature timestamp is outside the allowed window"


def test_telegram_secret_token_accepts_happy_path_and_rejects_tampering() -> None:
    body = _body()

    accepted = validate_webhook_request(
        body=body,
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
        secret=SECRET,
        allowed_event_types={"channel.message"},
        seen_event_ids=set(),
        signature_platform="telegram",
        now=NOW,
    )
    tampered = validate_webhook_request(
        body=body,
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
        secret=SECRET,
        allowed_event_types={"channel.message"},
        seen_event_ids=set(),
        signature_platform="telegram",
        now=NOW,
    )

    assert accepted.accepted is True
    assert tampered.status == "invalid"


def test_discord_native_headers_fail_closed_when_verifier_unavailable() -> None:
    result = validate_webhook_request(
        body=_body(),
        headers={
            "X-Signature-Ed25519": "00",
            "X-Signature-Timestamp": str(int(NOW.timestamp())),
        },
        secret="00",
        allowed_event_types={"channel.message"},
        seen_event_ids=set(),
        signature_platform="discord",
        now=NOW,
    )

    assert result.status == "invalid"
    assert result.reason in {
        "discord webhook signature verifier unavailable",
        "webhook signature is missing or invalid",
    }


def test_discord_verifier_unavailable_reports_correct_error(monkeypatch) -> None:
    original_import = builtins.__import__

    def import_without_verifiers(
        name: str,
        globals=None,
        locals=None,
        fromlist=(),
        level: int = 0,
    ):
        if name.startswith(("nacl", "cryptography")):
            raise ImportError(name)
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(webhook_ingress, "discord_signature_verifier_available", lambda: True)
    monkeypatch.setattr(builtins, "__import__", import_without_verifiers)

    result = validate_webhook_request(
        body=_body(),
        headers={
            "X-Signature-Ed25519": "00",
            "X-Signature-Timestamp": str(int(NOW.timestamp())),
        },
        secret="00",
        allowed_event_types={"channel.message"},
        seen_event_ids=set(),
        signature_platform="discord",
        now=NOW,
    )

    assert result.status == "invalid"
    assert result.reason == "discord webhook signature verifier unavailable"


def test_discord_signature_valid_raises_when_all_verifiers_are_unavailable(monkeypatch) -> None:
    original_import = builtins.__import__

    def import_without_verifiers(
        name: str,
        globals=None,
        locals=None,
        fromlist=(),
        level: int = 0,
    ):
        if name.startswith(("nacl", "cryptography")):
            raise ImportError(name)
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", import_without_verifiers)

    try:
        webhook_ingress._discord_signature_valid(
            body=_body(),
            public_key="00",
            signature="00",
            timestamp=str(int(NOW.timestamp())),
        )
    except webhook_ingress._DiscordVerifierUnavailable:
        pass
    else:
        raise AssertionError("expected Discord verifier unavailable when no backend imports")


def test_discord_invalid_signature_reports_correct_error(monkeypatch) -> None:
    monkeypatch.setattr(webhook_ingress, "discord_signature_verifier_available", lambda: True)
    monkeypatch.setattr(webhook_ingress, "_discord_signature_valid", lambda **_: False)

    result = validate_webhook_request(
        body=_body(),
        headers={
            "X-Signature-Ed25519": "00",
            "X-Signature-Timestamp": str(int(NOW.timestamp())),
        },
        secret="00",
        allowed_event_types={"channel.message"},
        seen_event_ids=set(),
        signature_platform="discord",
        now=NOW,
    )

    assert result.status == "invalid"
    assert result.reason == "webhook signature is missing or invalid"


def test_channel_doctor_warns_when_discord_signature_verifier_unavailable() -> None:
    payload = diagnose_channel_adapter("discord", env={}).as_dict()

    assert any("signature verifier" in warning for warning in payload["warnings"])
