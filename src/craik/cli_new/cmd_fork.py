"""CLI registration for the /fork command."""

from __future__ import annotations

from craik.cli import app
from craik.cli_output import emit_command_result
from craik.runtime.contract import CommandResult, craik_command
from craik.runtime.shell.commands import fork_result


@app.command("fork")
@craik_command(slash_alias="fork", payload_shape="kv")
def fork_command() -> CommandResult:
    """Fork the active persistent session."""
    result = fork_result()
    emit_command_result(result)
    return result
