"""MCP compatibility CLI."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated

import typer

from craik.cli import mcp_app
from craik.cli_output import emit_command_result
from craik.cli_typer import craik_typer
from craik.runtime.contract import CommandResult, craik_command
from craik.runtime.sandbox.mcp_commands import (
    mcp_client_export_result,
    mcp_client_import_result,
    mcp_server_manifest_result,
)
from craik.runtime.sandbox.mcp_compat import (
    handle_mcp_jsonrpc_lines,
    handle_mcp_jsonrpc_request,
)

server_app = craik_typer(help="Expose Craik MCP server compatibility surfaces.")
client_app = craik_typer(help="Import and export redacted MCP client config.")
mcp_app.add_typer(server_app, name="server")
mcp_app.add_typer(client_app, name="client")


@server_app.command("manifest")
@craik_command(payload_shape="tree")
def server_manifest_command(
    include_write_tools: Annotated[
        bool,
        typer.Option("--include-write-tools", help="Include gated write tools in the manifest."),
    ] = False,
) -> CommandResult:
    """Print the Craik MCP server compatibility manifest."""
    result = mcp_server_manifest_result(include_write_tools=include_write_tools)
    emit_command_result(result)
    return result


@server_app.command("handle")
@craik_command(
    tui_eligible=False,
    tui_exempt_reason="JSON-RPC protocol handler streams stdin/stdout; not an operator TUI command",
)
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
@craik_command(payload_shape="card_list")
def client_import_command(
    path: Annotated[Path, typer.Option("--path", help="MCP client config JSON path.")],
) -> CommandResult:
    """Import MCP client config and print redacted Craik metadata."""
    try:
        result = mcp_client_import_result(path)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from None
    emit_command_result(result)
    return result


@client_app.command("export")
@craik_command(payload_shape="card_list")
def client_export_command(
    path: Annotated[Path, typer.Option("--path", help="Craik MCP client config JSON path.")],
) -> CommandResult:
    """Export MCP client config in redacted JSON form."""
    try:
        result = mcp_client_export_result(path)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from None
    emit_command_result(result)
    return result
