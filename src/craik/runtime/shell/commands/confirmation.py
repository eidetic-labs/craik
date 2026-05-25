"""CommandResult helpers for modal-only slash-command confirmations."""

from craik.runtime.contract import CommandResult

_MESSAGES: dict[str, str] = {
    "clear": (
        "Transcript clear confirmation requested. "
        "The interactive TUI opens a confirmation modal for this action."
    ),
    "policy.reset": (
        "Policy reset confirmation requested. "
        "The interactive TUI opens a confirmation modal for this action."
    ),
    "migrate.apply": (
        "Migration apply confirmation requested. "
        "The interactive TUI opens a confirmation modal for this action."
    ),
    "agent.delete": (
        "Agent delete confirmation requested. "
        "The interactive TUI opens a confirmation modal for this action."
    ),
    "session.delete": (
        "Session delete confirmation requested. "
        "The interactive TUI opens a confirmation modal for this action."
    ),
}


def confirmation_result(
    action: str,
    *,
    target_id: str | None = None,
) -> CommandResult:
    """Return a structured result for a confirmation-only slash action."""
    try:
        text = _MESSAGES[action]
    except KeyError as error:
        raise ValueError(f"unknown confirmation action: {action}") from error
    payload = {
        "action": action,
        "target_id": target_id,
        "requires_confirmation": True,
        "modal": action.replace(".", "_"),
    }
    return CommandResult(payload=payload, shape="markdown", text=text)
