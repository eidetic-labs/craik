#!/usr/bin/env python3
"""Verify interactive prompt metadata is consumed in slash dispatch."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DISPATCH_PATH = ROOT / "src" / "craik" / "runtime" / "contract" / "dispatch.py"
REQUIRED_FUNCTION = "intercept_interactive_prompts"
REQUIRED_INVOKER = "invoke_slash_command"
REQUIRED_CALLBACK = "_call_entry"


def validate_dispatch(path: Path = DISPATCH_PATH) -> list[str]:
    """Return findings when dispatch does not apply prompt interception at runtime."""
    display_path = _display_path(path)
    if not path.exists():
        return [f"{display_path}: dispatch module is missing"]
    tree = ast.parse(path.read_text(encoding="utf-8"))
    functions = {
        node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }
    if REQUIRED_FUNCTION not in functions:
        return [
            f"{display_path}: missing `{REQUIRED_FUNCTION}` context manager "
            "for typer.confirm/typer.prompt interception"
        ]
    invoker = functions.get(REQUIRED_INVOKER)
    if invoker is None:
        return [f"{display_path}: missing `{REQUIRED_INVOKER}`"]
    for node in ast.walk(invoker):
        if isinstance(node, ast.With) and _with_intercepts_prompts(node):
            if _with_body_invokes_callback(node):
                return []
            return [
                f"{display_path}:{node.lineno}: `{REQUIRED_FUNCTION}` is "
                f"present but does not wrap `{REQUIRED_CALLBACK}`"
            ]
    return [
        f"{display_path}: `{REQUIRED_FUNCTION}` is not applied in "
        f"`{REQUIRED_INVOKER}`; interactive_prompts metadata would be dead"
    ]


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _with_intercepts_prompts(node: ast.With) -> bool:
    return any(
        isinstance(item.context_expr, ast.Call)
        and _call_name(item.context_expr.func) == REQUIRED_FUNCTION
        for item in node.items
    )


def _with_body_invokes_callback(node: ast.With) -> bool:
    return any(
        isinstance(child, ast.Call) and _call_name(child.func) == REQUIRED_CALLBACK
        for stmt in node.body
        for child in ast.walk(stmt)
    )


def _call_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def main() -> int:
    failures = validate_dispatch()
    if failures:
        print("Interactive prompts runtime guard FAILED:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1
    print("Interactive prompts runtime guard passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
