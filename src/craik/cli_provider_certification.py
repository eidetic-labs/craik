"""Provider certification matrix CLI commands."""

from __future__ import annotations

import json
from typing import Annotated

import typer

from craik.cli import provider_app
from craik.runtime.providers.provider_certification import (
    ProviderCertificationMatrix,
    provider_certification_matrix,
)


@provider_app.command("certification")
def provider_certification(
    provider_id: Annotated[
        str | None,
        typer.Option("--provider-id", help="Provider id to inspect. Prints all when omitted."),
    ] = None,
) -> None:
    """Print the provider certification matrix as JSON."""
    matrix = provider_certification_matrix()
    if provider_id is not None:
        rows = [row for row in matrix.rows if row.provider_id == provider_id]
        if not rows:
            raise typer.BadParameter(f"unknown provider certification row: {provider_id}")
        matrix = ProviderCertificationMatrix(generated_at=matrix.generated_at, rows=rows)
    payload = matrix.model_dump(mode="json", by_alias=True)
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))
