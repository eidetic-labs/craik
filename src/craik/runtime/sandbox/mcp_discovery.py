"""Operator-facing MCP client discovery rendering."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from craik.runtime.paths import resolve_craik_paths
from craik.runtime.sandbox.mcp_client import MCPClientConfig

MCP_EMPTY_STATE = (
    "No MCP clients configured. Run `craik mcp client import --path <config.json>` "
    "from your operator shell to add one."
)


@dataclass(frozen=True)
class MCPToolView:
    """Tool metadata surfaced from a configured MCP client."""

    name: str
    effect: str = "read"
    requires_auth: bool = True
    requires_policy_gate: bool = True
    description: str = ""


@dataclass(frozen=True)
class MCPClientView:
    """Rendered MCP client with stale-config and advertised-tool metadata."""

    client: MCPClientConfig
    source: Path
    tools: tuple[MCPToolView, ...]
    unreadable_refs: tuple[str, ...] = ()


def mcp_discovery_payload(env: dict[str, str] | None = None) -> dict[str, Any]:
    """Return structured MCP discovery state for slash-command JSON output."""
    clients, warnings, source = load_mcp_clients(env)
    return {
        "source": str(source),
        "warnings": warnings,
        "total_clients": len(clients),
        "total_tools": sum(len(client.tools) for client in clients),
        "clients": [_client_payload(client) for client in clients],
    }


def render_mcp_discovery(
    args: list[str],
    *,
    env: dict[str, str] | None = None,
) -> tuple[str, int]:
    """Render `/mcp` output with optional verbose, filter, and JSON modes."""
    output_json = "--json" in args
    tokens = [arg for arg in args if arg != "--json"]
    verbose = bool(tokens and tokens[0] == "verbose")
    filters = tokens[1:] if verbose else tokens
    clients, warnings, source = load_mcp_clients(env)
    if filters:
        clients = _filtered_clients(clients, filters)
    if output_json:
        payload = {
            "source": str(source),
            "warnings": warnings,
            "total_clients": len(clients),
            "total_tools": sum(len(client.tools) for client in clients),
            "clients": [_client_payload(client) for client in clients],
        }
        return json.dumps(payload, indent=2, sort_keys=True), 0
    if not clients and not warnings:
        return MCP_EMPTY_STATE, 0
    lines: list[str] = []
    lines.extend(f"warning: {warning}" for warning in warnings)
    lines.extend(_render_verbose(clients) if verbose else _render_summary(clients))
    if clients:
        lines.append(f"[total] {len(clients)} clients, {sum(len(c.tools) for c in clients)} tools")
    return "\n".join(lines), 0


def load_mcp_clients(
    env: dict[str, str] | None = None,
) -> tuple[list[MCPClientView], list[str], Path]:
    """Load configured MCP clients from Craik state."""
    source = resolve_craik_paths(env).state / "mcp" / "clients.json"
    if not source.exists():
        return [], [], source
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return [], [f"unreadable MCP client config: {error}"], source
    raw_clients = payload.get("clients") if isinstance(payload, dict) else None
    if not isinstance(raw_clients, list):
        return [], ["unreadable MCP client config: expected clients list"], source
    clients: list[MCPClientView] = []
    warnings: list[str] = []
    for index, raw_client in enumerate(raw_clients):
        try:
            client = MCPClientConfig.model_validate(raw_client)
        except ValueError as error:
            warnings.append(f"skipped MCP client at index {index}: {error}")
            continue
        clients.append(
            MCPClientView(
                client=client,
                source=source,
                tools=_tool_views(client.metadata.get("tools")),
                unreadable_refs=_unreadable_config_refs(client.config_refs),
            )
        )
    return clients, warnings, source


def _render_summary(clients: list[MCPClientView]) -> list[str]:
    lines: list[str] = []
    for view in clients:
        marker = " [unreadable]" if view.unreadable_refs else ""
        lines.append(
            f"[{view.client.id}] {view.client.name}{marker} "
            f"({view.client.transport}) tools: {len(view.tools)}"
        )
    return lines


def _render_verbose(clients: list[MCPClientView]) -> list[str]:
    lines: list[str] = []
    for view in clients:
        marker = " [unreadable]" if view.unreadable_refs else ""
        lines.append(f"[{view.client.id}] {view.client.name}{marker}")
        lines.append(
            "  policy: "
            f"grant {_required(view.client.grant_required)}, "
            f"receipt {_required(view.client.receipt_required)}, "
            f"redaction {_required(view.client.redaction_required)}"
        )
        lines.append(f"  configured: {view.source}")
        if view.unreadable_refs:
            lines.append(f"  unreadable: {', '.join(view.unreadable_refs)}")
        lines.append("  tools:")
        if not view.tools:
            lines.append("    - (no tools advertised)")
        for tool in view.tools:
            lines.append(
                f"    - {tool.name} (effect: {tool.effect}, "
                f"requires_auth: {_yes(tool.requires_auth)}, "
                f"requires_policy_gate: {_yes(tool.requires_policy_gate)})"
            )
            if tool.description:
                lines.append(f"        {tool.description}")
    return lines


def _filtered_clients(clients: list[MCPClientView], filters: list[str]) -> list[MCPClientView]:
    client_id = filters[0]
    tool_name = filters[1] if len(filters) > 1 else None
    filtered = [view for view in clients if view.client.id == client_id]
    if tool_name is None:
        return filtered
    return [
        MCPClientView(
            client=view.client,
            source=view.source,
            tools=tuple(tool for tool in view.tools if tool.name == tool_name),
            unreadable_refs=view.unreadable_refs,
        )
        for view in filtered
    ]


def _tool_views(value: Any) -> tuple[MCPToolView, ...]:
    if not isinstance(value, list):
        return ()
    tools: list[MCPToolView] = []
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            continue
        tools.append(
            MCPToolView(
                name=item["name"],
                effect=_text(item.get("effect"), default="read"),
                requires_auth=_bool(item.get("requires_auth"), default=True),
                requires_policy_gate=_bool(item.get("requires_policy_gate"), default=True),
                description=_text(item.get("description"), default=""),
            )
        )
    return tuple(tools)


def _unreadable_config_refs(refs: list[str]) -> tuple[str, ...]:
    values: list[str] = []
    for ref in refs:
        path = Path(ref).expanduser()
        if (path.is_absolute() or "/" in ref) and not path.exists():
            values.append(ref)
    return tuple(values)


def _client_payload(view: MCPClientView) -> dict[str, Any]:
    payload = view.client.model_dump(mode="json")
    payload["source"] = str(view.source)
    payload["status"] = "unreadable" if view.unreadable_refs else "configured"
    payload["unreadable_refs"] = list(view.unreadable_refs)
    payload["tools"] = [tool.__dict__ for tool in view.tools]
    return payload


def _required(value: bool) -> str:
    return "required" if value else "not required"


def _yes(value: bool) -> str:
    return "yes" if value else "no"


def _bool(value: Any, *, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _text(value: Any, *, default: str) -> str:
    return value if isinstance(value, str) and value else default
