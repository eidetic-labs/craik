"""CLI registration for the /compact placeholder command."""

from __future__ import annotations

from craik.cli import app
from craik.cli_output import emit_command_result
from craik.runtime.contract import CommandResult, craik_command
from craik.runtime.shell.commands import compact_stub_result


@app.command("compact")
@craik_command(slash_alias="compact", payload_shape="kv")
def compact_command() -> CommandResult:
    """Manually compact the current conversation (coming in v0.14.0)."""
    result = compact_stub_result()
    emit_command_result(result)
    return result
