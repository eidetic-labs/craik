"""MCP compatibility CLI."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from craik.cli import mcp_app
from craik.cli_typer import craik_typer
from craik.runtime.sandbox.mcp_compat import (
    export_mcp_client_config,
    handle_mcp_jsonrpc_lines,
    handle_mcp_jsonrpc_request,
    import_mcp_client_config,
    mcp_server_manifest,
)

server_app = craik_typer(help="Expose Craik MCP server compatibility surfaces.")
client_app = craik_typer(help="Import and export redacted MCP client config.")
mcp_app.add_typer(server_app, name="server")
mcp_app.add_typer(client_app, name="client")


@server_app.command("manifest")
def server_manifest_command(
    include_write_tools: Annotated[
        bool,
        typer.Option("--include-write-tools", help="Include gated write tools in the manifest."),
    ] = False,
) -> None:
    """Print the Craik MCP server compatibility manifest."""
    manifest = mcp_server_manifest(include_write_tools=include_write_tools)
    typer.echo(json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True))


@server_app.command("handle")
def server_handle_command(
    request_json: Annotated[
        str | None,
        typer.Option(
            "--request-json",
            help="Single JSON-RPC request. Defaults to newline-delimited JSON on stdin.",
        ),
    ] = None,
    include_write_tools: Annotated[
        bool,
        typer.Option("--include-write-tools", help="Enable gated write tools for this request."),
    ] = False,
) -> None:
    """Handle MCP JSON-RPC compatibility requests over JSON lines."""
    if request_json is not None:
        payload = json.loads(request_json)
        if not isinstance(payload, dict):
            raise typer.BadParameter("--request-json must decode to an object")
        typer.echo(
            json.dumps(
                handle_mcp_jsonrpc_request(payload, include_write_tools=include_write_tools),
                sort_keys=True,
            )
        )
        return
    for response in handle_mcp_jsonrpc_lines(
        sys.stdin,
        include_write_tools=include_write_tools,
    ):
        typer.echo(response)


@client_app.command("import")
def client_import_command(
    path: Annotated[Path, typer.Option("--path", help="MCP client config JSON path.")],
) -> None:
    """Import MCP client config and print redacted Craik metadata."""
    try:
        result = import_mcp_client_config(path)
    except ValidationError as error:
        raise typer.BadParameter(_validation_error_message(error)) from None
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise typer.BadParameter(str(error)) from None
    typer.echo(json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True))


@client_app.command("export")
def client_export_command(
    path: Annotated[Path, typer.Option("--path", help="Craik MCP client config JSON path.")],
) -> None:
    """Export MCP client config in redacted JSON form."""
    try:
        result = import_mcp_client_config(path)
    except ValidationError as error:
        raise typer.BadParameter(_validation_error_message(error)) from None
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise typer.BadParameter(str(error)) from None
    payload = [export_mcp_client_config(client) for client in result.clients]
    typer.echo(json.dumps({"clients": payload}, indent=2, sort_keys=True))


def _validation_error_message(error: ValidationError) -> str:
    lines = ["MCP config validation failed:"]
    for item in error.errors(include_url=False, include_input=False):
        location = ".".join(str(part) for part in item.get("loc", ())) or "config"
        lines.append(f"- {location}: {item.get('msg', 'invalid value')}")
    return "\n".join(lines)
