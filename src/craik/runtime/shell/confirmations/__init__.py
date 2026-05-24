"""Confirmation helpers for destructive interactive-shell actions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from craik.contracts.models import CapabilityReceipt, ReceiptResult
from craik.runtime.paths import resolve_craik_paths
from craik.runtime.shell.slash_command_schema import slash_command_spec_by_name
from craik.runtime.shell.textual_widgets.confirm_modal import ConfirmationRequest
from craik.runtime.store import LocalStore


@dataclass(frozen=True)
class InlineActionSpec:
    """Resolved slash command for one inline table action."""

    command_text: str
    requires_confirmation: bool
    confirm_title: str
    confirm_body: str


def confirmation_request_for_text(
    text: str,
    *,
    transcript_line_count: int,
    active_profile: str,
) -> ConfirmationRequest | None:
    """Build a confirmation request for destructive slash-command text."""
    tokens = text.strip().split()
    if not tokens or not tokens[0].startswith("/"):
        return None
    if tokens == ["/clear"]:
        message = (
            "This will discard the current session transcript from the screen "
            f"({transcript_line_count} lines). Persisted receipts and audit records "
            "remain stored."
        )
        return ConfirmationRequest(text, "Confirm: clear transcript", message)
    spec = slash_command_spec_by_name(tokens[0])
    if spec is not None and spec.requires_confirmation and _destructive_subcommand(tokens):
        message = spec.confirm_message or "This command changes local Craik state."
        return ConfirmationRequest(text, f"Confirm: {text}", message)
    return None


def resolve_inline_action(
    command_name: str,
    action: str,
    row_id: str,
) -> InlineActionSpec | None:
    """Resolve a focused row action into a slash command."""
    normalized = command_name.strip()
    if action == "delete":
        if normalized == "/agent list":
            command_text = f"/agent delete {row_id}"
        elif normalized == "/session list":
            command_text = f"/session delete {row_id}"
        elif normalized == "/receipts list":
            command_text = f"/receipts purge {row_id}"
        else:
            return None
        return InlineActionSpec(
            command_text=command_text,
            requires_confirmation=True,
            confirm_title=f"Confirm: {command_text}",
            confirm_body=f"This will apply `{command_text}` to `{row_id}`.",
        )
    if action == "rename" and normalized == "/agent list":
        return InlineActionSpec(
            command_text=f"/agent rename {row_id}",
            requires_confirmation=False,
            confirm_title="",
            confirm_body="",
        )
    if action == "details" and normalized == "/receipts list":
        return InlineActionSpec(
            command_text=f"/receipts detail {row_id}",
            requires_confirmation=False,
            confirm_title="",
            confirm_body="",
        )
    return None


def record_confirmation_decision(
    command_text: str,
    decision: str,
    *,
    env: dict[str, str],
) -> str | None:
    """Persist an audit receipt for a confirmation decision."""
    command_preview = command_text[:256]
    store = LocalStore.from_paths(resolve_craik_paths(env))
    try:
        store.initialize()
        store.put_receipt(
            CapabilityReceipt(
                id=f"confirmation_{uuid4().hex[:12]}",
                task_id="interactive-shell",
                actor="operator",
                capability="slash.confirmation",
                target=command_preview,
                policy_profile="strict",
                reason="Record operator confirmation decision for a destructive slash command.",
                result=ReceiptResult(
                    status="passed",
                    summary=f"Confirmation {decision} for `{command_preview}`.",
                    metadata={
                        "command": command_preview,
                        "command_preview": command_preview,
                        "decision": decision,
                    },
                ),
                redacted=True,
                created_at=datetime.now(UTC),
            )
        )
    except Exception as error:
        return f"Confirmation audit receipt could not be recorded: {error}"
    finally:
        store.close()
    return None


def _destructive_subcommand(tokens: list[str]) -> bool:
    """Return whether slash tokens match a destructive command shape."""
    destructive_prefixes = {
        ("/policy", "reset"),
        ("/migrate", "apply"),
        ("/agent", "delete"),
        ("/session", "delete"),
        ("/receipts", "purge"),
    }
    return any(tuple(tokens[: len(prefix)]) == prefix for prefix in destructive_prefixes)
