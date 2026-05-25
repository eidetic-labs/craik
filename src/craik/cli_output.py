"""CLI output helpers for shared CommandResult callbacks."""

from __future__ import annotations

import json

import typer

from craik.runtime.contract import CommandResult, detect_default_format, format_command_result
from craik.runtime.contract.output_context import slash_dispatch_active


def emit_command_result(result: CommandResult) -> None:
    """Emit a CommandResult for Typer while staying silent during slash dispatch."""
    if slash_dispatch_active():
        return
    output_format = detect_default_format()
    rendered = (
        json.dumps(result.payload, default=str, indent=2, sort_keys=True)
        if output_format == "json"
        else format_command_result(result, kind=output_format)
    )
    if rendered:
        typer.echo(rendered)
