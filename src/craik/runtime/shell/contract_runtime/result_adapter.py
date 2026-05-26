"""Adapter from contract CommandResult to the legacy SlashCommandResult shape."""

from __future__ import annotations

import json

from craik.runtime.contract.command_result import CommandResult
from craik.runtime.shell.slash_command_schema.results import SlashCommandResult


def to_slash_command_result(result: CommandResult) -> SlashCommandResult:
    """Wrap a CommandResult for transitional TUI surfaces."""
    from craik.runtime.shell.contract_runtime.registry_provider import get_tui_slash_spec

    text = result.text
    if text is None:
        text = (
            json.dumps(result.payload, indent=2, sort_keys=True)
            if not isinstance(result.payload, str)
            else result.payload
        )
    spec = get_tui_slash_spec(result.command_name or "")
    payload_shape = spec.payload_shape if spec is not None else result.shape
    empty_state_message = None
    empty_state_remediation = None
    if spec is not None and spec.empty_state is not None and _payload_is_empty(result.payload):
        empty_state_message = spec.empty_state.message
        empty_state_remediation = spec.empty_state.remediation
    return SlashCommandResult(
        text=text,
        exit_shell=result.exit_shell,
        exit_code=result.exit_code,
        command_name=result.command_name,
        payload_shape=payload_shape,
        payload=result.payload,
        empty_state_message=result.empty_state_message or empty_state_message,
        empty_state_remediation=empty_state_remediation,
    )


def _payload_is_empty(payload: object) -> bool:
    if payload == []:
        return True
    if isinstance(payload, dict):
        if payload.get("count") == 0:
            return True
        values = [value for key, value in payload.items() if key not in {"active_session"}]
        return bool(values) and all(value in ([], {}, None, "", 0) for value in values)
    return False
