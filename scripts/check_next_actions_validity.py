"""Verify literal NextAction commands resolve to registered slash commands."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from craik.cli import app  # noqa: E402
from craik.runtime.contract.auto_registry import AutoSlashRegistry  # noqa: E402
from craik.runtime.shell.contract_runtime.registry_provider import get_tui_slash_specs  # noqa: E402


def main() -> int:
    failures = next_action_validity_failures(ROOT, slash_names=_registered_slash_names())
    if failures:
        print("NextAction validity guard failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("NextAction validity guard passed.")
    return 0


def next_action_validity_failures(root: Path, slash_names: set[str]) -> list[str]:
    """Return literal NextAction.command values whose first slash token is unknown."""
    failures: list[str] = []
    for path in sorted((root / "src" / "craik").rglob("*.py")):
        relative = path.relative_to(root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or _name(node.func) != "NextAction":
                continue
            command = _keyword_value(node, "command")
            if command is None:
                failures.append(f"{relative}:{node.lineno} NextAction must declare command")
                continue
            if not isinstance(command, ast.Constant) or not isinstance(command.value, str):
                failures.append(
                    f"{relative}:{_line_number(command)} "
                    "NextAction.command must be a string literal"
                )
                continue
            if not _command_resolves(command.value, slash_names):
                failures.append(
                    f"{relative}:{_line_number(command)} NextAction.command={command.value!r} "
                    "does not resolve to a registered slash command"
                )
    return failures


def _registered_slash_names() -> set[str]:
    auto_names = {spec.name for spec in AutoSlashRegistry.from_typer(app).slash_specs}
    registry_specs = get_tui_slash_specs()
    canonical_names = {spec.name for spec in registry_specs}
    alias_names = {
        f"/{alias}"
        for spec in registry_specs
        for alias in spec.aliases
    }
    return auto_names | canonical_names | alias_names


def _command_resolves(command: str, slash_names: set[str]) -> bool:
    tokens = command.strip().split()
    if not tokens or not tokens[0].startswith("/"):
        return False
    if tokens[0] in slash_names:
        return True
    if len(tokens) > 1:
        return " ".join(tokens[:2]) in slash_names
    return False


def _keyword_value(node: ast.Call, keyword: str) -> ast.AST | None:
    for candidate in node.keywords:
        if candidate.arg == keyword:
            return candidate.value
    return None


def _name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def _line_number(node: ast.AST) -> int:
    return getattr(node, "lineno", 0)


if __name__ == "__main__":
    raise SystemExit(main())
