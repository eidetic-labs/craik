"""Validate CLI/TUI command metadata exported by the auto registry."""

from __future__ import annotations

import sys
from pathlib import Path

import typer

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from craik.cli import app  # noqa: E402
from craik.runtime.contract.auto_registry import AutoSlashRegistry  # noqa: E402


def main() -> int:
    failures = cli_tui_contract_failures(AutoSlashRegistry.from_typer(app))
    if failures:
        print("CLI/TUI contract guard failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("CLI/TUI contract guard passed.")
    return 0


def cli_tui_contract_failures(registry: AutoSlashRegistry) -> list[str]:
    """Return metadata consistency failures for decorated Typer commands."""
    failures: list[str] = []
    slash_entries = [entry for entry in registry.inventory if entry.is_slash]
    slash_callbacks: dict[str, set[int]] = {}
    for entry in slash_entries:
        if entry.slash_name is None or entry.callback is None:
            continue
        slash_callbacks.setdefault(entry.slash_name, set()).add(id(entry.callback))
    spec_names = {spec.name for spec in registry.slash_specs}

    for slash_name, callback_ids in sorted(slash_callbacks.items()):
        if len(callback_ids) > 1:
            failures.append(
                f"{slash_name}: duplicate slash name maps to {len(callback_ids)} callbacks"
            )

    for entry in registry.inventory:
        if entry.metadata is None:
            continue
        if entry.metadata.tui_eligible:
            if entry.slash_name is None:
                failures.append(f"{entry.command_name}: TUI-eligible command has no slash name")
            elif entry.slash_name not in spec_names:
                failures.append(
                    f"{entry.command_name}: slash name {entry.slash_name} has no derived spec"
                )
            continue
        if not entry.exempt_reason:
            failures.append(f"{entry.command_name}: TUI-exempt command must include a reason")

    spec_by_name = {spec.name: spec for spec in registry.slash_specs}
    for entry in slash_entries:
        if entry.slash_name is None or entry.metadata is None:
            continue
        spec = spec_by_name.get(entry.slash_name)
        if spec is None:
            continue
        if spec.payload_shape != entry.metadata.payload_shape:
            failures.append(
                f"{entry.command_name}: spec payload shape {spec.payload_shape!r} "
                f"does not match metadata {entry.metadata.payload_shape!r}"
            )
        if not spec.summary.strip():
            failures.append(f"{entry.command_name}: slash spec summary is empty")

    return failures


def registry_from_app(test_app: typer.Typer) -> AutoSlashRegistry:
    """Build a registry for fixture apps without importing the production CLI."""
    return AutoSlashRegistry.from_typer(test_app)


if __name__ == "__main__":
    raise SystemExit(main())
