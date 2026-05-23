"""Executable MCP compatibility helpers for server and client surfaces."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from craik.contracts.models import CraikModel
from craik.runtime.sandbox.mcp_client import MCPClientConfig
from craik.runtime.sandbox.mcp_export import MCPExportSurface, mcp_export_decision

MCPToolEffect = Literal["read", "write"]
MCPToolPolicyStatus = Literal["allowed", "blocked"]

SECRET_KEY_TOKENS = ("secret", "token", "api_key", "apikey", "password", "credential")


class MCPToolDescriptor(CraikModel):
    """Craik tool surface advertised through MCP server compatibility mode."""

    name: str
    title: str
    effect: MCPToolEffect
    capabilities: list[str] = Field(default_factory=list)
    description: str
    requires_auth: bool = True
    requires_policy_gate: bool = True
    requires_receipt: bool = True


class MCPServerManifest(CraikModel):
    """Safe-to-share MCP server compatibility manifest."""

    server_id: str
    name: str
    protocol_version: str
    tools: list[MCPToolDescriptor]
    compatibility_matrix: dict[str, str]


class MCPToolPolicyResult(CraikModel):
    """Auth, policy, and receipt decision for one MCP tool call."""

    status: MCPToolPolicyStatus
    allowed: bool
    tool_name: str
    reason: str
    required_controls: list[str] = Field(default_factory=list)
    receipt_id: str | None = None


class MCPClientImportResult(CraikModel):
    """Redacted MCP client import result."""

    clients: list[MCPClientConfig]
    warnings: list[str] = Field(default_factory=list)


READ_ONLY_TOOLS: tuple[MCPToolDescriptor, ...] = (
    MCPToolDescriptor(
        name="craik.case.read",
        title="Read case-file summaries",
        effect="read",
        capabilities=["file.read"],
        description="Return redacted case-file metadata and summaries.",
    ),
    MCPToolDescriptor(
        name="craik.memory.search",
        title="Search approved memory",
        effect="read",
        capabilities=["memory.read"],
        description="Search approved, redacted runtime memory records.",
    ),
    MCPToolDescriptor(
        name="craik.receipts.list",
        title="List receipt metadata",
        effect="read",
        capabilities=["receipt.read"],
        description="List receipt ids, statuses, and timestamps without secret values.",
    ),
)

WRITE_TOOLS: tuple[MCPToolDescriptor, ...] = (
    MCPToolDescriptor(
        name="craik.memory.propose",
        title="Propose memory write",
        effect="write",
        capabilities=["memory.write"],
        description="Propose a governed memory write that requires policy and receipts.",
    ),
)


def mcp_server_manifest(*, include_write_tools: bool = False) -> MCPServerManifest:
    """Build the Craik MCP server compatibility manifest."""
    tools = list(READ_ONLY_TOOLS)
    if include_write_tools:
        tools.extend(WRITE_TOOLS)
    return MCPServerManifest(
        server_id="craik.mcp.compat",
        name="Craik MCP Compatibility Server",
        protocol_version="2024-11-05",
        tools=tools,
        compatibility_matrix={tool.name: _export_status(tool) for tool in tools},
    )


def mcp_tool_policy_result(
    tool_name: str,
    *,
    operator_authenticated: bool,
    policy_gate_approved: bool = False,
    receipt_id: str | None = None,
    include_write_tools: bool = False,
) -> MCPToolPolicyResult:
    """Map an MCP tool call to Craik auth, policy, and receipt controls."""
    manifest = mcp_server_manifest(include_write_tools=include_write_tools)
    tools = {tool.name: tool for tool in manifest.tools}
    tool = tools.get(tool_name)
    if tool is None:
        return MCPToolPolicyResult(
            status="blocked",
            allowed=False,
            tool_name=tool_name,
            reason="unknown MCP tool",
            required_controls=[],
        )
    controls = _required_tool_controls(tool)
    if tool.requires_auth and not operator_authenticated:
        return MCPToolPolicyResult(
            status="blocked",
            allowed=False,
            tool_name=tool_name,
            reason="active operator authentication required",
            required_controls=controls,
        )
    if tool.effect == "write" and tool.requires_policy_gate and not policy_gate_approved:
        return MCPToolPolicyResult(
            status="blocked",
            allowed=False,
            tool_name=tool_name,
            reason="write MCP tools require an approved policy gate",
            required_controls=controls,
        )
    if tool.effect == "write" and tool.requires_receipt and receipt_id is None:
        return MCPToolPolicyResult(
            status="blocked",
            allowed=False,
            tool_name=tool_name,
            reason="write MCP tools require a receipt id",
            required_controls=controls,
        )
    return MCPToolPolicyResult(
        status="allowed",
        allowed=True,
        tool_name=tool_name,
        reason="MCP tool call satisfies Craik auth, policy, and receipt controls",
        required_controls=controls,
        receipt_id=receipt_id,
    )


def handle_mcp_jsonrpc_request(
    request: dict[str, Any],
    *,
    include_write_tools: bool = False,
) -> dict[str, Any]:
    """Handle a minimal MCP JSON-RPC request for compatibility smoke tests."""
    method = request.get("method")
    request_id = request.get("id")
    if method == "initialize":
        return _jsonrpc_result(
            request_id,
            {
                "protocolVersion": mcp_server_manifest().protocol_version,
                "serverInfo": {"name": "craik", "version": "0.12.0"},
                "capabilities": {"tools": {}, "resources": {}},
            },
        )
    if method == "tools/list":
        manifest = mcp_server_manifest(include_write_tools=include_write_tools)
        return _jsonrpc_result(
            request_id,
            {
                "tools": [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "operator_authenticated": {"type": "boolean"},
                                "policy_gate_approved": {"type": "boolean"},
                                "receipt_id": {"type": "string"},
                            },
                        },
                    }
                    for tool in manifest.tools
                ]
            },
        )
    if method == "tools/call":
        params = request.get("params", {})
        if not isinstance(params, dict):
            return _jsonrpc_error(request_id, -32602, "params must be an object")
        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            return _jsonrpc_error(request_id, -32602, "arguments must be an object")
        decision = mcp_tool_policy_result(
            str(params.get("name", "")),
            operator_authenticated=bool(arguments.get("operator_authenticated", False)),
            policy_gate_approved=bool(arguments.get("policy_gate_approved", False)),
            receipt_id=arguments.get("receipt_id"),
            include_write_tools=include_write_tools,
        )
        if not decision.allowed:
            return _jsonrpc_error(
                request_id,
                -32001,
                decision.reason,
                decision.model_dump(mode="json"),
            )
        return _jsonrpc_result(
            request_id,
            {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(decision.model_dump(mode="json"), sort_keys=True),
                    }
                ],
                "isError": False,
            },
        )
    return _jsonrpc_error(request_id, -32601, f"unsupported MCP method: {method}")


def handle_mcp_jsonrpc_lines(
    lines: Iterable[str],
    *,
    include_write_tools: bool = False,
) -> list[str]:
    """Handle newline-delimited JSON-RPC requests."""
    responses: list[str] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as error:
            responses.append(json.dumps(_jsonrpc_error(None, -32700, f"invalid JSON: {error.msg}")))
            continue
        if not isinstance(request, dict):
            responses.append(json.dumps(_jsonrpc_error(None, -32600, "request must be an object")))
            continue
        responses.append(
            json.dumps(
                handle_mcp_jsonrpc_request(request, include_write_tools=include_write_tools),
                sort_keys=True,
            )
        )
    return responses


def import_mcp_client_config(path: Path) -> MCPClientImportResult:
    """Import MCP client config from a redacted JSON file."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    clients: list[MCPClientConfig] = []
    warnings: list[str] = []
    if isinstance(payload, dict) and "mcpServers" in payload:
        servers = payload["mcpServers"]
        if not isinstance(servers, dict):
            raise ValueError("mcpServers must be an object")
        for server_name, server_payload in servers.items():
            if not isinstance(server_payload, dict):
                warnings.append(f"skipped MCP server {server_name}: config must be an object")
                continue
            clients.append(_client_from_external_server(server_name, server_payload))
        return MCPClientImportResult(clients=clients, warnings=warnings)
    if isinstance(payload, dict):
        client = MCPClientConfig.model_validate(_redact_client_payload(payload))
        return MCPClientImportResult(clients=[client])
    raise ValueError("MCP client config must be a JSON object")


def export_mcp_client_config(client: MCPClientConfig) -> dict[str, Any]:
    """Export MCP client config without inline secret values."""
    payload = client.model_dump(mode="json")
    payload["metadata"] = _redact_mapping(payload.get("metadata", {}))
    payload["secret_ref_names"] = sorted(set(client.secret_ref_names))
    return payload


def _export_status(tool: MCPToolDescriptor) -> str:
    decision = mcp_export_decision(
        MCPExportSurface(
            id=tool.name,
            name=tool.title,
            stability="stable",
            capabilities=tool.capabilities,
            requires_capability_grant=tool.requires_policy_gate,
            requires_receipts=tool.requires_receipt,
            docs_ref="docs/reference/mcp-export-boundary.md",
        )
    )
    return decision.status


def _required_tool_controls(tool: MCPToolDescriptor) -> list[str]:
    controls = ["operator_auth", "redaction"]
    if tool.requires_policy_gate:
        controls.append("policy_gate")
    if tool.requires_receipt:
        controls.append("receipts")
    return controls


def _client_from_external_server(server_name: str, payload: dict[str, Any]) -> MCPClientConfig:
    command = payload.get("command")
    url = payload.get("url")
    env = payload.get("env", {})
    args = payload.get("args", [])
    secret_ref_names = sorted(
        key for key in env if isinstance(key, str) and _is_secret_key(key)
    ) if isinstance(env, dict) else []
    if isinstance(command, str) and command.strip():
        return MCPClientConfig.model_validate(
            {
                "id": f"mcp_client_{_slug(server_name)}",
                "name": server_name,
                "transport": "stdio",
                "server_ref": f"mcp_server_{_slug(server_name)}",
                "command_ref": command,
                "config_refs": [str(arg) for arg in args if not _looks_secret(str(arg))],
                "secret_ref_names": secret_ref_names,
                "metadata": {"import_source": "mcpServers"},
                "docs": ["docs/reference/mcp-client.md"],
            }
        )
    if isinstance(url, str) and url.strip():
        return MCPClientConfig.model_validate(
            {
                "id": f"mcp_client_{_slug(server_name)}",
                "name": server_name,
                "transport": "http",
                "server_ref": f"mcp_server_{_slug(server_name)}",
                "endpoint_ref": url,
                "secret_ref_names": secret_ref_names,
                "metadata": {"import_source": "mcpServers"},
                "docs": ["docs/reference/mcp-client.md"],
            }
        )
    raise ValueError(f"MCP server {server_name} requires command or url")


def _redact_client_payload(payload: dict[str, Any]) -> dict[str, Any]:
    redacted = dict(payload)
    redacted["metadata"] = _redact_mapping(redacted.get("metadata", {}))
    return redacted


def _redact_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    redacted: dict[str, Any] = {}
    for key, item in value.items():
        if _is_secret_key(str(key)):
            redacted[str(key)] = "<redacted>"
        elif isinstance(item, dict):
            redacted[str(key)] = _redact_mapping(item)
        elif isinstance(item, list):
            redacted[str(key)] = [
                "<redacted>" if _looks_secret(str(part)) else part for part in item
            ]
        else:
            redacted[str(key)] = "<redacted>" if _looks_secret(str(item)) else item
    return redacted


def _is_secret_key(value: str) -> bool:
    normalized = value.lower().replace("-", "_")
    return any(token in normalized for token in SECRET_KEY_TOKENS)


def _looks_secret(value: str) -> bool:
    normalized = value.lower()
    return any(token in normalized for token in ("token=", "api_key=", "password=", "secret="))


def _slug(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_") or "server"


def _jsonrpc_result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _jsonrpc_error(
    request_id: Any,
    code: int,
    message: str,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}
