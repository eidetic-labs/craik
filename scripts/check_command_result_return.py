"""Require migrated @craik_command callbacks to declare CommandResult returns."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    failures = command_result_return_failures(ROOT)
    if failures:
        print("CommandResult return guard failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("CommandResult return guard passed.")
    return 0


def command_result_return_failures(root: Path) -> list[str]:
    """Return decorated CLI callbacks that do not annotate ``-> CommandResult``."""
    failures: list[str] = []
    for path in sorted((root / "src" / "craik").glob("cli*.py")):
        relative = path.relative_to(root).as_posix()
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or not _has_tui_eligible_craik_command(node):
                continue
            if _annotation_name(node.returns) != "CommandResult":
                failures.append(
                    f"{relative}:{node.lineno} {node.name} must annotate -> CommandResult"
                )
    return failures


def _has_tui_eligible_craik_command(node: ast.FunctionDef) -> bool:
    for decorator in node.decorator_list:
        if _decorator_name(decorator) != "craik_command":
            continue
        if isinstance(decorator, ast.Call):
            for keyword in decorator.keywords:
                if (
                    keyword.arg == "tui_eligible"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is False
                ):
                    return False
        return True
    return False


def _decorator_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
        return _name(node.func)
    return _name(node)


def _annotation_name(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    name = _name(node)
    if name is not None:
        return name.rsplit(".", 1)[-1]
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.rsplit(".", 1)[-1]
    return None


def _name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


if __name__ == "__main__":
    raise SystemExit(main())
