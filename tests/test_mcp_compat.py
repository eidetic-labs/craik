import json

from typer.testing import CliRunner

from craik.cli import app
from craik.runtime.sandbox.mcp_compat import (
    export_mcp_client_config,
    handle_mcp_jsonrpc_request,
    import_mcp_client_config,
    mcp_server_manifest,
    mcp_tool_policy_result,
)

runner = CliRunner()


def test_mcp_server_manifest_exposes_safe_read_surfaces_first() -> None:
    manifest = mcp_server_manifest()

    assert [tool.name for tool in manifest.tools] == [
        "craik.case.read",
        "craik.memory.search",
        "craik.receipts.list",
    ]
    assert all(tool.effect == "read" for tool in manifest.tools)
    assert set(manifest.compatibility_matrix.values()) == {"exportable"}


def test_mcp_tool_policy_blocks_unauthenticated_and_ungated_write_calls() -> None:
    unauthenticated = mcp_tool_policy_result(
        "craik.case.read",
        operator_authenticated=False,
    )
    assert unauthenticated.allowed is False
    assert unauthenticated.reason == "active operator authentication required"

    ungated_write = mcp_tool_policy_result(
        "craik.memory.propose",
        operator_authenticated=True,
        include_write_tools=True,
    )
    assert ungated_write.allowed is False
    assert ungated_write.reason == "write MCP tools require an approved policy gate"

    allowed_write = mcp_tool_policy_result(
        "craik.memory.propose",
        operator_authenticated=True,
        policy_gate_approved=True,
        receipt_id="receipt_mcp_fixture",
        include_write_tools=True,
    )
    assert allowed_write.allowed is True
    assert allowed_write.receipt_id == "receipt_mcp_fixture"


def test_mcp_jsonrpc_lists_tools_and_denies_policy_failures() -> None:
    tools = handle_mcp_jsonrpc_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert tools["result"]["tools"][0]["name"] == "craik.case.read"

    denied = handle_mcp_jsonrpc_request(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "craik.case.read",
                "arguments": {"operator_authenticated": False},
            },
        }
    )
    assert denied["error"]["code"] == -32001
    assert denied["error"]["data"]["required_controls"] == [
        "operator_auth",
        "redaction",
        "policy_gate",
        "receipts",
    ]


def test_mcp_client_import_redacts_external_config(tmp_path) -> None:
    config_path = tmp_path / "mcp.json"
    config_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "Search Server": {
                        "command": "mcp-search",
                        "args": ["--profile", "default", "--token=raw"],
                        "env": {"MCP_TOKEN": "raw-secret-value"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    result = import_mcp_client_config(config_path)
    client = result.clients[0]
    exported = export_mcp_client_config(client)

    assert client.id == "mcp_client_search_server"
    assert client.transport == "stdio"
    assert client.secret_ref_names == ["MCP_TOKEN"]
    assert "--token=raw" not in client.config_refs
    assert "raw-secret-value" not in json.dumps(exported)


def test_mcp_cli_manifest_and_client_import(tmp_path) -> None:
    manifest_result = runner.invoke(app, ["mcp", "server", "manifest"])
    assert manifest_result.exit_code == 0
    assert json.loads(manifest_result.stdout)["tools"][0]["name"] == "craik.case.read"

    config_path = tmp_path / "mcp.json"
    config_path.write_text(
        json.dumps({"mcpServers": {"local": {"url": "https://example.invalid/mcp"}}}),
        encoding="utf-8",
    )
    import_result = runner.invoke(app, ["mcp", "client", "import", "--path", str(config_path)])

    assert import_result.exit_code == 0
    assert json.loads(import_result.stdout)["clients"][0]["endpoint_ref"] == (
        "https://example.invalid/mcp"
    )


def test_mcp_cli_import_validation_error_is_operator_readable(tmp_path) -> None:
    config_path = tmp_path / "mcp.json"
    config_path.write_text(
        json.dumps({"mcpServers": {"bad": {"url": "file:///tmp/socket"}}}),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["mcp", "client", "import", "--path", str(config_path)])

    assert result.exit_code != 0
    assert "MCP config validation failed:" in result.output
    assert "endpoint_ref" in result.output
    assert "input_value=" not in result.output
    assert "pydantic.dev" not in result.output
