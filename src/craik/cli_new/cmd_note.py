"""CLI registration for the /note command."""

from __future__ import annotations

from typing import Annotated

import typer

from craik.cli import app
from craik.cli_output import emit_command_result
from craik.runtime.contract import CommandResult, craik_command
from craik.runtime.shell.commands import note_result


@app.command("note")
@craik_command(slash_alias="note", payload_shape="kv")
def note_command(text: Annotated[str, typer.Argument(help="Operator note text.")]) -> CommandResult:
    """Add an operator note to the active session."""
    result = note_result(text)
    emit_command_result(result)
    return result
