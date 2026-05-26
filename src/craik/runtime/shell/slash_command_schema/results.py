"""Slash command dispatch result helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from craik.runtime.shell.slash_command_schema import PayloadShape


@dataclass(frozen=True)
class SlashCommandResult:
    """Rendered slash-command dispatch result."""

    text: str
    exit_shell: bool = False
    exit_code: int = 0
    command_name: str | None = None
    payload_shape: PayloadShape | None = None
    payload: Any | None = None
    empty_state_message: str | None = None
    empty_state_remediation: str | None = None


def payload_result(command_name: str, payload: Any) -> SlashCommandResult:
    """Build a dispatch result with structured payload metadata."""
    from craik.runtime.shell.contract_runtime.registry_provider import get_tui_slash_spec

    spec = get_tui_slash_spec(command_name)
    is_empty = _payload_is_empty(payload)
    return SlashCommandResult(
        json.dumps(payload, indent=2, sort_keys=True) if not isinstance(payload, str) else payload,
        command_name=command_name,
        payload_shape=spec.payload_shape if spec is not None else None,
        payload=payload,
        empty_state_message=spec.empty_state.message
        if spec is not None and spec.empty_state is not None and is_empty
        else None,
        empty_state_remediation=spec.empty_state.remediation
        if spec is not None and spec.empty_state is not None and is_empty
        else None,
    )


def _payload_is_empty(payload: Any) -> bool:
    if payload == []:
        return True
    if isinstance(payload, dict):
        if payload.get("count") == 0:
            return True
        values = [value for key, value in payload.items() if key not in {"active_session"}]
        return bool(values) and all(value in ([], {}, None, "", 0) for value in values)
    return False
