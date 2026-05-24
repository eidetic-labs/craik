from __future__ import annotations

import json
from pathlib import Path

from craik.runtime.paths import ensure_craik_home
from craik.runtime.shell.slash_commands import dispatch_slash_command


def _env(tmp_path: Path) -> dict[str, str]:
    return {"CRAIK_HOME": str(tmp_path / ".craik")}


def _write_clients(env: dict[str, str], clients: list[dict[str, object]]) -> None:
    path = ensure_craik_home(env).state / "mcp" / "clients.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"clients": clients}), encoding="utf-8")


def _client(client_id: str = "mcp_client_github") -> dict[str, object]:
    return {
        "id": client_id,
        "name": "github-tools",
        "transport": "stdio",
        "server_ref": "mcp_server_github",
        "command_ref": "github-mcp",
        "config_refs": [],
        "metadata": {
            "tools": [
                {
                    "name": "github.pr.create",
                    "effect": "write",
                    "requires_auth": True,
                    "requires_policy_gate": True,
                    "description": "Create a new pull request.",
                },
                {
                    "name": "github.issues.list",
                    "effect": "read",
                    "requires_auth": True,
                    "requires_policy_gate": False,
                    "description": "List issues.",
                },
            ]
        },
    }


def test_mcp_slash_command_empty_state(tmp_path: Path) -> None:
    result = dispatch_slash_command("/mcp", env=_env(tmp_path))

    assert result.exit_code == 0
    assert "No MCP clients configured" in result.text


def test_mcp_slash_command_renders_summary_and_totals(tmp_path: Path) -> None:
    env = _env(tmp_path)
    _write_clients(env, [_client(), {**_client("mcp_client_docs"), "name": "docs"}])

    result = dispatch_slash_command("/mcp", env=env)

    assert "[mcp_client_github] github-tools" in result.text
    assert "[mcp_client_docs] docs" in result.text
    assert "[total] 2 clients, 4 tools" in result.text


def test_mcp_slash_command_verbose_filters_client_and_tool(tmp_path: Path) -> None:
    env = _env(tmp_path)
    _write_clients(env, [_client()])

    result = dispatch_slash_command(
        "/mcp verbose mcp_client_github github.pr.create",
        env=env,
    )

    assert "policy: grant required, receipt required, redaction required" in result.text
    assert "github.pr.create" in result.text
    assert "github.issues.list" not in result.text
    assert "requires_policy_gate: yes" in result.text


def test_mcp_slash_command_marks_stale_config_refs(tmp_path: Path) -> None:
    env = _env(tmp_path)
    _write_clients(
        env,
        [{**_client(), "config_refs": [str(tmp_path / "missing.json")]}],
    )

    result = dispatch_slash_command("/mcp verbose", env=env)

    assert "[unreadable]" in result.text
    assert "missing.json" in result.text


def test_mcp_slash_command_json_output(tmp_path: Path) -> None:
    env = _env(tmp_path)
    _write_clients(env, [_client()])

    result = dispatch_slash_command("/mcp --json", env=env)
    payload = json.loads(result.text)

    assert payload["total_clients"] == 1
    assert payload["total_tools"] == 2
    assert payload["clients"][0]["tools"][0]["name"] == "github.pr.create"
