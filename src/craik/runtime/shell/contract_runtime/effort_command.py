"""Slash command handler for active model reasoning effort."""

from __future__ import annotations

from craik.runtime.contract.command_result import CommandResult
from craik.runtime.model_commands import model_effort_result


def effort_command(*args: str, env: dict[str, str] | None = None) -> CommandResult:
    try:
        result = model_effort_result(args[0] if args else None, env=env)
    except ValueError as error:
        text = str(error)
        return CommandResult(payload=text, shape="markdown", text=text, exit_code=2)
    effort = result.payload.get("reasoning_effort") if isinstance(result.payload, dict) else None
    return CommandResult(
        payload=result.payload,
        shape=result.shape,
        text=f"Reasoning effort: `{effort}`." if args and isinstance(effort, str) else None,
        command_name="effort",
    )
