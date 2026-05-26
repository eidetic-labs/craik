"""Status CLI command."""

from __future__ import annotations

from craik.cli import app
from craik.cli_output import emit_command_result
from craik.runtime.contract import CommandResult, craik_command
from craik.runtime.status import status_command_result


@app.command("status")
@craik_command(payload_shape="kv")
def status_command() -> CommandResult:
    """Show progressive setup readiness for shell and runtime actions."""
    result = status_command_result()
    emit_command_result(result)
    return result
