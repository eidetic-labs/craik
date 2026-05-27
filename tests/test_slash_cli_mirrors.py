from __future__ import annotations

from craik.cli import app
from craik.runtime.contract.auto_registry import AutoSlashRegistry
from craik.runtime.shell.contract_runtime.registry_provider import get_tui_registry

REQUIRED_CLI_MIRRORS = {
    "/auth": "auth status",
    "/doctor": "doctor",
    "/gateway": "gateway status",
    "/handoffs": "handoff list",
    "/memory": "memory list",
    "/model": "model status",
    "/note": "note",
    "/provider": "provider list",
    "/receipts": "receipts list",
    "/resume": "session resume",
    "/run": "run prompt",
    "/sessions": "session list",
    "/skills": "skills list",
    "/status": "status",
}


def test_backend_affecting_slash_commands_have_cli_mirror_policy() -> None:
    cli_commands = {entry.command_name for entry in AutoSlashRegistry.from_typer(app).inventory}

    missing_cli = sorted(
        f"{slash_name} -> craik {cli_name}"
        for slash_name, cli_name in REQUIRED_CLI_MIRRORS.items()
        if cli_name not in cli_commands
    )

    assert missing_cli == []


def test_backend_affecting_slash_specs_record_cli_mirrors() -> None:
    registry = get_tui_registry()

    missing_metadata = sorted(
        slash_name
        for slash_name, cli_name in REQUIRED_CLI_MIRRORS.items()
        if (spec := registry.spec_by_name(slash_name)) is None
        or spec.cli_mirror != cli_name
    )

    assert missing_metadata == []
