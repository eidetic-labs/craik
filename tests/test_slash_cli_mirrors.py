from __future__ import annotations

from craik.runtime.shell.contract_runtime.registry_provider import get_tui_registry

REQUIRED_CLI_MIRRORS = {
    "/auth": "auth",
    "/doctor": "doctor",
    "/gateway": "gateway",
    "/handoffs": "handoffs",
    "/memory": "memory",
    "/model": "model",
    "/note": "note",
    "/provider": "provider",
    "/receipts": "receipts",
    "/resume": "resume",
    "/run": "run prompt",
    "/sessions": "sessions",
    "/skills": "skills",
    "/status": "status",
}


def test_backend_affecting_slash_commands_have_cli_mirror_policy() -> None:
    registry = get_tui_registry()
    cli_commands = {entry.command_name for entry in registry.inventory}

    missing_cli = sorted(
        f"{slash_name} -> craik {cli_name}"
        for slash_name, cli_name in REQUIRED_CLI_MIRRORS.items()
        if cli_name not in cli_commands
    )

    assert missing_cli == []
