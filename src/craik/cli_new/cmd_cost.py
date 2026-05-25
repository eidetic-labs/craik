"""CLI registration for the /cost command."""

from __future__ import annotations

from craik.cli import app
from craik.cli_output import emit_command_result
from craik.runtime.contract import CommandResult, craik_command
from craik.runtime.shell.commands import cost_result


@app.command("cost")
@craik_command(slash_alias="cost", payload_shape="kv")
def cost_command() -> CommandResult:
    """Show provider token usage and cost accounting state."""
    result = cost_result()
    emit_command_result(result)
    return result
