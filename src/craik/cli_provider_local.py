"""Local provider preset CLI commands."""

from __future__ import annotations

import json
from typing import Annotated

import typer

from craik.cli import provider_app
from craik.runtime.local_models import (
    check_local_model_health,
    list_local_model_presets,
    provider_for_local_model_preset,
)


@provider_app.command("local-presets")
def provider_local_presets() -> None:
    """Print local model routing presets as JSON."""
    payload = [
        {
            **preset.model_dump(mode="json", by_alias=True),
            "provider": provider_for_local_model_preset(preset.id).model_dump(
                mode="json",
                by_alias=True,
            ),
        }
        for preset in list_local_model_presets()
    ]
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@provider_app.command("local-health")
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
) -> None:
    """Check a local OpenAI-compatible endpoint without loading provider credentials."""
    try:
        health = check_local_model_health(
            preset_id,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
        )
    except ValueError as error:
        raise typer.BadParameter(str(error)) from None
    typer.echo(json.dumps(health.model_dump(mode="json"), indent=2, sort_keys=True))
