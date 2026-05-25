"""CommandResult helpers for MCP compatibility CLI surfaces."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from craik.runtime.contract import CommandResult
from craik.runtime.sandbox.mcp_compat import (
    export_mcp_client_config,
    import_mcp_client_config,
    mcp_server_manifest,
)
from craik.runtime.sandbox.mcp_discovery import mcp_discovery_payload


def mcp_discovery_result(env: dict[str, str] | None = None) -> CommandResult:
    """Return configured MCP client discovery state."""
    payload = mcp_discovery_payload(env)
    return CommandResult(
        payload=payload,
        shape="card_list",
        empty_state_message="No MCP clients configured.",
    )


def mcp_server_manifest_result(*, include_write_tools: bool = False) -> CommandResult:
    """Return the Craik MCP server compatibility manifest."""
    manifest = mcp_server_manifest(include_write_tools=include_write_tools)
    return CommandResult(payload=manifest.model_dump(mode="json"), shape="tree")


def mcp_client_import_result(path: Path) -> CommandResult:
    """Import MCP client config and return redacted Craik metadata."""
    try:
        result = import_mcp_client_config(path)
    except ValidationError as error:
        raise ValueError(_validation_error_message(error)) from None
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(str(error)) from None
    return CommandResult(payload=result.model_dump(mode="json"), shape="card_list")


def mcp_client_export_result(path: Path) -> CommandResult:
    """Export MCP client config in redacted JSON form."""
    try:
        result = import_mcp_client_config(path)
    except ValidationError as error:
        raise ValueError(_validation_error_message(error)) from None
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(str(error)) from None
    payload = [export_mcp_client_config(client) for client in result.clients]
    return CommandResult(payload={"clients": payload}, shape="card_list")


def _validation_error_message(error: ValidationError) -> str:
    lines = ["MCP config validation failed:"]
    for item in error.errors(include_url=False, include_input=False):
        location = ".".join(str(part) for part in item.get("loc", ())) or "config"
        lines.append(f"- {location}: {item.get('msg', 'invalid value')}")
    return "\n".join(lines)
