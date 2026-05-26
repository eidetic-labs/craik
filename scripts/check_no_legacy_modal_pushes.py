#!/usr/bin/env python3
"""Fail if runtime code pushes legacy Textual modal classes."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGACY_MODAL_MODULE = "craik.runtime.shell.textual_modals"
LEGACY_MODAL_NAMES = {
    "ApprovalDecisionModal",
    "AuthCaptureModal",
    "AuthLogoutModal",
    "ModalFlowResult",
    "ReceiptDetailModal",
}


def scan_root(root: Path) -> list[str]:
    """Return legacy modal push/import findings under ``root``."""
    failures: list[str] = []
    src_root = root / "src" / "craik"
    legacy_path = src_root / "runtime" / "shell" / "textual_modals.py"
    if legacy_path.exists():
        failures.append(
            f"{legacy_path.relative_to(root)}: legacy textual_modals.py was reintroduced; "
            "use canonical modal modules under runtime/shell/modals/"
        )
    if not src_root.exists():
        return failures
    for path in src_root.rglob("*.py"):
        if path == legacy_path:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as error:
            failures.append(f"{path.relative_to(root)}:{error.lineno}: syntax error: {error.msg}")
            continue
        aliases = _legacy_modal_aliases(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == LEGACY_MODAL_MODULE:
                failures.append(
                    f"{path.relative_to(root)}:{node.lineno}: imports legacy modal module "
                    f"{LEGACY_MODAL_MODULE}; use runtime/shell/modals/"
                )
            if isinstance(node, ast.Call) and _pushes_legacy_modal(node, aliases):
                failures.append(
                    f"{path.relative_to(root)}:{node.lineno}: pushes a legacy modal; "
                    "use canonical equivalents from runtime/shell/modals/"
                )
    return failures


def _legacy_modal_aliases(tree: ast.AST) -> set[str]:
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == LEGACY_MODAL_MODULE:
            for alias in node.names:
                if alias.name in LEGACY_MODAL_NAMES or alias.name == "*":
                    aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == LEGACY_MODAL_MODULE:
                    aliases.add(alias.asname or alias.name.rsplit(".", 1)[-1])
    return aliases


def _pushes_legacy_modal(node: ast.Call, aliases: set[str]) -> bool:
    if not (
        isinstance(node.func, ast.Attribute)
        and node.func.attr == "push_screen"
        and node.args
        and isinstance(node.args[0], ast.Call)
    ):
        return False
    constructor = node.args[0].func
    if isinstance(constructor, ast.Name):
        return constructor.id in aliases
    if isinstance(constructor, ast.Attribute) and isinstance(constructor.value, ast.Name):
        return constructor.value.id in aliases and constructor.attr in LEGACY_MODAL_NAMES
    return False


def main() -> int:
    failures = scan_root(ROOT)
    if failures:
        print("Legacy modal pushes guard FAILED:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1
    print("Legacy modal pushes guard passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
