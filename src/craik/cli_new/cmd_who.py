"""CLI registration for the /who command."""

from __future__ import annotations

from craik.cli import app
from craik.cli_output import emit_command_result
from craik.runtime.contract import CommandResult, craik_command
from craik.runtime.shell.commands import who_result


@app.command("who")
@craik_command(slash_alias="who", payload_shape="kv")
def who_command() -> CommandResult:
    """Show active operator identity and auth scope."""
    result = who_result()
    emit_command_result(result)
    return result
