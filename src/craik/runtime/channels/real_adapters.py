"""First real messaging channel adapter boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from craik.contracts.models import (
    CapabilityReceipt,
    ChannelAdapterContract,
    ChannelAllowlist,
    PolicyProfile,
    ReceiptResult,
)
from craik.runtime.channels.messaging import (
    MESSAGE_RECEIVE_CAPABILITY,
    MESSAGE_RESPOND_CAPABILITY,
    messaging_response_payload,
    normalize_inbound_message,
)
from craik.runtime.secrets import SecretNotFoundError, SecretRef, SecretResolver
from craik.runtime.shell.credential_storage import credential_storage_status

RealChannelService = Literal["webchat", "telegram", "discord", "slack"]


@dataclass(frozen=True)
class RealChannelAdapterSpec:
    """Static metadata for one supported channel adapter."""

    service: RealChannelService
    adapter_id: str
    name: str
    token_env_var: str
    default_workspace: str
    setup_hint: str


@dataclass(frozen=True)
class ChannelSetupPlan:
    """Redacted setup plan for installing one channel adapter."""

    service: RealChannelService
    adapter_id: str
    secret_ref: SecretRef
    allowlist_id: str
    policy_envelope_id: str
    pairing_required: bool
    default_posture: str
    diagnostics: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        return {
            "service": self.service,
            "adapter_id": self.adapter_id,
            "secret_ref": {"env_var": self.secret_ref.env_var},
            "allowlist_id": self.allowlist_id,
            "policy_envelope_id": self.policy_envelope_id,
            "pairing_required": self.pairing_required,
            "default_posture": self.default_posture,
            "diagnostics": self.diagnostics,
        }


@dataclass(frozen=True)
class ChannelDiagnostic:
    """Redacted diagnostic status for one adapter."""

    service: RealChannelService
    configured: bool
    token_resolved: bool
    credential_backend: dict[str, object]
    pairing_required: bool
    allowlist_default: str
    warnings: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "service": self.service,
            "configured": self.configured,
            "token_resolved": self.token_resolved,
            "credential_backend": self.credential_backend,
            "pairing_required": self.pairing_required,
            "allowlist_default": self.allowlist_default,
            "warnings": list(self.warnings),
        }


REAL_CHANNEL_ADAPTERS: dict[RealChannelService, RealChannelAdapterSpec] = {
    "webchat": RealChannelAdapterSpec(
        service="webchat",
        adapter_id="webchat_adapter",
        name="WebChat Local Browser Adapter",
        token_env_var="CRAIK_WEBCHAT_TOKEN",
        default_workspace="local-browser",
        setup_hint="Use the local dashboard WebChat surface with a generated bearer token.",
    ),
    "telegram": RealChannelAdapterSpec(
        service="telegram",
        adapter_id="telegram_adapter",
        name="Telegram Bot Adapter",
        token_env_var="CRAIK_TELEGRAM_BOT_TOKEN",
        default_workspace="telegram",
        setup_hint="Create a Telegram bot token and expose it through CRAIK_TELEGRAM_BOT_TOKEN.",
    ),
    "discord": RealChannelAdapterSpec(
        service="discord",
        adapter_id="discord_adapter",
        name="Discord Bot Adapter",
        token_env_var="CRAIK_DISCORD_BOT_TOKEN",
        default_workspace="discord",
        setup_hint="Create a Discord bot token and expose it through CRAIK_DISCORD_BOT_TOKEN.",
    ),
    "slack": RealChannelAdapterSpec(
        service="slack",
        adapter_id="slack_adapter",
        name="Slack App Adapter",
        token_env_var="CRAIK_SLACK_BOT_TOKEN",
        default_workspace="slack",
        setup_hint="Create a Slack bot token and expose it through CRAIK_SLACK_BOT_TOKEN.",
    ),
}


def supported_real_channel_services() -> list[RealChannelService]:
    """Return supported concrete channel services in stable display order."""
    return ["webchat", "telegram", "discord", "slack"]


def real_channel_adapter_contract(
    service: RealChannelService,
    *,
    created_at: datetime | None = None,
) -> ChannelAdapterContract:
    """Return the policy-bound adapter contract for one real channel."""
    spec = _spec(service)
    return ChannelAdapterContract.model_validate(
        {
            "id": f"channel_adapter_{spec.service}",
            "identity": {
                "adapter_id": spec.adapter_id,
                "channel": "messaging",
                "name": spec.name,
                "adapter_version": "0.11.0",
                "service": spec.service,
            },
            "capabilities": [
                {
                    "name": MESSAGE_RECEIVE_CAPABILITY,
                    "direction": "inbound",
                    "description": f"Receive normalized {spec.service} messages.",
                    "grant_required": True,
                    "receipt_required": True,
                },
                {
                    "name": MESSAGE_RESPOND_CAPABILITY,
                    "direction": "outbound",
                    "description": f"Deliver redacted responses to {spec.service}.",
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
                "metadata": {"service": spec.service, "identity_model": "pair before authority"},
            },
            "outbound_response": {
                "fields": ["response_id", "event_id", "status", "summary", "text", "receipt_ids"],
                "redacted_fields": ["text"],
                "metadata": {"delivery": "provider transport boundary emits receipts"},
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
                    f"{spec.name} stores only a secret reference in Craik config.",
                    "Unknown senders are denied until paired and allowlisted.",
                    "Outbound delivery success and failure both emit redacted receipts.",
                ],
            },
            "docs": ["docs/guides/channel-adapters.md", "docs/security/channel-adapters.md"],
            "created_at": created_at or datetime.now(UTC),
        }
    )


def channel_setup_plan(
    service: RealChannelService,
    *,
    env: dict[str, str] | None = None,
) -> ChannelSetupPlan:
    """Return a redacted setup plan without storing provider tokens."""
    spec = _spec(service)
    diagnostic = diagnose_channel_adapter(service, env=env)
    return ChannelSetupPlan(
        service=service,
        adapter_id=spec.adapter_id,
        secret_ref=SecretRef(env_var=spec.token_env_var),
        allowlist_id=f"allowlist_{service}",
        policy_envelope_id=f"policy_channel_{service}",
        pairing_required=True,
        default_posture="deny unknown senders; pair and allowlist before privileged ingress",
        diagnostics=diagnostic.as_dict(),
    )


def default_channel_allowlist(
    service: RealChannelService,
    *,
    sender_external_ids: list[str] | None = None,
    workspace_ids: list[str] | None = None,
    created_at: datetime | None = None,
) -> ChannelAllowlist:
    """Build a deny-by-default allowlist scoped to one real adapter service."""
    now = created_at or datetime.now(UTC)
    senders = sender_external_ids or []
    workspaces = workspace_ids or []
    rules = []
    if senders or workspaces:
        rules.append(
            {
                "id": f"{service}_paired_sender",
                "description": f"Allow paired {service} senders in configured workspace.",
                "channel": "messaging",
                "service": service,
                "sender_external_ids": senders,
                "workspace_ids": workspaces,
                "enabled": True,
            }
        )
    return ChannelAllowlist.model_validate(
        {
            "id": f"allowlist_{service}",
            "channel": "messaging",
            "default_action": "deny",
            "rules": rules,
            "audit_required": True,
            "denial_capability": "channel.ingress.denied",
            "created_at": now,
            "updated_at": now,
        }
    )


def normalize_real_channel_inbound(
    service: RealChannelService,
    raw_event: dict[str, Any],
    *,
    received_at: datetime | None = None,
    identity_id: str | None = None,
    policy_envelope_id: str | None = None,
) -> dict[str, Any]:
    """Normalize one provider event into Craik's messaging event shape."""
    spec = _spec(service)
    extracted = _extract_provider_event(service, raw_event)
    metadata = {
        "service": service,
        "workspace": extracted["workspace"] or spec.default_workspace,
        "provider_event_id": extracted["provider_event_id"],
    }
    metadata.update(extracted["metadata"])
    return normalize_inbound_message(
        event_id=f"{service}_{extracted['event_id']}",
        sender_id=f"{service}:{extracted['sender_id']}",
        text=extracted["text"],
        received_at=received_at,
        thread_id=extracted["thread_id"],
        identity_id=identity_id,
        policy_envelope_id=policy_envelope_id,
        metadata=metadata,
    )


def channel_outbound_response(
    service: RealChannelService,
    *,
    response_id: str,
    event_id: str,
    summary: str,
    text: str | None = None,
    receipt_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Build a provider-scoped outbound payload before transport delivery."""
    payload = messaging_response_payload(
        response_id=response_id,
        event_id=event_id,
        status="queued",
        summary=summary,
        text=text,
        receipt_ids=receipt_ids,
    )
    payload["service"] = service
    return payload


def outbound_delivery_receipt(
    service: RealChannelService,
    *,
    response: dict[str, Any],
    task_id: str,
    actor: str,
    policy_profile: PolicyProfile,
    policy_envelope_id: str,
    delivered: bool,
    error: str | None = None,
    created_at: datetime | None = None,
) -> CapabilityReceipt:
    """Build a redacted receipt for outbound delivery success or failure."""
    now = created_at or datetime.now(UTC)
    response_id = _required_string(response, "response_id")
    event_id = _required_string(response, "event_id")
    return CapabilityReceipt(
        id=f"receipt_channel_message_respond_{service}_{response_id}",
        task_id=task_id,
        actor=actor,
        capability=MESSAGE_RESPOND_CAPABILITY,
        target=f"{service}:{event_id}",
        policy_profile=policy_profile,
        fail_open=False,
        reason="Channel response delivery completed." if delivered else "Channel delivery failed.",
        result=ReceiptResult(
            status="passed" if delivered else "failed",
            summary="Channel response delivered." if delivered else "Channel response failed.",
            metadata={
                "policy_envelope_id": policy_envelope_id,
                "service": service,
                "event_id": event_id,
                "response_id": response_id,
                "delivery_error": error,
                "redacted_fields": ["text"],
            },
        ),
        redacted=True,
        created_at=now,
    )


def diagnose_channel_adapter(
    service: RealChannelService,
    *,
    env: dict[str, str] | None = None,
    resolver: SecretResolver | None = None,
) -> ChannelDiagnostic:
    """Return redacted readiness diagnostics for one adapter."""
    spec = _spec(service)
    values = env or {}
    secret_ref = SecretRef(env_var=spec.token_env_var)
    token_resolved = False
    if env is not None and values.get(spec.token_env_var):
        token_resolved = True
    else:
        try:
            (resolver or SecretResolver()).resolve(secret_ref)
            token_resolved = True
        except SecretNotFoundError:
            token_resolved = False
    credential_status = credential_storage_status(env).as_dict()
    warnings = []
    if not token_resolved:
        warnings.append(f"missing secret reference {spec.token_env_var}")
    if not credential_status["secure"]:
        warnings.append("credential backend is not OS-secure; keep token refs out of config")
    return ChannelDiagnostic(
        service=service,
        configured=token_resolved,
        token_resolved=token_resolved,
        credential_backend=credential_status,
        pairing_required=True,
        allowlist_default="deny",
        warnings=tuple(warnings),
    )


def _spec(service: RealChannelService) -> RealChannelAdapterSpec:
    try:
        return REAL_CHANNEL_ADAPTERS[service]
    except KeyError:
        raise ValueError(f"unsupported channel service: {service}") from None


def _extract_provider_event(
    service: RealChannelService,
    raw_event: dict[str, Any],
) -> dict[str, Any]:
    if service == "webchat":
        return {
            "event_id": _string(raw_event, "message_id", fallback="event_id"),
            "provider_event_id": _string(raw_event, "message_id", fallback="event_id"),
            "sender_id": _string(raw_event, "user_id", fallback="sender_id"),
            "text": _string(raw_event, "text", fallback="message"),
            "thread_id": _optional_string(raw_event.get("session_id")),
            "workspace": _optional_string(raw_event.get("origin")),
            "metadata": {"surface": "local_browser"},
        }
    if service == "telegram":
        message = _dict(raw_event.get("message"))
        sender = _dict(message.get("from"))
        chat = _dict(message.get("chat"))
        message_id = str(message.get("message_id") or raw_event.get("update_id") or "unknown")
        return {
            "event_id": message_id,
            "provider_event_id": str(raw_event.get("update_id") or message_id),
            "sender_id": str(sender.get("id") or "unknown"),
            "text": _optional_string(message.get("text")) or "",
            "thread_id": str(chat.get("id") or "unknown"),
            "workspace": str(chat.get("id") or "telegram"),
            "metadata": {"chat_type": _optional_string(chat.get("type"))},
        }
    if service == "discord":
        author = _dict(raw_event.get("author"))
        return {
            "event_id": _string(raw_event, "id"),
            "provider_event_id": _string(raw_event, "id"),
            "sender_id": str(author.get("id") or raw_event.get("author_id") or "unknown"),
            "text": _string(raw_event, "content"),
            "thread_id": _optional_string(raw_event.get("channel_id")),
            "workspace": _optional_string(raw_event.get("guild_id")) or "dm",
            "metadata": {"guild_id": _optional_string(raw_event.get("guild_id"))},
        }
    event = _dict(raw_event.get("event"))
    event_id = _optional_string(raw_event.get("event_id")) or _optional_string(
        event.get("client_msg_id")
    )
    event_id = event_id or _optional_string(event.get("ts")) or "unknown"
    return {
        "event_id": event_id.replace(".", "_"),
        "provider_event_id": event_id,
        "sender_id": str(event.get("user") or raw_event.get("user_id") or "unknown"),
        "text": _optional_string(event.get("text")) or "",
        "thread_id": _optional_string(event.get("channel")),
        "workspace": _optional_string(raw_event.get("team_id")) or "slack",
        "metadata": {"channel_id": _optional_string(event.get("channel"))},
    }


def _string(raw_event: dict[str, Any], key: str, *, fallback: str | None = None) -> str:
    value = raw_event.get(key)
    if not isinstance(value, str) and fallback is not None:
        value = raw_event.get(fallback)
    if isinstance(value, str) and value:
        return value
    raise ValueError(f"{key} is required")


def _required_string(raw_event: dict[str, Any], key: str) -> str:
    value = raw_event.get(key)
    if isinstance(value, str) and value:
        return value
    raise ValueError(f"{key} is required")


def _optional_string(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
