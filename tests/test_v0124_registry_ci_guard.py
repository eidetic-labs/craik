from __future__ import annotations

import subprocess
import sys
from importlib import util
from pathlib import Path

from craik.runtime.shell.slash_command_schema import (
    SlashCommandSpec,
    is_known_command_name,
    slash_command_spec_by_name,
    slash_command_specs,
)
from craik.runtime.shell.slash_command_schema.results import SlashCommandResult

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_slash_command_registry.py"
spec = util.spec_from_file_location("check_slash_command_registry", SCRIPT)
assert spec is not None
check_slash_command_registry = util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(check_slash_command_registry)
registry_failures = check_slash_command_registry.registry_failures


def test_slash_command_schema_covers_runtime_registry() -> None:
    assert registry_failures(slash_command_specs()) == []


def test_slash_command_lookup_accepts_bare_slash_and_alias_names() -> None:
    assert slash_command_spec_by_name("provider") is not None
    assert slash_command_spec_by_name("/provider") is not None
    assert slash_command_spec_by_name("quit") is not None
    assert is_known_command_name("/quit")
    assert not is_known_command_name("missing-command")


def test_registry_guard_reports_schema_without_runtime_command() -> None:
    specs = [
        *slash_command_specs(),
        SlashCommandSpec(
            name="/missing",
            summary="Missing runtime command.",
            usage="/missing",
            payload_shape="markdown",
            help="Synthetic command used by the registry guard test.",
        ),
    ]

    failures = registry_failures(specs)

    assert "schema entries without runtime commands: missing" in failures


def test_registry_guard_reports_runtime_metadata_mismatch() -> None:
    provider = slash_command_spec_by_name("provider")
    assert provider is not None
    changed = provider.model_copy(update={"usage": "/provider changed"})
    specs = [changed if spec.command_name == "provider" else spec for spec in slash_command_specs()]

    failures = registry_failures(specs)

    assert any("/provider: runtime usage" in failure for failure in failures)


def test_registry_guard_reports_structured_payload_shape_mismatch(monkeypatch) -> None:
    def _unstructured_dispatch(
        _text: str,
        *,
        env: dict[str, str] | None = None,
    ) -> SlashCommandResult:
        return SlashCommandResult("plain text", command_name="provider")

    monkeypatch.setattr(
        check_slash_command_registry,
        "dispatch_slash_command",
        _unstructured_dispatch,
    )

    failures = registry_failures(slash_command_specs())

    assert any("/provider: dispatch payload_shape" in failure for failure in failures)
    assert "/provider: dispatch returned no structured payload" in failures


def test_registry_guard_script_passes_on_current_tree() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_slash_command_registry.py"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Slash command registry checks passed." in result.stdout
