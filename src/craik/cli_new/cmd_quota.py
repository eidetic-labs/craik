"""CLI registration for the /quota command."""

from __future__ import annotations

from craik.cli import app
from craik.cli_output import emit_command_result
from craik.runtime.contract import CommandResult, craik_command
from craik.runtime.shell.commands import quota_result


@app.command("quota")
@craik_command(slash_alias="quota", payload_shape="table")
def quota_command() -> CommandResult:
    """Show provider quota references and runtime quota state."""
    result = quota_result()
    emit_command_result(result)
    return result
