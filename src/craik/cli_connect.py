"""Connection detection CLI commands."""

from __future__ import annotations

from typing import Annotated

import typer

from craik.cli import connect_app
from craik.cli_output import emit_command_result
from craik.runtime.contract import CommandResult, craik_command
from craik.runtime.memory.memory import StigmemClient, StigmemConfig, StigmemMemoryStore


@connect_app.command("stigmem")
@craik_command(payload_shape="card")
def connect_stigmem(
    url: Annotated[
        str,
        typer.Option(
            "--url",
            envvar="CRAIK_STIGMEM_URL",
            help="Stigmem node URL.",
        ),
    ],
    api_key: Annotated[
        str | None,
        typer.Option(
            "--api-key",
            envvar="CRAIK_STIGMEM_API_KEY",
            help="Bearer API key. Prefer CRAIK_STIGMEM_API_KEY.",
        ),
    ] = None,
    timeout: Annotated[
        float,
        typer.Option(
            "--timeout",
            envvar="CRAIK_STIGMEM_TIMEOUT",
            help="Request timeout in seconds.",
        ),
    ] = 5.0,
) -> CommandResult:
    """Detect Stigmem backend compatibility."""
    config = StigmemConfig(node_url=url, api_key=api_key, timeout_seconds=timeout)
    capabilities = StigmemMemoryStore(StigmemClient(config)).discover()
    result = CommandResult(
        payload=capabilities.model_dump(mode="json", by_alias=True),
        shape="card",
    )
    emit_command_result(result)
    return result
