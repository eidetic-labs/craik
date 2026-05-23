"""Webhook ingress validation and parsing for the gateway."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from importlib.util import find_spec
from pathlib import Path
from typing import Any, Literal, Protocol

from craik.contracts.models import CapabilityReceipt, CraikModel, PolicyProfile, ReceiptResult
from craik.runtime.channels.persistence import (
    GatewayArtifactStore,
    persist_gateway_channel_artifacts,
)

WebhookIngressStatus = Literal["accepted", "invalid", "duplicate", "unauthorized"]
WebhookSignaturePlatform = Literal["craik", "webchat", "slack", "telegram", "discord"]
MAX_WEBHOOK_BODY_BYTES = 1024 * 1024
MAX_WEBHOOK_JSON_DEPTH = 32
DEFAULT_WEBHOOK_TIMESTAMP_WINDOW = timedelta(minutes=5)
WEBHOOK_TIMESTAMP_FIELD = "timestamp"


class WebhookReplayStore(Protocol):
    """Persistent replay boundary for webhook event ids."""

    def contains(self, event_id: str) -> bool:
        """Return whether the event id has already been accepted."""

    def add(self, event_id: str) -> None:
        """Record an accepted event id."""


class JsonFileWebhookReplayStore:
    """Small JSON-backed replay store for local gateway deployments."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def contains(self, event_id: str) -> bool:
        return event_id in self._read()

    def add(self, event_id: str) -> None:
        values = self._read()
        values.add(event_id)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(sorted(values), indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _read(self) -> set[str]:
        if not self.path.exists():
            return set()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return set()
        if not isinstance(payload, list):
            return set()
        return {item for item in payload if isinstance(item, str)}


class WebhookIngressResult(CraikModel):
    """Inspectable result of validating one webhook request."""

    status: WebhookIngressStatus
    accepted: bool
    reason: str
    event_id: str | None = None
    event_type: str | None = None
    dispatch_payload: dict[str, Any] = {}


class _DiscordVerifierUnavailable(Exception):
    """Raised when no optional Discord Ed25519 verifier can be imported."""


def validate_webhook_request(
    *,
    body: bytes,
    headers: dict[str, str],
    secret: str,
    allowed_event_types: set[str],
    seen_event_ids: set[str],
    signature_platform: WebhookSignaturePlatform = "craik",
    replay_store: WebhookReplayStore | None = None,
    now: datetime | None = None,
    max_body_bytes: int = MAX_WEBHOOK_BODY_BYTES,
    max_json_depth: int = MAX_WEBHOOK_JSON_DEPTH,
    timestamp_window: timedelta = DEFAULT_WEBHOOK_TIMESTAMP_WINDOW,
) -> WebhookIngressResult:
    """Validate and parse one webhook request without dispatching side effects."""
    if len(body) > max_body_bytes:
        return WebhookIngressResult(
            status="invalid",
            accepted=False,
            reason="webhook body exceeds maximum size",
        )

    signature_failure = _signature_failure(
        body=body,
        headers=headers,
        secret=secret,
        platform=signature_platform,
        now=now or datetime.now(UTC),
        timestamp_window=timestamp_window,
    )
    if signature_failure is not None:
        return WebhookIngressResult(
            status="invalid",
            accepted=False,
            reason=signature_failure,
        )

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return WebhookIngressResult(
            status="invalid",
            accepted=False,
            reason="webhook body is not valid JSON",
        )
    if not isinstance(payload, dict):
        return WebhookIngressResult(
            status="invalid",
            accepted=False,
            reason="webhook body must be a JSON object",
        )
    if _json_depth(payload) > max_json_depth:
        return WebhookIngressResult(
            status="invalid",
            accepted=False,
            reason="webhook body exceeds maximum JSON depth",
        )

    event_id = _optional_string(payload.get("event_id"))
    event_type = _optional_string(payload.get("event_type"))
    timestamp = _optional_datetime(payload.get(WEBHOOK_TIMESTAMP_FIELD))
    if event_id is None or event_type is None or timestamp is None:
        return WebhookIngressResult(
            status="invalid",
            accepted=False,
            reason="webhook event requires event_id, event_type, and timestamp",
        )
    checked_at = now or datetime.now(UTC)
    if timestamp < checked_at - timestamp_window or timestamp > checked_at + timestamp_window:
        return WebhookIngressResult(
            status="invalid",
            accepted=False,
            reason="webhook timestamp is outside the allowed window",
            event_id=event_id,
            event_type=event_type,
        )
    if event_id in seen_event_ids or (replay_store is not None and replay_store.contains(event_id)):
        return WebhookIngressResult(
            status="duplicate",
            accepted=False,
            reason="webhook event was already seen",
            event_id=event_id,
            event_type=event_type,
        )
    if event_type not in allowed_event_types:
        return WebhookIngressResult(
            status="unauthorized",
            accepted=False,
            reason=f"webhook event_type {event_type!r} is not allowed",
            event_id=event_id,
            event_type=event_type,
        )

    seen_event_ids.add(event_id)
    if replay_store is not None:
        replay_store.add(event_id)
    return WebhookIngressResult(
        status="accepted",
        accepted=True,
        reason="webhook event accepted for safe dispatch",
        event_id=event_id,
        event_type=event_type,
        dispatch_payload={
            "event_id": event_id,
            "event_type": event_type,
            "payload": payload.get("payload") if isinstance(payload.get("payload"), dict) else {},
        },
    )


def webhook_ingress_receipt(
    *,
    result: WebhookIngressResult,
    task_id: str,
    actor: str,
    policy_profile: PolicyProfile,
    policy_envelope_id: str,
    created_at: datetime | None = None,
) -> CapabilityReceipt:
    """Build a redacted receipt for a webhook ingress decision."""
    now = created_at or datetime.now(UTC)
    event_id = result.event_id or "unknown"
    return CapabilityReceipt(
        id=f"receipt_webhook_ingress_{result.status}_{event_id}",
        task_id=task_id,
        actor=actor,
        capability="webhook.ingress",
        target=f"webhook:{event_id}",
        policy_profile=policy_profile,
        fail_open=False,
        reason=result.reason,
        result=ReceiptResult(
            status="passed" if result.accepted else "denied",
            summary=f"Webhook ingress {result.status}.",
            metadata={
                "policy_envelope_id": policy_envelope_id,
                "event_id": result.event_id,
                "event_type": result.event_type,
                "ingress_status": result.status,
                "redacted_fields": ["body", "signature", "payload"],
            },
        ),
        redacted=True,
        created_at=now,
    )


def persist_webhook_ingress_receipt(
    store: GatewayArtifactStore,
    *,
    result: WebhookIngressResult,
    task_id: str,
    actor: str,
    policy_profile: PolicyProfile,
    policy_envelope_id: str,
    created_at: datetime | None = None,
) -> CapabilityReceipt:
    """Build and persist the gateway receipt for one webhook ingress decision."""
    receipt = webhook_ingress_receipt(
        result=result,
        task_id=task_id,
        actor=actor,
        policy_profile=policy_profile,
        policy_envelope_id=policy_envelope_id,
        created_at=created_at,
    )
    persist_gateway_channel_artifacts(store, receipt=receipt)
    return receipt


def webhook_signature(body: bytes, secret: str) -> str:
    """Return the expected sha256 webhook signature header value."""
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def slack_webhook_signature(body: bytes, secret: str, timestamp: str) -> str:
    """Return Slack's v0 HMAC signature for one request body."""
    base = b"v0:" + timestamp.encode("utf-8") + b":" + body
    digest = hmac.new(secret.encode("utf-8"), base, hashlib.sha256).hexdigest()
    return f"v0={digest}"


def discord_signature_verifier_available() -> bool:
    """Return whether native Discord Ed25519 verification can run."""
    return find_spec("nacl") is not None or find_spec("cryptography") is not None


def _signature_failure(
    *,
    body: bytes,
    headers: dict[str, str],
    secret: str,
    platform: WebhookSignaturePlatform,
    now: datetime,
    timestamp_window: timedelta,
) -> str | None:
    if platform in {"craik", "webchat"}:
        return _craik_signature_failure(body=body, headers=headers, secret=secret)
    if platform == "slack":
        return _slack_signature_failure(
            body=body,
            headers=headers,
            secret=secret,
            now=now,
            timestamp_window=timestamp_window,
        )
    if platform == "telegram":
        return _secret_token_failure(
            headers=headers,
            secret=secret,
            header_name="X-Telegram-Bot-Api-Secret-Token",
        )
    return _discord_signature_failure(body=body, headers=headers, public_key=secret)


def _craik_signature_failure(*, body: bytes, headers: dict[str, str], secret: str) -> str | None:
    signature_result = _signature_header(headers, "X-Craik-Signature")
    if signature_result is None:
        return "webhook signature is missing or invalid"
    signature, ambiguous = signature_result
    if ambiguous:
        return "webhook signature header is ambiguous"
    if not signature or not _signature_valid(body=body, secret=secret, signature=signature):
        return "webhook signature is missing or invalid"
    return None


def _slack_signature_failure(
    *,
    body: bytes,
    headers: dict[str, str],
    secret: str,
    now: datetime,
    timestamp_window: timedelta,
) -> str | None:
    signature_result = _signature_header(headers, "X-Slack-Signature")
    timestamp_result = _signature_header(headers, "X-Slack-Request-Timestamp")
    if signature_result is None or timestamp_result is None:
        return "webhook signature is missing or invalid"
    signature, signature_ambiguous = signature_result
    timestamp, timestamp_ambiguous = timestamp_result
    if signature_ambiguous or timestamp_ambiguous:
        return "webhook signature header is ambiguous"
    if timestamp is None:
        return "webhook signature is missing or invalid"
    parsed_timestamp = _unix_timestamp(timestamp)
    if parsed_timestamp is None:
        return "webhook signature is missing or invalid"
    if parsed_timestamp < now - timestamp_window or parsed_timestamp > now + timestamp_window:
        return "webhook signature timestamp is outside the allowed window"
    expected = slack_webhook_signature(body, secret, timestamp)
    if not signature or not hmac.compare_digest(signature, expected):
        return "webhook signature is missing or invalid"
    return None


def _secret_token_failure(
    *,
    headers: dict[str, str],
    secret: str,
    header_name: str,
) -> str | None:
    token_result = _signature_header(headers, header_name)
    if token_result is None:
        return "webhook signature is missing or invalid"
    token, ambiguous = token_result
    if ambiguous:
        return "webhook signature header is ambiguous"
    if not token or not hmac.compare_digest(token, secret):
        return "webhook signature is missing or invalid"
    return None


def _discord_signature_failure(
    *,
    body: bytes,
    headers: dict[str, str],
    public_key: str,
) -> str | None:
    signature_result = _signature_header(headers, "X-Signature-Ed25519")
    timestamp_result = _signature_header(headers, "X-Signature-Timestamp")
    if signature_result is None or timestamp_result is None:
        return "webhook signature is missing or invalid"
    signature, signature_ambiguous = signature_result
    timestamp, timestamp_ambiguous = timestamp_result
    if signature_ambiguous or timestamp_ambiguous:
        return "webhook signature header is ambiguous"
    if not discord_signature_verifier_available():
        return "discord webhook signature verifier unavailable"
    try:
        if _discord_signature_valid(
            body=body,
            public_key=public_key,
            signature=signature or "",
            timestamp=timestamp or "",
        ):
            return None
    except _DiscordVerifierUnavailable:
        return "discord webhook signature verifier unavailable"
    return "webhook signature is missing or invalid"


def _discord_signature_valid(
    *,
    body: bytes,
    public_key: str,
    signature: str,
    timestamp: str,
) -> bool:
    message = timestamp.encode("utf-8") + body
    nacl_unavailable = False
    cryptography_unavailable = False
    try:
        from nacl.signing import VerifyKey  # type: ignore[import-not-found]

        VerifyKey(bytes.fromhex(public_key)).verify(message, bytes.fromhex(signature))
        return True
    except ImportError:
        nacl_unavailable = True
    except Exception:
        return False
    try:
        from cryptography.exceptions import InvalidSignature  # type: ignore[import-not-found]
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # type: ignore[import-not-found]
            Ed25519PublicKey,
        )

        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key))
        key.verify(bytes.fromhex(signature), message)
        return True
    except ImportError:
        cryptography_unavailable = True
        if nacl_unavailable:
            raise _DiscordVerifierUnavailable from None
    except (InvalidSignature, ValueError):
        return False
    if cryptography_unavailable:
        return False
    return False


def _signature_valid(*, body: bytes, secret: str, signature: str) -> bool:
    expected = webhook_signature(body, secret)
    return hmac.compare_digest(signature, expected)


def _signature_header(
    headers: dict[str, str],
    header_name: str,
) -> tuple[str | None, bool] | None:
    values = [
        value
        for name, value in headers.items()
        if name.lower() == header_name.lower()
    ]
    if not values:
        return None
    return values[0], len(values) > 1


def _unix_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=UTC)
    except ValueError:
        return None


def _optional_string(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _optional_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed
    return None


def _json_depth(value: Any) -> int:
    if isinstance(value, dict):
        if not value:
            return 1
        return 1 + max(_json_depth(item) for item in value.values())
    if isinstance(value, list):
        if not value:
            return 1
        return 1 + max(_json_depth(item) for item in value)
    return 1
