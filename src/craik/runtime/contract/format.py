"""Output format selection for CommandResult values."""

from __future__ import annotations

import json
import sys
from importlib import import_module
from typing import Any, Literal

from craik.runtime.contract.command_result import CommandResult

FormatKind = Literal["json", "text", "tui"]


def detect_default_format() -> FormatKind:
    """Return the default output format for the current stdout mode."""
    return "text" if sys.stdout.isatty() else "json"


def _format_json(result: CommandResult) -> str:
    """Serialize a CommandResult as JSON for scripting consumers."""
    return json.dumps(
        {
            "payload": result.payload,
            "shape": result.shape,
            "text": result.text,
            "exit_code": result.exit_code,
            "exit_shell": result.exit_shell,
            "command_name": result.command_name,
            "next_actions": [
                {
                    "text": action.text,
                    "command": action.command,
                    "field": action.field,
                }
                for action in result.next_actions
            ],
            "empty_state_message": result.empty_state_message,
        },
        default=str,
        indent=2,
    )


def _format_text(result: CommandResult) -> str:
    """Serialize a CommandResult as compact plain text."""
    lines: list[str] = []
    if result.text:
        lines.append(result.text)
    elif isinstance(result.payload, dict):
        lines.extend(f"{key}: {value}" for key, value in result.payload.items())
    elif isinstance(result.payload, list):
        lines.extend(str(item) for item in result.payload)
    elif result.payload is not None:
        lines.append(str(result.payload))
    elif result.empty_state_message:
        lines.append(result.empty_state_message)

    if result.next_actions:
        if lines:
            lines.append("")
        lines.append("Next actions:")
        for index, action in enumerate(result.next_actions, start=1):
            lines.append(f"  {index}. {action.text}")
    return "\n".join(lines)


def _format_tui(result: CommandResult) -> Any:
    """Return the renderer pipeline output for TUI consumers."""
    render = import_module("craik.runtime.shell.renderers").render

    return render(
        result.payload,
        shape=result.shape,
        next_actions=result.next_actions,
    )


def format_command_result(result: CommandResult, *, kind: FormatKind) -> Any:
    """Dispatch a CommandResult to the requested output format."""
    if kind == "json":
        return _format_json(result)
    if kind == "text":
        return _format_text(result)
    if kind == "tui":
        return _format_tui(result)
    raise ValueError(f"Unknown format: {kind!r}")
