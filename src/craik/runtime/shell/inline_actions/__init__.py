"""Inline-action dispatch bridge for the interactive TUI."""

from __future__ import annotations

from typing import Any

from textual.widgets import RichLog

from craik.runtime.contract.format import format_command_result
from craik.runtime.shell.confirmations import InlineActionSpec, resolve_inline_action
from craik.runtime.shell.contract_runtime.result_adapter import to_slash_command_result
from craik.runtime.shell.textual_widgets.confirm_modal import ConfirmationRequest, ConfirmModal
from craik.runtime.shell.textual_widgets.inline_action_table import InlineActionTable


def handle_inline_action(
    app: Any,
    message: InlineActionTable.InlineActionRequested,
) -> None:
    """Resolve, confirm, and dispatch a focused inline table action."""
    action_spec = resolve_inline_action(message.command_name, message.action, message.row_id)
    if action_spec is None:
        app._toast(
            f"No `{message.action}` handler for `{message.command_name}`.",
            severity="warning",
        )
        return
    if action_spec.requires_confirmation:
        request = ConfirmationRequest(
            action_spec.command_text,
            action_spec.confirm_title,
            action_spec.confirm_body,
        )
        app.push_screen(
            ConfirmModal(request),
            lambda confirmed: complete_inline_action(app, action_spec, confirmed),
        )
        return
    dispatch_inline_action(app, action_spec.command_text)


def complete_inline_action(
    app: Any,
    action_spec: InlineActionSpec,
    confirmed: bool | None,
) -> None:
    """Continue inline action flow after confirmation."""
    decision = "confirmed" if confirmed else "declined"
    app._record_confirmation_decision(action_spec.command_text, decision)
    if not confirmed:
        app._toast("Action cancelled.", severity="information")
        return
    dispatch_inline_action(app, action_spec.command_text)


def dispatch_inline_action(app: Any, command_text: str) -> None:
    """Dispatch a resolved inline action command and append it to the transcript."""
    contract_result = app._dispatch_contract(command_text)
    result = to_slash_command_result(contract_result)
    transcript = app.query_one("#transcript", RichLog)
    transcript.write(format_command_result(contract_result, kind="tui"))
    app._transcript_lines.append(result.text)
