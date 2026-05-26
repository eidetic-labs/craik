"""Verify migrated command output has JSON and text format coverage.

Craik v0.12.8 routes migrated CLI commands through ``emit_command_result``.
That helper selects text when stdout is a TTY and JSON when stdout is piped,
rather than exposing a per-command ``--format`` flag. This guard pins that
centralized dual-output contract so every migrated command benefits from the
same tested formatter.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    failures = format_coverage_failures(ROOT)
    if failures:
        print("Format coverage guard failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("Format coverage guard passed.")
    return 0


def format_coverage_failures(root: Path) -> list[str]:
    """Return gaps in centralized CommandResult format coverage."""
    failures: list[str] = []
    failures.extend(_cli_output_contract_failures(root))
    failures.extend(_format_test_failures(root))
    return failures


def _cli_output_contract_failures(root: Path) -> list[str]:
    path = root / "src" / "craik" / "cli_output.py"
    relative = path.relative_to(root).as_posix()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    calls = {_name(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}
    if "detect_default_format" not in calls:
        return [f"{relative}: emit_command_result must call detect_default_format()"]
    if "format_command_result" not in calls:
        return [f"{relative}: emit_command_result must call format_command_result()"]
    source = path.read_text(encoding="utf-8")
    failures: list[str] = []
    if '"json"' not in source:
        failures.append(f"{relative}: missing JSON output branch")
    if "typer.echo" not in source:
        failures.append(f"{relative}: missing CLI echo emission")
    return failures


def _format_test_failures(root: Path) -> list[str]:
    path = root / "tests" / "contract" / "test_format.py"
    relative = path.relative_to(root).as_posix()
    if not path.exists():
        return [f"{relative}: missing centralized format contract tests"]
    tree = ast.parse(path.read_text(encoding="utf-8"))
    format_kinds = _format_kinds_under_test(tree)
    failures: list[str] = []
    for required in ("json", "text", "tui"):
        if required not in format_kinds:
            failures.append(f"{relative}: missing format_command_result kind={required!r} test")
    test_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    }
    if "test_detect_default_format_tty" not in test_names:
        failures.append(f"{relative}: missing TTY default-format test")
    if "test_detect_default_format_non_tty" not in test_names:
        failures.append(f"{relative}: missing non-TTY default-format test")
    return failures


def _format_kinds_under_test(tree: ast.AST) -> set[str]:
    kinds: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or _name(node.func) != "format_command_result":
            continue
        for keyword in node.keywords:
            if (
                keyword.arg == "kind"
                and isinstance(keyword.value, ast.Constant)
                and isinstance(keyword.value.value, str)
            ):
                kinds.add(keyword.value.value)
    return kinds


def _name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


if __name__ == "__main__":
    raise SystemExit(main())
