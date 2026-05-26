"""Validate CLI/TUI command metadata exported by the auto registry."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import typer

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from craik.cli import app  # noqa: E402
from craik.runtime.contract.auto_registry import AutoSlashRegistry  # noqa: E402

LEGACY_COMMAND_MARKER = "craik-legacy-command:"
LEGACY_MARKER_FILES: tuple[str, ...] = (
    "src/craik/cli_auth.py",
    "src/craik/cli_shell.py",
    "src/craik/cli_onboarding.py",
    "src/craik/cli_status.py",
)


def main() -> int:
    failures = [
        *cli_tui_contract_failures(AutoSlashRegistry.from_typer(app)),
        *legacy_command_marker_failures(ROOT),
    ]
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


def legacy_command_marker_failures(root: Path) -> list[str]:
    """Require explicit markers for scoped Typer commands left outside craik_command."""
    failures: list[str] = []
    for relative in LEGACY_MARKER_FILES:
        path = root / relative
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if not _has_typer_command_decorator(node):
                continue
            if _has_craik_command_decorator(node):
                continue
            if _has_legacy_marker(lines, node):
                continue
            failures.append(
                f"{relative}:{node.lineno} {node.name} is a Typer command without "
                f"@craik_command or {LEGACY_COMMAND_MARKER} marker"
            )
    return failures


def registry_from_app(test_app: typer.Typer) -> AutoSlashRegistry:
    """Build a registry for fixture apps without importing the production CLI."""
    return AutoSlashRegistry.from_typer(test_app)


def _has_typer_command_decorator(node: ast.FunctionDef) -> bool:
    return any(
        isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Attribute)
        and decorator.func.attr == "command"
        for decorator in node.decorator_list
    )


def _has_craik_command_decorator(node: ast.FunctionDef) -> bool:
    for decorator in node.decorator_list:
        candidate = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(candidate, ast.Name) and candidate.id == "craik_command":
            return True
    return False


def _has_legacy_marker(lines: list[str], node: ast.FunctionDef) -> bool:
    first_decorator = min(
        (decorator.lineno for decorator in node.decorator_list),
        default=node.lineno,
    )
    start = max(0, first_decorator - 4)
    end = max(0, first_decorator - 1)
    return any(LEGACY_COMMAND_MARKER in line for line in lines[start:end])


if __name__ == "__main__":
    raise SystemExit(main())
