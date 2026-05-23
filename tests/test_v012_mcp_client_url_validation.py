from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from craik.cli import app
from craik.runtime.sandbox.mcp_client import MCPClientConfig

runner = CliRunner()


def _client(**overrides: object) -> MCPClientConfig:
    payload = {
        "id": "mcp_client_fixture",
        "name": "Fixture MCP Client",
        "transport": "http",
        "server_ref": "mcp_server_fixture",
        "endpoint_ref": "https://example.test/mcp",
        "secret_ref_names": ["MCP_FIXTURE_TOKEN"],
        "policy_envelope_id": "policy_mcp_fixture",
    }
    payload.update(overrides)
    return MCPClientConfig.model_validate(payload)


@pytest.mark.parametrize(
    "endpoint",
    [
        "file:///etc/passwd",
        "gopher://example.test/mcp",
        "javascript:alert(1)",
        "data:text/plain,hello",
        "ftp://example.test/mcp",
    ],
)
def test_mcp_client_rejects_non_http_url_schemes(endpoint: str) -> None:
    with pytest.raises(ValidationError, match="endpoint_ref must use http or https"):
        _client(endpoint_ref=endpoint)


@pytest.mark.parametrize("endpoint", ["http://example.test/mcp", "https://example.test/mcp"])
def test_mcp_client_accepts_http_url_schemes(endpoint: str) -> None:
    assert _client(endpoint_ref=endpoint).endpoint_ref == endpoint


def test_mcp_client_accepts_stdio_command_ref_without_scheme() -> None:
    client = _client(
        transport="stdio",
        endpoint_ref=None,
        command_ref="MCP_FIXTURE_COMMAND",
    )

    assert client.command_ref == "MCP_FIXTURE_COMMAND"


def test_mcp_client_import_cli_rejects_file_url_endpoint(tmp_path: Path) -> None:
    path = tmp_path / "mcp.json"
    path.write_text(
        json.dumps({"mcpServers": {"bad": {"url": "file:///etc/passwd"}}}),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["mcp", "client", "import", "--path", str(path)])

    assert result.exit_code != 0
    assert "endpoint_ref must use http or https" in result.output
