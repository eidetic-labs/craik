"""Provider certification matrix CLI commands."""

from __future__ import annotations

import json
from typing import Annotated

import typer

from craik.cli import provider_app
from craik.runtime.contract import CommandResult, craik_command
from craik.runtime.providers.commands import provider_certification_result


@provider_app.command("certification")
@craik_command(payload_shape="card")
def provider_certification(
    provider_id: Annotated[
        str | None,
        typer.Option("--provider-id", help="Provider id to inspect. Prints all when omitted."),
    ] = None,
) -> CommandResult:
    """Print the provider certification matrix as JSON."""
    try:
        result = provider_certification_result(provider_id)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from None
    typer.echo(json.dumps(result.payload, indent=2, sort_keys=True))
    return result
