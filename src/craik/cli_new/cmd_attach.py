"""CLI registration for the /attach command."""

from __future__ import annotations

from typing import Annotated

import typer

from craik.cli import app
from craik.cli_output import emit_command_result
from craik.runtime.contract import CommandResult, craik_command
from craik.runtime.shell.commands import attach_result


@app.command("attach")
@craik_command(slash_alias="attach", payload_shape="kv")
def attach_command(
    path: Annotated[str, typer.Argument(help="File path to attach.")],
) -> CommandResult:
    """Attach a file reference to the active session."""
    result = attach_result(path)
    emit_command_result(result)
    return result
