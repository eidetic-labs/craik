"""Environment capability receipt builders."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import Field

from craik.contracts.models import CapabilityReceipt, CraikModel, PolicyProfile, ReceiptResult
from craik.runtime.policy.redaction import redact

EnvironmentReceiptAction = Literal[
    "environment_decision",
    "provider_action",
    "sandbox_action",
    "denial",
]


class EnvironmentReceiptContext(CraikModel):
    """Context links preserved for environment capability receipts."""

    task_id: str
    agent_session_id: str | None = None
    policy_envelope_id: str | None = None
    provider_id: str | None = None
    backend_id: str | None = None
    route_id: str | None = None
    target_id: str | None = None
    command_ref: str | None = None
    receipt_ids: list[str] = Field(default_factory=list)


def environment_receipt(
    *,
    receipt_id: str,
    action: EnvironmentReceiptAction,
    context: EnvironmentReceiptContext,
    actor: str,
    capability: str,
    policy_profile: PolicyProfile,
    status: Literal["passed", "denied"],
    reason: str,
    summary: str,
    metadata: dict[str, Any] | None = None,
    created_at: datetime | None = None,
) -> CapabilityReceipt:
    """Build a redacted capability receipt for provider and sandbox actions."""
    now = created_at or datetime.now(UTC)
    return CapabilityReceipt(
        id=receipt_id,
        task_id=context.task_id,
        actor=actor,
        capability=capability,
        target=_target(action, context),
        policy_profile=policy_profile,
        fail_open=False,
        reason=reason,
        result=ReceiptResult(
            status=status,
            summary=summary,
            metadata={
                **_context_metadata(context),
                "environment_action": action,
                **_redacted_metadata(metadata or {}),
                "redacted_fields": sorted(_REDACTED_METADATA_KEYS),
            },
        ),
        redacted=True,
        created_at=now,
    )


def _target(action: EnvironmentReceiptAction, context: EnvironmentReceiptContext) -> str:
    if context.command_ref:
        return f"{action}:{redact(context.command_ref).value}"
    if context.backend_id:
        return f"{action}:{context.backend_id}"
    if context.provider_id:
        return f"{action}:{context.provider_id}"
    return action


def _context_metadata(context: EnvironmentReceiptContext) -> dict[str, Any]:
    return {
        "policy_envelope_id": context.policy_envelope_id,
        "agent_session_id": context.agent_session_id,
        "provider_id": context.provider_id,
        "backend_id": context.backend_id,
        "route_id": context.route_id,
        "target_id": redact(context.target_id).value if context.target_id else None,
        "command_ref": redact(context.command_ref).value if context.command_ref else None,
        "receipt_ids": context.receipt_ids,
    }


def _redacted_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in metadata.items():
        normalized = key.lower().replace("-", "_")
        if normalized in _REDACTED_METADATA_KEYS:
            continue
        if any(token in normalized for token in _SECRET_KEY_TOKENS):
            continue
        redacted[key] = redact(value).value
    return redacted


_REDACTED_METADATA_KEYS = {
    "command",
    "command_payload",
    "credentials",
    "env",
    "environment",
    "environment_variables",
    "payload",
    "raw_command",
    "secret",
    "stderr",
    "stdin",
    "stdout",
    "target",
    "target_payload",
}
_SECRET_KEY_TOKENS = ("secret", "token", "api_key", "apikey", "password", "credential")
