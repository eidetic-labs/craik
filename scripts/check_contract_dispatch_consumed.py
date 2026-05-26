#!/usr/bin/env python3
"""Verify TUI runtime entry points consume the contract dispatcher."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SHELL = ROOT / "src" / "craik" / "runtime" / "shell"

TUI_ENTRY_POINTS = {
    "textual_app.py",
    "tui.py",
    "agent_shell.py",
}


def _module_imports(tree: ast.Module) -> set[tuple[str, str]]:
    imports: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                imports.add((node.module, alias.name))
    return imports


def main() -> int:
    failures: list[str] = []
    for entry_point in TUI_ENTRY_POINTS:
        path = RUNTIME_SHELL / entry_point
        if not path.exists():
            failures.append(f"{entry_point}: expected TUI entry point file does not exist")
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = _module_imports(tree)
        if not any(module == "craik.runtime.contract.dispatch" for module, _ in imports):
            failures.append(
                f"{path.relative_to(ROOT)}: TUI entry point must import from "
                "craik.runtime.contract.dispatch"
            )

    for path in RUNTIME_SHELL.rglob("*.py"):
        if path.name == "slash_commands.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for module, name in _module_imports(tree):
            if (
                module == "craik.runtime.shell.slash_commands"
                and name == "dispatch_slash_command"
            ):
                failures.append(
                    f"{path.relative_to(ROOT)}: imports legacy dispatch_slash_command"
                )

    if failures:
        print("Contract dispatch consumption guard FAILED:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print("Contract dispatch consumption guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
