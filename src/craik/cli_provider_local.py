"""Local provider preset CLI commands."""

from __future__ import annotations

import json
from typing import Annotated

import typer

from craik.cli import provider_app
from craik.runtime.contract import CommandResult, craik_command
from craik.runtime.providers.commands import (
    provider_local_health_result,
    provider_local_presets_result,
)


@provider_app.command("local-presets")
@craik_command(payload_shape="card_list")
def provider_local_presets() -> CommandResult:
    """Print local model routing presets as JSON."""
    result = provider_local_presets_result()
    typer.echo(json.dumps(result.payload, indent=2, sort_keys=True))
    return result


@provider_app.command("local-health")
@craik_command(payload_shape="card")
def provider_local_health(
    preset_id: str,
    base_url: Annotated[
        str | None,
        typer.Option("--base-url", help="Override the preset base URL for this check."),
    ] = None,
    timeout_seconds: Annotated[
        float,
        typer.Option("--timeout-seconds", help="Local endpoint health check timeout."),
    ] = 2.0,
) -> CommandResult:
    """Check a local OpenAI-compatible endpoint without loading provider credentials."""
    try:
        result = provider_local_health_result(
            preset_id,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
        )
    except ValueError as error:
        raise typer.BadParameter(str(error)) from None
    typer.echo(json.dumps(result.payload, indent=2, sort_keys=True))
    return result
