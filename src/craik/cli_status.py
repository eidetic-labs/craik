"""Status CLI command."""

from __future__ import annotations

import json

import typer

from craik.cli import app
from craik.runtime.contract import CommandResult, craik_command
from craik.runtime.status import status_command_result


@app.command("status")
@craik_command(payload_shape="kv")
def status_command() -> CommandResult:
    """Show progressive setup readiness for shell and runtime actions."""
    result = status_command_result()
    typer.echo(json.dumps(result.payload, indent=2, sort_keys=True))
    return result
