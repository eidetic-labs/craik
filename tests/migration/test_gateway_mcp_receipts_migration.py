"""Migration coverage for gateway, MCP, and receipt command contract surfaces."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console
from typer.testing import CliRunner

from craik.cli import app
from craik.runtime.contract import CommandResult
from craik.runtime.contract.auto_registry import AutoSlashRegistry
from craik.runtime.contract.format import format_command_result
from craik.runtime.sandbox.mcp_commands import (
    mcp_client_export_result,
    mcp_client_import_result,
    mcp_discovery_result,
    mcp_server_manifest_result,
)
from craik.runtime.services.gateway_commands import gateway_status_result
from craik.runtime.shell.slash_commands import dispatch_slash_command
from craik.runtime.work.receipts import receipts_list_result

runner = CliRunner()


def _capture(renderable: Any, *, width: int = 80) -> str:
    console = Console(color_system=None, force_terminal=False, record=True, width=width)
    console.print(renderable)
    return console.export_text()


def _rstrip_lines(value: str) -> str:
    return "\n".join(line.rstrip() for line in value.splitlines())


def test_gateway_cli_and_slash_share_status_payload(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "home")}

    cli = runner.invoke(app, ["gateway", "status"], env=env)
    slash = dispatch_slash_command("/gateway status", env=env)

    assert cli.exit_code == 0, cli.output
    assert json.loads(cli.stdout) == json.loads(slash.text)


def test_gateway_receipt_and_mcp_helpers_return_command_results(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "home")}

    gateway = gateway_status_result(env)
    receipts = receipts_list_result(env=env)
    mcp = mcp_discovery_result(env)
    manifest = mcp_server_manifest_result()

    assert isinstance(gateway, CommandResult)
    assert gateway.shape == "kv"
    assert receipts.shape == "card_list"
    assert mcp.shape == "card_list"
    assert manifest.shape == "tree"


def test_mcp_client_import_and_export_return_command_results(tmp_path: Path) -> None:
    config = tmp_path / "mcp.json"
    config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "local": {
                        "command": "craik-mcp",
                        "args": ["serve"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    imported = mcp_client_import_result(config)
    exported = mcp_client_export_result(config)

    assert imported.shape == "card_list"
    assert exported.payload["clients"][0]["id"] == "mcp_client_local"


def test_gateway_mcp_and_receipt_commands_are_registered() -> None:
    registry = AutoSlashRegistry.from_typer(app)

    assert registry.spec_by_name("/gateway") is not None
    assert registry.spec_by_name("/gateway-logs") is not None
    assert registry.spec_by_name("/gateway-doctor") is not None
    assert registry.spec_by_name("/receipts-list") is not None
    assert registry.spec_by_name("/receipts-show") is not None
    assert registry.spec_by_name("/receipts-verify") is not None
    assert registry.spec_by_name("/mcp-server-manifest") is not None
    assert registry.spec_by_name("/mcp-client-import") is not None
    assert registry.spec_by_name("/mcp-client-export") is not None


def test_mcp_jsonrpc_handler_is_documented_tui_exempt() -> None:
    registry = AutoSlashRegistry.from_typer(app)
    entry = next(item for item in registry.inventory if item.command_name == "mcp server handle")

    assert entry.is_slash is False
    assert entry.exempt_reason is not None
    assert "JSON-RPC" in entry.exempt_reason


def test_gateway_tui_snapshot() -> None:
    result = CommandResult(
        payload={
            "configured": False,
            "enabled": False,
            "status": "not configured",
            "pid": None,
            "pid_file": "/tmp/craik/state/gateway.pid",
            "pid_file_exists": False,
            "stale_pid": False,
            "bind": None,
            "log_file": None,
        },
        shape="kv",
    )
    output = _capture(format_command_result(result, kind="tui"), width=80)

    snapshot = (
        Path(__file__).resolve().parents[1]
        / "snapshots"
        / "slash"
        / "gateway"
        / "width-80.txt"
    )
    assert _rstrip_lines(output) == _rstrip_lines(snapshot.read_text(encoding="utf-8"))


def test_receipts_tui_snapshot() -> None:
    output = _capture(
        format_command_result(
            CommandResult(payload=[], shape="card_list", empty_state_message="No receipts."),
            kind="tui",
        ),
        width=80,
    )

    snapshot = (
        Path(__file__).resolve().parents[1]
        / "snapshots"
        / "slash"
        / "receipts"
        / "width-80.txt"
    )
    assert _rstrip_lines(output) == _rstrip_lines(snapshot.read_text(encoding="utf-8"))
