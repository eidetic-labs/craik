#!/usr/bin/env python3
"""Fail if code consumes the deleted legacy slash-command specs API."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_MODULE = "craik.runtime.shell.slash_command_schema"
LEGACY_NAMES = {
    "SLASH_COMMAND_SPECS",
    "is_known_command_name",
    "slash_command_spec_by_name",
    "slash_command_specs",
}


def scan_root(root: Path) -> list[str]:
    """Return legacy slash-command spec API findings under ``root``."""
    failures: list[str] = []
    for base in (root / "src", root / "tests", root / "scripts"):
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError as error:
                failures.append(
                    f"{path.relative_to(root)}:{error.lineno}: syntax error: {error.msg}"
                )
                continue
            aliases = _legacy_import_aliases(tree)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module == SCHEMA_MODULE:
                    for alias in node.names:
                        if alias.name in LEGACY_NAMES:
                            failures.append(
                                f"{path.relative_to(root)}:{node.lineno}: imports legacy "
                                f"slash-command specs API `{alias.name}`"
                            )
                elif isinstance(node, ast.Name) and node.id in aliases:
                    failures.append(
                        f"{path.relative_to(root)}:{node.lineno}: consumes legacy "
                        f"slash-command specs API `{node.id}`"
                    )
                elif isinstance(node, ast.Attribute) and node.attr in LEGACY_NAMES:
                    failures.append(
                        f"{path.relative_to(root)}:{node.lineno}: consumes legacy "
                        f"slash-command specs API `{node.attr}`"
                    )
    return sorted(set(failures))


def _legacy_import_aliases(tree: ast.AST) -> set[str]:
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == SCHEMA_MODULE:
            for alias in node.names:
                if alias.name in LEGACY_NAMES:
                    aliases.add(alias.asname or alias.name)
    return aliases


def main() -> int:
    failures = scan_root(ROOT)
    if failures:
        print("Slash command specs consumption guard FAILED:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1
    print("Slash command specs consumption guard passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
