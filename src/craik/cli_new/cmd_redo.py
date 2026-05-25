"""CLI registration for the /redo command."""

from __future__ import annotations

from craik.cli import app
from craik.cli_output import emit_command_result
from craik.runtime.contract import CommandResult, craik_command
from craik.runtime.shell.commands import redo_result


@app.command("redo")
@craik_command(slash_alias="redo", payload_shape="kv")
def redo_command() -> CommandResult:
    """Redo the latest replayable agent turn when available."""
    result = redo_result()
    emit_command_result(result)
    return result
