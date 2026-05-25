"""CLI registration for the /share placeholder command."""

from __future__ import annotations

from craik.cli import app
from craik.cli_output import emit_command_result
from craik.runtime.contract import CommandResult, craik_command
from craik.runtime.shell.commands import share_stub_result


@app.command("share")
@craik_command(slash_alias="share", payload_shape="kv")
def share_command() -> CommandResult:
    """Share the current transcript (coming in v0.13.0)."""
    result = share_stub_result()
    emit_command_result(result)
    return result
